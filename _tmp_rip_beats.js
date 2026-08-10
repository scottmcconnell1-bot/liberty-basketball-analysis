/**
 * Capture Play All beat labels + end positions for Rip 125.
 */
const fs = require('fs');
const puppeteer = require('puppeteer-core');

const candidates = [
  'C:\\\\Program Files (x86)\\\\Microsoft\\\\Edge\\\\Application\\\\msedge.exe',
  'C:\\\\Program Files\\\\Microsoft\\\\Edge\\\\Application\\\\msedge.exe',
  'C:\\\\Program Files\\\\Google\\\\Chrome\\\\Application\\\\chrome.exe',
];
const exe = candidates.find((p) => fs.existsSync(p));
if (!exe) {
  console.error('NO_BROWSER');
  process.exit(1);
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: exe,
    headless: true,
    args: ['--no-sandbox', '--disable-gpu'],
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(120000);
  page.on('console', (msg) => {
    const t = msg.text();
    if (t.includes('RIPBEAT') || t.includes('RIPDONE') || t.includes('RIPERR')) console.log(t);
  });

  await page.goto('http://127.0.0.1:8080/playbook/play/125', { waitUntil: 'networkidle2', timeout: 60000 });
  await page.waitForFunction(() => {
    const t = document.getElementById('sheetAlignBannerText');
    return t && /Ready/i.test(t.textContent || '');
  }, { timeout: 120000 });

  const report = await page.evaluate(async () => {
    const out = { sheets: [], err: null };
    try {
      // Monkeypatch to capture beats without full long animation waits if needed —
      // but run real playSheetsDirectly with shorter ANIM for speed.
      const orig = { ...ANIM };
      ANIM.MOVE_MS = 400;
      ANIM.LINE_PREVIEW_MS = 50;
      ANIM.HOLD_PASS_MS = 40;
      ANIM.HOLD_CUT_MS = 40;
      ANIM.HOLD_DRIBBLE_MS = 40;
      ANIM.HOLD_SCREEN_MS = 40;
      ANIM.HOLD_RELOCATE_MS = 40;
      ANIM.SHEET_END_HOLD_MS = 80;

      const origForce = forceGuaranteeBeats;
      window.__ripBeats = [];
      forceGuaranteeBeats = function (fromRaw, toRaw, step, paths, ballPid) {
        const beats = origForce(fromRaw, toRaw, step, paths, ballPid);
        const summary = (beats || []).map((b) => ({
          kind: b.kind,
          label: b.label,
          pid: b.path && b.path.pid,
          type: b.path && b.path.type,
          fromPid: b.path && b.path.fromPid,
          toPid: b.path && b.path.toPid,
          orphan: b.path && b.path.orphan,
          from: b.path && b.path.from,
          to: b.path && b.path.to,
          ballTo: b.ballTo,
          carryBall: b.carryBall,
        }));
        window.__ripBeats.push({
          stepLabel: step && step.label,
          ballPid,
          pathCount: (paths || []).length,
          paths: (paths || []).map((p) => ({
            pid: p.pid, type: p.type, ballOnly: p.ballOnly,
            fromPid: p.fromPid, toPid: p.toPid, orphan: p.orphan,
            from: p.from, to: p.to,
            nPts: p.points ? p.points.length : 0,
          })),
          beats: summary,
        });
        return beats;
      };

      const positions = [];
      const origSync = syncPlayerTokens;
      syncPlayerTokens = function (pos, ball) {
        origSync(pos, ball);
        const snap = {};
        for (let i = 1; i <= 5; i++) {
          const oid = 'o' + i;
          if (pos && pos[oid]) snap[oid] = { x: +pos[oid].x.toFixed(1), y: +pos[oid].y.toFixed(1) };
        }
        positions.push({ ball, snap, hint: (document.getElementById('sheetAnimHint') || {}).textContent || '' });
      };

      playAllRunning = true;
      playbarPlaying = true;
      await playSheetsDirectly({ resetAtEnd: false, alreadyRunning: true });

      // restore
      Object.assign(ANIM, orig);
      forceGuaranteeBeats = origForce;
      syncPlayerTokens = origSync;

      out.sheets = window.__ripBeats;
      out.positions = positions.slice(-12);
      // final token DOM positions
      const final = {};
      document.querySelectorAll('[data-pid^="o"]').forEach((el) => {
        final[el.getAttribute('data-pid')] = {
          x: parseFloat(el.getAttribute('cx') || el.style.left || 0),
          y: parseFloat(el.getAttribute('cy') || el.style.top || 0),
          transform: el.getAttribute('transform') || '',
        };
      });
      out.finalTokens = final;
      out.hint = (document.getElementById('sheetAnimHint') || {}).textContent || '';
    } catch (e) {
      out.err = String(e && e.stack || e);
    }
    return out;
  });

  console.log(JSON.stringify(report, null, 2));
  fs.writeFileSync('_tmp_rip_beats.json', JSON.stringify(report, null, 2));
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
