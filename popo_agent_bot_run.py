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
from socketserver import ThreadingMixIn
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

import requests
from Crypto.Cipher import AES
from flask import Flask, jsonify, make_response, request


DEFAULT_ROBOT_APP_KEY = os.environ.get("POPO_APP_KEY", "").strip()
POPO_API_BASE = "https://open.popo.netease.com"

BLUEPRINT_PROJECT_DIR = os.environ.get("POPO_BLUEPRINT_PROJECT_DIR", "").strip()
BLUEPRINT_REPLY_TIMEOUT = int(os.environ.get("POPO_BLUEPRINT_REPLY_TIMEOUT", "300"))
BLUEPRINT_POLL_INTERVAL = float(os.environ.get("POPO_BLUEPRINT_POLL_INTERVAL", "2"))
BLUEPRINT_CALLBACK_CONFIG_TIMEOUT = float(os.environ.get("POPO_BLUEPRINT_CALLBACK_CONFIG_TIMEOUT", "3"))
POPO_EVENT_DEDUP_TTL = float(os.environ.get("POPO_EVENT_DEDUP_TTL", "600"))
POPO_CALLBACK_HOST = os.environ.get("POPO_CALLBACK_HOST", "0.0.0.0").strip() or "0.0.0.0"
POPO_CALLBACK_PORT = int(os.environ.get("POPO_CALLBACK_PORT", "3100"))

REPO_ROOT = Path(__file__).resolve().parent
PLUGIN_ROOT = Path(os.environ.get("GULICODE_BP_PLUGIN_ROOT") or REPO_ROOT / "plugins" / "gulicode-bp").resolve()
RUNTIME_HOME = Path(os.environ.get("GULICODE_BP_RUNTIME_HOME") or PLUGIN_ROOT / ".runtime").resolve()
RUNTIME_DATA_DIR = Path(os.environ.get("GULICODE_BP_DATA_DIR") or RUNTIME_HOME / "state").resolve()
POPO_ROBOT_ROUTES_PATH = RUNTIME_DATA_DIR / "popo_robot_routes.json"
MCP_DIR = PLUGIN_ROOT / "mcp"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from gulicode_bp_singleton import SingletonServiceError, ensure_singleton_service, service_rpc  # noqa: E402


app = Flask(__name__)

_service_lock = threading.Lock()
_config_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_event_cache: dict[str, float] = {}
_token_cache: dict[str, dict[str, Any]] = {}
_config_lock = threading.Lock()
_event_lock = threading.Lock()
_token_lock = threading.Lock()


class ThreadingCallbackServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = True


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "ok": True,
            "service": "gulicode-bp-popo-callback",
            "runtimeDataDir": str(RUNTIME_DATA_DIR),
        }
    )


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


def _normal_popo_robot_config(robot: dict[str, Any], *, fallback_app_key: str = "") -> dict[str, Any]:
    return {
        "robot_app_key": str(robot.get("robot_app_key") or robot.get("robotAppKey") or fallback_app_key).strip(),
        "robot_name": str(robot.get("robot_name") or robot.get("robotName") or "").strip(),
        "robot_app_secret": str(robot.get("robot_app_secret") or robot.get("robotAppSecret") or "").strip(),
        "callback_token": str(robot.get("callback_token") or robot.get("callbackToken") or "").strip(),
        "aes_key": str(robot.get("aes_key") or robot.get("aesKey") or "").strip(),
        "blueprint_id": "",
        "blueprint_name": "",
        "blueprint_structure_id": "",
        "source": "local_routes",
    }


def _validate_popo_robot_config(config: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in ("robot_app_key", "robot_app_secret", "callback_token", "aes_key") if not config.get(key)]
    if missing:
        raise SingletonServiceError(
            "BLUEPRINT_POPO_ENTRY_REQUIRED",
            "POPO entry is incomplete: " + ", ".join(missing),
            status=400,
            details={"missing": missing},
        )
    return config


def _load_local_popo_robot_routes() -> list[dict[str, Any]]:
    try:
        payload = json.loads(POPO_ROBOT_ROUTES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except Exception as exc:
        raise SingletonServiceError(
            "BLUEPRINT_POPO_ROUTES_INVALID",
            f"local POPO robot routes are invalid: {exc}",
            status=500,
        ) from exc
    robots = payload.get("robots") if isinstance(payload, dict) else None
    values = robots.values() if isinstance(robots, dict) else []
    return [dict(item) for item in values if isinstance(item, dict) and item.get("enabled") is True]


def _load_popo_config_from_local_routes(robot_app_key: str) -> dict[str, Any]:
    app_key = str(robot_app_key or "").strip()
    enabled = _load_local_popo_robot_routes()
    if app_key:
        for robot in enabled:
            if str(robot.get("robot_app_key") or robot.get("robotAppKey") or "").strip() == app_key:
                return _validate_popo_robot_config(_normal_popo_robot_config(robot, fallback_app_key=app_key))
        raise SingletonServiceError(
            "BLUEPRINT_POPO_ROBOT_NOT_BOUND",
            "POPO callback robot is not enabled in local routes",
            details={"robotAppKey": app_key},
            status=404,
        )
    if not enabled:
        raise SingletonServiceError(
            "BLUEPRINT_POPO_ROBOT_NOT_BOUND",
            "no enabled POPO callback robot is configured in local routes",
            status=404,
        )
    if len(enabled) > 1:
        raise SingletonServiceError(
            "BLUEPRINT_POPO_ROBOT_STRUCTURE_CONFLICT",
            "legacy POPO callback path matched multiple enabled callback robots in local routes",
            details={"robotAppKeys": sorted(str(item.get("robot_app_key") or item.get("robotAppKey") or "") for item in enabled)},
            status=409,
        )
    return _validate_popo_robot_config(_normal_popo_robot_config(enabled[0]))


def _should_use_local_popo_config_fallback(exc: SingletonServiceError) -> bool:
    message = str(getattr(exc, "message", "") or exc).lower()
    return getattr(exc, "code", "") in {"SERVICE_UNAVAILABLE", "SERVICE_ERROR"} or "timed out" in message or "timeout" in message


def _popo_config_cache_key(robot_app_key: str) -> str:
    return str(robot_app_key or "").strip() or "<legacy>"


def _get_cached_popo_config(robot_app_key: str) -> dict[str, Any] | None:
    key = _popo_config_cache_key(robot_app_key)
    with _config_lock:
        cached = _config_cache.get(key)
        if not cached:
            return None
        cached_at, config = cached
        if time.time() - cached_at > 60:
            _config_cache.pop(key, None)
            return None
        return dict(config)


def _set_cached_popo_config(robot_app_key: str, config: dict[str, Any]) -> dict[str, Any]:
    key = _popo_config_cache_key(robot_app_key)
    payload = dict(config)
    with _config_lock:
        _config_cache[key] = (time.time(), payload)
    return dict(payload)


def load_popo_config(robot_app_key: str) -> dict[str, Any]:
    app_key = str(robot_app_key or "").strip()
    cached = _get_cached_popo_config(app_key)
    if cached is not None:
        return cached
    try:
        return _set_cached_popo_config(app_key, _load_popo_config_from_local_routes(app_key))
    except SingletonServiceError as local_exc:
        local_error = local_exc
    request_args: dict[str, Any] = {}
    if app_key:
        request_args["robotAppKey"] = app_key
    if BLUEPRINT_PROJECT_DIR:
        request_args["projectDir"] = BLUEPRINT_PROJECT_DIR
    try:
        response = blueprint_request(
            "blueprint.popo.callbackConfig",
            request_args,
            request_kind="internal",
            timeout=BLUEPRINT_CALLBACK_CONFIG_TIMEOUT,
        )
    except SingletonServiceError as exc:
        if not _should_use_local_popo_config_fallback(exc) or getattr(local_error, "code", "") != "BLUEPRINT_POPO_ROBOT_NOT_BOUND":
            raise
        print(f"[WARN] POPO config service unavailable and no local route matched: {exc}", flush=True)
        raise local_error from exc
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
    return _set_cached_popo_config(app_key, _validate_popo_robot_config(config))


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
    robot_app_key: str,
    sender: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
    reply_to: str = "",
    session_type: Any = "",
) -> str:
    print(
        f"[BLUEPRINT] message: {user_message} (robot={robot_app_key}, sender={sender}, session={popo_session_id}, group={popo_group_id})",
        flush=True,
    )
    try:
        request_args = {
            "message": user_message,
            "source": "popo",
            "sourceIdentity": {"robotAppKey": robot_app_key},
            "sessionIdentity": {
                "popoUserId": sender or "",
                "popoSessionId": popo_session_id or "",
                "popoGroupId": popo_group_id or "",
                "popoReplyTo": reply_to or "",
                "popoSessionType": str(session_type or ""),
            },
        }
        if BLUEPRINT_PROJECT_DIR:
            request_args["projectDir"] = BLUEPRINT_PROJECT_DIR
        started = blueprint_request(
            "blueprint.slots.message",
            request_args,
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
    if started.get("cleared"):
        return "已开启新会话"
    if started.get("queued"):
        return ""
    if not run_id:
        return ""

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


def _popo_event_id(event_json: dict[str, Any]) -> str:
    event_data = event_json.get("eventData") if isinstance(event_json, dict) else {}
    if not isinstance(event_data, dict):
        return ""
    value = event_data.get("uuid") or event_data.get("msgId") or event_data.get("messageId")
    return str(value or "").strip()


def _mark_popo_event_seen(event_id: str) -> bool:
    event_key = str(event_id or "").strip()
    if not event_key:
        return True
    now = time.time()
    with _event_lock:
        expired = [key for key, seen_at in _event_cache.items() if now - seen_at > POPO_EVENT_DEDUP_TTL]
        for key in expired:
            _event_cache.pop(key, None)
        if event_key in _event_cache:
            return False
        _event_cache[event_key] = now
    return True


def _success_response(aes: AESCipher):
    return jsonify({"success": aes.aes_cbc_encrypt("success")})


def handle_and_reply(
    reply_to: str,
    user_message: str,
    *,
    robot_config: dict[str, Any],
    sender: str = "",
    popo_session_id: str = "",
    popo_group_id: str = "",
    session_type: Any = "",
) -> None:
    try:
        send_message(reply_to, "思考中....", robot_config)
        reply = call_blueprint(
            user_message,
            robot_app_key=str(robot_config.get("robot_app_key") or ""),
            sender=sender,
            popo_session_id=popo_session_id,
            popo_group_id=popo_group_id,
            reply_to=reply_to,
            session_type=session_type,
        )
        if reply:
            send_message(reply_to, reply, robot_config)
    except Exception as exc:
        print(f"[HANDLE] exception: {exc}", flush=True)
        send_message(reply_to, f"处理消息时出错：{str(exc)}", robot_config)


def _start_handler_thread(robot_config, reply_to, notify, sender, popo_session_id, popo_group_id="", session_type=""):
    threading.Thread(
        target=handle_and_reply,
        kwargs={
            "reply_to": reply_to,
            "user_message": notify,
            "robot_config": robot_config,
            "sender": sender,
            "popo_session_id": popo_session_id,
            "popo_group_id": popo_group_id,
            "session_type": session_type,
        },
        daemon=True,
    ).start()


@app.route("/popo/callback/<robot_app_key>", methods=["GET", "POST"])
@app.route("/popo/callback", defaults={"robot_app_key": None}, methods=["GET", "POST"])
def popo_callback(robot_app_key=None):
    timestamp = request.args.get("timestamp", "")
    signature = request.args.get("signature", "")
    nonce = request.args.get("nonce", "")
    app_key = str(robot_app_key or "").strip()
    try:
        robot_config = load_popo_config(app_key)
    except SingletonServiceError as exc:
        label = app_key or "<auto>"
        print(f"[WARN] POPO config rejected for {label}: {exc}", flush=True)
        return jsonify({"ok": False, "code": exc.code, "error": exc.message, "details": exc.details}), exc.status
    except Exception as exc:
        label = app_key or "<auto>"
        print(f"[WARN] POPO config load failed for {label}: {exc}", flush=True)
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
        return _success_response(aes)

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

        event_id = _popo_event_id(event_json)
        if not _mark_popo_event_seen(event_id):
            print(f"[INFO] duplicate POPO event ignored: {event_id}", flush=True)
            return _success_response(aes)
        reply_to = sender if session_type == 1 else session_id
        group_id = session_id if session_type == 3 else ""
        _start_handler_thread(robot_config, reply_to, notify, sender, session_id, group_id, session_type)
        return _success_response(aes)

    if event_type == "IM_P2P_TO_ROBOT_MSG":
        event_data = event_json.get("eventData", {})
        sender = event_data.get("from", "")
        notify = event_data.get("notify", "")
        session_id = event_data.get("sessionId", "")
        session_type = event_data.get("sessionType", "")
        print(f"[MSG] user {sender} p2p: {notify}", flush=True)

        event_id = _popo_event_id(event_json)
        if not _mark_popo_event_seen(event_id):
            print(f"[INFO] duplicate POPO event ignored: {event_id}", flush=True)
            return _success_response(aes)
        reply_to = sender or session_id
        _start_handler_thread(robot_config, reply_to, notify, sender, session_id, "", session_type)
        return _success_response(aes)

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

        event_id = _popo_event_id(event_json)
        if not _mark_popo_event_seen(event_id):
            print(f"[INFO] duplicate POPO event ignored: {event_id}", flush=True)
            return _success_response(aes)
        reply_to = session_id if session_type == 3 else sender
        group_id = session_id if session_type == 3 else ""
        _start_handler_thread(robot_config, reply_to, notify, sender, session_id, group_id, session_type)
        return _success_response(aes)

    print(f"[INFO] ignored event: {event_type}", flush=True)
    return _success_response(aes)


def run_callback_server(host: str, port: int) -> None:
    with make_server(host, port, app, server_class=ThreadingCallbackServer, handler_class=WSGIRequestHandler) as server:
        print(f"serving: http://{host}:{port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="POPO Blueprint Agent service")
    parser.add_argument("--app-key", default=DEFAULT_ROBOT_APP_KEY, help="Deprecated; callback robots are resolved from plugin state")
    parser.add_argument("--project-dir", default=BLUEPRINT_PROJECT_DIR, help="Optional fallback Blueprint project directory")
    parser.add_argument("--host", default=POPO_CALLBACK_HOST, help="Callback bind host")
    parser.add_argument("--port", type=int, default=POPO_CALLBACK_PORT, help="Callback bind port")
    args = parser.parse_args()

    DEFAULT_ROBOT_APP_KEY = str(args.app_key or "").strip()
    BLUEPRINT_PROJECT_DIR = str(Path(args.project_dir).expanduser().resolve()) if str(args.project_dir or "").strip() else ""
    POPO_CALLBACK_HOST = str(args.host or "0.0.0.0").strip() or "0.0.0.0"
    POPO_CALLBACK_PORT = int(args.port)

    print("=" * 60, flush=True)
    print("POPO Blueprint Agent service started", flush=True)
    print(f"callback: http://{POPO_CALLBACK_HOST}:{POPO_CALLBACK_PORT}/popo/callback/<robot_app_key>", flush=True)
    print(f"legacy callback: http://{POPO_CALLBACK_HOST}:{POPO_CALLBACK_PORT}/popo/callback", flush=True)
    print(f"moduleFile: {Path(__file__).resolve()}", flush=True)
    print(f"routes: {[rule.rule for rule in app.url_map.iter_rules()]}", flush=True)
    print(f"projectDir: {BLUEPRINT_PROJECT_DIR or '(registry routing)'}", flush=True)
    print(f"runtimeDataDir: {RUNTIME_DATA_DIR}", flush=True)
    print(f"replyTimeout: {BLUEPRINT_REPLY_TIMEOUT}s", flush=True)
    print("=" * 60, flush=True)
    run_callback_server(POPO_CALLBACK_HOST, POPO_CALLBACK_PORT)
