from __future__ import annotations

import pytest

from app.cli.investigation.payload import load_payload
from app.cli.support.constants import SAMPLE_ALERT_OPTIONS


def test_load_payload_tty_guided_menu_template_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.cli.investigation.payload.sys.stdin.isatty", lambda: True)
    answers = iter(["2"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    payload = load_payload(input_path=None, input_json=None, interactive=False)

    assert payload["alert_source"] == "generic"
    assert payload["alert_name"]


def test_load_payload_tty_guided_menu_custom_file_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.cli.investigation.payload.sys.stdin.isatty", lambda: True)
    custom_file_index = str(1 + len(SAMPLE_ALERT_OPTIONS) + 1)
    answers = iter([custom_file_index, "alerts/custom.json"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(
        "app.cli.investigation.payload.load_file",
        lambda path: {"loaded_from": path},
    )

    payload = load_payload(input_path=None, input_json=None, interactive=False)

    assert payload == {"loaded_from": "alerts/custom.json"}


def test_load_payload_without_tty_uses_stdin_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.cli.investigation.payload.sys.stdin.isatty", lambda: False)
    monkeypatch.setattr(
        "app.cli.investigation.payload.load_stdin",
        lambda: {"alert_name": "from-stdin"},
    )

    payload = load_payload(input_path=None, input_json=None, interactive=False)

    assert payload == {"alert_name": "from-stdin"}


def test_load_payload_tty_guided_menu_cancel_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.cli.investigation.payload.sys.stdin.isatty", lambda: True)
    answers = iter(["10"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    with pytest.raises(SystemExit) as exc_info:
        load_payload(input_path=None, input_json=None, interactive=False)

    assert exc_info.value.code == 0
