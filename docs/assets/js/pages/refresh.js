const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const STATUS_URL = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/refresh/status.json';

let mounted = false;
let pollTimer = 0;
let passwordMemory = '';
let statusState = null;
let returnFocus = null;
let mountEpoch = 0;
let statusSequence = 0;
let statusController = null;
let startController = null;
let pendingStart = null;
let pollFailures = 0;
let unconfirmedPreviousRun = null;

export const id = 'refresh';
export const title = 'Refresh';
export const sidebarHtml = '';
export const mainHtml = `
  <section class="refresh-page" aria-labelledby="refreshPageTitle">
    <h1 id="refreshPageTitle" class="sr-only">Dashboard refresh</h1>
    <div class="refresh-card">
      <div class="refresh-progress" id="refreshProgress" hidden>
        <div class="refresh-progress-meta">
          <span id="refreshPhase">Starting refresh</span>
          <span id="refreshPercent">0%</span>
        </div>
        <div class="refresh-progress-track"
             id="refreshProgressTrack"
             role="progressbar"
             aria-label="Refresh progress"
             aria-valuemin="0"
             aria-valuemax="100"
             aria-valuenow="0">
          <div class="refresh-progress-fill" id="refreshProgressFill"></div>
        </div>
      </div>
      <button type="button" class="refresh-start-button" id="refreshStartButton">Refresh</button>
      <p class="refresh-last-update" id="refreshLastUpdate">Last update: —</p>
      <p class="refresh-message" id="refreshMessage" aria-live="polite"></p>
    </div>
  </section>
  <div class="refresh-password-modal" id="refreshPasswordModal" hidden
       role="dialog" aria-modal="true" aria-labelledby="refreshPasswordTitle">
    <form class="refresh-password-card" id="refreshPasswordForm">
      <h2 id="refreshPasswordTitle">Manual refresh</h2>
      <label for="refreshPasswordInput">Password</label>
      <input type="password" id="refreshPasswordInput" autocomplete="off" required />
      <p class="refresh-password-error" id="refreshPasswordError" aria-live="assertive"></p>
      <div class="refresh-password-actions">
        <button type="button" class="refresh-modal-cancel" id="refreshPasswordCancel">Cancel</button>
        <button type="submit" class="refresh-modal-confirm">OK</button>
      </div>
    </form>
  </div>`;

function pad(value) {
  return String(value).padStart(2, '0');
}

function formatUtc(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return `${pad(date.getUTCFullYear() % 100)}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}, ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())} UTC`;
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Number.parseInt(value, 10) || 0));
}

function renderStatus(status) {
  if (!mounted || !status) return;
  if (!['idle', 'running', 'succeeded', 'failed', 'starting', 'unconfirmed'].includes(status.state)) {
    throw new Error('Invalid refresh state');
  }
  if (statusState?.state === 'unconfirmed' && status.run_id === unconfirmedPreviousRun) {
    schedulePoll(15000);
    return;
  }
  if (!pendingStart && statusState?.run_id && status.run_id && status.run_id !== statusState.run_id) {
    const newer = Date.parse(status.started_at) > Date.parse(statusState.started_at);
    if (!newer) { schedulePoll(2000); return; }
  }
  if (pendingStart && status.state !== 'starting') {
    const matches = pendingStart.runId
      ? status.run_id === pendingStart.runId
      : status.run_id && status.run_id !== pendingStart.previousRun;
    if (!matches) {
      if (pendingStart.confirmBy && Date.now() >= pendingStart.confirmBy) {
        unconfirmedPreviousRun = pendingStart.previousRun;
        pendingStart = null;
        renderStatus({ ...statusState, state: 'unconfirmed', phase: 'Start not confirmed' });
      } else schedulePoll(2000);
      return;
    }
    pendingStart = null;
  }
  if (statusState?.state === 'running' && status.run_id === statusState.run_id && status.state === 'running') {
    status = { ...status, progress_percent: Math.max(clampPercent(status.progress_percent), clampPercent(statusState.progress_percent)) };
  }
  statusState = status;
  const state = String(status.state || 'idle');
  const running = state === 'running' || state === 'starting';
  const failed = state === 'failed';
  const unconfirmed = state === 'unconfirmed';
  const succeeded = state === 'succeeded';
  const percent = clampPercent(status.progress_percent);
  const progress = document.getElementById('refreshProgress');
  const track = document.getElementById('refreshProgressTrack');
  const fill = document.getElementById('refreshProgressFill');
  const button = document.getElementById('refreshStartButton');
  const message = document.getElementById('refreshMessage');

  document.getElementById('refreshLastUpdate').textContent =
    `Last update: ${formatUtc(status.last_completed_at)}`;
  document.getElementById('refreshPhase').textContent = status.phase || (running ? 'Refreshing' : 'Ready');
  document.getElementById('refreshPercent').textContent = `${percent}%`;
  progress.hidden = !(running || failed || succeeded);
  progress.classList.toggle('refresh-progress-failed', failed);
  progress.classList.toggle('refresh-progress-complete', succeeded);
  track.setAttribute('aria-valuenow', String(percent));
  fill.style.width = `${percent}%`;
  button.disabled = running;
  button.textContent = running ? 'Refreshing…' : failed || unconfirmed ? 'Retry' : 'Refresh';
  message.textContent = unconfirmed
    ? 'Could not confirm that the refresh started. You can retry; an existing run will be reused.'
    : failed
    ? 'The refresh did not complete. The previous snapshots remain active.'
    : succeeded ? 'Refresh completed successfully.' : '';
  schedulePoll(running ? 2000 : 15000);
}

async function fetchStatus(useApiFallback = true) {
  const epoch = mountEpoch;
  const sequence = ++statusSequence;
  statusController?.abort();
  const controller = statusController = new AbortController();
  const current = () => mounted && epoch === mountEpoch && sequence === statusSequence;
  try {
    let payload;
    try {
      const response = await fetch(`${STATUS_URL}?t=${Date.now()}`, { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error(`Status ${response.status}`);
      payload = await response.json();
    } catch (error) {
      if (!useApiFallback || controller.signal.aborted) throw error;
      const response = await fetch(API_URL, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_status: true }), cache: 'no-store', signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Status ${response.status}`);
      payload = (await response.json()).refresh_status;
    }
    if (!current()) return false;
    if (!payload || !['idle', 'running', 'succeeded', 'failed'].includes(payload.state)) throw new Error('Invalid refresh status');
    pollFailures = 0;
    renderStatus(payload);
    return true;
  } catch (_) {
    if (!current() || controller.signal.aborted) return false;
    document.getElementById('refreshMessage').textContent = 'Connection interrupted. Reconnecting to refresh status…';
    schedulePoll(Math.min(30000, 2000 * 2 ** Math.min(++pollFailures, 4)));
    return false;
  } finally {
    if (statusController === controller) statusController = null;
  }
}

function schedulePoll(delay) {
  window.clearTimeout(pollTimer);
  if (!mounted) return;
  pollTimer = window.setTimeout(() => fetchStatus(false), delay);
}

function openPasswordModal() {
  const modal = document.getElementById('refreshPasswordModal');
  const input = document.getElementById('refreshPasswordInput');
  returnFocus = document.activeElement;
  document.getElementById('refreshPasswordError').textContent = '';
  input.value = passwordMemory;
  modal.hidden = false;
  window.requestAnimationFrame(() => {
    input.focus();
    input.select();
  });
}

function closePasswordModal() {
  const modal = document.getElementById('refreshPasswordModal');
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  document.getElementById('refreshPasswordInput').value = '';
  const focusTarget = returnFocus;
  returnFocus = null;
  focusTarget?.focus?.();
}

async function startRefresh(password) {
  if (!mounted || pendingStart) return;
  const epoch = mountEpoch;
  const previousRun = statusState?.run_id || null;
  pendingStart = { previousRun, runId: null };
  statusSequence++;
  statusController?.abort();
  const controller = startController = new AbortController();
  const startTimeout = window.setTimeout(() => controller.abort(), 30000);
  const optimistic = {
    ...(statusState || {}),
    run_id: null,
    state: 'starting',
    progress_percent: 0,
    phase: 'Starting refresh',
  };
  renderStatus(optimistic);
  // Polls may reconnect while the POST is pending, but can never accept the
  // preceding run as completion of this request.
  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Ark-Nova-Refresh-Password': password,
      },
      body: JSON.stringify({ manual_refresh: true }),
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!mounted || epoch !== mountEpoch) return;
    if (response.status === 403) {
      pendingStart = null;
      passwordMemory = '';
      renderStatus({ ...(statusState || {}), state: 'idle', phase: 'Ready' });
      openPasswordModal();
      document.getElementById('refreshPasswordError').textContent = 'Invalid password.';
      return;
    }
    if (!response.ok && response.status !== 409) {
      pendingStart = null;
      renderStatus({ ...statusState, state: 'failed', phase: 'Could not start refresh' });
      return;
    }
    const acknowledgement = await response.json();
    if (!mounted || epoch !== mountEpoch) return;
    const runId = acknowledgement.run_id || acknowledgement.refresh_status?.run_id;
    if (pendingStart && runId) pendingStart.runId = runId;
    if (acknowledgement.refresh_status) renderStatus(acknowledgement.refresh_status);
  } catch (_) {
    if (!mounted || epoch !== mountEpoch) return;
    if (pendingStart) pendingStart.confirmBy = Date.now() + 60000;
    document.getElementById('refreshMessage').textContent = 'Waiting for refresh confirmation…';
  } finally {
    window.clearTimeout(startTimeout);
    if (startController === controller) startController = null;
  }
  if (mounted && epoch === mountEpoch) await fetchStatus(true);
}

function onSubmitPassword(event) {
  event.preventDefault();
  const input = document.getElementById('refreshPasswordInput');
  const password = input.value;
  if (!password) return;
  passwordMemory = password;
  closePasswordModal();
  void startRefresh(password);
}

function onModalKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault();
    closePasswordModal();
    return;
  }
  if (event.key !== 'Tab') return;
  const modal = document.getElementById('refreshPasswordModal');
  const focusable = [...modal.querySelectorAll('input, button')]
    .filter(element => !element.disabled && element.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

export function mount() {
  mountEpoch++;
  mounted = true;
  document.getElementById('refreshStartButton').addEventListener('click', () => {
    if (pendingStart || statusState?.state === 'running') return;
    if (passwordMemory) void startRefresh(passwordMemory);
    else openPasswordModal();
  });
  document.getElementById('refreshPasswordForm').addEventListener('submit', onSubmitPassword);
  document.getElementById('refreshPasswordCancel').addEventListener('click', closePasswordModal);
  document.getElementById('refreshPasswordModal').addEventListener('keydown', onModalKeydown);
  void fetchStatus(true);
}

export function unmount() {
  mounted = false;
  mountEpoch++;
  statusSequence++;
  statusController?.abort();
  startController?.abort();
  statusController = startController = null;
  pendingStart = null;
  pollFailures = 0;
  unconfirmedPreviousRun = null;
  window.clearTimeout(pollTimer);
  pollTimer = 0;
  passwordMemory = '';
  statusState = null;
  returnFocus = null;
}
