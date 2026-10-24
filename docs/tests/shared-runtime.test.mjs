import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../assets/js');
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; };
const json = value => new Response(JSON.stringify(value), {status:200});
function environment() {
  const elements = new Map();
  const timers = new Map();
  let timerId = 0;
  const classes = () => { const values = new Set(); return {add: v => values.add(v), remove: v => values.delete(v),
    contains: v => values.has(v), toggle(v, yes) {yes ? values.add(v) : values.delete(v);}}; };
  const element = id => {
    if (!elements.has(id)) elements.set(id, {classList:classes(), style:{}, dataset:{}, checked:false,
      setAttribute(){}, addEventListener(){}, focus(){}, select(){}, querySelectorAll(){return [];}});
    return elements.get(id);
  };
  const positions = ['First player','Second player'].map(value => ({dataset:{startingPosition:value},
    classList:classes(), setAttribute(){}}));
  positions.forEach(button => button.classList.add('active'));
  const document = {getElementById: element,
    querySelectorAll(selector) {return selector.endsWith('.active') ? positions.filter(x => x.classList.contains('active')) : positions;}};
  const window = {__ARK_NOVA_DATA_VERSION__:'v2', setTimeout(fn, delay){timers.set(++timerId,{fn,delay});return timerId;},
    clearTimeout(id){timers.delete(id);}, requestAnimationFrame(fn){fn();}};
  const context = vm.createContext({window, document, URL, Response, AbortController, console,
    fetch:async () => {throw new Error('Unexpected network');}});
  const modules = new Map();
  async function load(name, extras='') {
    if (modules.has(name)) return modules.get(name);
    const module = new vm.SourceTextModule(fs.readFileSync(path.join(root,name),'utf8')+extras, {context, identifier:name});
    modules.set(name,module);
    await module.link(spec => load(path.posix.normalize(path.posix.join(path.posix.dirname(name),spec.split('?')[0]))));
    await module.evaluate();
    return module;
  }
  return {context,load,document,window,element,positions,timers};
}

test('Reset precedes page request; edited global controls do not alter applied scope', async () => {
  const e=environment(), state=(await e.load('filter-state.js')).namespace;
  e.element('globalArenaOnly').checked=true;
  e.positions[1].classList.remove('active');
  state.captureGlobalFilters(e.document);
  e.element('globalArenaOnly').checked=false;
  assert.equal(state.normalizeGlobalFilters({stats_page:'cards'}).arena_only,true);
  assert.deepEqual([...state.normalizeGlobalFilters({stats_page:'cards'}).starting_positions],['First player']);
  state.resetGlobalFilters(e.document);
  const request=state.normalizeGlobalFilters({stats_page:'cards'});
  assert.equal(request.arena_only,false);
  assert.equal(request.starting_positions,undefined);
  // Exercise the actual app capture-phase listener before a simulated inline request.
  const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
  const start=app.indexOf("document.addEventListener('click', event => {\n  if (!event.target.closest('#sidebar .reset-btn'))");
  const end=app.indexOf('\n\nfunction prioritizeNavigationSnapshot',start);
  let listener, capture;
  e.document.addEventListener=(_kind,fn,flag)=>{listener=fn;capture=flag;};
  e.context.resetGlobalFilters=state.resetGlobalFilters;
  e.context.activeEloRangeLinkController={reset(){}};
  vm.runInContext(app.slice(start,end),e.context);
  assert.equal(capture,true);
  e.element('globalTournamentOnly').checked=true;
  state.captureGlobalFilters(e.document);
  listener({target:{closest(){return {};}}});
  assert.equal(state.normalizeGlobalFilters({stats_page:'cards'}).tournament_only,false);
});

test('Explicit filters survive normalization with no sidebar dependency', async () => {
  const e=environment(), state=(await e.load('filter-state.js')).namespace;
  const request=state.normalizeGlobalFilters({stats_page:'cards',arena_only:true,tournament_only:true,starting_positions:['First player']});
  assert.equal(request.arena_only,true); assert.equal(request.tournament_only,true);
  assert.deepEqual([...request.starting_positions],['First player']);
  assert.deepEqual([...state.normalizeGlobalFilters({starting_positions:[]}).starting_positions],[]);
});

test('Cards, Opening Hand and Endgames Reset reuse their Standard-only mount defaults', () => {
  const catalog=fs.readFileSync(path.join(root,'map-catalog.js'),'utf8');
  const literal=catalog.match(/export const STANDARD_MAPS = (\[[\s\S]*?\n\]);/)[1];
  const defaults=vm.runInNewContext(literal);
  for(const page of ['cards','opening-hand','endgames']) {
    const e=environment(), source=fs.readFileSync(path.join(root,'pages',page+'.js'),'utf8');
    e.context.DEFAULT_MAPS=defaults;
    e.context.VALID_MAPS=defaults.map(([,field,full])=>({field,full}));
    e.context.mountToken=1;
    let selected=[], requested;
    e.context.renderMapFilterChips=(_host,maps)=>{selected=[...maps];};
    e.context.applyFilters=()=>{requested=[...selected];};
    for(const name of ['updateTypeFilterIndicator','resetAllAttributeFilters',
      'refreshAttributeAvailability','updateCardSearchIndicator']) e.context[name]=()=>{};
    vm.runInContext(source.match(/function buildMapChips\(\) \{[\s\S]*?\n\}/)[0],e.context);
    vm.runInContext(source.match(/function resetFilters\(\) \{[\s\S]*?\n\}/)[0]+'\nresetFilters();',e.context);
    assert.deepEqual(requested,Array.from(defaults,([, ,full])=>full),page);
    assert.equal(e.element('dateFrom').value,'2025-01-01');
  }
});

test('Pack rejects old generation, malformed members and null snapshots; matching pack pins URLs', async () => {
  const e=environment(), cache=(await e.load('snapshot-cache.js','\nexport {seedDefaultPack, memoryPut, memoryBytes, memoryCache};')).namespace;
  const url='https://storage.googleapis.com/ark-nova-stats-dashboard-cache/card-stats/default-mw.json';
  const pack={schema_version:23,data_version:'v2',release_version:'release-2',snapshots:{'card-stats/default-mw.json':{data_version:'v2',data:[]}}};
  assert.equal(cache.seedDefaultPack({...pack,data_version:'v1'}),false);
  assert.equal(cache.seedDefaultPack({...pack,snapshots:null}),false);
  assert.equal(cache.seedDefaultPack({...pack,snapshots:{bad:{data_version:'v1'}}}),false);
  assert.equal(cache.seedDefaultPack(pack),true);
  assert.equal(cache.peekSnapshot(url+'?v=any').data_version,'v2');
  let requested;
  e.context.fetch=async url => {requested=url;return json({data_version:'v2',data:[]});};
  await cache.loadSnapshot(url.replace('default-mw','default-base'));
  assert.match(requested,/releases\/release-2\/default-base/);
  e.context.fetch=async () => json({data_version:'v1'});
  await assert.rejects(cache.loadSnapshot(url.replace('default-mw','other')),/data version/);
});

test('Validated initialization retains only metadata, and Arena warms latest only', async () => {
  const e=environment(), requests=[];
  e.context.fetch=async url => {
    requests.push(url);
    return json(url.includes('default-pack') ? {schema_version:23,data_version:'v2',release_version:'r2',
      snapshots:{'card-stats/default-mw.json':{data_version:'v2'}}} : {data_version:'v2'});
  };
  const cache=(await e.load('snapshot-cache.js')).namespace;
  const result=await cache.initializeDefaultSnapshots();
  assert.equal(result.snapshots,undefined);
  cache.prioritizeSnapshotGroup('arena');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.filter(x=>x.includes('/arena/latest.json')).length,1);
  assert.equal(requests.filter(x=>x.includes('/arena/manifest.json')).length,0);
});

test('Memory cache respects retained size and evicts LRU without retaining oversized entries', async () => {
  const e=environment();
  const source=fs.readFileSync(path.join(root,'snapshot-cache.js'),'utf8').replace('64 * 1024 * 1024','1024');
  const module=new vm.SourceTextModule(source+'\nexport {memoryPut,memoryCache,memoryBytes};',{context:e.context});
  await module.link(()=>e.load('filter-state.js')); await module.evaluate();
  const cache=module.namespace;
  cache.memoryPut('small',{value:'x'.repeat(200)});
  cache.memoryPut('next',{value:'x'.repeat(200)});
  cache.memoryPut('third',{value:'x'.repeat(200)});
  assert.equal(cache.memoryCache.has('small'),false);
  assert.ok(cache.memoryBytes<=1024);
  cache.memoryPut('large',{value:'x'.repeat(2000)});
  assert.equal(cache.memoryCache.has('large'),false);
});

async function refreshEnvironment() {
  const e=environment();
  const module=await e.load('pages/refresh.js','\nexport {fetchStatus,startRefresh,renderStatus};');
  e.context.fetch=async()=>json({state:'succeeded',run_id:'old',progress_percent:100,started_at:'2026-10-08T00:00:00Z'});
  module.namespace.mount();
  await new Promise(resolve=>setImmediate(resolve));
  return {...e,refresh:module.namespace};
}
test('Refresh retries asset failures with one timer and recovers', async () => {
  const e=await refreshEnvironment();
  e.context.fetch=async()=>{throw new Error('temporary');};
  await e.refresh.fetchStatus(false);
  assert.equal(e.timers.size,1);
  assert.match(e.element('refreshMessage').textContent,/Reconnecting/);
  e.context.fetch=async()=>json({state:'running',run_id:'new',progress_percent:12,started_at:'2026-10-09T00:00:00Z'});
  await e.refresh.fetchStatus(false);
  assert.equal(e.element('refreshPercent').textContent,'12%');
  assert.equal(e.timers.size,1);
});
test('Slow manual start ignores old success and accepts acknowledgement of new run', async () => {
  const e=await refreshEnvironment(), post=deferred();
  e.context.fetch=async (_url,options)=>options?.method==='POST'?post.promise:json({state:'succeeded',run_id:'old',progress_percent:100});
  const request=e.refresh.startRefresh('fixture-password');
  await e.refresh.fetchStatus(false);
  assert.equal(e.element('refreshPercent').textContent,'0%');
  assert.equal(e.element('refreshStartButton').disabled,true);
  post.resolve(json({run_id:'new',refresh_status:{state:'running',run_id:'new',progress_percent:8}}));
  await request;
  assert.notEqual(e.element('refreshPercent').textContent,'100%');
  e.context.fetch=async()=>json({state:'succeeded',run_id:'new',progress_percent:100});
  await e.refresh.fetchStatus(false);
  assert.equal(e.element('refreshStartButton').disabled,false);
});
test('Late password rejection after unmount does not reopen modal or schedule polling', async () => {
  const e=await refreshEnvironment(), post=deferred();
  e.context.fetch=()=>post.promise;
  const request=e.refresh.startRefresh('fixture-password');
  e.refresh.unmount();
  post.resolve(new Response('{}',{status:403}));
  await request;
  assert.equal(e.timers.size,0);
  assert.equal(e.element('refreshPasswordModal').hidden,undefined);
});

test('Lost start acknowledgement reconciles before offering Retry, never old success', async () => {
  const e=await refreshEnvironment();
  e.context.fetch=async (_url,options)=>{
    if(options?.method==='POST') throw new Error('lost acknowledgement');
    return json({state:'succeeded',run_id:'old',progress_percent:100});
  };
  await e.refresh.startRefresh('fixture-password');
  assert.equal(e.element('refreshStartButton').disabled,true);
  vm.runInContext('Date.now = () => 9999999999999',e.context);
  await e.refresh.fetchStatus(false);
  assert.equal(e.element('refreshStartButton').textContent,'Retry');
  assert.match(e.element('refreshMessage').textContent,/Could not confirm/);
  await e.refresh.fetchStatus(false);
  assert.equal(e.element('refreshStartButton').textContent,'Retry');
  e.context.fetch=async()=>json({state:'running',run_id:'new',progress_percent:14});
  await e.refresh.fetchStatus(false);
  assert.equal(e.element('refreshPercent').textContent,'14%');
});
