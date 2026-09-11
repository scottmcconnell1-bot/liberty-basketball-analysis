#!/usr/bin/env python3
"""Build a demo/validation database + upload folder with the E2E test data.

    python scripts/seed_e2e_data.py --db /tmp/demo.db --uploads /tmp/demo_uploads
    LIBERTY_DATABASE=/tmp/demo.db LIBERTY_UPLOAD_FOLDER=/tmp/demo_uploads .venv/bin/gunicorn --bind 127.0.0.1:8091 app:app

Drives the application through its own routes (same as tests/e2e), so what you get is exactly
what a coach would have after: seasons, schedule with results, roster, two uploaded videos
(synthetic + a real 12 s film clip when the LFS snippet is hydrated), synthetic detections and
pending AI drafts, a few reviewed events, highlight clips, plays, practices, playlists, a
scouting report, and a confirmed stat book. All names are fictional.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--uploads", required=True)
    ap.add_argument("--no-real-film", action="store_true", help="skip the real 12 s clip even if available")
    args = ap.parse_args(argv)

    os.environ.setdefault("LIBERTY_COACH_PASSWORD", "e2e-coach-pass")  # the coach-portal step logs in with it
    os.environ["LIBERTY_DATABASE"] = str(Path(args.db).resolve())
    os.environ["LIBERTY_UPLOAD_FOLDER"] = str(Path(args.uploads).resolve())
    Path(args.uploads).mkdir(parents=True, exist_ok=True)

    import app as app_module
    from stat_book import paths as sb_paths
    from tests.e2e.conftest import E2E
    from tests.e2e import scenarios

    # confirmed stat books default to <repo>/data/stat_books/confirmed (tracked); keep demo
    # output next to the demo uploads instead of dirtying the working copy
    sb_paths.CONFIRMED_ROOT = Path(args.uploads).resolve() / "stat_books_confirmed"
    sb_paths.CONFIRMED_ROOT.mkdir(parents=True, exist_ok=True)

    app_module.app.config.update({"TESTING": True, "DATABASE": os.environ["LIBERTY_DATABASE"],
                                  "UPLOAD_FOLDER": os.environ["LIBERTY_UPLOAD_FOLDER"]})
    with app_module.app.app_context():
        app_module.init_db()
    import blueprints.ai as ai_mod
    ai_mod.start_analysis_subprocess = lambda game_id, video_path: None  # synthetic data instead
    e = E2E(app_module.app.test_client(), os.environ["LIBERTY_DATABASE"], os.environ["LIBERTY_UPLOAD_FOLDER"],
            live=False, app=app_module.app)
    e.real_analysis = False
    scenarios.seed_everything(e, real_film=not args.no_real_film)
    print(f"seeded: db={args.db} uploads={args.uploads}")
    print("state:", {k: v for k, v in e.state.items() if not k.startswith("_")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
