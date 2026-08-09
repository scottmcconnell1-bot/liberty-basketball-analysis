"""Inspect mask geometry vs tokens; sample screenshot pixels."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("_tmp_mask_geom.json")


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.goto("http://127.0.0.1:8080/playbook/play/127", wait_until="domcontentloaded")
        page.evaluate("typeof ensureSheetAlignment === 'function' && ensureSheetAlignment()")
        page.wait_for_function("() => !!(window.sheetAlignReady)", timeout=45000)
        page.wait_for_timeout(800)
        info = page.evaluate(
            """() => {
              const layer = document.getElementById('sheetDigitMaskLayer');
              const masks = [...(layer ? layer.querySelectorAll('circle') : [])].map((c) => ({
                cx: +c.getAttribute('cx'),
                cy: +c.getAttribute('cy'),
                r: +c.getAttribute('r'),
                fill: c.getAttribute('fill'),
                className: c.getAttribute('class'),
              }));
              const tokens = [...document.querySelectorAll('#playerLayer .player-token[data-type=\"offense\"]')].map((g) => {
                const t = g.getAttribute('transform') || '';
                const m = /translate\\(([-0-9.]+),\\s*([-0-9.]+)\\)/.exec(t);
                return { pid: g.dataset.player, x: m ? +m[1] : null, y: m ? +m[2] : null };
              });
              const cs = layer ? getComputedStyle(layer) : null;
              const svg = document.getElementById('courtSvg');
              return {
                masks,
                tokens,
                layerDisplay: cs && cs.display,
                layerVisibility: cs && cs.visibility,
                layerHtml: layer ? layer.outerHTML.slice(0, 500) : null,
                underOpacity: (document.querySelector('#sheetUnderlayLayer image') || {}).getAttribute
                  ? document.querySelector('#sheetUnderlayLayer image').getAttribute('opacity')
                  : null,
                viewBox: svg && svg.getAttribute('viewBox'),
                showFlag: window.SHOW_SHEET_PRINTED_DIGITS,
                bodyClass: document.body.className,
              };
            }"""
        )
        page.screenshot(path="_tmp_digit_mask_127b.png")
        browser.close()
    OUT.write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2)[:2000])


if __name__ == "__main__":
    main()
