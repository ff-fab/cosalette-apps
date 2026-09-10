from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_render_adr_module():
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "render_adr.py"
    spec = importlib.util.spec_from_file_location("render_adr", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_new_payload() -> dict:
    return {
        "type": "new",
        "title": "Test ADR",
        "date": "2026-04-10",
        "status": "Proposed",
        "impact": "low",
        "context": "Context",
        "decision": "Decision",
        "decision_drivers": ["driver-1", "driver-2", "driver-3"],
        "considered_options": [
            {
                "name": "Option A",
                "description": "Desc A",
                "advantages": ["Adv A"],
                "disadvantages": ["Dis A"],
                "chosen": True,
            },
            {
                "name": "Option B",
                "description": "Desc B",
                "advantages": ["Adv B"],
                "disadvantages": ["Dis B"],
                "chosen": False,
            },
        ],
        "consequences_positive": ["Pos"],
        "consequences_negative": ["Neg"],
        "frontmatter": {"tags": ["architecture"]},
    }


def test_validate_new_rejects_malformed_option() -> None:
    module = _load_render_adr_module()
    payload = _valid_new_payload()
    payload["considered_options"][0].pop("description")
    try:
        module.validate(payload)
    except ValueError as exc:
        assert "'description'" in str(exc) and "considered_options/0" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing option description")


def test_validate_new_rejects_invalid_matrix_score_type() -> None:
    module = _load_render_adr_module()
    payload = _valid_new_payload()
    payload["impact"] = "moderate"
    payload["decision_matrix"] = [
        {
            "criterion": "Maintainability",
            "scores": {"Option A": "5", "Option B": 4},
        },
        {
            "criterion": "Complexity",
            "scores": {"Option A": 4, "Option B": 3},
        },
        {
            "criterion": "Adoption",
            "scores": {"Option A": 4, "Option B": 4},
        },
    ]

    try:
        module.validate(payload)
    except ValueError as exc:
        assert "decision_matrix/0/scores/Option A" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid matrix score type")


def test_find_adr_file_raises_on_ambiguous_match(tmp_path: Path) -> None:
    module = _load_render_adr_module()
    (tmp_path / "ADR-006-foo.md").write_text("", encoding="utf-8")
    (tmp_path / "ADR-006-bar.md").write_text("", encoding="utf-8")

    try:
        module.find_adr_file(tmp_path, "ADR-006")
    except ValueError as exc:
        assert "Multiple files found" in str(exc)
    else:
        raise AssertionError("Expected ValueError for ambiguous ADR match")


def _valid_amendment_payload() -> dict:
    return {
        "type": "amendment",
        "target_adr": "ADR-008",
        "amendment_scope": "minor",
        "amendment_date": "2026-09-10",
        "amendment_content": {"notes": ["First note.", "Second note."]},
    }


def test_schema_validate_rejects_string_where_array_expected() -> None:
    """A string in place of an array of strings is caught by schema validation.

    Regression for cap-ak7: the hand-rolled pass never typed
    ``amendment_content.notes``, so a plain string validated and the renderer
    iterated it character by character, splicing ~3000 one-character admonition
    blocks into the target ADR while exiting 0.
    """
    module = _load_render_adr_module()
    payload = _valid_amendment_payload()
    payload["amendment_content"]["notes"] = "a plain string, not a list"
    try:
        module.validate(payload)
    except ValueError as exc:
        message = str(exc)
        assert "amendment_content/notes" in message
        assert "array" in message
    else:
        raise AssertionError("Expected ValueError for notes given as a string")


def test_schema_validate_accepts_valid_payloads() -> None:
    """Schema validation is additive: previously valid inputs still pass."""
    module = _load_render_adr_module()
    module.validate(_valid_new_payload())
    module.validate(_valid_amendment_payload())
