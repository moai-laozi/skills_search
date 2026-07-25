from __future__ import annotations

import base64
import logging
import os
import time
from collections.abc import Iterator
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


class GitHubAPIError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, config: dict[str, Any], token: str | None = None) -> None:
        github_cfg = config["github"]
        token = token or os.getenv(str(github_cfg["token_env"])) or os.getenv(str(github_cfg["fallback_token_env"]))
        if not token:
            raise GitHubAPIError(
                f"No GitHub token found. Set {github_cfg['token_env']} or {github_cfg['fallback_token_env']}."
            )
        self.api_url = str(github_cfg["api_url"]).rstrip("/")
        self.timeout = int(github_cfg["request_timeout_seconds"])
        self.request_interval = float(github_cfg.get("request_interval_seconds", 0.15))
        self.max_retries = int(github_cfg["max_retries"])
        self.max_retry_wait = int(github_cfg["max_retry_wait_seconds"])
        self.search_interval = float(github_cfg["search_interval_seconds"])
        self.max_file_bytes = int(github_cfg["max_file_bytes"])
        self._last_request = 0.0
        self._last_search_request = 0.0
        self._repo_cache: dict[str, dict[str, Any]] = {}

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": str(github_cfg["api_version"]),
                "User-Agent": "skill-harvester/0.1",
            }
        )

    def _throttle_general(self) -> None:
        elapsed = time.monotonic() - self._last_request
        wait = self.request_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _throttle_search(self) -> None:
        elapsed = time.monotonic() - self._last_search_request
        wait = self.search_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_search_request = time.monotonic()

    def _request(self, method: str, url: str, *, search_request: bool = False, **kwargs: Any) -> requests.Response:
        self._throttle_general()
        if search_request:
            self._throttle_search()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 15))
                continue

            if response.status_code in {429, 502, 503, 504}:
                if attempt >= self.max_retries:
                    return response
                retry_after = int(response.headers.get("Retry-After", "0") or 0)
                time.sleep(min(self.max_retry_wait, max(retry_after, 2**attempt)))
                continue

            if response.status_code == 403 and (
                response.headers.get("X-RateLimit-Remaining") == "0"
                or "rate limit" in response.text.lower()
            ):
                reset = int(response.headers.get("X-RateLimit-Reset", "0") or 0)
                wait = max(1, reset - int(time.time()) + 1) if reset else 10
                if wait > self.max_retry_wait or attempt >= self.max_retries:
                    raise GitHubAPIError(
                        f"GitHub rate limit exceeded; reset wait is {wait}s. Reduce queries or rerun later."
                    )
                LOGGER.warning("Rate limited by GitHub; sleeping %s seconds.", wait)
                time.sleep(wait)
                continue

            if response.status_code >= 400:
                message = response.text[:500]
                raise GitHubAPIError(f"GitHub API {response.status_code} for {url}: {message}")
            return response

        raise GitHubAPIError(f"GitHub request failed for {url}: {last_error}")

    def search_code(self, query: str, *, per_page: int, max_pages: int) -> Iterator[dict[str, Any]]:
        endpoint = f"{self.api_url}/search/code"
        for page in range(1, max_pages + 1):
            response = self._request(
                "GET",
                endpoint,
                search_request=True,
                params={
                    "q": query,
                    "per_page": min(100, per_page),
                    "page": page,
                    "sort": "indexed",
                    "order": "desc",
                },
            )
            payload = response.json()
            items = payload.get("items", [])
            if not isinstance(items, list):
                return
            yield from items
            if len(items) < min(100, per_page):
                return

    def get_repository(self, repository_url: str) -> dict[str, Any]:
        if repository_url not in self._repo_cache:
            response = self._request("GET", repository_url)
            self._repo_cache[repository_url] = response.json()
        return self._repo_cache[repository_url]

    def get_code_content(self, content_url: str) -> tuple[str, str, str | None]:
        response = self._request("GET", content_url)
        payload = response.json()
        if isinstance(payload, list):
            raise GitHubAPIError(f"Expected a file but received a directory: {content_url}")
        size = int(payload.get("size") or 0)
        if size > self.max_file_bytes:
            raise GitHubAPIError(f"SKILL.md is too large ({size} bytes): {content_url}")

        encoded = payload.get("content")
        encoding = payload.get("encoding")
        if encoded and encoding == "base64":
            raw = base64.b64decode(encoded, validate=False)
        elif payload.get("download_url"):
            raw_response = self._request("GET", str(payload["download_url"]))
            raw = raw_response.content
        else:
            raise GitHubAPIError(f"No downloadable content returned for {content_url}")

        if len(raw) > self.max_file_bytes:
            raise GitHubAPIError(f"SKILL.md exceeds max_file_bytes: {content_url}")
        return raw.decode("utf-8", errors="replace"), str(payload.get("sha") or ""), payload.get("download_url")
