import pytest
from mentor_course_builder.jsonparse import parse_model_json

TEXT = r"Tính $\frac{1}{2} + \beta$ và $\theta \neq \nu$, \times"


def test_plain():
    assert parse_model_json('{"readable": true, "text": "x"}') == {"readable": True, "text": "x"}


def test_code_fence_and_chatter():
    raw = 'Here you go:\n```json\n{"readable": false, "readable_fraction": 0.4}\n```\nHope it helps'
    assert parse_model_json(raw)["readable_fraction"] == 0.4


def test_unterminated_fence():
    assert parse_model_json('```json\n{"a": 1}')["a"] == 1


def test_unescaped_latex_backslashes_survive():
    raw = '{"readable": true, "text": "' + TEXT + '"}'
    assert parse_model_json(raw)["text"] == TEXT  # \frac \beta \theta \neq \nu \times not turned into escapes


def test_properly_escaped_latex():
    raw = '{"text": "' + TEXT.replace("\\", "\\\\") + '"}'
    assert parse_model_json(raw)["text"] == TEXT


def test_real_newlines_and_escaped_newlines():
    assert parse_model_json('{"text": "a\\nb"}')["text"] == "a\nb"
    assert parse_model_json('{"text": "a\nb"}')["text"] == "a\nb"  # raw newline inside string
    assert parse_model_json('{"text": "x\\nNext"}')["text"] == "x\nNext"


def test_trailing_comma():
    assert parse_model_json('{"a": 1,}') == {"a": 1}


def test_truncated_output_salvaged():
    d = parse_model_json('{"readable": true, "readable_fraction": 0.9, "reason_vi": "", "text": "Dòng một\\nDòng hai')
    assert d["readable"] is True and d["text"].startswith("Dòng một")


def test_no_json_raises():
    with pytest.raises(ValueError):
        parse_model_json("I cannot read this image")


def test_regex_salvage_does_not_crash_on_unparsable_json():
    # LaTeX-style backslashes + a truncated object used to reach a malformed regex (re.error: unterminated character set)
    from mentor_course_builder.jsonparse import parse_model_json
    raw = '{"readable": true, "reason_vi": "ok \theta", "text": "a \frac{1}{2} b'
    out = parse_model_json(raw)
    assert out["readable"] is True
    with pytest.raises(ValueError):
        parse_model_json('{"title": "x" "chapters": [oops')
