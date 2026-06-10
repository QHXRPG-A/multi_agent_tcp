import pytest

from multi_agent_tcp import popo_agent_bot_run as popo


def test_popo_callback_notice_is_thinking_and_empty_blueprint_reply_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []

    monkeypatch.setattr(popo, "send_message", lambda receiver, message, robot_config: sent.append((receiver, message)))
    monkeypatch.setattr(popo, "call_blueprint", lambda *args, **kwargs: "")

    popo.handle_and_reply("popo-target", "hello", robot_config={"robot_app_key": "robot-key"})

    assert sent == [("popo-target", "思考中....")]


def test_popo_blueprint_queued_message_has_no_slot_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_blueprint_request(command: str, args: dict, **kwargs):
        assert command == "blueprint.slots.message"
        return {"queued": True, "sessionKey": "session-1", "runId": "run-1"}

    monkeypatch.setattr(popo, "blueprint_request", fake_blueprint_request)

    reply = popo.call_blueprint(
        "hello",
        robot_app_key="robot-key",
        sender="user",
        popo_session_id="user",
        reply_to="user",
        session_type="1",
    )

    assert reply == ""


def test_popo_blueprint_new_session_command_confirms_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_blueprint_request(command: str, args: dict, **kwargs):
        assert command == "blueprint.slots.message"
        assert args["message"] == "/new"
        return {"ok": True, "cleared": True, "sessionKey": "session-1"}

    monkeypatch.setattr(popo, "blueprint_request", fake_blueprint_request)

    reply = popo.call_blueprint(
        "/new",
        robot_app_key="robot-key",
        sender="user",
        popo_session_id="user",
        reply_to="user",
        session_type="1",
    )

    assert reply == "已开启新会话"
