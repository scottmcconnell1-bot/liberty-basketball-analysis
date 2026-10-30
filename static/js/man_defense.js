/* Liberty man shell. Basket is at the top of the diagram, so smaller y is closer to the rim.
   On the ball: high shoulder, gap to the sideline and the baseline, so the top man cannot walk into the key.
   One pass away: on the line between the man and the ball.
   High post: half deny. Ball at the free-throw line or below: front the posts.
   Two passes away: gap, one foot in the lane, still seeing the ball and the man.
   Three passes away: off the inside shoulder, help side in the lane, in front of a lob.
   On a screen: the screener's defender hedges, and the ball defender goes over the top.
   A dragged defender keeps that adjustment relative to the ball.
   Ball-you-man: the offense never gets between his defender and the ball.
   A cut across the lane is met chest-to-chest, in the path and on the ball.
   Scott 2026-10-29: off the ball, every defender builds a triangle with the ball and
   his man (pulled toward the ball, sagged toward the basket, more the farther the
   ball is), and no defender except the one on the ball is beyond the 3-point line.
*/
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.LibertyManDefense = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function sub(a, b) { return { x: a.x - b.x, y: a.y - b.y }; }
  function add(a, b) { return { x: a.x + b.x, y: a.y + b.y }; }
  function mul(a, s) { return { x: a.x * s, y: a.y * s }; }
  function len(a) { return Math.hypot(a.x, a.y); }
  function norm(a) {
    const l = len(a);
    if (l < 0.001) return { x: 0, y: 1 };
    return { x: a.x / l, y: a.y / l };
  }
  function lerp(a, b, t) {
    return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
  }
  function clamp(p, bounds) {
    return {
      x: Math.max(bounds.minX, Math.min(bounds.maxX, p.x)),
      y: Math.max(bounds.minY, Math.min(bounds.maxY, p.y)),
    };
  }

  function lineDrop(rim) { return (rim && rim.ftDepth) || 110; }

  // The editor's 3-point line: arc of 220 around the rim, corners at x = 40 / 460.
  const THREE_R = 220;
  const THREE_CORNER = 210;
  const INSIDE = 16; // a defender's whole body stays inside the line


  // Court is 500 units for 50 ft: 10 units = 1 ft.
  const FT = 10;
  // Fitted to Scott's own spots, 2026-10-29: 11 Defense Teacher lessons (3 out 2 in,
  // high/low post) + 19 dragged spots (4 out 1 in; 3 out 2 in both low), 74 defenders,
  // mean 2.5 ft off.
  // Share of the way from the man toward the ball, then feet off the passing lane
  // toward the basket.
  const SPOT = {
    1: { ball: 0.4, offFt: 4.5 },
    2: { ball: 0.45, offFt: 4.5 },
    3: { ball: 0.45, offFt: 7.5 },
    inside: { ball: 0.65, offFt: 3 }, // ball in the post or the lane: everyone sinks
    post: { ball: 0.2, offFt: 2 }, // man on the block or the elbow: stay tight
  };

  // Scott's dragged spots: the man on the ball is about 4 ft off him, always toward
  // the middle of the free-throw line (level on the wing, toward the rim at the top).
  const ON_BALL_FT = 4.1;
  function onBallSpot(man, rim, bounds) {
    const ft = { x: rim.x, y: ftY(rim) };
    const d = len(sub(ft, man));
    if (d < 8) return clamp({ x: man.x, y: man.y - ON_BALL_FT * 10 }, bounds);
    return clamp(add(man, mul(norm(sub(ft, man)), ON_BALL_FT * 10)), bounds);
  }

  function ballInside(ball, rim) {
    return isLowPost(ball, rim) || isHighPost(ball, rim) || Math.abs(ball.x - rim.x) < 60 && ball.y < ftY(rim) + 20;
  }

  // Three passes away (far side): Scott puts him in the middle of the lane, about 9.5 ft
  // out from the baseline, a step toward his man's side (33 of his spots: 3.1 ft off,
  // against 4.8 ft for the triangle share).
  const FAR_HELP = { sideFt: 0.5, depthFt: 9.5 };

  function triangle(man, ball, rim, away, isPost) {
    if (!isPost && away >= 3 && !ballInside(ball, rim)) {
      return { x: rim.x + (Math.sign(man.x - rim.x) || 1) * FAR_HELP.sideFt * 10, y: rim.y + FAR_HELP.depthFt * 10 };
    }
    const k = isPost ? SPOT.post : ballInside(ball, rim) ? SPOT.inside : SPOT[Math.min(3, Math.max(1, away))];
    const toBall = sub(ball, man);
    if (len(toBall) < 8) return lerp(man, rim, 0.2);
    const u = norm(toBall);
    let v = { x: -u.y, y: u.x };
    const toRim = sub(rim, man);
    if (v.x * toRim.x + v.y * toRim.y < 0) v = mul(v, -1); // off the lane on the basket side
    return add(add(man, mul(toBall, k.ball)), mul(v, k.offFt * 10));
  }

  // Scott 2026-10-29, "Fill - Sink - Close": only when a wing is beaten baseline -
  // the ball is near the baseline, inside the 3-point line, outside the lane, with a
  // post on the ball's side. Spacing from his two drawn drives (left and right):
  //   close   - the low post's defender stops the ball (3.6 ft off it, toward the rim)
  //   sink    - the high post's defender drops to the low post (2.2 ft off him, ball side)
  //   fill    - the point's defender fills to the high post (3.6 ft off him, ball side)
  //   rim     - the far wing's defender sinks to the rim
  //   recover - the beaten defender recovers toward the point (57% of the way to the rim)
  // Anything else is normal man defense.
  const DRIVE = { baselineFt: 3.5, closeFt: 3.6, sinkFt: 2.2, fillFt: 3.6, rimDropFt: 3, recover: 0.57 };

  function baselineDrive(offense, handler, rim) {
    const ball = offense[handler];
    const side = Math.sign(ball.x - rim.x);
    const insideArc = Math.abs(ball.x - rim.x) < THREE_CORNER;
    const outsideLane = Math.abs(ball.x - rim.x) > 60;
    if (!(ball.y <= DRIVE.baselineFt * 10 + 10 && insideArc && outsideLane && side)) return null;
    const ids = offenseIds(offense).filter(function (o) { return o !== handler; });
    const posts = ids.filter(function (o) {
      const m = offense[o];
      return (isLowPost(m, rim) || isHighPost(m, rim)) && Math.sign(m.x - rim.x) === side;
    }).sort(function (a, b) { return offense[a].y - offense[b].y; });
    if (!posts.length) return null;
    const low = posts[0], high = posts[1] || null;
    const point = topId(ids.filter(function (o) { return posts.indexOf(o) < 0; }), offense);
    const roles = {};
    roles[handler] = "recover";
    roles[low] = "close";
    if (high) roles[high] = "sink";
    if (point) roles[point] = high ? "fill" : roles[point];
    ids.forEach(function (o) { if (!roles[o]) roles[o] = "rim"; });
    const toward = function (from, to, ft) { return add(from, mul(norm(sub(to, from)), ft * 10)); };
    const spots = {};
    Object.keys(roles).forEach(function (o) {
      const r = roles[o];
      if (r === "close") spots[o] = toward(ball, rim, DRIVE.closeFt);
      else if (r === "sink") spots[o] = toward(offense[low], ball, DRIVE.sinkFt);
      else if (r === "fill") spots[o] = toward(offense[high], ball, DRIVE.fillFt);
      else if (r === "rim") spots[o] = { x: rim.x, y: rim.y + DRIVE.rimDropFt * 10 };
      else if (r === "recover") spots[o] = lerp(offense[point] || ball, rim, DRIVE.recover);
    });
    return { roles: roles, spots: spots };
  }

  function insideThree(spot, rim) {
    let p = { x: spot.x, y: spot.y };
    const maxR = THREE_R - INSIDE;
    const d = len(sub(p, rim));
    if (d > maxR) p = add(rim, mul(sub(p, rim), maxR / d));
    const maxX = THREE_CORNER - INSIDE;
    if (Math.abs(p.x - rim.x) > maxX) p = { x: rim.x + Math.sign(p.x - rim.x) * maxX, y: p.y };
    return p;
  }

  function ftY(rim) { return rim.y + lineDrop(rim); }

  function ballAtOrBelowFt(ball, rim) {
    return ball.y <= ftY(rim) + 8;
  }

  function isHighPost(man, rim) {
    const dy = man.y - rim.y;
    const dx = Math.abs(man.x - rim.x);
    const line = lineDrop(rim);
    return dy > line + 8 && dy < line + 80 && dx >= 36 && dx < 150;
  }

  function isLowPost(man, rim) {
    const dy = man.y - rim.y;
    const dx = Math.abs(man.x - rim.x);
    const line = lineDrop(rim);
    return dy >= 24 && dy <= line + 8 && dx >= 36 && dx < 150;
  }

  function onBall(man, rim, bounds, isTop) {
    const toMiddle = rim.x - man.x;
    const toRim = sub(rim, man);
    if (isTop || Math.abs(toMiddle) < 28) {
      // High shoulder on the top man: between him and the key, one sideline open.
      const step = len(toRim) < 24 ? { x: 0, y: -48 } : mul(norm(toRim), 48);
      const open = Math.abs(toMiddle) < 28 ? 26 : Math.sign(toMiddle) * 16;
      return clamp(add(add(man, step), { x: open, y: 0 }), bounds);
    }
    // Wing or corner: deny the middle and the high side. Sideline and baseline stay open.
    return clamp(add(man, { x: Math.sign(toMiddle || 1) * 30, y: 24 }), bounds);
  }

  function onTheLine(man, ball, bounds) {
    const toBall = sub(ball, man);
    const d = len(toBall);
    if (d < 8) return clamp({ x: man.x, y: man.y - 40 }, bounds);
    const step = Math.min(56, Math.max(40, d * 0.4));
    return clamp(add(man, mul(toBall, step / d)), bounds);
  }

  function frontPost(man, ball, bounds) {
    const toBall = sub(ball, man);
    const d = len(toBall);
    if (d < 8) return clamp({ x: man.x, y: man.y - 44 }, bounds);
    const step = Math.min(52, Math.max(38, d * 0.45));
    return clamp(add(man, mul(toBall, step / d)), bounds);
  }

  function halfDeny(man, ball, rim, bounds) {
    const toBall = sub(ball, man);
    const toRim = sub(rim, man);
    let spot = { x: man.x, y: man.y };
    if (len(toBall) > 8) spot = add(spot, mul(norm(toBall), 36));
    if (len(toRim) > 8) spot = add(spot, mul(norm(toRim), 8));
    return clamp(spot, bounds);
  }

  function twoPass(man, ball, rim, bounds) {
    const toBall = sub(ball, man);
    const d = len(toBall);
    let spot = d < 8
      ? { x: man.x, y: man.y - 40 }
      : add(man, mul(norm(toBall), Math.min(56, d * 0.35)));
    const laneLeft = rim.x - 80;
    const laneRight = rim.x + 80;
    if (spot.x < laneLeft) spot = { x: laneLeft + 14, y: spot.y };
    else if (spot.x > laneRight) spot = { x: laneRight - 14, y: spot.y };
    return clamp(spot, bounds);
  }

  function threePass(man, ball, rim, bounds) {
    const toBall = sub(ball, man);
    const d = len(toBall);
    const along = d < 8 ? { x: man.x, y: man.y } : add(man, mul(toBall, Math.min(0.38, 80 / d)));
    const toRim = sub(rim, along);
    let spot = len(toRim) < 8 ? along : add(along, mul(norm(toRim), 28));
    const floorY = rim.y + 48;
    if (spot.y < floorY) spot = { x: spot.x, y: Math.max(floorY, man.y - 28) };
    if (man.x < rim.x) spot = { x: Math.min(Math.max(spot.x, rim.x - 55), rim.x - 8), y: spot.y };
    else spot = { x: Math.max(Math.min(spot.x, rim.x + 55), rim.x + 8), y: spot.y };
    if (man.y > rim.y + 140 && spot.y > man.y - 30) spot = { x: spot.x, y: man.y - 48 };
    if (len(sub(spot, man)) < 36) {
      const nudged = add(man, mul(norm(sub({ x: rim.x, y: man.y }, man)), 48));
      spot = { x: nudged.x + (ball.x - nudged.x) * 0.2, y: nudged.y };
    }
    return clamp(spot, bounds);
  }

  function passesAway(oid, offense, ballXY, rim, peers) {
    const man = offense[oid];
    const d = len(sub(man, ballXY));
    const ballSide = ballXY.x - rim.x;
    const manSide = man.x - rim.x;
    const opposite = ballSide * manSide < -800;
    const closerSame = peers.filter(function (pid) {
      if (pid === oid) return false;
      const other = offense[pid];
      if (len(sub(other, ballXY)) >= d - 18) return false;
      const side = other.x - rim.x;
      return (side - ballSide) * (manSide - ballSide) > 0;
    }).length;
    if (d <= 205 && closerSame === 0) return 1;
    if (closerSame === 0 && !opposite) return 1;
    if (closerSame <= 1 && d < 330 && !(opposite && d >= 300)) return 2;
    return 3;
  }

  function offenseIds(offense) {
    const ids = [];
    for (let i = 1; i <= 5; i += 1) {
      const pid = "o" + i;
      const p = offense[pid];
      if (p && typeof p.x === "number" && typeof p.y === "number") ids.push(pid);
    }
    return ids;
  }

  function closest(ids, offense, point) {
    return ids.slice().sort(function (a, b) {
      return len(sub(offense[a], point)) - len(sub(offense[b], point));
    })[0];
  }

  function topId(ids, offense) {
    return ids.slice().sort(function (a, b) { return offense[b].y - offense[a].y; })[0];
  }

  function frame(man, ball, rim) {
    const toBall = sub(ball, man);
    const axis = len(toBall) > 12 ? toBall : sub(rim, man);
    const u = norm(len(axis) > 0.001 ? axis : { x: 0, y: -1 });
    return { u: u, v: { x: -u.y, y: u.x } };
  }

  function measureTune(drop, shell, man, ball, rim) {
    if (!drop || !shell || !man) return { along: 0, across: 0 };
    const basis = frame(man, ball || man, rim || { x: 250, y: 40 });
    const delta = sub(drop, shell);
    return {
      along: delta.x * basis.u.x + delta.y * basis.u.y,
      across: delta.x * basis.v.x + delta.y * basis.v.y,
    };
  }

  function applyTune(spot, man, ball, rim, tune) {
    if (!tune || !man) return spot;
    const basis = frame(man, ball || man, rim);
    return add(spot, add(mul(basis.u, tune.along || 0), mul(basis.v, tune.across || 0)));
  }

  function keepBallSide(man, ball, spot, bounds) {
    const toBall = sub(ball, man);
    const d = len(toBall);
    if (d < 8) return clamp(spot, bounds);
    const u = norm(toBall);
    const rel = sub(spot, man);
    const along = rel.x * u.x + rel.y * u.y;
    if (along >= 22) return clamp(spot, bounds);
    const v = { x: -u.y, y: u.x };
    const across = rel.x * v.x + rel.y * v.y;
    return clamp(add(man, add(mul(u, 26), mul(v, across))), bounds);
  }

  function tightLine(man, ball, bounds) {
    const toBall = sub(ball, man);
    const d = len(toBall);
    if (d < 8) return clamp({ x: man.x, y: man.y - 22 }, bounds);
    return clamp(add(man, mul(norm(toBall), Math.min(22, d * 0.45))), bounds);
  }

  function chestRedirect(man, ball, dest, bounds) {
    const toBall = sub(ball, man);
    const toDest = sub(dest, man);
    const u = len(toBall) < 8 ? { x: 0, y: -1 } : norm(toBall);
    const dir = len(toDest) < 8 ? u : norm(toDest);
    let spot = add(man, add(mul(u, 16), mul(dir, 14)));
    if (len(sub(spot, man)) > 26) spot = add(man, mul(norm(sub(spot, man)), 24));
    return clamp(spot, bounds);
  }

  function segmentCrossesLane(a, b, rim) {
    const left = rim.x - 80;
    const right = rim.x + 80;
    const top = rim.y - 8;
    const bottom = rim.y + 130;
    let minX = Infinity;
    let maxX = -Infinity;
    let inside = false;
    for (let i = 0; i <= 12; i += 1) {
      const p = lerp(a, b, i / 12);
      if (p.x < left || p.x > right || p.y < top || p.y > bottom) continue;
      inside = true;
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
    }
    return inside && maxX - minX > 70;
  }

  function cutsToBasket(from, to, rim) {
    return len(sub(from, rim)) - len(sub(to, rim)) > 36;
  }

  function cutProgress(from, to, at) {
    const travel = len(sub(to, from));
    if (travel < 12) return 0;
    const rel = sub(at, from);
    const dir = sub(to, from);
    return (rel.x * dir.x + rel.y * dir.y) / (travel * travel);
  }

  function inPostArea(man, rim) {
    const dy = man.y - rim.y;
    const dx = Math.abs(man.x - rim.x);
    const line = lineDrop(rim);
    return dy >= 20 && dy <= line + 70 && dx >= 28 && dx <= 150;
  }

  function hedgeAt(screenPt, ball, bounds) {
    const toBall = sub(ball, screenPt);
    let hedge = len(toBall) < 8 ? add(screenPt, { x: 0, y: 36 }) : add(screenPt, mul(norm(toBall), 36));
    hedge = add(hedge, { x: 0, y: 12 });
    return clamp(hedge, bounds);
  }

  function otherPost(cut, offense, ballId, rim) {
    let partner = null;
    let best = Infinity;
    offenseIds(offense).forEach(function (oid) {
      if (oid === cut.player || oid === ballId) return;
      const spot = (cut.starts && cut.starts[oid]) || offense[oid];
      if (!spot || !inPostArea(spot, rim)) return;
      const d = len(sub(spot, cut.from));
      if (d < best) { best = d; partner = oid; }
    });
    return partner;
  }

  function slide(from, to, t) {
    if (!from) return to;
    if (!to) return from;
    const u = Math.max(0, Math.min(1, t));
    return { x: from.x + (to.x - from.x) * u, y: from.y + (to.y - from.y) * u };
  }

  function applyPostExchange(out, offense, ballXY, onBallId, cuts, rim, bounds, matchups, switchSink, shell) {
    (cuts || []).forEach(function (cut) {
      if (!cut || !cut.from || !cut.player || cut.player === onBallId) return;
      const at = cut.at || cut.to;
      if (!at || !inPostArea(cut.from, rim)) return;
      const did = "d" + String(cut.player).replace(/\D/g, "");
      if (matchups && matchups[did] && matchups[did] !== cut.player) return;
      const travel = len(sub(at, cut.from));
      if (travel < 8) return;
      const partner = otherPost(cut, offense, onBallId, rim);
      if (!partner) return;
      const startDist = len(sub(cut.from, ballXY));
      const nowDist = len(sub(at, ballXY));
      const away = nowDist > startDist + 12;
      const toward = nowDist + 12 < startDist;
      const partnerMan = offense[partner];
      const partnerDef = "d" + String(partner).replace(/\D/g, "");
      const gap = partnerMan ? len(sub(cut.from, partnerMan)) : 100;
      const ramp = Math.max(72, Math.min(150, gap || 100));
      const progress = Math.max(0, Math.min(1, (travel - 6) / ramp));
      const home = (shell && shell[did]) || out[did];
      const partnerHome = (shell && shell[partnerDef]) || out[partnerDef];
      if (away) {
        const hedge = hedgeAt(partnerMan || at, ballXY, bounds);
        if (home) out[did] = slide(home, hedge, progress);
        if (partnerHome && partnerMan) out[partnerDef] = slide(partnerHome, tightLine(partnerMan, ballXY, bounds), progress * 0.85);
        return;
      }
      if (!toward || !partnerMan) return;
      const chest = chestRedirect(at, ballXY, ballXY, bounds);
      const hedge = hedgeAt(partnerMan, ballXY, bounds);
      const chestNow = slide(home, chest, Math.min(1, 0.2 + progress * 0.8));
      const hedgeNow = slide(partnerHome, hedge, progress);
      const partnerDist = len(sub(partnerMan, ballXY));
      const startedFarther = startDist > partnerDist + 10;
      const passGap = partnerDist - nowDist;
      const alongside = len(sub(at, partnerMan)) < 120;
      const crossT = startedFarther && alongside ? Math.max(0, Math.min(1, (passGap + 28) / 64)) : 0;
      const arrivedHigh = isHighPost(at, rim) && !ballAtOrBelowFt(ballXY, rim);
      const frontCutter = arrivedHigh ? halfDeny(at, ballXY, rim, bounds) : frontPost(at, ballXY, bounds);
      const takeScreener = keepBallSide(partnerMan, ballXY, onTheLine(partnerMan, ballXY, bounds), bounds);
      if (partnerHome || hedgeNow) out[partnerDef] = slide(hedgeNow, frontCutter, crossT);
      if (home || chestNow) out[did] = slide(chestNow, takeScreener, crossT);
      if (crossT >= 0.98 && switchSink) {
        switchSink.push({ defender: partnerDef, man: cut.player, other: did, otherMan: partner });
      }
    });
  }
  function applyCuts(out, offense, ballXY, onBallId, cuts, rim, bounds) {
    (cuts || []).forEach(function (cut) {
      if (!cut || !cut.player || cut.player === onBallId) return;
      const from = cut.from;
      const to = cut.to;
      const at = cut.at || to;
      if (!from || !to || !at || !offense[cut.player]) return;
      const liveCut = !!cut.live;
      const travel = len(sub(liveCut ? at : to, from));
      if (travel < 16) return;
      if (!liveCut) {
        const t = cutProgress(from, to, at);
        if (t < 0.08 || t > 0.98) return;
      }
      const did = "d" + String(cut.player).replace(/\D/g, "");
      if (!out[did]) return;
      const dest = liveCut ? at : to;
      if (segmentCrossesLane(from, dest, rim)) out[did] = chestRedirect(at, ballXY, dest, bounds);
      else if (cutsToBasket(from, dest, rim)) out[did] = tightLine(at, ballXY, bounds);
    });
  }
  function applyScreens(out, offense, ballId, screens, bounds) {
    (screens || []).forEach(function (screen) {
      const sid = screen && screen.screener;
      const screenPt = (screen && screen.point) || (sid && offense[sid]);
      const ball = offense[ballId];
      if (!sid || !screenPt || !ball) return;
      const dSid = "d" + String(sid).replace(/\D/g, "");
      const dBall = "d" + String(ballId).replace(/\D/g, "");
      const toBall = sub(ball, screenPt);
      let hedge = len(toBall) < 8 ? add(screenPt, { x: 0, y: 36 }) : add(screenPt, mul(norm(toBall), 44));
      hedge = add(hedge, { x: 0, y: 16 });
      if (out[dSid]) out[dSid] = clamp(hedge, bounds);
      const over = add(lerp(screenPt, ball, 0.35), { x: 0, y: 26 });
      if (out[dBall]) out[dBall] = clamp(over, bounds);
    });
  }

  function placeManDefense(offense, ballPid, options) {
    const opts = options || {};
    const rim = opts.rim || { x: 250, y: 15 };
    const bounds = opts.bounds || { minX: 18, minY: 18, maxX: 482, maxY: 452 };
    const ids = offenseIds(offense || {});
    if (!ids.length) return {};
    const handler = ballPid && offense[ballPid] ? ballPid : ids[0];
    const ballXY = opts.ballPoint && typeof opts.ballPoint.x === "number"
      ? opts.ballPoint
      : offense[handler];
    let onBallId = handler;
    if (opts.ballPoint && len(sub(opts.ballPoint, offense[handler])) > 36) {
      onBallId = closest(ids, offense, ballXY);
    }
    const top = topId(ids, offense);
    const below = ballAtOrBelowFt(ballXY, rim);
    const peers = ids.filter(function (oid) {
      if (oid === onBallId) return false;
      const man = offense[oid];
      if (isHighPost(man, rim)) return false;
      if (isLowPost(man, rim) && below) return false;
      return true;
    });
    const matchups = opts.matchups || {};
    const out = {};
    ids.forEach(function (oid) {
      const did = "d" + oid.slice(1);
      const manId = matchups[did] && offense[matchups[did]] ? matchups[did] : oid;
      const man = offense[manId];
      if (!man) return;
      if (manId === onBallId) out[did] = onBallSpot(man, rim, bounds);
      else if (isHighPost(man, rim) || isLowPost(man, rim)) out[did] = clamp(triangle(man, ballXY, rim, 1, true), bounds);
      else {
        const away = passesAway(manId, offense, ballXY, rim, peers);
        out[did] = clamp(triangle(man, ballXY, rim, away), bounds);
      }
      const tune = opts.tunes && opts.tunes[did];
      if (tune) out[did] = clamp(applyTune(out[did], man, manId === onBallId ? man : ballXY, rim, tune), bounds);
      if (manId !== onBallId) out[did] = keepBallSide(man, ballXY, out[did], bounds);
    });
    applyScreens(out, offense, onBallId, opts.screens, bounds);
    const shell = {};
    Object.keys(out).forEach(function (k) { shell[k] = { x: out[k].x, y: out[k].y }; });
    applyCuts(out, offense, ballXY, onBallId, opts.cuts, rim, bounds);
    applyPostExchange(out, offense, ballXY, onBallId, opts.cuts, rim, bounds, matchups, opts.switchSink, shell);
    const drive = opts.matchups ? null : baselineDrive(offense, handler, rim);
    if (drive) Object.keys(drive.spots).forEach(function (o) { out["d" + o.slice(1)] = clamp(drive.spots[o], bounds); });
    ids.forEach(function (oid) {
      const did = "d" + oid.slice(1);
      const manId = matchups[did] && offense[matchups[did]] ? matchups[did] : oid;
      if (out[did] && manId !== onBallId) out[did] = insideThree(out[did], rim);
    });
    return out;
  }

  // Each defender's job, named by the same branches placeManDefense takes
  // (for captions; no positions).
  function defenseRoles(offense, ballPid, options) {
    const opts = options || {};
    const rim = opts.rim || { x: 250, y: 15 };
    const ids = offenseIds(offense || {});
    if (!ids.length) return {};
    const handler = ballPid && offense[ballPid] ? ballPid : ids[0];
    const ballXY = offense[handler];
    const below = ballAtOrBelowFt(ballXY, rim);
    const peers = ids.filter(function (oid) {
      if (oid === handler) return false;
      const man = offense[oid];
      if (isHighPost(man, rim)) return false;
      if (isLowPost(man, rim) && below) return false;
      return true;
    });
    const out = {};
    const drive = baselineDrive(offense, handler, rim);
    if (drive) {
      Object.keys(drive.roles).forEach(function (o) { out["d" + o.slice(1)] = drive.roles[o]; });
      return out;
    }
    ids.forEach(function (oid) {
      const man = offense[oid];
      let role;
      if (oid === handler) role = "ball";
      else if (isHighPost(man, rim) || isLowPost(man, rim)) role = "post";
      else if (ballInside(ballXY, rim)) role = "sink";
      else role = "away" + Math.min(3, Math.max(1, passesAway(oid, offense, ballXY, rim, peers)));
      out["d" + oid.slice(1)] = role;
    });
    return out;
  }

  return { placeManDefense: placeManDefense, measureTune: measureTune, defenseRoles: defenseRoles };
});
