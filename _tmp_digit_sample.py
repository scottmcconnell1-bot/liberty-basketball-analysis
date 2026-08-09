"""Sample pixels near offense tokens to see if printed digits remain."""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image


def main() -> None:
    shot = Path("_tmp_digit_sample.png")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1100})
        page.goto("http://127.0.0.1:8080/playbook/play/127", wait_until="domcontentloaded")
        page.evaluate("typeof ensureSheetAlignment === 'function' && ensureSheetAlignment()")
        # wait until masks exist
        page.wait_for_function(
            "() => (document.querySelectorAll('#sheetDigitMaskLayer circle').length >= 3)",
            timeout=60000,
        )
        page.wait_for_timeout(500)
        geom = page.evaluate(
            """() => {
              const svg = document.getElementById('courtSvg');
              const rect = svg.getBoundingClientRect();
              const vb = (svg.getAttribute('viewBox') || '0 0 500 470').split(/\\s+/).map(Number);
              const [vx, vy, vw, vh] = vb;
              const toScreen = (x, y) => ({
                x: rect.x + ((x - vx) / vw) * rect.width,
                y: rect.y + ((y - vy) / vh) * rect.height,
              });
              const masks = [...document.querySelectorAll('#sheetDigitMaskLayer circle')].map((c) => {
                const cx = +c.getAttribute('cx');
                const cy = +c.getAttribute('cy');
                const r = +c.getAttribute('r');
                const s = toScreen(cx, cy);
                const sEdge = toScreen(cx + r, cy);
                return { cx, cy, r, sx: s.x, sy: s.y, sR: Math.abs(sEdge.x - s.x), fill: c.getAttribute('fill') };
              });
              const tokens = [...document.querySelectorAll('#playerLayer .player-token[data-type=\"offense\"]')].map((g) => {
                const t = g.getAttribute('transform') || '';
                const m = /translate\\(([-0-9.]+),\\s*([-0-9.]+)\\)/.exec(t);
                const x = m ? +m[1] : 0, y = m ? +m[2] : 0;
                const s = toScreen(x, y);
                return { pid: g.dataset.player, x, y, sx: s.x, sy: s.y };
              });
              return { masks, tokens, rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height } };
            }"""
        )
        page.screenshot(path=str(shot))
        browser.close()

    im = Image.open(shot).convert("RGB")
    samples = []
    for t in geom["tokens"]:
        # sample ring around token (outside token radius ~16 svg / ~ screen)
        sx, sy = int(t["sx"]), int(t["sy"])
        dark = 0
        total = 0
        # ring 22..38 px from center
        for dx in range(-40, 41, 2):
            for dy in range(-40, 41, 2):
                d2 = dx * dx + dy * dy
                if d2 < 22 * 22 or d2 > 38 * 38:
                    continue
                x, y = sx + dx, sy + dy
                if x < 0 or y < 0 or x >= im.width or y >= im.height:
                    continue
                r, g, b = im.getpixel((x, y))
                total += 1
                if r < 90 and g < 90 and b < 90:
                    dark += 1
        samples.append(
            {
                "pid": t["pid"],
                "sx": sx,
                "sy": sy,
                "darkRing": dark,
                "totalRing": total,
                "darkFrac": (dark / total) if total else None,
            }
        )

    out = {"geom": geom, "samples": samples}
    Path("_tmp_digit_sample.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"samples": samples, "maskCount": len(geom["masks"]), "mask0": geom["masks"][:1]}, indent=2))


if __name__ == "__main__":
    main()
