// Foreground-first cache for public dashboard snapshots and filtered responses.
// Snapshot bodies are persisted in Cache Storage without parsing during the
// background warmup. This keeps large assets off the main thread until needed.

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOT_CACHE_PREFIX = 'arkNovaSnapshotCache:';
const MEMORY_MAX_ENTRIES = 64;
const BACKGROUND_WORKERS = 2;
const BACKGROUND_DELAY_MS = 1200;

const memoryCache = new Map();
const inFlight = new Map();
const backgroundQueue = [];
const queuedUrls = new Set();
const backgroundControllers = new Map();
const idleWaiters = [];

let backgroundStarted = false;
let backgroundWorkersActive = 0;
let foregroundActivity = 0;
let backgroundTimer = 0;
let cacheCleanupStarted = false;

const DEFAULT_SNAPSHOT_MANIFEST = [
  ['cards', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-mw.json'],
  ['cards', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-base.json'],
  ['opening-hand', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/opening-hand/default-mw.json'],
  ['opening-hand', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/opening-hand/default-base.json'],
  ['endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/default-mw.json'],
  ['endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/default-base.json'],
  ['endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-distribution/default-mw.json'],
  ['endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-distribution/default-base.json'],
  ['endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-by-map/default-mw.json'],
  ['endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/endgames/cp-by-map/default-base.json'],
  ['maps', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/metrics/default-mw.json'],
  ['maps', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/metrics/default-base.json'],
  ['maps', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/tournament_h2h/default-mw.json'],
  ['maps', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/maps/tournament_h2h/default-base.json'],
  ['sponsor-endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/sponsor-endgames/cp/default-mw.json?v=20260628-1'],
  ['sponsor-endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/sponsor-endgames/cp/default-base.json?v=20260628-1'],
  ['sponsor-endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/sponsor-endgames/appeal/default-mw.json?v=20260628-1'],
  ['sponsor-endgames', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/sponsor-endgames/appeal/default-base.json?v=20260628-1'],
  ['icons', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/icons/default-mw.json?v=20260704-1'],
  ['icons', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/icons/default-base.json?v=20260704-1'],
  ['build', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/enclosures/delta/default-mw.json'],
  ['build', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/enclosures/delta/default-base.json'],
  ['build', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/enclosures/frequency/default-mw.json'],
  ['build', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/enclosures/frequency/default-base.json'],
  ['build', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/hexes/delta/default-mw.json'],
  ['build', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/hexes/delta/default-base.json'],
  ['build', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/hexes/frequency/default-mw.json'],
  ['build', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/build/hexes/frequency/default-base.json'],
  ['predictors', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/predictors/general/default-mw.json'],
  ['predictors', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/predictors/general/default-base.json'],
  ['predictors', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/predictors/icon/default-mw.json'],
  ['predictors', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/predictors/icon/default-base.json'],
  ['predictors', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/predictors/specific/default-mw.json'],
  ['predictors', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/predictors/specific/default-base.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/starting_position/delta/default-mw.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/starting_position/delta/default-base.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrades/delta/default-mw.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrades/delta/default-base.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrade_order/delta/default-mw.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrade_order/delta/default-base.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrade_order/frequency/default-mw.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrade_order/frequency/default-base.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrades_by_map/delta/default-mw.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrades_by_map/delta/default-base.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrades_by_map/frequency/default-mw.json'],
  ['actions', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/actions/upgrades_by_map/frequency/default-base.json'],
  ['combos', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/combinations/card-card/default-mw.json?v=20260629-13'],
  ['combos', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/combinations/card-card/default-base.json?v=20260629-13'],
  ['combos', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/combinations/card-map/default-mw.json?v=20260629-13'],
  ['combos', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/combinations/card-map/default-base.json?v=20260629-13'],
  ['combos', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/combinations/card-round/default-mw.json?v=20260629-13'],
  ['combos', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/combinations/card-round/default-base.json?v=20260629-13'],
  ['combos', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/combinations/card-endgame/default-mw.json?v=20260629-13'],
  ['combos', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/combinations/card-endgame/default-base.json?v=20260629-13'],
];

function dataVersion() {
  return String(window.__ARK_NOVA_DATA_VERSION__ || 'unknown');
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') {
    return Object.keys(value).sort().reduce((out, key) => {
      if (value[key] !== undefined) out[key] = stable(value[key]);
      return out;
    }, {});
  }
  return value;
}

function versionedUrl(url) {
  const version = dataVersion();
  if (!version || version === 'unknown') return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}ark_data_version=${encodeURIComponent(version)}`;
}

function snapshotCacheName() {
  return `${SNAPSHOT_CACHE_PREFIX}${dataVersion().replace(/[^a-zA-Z0-9._-]/g, '_')}`;
}

function cacheKey(kind, value) {
  return `${dataVersion()}:${kind}:${typeof value === 'string' ? value : JSON.stringify(stable(value))}`;
}

function memoryPut(key, payload) {
  memoryCache.delete(key);
  memoryCache.set(key, payload);
  while (memoryCache.size > MEMORY_MAX_ENTRIES) memoryCache.delete(memoryCache.keys().next().value);
}

async function snapshotStorage() {
  if (!('caches' in window) || dataVersion() === 'unknown') return null;
  try { return await caches.open(snapshotCacheName()); } catch { return null; }
}

async function cleanOldSnapshotCaches() {
  if (cacheCleanupStarted || !('caches' in window)) return;
  cacheCleanupStarted = true;
  try {
    const current = snapshotCacheName();
    const names = await caches.keys();
    await Promise.all(names
      .filter(name => name.startsWith(SNAPSHOT_CACHE_PREFIX) && name !== current)
      .map(name => caches.delete(name)));
  } catch { /* Persistent cache is best-effort. */ }
}

async function snapshotLoader(url) {
  const requestUrl = versionedUrl(url);
  const cache = await snapshotStorage();
  if (cache) {
    const cached = await cache.match(requestUrl);
    if (cached) return cached.json();
  }

  const response = await fetch(requestUrl, { cache: 'default' });
  if (!response.ok) throw new Error(`Snapshot request failed (${response.status})`);
  if (cache) void cache.put(requestUrl, response.clone()).catch(() => {});
  return response.json();
}

async function runForeground(loader) {
  foregroundActivity += 1;
  backgroundControllers.forEach(controller => controller.abort());
  try { return await loader(); }
  finally {
    foregroundActivity -= 1;
    if (!foregroundActivity) idleWaiters.splice(0).forEach(resolve => resolve());
  }
}

function waitForForegroundIdle() {
  if (!foregroundActivity) return Promise.resolve();
  return new Promise(resolve => idleWaiters.push(resolve));
}

async function loadCached(key, loader) {
  if (memoryCache.has(key)) {
    const payload = memoryCache.get(key);
    memoryCache.delete(key);
    memoryCache.set(key, payload);
    return payload;
  }
  if (inFlight.has(key)) return inFlight.get(key);
  const promise = loader().then(payload => {
    memoryPut(key, payload);
    return payload;
  }).finally(() => inFlight.delete(key));
  inFlight.set(key, promise);
  return promise;
}

export function loadSnapshot(url) {
  const requestUrl = versionedUrl(url);
  return runForeground(() => loadCached(cacheKey('snapshot', requestUrl), () => snapshotLoader(url)));
}

export function fetchStats(params) {
  return runForeground(() => loadCached(cacheKey('filtered', params), async () => {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== 'ok') {
      throw new Error(payload.message || `API request failed (${response.status})`);
    }
    return payload;
  }));
}

export async function loadStats(params, defaultUrl = null) {
  if (defaultUrl) {
    try { return await loadSnapshot(defaultUrl); } catch { return fetchStats(params); }
  }
  return fetchStats(params);
}

async function prefetchSnapshot(url) {
  const requestUrl = versionedUrl(url);
  const cache = await snapshotStorage();
  if (!cache) {
    const response = await fetch(requestUrl, { cache: 'default' });
    if (response.ok) await response.arrayBuffer();
    return;
  }
  if (await cache.match(requestUrl)) return;
  const controller = new AbortController();
  backgroundControllers.set(requestUrl, controller);
  try {
    const response = await fetch(requestUrl, {
      cache: 'default',
      signal: controller.signal,
      priority: 'low',
    });
    if (!response.ok) throw new Error(`Snapshot prefetch failed (${response.status})`);
    await cache.put(requestUrl, response);
  } finally {
    backgroundControllers.delete(requestUrl);
  }
}

async function backgroundWorker() {
  while (backgroundQueue.length) {
    await waitForForegroundIdle();
    const item = backgroundQueue.shift();
    if (!item) return;
    queuedUrls.delete(item.url);
    try {
      await prefetchSnapshot(item.url);
    } catch (error) {
      if (error?.name === 'AbortError') {
        if (!queuedUrls.has(item.url)) {
          queuedUrls.add(item.url);
          backgroundQueue.unshift(item);
        }
        await waitForForegroundIdle();
      }
    }
  }
}

function startBackgroundWorkers() {
  while (backgroundWorkersActive < BACKGROUND_WORKERS && backgroundQueue.length) {
    backgroundWorkersActive += 1;
    void backgroundWorker().finally(() => {
      backgroundWorkersActive -= 1;
      if (backgroundQueue.length) startBackgroundWorkers();
    });
  }
}

function scheduleBackgroundPreload() {
  if (backgroundTimer) return;
  const start = () => {
    backgroundTimer = 0;
    cleanOldSnapshotCaches();
    startBackgroundWorkers();
  };
  if ('requestIdleCallback' in window) {
    backgroundTimer = window.requestIdleCallback(start, { timeout: BACKGROUND_DELAY_MS });
  } else {
    backgroundTimer = window.setTimeout(start, BACKGROUND_DELAY_MS);
  }
}

export function preloadDefaultSnapshots(priorityGroup = '') {
  const ordered = [...DEFAULT_SNAPSHOT_MANIFEST].sort(([group]) => group === priorityGroup ? -1 : 1);
  for (const [group, url] of ordered) {
    const requestUrl = versionedUrl(url);
    if (memoryCache.has(cacheKey('snapshot', requestUrl)) || queuedUrls.has(requestUrl)) continue;
    queuedUrls.add(requestUrl);
    backgroundQueue.push({ group, url });
  }
  scheduleBackgroundPreload();
}

export function prioritizeSnapshotGroup(group) {
  const priority = DEFAULT_SNAPSHOT_MANIFEST.filter(([itemGroup]) => itemGroup === group);
  for (const item of priority) {
    const requestUrl = versionedUrl(item[1]);
    const index = backgroundQueue.findIndex(entry => versionedUrl(entry.url) === requestUrl);
    if (index >= 0) backgroundQueue.unshift(...backgroundQueue.splice(index, 1));
  }
  scheduleBackgroundPreload();
}
