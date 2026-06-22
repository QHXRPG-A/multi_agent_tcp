from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import requests
from fastapi.testclient import TestClient

from multi_agent_tcp.blueprint_resident_services import discover_resident_services
from multi_agent_tcp.hyskills_service import HyskillsClient, HyskillsError, clean_frontmatter, create_app


@dataclass
class FakeResponse:
    status_code: int
    body: Any
    content_type: str = "application/json"

    @property
    def headers(self) -> dict[str, str]:
        return {"content-type": self.content_type}

    @property
    def text(self) -> str:
        if isinstance(self.body, str):
            return self.body
        return json.dumps(self.body, ensure_ascii=False)

    def json(self) -> Any:
        if isinstance(self.body, str):
            return json.loads(self.body)
        return self.body


class FakeSession:
    def __init__(self, routes: dict[str, FakeResponse | Exception]) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> FakeResponse:
        path = urlparse(url).path
        self.calls.append({"url": url, "path": path, "headers": dict(headers), "timeout": timeout})
        response = self.routes.get(path)
        if response is None:
            return FakeResponse(404, {"ok": False})
        if isinstance(response, Exception):
            raise response
        return response


def _manifest() -> dict[str, Any]:
    return {
        "repo_url": "ssh://git@gitlab.nie.netease.com:32200/hyxd-ai/hyxd-skills",
        "skills": [
            {
                "id": "g83-review-package",
                "name": "g83-review-package",
                "display_name": "G83 Review Package",
                "description": "G83 weekly review package workflow",
                "author": "jiangfangxiao@CORP.NETEASE.COM",
                "tags": ["g83", "program", "review"],
                "project_id": "g83",
                "path": "skill_utils/g83-review-package",
                "added_at": 1718670000,
                "svn_urls": [
                    "https://svn-g83.gz.netease.com/svn/trunk/tools/AIWorkSpace/skill_utils/g83-review-package"
                ],
            },
            {
                "id": "memo-manager",
                "name": "memo-manager",
                "display_name": "Memo Manager",
                "description": "Local JSON memo tracking",
                "author": "gaoxilin@CORP.NETEASE.COM",
                "tags": ["planning", "program", "common"],
                "install_command": "npx skills add repo --skill memo-manager --yes",
            },
            {
                "id": "skin-config-check",
                "name": "skin-config-check",
                "display_name": "Skin Config Check",
                "description": "G83US skin client presentation config checker",
                "author": "xuchuyi01@CORP.NETEASE.COM",
                "tags": ["G83US", "QA", "planning", "test"],
                "path": "helper/AISkills/skin-config-check",
            },
            {
                "id": "gun-skin-direct",
                "name": "gun-skin-direct",
                "display_name": "Gun Skin Direct",
                "description": "G83US gun skin direct table writer",
                "author": "lipenghao01@CORP.NETEASE.COM",
                "tags": ["g83us", "planning", "gun-skin"],
                "project_id": "g83us",
                "path": "helper/AISkills/gun-skin-direct",
                "svn_urls": [
                    "https://svn-g83.gz.netease.com/svn/NewSpike/trunk/helper/AISkills/gun-skin-direct"
                ],
            },
        ],
    }


def _routes() -> dict[str, FakeResponse | Exception]:
    return {
        "/api/manifest": FakeResponse(200, _manifest()),
        "/api/stats": FakeResponse(
            200,
            {
                "total": {"g83-review-package": 12, "skin-config-check": 5, "gun-skin-direct": 9},
                "hot": {"gun-skin-direct": 2},
                "trending": {},
            },
        ),
        "/api/skill/skin-config-check/readme": FakeResponse(
            200,
            "---\nname: skin-config-check\n---\n# Skin Config Check\n\nREADME body",
            "text/plain",
        ),
        "/api/skill/skin-config-check/docs": FakeResponse(
            200,
            {"docs": [{"name": "usage.md", "type": "markdown"}]},
        ),
    }


def _load_skill_square_module() -> Any:
    service_root = Path(__file__).resolve().parent / "framework_assets" / "resident_services"
    path = service_root / "skill_square_service.py"
    spec = importlib.util.spec_from_file_location("test_skill_square_service", path)
    assert spec is not None and spec.loader is not None
    sys.path.insert(0, str(service_root))
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        try:
            sys.path.remove(str(service_root))
        except ValueError:
            pass


class FakeSkillSquareClient:
    def __init__(self, *, read_error: HyskillsError | None = None) -> None:
        self.read_error = read_error
        self.search_calls: list[dict[str, Any]] = []
        self.read_calls: list[str] = []

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "base_url": "https://hyskills.netease.com",
            "cookie_configured": True,
            "auth_header_configured": False,
            "cache_entries": 1,
            "cache_ttl_sec": 300,
        }

    def search(self, **kwargs: Any) -> dict[str, Any]:
        self.search_calls.append(dict(kwargs))
        return {
            "ok": True,
            "total": 1,
            "offset": kwargs.get("offset", 0),
            "limit": kwargs.get("limit", 20),
            "items": [{"id": "G83US-gun-academy-config", "project_id": "g83us"}],
        }

    def read_skill(self, skill_id: str) -> dict[str, Any]:
        self.read_calls.append(skill_id)
        if self.read_error is not None:
            raise self.read_error
        return {
            "ok": True,
            "skill": {
                "id": "G83US-gun-academy-config",
                "name": "G83US-gun-academy-config",
                "project_id": "g83us",
            },
            "readme_clean": "# G83US Gun Academy Config\n",
            "docs": [],
        }


def test_client_reads_visible_g83us_skill_summary_readme_docs_and_install_commands() -> None:
    session = FakeSession(_routes())
    client = HyskillsClient(session=session, cookie="sid=secret", auth_header="Authorization: Bearer abc")

    detail = client.read_skill("skin-config-check")

    assert detail["ok"] is True
    assert detail["skill"]["display_name"] == "Skin Config Check"
    assert detail["skill"]["heat"]["total"] == 5
    assert detail["docs"] == [{"name": "usage.md", "type": "markdown"}]
    assert detail["readme_markdown"].startswith("---")
    assert detail["readme_clean"].startswith("# Skin Config Check")
    assert detail["install_commands"][0]["command"].startswith("npx skills add ssh://")
    assert session.calls[0]["headers"]["Cookie"] == "sid=secret"
    assert session.calls[0]["headers"]["Authorization"] == "Bearer abc"


def test_search_is_limited_to_g83us_scope_and_paginates() -> None:
    client = HyskillsClient(session=FakeSession(_routes()))

    hidden = client.search(q="review", tag="g83", author="jiangfangxiao", project="g83", limit=10)
    assert hidden["total"] == 0

    result = client.search(q="skin", tag="g83us,planning", author="lipenghao01", project="g83us", limit=10)
    assert result["total"] == 1
    assert result["items"][0]["id"] == "gun-skin-direct"
    assert result["items"][0]["normalized_author"] == "lipenghao01"

    paged = client.search(q="", limit=1, offset=1)
    assert paged["total"] == 2
    assert len(paged["items"]) == 1
    assert paged["offset"] == 1
    assert paged["limit"] == 1


def test_project_filter_falls_back_to_tags_when_project_id_is_missing() -> None:
    client = HyskillsClient(session=FakeSession(_routes()))

    result = client.search(project="g83us")

    assert result["total"] == 2
    assert {item["id"] for item in result["items"]} == {"skin-config-check", "gun-skin-direct"}


def test_read_non_g83us_skill_is_rejected() -> None:
    client = HyskillsClient(session=FakeSession(_routes()))

    with pytest.raises(HyskillsError) as exc_info:
        client.read_skill("g83-review-package")

    assert exc_info.value.code == "SKILL_OUT_OF_SCOPE"
    assert exc_info.value.status_code == 403


def test_upstream_errors_are_mapped_to_stable_codes() -> None:
    unauthorized = HyskillsClient(session=FakeSession({"/api/manifest": FakeResponse(401, {})}))
    with pytest.raises(HyskillsError) as exc_info:
        unauthorized.manifest()
    assert exc_info.value.code == "UPSTREAM_UNAUTHORIZED"
    assert exc_info.value.upstream_status == 401

    missing = HyskillsClient(session=FakeSession({"/api/manifest": FakeResponse(404, {})}))
    with pytest.raises(HyskillsError) as missing_exc:
        missing.manifest()
    assert missing_exc.value.code == "UPSTREAM_NOT_FOUND"
    assert missing_exc.value.status_code == 404

    timed_out = HyskillsClient(session=FakeSession({"/api/manifest": requests.Timeout("slow")}))
    with pytest.raises(HyskillsError) as timeout_exc:
        timed_out.manifest()
    assert timeout_exc.value.code == "UPSTREAM_TIMEOUT"
    assert timeout_exc.value.status_code == 504


def test_clean_frontmatter_removes_yaml_header() -> None:
    assert clean_frontmatter("---\nname: demo\n---\n# Title\n") == "# Title\n"
    assert clean_frontmatter("# Title\n") == "# Title\n"


def test_api_health_search_read_token_and_cache_refresh() -> None:
    session = FakeSession(_routes())
    client = HyskillsClient(session=session, cookie="sid=secret")
    app = create_app(client=client, service_token="local-token")
    api = TestClient(app)

    unauthorized = api.get("/health")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "UNAUTHORIZED"

    headers = {"Authorization": "Bearer local-token"}
    health = api.get("/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["cookie_configured"] is True
    assert health.json()["visible_scope"] == "g83us"
    assert "secret" not in health.text
    assert "local-token" not in health.text

    search = api.get("/skills/search?q=skin", headers=headers)
    assert search.status_code == 200
    assert {item["id"] for item in search.json()["items"]} == {"skin-config-check", "gun-skin-direct"}

    hidden_search = api.get("/skills/search?q=review", headers=headers)
    assert hidden_search.status_code == 200
    assert hidden_search.json()["total"] == 0

    detail = api.get("/skills/skin-config-check", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["readme_clean"].startswith("# Skin Config Check")

    hidden_detail = api.get("/skills/g83-review-package", headers=headers)
    assert hidden_detail.status_code == 403
    assert hidden_detail.json()["code"] == "SKILL_OUT_OF_SCOPE"

    manifest_calls_before = [call for call in session.calls if call["path"] == "/api/manifest"]
    refreshed = api.post("/cache/refresh", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["skills"] == 2
    assert refreshed.json()["visible_scope"] == "g83us"
    manifest_calls_after = [call for call in session.calls if call["path"] == "/api/manifest"]
    assert len(manifest_calls_after) == len(manifest_calls_before) + 1


def test_api_maps_upstream_unauthorized_response() -> None:
    client = HyskillsClient(session=FakeSession({"/api/manifest": FakeResponse(401, {})}))
    api = TestClient(create_app(client=client, service_token=""))

    response = api.get("/skills/search")

    assert response.status_code == 502
    assert response.json()["code"] == "UPSTREAM_UNAUTHORIZED"


def test_skill_square_resident_service_catalog_metadata() -> None:
    root = Path(__file__).resolve().parent
    discovered = discover_resident_services(root / "framework_assets")

    service = next(
        item for item in discovered["services"] if item.get("module_path") == "skill_square_service.py"
    )

    assert service["service_name"] == "skill_square"
    assert service["title"] == "Skill 广场服务"
    assert service["description"] == "在 G83US 边界内搜索、读取并安装 Skill 广场技能。"
    assert {method["name"] for method in service["methods"]} >= {
        "help",
        "health",
        "preflight",
        "search",
        "read",
        "install",
    }
    assert not [item for item in discovered["diagnostics"] if item.get("path") == "skill_square_service.py"]


def test_skill_square_service_search_and_read_reuse_g83us_client(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_skill_square_module()
    fake_client = FakeSkillSquareClient()
    monkeypatch.setattr(module, "HyskillsClient", lambda **_kwargs: fake_client)

    service = module.SkillSquareService()
    search = service.search("枪皮", limit=5)
    detail = service.read("G83US-gun-academy-config")

    assert search["ok"] is True
    assert search["service"] == "skill_square"
    assert search["visible_scope"] == "g83us"
    assert fake_client.search_calls == [
        {"q": "枪皮", "project": "g83us", "limit": 5, "offset": 0},
    ]
    assert detail["ok"] is True
    assert detail["action"] == "read"
    assert fake_client.read_calls == ["G83US-gun-academy-config"]


def test_skill_square_install_rejects_non_g83us_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_skill_square_module()
    fake_client = FakeSkillSquareClient(
        read_error=HyskillsError(
            "SKILL_OUT_OF_SCOPE",
            "skill is outside the visible scope: g83us",
            status_code=403,
        )
    )
    monkeypatch.setattr(module, "HyskillsClient", lambda **_kwargs: fake_client)

    result = module.SkillSquareService().install("not-g83us")

    assert result["ok"] is False
    assert result["code"] == "SKILL_OUT_OF_SCOPE"
    assert result["action"] == "install"
    assert result["visible_scope"] == "g83us"


def test_skill_square_install_reports_ssh_precheck_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_skill_square_module()
    fake_client = FakeSkillSquareClient()
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(module, "HyskillsClient", lambda **_kwargs: fake_client)
    monkeypatch.setattr(
        module,
        "_find_executable",
        lambda *names: "npx.cmd" if any("npx" in name for name in names) else "git.exe",
    )
    monkeypatch.setattr(
        module,
        "_run_command",
        lambda *_args, **_kwargs: module.CommandResult(128, "", "Host key verification failed."),
    )

    result = module.SkillSquareService().install("G83US-gun-academy-config")

    assert result["ok"] is False
    assert result["code"] == "INSTALL_PRECHECK_FAILED"
    assert result["skill_id"] == "G83US-gun-academy-config"
    assert result["preflight"]["code"] == "SSH_PRECHECK_FAILED"
    assert "Host key verification failed" in result["preflight"]["checks"]["ssh"]["stderr"]


def test_skill_square_install_builds_npx_command_for_global_codex_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_skill_square_module()
    fake_client = FakeSkillSquareClient()
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    runs: list[dict[str, Any]] = []
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(module, "HyskillsClient", lambda **_kwargs: fake_client)
    monkeypatch.setattr(
        module,
        "_find_executable",
        lambda *names: "npx.cmd" if any("npx" in name for name in names) else "git.exe",
    )

    def fake_run(command: list[str], **kwargs: Any) -> Any:
        runs.append({"command": command, **kwargs})
        return module.CommandResult(0, "ok", "")

    monkeypatch.setattr(module, "_run_command", fake_run)

    result = module.SkillSquareService().install("G83US-gun-academy-config", timeout_sec=9)

    assert result["ok"] is True
    assert result["code"] == "OK"
    assert result["skills_dir"] == str(codex_home / "skills")
    assert (codex_home / "skills").is_dir()
    assert runs[0]["command"] == [
        "git.exe",
        "ls-remote",
        module.SKILL_REPO_URL,
        "HEAD",
    ]
    assert runs[1]["command"] == [
        "npx.cmd",
        "skills",
        "add",
        module.SKILL_REPO_URL,
        "--skill",
        "G83US-gun-academy-config",
        "--yes",
    ]
    assert runs[1]["timeout_sec"] == 9
    assert runs[1]["env"]["CODEX_HOME"] == str(codex_home)


def test_framework_agent_runtime_mentions_skill_square_fallback() -> None:
    skill_text = (
        Path(__file__).resolve().parent
        / "framework_assets"
        / "skills"
        / "framework-agent-runtime"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    rule_text = (
        Path(__file__).resolve().parent
        / "framework_assets"
        / "rules"
        / "framework-agent-runtime.md"
    ).read_text(encoding="utf-8")

    assert 'blueprint_service_docs("skill_square")' in skill_text
    assert 'blueprint_service_call("skill_square", "search"' in skill_text
    assert "G83US" in skill_text
    assert "CODEX_HOME/skills" in skill_text
    assert 'blueprint_service_docs("skill_square")' in rule_text
    assert 'blueprint_service_call("skill_square", "search"' in rule_text
    assert "G83US" in rule_text
