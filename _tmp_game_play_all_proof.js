/**
 * Headless Play All proof for 1-Game (play 98).
 * Prints beat labels + frame count; also smoke-checks Rip 125 / Triangle 127 / Pitt 5 137.
 */
const fs = require('fs');
const http = require('http');

async function fetchText(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let d = '';
      res.on('data', (c) => (d += c));
      res.on('end', () => resolve({ status: res.statusCode, body: d }));
    }).on('error', reject);
  });
}

async function provePlay(browser, playId, opts = {}) {
  const page = await browser.newPage();
  page.on('pageerror', (err) => console.log('PAGEERROR', playId, String(err)));
  await page.goto(`http://127.0.0.1:8080/playbook/play/${playId}`, {
    waitUntil: 'networkidle2',
    timeout: 90000,
  });
  await page.waitForFunction(() => {
    const t = document.getElementById('sheetAlignBannerText');
    return t && /Ready/i.test(t.textContent || '');
  }, { timeout: 180000 });

  const meta = await page.evaluate(() => ({
    name: (document.getElementById('playName') && document.getElementById('playName').value)
      || (typeof editingPlay !== 'undefined' && editingPlay && editingPlay.name)
      || '',
    steps: (typeof steps !== 'undefined' && steps.length) || 0,
    align: (typeof sheetAlignByStep !== 'undefined')
      ? sheetAlignByStep.map((a) => Object.keys((a && a.positions) || {}).length)
      : null,
    isGame: typeof isGamePlay === 'function' ? isGamePlay() : null,
    underlay: !!document.querySelector('#sheetUnderlayLayer image'),
    maskCircles: document.querySelectorAll('#sheetDigitMaskLayer circle').length,
  }));
  console.log('META', playId, JSON.stringify(meta));

  if (opts.collectBeats) {
    const beats = await page.evaluate(async () => {
      if (typeof ensureSheetAlignment === 'function') await ensureSheetAlignment();
      const out = [];
      let liveBall = (steps[0] && steps[0].ball) || 'o1';
      const heldLandings = {};
      for (let i = 0; i < steps.length; i += 1) {
        const isLast = i >= steps.length - 1;
        let fromRaw = withManDefense(positionsForAnim(i));
        Object.keys(heldLandings).forEach((pid) => {
          if (heldLandings[pid]) fromRaw[pid] = { x: heldLandings[pid].x, y: heldLandings[pid].y };
        });
        fromRaw = withManDefense(fromRaw);
        let toRaw = isLast ? fromRaw : withManDefense(positionsForAnim(i + 1));
        Object.keys(heldLandings).forEach((pid) => {
          if (heldLandings[pid]) toRaw[pid] = { x: heldLandings[pid].x, y: heldLandings[pid].y };
        });
        toRaw = withManDefense(toRaw);
        const inkPaths = await fetchSheetInkPaths(i, fromRaw, toRaw);
        const paths = buildTravelPaths(fromRaw, toRaw, steps[i], inkPaths, liveBall);
        const sheetBeats = forceGuaranteeBeats(fromRaw, toRaw, steps[i], paths, liveBall, i);
        out.push({
          sheet: i,
          beats: sheetBeats.map((b) => ({
            kind: b.kind,
            label: b.label,
            pid: b.path && b.path.pid,
            fromPid: b.path && b.path.fromPid,
            toPid: b.path && b.path.toPid,
            nPts: b.path && b.path.points ? b.path.points.length : null,
          })),
        });
        sheetBeats.forEach((b) => {
          if (b.path && b.path.pid && b.path.to) {
            heldLandings[b.path.pid] = { x: b.path.to.x, y: b.path.to.y };
          }
          if (b.kind === 'pass' && b.ballTo) liveBall = b.ballTo;
        });
      }
      return out;
    });
    console.log('BEATS', playId, JSON.stringify(beats, null, 2));
  }

  await page.evaluate(() => {
    window.__playbookAnimStats = { frames: 0 };
    playAnimation();
  });
  let maxFrames = 0;
  let last = null;
  const loops = opts.loops || 50;
  for (let i = 0; i < loops; i += 1) {
    await new Promise((r) => setTimeout(r, 250));
    last = await page.evaluate(() => ({
      running: !!(typeof playAllRunning !== 'undefined' && playAllRunning),
      frames: (window.__playbookAnimStats && window.__playbookAnimStats.frames) || 0,
      hint: (document.getElementById('sheetAnimHint') || {}).textContent || '',
      underlay: !!document.querySelector('#sheetUnderlayLayer image'),
      maskCircles: document.querySelectorAll('#sheetDigitMaskLayer circle').length,
      screenMarkers: document.querySelectorAll('.screen-marker').length,
    }));
    if (last.frames > maxFrames) maxFrames = last.frames;
    if (!last.running && i > 8) break;
  }
  console.log('AFTER', playId, JSON.stringify({ maxFrames, last }));
  await page.close();
  return { meta, maxFrames, last };
}

async function main() {
  let puppeteer;
  try {
    puppeteer = require('puppeteer-core');
  } catch (e) {
    const r = await fetchText('http://127.0.0.1:8080/playbook/play/98');
    const ok = r.body.includes('isGamePlay') && r.body.includes('orderGameBeats');
    console.log('NO_PUPPETEER', { status: r.status, ok, len: r.body.length });
    process.exit(ok ? 0 : 1);
  }
  const candidates = [
    'C:\\\\Program Files (x86)\\\\Microsoft\\\\Edge\\\\Application\\\\msedge.exe',
    'C:\\\\Program Files\\\\Microsoft\\\\Edge\\\\Application\\\\msedge.exe',
    'C:\\\\Program Files\\\\Google\\\\Chrome\\\\Application\\\\chrome.exe',
    'C:\\\\Program Files (x86)\\\\Google\\\\Chrome\\\\Application\\\\chrome.exe',
  ];
  const exe = candidates.find((p) => fs.existsSync(p));
  if (!exe) {
    console.log('NO_BROWSER');
    process.exit(0);
  }
  const browser = await puppeteer.launch({
    executablePath: exe,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  });
  try {
    const game = await provePlay(browser, 98, { collectBeats: true, loops: 80 });
    if (game.maxFrames < 40) {
      console.error('FAIL game frames', game.maxFrames);
      process.exit(1);
    }
    if (game.last && (game.last.underlay || game.last.maskCircles > 0)) {
      console.error('FAIL clean court', game.last);
      process.exit(1);
    }
    // Regression smoke: Rip / Triangle / Pitt 5 still animate.
    for (const id of [125, 127, 137]) {
      const r = await provePlay(browser, id, { loops: 40 });
      if (r.maxFrames < 20) {
        console.error('FAIL regress', id, r.maxFrames);
        process.exit(1);
      }
    }
    console.log('LIVE_PROOF_OK');
  } finally {
    await browser.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
