"""Tests for human-readable analysis failure messages."""


def test_format_exception_message_uses_headline_not_traceback_tail():
    from helpers import format_exception_message

    try:
        raise ValueError("YOLO model missing")
    except ValueError as exc:
        message = format_exception_message(exc)

    assert "ValueError: YOLO model missing" in message
    assert "_mark_failed" not in message


def test_analysis_log_error_message_extracts_exception_line():
    from helpers import _analysis_log_error_message

    content = (
        "Traceback (most recent call last):\n"
        '  File "analysis_launcher.py", line 71, in main\n'
        "    runpy.run_path('ai_analyzer.py', run_name='__main__')\n"
        "ModuleNotFoundError: No module named 'easyocr'\n"
        "    _mark_failed(db_path, game_id, f\"{exc}\")\n"
    )
    message = _analysis_log_error_message(content)
    assert message == "ModuleNotFoundError: No module named 'easyocr'"
