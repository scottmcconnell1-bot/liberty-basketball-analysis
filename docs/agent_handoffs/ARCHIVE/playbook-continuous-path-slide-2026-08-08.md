# Archive: playbook continuous path slide

Archived: 2026-08-08
Superseded by: playbook-play-all-scrub-abort (Play All dead — scrub abort)

Prior slice shipped continuous rAF slide via animateOnePath + playbarSuppressScrub (setTimeout 0).
That suppress window was too short — deferred scrub input aborted Play All (see ACTIVE.md).
