"""Apply sheet digit mask UI to playbook.html + playbook.css."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HTML = ROOT / "templates" / "playbook.html"
CSS = ROOT / "static" / "css" / "playbook.css"


def main() -> None:
    text = HTML.read_text(encoding="utf-8")

    old1 = (
        '        <g id="courtLayer"></g>\n'
        '        <g id="sheetUnderlayLayer"></g>\n'
        '        <g id="arrowLayer"></g>\n'
        '        <g id="playerLayer"></g>'
    )
    new1 = (
        '        <g id="courtLayer"></g>\n'
        '        <g id="sheetUnderlayLayer"></g>\n'
        "        <!-- Covers printed OCR digits on the sheet underlay (tokens stay above). -->\n"
        '        <g id="sheetDigitMaskLayer" class="sheet-digit-mask-layer" aria-hidden="true"></g>\n'
        '        <g id="arrowLayer"></g>\n'
        '        <g id="playerLayer"></g>'
    )
    if "sheetDigitMaskLayer" not in text:
        assert text.count(old1) == 1, f"svg layer count={text.count(old1)}"
        text = text.replace(old1, new1, 1)

    old2 = (
        "const PLAYER_RADIUS = 16;\n"
        "const DEFENSE_RADIUS = 7;\n"
        "const PLAYER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6'];"
    )
    new2 = (
        "const PLAYER_RADIUS = 16;\n"
        "const DEFENSE_RADIUS = 7;\n"
        "/** Cover printed sheet digits (large black 1-5). OCR detection stays; set true or\n"
        " *  add class `playbook-show-sheet-digits` on <body> to reveal sheet glyphs again. */\n"
        "const SHOW_SHEET_PRINTED_DIGITS = !!(typeof window !== 'undefined' && window.__playbookShowSheetDigits);\n"
        "const SHEET_DIGIT_MASK_RADIUS = 26;\n"
        "const PLAYER_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6'];"
    )
    if "SHOW_SHEET_PRINTED_DIGITS" not in text:
        assert text.count(old2) == 1, f"consts count={text.count(old2)}"
        text = text.replace(old2, new2, 1)

    if "renderSheetDigitMasks" not in text:
        m = re.search(
            r"function clearSheetUnderlay\(\) \{.*?\n"
            r"function showSheetUnderlay\(stepIndex\) \{.*?\n\}\n\n"
            r"async function ensureSheetAlignment",
            text,
            re.S,
        )
        assert m, "clear/showSheetUnderlay block not found"
        replacement = r"""function clearSheetUnderlay() {
  const layer = document.getElementById('sheetUnderlayLayer');
  if (layer) layer.innerHTML = '';
  clearSheetDigitMasks();
  setSheetCourtMode(false);
}

function clearSheetDigitMasks() {
  const layer = document.getElementById('sheetDigitMaskLayer');
  if (layer) layer.innerHTML = '';
}

/**
 * Paint white disks over OCR digit centers so large black sheet numbers
 * do not compete with colored tokens. Detection / positions unchanged.
 * Toggle off (show printed digits): window.__playbookShowSheetDigits = true
 * or add class playbook-show-sheet-digits on <body>.
 */
function renderSheetDigitMasks(stepIndex) {
  const layer = document.getElementById('sheetDigitMaskLayer');
  if (!layer) return;
  layer.innerHTML = '';
  const showPrinted = SHOW_SHEET_PRINTED_DIGITS
    || (typeof document !== 'undefined' && document.body
      && document.body.classList.contains('playbook-show-sheet-digits'));
  if (showPrinted || useSheetSlideshowMode()) return;
  if (!playHasSheets() || !steps[stepIndex] || !steps[stepIndex].source_image) return;
  // Prefer THIS sheet's OCR only (not carry-forward) — masks must sit on underlay glyphs.
  const align = sheetAlignByStep[stepIndex];
  const pos = (align && align.positions) || sheetPositionsForStep(stepIndex) || {};
  Object.keys(pos).forEach((pid) => {
    if (!String(pid).startsWith('o')) return;
    const p = pos[pid];
    if (!p || typeof p.x !== 'number' || typeof p.y !== 'number') return;
    const disk = makeCircle(p.x, p.y, SHEET_DIGIT_MASK_RADIUS, '#ffffff', 'none', 0);
    disk.setAttribute('class', 'sheet-digit-mask');
    disk.style.pointerEvents = 'none';
    layer.appendChild(disk);
  });
}

function showSheetUnderlay(stepIndex) {
  const layer = document.getElementById('sheetUnderlayLayer');
  if (!layer) return;
  layer.innerHTML = '';
  const url = steps[stepIndex] && steps[stepIndex].source_image;
  if (!url) {
    setSheetCourtMode(false);
    clearSheetDigitMasks();
    return;
  }
  setSheetCourtMode(true);
  const svgW = isFullCourt ? 500 : COURT_W;
  const svgH = isFullCourt ? 940 : COURT_H;
  const slideshow = useSheetSlideshowMode();
  const frac = (!slideshow && sheetAlignByStep[stepIndex] && sheetAlignByStep[stepIndex].court_frac) || null;
  // Sheet ink IS the court. Keep underlay readable so printed marks show under tokens.
  const img = document.createElementNS('http://www.w3.org/2000/svg', 'image');
  img.setAttribute('href', url);
  img.setAttributeNS('http://www.w3.org/1999/xlink', 'href', url);
  if (frac && typeof frac.x0 === 'number' && frac.x1 > frac.x0 && frac.y1 > frac.y0) {
    const cw = frac.x1 - frac.x0;
    const ch = frac.y1 - frac.y0;
    img.setAttribute('x', String(-frac.x0 / cw * svgW));
    img.setAttribute('y', String(-frac.y0 / ch * svgH));
    img.setAttribute('width', String(svgW / cw));
    img.setAttribute('height', String(svgH / ch));
    img.setAttribute('preserveAspectRatio', 'none');
    img.setAttribute('opacity', '0.88');
  } else {
    img.setAttribute('x', '0');
    img.setAttribute('y', '0');
    img.setAttribute('width', String(svgW));
    img.setAttribute('height', String(svgH));
    img.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    img.setAttribute('opacity', slideshow ? '0.98' : '0.78');
  }
  img.style.pointerEvents = 'none';
  layer.appendChild(img);
  renderSheetDigitMasks(stepIndex);
}

async function ensureSheetAlignment"""
        text = text[: m.start()] + replacement + text[m.end() :]

    HTML.write_text(text, encoding="utf-8")
    print("html", HTML.stat().st_size)
    print("mask", "sheetDigitMaskLayer" in text and "renderSheetDigitMasks" in text)
    print("triangle", "isTrianglePlay" in text)

    css = CSS.read_text(encoding="utf-8")
    if "sheet-digit-mask-layer" not in css:
        css += """

/* White disks covering printed OCR digits on sheet underlay (default: on).
   Reveal sheet glyphs: body.playbook-show-sheet-digits or window.__playbookShowSheetDigits = true */
.sheet-digit-mask-layer {
  pointer-events: none;
}
.sheet-digit-mask {
  fill: #ffffff;
}
body.playbook-show-sheet-digits .sheet-digit-mask-layer {
  display: none;
}
"""
        CSS.write_text(css, encoding="utf-8")
    print("css", CSS.stat().st_size)


if __name__ == "__main__":
    main()
