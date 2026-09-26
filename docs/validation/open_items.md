# Open items: validation log

These are the open items listed in docs/validation/README.md, plus one display
issue the access fixes left behind (#7).

Process for each item:

1. Write a new end-to-end test that asserts the correct behaviour, and run it on
   8b5c670 to record the failure ("Before").
2. Fix the code.
3. Rerun the same test ("After").

All the tests are in `tests/e2e/test_journey_open_items.py`, except the rewritten
test in `tests/test_messaging.py`.

| # | Item | Before (8b5c670) | Fix | After | Regression test |
|---|---|---|---|---|---|
| 1 | `DELETE /api/events/<id>` returned 500 when a clip or dev clip referenced the event | `sqlite3.IntegrityError: FOREIGN KEY constraint failed` | `blueprints/clips.py` `delete_event`: detaches `clips.event_id` and `player_development_clips.event_id` before the delete. The clips are kept. | passed | test_delete_event_referenced_by_clips_keeps_the_clips |
| 2a | The Users page read `username`/`is_admin`, but `/api/users` is the 20-row autocomplete route that returns neither | `404` on `/api/admin/users` (the page shows "undefined") | New admin-only `GET /api/admin/users` (replaces the shadowed `core.api_users_list`). `templates/users.html` renders `display_name`/`role`, escapes values, and hides Delete for admins. | passed | test_admin_user_list_has_the_fields_the_page_renders; test_users_page_renders_names_roles_and_no_delete_for_admins (runs the page JS in node) |
| 2b | Deleting a user referenced by `created_by_user_id`/`reviewed_by_user_id` returned 500 | `sqlite3.IntegrityError: FOREIGN KEY constraint failed` | `core._detach_user_references`: finds every FK to `users(id)` with `PRAGMA foreign_key_list` and nulls the nullable, no-action columns. A NOT NULL reference gets 409. | passed | test_admin_can_delete_a_user_other_rows_point_at |
| 3 | Assistant turnover/clip lookups used `LIKE %hint%`, so "Al" included Alice | `'Al has 3 reviewed turnover(s)'` (expected 1) | `assistant_query`: exact case-insensitive name first, substring only when no exact match. The same change applies to minutes. | passed | test_assistant_turnovers_and_clips_use_the_exact_player |
| 4 | The scouting report editor left jersey, PPP, frequency, opponent jersey and game time unescaped | injected tags `{'img'}` | `templates/scouting_report.html`: every stored value goes through `escapeHtml`; percentage fields are coerced with `Number()` | passed | test_scouting_editor_escapes_numbers_times_and_jerseys (runs the editor JS in node) |
| 5 | Status/progress/results counters summed rows across runs that share an NFHS relational game | `(8, 6) == (5, 4)` | New `helpers.count_rows_for_run` counts the run's own rows first and falls back to the relational game only for legacy rows. Used by `/api/analysis_status`, `/api/analysis_progress`, `/api/analysis/<id>` and `count_events_for_analysis`. | passed | test_counts_are_per_run_when_runs_share_a_relational_game |
| 6 | `/api/upload_video` overwrote a file with the same name | `'game.mp4' != 'game.mp4'` | Picks `name`, `name_2`, … and creates the file with O_EXCL. A name that sanitises to empty gets 400. | passed | test_upload_video_keeps_both_files_with_the_same_name |
| 7 | Messages panel and site nav showed "Signed in as <name>" from a cookie replayed after logout | `'Signed in as' is contained` | `templates/messages.html` uses only the server-verified `messaging_identity`. New `signed_in_user` context value (from `_current_user`) drives the nav name and the push/notification scripts. The recipient directory is hidden from anonymous visitors. | passed | test_messages_page_does_not_show_a_logged_out_cookie_as_signed_in; tests/test_messaging.py::test_session_without_live_login_is_not_signed_in (it replaces a test that asserted the insecure behaviour) |

## Evidence

- Full suite after the fixes: **984 passed, 31 skipped, 0 failed, 0 xfailed**.
  It writes nothing outside temp dirs.
- The same test files run against 8b5c670 app code give **10 failed**: every new
  test above, including the rewritten messaging test.
