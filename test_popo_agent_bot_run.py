import hashlib
import json
from pathlib import Path

import pytest

from multi_agent_tcp import popo_agent_bot_run as popo


def _reset_pending_files() -> None:
    with popo._pending_file_lock:
        popo._pending_file_cache.clear()


def _callback_signature(token: str, timestamp: str = "1", nonce: str = "2") -> str:
    sign_text = "".join(
        value
        for _, value in sorted(
            {"token": token, "timestamp": timestamp, "nonce": nonce}.items(),
            key=lambda item: item[1],
        )
    )
    return hashlib.sha256(sign_text.encode()).hexdigest()


def test_popo_callback_empty_blueprint_reply_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []

    monkeypatch.setattr(popo, "send_message", lambda receiver, message, robot_config: sent.append((receiver, message)))
    monkeypatch.setattr(popo, "call_blueprint", lambda *args, **kwargs: "")

    popo.handle_and_reply("popo-target", "hello", robot_config={"robot_app_key": "robot-key"})

    assert sent == []


def test_popo_blueprint_queued_message_has_no_immediate_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_blueprint_request(command: str, args: dict, **kwargs):
        assert command == "blueprint.sessions.message"
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


def test_popo_blueprint_running_timeout_has_no_status_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[str] = []

    def fake_blueprint_request(command: str, args: dict, **kwargs):
        requests.append(command)
        if command == "blueprint.sessions.message":
            return {"ok": True, "sessionKey": "session-1", "runId": "run-1"}
        assert command == "blueprint.status"
        return {"status": {"run": {"status": "running"}}}

    monkeypatch.setattr(popo, "blueprint_request", fake_blueprint_request)
    monkeypatch.setattr(popo, "BLUEPRINT_REPLY_TIMEOUT", 0.01)
    monkeypatch.setattr(popo, "BLUEPRINT_POLL_INTERVAL", 0.001)

    reply = popo.call_blueprint(
        "hello",
        robot_app_key="robot-key",
        sender="user",
        popo_session_id="user",
        reply_to="user",
        session_type="1",
    )

    assert reply == ""
    assert "blueprint.status" in requests


def test_popo_extracts_private_image_attachment_from_url(monkeypatch: pytest.MonkeyPatch) -> None:
    downloaded: list[dict] = []

    def fake_download(candidate: dict, robot_config: dict) -> dict:
        downloaded.append(candidate)
        return {
            "kind": "image",
            "path": r"F:\tmp\popo.png",
            "name": "popo.png",
            "mime": "image/png",
            "size": 12,
            "sourceKey": candidate["sourceKey"],
            "unresolved": False,
        }

    monkeypatch.setattr(popo, "_download_popo_attachment", fake_download)

    message, attachments = popo.extract_popo_message_and_attachments(
        {
            "from": "user-1",
            "notify": "",
            "sessionId": "session-1",
            "msgType": 2,
            "imageUrl": "https://example.invalid/popo.png",
        },
        {"robot_app_key": "robot-key"},
    )

    assert message == "[POPO attachment: image]"
    assert downloaded[0]["url"] == "https://example.invalid/popo.png"
    assert downloaded[0]["sourceKey"] == "imageUrl"
    assert attachments == [
        {
            "kind": "image",
            "path": r"F:\tmp\popo.png",
            "name": "popo.png",
            "mime": "image/png",
            "size": 12,
            "sourceKey": "imageUrl",
            "unresolved": False,
        }
    ]


def test_popo_call_blueprint_forwards_attachments(monkeypatch: pytest.MonkeyPatch) -> None:
    attachments = [{"kind": "image", "path": r"F:\tmp\popo.png", "name": "popo.png", "mime": "image/png"}]

    def fake_blueprint_request(command: str, args: dict, **kwargs):
        assert command == "blueprint.sessions.message"
        assert args["attachments"] == attachments
        return {"queued": True, "sessionKey": "session-1", "runId": "run-1"}

    monkeypatch.setattr(popo, "blueprint_request", fake_blueprint_request)

    reply = popo.call_blueprint(
        "[POPO attachment: image]",
        robot_app_key="robot-key",
        sender="user",
        popo_session_id="user",
        reply_to="user",
        session_type="1",
        attachments=attachments,
    )

    assert reply == ""


def test_popo_downloads_file_attachment_by_file_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(popo, "POPO_ATTACHMENTS_DIR", tmp_path)
    monkeypatch.setattr(popo, "get_access_token", lambda robot_config: "token")
    calls: list[dict] = []

    class FakeDownloadUrlResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def json(self) -> dict:
            return {"errcode": 0, "errmsg": "ok", "data": {"downloadUrl": "https://example.invalid/file-by-id"}}

    class FakeFileResponse:
        status_code = 200
        headers = {"Content-Type": "application/octet-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, chunk_size: int):
            yield b"graph-bytes"

    def fake_get(url: str, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        if url.endswith("/open-apis/robots/v1/im/file/file-1/download"):
            assert kwargs["headers"] == {"Open-Access-Token": "token"}
            return FakeDownloadUrlResponse()
        assert url == "https://example.invalid/file-by-id"
        assert kwargs["stream"] is True
        return FakeFileResponse()

    monkeypatch.setattr(popo.requests, "get", fake_get)

    attachment = popo._download_popo_attachment(
        {
            "kind": "file",
            "url": "",
            "id": "file-1",
            "name": "panpan_common.graph",
            "mime": "",
            "sourceKey": "fileInfo",
        },
        {"robot_app_key": "robot-key"},
    )

    path = Path(attachment["path"])
    assert path.is_absolute()
    assert path.name.endswith("_panpan_common.graph")
    assert path.read_bytes() == b"graph-bytes"
    assert attachment["unresolved"] is False
    assert attachment["size"] == len(b"graph-bytes")
    assert attachment["kind"] == "file"
    assert [item["url"] for item in calls] == [
        "https://open.popo.netease.com/open-apis/robots/v1/im/file/file-1/download",
        "https://example.invalid/file-by-id",
    ]


def test_popo_file_only_message_is_cached_until_next_text() -> None:
    _reset_pending_files()
    file_attachment = {"kind": "file", "path": r"F:\tmp\sheet.xlsx", "name": "sheet.xlsx"}

    should_dispatch, delivery = popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify="sheet.xlsx",
        raw_notify="sheet.xlsx",
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[file_attachment],
    )

    assert should_dispatch is False
    assert delivery == []

    should_dispatch, delivery = popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify="please process it",
        raw_notify="please process it",
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[],
    )

    assert should_dispatch is True
    assert delivery == [file_attachment]
    with popo._pending_file_lock:
        assert popo._pending_file_cache == {}


def test_popo_text_with_file_attachment_dispatches_immediately() -> None:
    _reset_pending_files()
    file_attachment = {"kind": "file", "path": r"F:\tmp\sheet.xlsx", "name": "sheet.xlsx"}

    should_dispatch, delivery = popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify="please process sheet.xlsx",
        raw_notify="please process sheet.xlsx",
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[file_attachment],
    )

    assert should_dispatch is True
    assert delivery == [file_attachment]
    with popo._pending_file_lock:
        assert popo._pending_file_cache == {}


def test_popo_callback_file_only_waits_for_next_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_pending_files()
    popo._event_cache.clear()
    aes_key = "0123456789abcdef0123456789abcdef"
    token = "callback-token"
    file_attachment = {"kind": "file", "path": r"F:\tmp\sheet.xlsx", "name": "sheet.xlsx"}
    captured: list[dict] = []

    monkeypatch.setattr(
        popo,
        "load_popo_config",
        lambda robot_app_key: {
            "robot_app_key": robot_app_key or "robot-1",
            "robot_app_secret": "secret",
            "callback_token": token,
            "aes_key": aes_key,
        },
    )

    def fake_extract(event_data: dict, robot_config: dict) -> tuple[str, list[dict]]:
        if event_data.get("fileInfo"):
            return str(event_data["notify"]), [file_attachment]
        return str(event_data["notify"]), []

    monkeypatch.setattr(popo, "extract_popo_message_and_attachments", fake_extract)
    monkeypatch.setattr(
        popo,
        "_start_handler_thread",
        lambda robot_config, reply_to, notify, sender, popo_session_id, popo_group_id="", session_type="", attachments=None: captured.append(
            {
                "notify": notify,
                "attachments": attachments or [],
                "replyTo": reply_to,
                "sender": sender,
                "sessionId": popo_session_id,
            }
        ),
    )

    def post_event(uuid: str, notify: str, *, file_info: bool = False) -> None:
        event_data = {
            "uuid": uuid,
            "from": "user-1",
            "notify": notify,
            "sessionId": "session-1",
            "sessionType": 1,
        }
        if file_info:
            event_data["fileInfo"] = {"fileId": "file-1", "name": "sheet.xlsx"}
        payload = {
            "eventType": "IM_P2P_TO_ROBOT_MSG",
            "eventData": event_data,
        }
        encrypted = popo.AESCipher(aes_key).aes_cbc_encrypt(json.dumps(payload))
        response = popo.app.test_client().post(
            f"/popo/callback/robot-1?timestamp=1&nonce=2&signature={_callback_signature(token)}",
            json={"encrypt": encrypted},
        )
        assert response.status_code == 200

    post_event("file-event", "sheet.xlsx", file_info=True)
    assert captured == []

    post_event("text-event", "process this file")
    assert captured == [
        {
            "notify": "process this file",
            "attachments": [file_attachment],
            "replyTo": "user-1",
            "sender": "user-1",
            "sessionId": "session-1",
        }
    ]


def test_popo_multiple_file_only_messages_accumulate_in_order() -> None:
    _reset_pending_files()
    first = {"kind": "file", "path": r"F:\tmp\first.txt", "name": "first.txt"}
    second = {"kind": "file", "path": r"F:\tmp\second.txt", "name": "second.txt"}

    for attachment in (first, second):
        should_dispatch, delivery = popo._prepare_popo_callback_delivery(
            robot_config={"robot_app_key": "robot-key"},
            reply_to="user",
            notify=attachment["name"],
            raw_notify=attachment["name"],
            sender="user",
            popo_session_id="session-1",
            session_type="1",
            attachments=[attachment],
        )
        assert should_dispatch is False
        assert delivery == []

    should_dispatch, delivery = popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify="use both files",
        raw_notify="use both files",
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[],
    )

    assert should_dispatch is True
    assert delivery == [first, second]


def test_popo_image_attachment_still_dispatches_immediately() -> None:
    _reset_pending_files()
    image_attachment = {"kind": "image", "path": r"F:\tmp\preview.png", "name": "preview.png"}

    should_dispatch, delivery = popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify="[POPO attachment: image]",
        raw_notify="",
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[image_attachment],
    )

    assert should_dispatch is True
    assert delivery == [image_attachment]
    with popo._pending_file_lock:
        assert popo._pending_file_cache == {}


@pytest.mark.parametrize("command", ["/help", "/excel-log 2026 1 1 0 0 0 0-2026 1 1 1 0 0 0"])
def test_popo_readonly_commands_do_not_consume_pending_files(command: str) -> None:
    _reset_pending_files()
    file_attachment = {"kind": "file", "path": r"F:\tmp\sheet.xlsx", "name": "sheet.xlsx"}

    popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify="sheet.xlsx",
        raw_notify="sheet.xlsx",
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[file_attachment],
    )
    should_dispatch, delivery = popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify=command,
        raw_notify=command,
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[],
    )

    assert should_dispatch is True
    assert delivery == []

    should_dispatch, delivery = popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify="now process the file",
        raw_notify="now process the file",
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[],
    )

    assert should_dispatch is True
    assert delivery == [file_attachment]


@pytest.mark.parametrize("command", ["/new", "/stop"])
def test_popo_reset_commands_clear_pending_files(command: str) -> None:
    _reset_pending_files()
    file_attachment = {"kind": "file", "path": r"F:\tmp\sheet.xlsx", "name": "sheet.xlsx"}

    popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify="sheet.xlsx",
        raw_notify="sheet.xlsx",
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[file_attachment],
    )
    should_dispatch, delivery = popo._prepare_popo_callback_delivery(
        robot_config={"robot_app_key": "robot-key"},
        reply_to="user",
        notify=command,
        raw_notify=command,
        sender="user",
        popo_session_id="session-1",
        session_type="1",
        attachments=[],
    )

    assert should_dispatch is True
    assert delivery == []
    with popo._pending_file_lock:
        assert popo._pending_file_cache == {}


def test_popo_blueprint_excel_log_command_returns_direct_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_blueprint_request(command: str, args: dict, **kwargs):
        assert command == "blueprint.sessions.message"
        assert args["message"].startswith("/excel-log")
        return {"ok": True, "excelLog": True, "sessionKey": "session-1", "message": "excel logs"}

    monkeypatch.setattr(popo, "blueprint_request", fake_blueprint_request)

    reply = popo.call_blueprint(
        "/excel-log 2026 6 11 12 0 0 0-2026 6 11 12 30 0 0",
        robot_app_key="robot-key",
        sender="user",
        popo_session_id="user",
        reply_to="user",
        session_type="1",
    )

    assert reply == "excel logs"


def test_popo_send_message_splits_long_text(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    class FakeResponse:
        def json(self) -> dict:
            return {"errcode": 0, "errmsg": "ok"}

    def fake_post(url: str, json: dict, headers: dict, timeout: int) -> FakeResponse:
        sent.append(json["message"]["content"])
        return FakeResponse()

    monkeypatch.setattr(popo, "get_access_token", lambda robot_config: "token")
    monkeypatch.setattr(popo.requests, "post", fake_post)

    popo.send_message("user", "\n".join(f"line {index}" for index in range(600)), {"robot_app_key": "robot-key"})

    assert len(sent) > 1
    assert all(len(message) <= popo.POPO_TEXT_CHUNK_LIMIT + 16 for message in sent)
    assert sent[0].startswith("[1/")


def test_popo_blueprint_help_command_returns_direct_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_blueprint_request(command: str, args: dict, **kwargs):
        assert command == "blueprint.sessions.message"
        assert args["message"] == "/help"
        return {
            "ok": True,
            "help": True,
            "commands": [{"command": "/help"}, {"command": "/new"}, {"command": "/stop"}],
            "message": "可用指令（后端直接处理，不会发送给 Agent）：\n/help - 查看可用指令列表。\n/new - 开启新会话。\n/stop - 结束当前会话。",
        }

    monkeypatch.setattr(popo, "blueprint_request", fake_blueprint_request)

    reply = popo.call_blueprint(
        "/help",
        robot_app_key="robot-key",
        sender="user",
        popo_session_id="user",
        reply_to="user",
        session_type="1",
    )

    assert "可用指令" in reply
    assert "/new" in reply
    assert "/stop" in reply


def test_popo_blueprint_new_session_command_confirms_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_blueprint_request(command: str, args: dict, **kwargs):
        assert command == "blueprint.sessions.message"
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


def test_popo_blueprint_stop_session_command_confirms_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_blueprint_request(command: str, args: dict, **kwargs):
        assert command == "blueprint.sessions.message"
        assert args["message"] == "/stop"
        return {"ok": True, "stopped": True, "sessionKey": "session-1", "message": "已结束当前会话"}

    monkeypatch.setattr(popo, "blueprint_request", fake_blueprint_request)

    reply = popo.call_blueprint(
        "/stop",
        robot_app_key="robot-key",
        sender="user",
        popo_session_id="user",
        reply_to="user",
        session_type="1",
    )

    assert reply == "已结束当前会话"
