import { spawn } from 'node:child_process';
import { writeFileSync, readFileSync, mkdtempSync } from 'node:fs';
const FILE = process.argv[2];
const prof = mkdtempSync(process.env.TMP + '/chrome_extra_');
const chrome = spawn('C:/Program Files/Google/Chrome/Application/chrome.exe', ['--headless=new','--remote-debugging-port=9435',`--user-data-dir=${prof}`,'--no-first-run','--disable-gpu','--window-size=1000,1100','about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms)); await sleep(2500);
const t = (await (await fetch('http://127.0.0.1:9435/json')).json()).find((x) => x.type === 'page');
const ws = new WebSocket(t.webSocketDebuggerUrl); await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = {}; const errs = [];
ws.addEventListener('message', (m) => { const d = JSON.parse(m.data); if (d.id && pending[d.id]) { pending[d.id](d.result); delete pending[d.id]; }
  if (d.method === 'Runtime.exceptionThrown') errs.push(d.params.exceptionDetails.exception?.description?.slice(0, 300)); });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (e) => { const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) errs.push(JSON.stringify(r.exceptionDetails).slice(0,300)); return r.result?.value; };
await send('Runtime.enable'); await send('Page.enable');
await send('Page.addScriptToEvaluateOnNewDocument', { source: `window.claude = { use: async (n) => n === 'user' ? { canEdit: async () => true } : n === 'artifact' ? { publish: async (h) => { window.__pub = h; return { version: 'v' }; } } : null };` });
const shot = async (name) => { const r = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); writeFileSync(name, Buffer.from(r.data, 'base64')); };
const url = 'file:///' + FILE.split(String.fromCharCode(92)).join('/');
await send('Page.navigate', { url }); await sleep(2000);
const src = readFileSync(FILE, 'utf8');
console.log('unchanged page rebuilds to itself:', (await ev('buildPage(current())')) === src, '| save bar:', await ev(`document.getElementById('saveAll').disabled + ' ' + document.getElementById('saveNote').innerText`));
console.log('tabs:', await ev(`[...document.querySelectorAll('#pageTabs button')].map(b => b.textContent).join(' | ')`));
const tab = async (p) => { await ev(`document.querySelector('[data-page=${p}]').click()`); await sleep(300); };
const pick = (name) => ev(`(() => { const s = document.getElementById('playSel'); const i = [...s.options].findIndex(o => o.textContent.startsWith(${JSON.stringify(name)} + ' (')); s.value = s.options[i].value; s.dispatchEvent(new Event('change', {bubbles:true})); return i; })()`);
const state = () => ev(`JSON.stringify({ intro: document.getElementById('pageIntro').textContent.slice(0, 40), plays: [...document.getElementById('playSel').options].slice(1).map(o => o.textContent).join(', '), man: !document.getElementById('manSec').hidden, zone: !document.getElementById('zoneSec').hidden, full: !document.getElementById('fullSec').hidden, vb: document.getElementById('f-court').getAttribute('viewBox'), addShown: getComputedStyle(document.getElementById('playAdd')).display !== 'none', kinds: document.getElementById('kindRow').textContent, players: document.querySelectorAll('#f-court g[transform]').length })`);
for (const [p, play] of [['blob', 'Box 1'], ['press', '12'], ['pressbreak', 'Man - 4 Across'], ['transition', '4 Flash']]) {
  await tab(p); console.log(p, await state());
  await pick(play); await sleep(200); console.log('  picked', play, await state()); await shot(`shot_${p}.png`);
}
// Run Cross (1 step) at Fast and check players end on the last step's spots.
await tab('blob'); await pick('Cross');
await ev(`document.querySelector('[data-speed="1"]').click(); document.getElementById('playGo').click()`);
await sleep(1200); await ev(`window.__mid = document.getElementById('playNote').textContent`); await shot('shot_blob_lines.png');
await sleep(4500);
console.log('after Play:', await ev(`document.getElementById('playNote').textContent`), '| mid:', await ev('window.__mid'));
console.log('end spots match last step:', await ev(`(() => { const p = window.libertyDefenseState.plays().now.blob.find(q => q.name === 'Cross'); const last = p.steps[p.steps.length - 1].offense; const gs = [...document.querySelectorAll('#f-court g[transform]')]; return gs.length + ' players; ' + Object.values(last).every(q => gs.some(g => { const v = g.getAttribute('transform').slice(10, -1).split(',').map(Number); return Math.hypot(v[0] - q.x, v[1] - q.y) < 1; })); })()`));
// Old pages still work.
await tab('offense'); console.log('offense', await state()); await pick('Curl'); await sleep(200); await shot('shot_offense.png');
await tab('defense'); console.log('defense', await state());
// Delete a BLOB play, Save for everyone, check the published page.
await tab('blob'); await pick('X'); await ev(`document.getElementById('playDel').click(); document.getElementById('playDel').click()`); await sleep(300);
console.log('after delete X:', await ev(`[...document.getElementById('playSel').options].slice(1).map(o => o.textContent).join(', ')`), '| save disabled:', await ev(`document.getElementById('saveAll').disabled`));
await ev(`document.getElementById('saveAll').click()`); await sleep(600);
const pub = await ev('window.__pub || ""');
console.log('published: has X in blob:', /"blob":\[[^\]]*"name":"X"/.test(pub), '| size', pub.length);
writeFileSync('extra_published_test.html', pub);
await send('Page.navigate', { url: 'file:///' + (process.cwd() + '/extra_published_test.html').split(String.fromCharCode(92)).join('/') }); await sleep(2000);
await tab('blob'); console.log('published page blob plays:', await ev(`[...document.getElementById('playSel').options].slice(1).map(o => o.textContent).join(', ')`));
await tab('transition'); console.log('published page transition plays:', await ev(`[...document.getElementById('playSel').options].slice(1).length`));
console.log('errors:', errs.length, errs.slice(0, 4));
chrome.kill(); process.exit(0);
