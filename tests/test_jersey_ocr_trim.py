"""Tests for jersey OCR target limiting."""


def test_trim_ocr_targets_balances_clusters():
    from jersey_ocr import _trim_ocr_targets

    targets = []
    for cluster_id in range(4):
        for i in range(10):
            targets.append({"cluster_id": cluster_id, "detection_id": cluster_id * 10 + i})
    trimmed = _trim_ocr_targets(targets, 8)
    assert len(trimmed) == 8
    clusters = {item["cluster_id"] for item in trimmed}
    assert len(clusters) == 4
