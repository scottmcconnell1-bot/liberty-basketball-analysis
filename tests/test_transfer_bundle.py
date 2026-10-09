"""Stage 9D transfer bundle completeness checks."""

import os
import subprocess
import tarfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))

REQUIRED_PATHS = (
    "app.py",
    "helpers.py",
    "module_entitlements.py",
    "player_development.py",
    "player_minutes.py",
    "nfhs.py",
    "secrets_audit.py",
    "schema.sql",
    ".env.example",
    "blueprints/core.py",
    "stat_book/paths.py",
    "static/js/film-tool.js",
    "templates/film_tool.html",
    "data/stat_books/templates/liberty_spiral_scorebook/layout.json",
    "scripts/build_transfer_bundle.sh",
    "scripts/docker_production_smoke.sh",
    "scripts/smoke_test.sh",
    "scripts/audit_secrets.py",
    "tests/conftest.py",
    "docs/HERMES_LINUX_PARITY.md",
    "docs/DOCKER_PRODUCTION_SMOKE.md",
)


@pytest.fixture(scope="module")
def bundle_names(tmp_path_factory):
    """Build the bundle ONCE per module, into a temp dir (never the tracked repo tree).

    LIBERTY_TRANSFER_SKIP_MODELS keeps the ~750 MB of hydrated model weights out of
    the test build; a real transfer includes them.
    """
    out_dir = tmp_path_factory.mktemp("transfer-bundles")
    stamp = "pytest-transfer"
    # Snapshot the legacy in-repo location so we can prove the build never touched it.
    stray = os.path.join(REPO_ROOT, "transfer-bundles", f"liberty-basketball-analysis-transfer-{stamp}.tar.gz")
    stray_mtime_before = os.path.getmtime(stray) if os.path.exists(stray) else None
    # bash on this PC is WSL. WSL drops Windows env vars unless they are named
    # in WSLENV. /p turns the Windows temp path into a /mnt/c path.
    wslenv_parts = [p for p in os.environ.get("WSLENV", "").split(":") if p]
    wslenv_names = {p.split("/")[0] for p in wslenv_parts}
    for entry in (
        "LIBERTY_TRANSFER_OUT_DIR/p",
        "LIBERTY_TRANSFER_SKIP_MODELS",
        "LIBERTY_TRANSFER_SKIP_BULK",
    ):
        if entry.split("/")[0] not in wslenv_names:
            wslenv_parts.append(entry)
    env = dict(
        os.environ,
        LIBERTY_TRANSFER_OUT_DIR=str(out_dir),
        LIBERTY_TRANSFER_SKIP_MODELS="1",
        LIBERTY_TRANSFER_SKIP_BULK="1",
        WSLENV=":".join(wslenv_parts),
    )
    result = subprocess.run(
        ["bash", "scripts/build_transfer_bundle.sh", stamp],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    archive = out_dir / f"liberty-basketball-analysis-transfer-{stamp}.tar.gz"
    assert archive.is_file(), archive
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    stray_mtime_after = os.path.getmtime(stray) if os.path.exists(stray) else None
    return {"names": names, "stray_unchanged": stray_mtime_before == stray_mtime_after}


@pytest.mark.parametrize("rel_path", REQUIRED_PATHS)
def test_transfer_bundle_includes_required_paths(bundle_names, rel_path):
    assert rel_path in set(bundle_names["names"]), f"missing {rel_path} in transfer bundle"


def test_transfer_bundle_excludes_benchmark_scripts(bundle_names):
    benchmark_hits = [n for n in bundle_names["names"] if os.path.basename(n).startswith("benchmark_")]
    assert benchmark_hits == []


def test_transfer_bundle_skips_bulk_files(bundle_names):
    names = set(bundle_names["names"])
    assert "film_analysis.db" not in names
    assert not any(n == "uploads" or n.startswith("uploads/") for n in names)


def test_transfer_bundle_does_not_write_into_repo(bundle_names):
    # A stale bundle may exist on disk from older runs (now gitignored); the build
    # must not create or overwrite anything under the repo's transfer-bundles/.
    assert bundle_names["stray_unchanged"], "test build must not write into the repo tree"
