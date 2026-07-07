def test_materialize_lfs_models_copies_object(tmp_path, monkeypatch):
    import scripts.materialize_lfs_models as materialize

    root = tmp_path / "repo"
    models = root / "models"
    lfs_dir = root / ".git" / "lfs" / "objects" / "ab" / "cd"
    models.mkdir(parents=True)
    lfs_dir.mkdir(parents=True)

    oid = "abcd" * 16
    weights = b"PYTORCH" + b"\0" * 12000
    (lfs_dir / oid).write_bytes(weights)

    pointer = models / "ball_detector.pt"
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{oid}\n"
        f"size {len(weights)}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(materialize, "ROOT", root)
    ok, message = materialize.materialize_model(pointer, fetch=False)
    assert ok is True
    assert pointer.read_bytes() == weights
    assert "materialized" in message
