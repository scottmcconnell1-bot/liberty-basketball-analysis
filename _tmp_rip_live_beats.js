/**
 * Capture Rip (125) live beat list via playbar timeline rebuild.
 */
const puppeteer = require('puppeteer-core');

async function main() {
  const edge = process.env.EDGE_PATH
    || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  const browser = await puppeteer.launch({
    executablePath: edge,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(120000);
  await page.goto('http://127.0.0.1:8080/playbook/play/125?cb=' + Date.now(), {
    waitUntil: 'networkidle2',
  });
  await page.waitForFunction(() => {
    const t = document.getElementById('sheetAlignBannerText');
    return t && /Ready/i.test(t.textContent || '');
  }, { timeout: 90000 });

  const result = await page.evaluate(async () => {
    // Force a fresh timeline so heldLandings / ink fetch use current code.
    if (typeof invalidatePlaybarTimeline === 'function') invalidatePlaybarTimeline();
    if (typeof sheetInkPathCache !== 'undefined' && sheetInkPathCache.clear) {
      sheetInkPathCache.clear();
    }
    await ensurePlaybarTimeline();
    const frames = (typeof playbarKeyframes !== 'undefined' ? playbarKeyframes : []).map((k) => ({
      sheetIndex: k.sheetIndex,
      kind: k.kind,
      beatKind: k.beatKind || null,
      label: k.label,
      pid: k.path && k.path.pid,
      fromPid: k.path && k.path.fromPid,
      toPid: k.path && k.path.toPid,
      type: k.path && k.path.type,
      orphan: k.path && !!k.path.orphan,
      to: k.path && k.path.to ? { x: +k.path.to.x.toFixed(1), y: +k.path.to.y.toFixed(1) } : null,
    }));
    const beats = frames.filter((f) => f.kind === 'beat_end');
    return {
      banner: (document.getElementById('sheetAlignBannerText') || {}).textContent,
      nFrames: frames.length,
      beats,
      hasNextHere: String(fetchSheetInkPaths).includes('nextHere'),
      hasMask: !!document.getElementById('sheetDigitMaskLayer'),
    };
  });

  console.log(JSON.stringify(result, null, 2));

  const labels = result.beats.map((b) => b.label).join(' | ');
  const ok120 = result.beats.some((b) => /Pass #1 → #3/.test(b.label));
  const badScreen1 = result.beats.some((b) => /Screen #1/.test(b.label));
  const ok121 = result.beats.filter((b) => /Screen #4|Screen #5|Pass #3 → #1/.test(b.label));
  const ok122 = result.beats.some((b) => /Dribble #1/.test(b.label))
    && result.beats.some((b) => /Cut #2/.test(b.label))
    && result.beats.some((b) => /Pass #1 → #2/.test(b.label));
  const dribbleIdx = result.beats.findIndex((b) => /Dribble #1/.test(b.label));
  const cut2Idx = result.beats.findIndex((b) => /Cut #2/.test(b.label));
  const pass12Idx = result.beats.findIndex((b) => /Pass #1 → #2/.test(b.label));
  const order122 = dribbleIdx >= 0 && cut2Idx > dribbleIdx && pass12Idx > cut2Idx;

  console.log('LABELS', labels);
  console.log('CHECK', {
    ok120, badScreen1, ok121: ok121.length, ok122, order122, hasNextHere: result.hasNextHere,
  });

  await browser.close();
  if (!ok120 || badScreen1 || !ok122 || !order122) {
    process.exit(1);
  }
  console.log('PASS');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
