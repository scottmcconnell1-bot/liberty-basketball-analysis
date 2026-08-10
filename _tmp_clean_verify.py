"""Verify clean court: no underlay image, no digit masks, SVG court visible."""
from playwright.sync_api import sync_playwright
import json
import time


def check(play_id: int) -> dict:
    url = f"http://127.0.0.1:8080/playbook/play/{play_id}?_={int(time.time())}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_function(
            """() => {
              const t = (document.getElementById('sheetAlignBannerText') || {}).textContent || '';
              return t === 'Ready to play';
            }""",
            timeout=90000,
        )
        detail = page.evaluate(
            """() => {
              const court = document.getElementById('courtLayer');
              const underlay = document.getElementById('sheetUnderlayLayer');
              const masks = document.getElementById('sheetDigitMaskLayer');
              const players = document.getElementById('playerLayer');
              const tokenSample = [];
              (players || document.createElement('g')).querySelectorAll('.player-token').forEach((g, i) => {
                if (i > 4) return;
                const circ = [...g.querySelectorAll('circle')].map((c) => ({
                  r: c.getAttribute('r'),
                  fill: c.getAttribute('fill'),
                  stroke: c.getAttribute('stroke'),
                  sw: c.getAttribute('stroke-width'),
                }));
                tokenSample.push({ id: g.getAttribute('data-player') || g.id, circ });
              });
              return {
                sheetCourtMode: typeof sheetCourtMode !== 'undefined' ? sheetCourtMode : 'n/a',
                courtChildCount: court ? court.childElementCount : -1,
                courtFirstTag: court && court.firstElementChild ? court.firstElementChild.tagName : null,
                courtHasPath: !!(court && court.querySelector('path')),
                courtHasLaneRect: !!(court && [...court.querySelectorAll('rect')].some(
                  (r) => r.getAttribute('width') === '160')),
                underlayKids: underlay ? underlay.childElementCount : -1,
                underlayHasImage: !!(underlay && underlay.querySelector('image')),
                maskCircleCount: masks ? masks.querySelectorAll('circle').length : -1,
                maskHTMLLen: masks ? masks.innerHTML.length : -1,
                offenseTokens: players
                  ? players.querySelectorAll('.player-token[data-player^="o"]').length
                  : -1,
                tokenSample,
                showSheetClean: (String(showSheetUnderlay)).includes('Clean animated court'),
                renderMasksClearsOnly: (String(renderSheetDigitMasks)).includes('clearSheetDigitMasks')
                  && !(String(renderSheetDigitMasks)).includes('makeCircle'),
              };
            }"""
        )
        page.screenshot(path=f"_tmp_clean_idle_{play_id}.png")
        # Start Play All and sample mid-animation
        page.click("#playAllBtn")
        page.wait_for_timeout(3500)
        mid = page.evaluate(
            """() => ({
              sheetCourtMode,
              underlayHasImage: !!(document.querySelector('#sheetUnderlayLayer image')),
              maskCircles: document.querySelectorAll('#sheetDigitMaskLayer circle').length,
              courtHasPath: !!document.querySelector('#courtLayer path'),
              animHint: (document.getElementById('sheetAnimHint') || {}).textContent || '',
              offenseTokens: document.querySelectorAll('.player-token[data-player^="o"]').length,
            })"""
        )
        detail["duringPlay"] = mid
        detail["url"] = url
        page.screenshot(path=f"_tmp_clean_play_{play_id}.png")
        browser.close()
        return detail


if __name__ == "__main__":
    out = {125: check(125), 127: check(127)}
    print(json.dumps(out, indent=2))
