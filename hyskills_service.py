from __future__ import annotations

import argparse
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote

import requests
import uvicorn
from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse


DEFAULT_BASE_URL = "https://hyskills.netease.com"
DEFAULT_CACHE_TTL_SECONDS = 300.0
DEFAULT_PORT = 8795
USER_AGENT = "multi-agent-tcp-hyskills-service/0.1"
FRONTMATTER_RE = re.compile(r"^---[\s\S]*?---\s*")
VISIBLE_PROJECT_ID = "g83us"


class HyskillsError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 502,
        upstream_status: int | None = None,
        path: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = int(status_code)
        self.upstream_status = upstream_status
        self.path = path

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "code": self.code,
            "error": self.message,
        }
        if self.path:
            payload["path"] = self.path
        if self.upstream_status is not None:
            payload["upstream_status"] = self.upstream_status
        return payload


@dataclass
class CacheEntry:
    value: Any
    created_at: float


class HyskillsClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        cache_ttl_sec: float = DEFAULT_CACHE_TTL_SECONDS,
        cookie: str | None = None,
        auth_header: str | None = None,
        session: requests.Session | None = None,
        timeout_sec: float = 20.0,
    ) -> None:
        self.base_url = str(base_url or DEFAULT_BASE_URL).rstrip("/")
        self.cache_ttl_sec = max(0.0, float(cache_ttl_sec))
        self.cookie = cookie if cookie is not None else os.environ.get("HYSKILLS_COOKIE", "")
        self.auth_header = (
            auth_header if auth_header is not None else os.environ.get("HYSKILLS_AUTH_HEADER", "")
        )
        self.session = session or requests.Session()
        self.timeout_sec = max(1.0, float(timeout_sec))
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "base_url": self.base_url,
            "cookie_configured": bool(str(self.cookie or "").strip()),
            "auth_header_configured": bool(str(self.auth_header or "").strip()),
            "visible_scope": VISIBLE_PROJECT_ID,
            "cache_ttl_sec": self.cache_ttl_sec,
            "cache_entries": len(self.cache_snapshot()["entries"]),
        }

    def cache_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            entries = [
                {
                    "key": key,
                    "age_sec": max(0.0, now - entry.created_at),
                    "ttl_sec": self.cache_ttl_sec,
                    "expired": self._is_expired(entry, now),
                }
                for key, entry in sorted(self._cache.items())
            ]
        return {"ok": True, "entries": entries}

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def refresh(self) -> dict[str, Any]:
        self.clear_cache()
        manifest = self.manifest()
        return {
            "ok": True,
            "skills": len(_visible_skills(manifest)),
            "visible_scope": VISIBLE_PROJECT_ID,
            "cache_entries": len(self.cache_snapshot()["entries"]),
        }

    def manifest(self) -> dict[str, Any]:
        data = self._get_json_cached("/api/manifest")
        if not isinstance(data, dict):
            raise HyskillsError("UPSTREAM_INVALID_JSON", "manifest response is not a JSON object")
        return data

    def stats(self) -> dict[str, Any]:
        try:
            data = self._get_json_cached("/api/stats")
        except HyskillsError as exc:
            if exc.code in {"UPSTREAM_NOT_FOUND", "UPSTREAM_REQUEST_FAILED"}:
                return {"total": {}, "trending": {}, "hot": {}}
            raise
        if not isinstance(data, dict):
            return {"total": {}, "trending": {}, "hot": {}}
        return data

    def search(
        self,
        *,
        q: str = "",
        tag: str = "",
        author: str = "",
        project: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        manifest = self.manifest()
        stats = self.stats()
        skills = _visible_skills(manifest)
        tags = _split_csv(tag)
        query = str(q or "").strip().casefold()
        author_filter = _normalize_author(author).casefold() if str(author or "").strip() else ""
        project_filter = str(project or "").strip().casefold()

        filtered = []
        for skill in skills:
            if tags and not _matches_all_tags(skill, tags):
                continue
            if author_filter and _normalize_author(skill.get("author")).casefold() != author_filter:
                continue
            if project_filter and not _matches_project(skill, project_filter):
                continue
            if query and not _matches_query(skill, query):
                continue
            filtered.append(skill)

        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 20), 200))
        page = filtered[safe_offset : safe_offset + safe_limit]
        return {
            "ok": True,
            "total": len(filtered),
            "offset": safe_offset,
            "limit": safe_limit,
            "items": [
                _skill_summary(skill, manifest=manifest, stats=stats, base_url=self.base_url)
                for skill in page
            ],
        }

    def read_skill(self, skill_id: str) -> dict[str, Any]:
        manifest = self.manifest()
        stats = self.stats()
        skill = _find_skill(_manifest_skills(manifest), skill_id)
        if skill is None:
            raise HyskillsError(
                "SKILL_NOT_FOUND",
                f"skill not found: {skill_id}",
                status_code=404,
            )
        if not _is_visible_skill(skill):
            raise HyskillsError(
                "SKILL_OUT_OF_SCOPE",
                f"skill is outside the visible scope: {VISIBLE_PROJECT_ID}",
                status_code=403,
            )
        resolved_id = _skill_id(skill)
        readme = self._get_text_cached(f"/api/skill/{quote(resolved_id, safe='')}/readme")
        docs_data = self._get_json_cached(f"/api/skill/{quote(resolved_id, safe='')}/docs")
        docs = docs_data.get("docs", []) if isinstance(docs_data, dict) else []
        if not isinstance(docs, list):
            docs = []
        return {
            "ok": True,
            "skill": _skill_summary(skill, manifest=manifest, stats=stats, base_url=self.base_url),
            "install_commands": _install_commands(skill, manifest),
            "detail_url": _detail_url(self.base_url, resolved_id),
            "download_url": _download_url(self.base_url, resolved_id),
            "readme_markdown": readme,
            "readme_clean": clean_frontmatter(readme),
            "docs": docs,
        }

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": USER_AGENT,
        }
        cookie = str(self.cookie or "").strip()
        if cookie:
            headers["Cookie"] = cookie
        auth_header = str(self.auth_header or "").strip()
        if auth_header:
            prefix = "authorization:"
            if auth_header.casefold().startswith(prefix):
                auth_header = auth_header[len(prefix) :].strip()
            headers["Authorization"] = auth_header
        return headers

    def _get_json_cached(self, path: str) -> Any:
        return self._get_cached(f"json:{path}", lambda: self._request_json(path))

    def _get_text_cached(self, path: str) -> str:
        return self._get_cached(f"text:{path}", lambda: self._request_text(path))

    def _get_cached(self, key: str, loader: Any) -> Any:
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and not self._is_expired(entry, now):
                return entry.value
        value = loader()
        with self._lock:
            self._cache[key] = CacheEntry(value=value, created_at=time.monotonic())
        return value

    def _is_expired(self, entry: CacheEntry, now: float | None = None) -> bool:
        if self.cache_ttl_sec <= 0:
            return True
        current = time.monotonic() if now is None else now
        return (current - entry.created_at) >= self.cache_ttl_sec

    def _request_json(self, path: str) -> Any:
        response = self._request(path)
        try:
            return response.json()
        except ValueError as exc:
            raise HyskillsError(
                "UPSTREAM_INVALID_JSON",
                f"upstream returned invalid JSON for {path}",
                path=path,
            ) from exc

    def _request_text(self, path: str) -> str:
        return self._request(path).text

    def _request(self, path: str) -> requests.Response:
        if not path.startswith("/"):
            path = f"/{path}"
        url = f"{self.base_url}{path}"
        try:
            response = self.session.get(url, headers=self._headers(), timeout=self.timeout_sec)
        except requests.Timeout as exc:
            raise HyskillsError(
                "UPSTREAM_TIMEOUT",
                f"upstream request timed out for {path}",
                status_code=504,
                path=path,
            ) from exc
        except requests.RequestException as exc:
            raise HyskillsError(
                "UPSTREAM_REQUEST_FAILED",
                str(exc),
                status_code=502,
                path=path,
            ) from exc
        if response.status_code in {401, 403}:
            raise HyskillsError(
                "UPSTREAM_UNAUTHORIZED",
                "hyskills upstream rejected the request; update HYSKILLS_COOKIE or HYSKILLS_AUTH_HEADER",
                status_code=502,
                upstream_status=response.status_code,
                path=path,
            )
        if response.status_code == 404:
            raise HyskillsError(
                "UPSTREAM_NOT_FOUND",
                f"hyskills upstream path not found: {path}",
                status_code=404,
                upstream_status=response.status_code,
                path=path,
            )
        if response.status_code >= 400:
            raise HyskillsError(
                "UPSTREAM_HTTP_ERROR",
                f"hyskills upstream returned HTTP {response.status_code}",
                status_code=502,
                upstream_status=response.status_code,
                path=path,
            )
        return response


def create_app(
    *,
    client: HyskillsClient | None = None,
    base_url: str = DEFAULT_BASE_URL,
    cache_ttl_sec: float = DEFAULT_CACHE_TTL_SECONDS,
    service_token: str | None = None,
) -> FastAPI:
    hyskills_client = client or HyskillsClient(base_url=base_url, cache_ttl_sec=cache_ttl_sec)
    required_token = service_token if service_token is not None else os.environ.get("HYSKILLS_SERVICE_TOKEN", "")

    app = FastAPI(title="hyskills local search service", version="0.1.0")
    app.state.hyskills_client = hyskills_client
    app.state.required_token = str(required_token or "")

    async def require_token(authorization: str | None = Header(default=None)) -> None:
        token = str(app.state.required_token or "")
        if not token:
            return
        expected = f"Bearer {token}"
        if authorization != expected:
            raise HyskillsError("UNAUTHORIZED", "missing or invalid service token", status_code=401)

    @app.exception_handler(HyskillsError)
    async def _hyskills_error_handler(_request: Request, exc: HyskillsError) -> JSONResponse:
        return JSONResponse(exc.to_payload(), status_code=exc.status_code)

    @app.get("/health", dependencies=[Depends(require_token)])
    def health() -> dict[str, Any]:
        return hyskills_client.health()

    @app.get("/skills/search", dependencies=[Depends(require_token)])
    def search_skills(
        q: str = "",
        tag: str = "",
        author: str = "",
        project: str = "",
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return hyskills_client.search(
            q=q,
            tag=tag,
            author=author,
            project=project,
            limit=limit,
            offset=offset,
        )

    @app.get("/skills/{skill_id}", dependencies=[Depends(require_token)])
    def read_skill(skill_id: str) -> dict[str, Any]:
        return hyskills_client.read_skill(skill_id)

    @app.get("/cache", dependencies=[Depends(require_token)])
    def cache() -> dict[str, Any]:
        return hyskills_client.cache_snapshot()

    @app.post("/cache/refresh", dependencies=[Depends(require_token)])
    def refresh_cache() -> dict[str, Any]:
        return hyskills_client.refresh()

    return app


def clean_frontmatter(markdown: str) -> str:
    return FRONTMATTER_RE.sub("", str(markdown or ""))


def serve_forever(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local hyskills search/read HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--cache-ttl-sec", type=float, default=DEFAULT_CACHE_TTL_SECONDS)
    parser.add_argument("--token", default=None, help="optional local Bearer token")
    args = parser.parse_args(argv)
    app = create_app(
        base_url=args.base_url,
        cache_ttl_sec=args.cache_ttl_sec,
        service_token=args.token,
    )
    uvicorn.run(app, host=args.host, port=args.port)


def _manifest_skills(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    skills = manifest.get("skills", [])
    if not isinstance(skills, list):
        return []
    return [skill for skill in skills if isinstance(skill, dict)]


def _visible_skills(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [skill for skill in _manifest_skills(manifest) if _is_visible_skill(skill)]


def _is_visible_skill(skill: dict[str, Any]) -> bool:
    return _matches_project(skill, VISIBLE_PROJECT_ID)


def _find_skill(skills: list[dict[str, Any]], skill_id: str) -> dict[str, Any] | None:
    needle = str(skill_id or "").strip()
    needle_fold = needle.casefold()
    for skill in skills:
        candidates = {_skill_id(skill), str(skill.get("name") or "")}
        if any(candidate == needle for candidate in candidates):
            return skill
        if any(candidate.casefold() == needle_fold for candidate in candidates):
            return skill
    return None


def _skill_id(skill: dict[str, Any]) -> str:
    return str(skill.get("id") or skill.get("name") or "").strip()


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _matches_all_tags(skill: dict[str, Any], tags: list[str]) -> bool:
    skill_tags = {str(tag).casefold() for tag in skill.get("tags", []) if tag is not None}
    return all(tag.casefold() in skill_tags for tag in tags)


def _matches_query(skill: dict[str, Any], query: str) -> bool:
    tags = " ".join(str(tag) for tag in skill.get("tags", []) if tag is not None)
    haystacks = [
        skill.get("id"),
        skill.get("name"),
        skill.get("display_name"),
        skill.get("description"),
        skill.get("author"),
        tags,
    ]
    return any(query in str(value or "").casefold() for value in haystacks)


def _matches_project(skill: dict[str, Any], project_filter: str) -> bool:
    project_id = str(skill.get("project_id") or "").strip().casefold()
    if project_id:
        return project_id == project_filter
    tags = [str(tag or "").casefold() for tag in skill.get("tags", [])]
    if project_filter in tags:
        return True
    fields = [
        skill.get("source"),
        skill.get("name"),
        skill.get("display_name"),
        skill.get("path"),
        skill.get("install_url"),
    ]
    return any(project_filter in str(value or "").casefold() for value in fields)


def _normalize_author(name: Any) -> str:
    value = str(name or "").strip()
    return re.sub(r"@.*$", "", value).strip() or value


def _skill_summary(
    skill: dict[str, Any],
    *,
    manifest: dict[str, Any],
    stats: dict[str, Any],
    base_url: str,
) -> dict[str, Any]:
    skill_id = _skill_id(skill)
    total_stats = stats.get("total", {}) if isinstance(stats, dict) else {}
    hot_stats = stats.get("hot", {}) if isinstance(stats, dict) else {}
    trending_stats = stats.get("trending", {}) if isinstance(stats, dict) else {}
    return {
        "id": skill_id,
        "name": skill.get("name") or skill_id,
        "display_name": skill.get("display_name"),
        "description": skill.get("description") or "",
        "author": skill.get("author") or "",
        "normalized_author": _normalize_author(skill.get("author")),
        "tags": [str(tag) for tag in skill.get("tags", []) if tag is not None],
        "project_id": skill.get("project_id"),
        "path": skill.get("path"),
        "added_at": skill.get("added_at"),
        "install_url": skill.get("install_url"),
        "svn_urls": skill.get("svn_urls") if isinstance(skill.get("svn_urls"), list) else [],
        "install_command": skill.get("install_command"),
        "install_commands": _install_commands(skill, manifest),
        "heat": {
            "total": _stat_value(total_stats, skill),
            "hot": _stat_value(hot_stats, skill),
            "trending": _stat_value(trending_stats, skill),
        },
        "detail_url": _detail_url(base_url, skill_id),
        "download_url": _download_url(base_url, skill_id),
    }


def _stat_value(values: Any, skill: dict[str, Any]) -> int:
    if not isinstance(values, dict):
        return 0
    for key in (_skill_id(skill), str(skill.get("name") or "")):
        value = values.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return 0


def _install_commands(skill: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, str]]:
    custom = str(skill.get("install_command") or "").strip()
    if custom:
        return [{"label": "install command", "command": custom, "source": "install_command"}]

    commands: list[dict[str, str]] = []
    repo_url = str(manifest.get("repo_url") or "").rstrip("/")
    skill_id = _skill_id(skill)
    path = str(skill.get("path") or "").strip()
    if repo_url and path:
        dir_name = path.replace("\\", "/").rstrip("/").split("/")[-1] or skill_id
        commands.append(
            {
                "label": "install command",
                "command": f"npx skills add {repo_url} --skill {dir_name} --yes",
                "source": "path",
            }
        )

    svn_urls = skill.get("svn_urls")
    if isinstance(svn_urls, list):
        for index, url in enumerate(svn_urls):
            url_text = str(url or "").strip()
            if not url_text:
                continue
            label = "install command (SVN)" if len(svn_urls) == 1 else f"install command (SVN {index + 1})"
            commands.append({"label": label, "command": f"安装技能 {url_text}", "source": "svn_urls"})

    install_url = str(skill.get("install_url") or "").strip()
    if not commands and install_url:
        commands.append({"label": "install command", "command": f"安装技能 {install_url}", "source": "install_url"})
    return commands


def _detail_url(base_url: str, skill_id: str) -> str:
    return f"{base_url.rstrip('/')}/skill-detail.html?name={quote(skill_id, safe='')}"


def _download_url(base_url: str, skill_id: str) -> str:
    return f"{base_url.rstrip('/')}/api/download/{quote(skill_id, safe='')}"
