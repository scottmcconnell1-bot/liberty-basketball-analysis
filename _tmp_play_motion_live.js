const puppeteer = require('puppeteer-core');
const fs = require('fs');

const exe = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
].find((p) => fs.existsSync(p));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: exe,
    headless: true,
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  page.on('console', (msg) => {
    if (msg.text().startsWith('PLAYDBG')) console.log(msg.text());
  });
  await page.goto('http://127.0.0.1:8080/playbook/play/125', {
    waitUntil: 'networkidle2',
    timeout: 60000,
  });
  await page.waitForFunction(
    () => /Ready/i.test((document.getElementById('sheetAlignBannerText') || {}).textContent || ''),
    { timeout: 120000 }
  );

  await page.evaluate(() => {
    const orig = animateOnePath;
    window.animateOnePath = function (live, path, toRaw, ballPid, durationMs, moveGen) {
      const n = normalizeAnimPath(path, live, toRaw);
      console.log('PLAYDBG animateOnePath', JSON.stringify({
        inPid: path && path.pid,
        inFrom: path && path.from,
        inTo: path && path.to,
        normFrom: n && n.from,
        normTo: n && n.to,
        pathLen: n && travelPathLength(n),
        active: isPlaybackActive(),
        gen: moveGen,
        sheetMoveGen,
      }));
      return orig(live, path, toRaw, ballPid, durationMs, moveGen);
    };
  });

  const playPromise = page.evaluate(() => playAnimation());
  const samples = [];
  for (let i = 0; i < 30; i += 1) {
    await new Promise((r) => setTimeout(r, 100));
    const s = await page.evaluate(() => {
      const tok = [...document.querySelectorAll('#playerLayer g.player-token')].find((el) =>
        (el.textContent || '').includes('1') && !(el.textContent || '').includes('×')
      );
      return {
        running: playAllRunning,
        btn: (document.getElementById('playAllBtn') || {}).textContent,
        hint: (document.getElementById('sheetAnimHint') || {}).textContent || '',
        stats: window.__playbookAnimStats,
        o1: tok ? tok.getAttribute('transform') : null,
      };
    });
    samples.push(s);
    if (!s.running && i > 8) break;
  }
  await playPromise;
  const o1s = samples.map((s) => s.o1).filter(Boolean);
  const uniq = [...new Set(o1s)];
  console.log('BTN_SAMPLES', samples.map((s) => s.btn).slice(0, 8));
  console.log('HINT_SAMPLES', samples.map((s) => s.hint).filter(Boolean).slice(0, 8));
  console.log('O1_UNIQUE', uniq);
  console.log('MAX_FRAMES', Math.max(...samples.map((s) => (s.stats && s.stats.frames) || 0)));
  console.log('FINAL_STATS', samples[samples.length - 1] && samples[samples.length - 1].stats);
  if (uniq.length < 2) {
    console.error('FAIL token did not change transform');
    process.exit(1);
  }
  console.log('MOTION_OK');
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
