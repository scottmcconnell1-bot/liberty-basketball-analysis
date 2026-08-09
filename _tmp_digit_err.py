"""Check playbook console errors after recovery."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    errs: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console", lambda m: errs.append(f"console:{m.type}:{m.text}") if m.type == "error" else None)
        page.goto("http://127.0.0.1:8080/playbook/play/127", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        info = page.evaluate(
            """() => ({
              ready: typeof sheetAlignReady === 'undefined' ? 'UNDEF' : sheetAlignReady,
              hasEnsure: typeof ensureSheetAlignment,
              hasTriangle: typeof isTrianglePlay,
              hasMask: typeof renderSheetDigitMasks,
              hasShow: typeof showSheetUnderlay,
              maskKids: (document.getElementById('sheetDigitMaskLayer')||{}).childElementCount || 0,
              underKids: (document.getElementById('sheetUnderlayLayer')||{}).childElementCount || 0,
            })"""
        )
        page.screenshot(path="_tmp_digit_err.png")
        browser.close()
    Path("_tmp_digit_err.json").write_text(json.dumps({"errs": errs[:20], "info": info}, indent=2), encoding="utf-8")
    print(json.dumps({"errs": errs[:20], "info": info}, indent=2))


if __name__ == "__main__":
    main()
