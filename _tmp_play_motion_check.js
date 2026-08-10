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
  await page.goto('http://127.0.0.1:8080/playbook/play/125', {
    waitUntil: 'networkidle2',
    timeout: 60000,
  });
  await page.waitForFunction(
    () => /Ready/i.test((document.getElementById('sheetAlignBannerText') || {}).textContent || ''),
    { timeout: 120000 }
  );

  const info = await page.evaluate(() => {
    const a0 = withManDefense(positionsForAnim(0));
    const a1 = withManDefense(positionsForAnim(1));
    const deltas = [];
    for (let i = 1; i <= 5; i += 1) {
      const k = 'o' + i;
      if (!a0[k] || !a1[k]) continue;
      deltas.push({
        k,
        d: Math.hypot(a0[k].x - a1[k].x, a0[k].y - a1[k].y),
        from: a0[k],
        to: a1[k],
      });
    }
    const paths = buildTravelPaths(a0, a1, steps[0], { paths: {}, marks: {}, passes: [] });
    const beats = forceGuaranteeBeats(a0, a1, steps[0], paths, steps[0].ball || 'o1');
    return {
      deltas,
      paths: paths.map((p) => ({
        pid: p.pid,
        from: p.from,
        to: p.to,
        len: travelPathLength(p),
      })),
      beats: beats.map((b) => ({
        kind: b.kind,
        label: b.label,
        pid: b.path && b.path.pid,
        from: b.path && b.path.from,
        to: b.path && b.path.to,
        len: b.path && travelPathLength(b.path),
      })),
    };
  });
  console.log('INFO', JSON.stringify(info, null, 2));

  await page.evaluate(() => playAnimation());
  const samples = [];
  for (let i = 0; i < 24; i += 1) {
    await new Promise((r) => setTimeout(r, 120));
    const s = await page.evaluate(() => {
      const kids = [...document.querySelectorAll('#playerLayer > *')].map((el) => ({
        tag: el.tagName,
        cls: el.getAttribute('class'),
        transform: el.getAttribute('transform'),
        text: (el.textContent || '').slice(0, 8),
      }));
      return {
        stats: window.__playbookAnimStats,
        running: playAllRunning,
        kids,
      };
    });
    samples.push(s);
  }
  console.log('SAMPLE0', JSON.stringify(samples[0]));
  console.log('SAMPLE8', JSON.stringify(samples[8]));
  console.log('SAMPLE16', JSON.stringify(samples[16]));
  const transforms = samples.map((s) => (s.kids.find((k) => k.text.includes('1')) || {}).transform);
  console.log('O1_TRANSFORMS', transforms);
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
