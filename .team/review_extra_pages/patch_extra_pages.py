"""Add BLOB/SLOB, Press, Press Break and Transition pages to the public playbook page.
Every code edit goes into the live page AND its PAGE_TEMPLATE copy (the page rebuilds itself
from the template on Save for everyone). The plays go into the live PLAYS_SAVED only (the
template holds the __PLAYS__ placeholder). Usage: patch_extra_pages.py <in.html> <plays.json> <out.html>
"""
import json
import sys

from tpl import enc, split

EDITS = []


def edit(old, new):
    EDITS.append((old, new))


# 1. Tabs.
edit('''    <button role="tab" data-page="defense">2 &middot; Defense</button>
''', '''    <button role="tab" data-page="defense">2 &middot; Defense</button>
    <button role="tab" data-page="blob">3 &middot; BLOB/SLOB</button>
    <button role="tab" data-page="press">4 &middot; Press</button>
    <button role="tab" data-page="pressbreak">5 &middot; Press Break</button>
    <button role="tab" data-page="transition">6 &middot; Transition</button>
''')

# 2. Styles: the viewer court sizes like the other courts; edit tools hidden on viewer pages.
edit('''  #manSec svg, #zoneSec svg { width: var(--cw) !important;''',
     '''  #manSec svg, #zoneSec svg, #fullSec svg { width: var(--cw) !important;''')
edit('''  #zoneSec .legend {''', '''  #fullSec svg { width: 100%; height: auto; display: block; border: 2px solid var(--line); border-radius: 6px; background: var(--court); user-select: none; }
  #fullSec .legend { display: flex; gap: 18px; flex-wrap: wrap; font-size: 16px; margin-bottom: 8px; }
  #fullSec .legend span { display: inline-flex; align-items: center; gap: 8px; }
  #fullSec .dot { width: 18px; height: 18px; border-radius: 50%; display: inline-block; }
  body.page-view #playAdd, body.page-view #playEdit, body.page-view #checkStack,
  body.page-view #m-reset, body.page-view #z-reset { display: none !important; }
  #zoneSec .legend {''')

# 3. The viewer section.
edit('''</main>''', '''<section id="fullSec" hidden>
  <div class="legend">
    <span><i class="dot" style="background:var(--off)"></i><b>Offense</b> = blue circles</span>
    <span id="f-defKey"><i class="dot" style="background:#fff;border:3px solid var(--def)"></i><b>Defense</b> = red X (start spots)</span>
    <span><i class="dot" style="background:var(--ball)"></i><b>Ball</b></span>
  </div>
  <svg id="f-court" viewBox="0 0 500 470" role="img" aria-label="Court showing the play"></svg>
</section>
</main>''')

# 4. Play lists for every page; deletes and merges cover the new pages too.
edit('''plays.offense = plays.offense || []; plays.defense = plays.defense || [];''',
     '''const PLAY_PAGES = ['offense', 'defense', 'blob', 'press', 'pressbreak', 'transition'];
PLAY_PAGES.forEach((k) => { plays[k] = plays[k] || []; });''')
edit('''['offense', 'defense'].forEach((k) => (PLAYS_SAVED[k] || []).forEach((p) => {''',
     '''PLAY_PAGES.forEach((k) => (PLAYS_SAVED[k] || []).forEach((p) => {''')
edit('''removedPlays.filter((r) => !['offense', 'defense'].some((k) =>''',
     '''removedPlays.filter((r) => !PLAY_PAGES.some((k) =>''')

# 5. Page list.
edit('''    kinds: [['man', 'Man'], ['zone', 'Zone']],
  },
};''', '''    kinds: [['man', 'Man'], ['zone', 'Zone']],
  },
  // Viewer pages: the coach's drawings played step by step (no dummy defense, no drawing tools).
  blob: {
    intro: "Baseline and sideline out-of-bounds plays, from the coach's drawings. Basket at the top. Pick a play and press Play.",
    kinds: [], court: 'half',
  },
  press: {
    intro: "Our press, from the coach's drawings. Red X = our defenders, blue = the other team. Full court.",
    kinds: [], court: 'full',
  },
  pressbreak: {
    intro: "Breaking the press, full court. We inbound under the top basket and bring it to the bottom basket. Red X = where the press starts.",
    kinds: [], court: 'full',
  },
  transition: {
    intro: 'Transition, full court. Pick a play and press Play.',
    kinds: [], court: 'full',
  },
};''')

# 6. No "Defense:" label when a page has no defense picker.
edit('''  row.innerHTML = '<span>Defense:</span>';''',
     '''  row.innerHTML = PAGES[page].kinds.length ? '<span>Defense:</span>' : '';''')

# 7. The viewer, and showPage using it.
VIEWER = r'''// Viewer for the BLOB/SLOB, Press, Press Break and Transition pages: the coach's drawings,
// step by step. Half court = basket at the top (500 x 470); full court = baskets at y 15 and 925.
const fullView = (() => {
  const NS = 'http://www.w3.org/2000/svg', svg = $('f-court'), AR = 'farrow';
  const mk = (tag, attrs, parent) => {
    const n = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v));
    (parent || svg).appendChild(n);
    return n;
  };
  const TOP = 45; // room above the top baseline for an inbounder standing out of bounds
  let H = 470, lineG = null, off = {}, def = {}, ball = null, defNow = {};
  const len = (pts) => { let s = 0; for (let i = 1; i < pts.length; i += 1) s += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y); return s; };
  function along(pts, t) {
    let left = len(pts) * Math.max(0, Math.min(1, t));
    for (let i = 1; i < pts.length; i += 1) {
      const a = pts[i - 1], b = pts[i], L = Math.hypot(b.x - a.x, b.y - a.y);
      if (left <= L || i === pts.length - 1) { const k = L ? Math.min(1, left / L) : 1; return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k }; }
      left -= L;
    }
    return pts[pts.length - 1];
  }
  function trimEnd(pts, r) {
    const out = pts.slice(), b = out[out.length - 1], a = out[out.length - 2], L = Math.hypot(b.x - a.x, b.y - a.y);
    if (L > r + 2) out[out.length - 1] = { x: b.x - (b.x - a.x) / L * r, y: b.y - (b.y - a.y) / L * r };
    return out;
  }
  const dOf = (pts) => 'M ' + pts.map((p) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' L ');
  function wavy(pts) {
    const total = len(pts), out = [pts[0]], n = Math.max(2, Math.floor((total - 14) / 9));
    for (let i = 1; i < n; i += 1) {
      const t = i / n, p = along(pts, t), q = along(pts, Math.min(1, t + 0.01));
      const L = Math.hypot(q.x - p.x, q.y - p.y) || 1, s = i % 2 ? 5 : -5;
      out.push({ x: p.x - (q.y - p.y) / L * s, y: p.y + (q.x - p.x) / L * s });
    }
    out.push(pts[pts.length - 1]);
    return out;
  }
  function courtEnd(g, flip) {
    const Y = (y) => (flip ? H - y : y);
    mk('rect', { x: 190, y: Math.min(Y(2), Y(160)), width: 120, height: 158 }, g);
    mk('path', { d: `M 190 ${Y(160)} A 60 60 0 0 ${flip ? 1 : 0} 310 ${Y(160)}` }, g);
    mk('path', { d: `M 40 ${Y(2)} L 40 ${Y(80.6)} A 220 220 0 0 ${flip ? 1 : 0} 460 ${Y(80.6)} L 460 ${Y(2)}`, stroke: '#111827', 'stroke-width': 3 }, g);
    mk('line', { x1: 220, y1: Y(6), x2: 280, y2: Y(6), stroke: '#111827', 'stroke-width': 3 }, g);
    mk('circle', { cx: 250, cy: Y(15), r: 8, stroke: '#ea580c', 'stroke-width': 3 }, g);
  }
  function drawCourt(full) {
    svg.innerHTML = '';
    H = full ? 940 : 470;
    svg.setAttribute('viewBox', `0 ${-TOP} 500 ${H + TOP}`);
    svg.setAttribute('aria-label', full ? 'Full court showing the play' : 'Half court showing the play');
    const m = mk('marker', { id: AR, viewBox: '0 0 10 10', refX: 8, refY: 5, markerWidth: 5, markerHeight: 5, orient: 'auto' }, mk('defs', {}));
    mk('path', { d: 'M0,0 L10,5 L0,10 z', fill: '#111827' }, m);
    const g = mk('g', { stroke: '#6b7280', 'stroke-width': 2, fill: 'none' });
    mk('rect', { x: 2, y: 2, width: 496, height: H - 4 }, g);
    courtEnd(g, false);
    if (full) {
      mk('line', { x1: 2, y1: 470, x2: 498, y2: 470 }, g);
      mk('circle', { cx: 250, cy: 470, r: 60 }, g);
      courtEnd(g, true);
    }
    lineG = mk('g', { 'pointer-events': 'none' });
    off = {}; def = {}; ball = null;
  }
  function player(id, p) {
    const g = mk('g', { transform: `translate(${p.x},${p.y})` });
    if (id[0] === 'o') {
      mk('circle', { r: 20, fill: 'var(--off)' }, g);
      mk('text', { 'text-anchor': 'middle', y: 7, 'font-size': 20, 'font-weight': 700, fill: '#fff' }, g).textContent = id.slice(1);
    } else {
      mk('circle', { r: 17, fill: '#fff', stroke: 'var(--def)', 'stroke-width': 3 }, g);
      mk('text', { 'text-anchor': 'middle', y: 6, 'font-size': 15, 'font-weight': 700, fill: 'var(--def)' }, g).textContent = 'X' + id.slice(1);
    }
    return g;
  }
  const put = (g, p) => g.setAttribute('transform', `translate(${p.x.toFixed(1)},${p.y.toFixed(1)})`);
  const putBall = (p) => ball && ball.setAttribute('transform', `translate(${(p.x + 15).toFixed(1)},${(p.y - 15).toFixed(1)})`);
  function setPlay(p) {
    drawCourt(PAGES[page].court === 'full');
    $('f-defKey').hidden = !(p && p.steps[0].defense);
    if (!p) return;
    const s = p.steps[0];
    defNow = Object.assign({}, s.defense || {});
    Object.entries(defNow).forEach(([id, q]) => { def[id] = player(id, q); });
    Object.entries(s.offense).forEach(([id, q]) => { off[id] = player(id, q); });
    ball = mk('circle', { r: 9, fill: 'var(--ball)', stroke: '#92400e', 'stroke-width': 2 });
    if (s.offense[s.ball]) putBall(s.offense[s.ball]);
  }
  function lines(prev, cur) {
    lineG.innerHTML = '';
    if (!prev || !cur) return;
    const ink = { stroke: '#111827', 'stroke-width': 2.5, fill: 'none', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
    Object.keys(cur.offense).forEach((o) => {
      const a = prev.offense[o], b = cur.offense[o];
      if (!a || !b) return;
      const path = (cur.paths || {})[o] || {};
      const pts = [a].concat(path.via || [], [b]);
      if (len(pts) < 8) return;
      const type = path.type || (prev.ball === o ? 'dribble' : 'cut');
      if (type === 'screen') {
        const end = trimEnd(pts, 21), e = end[end.length - 1], f = end[end.length - 2];
        const L = Math.hypot(e.x - f.x, e.y - f.y) || 1, nx = -(e.y - f.y) / L * 12, ny = (e.x - f.x) / L * 12;
        mk('path', Object.assign({ d: dOf(end) }, ink), lineG);
        mk('line', Object.assign({ x1: e.x + nx, y1: e.y + ny, x2: e.x - nx, y2: e.y - ny }, ink, { 'stroke-width': 4 }), lineG);
        return;
      }
      const end = trimEnd(pts, 22);
      mk('path', Object.assign({ d: dOf(type === 'dribble' ? wavy(end) : end), 'marker-end': `url(#${AR})` }, ink), lineG);
    });
    if (prev.ball !== cur.ball && cur.offense[prev.ball] && cur.offense[cur.ball]) {
      const a = cur.offense[prev.ball], b = cur.offense[cur.ball];
      mk('path', { d: dOf(trimEnd([a, b], 22)), stroke: '#111827', 'stroke-width': 2.5, fill: 'none', 'stroke-dasharray': '7 6', 'marker-end': `url(#${AR})` }, lineG);
    }
  }
  // Players run their lines; a pass flies in the last 40% of the step, from passer to catcher.
  function move(prev, cur, ms) {
    const routes = {};
    Object.keys(cur.offense).forEach((o) => {
      const a = prev.offense[o] || cur.offense[o], b = cur.offense[o];
      routes[o] = [a].concat(((cur.paths || {})[o] || {}).via || [], [b]);
    });
    const dPrev = Object.assign({}, defNow), dCur = Object.assign({}, defNow, cur.defense || {});
    return new Promise((res) => {
      let done = 0, last = null;
      function frame(now) {
        if (last === null) last = now;
        if (!window.libertyPaused) done += now - last;
        last = now;
        const t = stopAsked ? 1 : Math.min(1, done / ms);
        const at = {};
        Object.entries(routes).forEach(([o, pts]) => { at[o] = along(pts, t); if (off[o]) put(off[o], at[o]); });
        Object.keys(dCur).forEach((d) => {
          const a = dPrev[d] || dCur[d], b = dCur[d];
          if (def[d]) put(def[d], { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t });
        });
        if (prev.ball !== cur.ball && at[prev.ball] && at[cur.ball]) {
          const k = Math.max(0, (t - 0.6) / 0.4), a = at[prev.ball], b = at[cur.ball];
          putBall({ x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k });
        } else if (at[cur.ball]) putBall(at[cur.ball]);
        if (t < 1) requestAnimationFrame(frame);
        else { defNow = dCur; lineG.innerHTML = ''; res(); }
      }
      requestAnimationFrame(frame);
    });
  }
  function fit() {
    $('f-court').setAttribute('viewBox', `0 ${-TOP} 500 ${H + TOP}`);
    document.querySelector('main').style.setProperty('--ch', H + TOP);
  }
  return { setPlay, lines, move, fit, show: () => { setPlay(current()); $('fullSec').querySelector('svg').after($('courtCtl')); } };
})();
async function runView(p) {
  running = true; stopAsked = false; lock(true); $('playGo').innerHTML = '&#9632; Stop'; $('playPause').disabled = false;
  fullView.setPlay(p); note(`${p.name}: starting spots.`);
  await wait(700 * speed());
  for (let i = 1; i < p.steps.length && !stopAsked; i += 1) {
    note(`${p.name}: step ${i} of ${p.steps.length - 1}: read the lines.`);
    fullView.lines(p.steps[i - 1], p.steps[i]);
    await wait(1000 * speed());
    if (stopAsked) break;
    note(`${p.name}: step ${i} of ${p.steps.length - 1}.`);
    await fullView.move(p.steps[i - 1], p.steps[i], 1900 * speed());
    await wait(350 * speed());
  }
  note(stopAsked ? `${p.name}: stopped.` : `${p.name}: done. Press Play to run it again.`);
  running = false; lock(false); $('playGo').innerHTML = '&#9654; Play'; setPaused(false); $('playPause').disabled = true;
}
function showPage(p) {'''
edit('''function showPage(p) {''', VIEWER)
edit('''  $('defToggle').hidden = p !== 'offense';
  applyDefense();
  drawKinds(); drawPlays(); showKind(kindOf[p]); note(''); fitCourt();''',
     '''  $('defToggle').hidden = p !== 'offense';
  applyDefense();
  const view = !!PAGES[p].court;
  document.body.classList.toggle('page-view', view);
  $('fullSec').hidden = !view;
  drawKinds(); drawPlays();
  if (view) { $('manSec').hidden = $('zoneSec').hidden = true; fullView.show(); } else showKind(kindOf[p]);
  note(''); fitCourt();''')

# 8. Court height, play pick and Play on viewer pages.
edit('''function fitCourt() {
''', '''function fitCourt() {
  if (PAGES[page].court) { fullView.fit(); return; }
''')
edit('''  $('playDel').disabled = $('playEdit').disabled = !p;
  sec(shownKind).showLines(null);''', '''  $('playDel').disabled = $('playEdit').disabled = !p;
  if (PAGES[page].court) { fullView.setPlay(p); note(p ? `${p.name}: press Play.` : ''); return; }
  sec(shownKind).showLines(null);''')
edit('''  if (!p) { note('Pick a play first, or press Add play to draw one.'); return; }
''', '''  if (!p) { note('Pick a play first, or press Add play to draw one.'); return; }
  if (PAGES[page].court) { await runView(p); return; }
''')


def jsnum(v):
    """Numbers as JavaScript's JSON.stringify writes them (100.0 -> 100), so the page rebuilds to itself."""
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, list):
        return [jsnum(x) for x in v]
    if isinstance(v, dict):
        return {k: jsnum(x) for k, x in v.items()}
    return v


def apply(text, where):
    for old, new in EDITS:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{where}: expected 1 match, found {n}: {old[:70]!r}")
        text = text.replace(old, new)
    return text


def main():
    src, plays_file, out = sys.argv[1:4]
    s = open(src, encoding="utf-8", newline="").read()
    i, j = split(s)
    tpl = json.loads(s[i:j])
    head, body_end = s[:i], s[j:]
    live_code = head   # live page code is everything before the template literal
    live_code = apply(live_code, "live")
    tpl = apply(tpl, "template")
    # Plays: live PLAYS_SAVED gets the new pages.
    a = "const PLAYS_SAVED = "
    k = live_code.index(a) + len(a); e = live_code.index(";\n", k)
    saved = json.loads(live_code[k:e])
    extra = json.load(open(plays_file))
    for key in ("blob", "press", "pressbreak", "transition"):
        saved[key] = jsnum(extra[key])
    live_code = live_code[:k] + enc(saved) + live_code[e:]
    s2 = live_code + enc(tpl) + body_end
    open(out, "w", encoding="utf-8", newline="").write(s2)
    print("written", out, len(s), "->", len(s2))


if __name__ == "__main__":
    main()
