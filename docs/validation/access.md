# Validation: access control / messaging / settings

Findings from `docs/REVIEW_FINDINGS_2026-09-26.md`, area **access**. Each was validated with
`pytest <test> --runxfail -p no:cacheprovider` before the fix (first `E` line recorded), fixed
in the app code, then re-run with the `xfail` marker removed. The tests stay in
`tests/e2e/test_journey_access.py` (file abbreviated `tja` below) as permanent regression tests.

| # | Finding (file:line) | Before (failing assertion) | Fix (files/functions) | After (test result) | Regression test |
|---|---|---|---|---|---|
| 1 | Coach login open redirect, `blueprints/coach.py:216` | `AssertionError: assert not 'evil.example'` (Location netloc) | `coach.coach_login`: `next` goes through `helpers.extract_local_path`, fallback `/coach/progress` (same as `users.login`) | PASSED | `tja::test_coach_login_rejects_offsite_next` (off-site `https://` and `//` fall back; local `next` kept) |
| 2 | Logout does not invalidate the cookie, `blueprints/users.py:57` | `AssertionError: assert False` (`_redirects_to_login` on replayed cookie: got 200) | `users._current_user`: requires `session_token` and a matching, unexpired `user_sessions` row for that user (logout deletes the row). Used by the gate, `login_required`, `role_required`, messaging, settings, admin checks | PASSED | `tja::test_logged_out_cookie_cannot_be_replayed` (copy works before logout; after: page → /login, API 401, `login_required` → /login; re-login works) |
| 3 | Stale coach cookie bypasses gate when portal disabled, `app.py:200` | `assert 1 == 0` (issue report was planted) | `app.require_auth_for_api`: a `coach_portal` session only passes while `ENABLE_COACH_PORTAL` is on | PASSED | `tja::test_gate_on_stale_coach_cookie_gets_no_access_after_portal_disabled` (POSTs and GETs → /login, API 401, flags unchanged) |
| 4 | Any signed-in user can change settings, `blueprints/core.py:1883` (+ `/settings/ollama/pull` ~2000) | `AssertionError: assert '0' == '1'` (player switched the gate off) | New `core._settings_change_denied()` called on `POST /settings` and `POST /settings/ollama/pull`: admin always allowed; signed-in non-admin → 403 in both modes; anonymous → allowed only while `ENABLE_AUTH_MIDDLEWARE` is off (see note) | PASSED | `tja::test_gate_on_non_admin_cannot_change_settings` (player/coach/manager 403 on both routes, GET still 200, admin still saves); new `tja::test_gate_off_settings_open_to_anonymous_but_not_to_signed_in_non_admin` |
| 5 | Conversation list not scoped to user, `blueprints/messaging.py:111` (and API list :179) | `AssertionError: ('a', [1, 1])` / `assert [1, 1] == [1]` | New `messaging._conversations_for(db, user_id)`: JOIN on `cm.user_id = <session identity>`; used by `/messages` and `/api/messages/conversations` (anonymous: page shows none, API 401) | PASSED | `tja::test_messaging_each_user_lists_only_own_conversations` (API + page sidebar) |
| 6 | Poll / page read any conversation (IDOR), `messaging.py:297, 125-139` | `assert 200 in (403, 404)` | `messages_api_poll`: 401 anonymous, 403 non-member (`_is_member`); `/messages?c=` only loads the active conversation for a member | PASSED | `tja::test_messaging_outsider_cannot_read_conversation` (exact 403, body not leaked, page shows no messages) |
| 7 | Send never checks membership, `messaging.py:243` | `assert 200 in (403, 404)` | `messages_api_send`: posting to an existing conversation requires membership → 403 | PASSED | `tja::test_messaging_outsider_cannot_post_into_conversation` (403, nothing stored; members still post) |
| 8 | Message notifications never fire, `services/notifications.py:181/204/209` | `AssertionError: assert [] == ['New message from Alice']` | `notify_message_received`: dropped `conversations.name` lookup (column absent, value unused); insert only real columns into `notifications`; members resolved via JOIN `users` (legacy `"coach"` member skipped - FK); prefs converted `dict(row)` before `.get` | PASSED | `tja::test_messaging_recipient_gets_unread_notification_and_can_mark_it_read` (both directions, outsider gets none, mark-read, and again with push/email prefs saved) |
| 9 | Read receipts from payload `user_id`, `messaging.py:315` | `AssertionError: assert {'1', 'coach'} == {'2'}` | `messages_api_read`: reader = session identity (payload ignored), 401 anonymous; receipt inserted only when the message's conversation has the reader as a member | PASSED | `tja::test_messaging_mark_read_records_the_signed_in_reader` |
| 10 | Anonymous sender impersonation, `messaging.py:32` | `AssertionError: assert (<Row> is None or '1' != '1')` | `messaging._resolve_sender_id()`: identity from `_current_user()` (or coach portal while the portal feature is on); never from payload; `None` → 401 on send/poll/read/list even when the gate is off | PASSED | `tja::test_messaging_anonymous_cannot_impersonate_sender` (401 on send/poll/list/read, nothing stored, page shows nothing, replayed logged-out cookie also 401) |
| 11 | Numeric `recipient_id` crashes send, `messaging.py:203` | `AttributeError: 'int' object has no attribute 'strip'` | `messages_api_send`: `str(data.get("recipient_id") or "").strip()` | PASSED | `tja::test_messaging_numeric_recipient_id` (200, both members stored, recipient can poll) |
| 12 | Negative UTC offset crash, `module_entitlements.py:33` | `TypeError: can't compare offset-naive and offset-aware datetimes` | New `module_entitlements._parse_naive_utc()` used by `_normalize_at` / `_normalize_bound`: any parsed tz-aware value → naive UTC (old check only looked for `+` / `Z`) | PASSED | `tja::test_entitlement_window_with_negative_utc_offset` (active / expired / not-started with `-06:00`); new `tja::test_entitlement_negative_offset_is_converted_to_utc` |
| 13 | `safe_return_path` bad fallback, `helpers.py:1674` | `werkzeug.routing.exceptions.BuildError: Could not build url for endpoint 'debug_page'` | `helpers.safe_return_path` default `fallback="core.debug_page"` | PASSED | `tja::test_issue_report_offsite_return_to_falls_back_to_debug` (off-site, `//`, missing → `/debug`; reports saved) |
| 14 | User delete crashes / no auth, `blueprints/core.py:2559` | `IndexError: No item with that key` | `core.api_users_delete`: requires signed-in admin (`_is_admin_user(_current_user())`) even with gate off → 403; admin check on target uses `_is_admin_user` (role based; tolerates missing `is_admin`) | PASSED | `tja::test_admin_can_delete_a_user` (anonymous/coach 403 and nothing deleted; admin 200; 404 on repeat; admins cannot be deleted) |

## Decisions

- **Settings with the gate OFF (finding 4).** `ENABLE_AUTH_MIDDLEWARE` defaults off and the
  app is intentionally open until the owner enables sign-in, so an anonymous `POST /settings`
  still works in that mode (otherwise nobody could turn the gate on without first creating an
  admin). A signed-in non-admin is refused (403) in both modes, and with the gate on only an
  admin may change settings or start an Ollama pull. Viewing `GET /settings` is unchanged.
- **Session validation (finding 2).** `_current_user()` now requires the cookie's
  `session_token` to match a live, unexpired `user_sessions` row. Every real login already
  writes that row, so login flows are unchanged. This also closes cookie forgery with the
  committed dev `SECRET_KEY` fallback (a forged cookie cannot guess a token).
- **Messaging identity.** Signed-in user id (validated as above) or, while the coach portal
  feature is on, the shared `"coach"` identity (coach portal remains read-only through the
  denylist). Anonymous callers: `/messages` still renders (200) with no conversations;
  `/api/messages/*` return 401 `{"error": "Sign-in required."}` even with the gate off.
- No schema changes; feature-flag defaults unchanged.

## Test updates outside the journey file

`tests/test_messaging.py` encoded the old anonymous-as-`"coach"` behaviour (the bug in
findings 5-10). Those tests now sign in through `/login` (real session token) and create
conversations with the signed-in user as a member; new cases assert anonymous 401 on
list/send/poll/read, 403 for non-members on send/poll, and that the read receipt records the
signed-in reader.

## Not fixed (out of the covered tests)

- `/api/users` is registered by both `users_bp` (wins, returns `display_name`/`role`) and
  `core.api_users_list` (dead code, selects non-existent `username`/`is_admin`).
  `templates/users.html` still reads `u.username` / `u.is_admin`, so the list renders
  "undefined" and shows a Delete button on admins (the server now refuses deleting admins).
- Deleting a user referenced by `created_by_user_id` / `reviewed_by_user_id` columns (no
  `ON DELETE`) would fail the FK check; not covered by a test.
- `templates/messages.html` still shows "Signed in as" from raw `session['user_id']` for a
  stale cookie (display only; the server treats it as anonymous).

## Suite

- Before (28e6053): 846 passed, 31 skipped, 95 xfailed.
- After: 867 passed, 31 skipped, 81 xfailed (14 xfails fixed; +7 new tests: 2 in the journey
  file, 5 in `tests/test_messaging.py`).
