# Active Task

Updated: 2026-08-10 (stat-book upload fix)

Branch: `cursor/stat-book-upload-fix-ac1f` (merged)  
Base: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stat-book-upload-fix |
| **status** | `done` |
| **assigned_to** | cursor-agent |

## Scope delivered

- Fix Internal Server Error on `/stat-books` upload when Game ID contains commas (JrHigh keys like `jrhigh_adrian,_or_?`)
- Soft-fail OCR/align: still save upload + open review UI for manual fill
- Flask restarted on :8080 (Python312); upload returns 302 ? review 200

## Try

1. Hard-refresh `http://127.0.0.1:8080/stat-books`
2. Paste a JrHigh GameID from `/videos` (e.g. `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`)
3. Choose a scorebook photo ? **Upload & extract**
4. Expect redirect to review (not Internal Server Error); fill blanks if OCR is empty

## Report

### Proven

- Root cause: `sanitize_game_id` rejected `,` ? `ValueError` ? Flask 500 (`data/flask_8080_restart.err.log`)
- Commit `525a42d` on `jason-5-may-updates` (+ branch `cursor/stat-book-upload-fix-ac1f`)
- Live POST verified: upload **302** ? review **200**; `draft.json` + `original.png` written

### Inferred

- Form HTML5 `pattern` previously blocked commas client-side; some browsers/clients still POSTed and hit the server bug

### Unknown

- How complete EasyOCR digit reads are on real spiral photos vs blank template
