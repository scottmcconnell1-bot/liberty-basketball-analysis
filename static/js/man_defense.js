/* Man-to-man spots for the little defender marks.
   On the ball: between the man and the rim.
   One pass away: about two-fifths of the way from the man to the ball, a step toward the rim.
   Two passes away (help side): sag to the lane / rim line, still able to see the ball and the man.
   Basket is at the top of these diagrams, so smaller y is closer to the rim.
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

  function onBall(man, rim, bounds) {
    const gap = 36;
    const toRim = sub(rim, man);
    if (len(toRim) < 24) return clamp({ x: man.x, y: man.y + gap }, bounds);
    return clamp(add(man, mul(norm(toRim), gap)), bounds);
  }

  function onePass(man, ball, rim, bounds) {
    let spot = lerp(man, ball, 0.4);
    spot = add(spot, mul(norm(sub(rim, spot)), 16));
    if (len(sub(spot, man)) < 28) {
      const toward = norm(add(norm(sub(ball, man)), norm(sub(rim, man))));
      spot = add(man, mul(toward, 34));
    }
    return clamp(spot, bounds);
  }

  function isHelpSide(man, ball, rim) {
    const ballSide = ball.x - rim.x;
    const manSide = man.x - rim.x;
    const dist = len(sub(man, ball));
    if (Math.abs(ballSide) < 40) return dist > 190;
    return ballSide * manSide < 0 && dist > 100;
  }

  function helpSide(man, ball, rim, bounds) {
    const laneHalf = 80;
    const ballInCorner = ball.y < rim.y + 110 && Math.abs(ball.x - rim.x) > 80;
    let x;
    if (ballInCorner) {
      x = rim.x;
    } else if (Math.abs(man.x - rim.x) > laneHalf) {
      const side = Math.sign(man.x - rim.x) || 1;
      x = rim.x + side * laneHalf - side * 14;
    } else {
      x = man.x * 0.4 + rim.x * 0.6;
    }
    const yTowardBall = man.y + (ball.y - man.y) * 0.18;
    const y = yTowardBall + (rim.y - yTowardBall) * 0.15;
    let spot = { x: x, y: y };
    if (len(sub(spot, man)) < 28) {
      spot = add(man, mul(norm(sub({ x: rim.x, y: man.y }, man)), 36));
    }
    return clamp(spot, bounds);
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
    const out = {};
    ids.forEach(function (oid) {
      const man = offense[oid];
      const did = "d" + oid.slice(1);
      if (oid === onBallId) out[did] = onBall(man, rim, bounds);
      else if (isHelpSide(man, ballXY, rim)) out[did] = helpSide(man, ballXY, rim, bounds);
      else out[did] = onePass(man, ballXY, rim, bounds);
    });
    return out;
  }

  return { placeManDefense: placeManDefense };
});
