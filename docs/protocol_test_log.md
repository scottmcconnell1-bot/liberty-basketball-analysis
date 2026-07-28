# Basketball Evidence Protocol Test Log

## Test 1

Date: 2026-06-02

Question:
How many clip directories currently exist in the active extraction output?

Result:
5 directories

Assessment:
Likely correct

Violations:

* V1 Missing source evidence
* V2 Unsupported derived fact
* V6 Missing output type

Outcome:
Fail

## Test 2

Date: 2026-06-02

Question:
How many clip directories currently exist in the active extraction output?

Protocol Prompt:
Strict protocol format required

Result:
5 directories

Assessment:
Evidence and verification supplied

Violations:

* V6 Missing output type

Outcome:
Pass

## Test 3

Date: 2026-06-02

Question:
How many total extracted frames currently exist across all clip directories?

Result:
733 files

Assessment:
Raised discrepancy with earlier 728-frame claim

Violations:

* V1 Missing source evidence
* V6 Missing output type

Outcome:
Needs Follow-Up

## Test 4

Date: 2026-06-02

Question:
Provide JPG frame count for each clip directory individually.

Result:
728 frame_*.jpg files

Assessment:
Discrepancy resolved

Violations:

* V1 Formatting only
* V6 Formatting only

Outcome:
Pass

V8 Question not answered

V9 Conclusion exceeds evidence

Test 5

Question:
What objective criteria define annotation-ready?

Outcome:
Pass

Finding:
No documented annotation-ready criteria exist.

Follow-up:
All proposed thresholds were classified as PROPOSED.

Violations:
None identified.

Value:
Prevented proposed thresholds from being misrepresented as project requirements.

Test 6

Question:
Measure resolution and file statistics

Outcome:
Partial Pass

Observed:
File sizes measured successfully

Blocker:
Image resolution measurement failed

Finding:
Previous 1280x720 claim requires re-verification

Violations:
None

Value:
Agent reported measurement failure instead of inventing data.
