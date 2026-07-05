"""Stage 9D transfer bundle completeness checks."""

import os
import subprocess
import tarfile
import tempfile

import pytest

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
    "templates/film_tool.html",
    "scripts/build_transfer_bundle.sh",
    "scripts/docker_production_smoke.sh",
    "scripts/smoke_test.sh",
    "scripts/audit_secrets.py",
    "tests/conftest.py",
    "docs/HERMES_LINUX_PARITY.md",
    "docs/DOCKER_PRODUCTION_SMOKE.md",
)


def _build_bundle(tmpdir):
    stamp = "pytest-transfer"
    result = subprocess.run(
        ["bash", "scripts/build_transfer_bundle.sh", stamp],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    archive = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "transfer-bundles",
        f"liberty-basketball-analysis-transfer-{stamp}.tar.gz",
    )
    assert os.path.isfile(archive), archive
    return archive


@pytest.mark.parametrize("rel_path", REQUIRED_PATHS)
def test_transfer_bundle_includes_required_paths(rel_path):
    with tempfile.TemporaryDirectory() as tmpdir:
        archive = _build_bundle(tmpdir)
        with tarfile.open(archive, "r:gz") as tar:
            names = set(tar.getnames())
        assert rel_path in names, f"missing {rel_path} in transfer bundle"


def test_transfer_bundle_excludes_benchmark_scripts():
    with tempfile.TemporaryDirectory() as tmpdir:
        archive = _build_bundle(tmpdir)
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
        benchmark_hits = [n for n in names if os.path.basename(n).startswith("benchmark_")]
        assert benchmark_hits == []
