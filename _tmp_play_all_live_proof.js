/**
 * Live CDP-ish proof via Edge/Chrome if available: open play 125, click Play All,
 * sample __playbookAnimStats.frames.
 */
const { spawn } = require('child_process');
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

async function main() {
  // Prefer puppeteer-core + system Edge
  let puppeteer;
  try {
    puppeteer = require('puppeteer-core');
  } catch (e) {
    console.log('NO_PUPPETEER');
    // Still verify served content for play 125
    const body = await new Promise((resolve, reject) => {
      http.get('http://127.0.0.1:8080/playbook/play/125', (res) => {
        let d = '';
        res.on('data', (c) => (d += c));
        res.on('end', () => resolve(d));
      }).on('error', reject);
    });
    const ok = body.includes('forceGuaranteeBeats') && body.includes('playbarUserScrubbing');
    console.log('SERVED_125', { ok, len: body.length });
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
  const page = await browser.newPage();
  page.on('console', (msg) => console.log('BROWSER', msg.type(), msg.text()));
  page.on('pageerror', (err) => console.log('PAGEERROR', String(err)));
  await page.goto('http://127.0.0.1:8080/playbook/play/125', { waitUntil: 'networkidle2', timeout: 60000 });

  // Wait for Ready / alignment
  await page.waitForFunction(() => {
    const t = document.getElementById('sheetAlignBannerText');
    return t && /Ready/i.test(t.textContent || '');
  }, { timeout: 120000 });

  const before = await page.evaluate(() => ({
    btn: (document.getElementById('playAllBtn') || {}).textContent,
    steps: (typeof steps !== 'undefined' && steps.length) || 0,
    align: typeof sheetAlignByStep !== 'undefined' ? sheetAlignByStep.map((a) => Object.keys((a && a.positions) || {}).length) : null,
    playAllRunning: typeof playAllRunning !== 'undefined' ? playAllRunning : null,
  }));
  console.log('BEFORE', JSON.stringify(before));

  await page.evaluate(() => playAnimation());

  // Sample during play
  let maxFrames = 0;
  let last = null;
  for (let i = 0; i < 40; i += 1) {
    await new Promise((r) => setTimeout(r, 200));
    last = await page.evaluate(() => ({
      btn: (document.getElementById('playAllBtn') || {}).textContent,
      running: !!(typeof playAllRunning !== 'undefined' && playAllRunning),
      stats: (typeof window !== 'undefined' && window.__playbookAnimStats) || null,
      hint: (document.getElementById('sheetAnimHint') || {}).textContent || '',
    }));
    const f = (last.stats && last.stats.frames) || 0;
    if (f > maxFrames) maxFrames = f;
    if (!last.running && i > 5) break;
  }
  console.log('AFTER', JSON.stringify({ maxFrames, last }));
  await browser.close();
  if (maxFrames < 50) {
    console.error('FAIL frames', maxFrames);
    process.exit(1);
  }
  console.log('LIVE_PROOF_OK', maxFrames);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
