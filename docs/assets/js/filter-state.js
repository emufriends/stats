// Applied global scope is captured before a page starts a request. Transport
// normalization is pure: explicit request fields always win over defaults.
const BOTH = ['First player', 'Second player'];
let applied = { arena_only: false, tournament_only: false, starting_positions: BOTH };

export function captureGlobalFilters(root = document) {
  const positions = [...root.querySelectorAll('.global-fpa-button.active')]
    .map(button => button.dataset.startingPosition).filter(Boolean);
  applied = {
    arena_only: Boolean(root.getElementById('globalArenaOnly')?.checked),
    tournament_only: Boolean(root.getElementById('globalTournamentOnly')?.checked),
    starting_positions: positions.length ? positions : BOTH,
  };
  return getAppliedGlobalFilters();
}

export function getAppliedGlobalFilters() {
  return { ...applied, starting_positions: [...applied.starting_positions] };
}

export function restoreGlobalFilters(scope, root = document) {
  for (const [id, key] of [['globalArenaOnly','arena_only'],['globalTournamentOnly','tournament_only']]) {
    const input = root.getElementById(id);
    if (input) input.checked = Boolean(scope[key]);
  }
  const positions = scope.starting_positions || BOTH;
  root.querySelectorAll('.global-fpa-button').forEach(button => {
    const active = positions.includes(button.dataset.startingPosition);
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  return captureGlobalFilters(root);
}

export function resetGlobalFilters(root = document, resetLinkedElo = () => {}) {
  for (const id of ['globalArenaOnly', 'globalTournamentOnly']) {
    const input = root.getElementById(id);
    if (input) input.checked = false;
  }
  root.querySelectorAll('.global-fpa-button').forEach(button => {
    button.classList.add('active');
    button.setAttribute('aria-pressed', 'true');
  });
  resetLinkedElo();
  return captureGlobalFilters(root);
}

export function normalizeGlobalFilters(params, defaults = getAppliedGlobalFilters()) {
  const normalized = { ...params };
  if (params.stats_page !== 'records') {
    for (const key of ['arena_only', 'tournament_only']) {
      if (!Object.hasOwn(params, key)) normalized[key] = Boolean(defaults[key]);
    }
  }
  const positions = Object.hasOwn(params, 'starting_positions')
    ? params.starting_positions : defaults.starting_positions;
  if (Array.isArray(positions)) {
    if (positions.length === 1) normalized.starting_positions = [...positions];
    else if (positions.length === 2 && BOTH.every(value => positions.includes(value))) {
      delete normalized.starting_positions;
    } else normalized.starting_positions = [...positions]; // Backend rejects invalid selections.
  }
  return normalized;
}
