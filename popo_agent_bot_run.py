# -*- coding: utf-8 -*-
"""POPO intelligent robot service backed by GuLiCode Blueprint sessions."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests
from Crypto.Cipher import AES
from flask import Flask, jsonify, make_response, request


DEFAULT_ROBOT_APP_KEY = os.environ.get("POPO_APP_KEY", "").strip()
POPO_API_BASE = "https://open.popo.netease.com"

BLUEPRINT_PROJECT_DIR = os.environ.get("POPO_BLUEPRINT_PROJECT_DIR") or os.getcwd()
BLUEPRINT_REPLY_TIMEOUT = int(os.environ.get("POPO_BLUEPRINT_REPLY_TIMEOUT", "300"))
BLUEPRINT_POLL_INTERVAL = float(os.environ.get("POPO_BLUEPRINT_POLL_INTERVAL", "2"))

REPO_ROOT = Path(__file__).resolve().parent
PLUGIN_ROOT = Path(os.environ.get("GULICODE_BP_PLUGIN_ROOT") or REPO_ROOT / "plugins" / "gulicode-bp").resolve()
RUNTIME_HOME = Path(os.environ.get("GULICODE_BP_RUNTIME_HOME") or PLUGIN_ROOT / ".runtime").resolve()
RUNTIME_DATA_DIR = Path(os.environ.get("GULICODE_BP_DATA_DIR") or RUNTIME_HOME / "state").resolve()
MCP_DIR = PLUGIN_ROOT / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from gulicode_bp_singleton import SingletonServiceError, ensure_singleton_service, service_rpc  # noqa: E402


app = Flask(__name__)

_service_lock = threading.Lock()
_config_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_token_cache: dict[str, dict[str, Any]] = {}
_config_lock = threading.Lock()
_token_lock = threading.Lock()


def _runtime_python() -> Path:
    if sys.platform == "win32":
        return RUNTIME_HOME / "venv" / "Scripts" / "python.exe"
    return RUNTIME_HOME / "venv" / "bin" / "python"


def ensure_blueprint_service() -> None:
    with _service_lock:
        ensure_singleton_service(
            PLUGIN_ROOT,
            _runtime_python(),
            RUNTIME_HOME,
            RUNTIME_DATA_DIR,
        )


def blueprint_request(
    command: str,
    args: dict[str, Any] | None = None,
    *,
    request_kind: str = "read",
    timeout: float = 60,
) -> dict[str, Any]:
    ensure_blueprint_service()
    return service_rpc(
        RUNTIME_DATA_DIR,
        command,
        args or {},
        request_kind=request_kind,
        timeout=timeout,
    )


def load_popo_config(robot_app_key: str) -> dict[str, Any]:
    app_key = str(robot_app_key or "").strip()
    if not app_key:
        raise SingletonServiceError("BLUEPRINT_POPO_ROBOT_REQUIRED", "robot_app_key is required", status=400)
    now = time.time()
    with _config_lock:
        cached = _config_cache.get(app_key)
        if cached and now - cached[0] < 30:
            return dict(cached[1])
    response = blueprint_request(
        "blueprint.popo.config",
        {"projectDir": BLUEPRINT_PROJECT_DIR, "robotAppKey": app_key},
        request_kind="internal",
        timeout=30,
    )
    entry = response.get("popoEntry")
    if not isinstance(entry, dict):
        raise SingletonServiceError("BLUEPRINT_POPO_ENTRY_REQUIRED", "POPO entry is missing", status=400)
    config = {
        "robot_app_key": str(entry.get("robot_app_key") or entry.get("robotAppKey") or app_key).strip(),
        "robot_name": str(entry.get("robot_name") or entry.get("robotName") or "").strip(),
        "robot_app_secret": str(entry.get("robot_app_secret") or entry.get("robotAppSecret") or "").strip(),
        "callback_token": str(entry.get("callback_token") or entry.get("callbackToken") or "").strip(),
        "aes_key": str(entry.get("aes_key") or entry.get("aesKey") or "").strip(),
        "blueprint_id": str(response.get("blueprintId") or "").strip(),
        "blueprint_name": str(response.get("blueprintName") or "").strip(),
        "blueprint_structure_id": str(response.get("blueprintStructureId") or "").strip(),
    }
    missing = [key for key in ("robot_app_key", "robot_app_secret", "callback_token", "aes_key") if not config[key]]
    if missing:
        raise SingletonServiceError(
            "BLUEPRINT_POPO_ENTRY_REQUIRED",
            "POPO entry is incomplete: " + ", ".join(missing),
            status=400,
            details={"missing": missing},
        )
    with _config_lock:
        _config_cache[app_key] = (now, dict(config))
    return config


def get_access_token(robot_config: dict[str, Any]):
    app_key = str(robot_config.get("robot_app_key") or "").strip()
    app_secret = str(robot_config.get("robot_app_secret") or "").strip()
    if not app_key or not app_secret:
        return None
    with _token_lock:
        now_ms = int(time.time() * 1000)
        cached = _token_cache.get(app_key) or {}
        if (
            cached.get("access_token")
            and int(cached.get("expired_at") or 0) - now_ms > 300000
        ):
            return cached["access_token"]

        url = f"{POPO_API_BASE}/open-apis/robots/v1/token"
        resp = requests.post(
            url,
            json={
                "appKey": app_key,
                "appSecret": app_secret,
            },
            timeout=10,
        )
        data = resp.json()
        print(f"[TOKEN] response: {json.dumps(data, ensure_ascii=False)}", flush=True)

        if data.get("errcode") == 0 and data.get("data"):
            _token_cache[app_key] = {
                "access_token": data["data"]["accessToken"],
                "expired_at": data["data"]["accessExpiredAt"],
            }
            return _token_cache[app_key]["access_token"]

        print(f"[TOKEN] failed: {data}", flush=True)
        return None


def send_message(receiver, content, robot_config: dict[str, Any]):
    token = get_access_token(robot_config)
    if not token:
        print("[SEND] no access token; send skipped", flush=True)
        return

    url = f"{POPO_API_BASE}/open-apis/robots/v1/im/send-msg"
    payload = {
        "receiver": receiver,
        "msgType": "text",
        "message": {
            "content": content,
        },
    }
    headers = {
        "Content-Type": "application/json",
        "Open-Access-Token": token,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        result = resp.json()
        print(f"[SEND] -> {receiver}: {content[:100]}...", flush=True)
        print(f"[SEND] response: {json.dumps(result, ensure_ascii=False)}", flush=True)
    except Exception as exc:
        print(f"[SEND] exception: {exc}", flush=True)


def _runtime_status_text(status_response: dict[str, Any]) -> str:
    status = status_response.get("status")
    run = status.get("run") if isinstance(status, dict) else {}
    return str(run.get("status") or "").strip().lower() if isinstance(run, dict) else ""


def _runtime_summary_text(status_response: dict[str, Any]) -> str:
    explanation = status_response.get("explanation")
    if not isinstance(explanation, dict):
        return ""
    summary = explanation.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    if isinstance(summary, dict):
        text = summary.get("text") or summary.get("message") or summary.get("final")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def call_blueprint(
    user_message: str,
    *,
    sender: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    print(
        f"[BLUEPRINT] message: {user_message} (sender={sender}, session={popo_session_id}, group={popo_group_id})",
        flush=True,
    )
    try:
        started = blueprint_request(
            "blueprint.slots.message",
            {
                "projectDir": BLUEPRINT_PROJECT_DIR,
                "message": user_message,
                "source": "popo",
                "sourceIdentity": {"robotAppKey": ""},
                "sessionIdentity": {
                    "popoUserId": sender or "",
                    "popoSessionId": popo_session_id or "",
                    "popoGroupId": popo_group_id or "",
                },
            },
            request_kind="internal",
            timeout=90,
        )
    except SingletonServiceError as exc:
        print(f"[BLUEPRINT] service error: {exc}", flush=True)
        return f"蓝图服务处理失败：{exc}"
    except Exception as exc:
        print(f"[BLUEPRINT] exception: {exc}", flush=True)
        return f"蓝图服务处理失败：{exc}"

    session_key = str(started.get("sessionKey") or "")
    run_id = str(started.get("runId") or "")
    if started.get("queued"):
        return f"已发送到蓝图会话队列。\n会话：{session_key}\n运行：{run_id}"
    if not run_id:
        return f"蓝图会话已接收消息。\n会话：{session_key}"

    deadline = time.time() + BLUEPRINT_REPLY_TIMEOUT
    last_status = ""
    while time.time() < deadline:
        try:
            status_response = blueprint_request(
                "blueprint.status",
                {"runId": run_id},
                request_kind="read",
                timeout=30,
            )
        except Exception as exc:
            print(f"[BLUEPRINT] status error: {exc}", flush=True)
            break
        last_status = _runtime_status_text(status_response)
        if last_status in {"completed", "cancelled", "failed"}:
            summary = _runtime_summary_text(status_response)
            if summary:
                return summary
            return f"蓝图运行已结束：{last_status}\n会话：{session_key}\n运行：{run_id}"
        time.sleep(BLUEPRINT_POLL_INTERVAL)
    return f"蓝图会话已启动，仍在运行中。\n会话：{session_key}\n运行：{run_id}\n状态：{last_status or 'starting'}"


def call_blueprint(
    user_message: str,
    *,
    robot_app_key: str,
    sender: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> str:
    print(
        f"[BLUEPRINT] message: {user_message} (robot={robot_app_key}, sender={sender}, session={popo_session_id}, group={popo_group_id})",
        flush=True,
    )
    try:
        started = blueprint_request(
            "blueprint.slots.message",
            {
                "projectDir": BLUEPRINT_PROJECT_DIR,
                "message": user_message,
                "source": "popo",
                "sourceIdentity": {"robotAppKey": robot_app_key},
                "sessionIdentity": {
                    "popoUserId": sender or "",
                    "popoSessionId": popo_session_id or "",
                    "popoGroupId": popo_group_id or "",
                },
            },
            request_kind="internal",
            timeout=90,
        )
    except SingletonServiceError as exc:
        print(f"[BLUEPRINT] service error: {exc}", flush=True)
        code = str(getattr(exc, "code", "") or "")
        if code == "BLUEPRINT_SLOT_NOT_FOUND":
            return "当前没有可用的蓝图运行槽，请先在蓝图面板手动启动运行槽。"
        if code == "BLUEPRINT_SLOT_BUSY":
            return "当前蓝图运行槽都在处理任务，请稍后再试或启动新的运行槽。"
        if code == "BLUEPRINT_POPO_ROBOT_NOT_BOUND":
            return "这个 POPO 机器人还没有绑定到可用的蓝图结构。"
        if code == "BLUEPRINT_POPO_ENTRY_REQUIRED":
            return "蓝图中的 POPO 机器人入口配置不完整，请先在起始 Agent 检查器中补齐。"
        if code == "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT":
            return "这个 POPO 机器人绑定了多个蓝图结构，无法判断要投递到哪个结构池。"
        return f"蓝图服务处理失败：{getattr(exc, 'message', str(exc))}"
    except Exception as exc:
        print(f"[BLUEPRINT] exception: {exc}", flush=True)
        return f"蓝图服务处理失败：{exc}"

    session_key = str(started.get("sessionKey") or "")
    run_id = str(started.get("runId") or "")
    if started.get("queued"):
        return f"已发送到蓝图运行槽。\n会话：{session_key}\n运行：{run_id}"
    if not run_id:
        return f"蓝图会话已接收消息。\n会话：{session_key}"

    deadline = time.time() + BLUEPRINT_REPLY_TIMEOUT
    last_status = ""
    while time.time() < deadline:
        try:
            status_response = blueprint_request(
                "blueprint.status",
                {"runId": run_id},
                request_kind="read",
                timeout=30,
            )
        except Exception as exc:
            print(f"[BLUEPRINT] status error: {exc}", flush=True)
            break
        last_status = _runtime_status_text(status_response)
        if last_status in {"completed", "cancelled", "failed"}:
            summary = _runtime_summary_text(status_response)
            if summary:
                return summary
            return f"蓝图运行已结束：{last_status}\n会话：{session_key}\n运行：{run_id}"
        time.sleep(BLUEPRINT_POLL_INTERVAL)
    return f"蓝图运行仍在处理中。\n会话：{session_key}\n运行：{run_id}\n状态：{last_status or 'starting'}"


def handle_and_reply(
    reply_to: str,
    user_message: str,
    *,
    sender: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> None:
    try:
        send_message(reply_to, "正在提交到蓝图会话，请稍候...")
        reply = call_blueprint(
            user_message,
            sender=sender,
            popo_session_id=popo_session_id,
            popo_group_id=popo_group_id,
        )
        send_message(reply_to, reply)
    except Exception as exc:
        print(f"[HANDLE] exception: {exc}", flush=True)
        send_message(reply_to, f"处理消息时出错：{str(exc)}")


class AESCipher:
    def __init__(self, key_text):
        key = key_text[:16]
        iv = key_text[16:]
        self.key = key.encode()
        self.iv = iv.encode()

    def aes_cbc_encrypt(self, text):
        block_size = AES.block_size
        pad_len = block_size - len(text.encode()) % block_size
        text = text + pad_len * chr(pad_len)
        cipher = AES.new(key=self.key, mode=AES.MODE_CBC, IV=self.iv)
        encrypted_text = cipher.encrypt(text.encode())
        return base64.b64encode(encrypted_text).decode("utf-8")

    def aes_cbc_decrypt(self, encrypted_text):
        encrypted_text = base64.b64decode(encrypted_text)
        cipher = AES.new(key=self.key, mode=AES.MODE_CBC, IV=self.iv)
        decrypted_text = cipher.decrypt(encrypted_text)
        dec_res = decrypted_text[: -ord(decrypted_text[len(decrypted_text) - 1 :])]
        return dec_res.decode()


def check_sha256_signature(token, timestamp, nonce, signature):
    temp_data_dict = {"token": token, "timestamp": timestamp, "nonce": nonce}
    sorted_data = sorted(temp_data_dict.items(), key=lambda x: x[1])
    data = ""
    for _, value in sorted_data:
        data += value
    hash_object = hashlib.sha256()
    hash_object.update(data.encode())
    hash_value = hash_object.hexdigest()
    return hash_value == signature


def handle_and_reply(
    reply_to: str,
    user_message: str,
    *,
    robot_config: dict[str, Any],
    sender: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
) -> None:
    try:
        send_message(reply_to, "正在提交到蓝图运行槽，请稍候...", robot_config)
        reply = call_blueprint(
            user_message,
            robot_app_key=str(robot_config.get("robot_app_key") or ""),
            sender=sender,
            popo_session_id=popo_session_id,
            popo_group_id=popo_group_id,
        )
        send_message(reply_to, reply, robot_config)
    except Exception as exc:
        print(f"[HANDLE] exception: {exc}", flush=True)
        send_message(reply_to, f"处理消息时出错：{str(exc)}", robot_config)


def _start_handler_thread(robot_config, reply_to, notify, sender, popo_session_id, popo_group_id=""):
    threading.Thread(
        target=handle_and_reply,
        kwargs={
            "reply_to": reply_to,
            "user_message": notify,
            "robot_config": robot_config,
            "sender": sender,
            "popo_session_id": popo_session_id,
            "popo_group_id": popo_group_id,
        },
        daemon=True,
    ).start()


@app.route("/popo/callback/<robot_app_key>", methods=["GET", "POST"])
@app.route("/popo/callback", defaults={"robot_app_key": None}, methods=["GET", "POST"])
def popo_callback(robot_app_key=None):
    timestamp = request.args.get("timestamp", "")
    signature = request.args.get("signature", "")
    nonce = request.args.get("nonce", "")
    app_key = str(robot_app_key or DEFAULT_ROBOT_APP_KEY or "").strip()
    if not app_key:
        return jsonify({"error": "robot_app_key required in callback URL"}), 404
    try:
        robot_config = load_popo_config(app_key)
    except Exception as exc:
        print(f"[WARN] POPO config load failed for {app_key}: {exc}", flush=True)
        return jsonify({"error": "robot config unavailable"}), 503
    callback_token = str(robot_config.get("callback_token") or "")
    aes_key = str(robot_config.get("aes_key") or "")

    if request.method == "GET":
        encrypt_raw = request.args.get("encrypt")
        if encrypt_raw is None:
            resp = make_response(nonce)
            resp.headers["Content-Type"] = "application/json"
            return resp

        if not check_sha256_signature(callback_token, timestamp, nonce, signature):
            print("[WARN] GET bad signature", flush=True)
            return make_response(json.dumps({"error": "bad signature"}), 403)

        aes = AESCipher(key_text=aes_key)
        decrypt_msg = aes.aes_cbc_decrypt(encrypt_raw)
        event_json = json.loads(decrypt_msg)
        event_type = event_json.get("eventType")
        print(f"[GET] eventType={event_type}, decrypted={decrypt_msg}", flush=True)

        if event_type == "valid_url":
            plaintext = aes.aes_cbc_encrypt("success")
            resp = make_response(json.dumps({"success": plaintext}))
            resp.headers["Content-Type"] = "application/json"
            return resp

        resp = make_response(nonce)
        resp.headers["Content-Type"] = "application/json"
        return resp

    encrypt_msg = None
    try:
        body = request.get_json(force=True, silent=True)
        if body and isinstance(body, dict):
            encrypt_msg = body.get("encrypt")
    except Exception:
        pass

    if not encrypt_msg:
        print("[WARN] POST missing encrypt", flush=True)
        return jsonify({"error": "missing encrypt"}), 400

    if not check_sha256_signature(callback_token, timestamp, nonce, signature):
        print("[WARN] POST bad signature", flush=True)
        return jsonify({"error": "bad signature"}), 403

    aes = AESCipher(key_text=aes_key)
    decrypt_msg = aes.aes_cbc_decrypt(encrypt_msg)
    event_json = json.loads(decrypt_msg)
    event_type = event_json.get("eventType")
    print(f"\n[POST] eventType={event_type}", flush=True)
    print(
        f"[POST] decrypted={json.dumps(event_json, ensure_ascii=False, indent=2)}",
        flush=True,
    )

    if event_type == "valid_url":
        plaintext = aes.aes_cbc_encrypt("success")
        return jsonify({"success": plaintext})

    if event_type == "MSG_SEND":
        event_data = event_json.get("eventData", {})
        sender = event_data.get("from", "")
        notify = event_data.get("notify", "")
        session_type = event_data.get("sessionType")
        session_id = event_data.get("sessionId", "")
        print(
            f"[MSG] from={sender}, sessionType={session_type}, sessionId={session_id}",
            flush=True,
        )
        print(f"[MSG] content={notify}", flush=True)

        reply_to = sender if session_type == 1 else session_id
        group_id = session_id if session_type == 3 else ""
        _start_handler_thread(robot_config, reply_to, notify, sender, session_id, group_id)
        return jsonify({"success": aes.aes_cbc_encrypt("success")})

    if event_type == "IM_P2P_TO_ROBOT_MSG":
        event_data = event_json.get("eventData", {})
        sender = event_data.get("from", "")
        notify = event_data.get("notify", "")
        session_id = event_data.get("sessionId", "")
        print(f"[MSG] user {sender} p2p: {notify}", flush=True)

        reply_to = sender or session_id
        _start_handler_thread(robot_config, reply_to, notify, sender, session_id)
        return jsonify({"success": aes.aes_cbc_encrypt("success")})

    if event_type == "IM_CHAT_TO_ROBOT_AT_MSG":
        event_data = event_json.get("eventData", {})
        sender = event_data.get("from", "")
        notify = event_data.get("notify", "")
        session_id = event_data.get("sessionId", "")
        session_type = event_data.get("sessionType")
        print(
            f"[MSG] user {sender} in group {session_id} at robot: {notify}",
            flush=True,
        )

        reply_to = session_id if session_type == 3 else sender
        group_id = session_id if session_type == 3 else ""
        _start_handler_thread(robot_config, reply_to, notify, sender, session_id, group_id)
        return jsonify({"success": aes.aes_cbc_encrypt("success")})

    print(f"[INFO] ignored event: {event_type}", flush=True)
    return jsonify({"success": aes.aes_cbc_encrypt("success")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="POPO Blueprint Agent service")
    parser.add_argument("--app-key", default=DEFAULT_ROBOT_APP_KEY, help="Optional default POPO robot AppKey for /popo/callback")
    parser.add_argument("--project-dir", default=BLUEPRINT_PROJECT_DIR, help="Blueprint project directory")
    args = parser.parse_args()

    missing = [
        name
        for name, value in {
            "project-dir": args.project_dir,
        }.items()
        if not value
    ]
    if missing:
        parser.error("missing required configuration: " + ", ".join(missing))

    DEFAULT_ROBOT_APP_KEY = str(args.app_key or "").strip()
    BLUEPRINT_PROJECT_DIR = str(Path(args.project_dir).expanduser().resolve())

    print("=" * 60, flush=True)
    print("POPO Blueprint Agent service started", flush=True)
    print("callback: http://0.0.0.0:3100/popo/callback/<robot_app_key>", flush=True)
    if DEFAULT_ROBOT_APP_KEY:
        print("legacy callback: http://0.0.0.0:3100/popo/callback", flush=True)
    print(f"projectDir: {BLUEPRINT_PROJECT_DIR}", flush=True)
    print(f"runtimeDataDir: {RUNTIME_DATA_DIR}", flush=True)
    print(f"replyTimeout: {BLUEPRINT_REPLY_TIMEOUT}s", flush=True)
    print("=" * 60, flush=True)
    app.run(host="0.0.0.0", port=3100, debug=False)
