"""Verify digit masks on play 127/125 with Playwright."""
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("_tmp_digit_mask_verify.json")


def check(page, play_id: int) -> dict:
    page.goto(f"http://127.0.0.1:8080/playbook/play/{play_id}?_={int(time.time())}", wait_until="domcontentloaded")
    page.wait_for_selector("#courtSvg", timeout=30000)
    # Kick align if needed
    page.evaluate("typeof ensureSheetAlignment === 'function' && ensureSheetAlignment()")
    deadline = time.time() + 50
    info = {}
    while time.time() < deadline:
        info = page.evaluate(
            """() => {
              const layer = document.getElementById('sheetDigitMaskLayer');
              const masks = layer ? layer.querySelectorAll('.sheet-digit-mask').length : -1;
              const tokens = document.querySelectorAll('#playerLayer .player-token[data-type=\"offense\"]').length;
              const underImg = !!document.querySelector('#sheetUnderlayLayer image');
              const ready = !!(typeof sheetAlignReady !== 'undefined' && sheetAlignReady);
              const show = !!(typeof SHOW_SHEET_PRINTED_DIGITS !== 'undefined' && SHOW_SHEET_PRINTED_DIGITS);
              const triangle = !!(typeof isTrianglePlay === 'function' && isTrianglePlay());
              const pos = (sheetAlignByStep && sheetAlignByStep[0] && sheetAlignByStep[0].positions) || {};
              return {
                playId: null,
                masks, tokens, underImg, ready, showPrintedFlag: show, triangle,
                ocrKeys: Object.keys(pos),
                maskRadii: layer ? Array.from(layer.querySelectorAll('circle')).map(c => c.getAttribute('r')) : [],
              };
            }"""
        )
        info["playId"] = play_id
        if info.get("ready") and info.get("underImg") and info.get("masks", 0) >= 0:
            # allow one extra tick for masks after align refresh
            if info.get("masks", 0) > 0 or time.time() > deadline - 2:
                break
        page.wait_for_timeout(400)
    page.screenshot(path=f"_tmp_digit_mask_{play_id}.png", full_page=False)
    info["shot"] = f"_tmp_digit_mask_{play_id}.png"
    return info


def main() -> None:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        for pid in (127, 125):
            results.append(check(page, pid))
        browser.close()
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
