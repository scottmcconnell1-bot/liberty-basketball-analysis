# Stage A — small fixes per-fix report

Plan: `.team/specs/18_makes_misses_work_plan.md` (VETTED). Switches default OFF; no cutoff changes.

Identity: IDENTITY: 140/140 same

Build set: 140 = 47 makes (28 rule-right + 19 missed) + 93 misses.

Hard gate: 0 misses called makes. Numbers are measured once; nothing was tuned to them.

## baseline_all_off

- makes right: 28
- missed makes: 19
- misses called makes: 0
- hard gate: PASS
- missed makes recovered (t): []
- verdict changes: 0

(no verdict changes)

## A7_alone

- makes right: 28
- missed makes: 19
- misses called makes: 0
- hard gate: PASS
- missed makes recovered (t): []
- verdict changes: 2

| t | film | old | new |
| --- | --- | --- | --- |
| 755400 | adrian | miss/short_net_depth | miss/ball_box_jump |
| 2529600 | adrian | miss/short_net_depth | miss/ball_starts_well_below |

## A8_alone

- makes right: 28
- missed makes: 19
- misses called makes: 0
- hard gate: PASS
- missed makes recovered (t): []
- verdict changes: 1

| t | film | old | new |
| --- | --- | --- | --- |
| 774600 | notus_a1 | miss/ball_went_up | miss/ball_box_jump |

## A4_alone

- makes right: 25
- missed makes: 22
- misses called makes: 1
- hard gate: FAIL
- missed makes recovered (t): []
- verdict changes: 4

| t | film | old | new |
| --- | --- | --- | --- |
| 338700 | adrian | miss/sideways_drift | make/None |
| 590900 | adrian | make/None | miss/sideways_drift |
| 2607300 | adrian | make/None | miss/sideways_drift |
| 2914500 | adrian | make/None | miss/sideways_drift |

## C4_alone

- makes right: 28
- missed makes: 19
- misses called makes: 0
- hard gate: PASS
- missed makes recovered (t): []
- verdict changes: 0

(no verdict changes)

## all_four

- makes right: 25
- missed makes: 22
- misses called makes: 1
- hard gate: FAIL
- missed makes recovered (t): []
- verdict changes: 7

| t | film | old | new |
| --- | --- | --- | --- |
| 774600 | notus_a1 | miss/ball_went_up | miss/ball_box_jump |
| 338700 | adrian | miss/sideways_drift | make/None |
| 590900 | adrian | make/None | miss/sideways_drift |
| 755400 | adrian | miss/short_net_depth | miss/tracker_swap_bodd_ball |
| 2529600 | adrian | miss/short_net_depth | miss/ball_starts_well_below |
| 2607300 | adrian | make/None | miss/sideways_drift |
| 2914500 | adrian | make/None | miss/sideways_drift |
