const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const script = name => fs.readFileSync(require('node:path').join(__dirname, '../web/', name), 'utf8');
let renders = 0;
const context = vm.createContext({
  boot(){}, state: {}, navEntries: [], renderRoute(){}, renderLanding(){}, refreshAll(){}, renderDetail(){}, handleCommand(){},
  document: {addEventListener(){}, querySelector(){return null;}},
  esc: x => String(x ?? ''), renderWorkspace(){renders++;}, toast(){},
  api: async () => ({edge:{id:'link',source_id:'a',target_id:'b'}}),
});
const run = text => vm.runInContext(text, context);
run(script('enhancements.js'));
context.renderWorkspace = () => { renders++; };
(async () => {
  run(`state.items = [{id:'a',title:'Note',kind:'note',tags:['sample']},{id:'b',title:'Video',kind:'youtube',tags:['sample']}];`);
  assert.equal(run('inferredEdges(state.items).length'), 0);
  run("state.items.forEach(i=>i.tags.push('dbms'))");
  assert.equal(run('inferredEdges(state.items).length'),1);
  assert.ok(!run('renderMap()').includes('data-line-source='));
  for(let n=0;n<2;n++) {
    await run(`handleCommand('map-link', {dataset:{id:'a'}})`);
    await run(`handleCommand('map-link', {dataset:{id:'b'}})`);
  }
  assert.equal(run('state.mapData.edges.length'),1);
  assert.ok(run('renderMap()').includes('Disconnect'));
  await run(`handleCommand('map-unlink', {dataset:{id:'link'}})`);
  assert.ok(!run('renderMap()').includes('data-line-source='));
  await run(`handleCommand('map-suggestions', {dataset:{}})`);
  assert.ok(run('renderMap()').includes('data-line-source='));
  run(`state.capabilities = {ai:{chat:'offline',voice:'manual',embeddings:'none'}}`);
  assert.ok(run('renderSettings()').includes('Not installed'));
  assert.ok(run('renderSettings()').includes('Not configured'));
  assert.ok(!run('renderSettings()').includes('>Available<'));
  const main=script('main.js');
  run(main.slice(main.indexOf('async function refreshProcessingItems()'), main.indexOf('setInterval(refreshProcessingItems')));
  run(`state.user={id:'u'}; state.view='detail'; state.detail={id:'video',status:'fetching_captions'}; state.items=[];`);
  context.refreshItems=async()=>{};
  context.api=async()=>({item:{id:'video',status:'searchable',transcript:'00:00:01 Actual caption'}});
  renders=0;
  await run('refreshProcessingItems()');
  assert.equal(run('state.detail.transcript'),'00:00:01 Actual caption');
  assert.equal(renders,1);
  await run('refreshProcessingItems()');
  assert.equal(renders,1);
  console.log('PASS: map defaults, suggestions, connect/disconnect, duplicate prevention, honest statuses, open transcript refresh');
})().catch(e=>{console.error(e);process.exit(1);});
