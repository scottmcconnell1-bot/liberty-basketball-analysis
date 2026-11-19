# Spec 44 GV hand-check (Claude Code 2026-11-09), written BEFORE 44_gv_score.py was run

Run note: run.sh steps ft/tracks/v6/d2 rc 0. The vote step returned rc 1 because the out dir
(mm44_gv) already existed (it held run.sh). Fix: I re-ran ONLY the vote, which is a pure join of the
saved v6/d2 results, into mm44_gv/vote/. No model or rule was re-run. Vote: make 19, coach 6,
miss 453, no_track 54 (532).
d2 log mapping gate: agreement with v6 = 0.81. Mapping is proven by the v6 candidates (rate 1.00),
as spec 23 v3 requires; the gate note is expected for d2v1.

Sheets: scratchpad gv/hc/r000-r026.jpg (wide -1.6/-0.6 s, hoop crops -0.32..+0.96 s, score -2/+8 s).
Verdict = what I see at the moment (shot y/n, result, FT). Each was set from the frames, not from the frozen labels.

## Make calls (19)
- right (real make): 153 (FT), 179 (FT), 181 (FT), 309 (FT), 347 (FT), 444 (FT), 445 (FT), 486 (FT), 498, 507, 450 (ball sits on the rim and rolls in; score +3, so probably a make)
- wrong, real miss: 98 (off the board), 214 (off the rim)
- wrong, not a shot: 76, 212 (pre-FT setup), 250 (warm-up), 344 (no ball at the rim), 366 (no ball at the rim)
- unclear: 354 (miss, then a put-back that scores about 1 s later)

## Coach calls (6)
- real make: 201 (FT), 447, 487 (FT)
- real miss: 190
- not a shot: 266 (warm-up), 492 (ref holding the ball)

## no_track (54)
- All are not a shot: warm-ups / halftime / off-court (108-128 game-1 break, 405, 433-438 halftime) and dead balls / ref holding the ball / camera pans (5, 6, 7, 34, 42, 43, 45, 57, 58, 81, 84, 90, 131, 156, 157, 188, 194, 221, 297, 455, 472, 473, 481, 483, 493, 494). No real shot is hidden in no_track.

## FT rule flags
- free_throw_line (20), real FT: 26, 153, 179, 183, 201, 202, 218, 309, 310, 347, 444, 457, 459, 460 (same miss as 459, 0.56 s later), 461, 486, 487, 495, 496 = 19
- free_throw_line, NOT an FT: 118 (game-1 break, finder hoop = a door)
- maybe_free_throw (18): none is an FT. 38, 56, 63, 109, 158 (FT line-up before the shot), 166, 236, 237, 242, 257, 270, 279, 305, 351, 372, 418, 471, 500 are live play, warm-ups, or the ref holding the ball.
- Real FTs called miss by make/miss (makes seen in frames): 202, 218, 310, 457, 461, 496 (silent errors). FT misses called miss correctly: 183, 459, 460, 495.
