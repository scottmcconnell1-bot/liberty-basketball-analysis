# Active Task



Updated: 2026-07-23 (Recruiting Station MVP)



Branch: `cursor/recruiting-station-ac1f`



PR: https://github.com/scottmcconnell1-bot/liberty-basketball-analysis/pull/134





## Meta



| Field | Value |

| --- | --- |

| **id** | recruiting-station-mvp |

| **status** | `completed` (MVP shipped) |

| **assigned_to** | cursor-agent |





## Objective



Add a **Recruiting Station** — list/create/edit recruiting profiles linked to roster players, public share URL + print view, program level (jr_high / jv / varsity), gated by `ENABLE_RECRUITING`.





## Checklist



- [x] Branch off `jason-5-may-updates`

- [x] `ENABLE_RECRUITING` feature flag (default **True** — note for Scott)

- [x] `recruiting_profiles` via `helpers.py` `CREATE TABLE IF NOT EXISTS` (no `schema.sql` change)

- [x] Nav: More → Recruiting

- [x] List + create/edit UI; optional player link; stats blurb from `stats`

- [x] Public share `/recruiting/share/<token>` + print `/recruiting/share/<token>/print`

- [x] API smoke tests `tests/test_recruiting.py`

- [x] Restart web :8080 only (left `analysis_launcher` / `hoops_teach_loop` running)

- [x] Update ACTIVE.md; open PR





## Report



### Proven



- Routes live on :8080: `/recruiting`, `/recruiting/new`, `/api/recruiting`, `/recruiting/share/<token>`, `/…/print`

- Table created by `_ensure_migration_columns` (not `schema.sql`)

- Flag default True in `config.Features`; appears in Settings like other ENABLE_* flags

- `pytest tests/test_recruiting.py tests/test_nav_cleanup.py` → 9 passed

- Reuses `/api/players`-compatible `players` rows + aggregates `stats` by `player_id` (fallback name match)



### Inferred



- Default True matches Practices / Player Dev coach tools; Scott can uncheck in Settings without a code change

- Career totals are the same aggregation as season until multi-season person identity exists (see prior Career discovery)



### Unknown



- Whether Scott wants `ENABLE_RECRUITING` default flipped to False for demos

- Whether share links should require login later (MVP matches ungated playbook share)





## Try on :8080



| Page | URL |

| --- | --- |

| List | http://127.0.0.1:8080/recruiting |

| New profile | http://127.0.0.1:8080/recruiting/new |

| Settings flag | http://127.0.0.1:8080/settings (Recruiting checkbox) |

| Public share | http://127.0.0.1:8080/recruiting/share/&lt;token&gt; (after Share link) |

| Print | http://127.0.0.1:8080/recruiting/share/&lt;token&gt;/print |





## Out of scope (deferred)



College CRM inbox, OAuth, email blast, NIL, payments, `schema.sql` edits.





## Prior completed (reference)



- Backup / retention / career discovery (inventory only; Career not implemented)

- Playbook wipe + Fast Scout re-import; header Option grouping

