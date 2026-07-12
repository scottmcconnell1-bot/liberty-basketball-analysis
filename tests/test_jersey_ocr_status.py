"""Tests for lightweight OCR engine availability checks."""


def test_jersey_ocr_engine_status_does_not_load_reader(monkeypatch):
    from jersey_ocr import jersey_ocr_engine_status

    reader_calls = []

    def fake_reader(*_args, **_kwargs):
        reader_calls.append(1)
        raise AssertionError("easyocr.Reader should not load during status check")

    fake_easyocr = type("EasyOCR", (), {"Reader": staticmethod(fake_reader)})()
    monkeypatch.setitem(__import__("sys").modules, "easyocr", fake_easyocr)
    monkeypatch.setattr("helpers.module_available", lambda name: name == "easyocr")

    status = jersey_ocr_engine_status()
    assert status["easyocr"] is True
    assert status["easyocr_loaded"] is False
    assert reader_calls == []
