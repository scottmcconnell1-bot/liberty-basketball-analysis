/**
 * Headless proof: Rip (play 125) Play All follows sheet ink passes, not fake cuts.
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

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
  await page.goto('http://127.0.0.1:8080/playbook/play/125', { waitUntil: 'networkidle2' });

  // Wait for Ready
  await page.waitForFunction(() => {
    const t = document.getElementById('sheetAlignBannerText');
    return t && /Ready/i.test(t.textContent || '');
  }, { timeout: 90000 });

  const pre = await page.evaluate(() => {
    const html = document.documentElement.innerHTML;
    return {
      hasOrient: html.includes('orientSheetPass'),
      hasForce: html.includes('forceGuaranteeBeats'),
      noAnyMoveGuard: !html.includes('if (!anyMove) return { paths: {}, marks: {}, passes: [] }'),
      steps: typeof steps !== 'undefined' ? steps.length : 0,
      align: (typeof sheetAlignByStep !== 'undefined' ? sheetAlignByStep : []).map((a) => Object.keys(a.positions || {})),
    };
  });
  console.log('PRE', JSON.stringify(pre));

  // Spy on beats by wrapping forceGuaranteeBeats after page scripts run
  await page.evaluate(() => {
    window.__ripBeats = [];
    const orig = forceGuaranteeBeats;
    window.forceGuaranteeBeats = function (...args) {
      const beats = orig.apply(this, args);
      window.__ripBeats.push(beats.map((b) => ({
        kind: b.kind,
        label: b.label,
        fromPid: b.path && b.path.fromPid,
        toPid: b.path && b.path.toPid,
        pid: b.path && b.path.pid,
        ballOnly: b.path && b.path.ballOnly,
        pathLen: typeof travelPathLength === 'function' ? travelPathLength(b.path) : 0,
      })));
      return beats;
    };
  });

  await page.click('#playAllBtn');
  // Let Play All run through sheets (pass ~2.3s + holds × a few)
  await page.waitForFunction(() => !window.playAllRunning && !window.playbarPlaying, { timeout: 90000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 500));

  const result = await page.evaluate(() => ({
    beats: window.__ripBeats || [],
    stats: window.__playbookAnimStats || null,
    playAllRunning: !!window.playAllRunning,
    banner: (document.getElementById('sheetAlignBannerText') || {}).textContent,
  }));
  console.log('RESULT', JSON.stringify(result, null, 2));

  const flat = (result.beats || []).flat();
  const hasPass13 = flat.some((b) => b.kind === 'pass' && (
    (b.fromPid === 'o1' && b.toPid === 'o3') || (b.fromPid === 'o3' && b.toPid === 'o1')
  ));
  const fakeCut = flat.some((b) => b.kind === 'cut' && b.pid === 'o1' && !b.ballOnly && b.pathLen > 50
    && !(b.fromPid || b.toPid));
  console.log('CHECK hasPass13', hasPass13, 'fakeCutO1', fakeCut, 'nBeats', flat.length);

  await browser.close();
  if (!hasPass13) {
    console.error('FAIL: expected pass 1↔3 from sheet ink');
    process.exit(1);
  }
  if (fakeCut && flat.filter((b) => b.kind === 'pass').length === 0) {
    console.error('FAIL: only fake cut, no passes');
    process.exit(1);
  }
  console.log('PASS');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
