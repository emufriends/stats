// Foreground-first cache for public dashboard snapshots and filtered responses.
// Snapshot bodies are persisted in Cache Storage without parsing during the
// background warmup. This keeps large assets off the main thread until needed.

const API_URL = 'https://europe-west1-ark-nova-stats-dashboard.cloudfunctions.net/get-card-stats';
const SNAPSHOT_CACHE_PREFIX = 'arkNovaSnapshotCache:';
const DEFAULT_PACK_CACHE_PREFIX = 'arkNovaDefaultPack:';
const DEFAULT_PACK_URL = 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/bootstrap/default-pack.json';
const DEFAULT_PACK_SCHEMA_VERSION = 3;
const MEMORY_MAX_ENTRIES = 128;

const memoryCache = new Map();
const inFlight = new Map();
let foregroundActivity = 0;
let cacheCleanupStarted = false;
let defaultPackInit = null;
let currentPackReady = false;

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
  ['conservation', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/conservation/projects/default-mw.json'],
  ['conservation', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/conservation/projects/default-base.json'],
  ['conservation', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/conservation/project-rewards/default-mw.json'],
  ['conservation', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/conservation/project-rewards/default-base.json'],
  ['conservation', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/conservation/cp-rewards/default-mw.json'],
  ['conservation', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/conservation/cp-rewards/default-base.json'],
  ['workers', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/workers/general/default-mw.json'],
  ['workers', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/workers/general/default-base.json'],
  ['workers', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/workers/two-cp-worker/default-mw.json'],
  ['workers', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/workers/two-cp-worker/default-base.json'],
  ['players', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/general/default-mw.json'],
  ['players', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/general/default-base.json'],
  ['players', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/arena/manifest.json'],
  ['players', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/players/arena-top-100/all-seasons.json'],
  ['records', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records/fastest-games/default-mw.json'],
  ['records', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records/fastest-games/default-base.json'],
  ['records', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records/highest-scores/default-mw.json'],
  ['records', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records/highest-scores/default-base.json'],
  ['records', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records/biggest-turns/default-mw.json'],
  ['records', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records/biggest-turns/default-base.json'],
  ['records', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records/most-icons/default-mw.json'],
  ['records', 'https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/records/most-icons/default-base.json'],
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
  try { return await loader(); }
  finally { foregroundActivity -= 1; }
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

export function peekSnapshot(url) {
  const key = cacheKey('snapshot', versionedUrl(url));
  return memoryCache.get(key) || null;
}

export function fetchStats(params, { signal } = {}) {
  return runForeground(() => loadCached(cacheKey('filtered', params), async () => {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
      signal,
    });
    const payload = await response.json();
    if (!response.ok || payload.status !== 'ok') {
      throw new Error(payload.message || `API request failed (${response.status})`);
    }
    return payload;
  }));
}

export async function loadStats(params, defaultUrl = null, options = {}) {
  if (defaultUrl) {
    try { return await loadSnapshot(defaultUrl); } catch { return fetchStats(params, options); }
  }
  return fetchStats(params, options);
}

function packCacheName(version = dataVersion()) {
  return `${DEFAULT_PACK_CACHE_PREFIX}${String(version).replace(/[^a-zA-Z0-9._-]/g, '_')}`;
}

function snapshotBlobPath(url) {
  try {
    const path = new URL(url).pathname.replace(/^\/+/, '');
    return path.replace(/^ark-nova-stats-dashboard-cache\//, '');
  } catch { return ''; }
}

function compatibleDefaultPack(payload) {
  return Boolean(payload && Number(payload.schema_version) === DEFAULT_PACK_SCHEMA_VERSION && typeof payload.snapshots === 'object');
}

function seedDefaultPack(payload) {
  if (!compatibleDefaultPack(payload)) return false;
  const byPath = new Map(DEFAULT_SNAPSHOT_MANIFEST.map(([, url]) => [snapshotBlobPath(url), url]));
  let seeded = 0;
  Object.entries(payload.snapshots).forEach(([path, snapshot]) => {
    const url = byPath.get(path);
    if (!url || !snapshot) return;
    memoryPut(cacheKey('snapshot', versionedUrl(url)), snapshot);
    seeded += 1;
  });
  return seeded > 0;
}

async function cachedPackFrom(cacheName) {
  try {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    const request = keys.find(item => new URL(item.url).pathname.endsWith('/card-stats/bootstrap/default-pack.json'));
    if (!request) return null;
    const response = await cache.match(request);
    return response ? await response.json() : null;
  } catch { return null; }
}

async function hydrateNewestCachedPack() {
  if (!('caches' in window)) return null;
  try {
    const names = (await caches.keys())
      .filter(name => name.startsWith(DEFAULT_PACK_CACHE_PREFIX))
      .sort()
      .reverse();
    for (const name of names) {
      const payload = await cachedPackFrom(name);
      if (!currentPackReady && seedDefaultPack(payload)) return { name, payload };
      if (currentPackReady) return null;
    }
  } catch { /* The daily pack is an optimization, never a hard dependency. */ }
  return null;
}

async function installCurrentPack() {
  const version = dataVersion();
  const requestUrl = versionedUrl(DEFAULT_PACK_URL);
  const cacheName = packCacheName(version);
  let response = null;
  if ('caches' in window) {
    try {
      const cache = await caches.open(cacheName);
      response = await cache.match(requestUrl);
      if (!response) {
        const fetched = await fetch(requestUrl, { cache: 'default', priority: 'low' });
        if (!fetched.ok) throw new Error(`Default pack request failed (${fetched.status})`);
        await cache.put(requestUrl, fetched.clone());
        response = fetched;
      }
    } catch { response = null; }
  }
  if (!response) {
    response = await fetch(requestUrl, { cache: 'default', priority: 'low' });
    if (!response.ok) throw new Error(`Default pack request failed (${response.status})`);
  }
  let payload = await response.json();
  if (!compatibleDefaultPack(payload)) {
    // A Cache Storage entry can outlive a frontend schema bump. Replace it
    // immediately instead of repeatedly failing and falling back forever.
    const fetched = await fetch(requestUrl, { cache: 'reload', priority: 'low' });
    if (!fetched.ok) throw new Error(`Default pack refresh failed (${fetched.status})`);
    if ('caches' in window) {
      try {
        const cache = await caches.open(cacheName);
        await cache.put(requestUrl, fetched.clone());
      } catch { /* A fresh in-memory pack is still useful without persistence. */ }
    }
    payload = await fetched.json();
  }
  if (!seedDefaultPack(payload)) throw new Error('Default pack has no recognized snapshots');
  currentPackReady = true;

  if ('caches' in window) {
    try {
      const names = (await caches.keys())
        .filter(name => name.startsWith(DEFAULT_PACK_CACHE_PREFIX))
        .sort()
        .reverse();
      const keep = new Set([cacheName, names.find(name => name !== cacheName)].filter(Boolean));
      await Promise.all(names.filter(name => !keep.has(name)).map(name => caches.delete(name)));
    } catch { /* Cache cleanup is best-effort. */ }
  }
  cleanOldSnapshotCaches();
  return payload;
}

export function initializeDefaultSnapshots() {
  if (defaultPackInit) return defaultPackInit;
  const current = installCurrentPack();
  defaultPackInit = (async () => {
    const cached = await hydrateNewestCachedPack();
    if (cached) {
      void current.catch(() => {});
      return cached.payload;
    }
    return current;
  })();
  return defaultPackInit;
}

export async function waitForDefaultSnapshotWarmup(timeoutMs = 120) {
  const warmup = initializeDefaultSnapshots().catch(() => null);
  if (!timeoutMs) return warmup;
  return Promise.race([
    warmup,
    new Promise(resolve => window.setTimeout(() => resolve(null), timeoutMs)),
  ]);
}

export function preloadDefaultSnapshots() {
  void initializeDefaultSnapshots().catch(() => {});
}

export function prioritizeSnapshotGroup(group) {
  // Players owns a deliberately separate Arena history bundle, so hovering or
  // focusing that nav item must still warm its assets after the universal
  // default pack is ready.
  if (currentPackReady && group !== 'players') return;
  const urls = DEFAULT_SNAPSHOT_MANIFEST.filter(([itemGroup]) => itemGroup === group).map(([, url]) => url);
  urls.forEach(url => { void loadSnapshot(url).catch(() => {}); });
}
