"""Build Liberty_Shot_Outputs/review_queue/page/: the coach review page for all tagged games.
Both models say make -> auto make (shown, coach clicks Miss if wrong).
Models disagree -> needs the coach's call. Both say miss -> auto miss (not shown).
With --clip-moment-fix: a shot whose program moment belongs to the next shot is
shown (even if both models said miss), orange, clip at tag time, with a note.
With --wide-combined: every card also shows a whole-frame wide view; conflict
chains become one orange card (implies conflict grouping). Default off = page_v3.
Usage: <repo venv python> -I make_review_queue_page.py [--clip-moment-fix]
       [--wide-combined] [--out-dir DIR]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2

from clip_moment_fix import (
    group_clip_extent,
    group_flagged_chains,
    resolve_clip_centres,
    review_storage_key,
    seconds_to_frames,
    too_short_conflict_note,
)

OUT_ROOT = Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs")
OUT_DEFAULT = OUT_ROOT / "review_queue/page"
REPO = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
VIDEOS = {"adrian": REPO / "uploads/nfhs_gam0a66d85e12.mp4",
          "notus_a1": REPO / "uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4"}
GAME = {"adrian": "Liberty at Adrian", "notus_a1": "Notus at Liberty"}
TRACKS = [Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks.json"),
          Path(r"C:\Users\scott\AppData\Local\Temp\v6_tracks_notus_q1.json"),
          OUT_ROOT / "q4_guard/v6_tracks_q4.json"]
TRACK_FILM = ["adrian", "notus_a1", "adrian"]
RESULTS = [(OUT_ROOT / "ball_arc/d1_results.json", OUT_ROOT / "d2_train/test2/d2_results.json"),
           (OUT_ROOT / "review_queue/q4/v6/results.json", OUT_ROOT / "review_queue/q4/d2v1/results.json")]
BEFORE, AFTER = 8, 14  # flag-off / page_v3 path
# Scott 2026-11-03
CLIP_BEFORE_S = 2.0
CLIP_AFTER_S = 1.5
HALF_W, ABOVE, BELOW = 170, 150, 190
CONFLICT_NOTE = "program's moment belonged to the next shot - clip shown at the tag time"
COMBINED_HEADER = "{n} shots in this clip (e.g. miss and tip-in)"


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clip-moment-fix", action="store_true", default=False,
                   help="Recentres clips on tag time when two shots share a moment")
    p.add_argument("--wide-combined", action="store_true", default=False,
                   help="Wide view on every card; combine conflict chains (implies grouping)")
    p.add_argument("--out-dir", type=Path, default=OUT_DEFAULT,
                   help=f"Output directory (default: {OUT_DEFAULT})")
    return p.parse_args(argv)


def _clock(t_ms):
    m, sec = divmod(t_ms / 1000.0, 60)
    return f"{int(m)}:{sec:04.1f}"


def _write_clip_jpegs(out_dir, sid, video, start, n_frames, hoop, wide):
    """Write close-up (and optional wide) JPEGs; return (close_names, wide_names)."""
    hx, hy = float(hoop[0]), float(hoop[1])
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    names, wide_names = [], []
    for k in range(n_frames):
        ok, fr = cap.read()
        if not ok:
            break
        H, W = fr.shape[:2]
        crop = fr[int(max(0, hy - ABOVE)):int(min(H, hy + BELOW)),
                  int(max(0, hx - HALF_W)):int(min(W, hx + HALF_W))]
        crop = cv2.resize(crop, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        n = f"{sid}_{k:02d}.jpg"
        cv2.imwrite(str(out_dir / n), crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        names.append(n)
        if wide:
            wn = f"{sid}_w_{k:02d}.jpg"
            cv2.imwrite(str(out_dir / wn), fr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            wide_names.append(wn)
    cap.release()
    return names, wide_names


def _page_v3_html():
    return r"""<!doctype html><html><head><meta charset="utf-8"><title>Coach Shot Review</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#f4f4f4;color:#111}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:10px 14px;z-index:5}
h1{font-size:18px;margin:0 0 4px}
h2.sec{font-size:17px;margin:18px 14px 0}
.help{font-size:14px;color:#333;max-width:950px}
.wrap{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;padding:14px}
.card{background:#fff;border:1px solid #ccc;border-radius:6px;padding:10px}
.card.review{border:2px solid #e65100}
.card h3{font-size:15px;margin:0 0 6px}
.view{position:relative;background:#000}
.view img{width:100%;display:block}
.tag{position:absolute;left:6px;top:6px;background:rgba(0,0,0,.65);color:#fff;font-size:12px;padding:2px 6px;border-radius:3px}
.ctl{display:flex;gap:6px;align-items:center;margin:6px 0;flex-wrap:wrap}
button{font-size:14px;padding:6px 10px;cursor:pointer}
.pick button.on{background:#1b5e20;color:#fff}
.pick button.on.miss{background:#b71c1c}
.ans{margin-top:6px;font-size:14px;display:none}
.ans.wrong{color:#b71c1c;font-weight:bold}
body.reveal .ans{display:block}
textarea{width:100%;box-sizing:border-box;font-size:14px;margin-top:4px}
input[type=range]{flex:1}
table{border-collapse:collapse;font-size:14px;margin-top:6px}
td,th{border:1px solid #ccc;padding:3px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}
.note{font-size:13px;color:#e65100;margin:4px 0 0}
</style></head><body>
<header><h1>Shot review: all tagged games</h1>
<div class="help"><b>Orange cards: the program isn't sure.</b> Press <b>Make</b> or <b>Miss</b>.
<b>Grey cards: the program called a make.</b> They start as Make. Press <b>Miss</b> only if it's wrong.
Every other shot the program called a miss on its own, so you won't see those here.
Each clip loops around the rim. Use the slider or the step buttons to go frame by frame.
When you're done, press <b>Export calls</b> and give me the file. For this test, <b>Reveal answers</b> compares your calls with the tags.</div>
<div class="ctl"><b id="count"></b><button id="rev">Reveal answers</button><button id="exp">Export calls</button></div>
<div id="box"></div></header>
<div id="main"></div>
<script>
const ROWS = __ROWS__;
const TOTAL = __TOTAL__;
const KEY = '__STORAGE_KEY__';
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { st = {}; }
ROWS.forEach(r => { st[r.id] = st[r.id] || {call: r.group === 'auto' ? 'make' : '', note: ''}; });
function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} summary(); }
function summary() {
  const rev = ROWS.filter(r => r.group === 'review');
  const done = rev.filter(r => st[r.id].call).length;
  document.getElementById('count').textContent = done + ' of ' + rev.length + ' orange shots called';
  const reveal = document.body.classList.contains('reveal');
  let h = '<table><tr><th>Game</th><th>Shots</th><th>Auto makes</th><th>Need your call</th><th>Makes after your calls</th>' + (reveal ? '<th>Real makes found</th><th>Misses counted as makes</th>' : '') + '</tr>';
  Object.keys(TOTAL).forEach(f => {
    const rs = ROWS.filter(r => r.film === f), mk = rs.filter(r => st[r.id].call === 'make');
    h += '<tr><td>' + (rs[0] ? rs[0].game : f) + '</td><td>' + TOTAL[f].shots + '</td><td>' + rs.filter(r => r.group === 'auto').length + '</td><td>' + rs.filter(r => r.group === 'review').length + '</td><td>' + mk.length + '</td>' +
      (reveal ? '<td>' + mk.filter(r => r.truth === 'make').length + ' of ' + TOTAL[f].makes + '</td><td>' + mk.filter(r => r.truth === 'miss').length + '</td>' : '') + '</tr>';
  });
  document.getElementById('box').innerHTML = h + '</table>';
  ROWS.forEach(r => { const a = document.getElementById('ans_' + r.id); if (a) { a.textContent = 'Tag says: ' + r.truth.toUpperCase(); a.classList.toggle('wrong', !!st[r.id].call && st[r.id].call !== r.truth); } });
}
const main = document.getElementById('main');
function section(title, list) {
  if (!list.length) return;
  const h = document.createElement('h2'); h.className = 'sec'; h.textContent = title; main.appendChild(h);
  const wrap = document.createElement('div'); wrap.className = 'wrap'; main.appendChild(wrap);
  list.forEach(r => {
    const c = document.createElement('div'); c.className = 'card ' + r.group;
    c.innerHTML = '<h3>' + r.game + ', ' + r.clock + (r.group === 'review' ? ' (needs your call)' : ' (auto make)') + '</h3><div class="view"><img><span class="tag"></span></div>' +
      '<div class="ctl"><button class="pp">Pause</button><button class="bk">&lt;</button><button class="fw">&gt;</button><input type="range" min="0" max="' + (r.frames.length - 1) + '"></div>' +
      '<div class="ctl pick"><button class="mk">Make</button><button class="ms miss">Miss</button></div>' +
      (r.note ? '<p class="note">' + r.note + '</p>' : '') +
      '<textarea rows="1" placeholder="Note (optional)"></textarea><div class="ans" id="ans_' + r.id + '"></div>';
    const img = c.querySelector('img'), tag = c.querySelector('.tag'), rng = c.querySelector('input'), pp = c.querySelector('.pp');
    let i = 0, play = true;
    function show() { img.src = r.frames[i]; rng.value = i; const d = i - r.mark; tag.textContent = 'frame ' + (d >= 0 ? '+' : '') + d + (d === 0 ? '  (program\'s moment)' : ''); }
    function stop() { play = false; pp.textContent = 'Play'; }
    setInterval(() => { if (play) { i = (i + 1) % r.frames.length; show(); } }, 220);
    pp.onclick = () => { play = !play; pp.textContent = play ? 'Pause' : 'Play'; };
    c.querySelector('.bk').onclick = () => { stop(); i = (i - 1 + r.frames.length) % r.frames.length; show(); };
    c.querySelector('.fw').onclick = () => { stop(); i = (i + 1) % r.frames.length; show(); };
    rng.oninput = () => { stop(); i = +rng.value; show(); };
    const mk = c.querySelector('.mk'), ms = c.querySelector('.ms'), ta = c.querySelector('textarea');
    function paint() { mk.classList.toggle('on', st[r.id].call === 'make'); ms.classList.toggle('on', st[r.id].call === 'miss'); }
    mk.onclick = () => { st[r.id].call = 'make'; paint(); save(); };
    ms.onclick = () => { st[r.id].call = 'miss'; paint(); save(); };
    ta.value = st[r.id].note; ta.oninput = () => { st[r.id].note = ta.value; save(); };
    paint(); show(); wrap.appendChild(c);
  });
}
section('Needs your call', ROWS.filter(r => r.group === 'review'));
section('Program called a make: press Miss if wrong', ROWS.filter(r => r.group === 'auto'));
summary();
document.getElementById('rev').onclick = () => { document.body.classList.add('reveal'); summary(); };
document.getElementById('exp').onclick = () => {
  const out = ROWS.map(r => ({shot: r.id, game: r.game, clock: r.clock, program: r.group, coach_call: st[r.id].call, note: st[r.id].note}));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: 'application/json'}));
  a.download = 'coach_calls.json'; a.click();
};
</script></body></html>"""


def _page_wide_html():
    return r"""<!doctype html><html><head><meta charset="utf-8"><title>Coach Shot Review</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#f4f4f4;color:#111}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid #ccc;padding:10px 14px;z-index:5}
h1{font-size:18px;margin:0 0 4px}
h2.sec{font-size:17px;margin:18px 14px 0}
.help{font-size:14px;color:#333;max-width:950px}
.wrap{display:grid;grid-template-columns:1fr;gap:14px;padding:14px}
.card{background:#fff;border:1px solid #ccc;border-radius:6px;padding:10px}
.card.review{border:2px solid #e65100}
.card h3{font-size:15px;margin:0 0 6px}
.card .hdr{font-size:13px;color:#e65100;margin:0 0 6px}
.views{display:grid;grid-template-columns:1fr;gap:6px}
.view{position:relative;background:#000}
.view img.wide{width:100%;display:block;cursor:pointer}
.view.close-view{width:fit-content;max-width:100%}
.view img.close{width:auto;max-width:100%;display:block}
.tag{position:absolute;left:6px;top:6px;background:rgba(0,0,0,.65);color:#fff;font-size:12px;padding:2px 6px;border-radius:3px}
.ctl{display:flex;gap:6px;align-items:center;margin:6px 0;flex-wrap:wrap}
button{font-size:14px;padding:6px 10px;cursor:pointer}
.pick button.on{background:#1b5e20;color:#fff}
.pick button.on.miss{background:#b71c1c}
.pick button.on.dup{background:#e65100;color:#fff}
.shot-row{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:4px 0;font-size:14px}
.ans{margin-top:6px;font-size:14px;display:none}
.ans.wrong{color:#b71c1c;font-weight:bold}
body.reveal .ans{display:block}
textarea{width:100%;box-sizing:border-box;font-size:14px;margin-top:4px}
input[type=range]{flex:1}
table{border-collapse:collapse;font-size:14px;margin-top:6px}
td,th{border:1px solid #ccc;padding:3px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}
.note{font-size:13px;color:#e65100;margin:4px 0 0}
#fs{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:100;align-items:center;justify-content:center;cursor:pointer}
#fs.open{display:flex}
#fs img{max-width:100%;max-height:100%;object-fit:contain}
</style></head><body>
<header><h1>Shot review: all tagged games</h1>
<div class="help"><b>Orange cards: the program isn't sure.</b> Press <b>Make</b> or <b>Miss</b>.
<b>Grey cards: the program called a make.</b> They start as Make. Press <b>Miss</b> only if it's wrong.
Every other shot the program called a miss on its own, so you won't see those here.
Each card shows the whole frame above a rim close-up; one slider drives both. Click the wide view for full screen (Esc or click to close).
A combined orange card holds shots that share one clip — use <b>Same shot, tagged twice</b> when the earlier tags are the same attempt.
When you're done, press <b>Export calls</b> and give me the file. For this test, <b>Reveal answers</b> compares your calls with the tags.</div>
<div class="ctl"><b id="count"></b><button id="rev">Reveal answers</button><button id="exp">Export calls</button></div>
<div id="box"></div></header>
<div id="main"></div>
<div id="fs"><img alt=""></div>
<script>
const ROWS = __ROWS__;
const TOTAL = __TOTAL__;
const KEY = '__STORAGE_KEY__';
let st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { st = {}; }
const fs = document.getElementById('fs');
const fsImg = fs.querySelector('img');
function closeFs() { fs.classList.remove('open'); fs._owner = null; }
fs.onclick = () => closeFs();
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeFs(); });
function allShots() {
  const out = [];
  ROWS.forEach(r => {
    if (r.combined) r.shots.forEach(s => out.push(Object.assign({film: r.film, game: r.game}, s)));
    else out.push(r);
  });
  return out;
}
allShots().forEach(s => { st[s.id] = st[s.id] || {call: s.group === 'auto' ? 'make' : '', note: ''}; });
function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} summary(); }
function summary() {
  const shots = allShots();
  const rev = shots.filter(s => s.card_group === 'review');
  const done = rev.filter(s => st[s.id].call).length;
  document.getElementById('count').textContent = done + ' of ' + rev.length + ' orange shots called';
  const reveal = document.body.classList.contains('reveal');
  let h = '<table><tr><th>Game</th><th>Shots</th><th>Auto makes</th><th>Need your call</th><th>Makes after your calls</th>' + (reveal ? '<th>Real makes found</th><th>Misses counted as makes</th>' : '') + '</tr>';
  Object.keys(TOTAL).forEach(f => {
    const rs = shots.filter(s => s.film === f);
    const mk = rs.filter(s => st[s.id].call === 'make');
    const autoN = rs.filter(s => s.card_group === 'auto').length;
    const needN = rs.filter(s => s.card_group === 'review').length;
    h += '<tr><td>' + (rs[0] ? rs[0].game : f) + '</td><td>' + TOTAL[f].shots + '</td><td>' + autoN + '</td><td>' + needN + '</td><td>' + mk.length + '</td>' +
      (reveal ? '<td>' + mk.filter(s => s.truth === 'make').length + ' of ' + TOTAL[f].makes + '</td><td>' + mk.filter(s => s.truth === 'miss').length + '</td>' : '') + '</tr>';
  });
  document.getElementById('box').innerHTML = h + '</table>';
  shots.forEach(s => {
    const a = document.getElementById('ans_' + s.id);
    if (a) {
      a.textContent = 'Tag says: ' + s.truth.toUpperCase();
      const call = st[s.id].call;
      a.classList.toggle('wrong', !!call && call !== 'duplicate' && call !== s.truth);
    }
  });
}
const main = document.getElementById('main');
function bindClip(c, r) {
  const imgC = c.querySelector('img.close'), imgW = c.querySelector('img.wide');
  const tag = c.querySelector('.tag'), rng = c.querySelector('input'), pp = c.querySelector('.pp');
  let i = 0, play = true;
  function show() {
    imgC.src = r.frames[i];
    if (imgW && r.wide_frames) imgW.src = r.wide_frames[i];
    if (fs.classList.contains('open') && fs._owner === c && r.wide_frames) fsImg.src = r.wide_frames[i];
    rng.value = i;
    const d = i - r.mark;
    tag.textContent = 'frame ' + (d >= 0 ? '+' : '') + d + (d === 0 ? '  (program\'s moment)' : '');
  }
  function stop() { play = false; pp.textContent = 'Play'; }
  setInterval(() => { if (play) { i = (i + 1) % r.frames.length; show(); } }, 220);
  pp.onclick = () => { play = !play; pp.textContent = play ? 'Pause' : 'Play'; };
  c.querySelector('.bk').onclick = () => { stop(); i = (i - 1 + r.frames.length) % r.frames.length; show(); };
  c.querySelector('.fw').onclick = () => { stop(); i = (i + 1) % r.frames.length; show(); };
  rng.oninput = () => { stop(); i = +rng.value; show(); };
  if (imgW) {
    imgW.onclick = e => {
      e.stopPropagation();
      fs._owner = c;
      fsImg.src = r.wide_frames[i];
      fs.classList.add('open');
    };
  }
  show();
}
function section(title, list) {
  if (!list.length) return;
  const h = document.createElement('h2'); h.className = 'sec'; h.textContent = title; main.appendChild(h);
  const wrap = document.createElement('div'); wrap.className = 'wrap'; main.appendChild(wrap);
  list.forEach(r => {
    const c = document.createElement('div'); c.className = 'card ' + r.group;
    const views = '<div class="views"><div class="view"><img class="wide"></div><div class="view close-view"><img class="close"><span class="tag"></span></div></div>';
    const ctl = '<div class="ctl"><button class="pp">Pause</button><button class="bk">&lt;</button><button class="fw">&gt;</button><input type="range" min="0" max="' + (r.frames.length - 1) + '"></div>';
    if (r.combined) {
      let rows = '';
      r.shots.forEach(s => {
        rows += '<div class="shot-row" data-sid="' + s.id + '"><span>' + s.label + ' - ' + s.clock + ':</span>' +
          '<span class="pick"><button class="mk">Make</button><button class="ms miss">Miss</button></span>' +
          '<div class="ans" id="ans_' + s.id + '"></div></div>';
      });
      c.innerHTML = '<h3>' + r.game + ' (needs your call)</h3><p class="hdr">' + r.header + '</p>' + views + ctl + rows +
        '<div class="ctl"><button class="dup">Same shot, tagged twice</button></div>' +
        '<textarea rows="1" placeholder="Note (optional)"></textarea>';
      bindClip(c, r);
      const ta = c.querySelector('textarea');
      const noteId = r.shots[r.shots.length - 1].id;
      ta.value = st[noteId].note; ta.oninput = () => { st[noteId].note = ta.value; save(); };
      function paint() {
        r.shots.forEach(s => {
          const row = c.querySelector('.shot-row[data-sid="' + s.id + '"]');
          const mk = row.querySelector('.mk'), ms = row.querySelector('.ms');
          const call = st[s.id].call;
          mk.classList.toggle('on', call === 'make');
          ms.classList.toggle('on', call === 'miss');
        });
        c.querySelector('.dup').classList.toggle('on',
          r.shots.slice(0, -1).every(s => st[s.id].call === 'duplicate'));
      }
      r.shots.forEach(s => {
        const row = c.querySelector('.shot-row[data-sid="' + s.id + '"]');
        row.querySelector('.mk').onclick = () => { st[s.id].call = 'make'; paint(); save(); };
        row.querySelector('.ms').onclick = () => { st[s.id].call = 'miss'; paint(); save(); };
      });
      c.querySelector('.dup').onclick = () => {
        r.shots.slice(0, -1).forEach(s => { st[s.id].call = 'duplicate'; });
        paint(); save();
      };
      paint();
    } else {
      c.innerHTML = '<h3>' + r.game + ', ' + r.clock + (r.group === 'review' ? ' (needs your call)' : ' (auto make)') + '</h3>' + views + ctl +
        '<div class="ctl pick"><button class="mk">Make</button><button class="ms miss">Miss</button></div>' +
        (r.note ? '<p class="note">' + r.note + '</p>' : '') +
        '<textarea rows="1" placeholder="Note (optional)"></textarea><div class="ans" id="ans_' + r.id + '"></div>';
      bindClip(c, r);
      const mk = c.querySelector('.mk'), ms = c.querySelector('.ms'), ta = c.querySelector('textarea');
      function paint() { mk.classList.toggle('on', st[r.id].call === 'make'); ms.classList.toggle('on', st[r.id].call === 'miss'); }
      mk.onclick = () => { st[r.id].call = 'make'; paint(); save(); };
      ms.onclick = () => { st[r.id].call = 'miss'; paint(); save(); };
      ta.value = st[r.id].note; ta.oninput = () => { st[r.id].note = ta.value; save(); };
      paint();
    }
    wrap.appendChild(c);
  });
}
section('Needs your call', ROWS.filter(r => r.group === 'review'));
section('Program called a make: press Miss if wrong', ROWS.filter(r => r.group === 'auto'));
summary();
document.getElementById('rev').onclick = () => { document.body.classList.add('reveal'); summary(); };
document.getElementById('exp').onclick = () => {
  const out = allShots().map(s => ({
    shot: s.id, game: s.game, clock: s.clock, program: s.group,
    coach_call: st[s.id].call, note: st[s.id].note
  }));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], {type: 'application/json'}));
  a.download = 'coach_calls.json'; a.click();
};
</script></body></html>"""


def main(argv=None):
    args = parse_args(argv)
    OUT = args.out_dir
    if OUT.exists():
        sys.exit(f"refused: {OUT} exists")

    hoops = {}
    for path, film in zip(TRACKS, TRACK_FILM):
        for r in json.loads(path.read_text(encoding="utf-8")):
            hoops[(film, int(r["t"]))] = r["hoop"]

    # All tagged shots from v6 results (read-only), keyed for pair resolve.
    all_tagged = []
    pair_rows = []  # (film, t, v6_shot, d2_shot)
    n_total = {"adrian": 0, "notus_a1": 0}
    for v6_path, d2_path in RESULTS:
        a = {(s["film"], int(s["t"])): s for s in json.loads(v6_path.read_text(encoding="utf-8"))["shots"]}
        b = {(s["film"], int(s["t"])): s for s in json.loads(d2_path.read_text(encoding="utf-8"))["shots"]}
        assert a.keys() == b.keys()
        for k, s in a.items():
            n_total[k[0]] += 1
            fps = float(s["fps"]) if "fps" in s else float(b[k]["fps"]) if "fps" in b[k] else 25.0
            all_tagged.append({"film": k[0], "t": k[1], "anchor_frame": int(s["anchor_frame"]), "fps": fps})
            pair_rows.append((k[0], k[1], s, b[k]))

    by_key = {(film, t): (s, d2) for film, t, s, d2 in pair_rows}

    clip_centres = {}
    flags = {}
    clip_extents = {}
    if args.clip_moment_fix and not args.wide_combined:
        by_film = defaultdict(list)
        for s in all_tagged:
            by_film[s["film"]].append(s)
        for film, film_shots in by_film.items():
            centres, film_flags, extents = resolve_clip_centres(film_shots)
            for t, c in centres.items():
                clip_centres[(film, t)] = c
            for t, f in film_flags.items():
                flags[(film, t)] = f
            for t, ext in extents.items():
                clip_extents[(film, t)] = ext

    OUT.mkdir(parents=True)
    rows = []
    shots_meta = []  # for end-of-run counts (one entry per card)
    combined_print = []
    clip_lengths = []  # per-card frame counts (--wide-combined only)
    n_shots_on_page = 0

    if args.wide_combined:
        by_film = defaultdict(list)
        for s in all_tagged:
            by_film[s["film"]].append(s)
        film_order = sorted(by_film.keys(), key=lambda f: f != "adrian")
        card_i = 0
        for film in film_order:
            for group in group_flagged_chains(by_film[film]):
                members = []
                for g in sorted(group, key=lambda x: int(x["t"])):
                    s, d2 = by_key[(film, int(g["t"]))]
                    p1, p2 = bool(s["new_pred"]), bool(d2["new_pred"])
                    prog = "auto" if (p1 and p2) else ("review" if (p1 or p2) else "miss")
                    members.append({
                        "t": int(g["t"]), "anchor": int(g["anchor_frame"]),
                        "fps": float(g["fps"]), "p1": p1, "p2": p2,
                        "prog": prog, "truth": "make" if s["gt_make"] else "miss",
                        "hoop": hoops[(film, int(g["t"]))],
                    })
                # Show multi-shot conflict groups always; singles only if shown today.
                if len(group) == 1 and not (members[0]["p1"] or members[0]["p2"]):
                    continue

                fps = members[0]["fps"]
                before = seconds_to_frames(CLIP_BEFORE_S, fps)
                after = seconds_to_frames(CLIP_AFTER_S, fps)

                if len(group) >= 2:
                    first, last = group_clip_extent(
                        [{"t": m["t"], "anchor_frame": m["anchor"]} for m in members],
                        fps, before, after,
                    )
                    n_frames = last - first + 1
                    sid = f"{film}_" + "_".join(str(m["t"]) for m in members)
                    names, wide_names = _write_clip_jpegs(
                        OUT, sid, VIDEOS[film], first, n_frames, members[0]["hoop"], wide=True)
                    shot_rows = []
                    for idx, m in enumerate(members):
                        shot_rows.append({
                            "id": f"{film}_{m['t']}",
                            "label": f"Shot {idx + 1}",
                            "clock": _clock(m["t"]),
                            "group": "auto" if m["prog"] == "auto" else "review",
                            "card_group": "review",
                            "truth": m["truth"],
                        })
                    row = {
                        "id": sid, "film": film, "game": GAME[film],
                        "group": "review", "combined": True,
                        "header": COMBINED_HEADER.format(n=len(members)),
                        "frames": names, "wide_frames": wide_names,
                        "mark": before, "shots": shot_rows,
                    }
                    rows.append(row)
                    shots_meta.append({"group": "review", "combined": True})
                    clip_lengths.append(n_frames)
                    n_shots_on_page += len(members)
                    combined_print.append(
                        (film, [m["t"] for m in members], first, last, n_frames))
                    card_i += 1
                    print(card_i, sid, "combined", len(names), "frames")
                else:
                    m = members[0]
                    group_name = "auto" if m["prog"] == "auto" else "review"
                    centre = m["anchor"]
                    start = centre - before
                    n_frames = before + after + 1
                    sid = f"{film}_{m['t']}"
                    names, wide_names = _write_clip_jpegs(
                        OUT, sid, VIDEOS[film], start, n_frames, m["hoop"], wide=True)
                    row = {
                        "id": sid, "film": film, "game": GAME[film],
                        "clock": _clock(m["t"]), "group": group_name,
                        "combined": False, "card_group": group_name,
                        "frames": names, "wide_frames": wide_names,
                        "mark": before, "truth": m["truth"],
                    }
                    rows.append(row)
                    shots_meta.append({"group": group_name, "combined": False})
                    clip_lengths.append(n_frames)
                    n_shots_on_page += 1
                    card_i += 1
                    print(card_i, sid, group_name, len(names), "frames")
        rows.sort(key=lambda r: (r["film"] != "adrian",
                                 r["shots"][0]["id"] if r.get("combined") else r["id"]))
    else:
        # page_v3 path (with or without --clip-moment-fix); unchanged behaviour
        shots = []
        for film, t, s, d2 in pair_rows:
            p1, p2 = bool(s["new_pred"]), bool(d2["new_pred"])
            flagged = flags.get((film, t)) == "clip_moment_conflict"
            if not (p1 or p2) and not flagged:
                continue
            assert s["anchor_frame"] == d2["anchor_frame"]
            anchor = int(s["anchor_frame"])
            if flagged:
                group = "review"
                centre = clip_centres[(film, t)]
                ext = clip_extents[(film, t)]
                note = CONFLICT_NOTE
                if ext["clip_end"] <= centre + AFTER:
                    note += too_short_conflict_note(ext["next_gap_s"])
            else:
                group = "auto" if (p1 and p2) else "review"
                centre = anchor
                note = ""
                ext = None
            shot_row = {"film": film, "t": t, "group": group,
                        "anchor": anchor, "centre": centre, "note": note,
                        "hoop": hoops[(film, t)],
                        "truth": "make" if s["gt_make"] else "miss"}
            if ext is not None:
                shot_row["clip_end"] = ext["clip_end"]
            shots.append(shot_row)
        shots.sort(key=lambda s: (s["film"] != "adrian", s["t"]))

        for i, s in enumerate(shots):
            sid = f"{s['film']}_{s['t']}"
            start = s["centre"] - BEFORE
            if "clip_end" in s:
                n_frames = s["clip_end"] - start + 1
            else:
                n_frames = BEFORE + AFTER + 1
            names, _ = _write_clip_jpegs(
                OUT, sid, VIDEOS[s["film"]], start, n_frames, s["hoop"], wide=False)
            row = {"id": sid, "film": s["film"], "game": GAME[s["film"]], "clock": _clock(s["t"]),
                   "group": s["group"], "frames": names, "mark": BEFORE, "truth": s["truth"]}
            if s["note"]:
                row["note"] = s["note"]
            rows.append(row)
            shots_meta.append({"group": s["group"], "combined": False})
            n_shots_on_page += 1
            print(i + 1, len(shots), sid, s["group"], len(names), "frames")

    makes = {}
    for v6_path, _ in RESULTS:
        for s in json.loads(v6_path.read_text(encoding="utf-8"))["shots"]:
            makes[s["film"]] = makes.get(s["film"], 0) + int(bool(s["gt_make"]))
    total = {f: {"shots": n_total[f], "makes": makes.get(f, 0)} for f in ("adrian", "notus_a1")}
    storage_key = review_storage_key(OUT)
    page = _page_wide_html() if args.wide_combined else _page_v3_html()
    (OUT / "review.html").write_text(
        page.replace("__ROWS__", json.dumps(rows))
            .replace("__TOTAL__", json.dumps(total))
            .replace("__STORAGE_KEY__", storage_key),
        encoding="utf-8",
    )
    print("wrote", OUT / "review.html", "shots shown", len(rows), total)

    n_gray = sum(1 for s in shots_meta if s["group"] == "auto")
    n_orange = sum(1 for s in shots_meta if s["group"] == "review")
    if args.wide_combined:
        length_counts = Counter(clip_lengths)
        summary = ", ".join(
            f"{length}={length_counts[length]}" for length in sorted(length_counts))
        print(f"clip lengths summary: {summary}")
        print(f"gray={n_gray} orange={n_orange}")
        print("combined groups (film, times, first, last, length):")
        for film, times, first, last, length in combined_print:
            print(f"  {film} t={times} first={first} last={last} length={length}")
        print(f"shots on page={n_shots_on_page}")
    elif args.clip_moment_fix:
        print("flagged shots (film, t, anchor, clip_centre):")
        n_flagged = 0
        for (film, t), f in sorted(flags.items(), key=lambda x: (x[0][0], x[0][1])):
            if f != "clip_moment_conflict":
                continue
            tagged = next(x for x in all_tagged if x["film"] == film and x["t"] == t)
            print(f"  {film} t={t} anchor={int(tagged['anchor_frame'])} "
                  f"clip_centre={clip_centres[(film, t)]}")
            n_flagged += 1
        print(f"gray={n_gray} orange={n_orange} flagged={n_flagged}")
    else:
        print(f"gray={n_gray} orange={n_orange}")


if __name__ == "__main__":
    main()
