"""Live verify Pitt 5 Play All: spacing, around path, no T-bar, #4 holds left."""
import json
import sys
import time

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

url = f"http://127.0.0.1:8080/playbook/play/137?_={int(time.time())}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_function(
        """() => {
          const t = (document.getElementById('sheetAlignBannerText')||{}).textContent || '';
          return t.includes('Ready') || t.includes('Aligned') || t.includes('play');
        }""",
        timeout=45000,
    )
    page.wait_for_timeout(1500)

    info = page.evaluate(
        """() => ({
        stepImgs: (typeof steps !== 'undefined' ? steps : []).map(s => ({
          label: s.label,
          src: (s.source_image || '').split('/').pop(),
        })),
        isPitt5: typeof isPitt5Play === 'function' && isPitt5Play(),
        underlayKids: (document.getElementById('sheetUnderlayLayer')||{}).childElementCount || 0,
        maskCircles: document.querySelectorAll('#sheetDigitMaskLayer circle').length,
        drawGuardsPitt5: (drawScreenMarker && drawScreenMarker.toString() || '').includes('isPitt5Play'),
      })"""
    )

    page.evaluate(
        """() => {
      window.__pitt5Beats = [];
      window.__pitt5ScreenMarkers = 0;
      window.__pitt5FinalO4 = null;
      const origDraw = drawScreenMarker;
      drawScreenMarker = function(at) {
        window.__pitt5ScreenMarkers += 1;
        return origDraw(at);
      };
      const orig = forceGuaranteeBeats;
      forceGuaranteeBeats = function(fromRaw, toRaw, step, paths, ballPid, sheetIndex) {
        const beats = orig(fromRaw, toRaw, step, paths, ballPid, sheetIndex);
        window.__pitt5Beats.push({
          sheetIndex,
          beats: (beats || []).map(b => ({
            kind: b.kind,
            label: b.label,
            pid: b.path && b.path.pid,
            type: b.path && b.path.type,
            pitt5Drop: !!(b.path && b.path.pitt5Drop),
            nPoints: b.path && b.path.points ? b.path.points.length : null,
            from: b.path && b.path.from ? { x: +b.path.from.x.toFixed(1), y: +b.path.from.y.toFixed(1) } : null,
            to: b.path && b.path.to ? { x: +b.path.to.x.toFixed(1), y: +b.path.to.y.toFixed(1) } : null,
            mid: (b.path && b.path.points && b.path.points[1])
              ? { x: +b.path.points[1].x.toFixed(1), y: +b.path.points[1].y.toFixed(1) }
              : null,
          })),
        });
        return beats;
      };
      const origPlay = playActionBeats;
      playActionBeats = async function(fromRaw, toRaw, beats, ballRef, durationMs) {
        const live = await origPlay(fromRaw, toRaw, beats, ballRef, durationMs);
        if (live && live.o4) {
          window.__pitt5FinalO4 = { x: +live.o4.x.toFixed(1), y: +live.o4.y.toFixed(1) };
        }
        return live;
      };
    }"""
    )

    # Drive Play without end-reset so final hold is observable.
    page.evaluate(
        """async () => {
      playAllRunning = true;
      playbarPlaying = true;
      setPlayAllButton(true);
      await playSheetsDirectly({ resetAtEnd: false, alreadyRunning: true });
    }"""
    )
    page.wait_for_function(
        "() => !playAllRunning && !playbarPlaying",
        timeout=90000,
    )
    page.wait_for_timeout(500)

    captured = page.evaluate("() => window.__pitt5Beats || []")
    final = page.evaluate(
        """() => {
      const tokens = {};
      document.querySelectorAll('#playerLayer g').forEach(g => {
        const label = (g.textContent || '').trim();
        const t = g.getAttribute('transform') || '';
        const m = /translate\\(([-\\d.]+),\\s*([-\\d.]+)\\)/.exec(t);
        if (m && /^[1-5]$/.test(label)) {
          tokens['o' + label] = { x: +(+m[1]).toFixed(1), y: +(+m[2]).toFixed(1) };
        }
      });
      return {
        animHint: (document.getElementById('sheetAnimHint')||{}).textContent || '',
        underlayKids: (document.getElementById('sheetUnderlayLayer')||{}).childElementCount || 0,
        maskCircles: document.querySelectorAll('#sheetDigitMaskLayer circle').length,
        screenMarkerCalls: window.__pitt5ScreenMarkers || 0,
        screenMarkerEls: document.querySelectorAll('.screen-marker').length,
        finalO4FromBeats: window.__pitt5FinalO4,
        tokens,
      };
    }"""
    )

    page.screenshot(path="_tmp_pitt5_play.png")
    browser.close()

    # De-dupe sheet captures (playbar build may also call forceGuaranteeBeats).
    seen = set()
    all_beats = []
    for block in captured:
        key = (block.get("sheetIndex"), tuple(
            (b.get("label"), b.get("pitt5Drop"), str(b.get("to")))
            for b in (block.get("beats") or [])
        ))
        if key in seen:
            continue
        seen.add(key)
        for b in block.get("beats") or []:
            all_beats.append({**b, "sheetIndex": block.get("sheetIndex")})

    print("URL", url)
    print("INFO", json.dumps(info))
    print("\n=== BEAT LIST ===")
    for i, b in enumerate(all_beats, 1):
        lab = (b.get("label") or "").replace("\u2192", "->")
        print(
            f"{i}. sheet={b.get('sheetIndex')} {lab} kind={b.get('kind')} "
            f"pid={b.get('pid')} from={b.get('from')} to={b.get('to')} "
            f"mid={b.get('mid')} nPts={b.get('nPoints')} drop={b.get('pitt5Drop')}"
        )

    o4_moves = [b for b in all_beats if b.get("pid") == "o4"]
    o5 = next((b for b in all_beats if b.get("pid") == "o5"), None)
    screen = o4_moves[0] if o4_moves else {}
    drop = o4_moves[-1] if len(o4_moves) >= 2 else {}
    st, dt = screen.get("to") or {}, drop.get("to") or {}
    o5s = (o5 or {}).get("from") or {}
    gap = ((st["x"] - o5s["x"]) ** 2 + (st["y"] - o5s["y"]) ** 2) ** 0.5 if st and o5s else None
    mid = (o5 or {}).get("mid") or {}
    tok4 = final.get("finalO4FromBeats") or (final.get("tokens") or {}).get("o4")

    checks = {
        "OK_PAGES": info.get("stepImgs") and len(info["stepImgs"]) == 2,
        "OK_CLEAN": final.get("underlayKids") == 0 and final.get("maskCircles") == 0,
        "OK_SCREEN_STRAIGHT": screen.get("nPoints") == 2,
        "OK_SCREEN_GAP": gap is not None and gap >= 55,
        "OK_AROUND": mid.get("x", 0) > st.get("x", 999) + 20 and (o5 or {}).get("nPoints") == 4,
        "OK_DROP_LEFT": bool(drop.get("pitt5Drop")) and dt.get("x", 999) < 220 and dt.get("y", 999) < 140,
        # drawScreenMarker may still be invoked; Pitt 5 guard must leave zero DOM nodes.
        "OK_NO_TBAR": final.get("screenMarkerEls") == 0,
        "OK_HOLD_LEFT": bool(tok4) and tok4.get("x", 999) < 220 and tok4.get("y", 999) < 140,
    }
    print("\nCHECKS", json.dumps(checks, indent=2))
    print("gap", round(gap, 1) if gap else None, "screen_tip", st, "drop", dt, "mid5", mid, "final_o4", tok4)
    print("FINAL", json.dumps(final))
    if not all(checks.values()):
        raise SystemExit(1)
    print("ALL_OK")
