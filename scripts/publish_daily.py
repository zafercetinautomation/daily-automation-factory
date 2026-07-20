#!/usr/bin/env python3
"""Generate, validate, and optionally publish one small AI automation project."""

from __future__ import annotations

import argparse
import ast
import base64
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "config" / "settings.json"
IDEAS_PATH = ROOT / "config" / "project_ideas.json"
FIXTURE_PATH = ROOT / "fixtures" / "sample_project.json"

PROFILE_START = "<!-- DAILY_PROJECTS:START -->"
PROFILE_END = "<!-- DAILY_PROJECTS:END -->"

ALLOWED_EXACT_FILENAMES = {
    ".env.example",
    ".gitattributes",
    ".gitignore",
    "LICENSE",
    "README.md",
    "pyproject.toml",
}
ALLOWED_SUFFIXES = {
    ".py",
    ".md",
    ".json",
    ".toml",
    ".txt",
    ".csv",
    ".st",
    ".xml",
    ".TcPOU",
    ".TcGVL",
    ".TcDUT",
}
REQUIRED_FILES = {
    ".gitattributes",
    "LICENSE",
    "README.md",
    "plc/MAIN.st",
    "pyproject.toml",
    "src/main.py",
    "tests/test_main.py",
}
BLOCKED_TEXT_PATTERNS = {
    "github_pat_": "a GitHub token-like value",
    "ghp_": "a GitHub token-like value",
    "-----BEGIN PRIVATE KEY-----": "a private key",
    "${{ secrets.": "a GitHub secret expression",
    "AT %": "a direct hardware I/O mapping",
}
BLOCKED_IMPORTS = {"ctypes", "resource", "socket", "subprocess"}
BLOCKED_CALLS = {"__import__", "compile", "eval", "exec"}
MAX_FILE_CHARS = 30_000
MAX_TOTAL_CHARS = 140_000


PROJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "slug": {
            "type": "string",
            "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
            "minLength": 3,
            "maxLength": 48,
        },
        "title": {"type": "string", "minLength": 3, "maxLength": 80},
        "description": {"type": "string", "minLength": 20, "maxLength": 220},
        "files": {
            "type": "array",
            "minItems": 5,
            "maxItems": 14,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "path": {
                        "type": "string",
                        "pattern": "^(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+$",
                        "maxLength": 120,
                    },
                    "content": {"type": "string", "maxLength": MAX_FILE_CHARS},
                },
                "required": ["path", "content"],
            },
        },
    },
    "required": ["slug", "title", "description", "files"],
}


class PublisherError(RuntimeError):
    """A safe, user-readable publisher failure."""


@dataclass(frozen=True)
class ProjectIdea:
    slug: str
    title: str
    brief: str
    category: str


@dataclass(frozen=True)
class ProjectFile:
    path: str
    content: str


@dataclass(frozen=True)
class GeneratedProject:
    slug: str
    title: str
    description: str
    files: tuple[ProjectFile, ...]


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublisherError(f"Could not read valid JSON from {path}: {exc}") from exc


def load_settings() -> dict[str, Any]:
    settings = load_json(SETTINGS_PATH)
    required = {
        "timezone",
        "launch_date",
        "model",
        "max_output_tokens",
        "repository_prefix",
        "profile_project_limit",
        "topics",
    }
    missing = required - settings.keys()
    if missing:
        raise PublisherError(f"Missing settings: {', '.join(sorted(missing))}")
    return settings


def load_ideas() -> list[ProjectIdea]:
    raw_ideas = load_json(IDEAS_PATH)
    if not isinstance(raw_ideas, list) or not raw_ideas:
        raise PublisherError("The project idea queue must be a non-empty JSON list.")
    try:
        return [ProjectIdea(**item) for item in raw_ideas]
    except (TypeError, KeyError) as exc:
        raise PublisherError(f"Invalid project idea: {exc}") from exc


def parse_date(value: str | None, timezone_name: str) -> date:
    if value:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise PublisherError("--date must use YYYY-MM-DD format.") from exc
    return datetime.now(ZoneInfo(timezone_name)).date()


def select_idea(target_date: date, launch_date: date, ideas: list[ProjectIdea]) -> ProjectIdea:
    index = (target_date - launch_date).days % len(ideas)
    return ideas[index]


def repository_name(settings: dict[str, Any], target_date: date, idea: ProjectIdea) -> str:
    prefix = str(settings["repository_prefix"]).strip("-")
    value = f"{prefix}-{target_date:%Y%m%d}-{idea.slug}"
    if len(value) > 100:
        raise PublisherError("Generated repository name exceeds GitHub's 100 character limit.")
    return value


def render_fixture(idea: ProjectIdea) -> dict[str, Any]:
    template = FIXTURE_PATH.read_text(encoding="utf-8")
    replacements = {
        "{{SLUG}}": idea.slug,
        "{{TITLE}}": idea.title,
        "{{DESCRIPTION}}": idea.brief,
    }
    for source, target in replacements.items():
        template = template.replace(source, target)
    try:
        return json.loads(template)
    except json.JSONDecodeError as exc:
        raise PublisherError(f"Dry-run fixture is invalid: {exc}") from exc


def generation_instructions() -> str:
    return """
Öğrenciler için portföy kalitesinde, küçük bir Beckhoff TwinCAT 3 / PLC
eğitim deposu oluştur.

Yalnızca verilen şemaya uyan JSON nesnesini döndür. Şu kurallara uy:
- IEC 61131-3 Structured Text ile bir PLC örneği ve yalnızca standart kütüphaneyi
  kullanan Python 3.11+ simülasyonu yap.
- Tek bir otomasyon senaryosuna, açık giriş/çıkışlara ve tekrarlanabilir çıktılara odaklan.
- Açıklanabilir kurallar veya sağlayıcı arayüzü kullan; yapay zekâ doğruluğunu garanti etme.
- Şu temel yollar mutlaka olsun: README.md, LICENSE, .gitattributes, plc/MAIN.st,
  pyproject.toml, src/main.py, tests/test_main.py. examples/ altında küçük örnekler
  ekleyebilirsin.
- GitHub'ın `.st` dosyalarını Smalltalk olarak sınıflandırmaması için `.gitattributes`
  dosyasında `*.st -linguist-detectable` satırı bulunsun.
- plc/MAIN.st dosyası TwinCAT 3 ile uyumlu, öğretici yorumlara sahip Structured Text
  kodu içersin. Doğrudan I/O adresi kullanma; sembolik giriş/çıkış değişkenleri kullan.
- Python simülasyonu PLC mantığını donanım olmadan taklit etsin; testler temel
  senaryoları ve kilitlemeleri doğrulasın.
- README.md tamamen Türkçe olsun; hızlı başlangıç, örnek girdi/çıktı, sınırlamalar,
  gizlilik notları ve portföye uygun net bir açıklama içersin.
- README'de TwinCAT'a aktarım adımları, değişken tablosu, öğrenciler için deneyler
  ve Beckhoff resmî başlangıç belgesine bağlantı bulunsun:
  https://infosys.beckhoff.com/content/1033/tc3_system/2525041803.html
- Her README açıkça "Eğitim ve simülasyon amaçlıdır" desin. Gerçek makinede kullanım
  öncesinde risk analizi, emniyet doğrulaması ve yetkin uzman incelemesi gerektiğini;
  standart PLC kodunun sertifikalı emniyet fonksiyonu olmadığını belirt.
- Depo açıklaması ve kullanıcıya gösterilen CLI mesajları Türkçe olsun.
- Testlerde unittest kullan; ağ bağlantısına, ortam sırlarına veya geçici dizin dışındaki
  dosya sistemine erişme.
- İş akışı, kilit dosyası, ikili dosya, görsel, gizli çalıştırılabilir dosya veya bağımlılık oluşturma.
- subprocess, socket, ctypes, eval, exec, dinamik import, kabuk komutu, telemetri,
  kimlik bilgisi toplama, yıkıcı dosya işlemi ya da gizlenmiş/kodlanmış kaynak kullanma.
- Gerçek sırları asla ekleme. Gerekirse .env.example içinde açık bir örnek değer kullan.
- Dosyaları küçük ve okunabilir tut. Yararlı yerlerde tip ipuçları ve kısa docstring ekle.
- slug, istenen slug ile birebir aynı olmalı.
""".strip()


def generation_prompt(idea: ProjectIdea, target_date: date) -> str:
    return (
        f"Tarih: {target_date.isoformat()}\n"
        f"Zorunlu slug: {idea.slug}\n"
        f"Proje başlığı: {idea.title}\n"
        f"Kategori: {idea.category}\n"
        f"Ürün özeti: {idea.brief}\n\n"
        "Bu özeti, bir öğrencinin beş dakikadan kısa sürede anlayıp simülasyonu "
        "çalıştırabileceği küçük ve tamamen Türkçe anlatımlı bir TwinCAT/PLC eğitim "
        "deposuna dönüştür."
    )


def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
    attempts: int = 3,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Accept": "application/json", **headers}
    if body is not None:
        request_headers["Content-Type"] = "application/json"

    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")[:1200]
            if exc.code == 429 or 500 <= exc.code < 600:
                if attempt + 1 < attempts:
                    time.sleep(2**attempt)
                    continue
            raise PublisherError(f"{method} {url} failed with HTTP {exc.code}: {error_body}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
                continue
            raise PublisherError(f"{method} {url} failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise PublisherError(f"{method} {url} returned invalid JSON.") from exc

    raise PublisherError(f"{method} {url} failed after retries.")


def call_openai(
    *,
    api_key: str,
    model: str,
    idea: ProjectIdea,
    target_date: date,
    max_output_tokens: int,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "instructions": generation_instructions(),
        "input": generation_prompt(idea, target_date),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "daily_automation_project",
                "strict": True,
                "schema": PROJECT_SCHEMA,
            }
        },
        "max_output_tokens": max_output_tokens,
    }
    _, response = http_json(
        "POST",
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}"},
        payload=payload,
        timeout=180,
    )
    output_text = extract_output_text(response)
    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise PublisherError("OpenAI returned output that was not valid JSON.") from exc


def extract_output_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise PublisherError("OpenAI response did not contain output_text.")


def validate_path(raw_path: str) -> str:
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise PublisherError(f"Unsafe project path: {raw_path}")
    if "\\" in raw_path or raw_path.startswith(".github/"):
        raise PublisherError(f"Disallowed project path: {raw_path}")
    if raw_path not in ALLOWED_EXACT_FILENAMES and path.suffix not in ALLOWED_SUFFIXES:
        raise PublisherError(f"Disallowed file type: {raw_path}")
    return path.as_posix()


def dotted_name(node: ast.AST) -> str:
    parts: list[str] = []
    cursor: ast.AST | None = node
    while isinstance(cursor, ast.Attribute):
        parts.append(cursor.attr)
        cursor = cursor.value
    if isinstance(cursor, ast.Name):
        parts.append(cursor.id)
    return ".".join(reversed(parts))


def validate_python(path: str, content: str) -> None:
    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError as exc:
        raise PublisherError(f"Python syntax error in {path}: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
            blocked = roots & BLOCKED_IMPORTS
            if blocked:
                raise PublisherError(f"Blocked import in {path}: {', '.join(sorted(blocked))}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in BLOCKED_IMPORTS:
                raise PublisherError(f"Blocked import in {path}: {root}")
        elif isinstance(node, ast.Call):
            name = dotted_name(node.func)
            root_name = name.rsplit(".", 1)[-1]
            if root_name in BLOCKED_CALLS or name in {"os.popen", "os.system", "shutil.rmtree"}:
                raise PublisherError(f"Blocked call in {path}: {name}")


def validate_project(payload: dict[str, Any], expected_slug: str) -> GeneratedProject:
    if not isinstance(payload, dict):
        raise PublisherError("Generated project must be a JSON object.")

    required_keys = {"slug", "title", "description", "files"}
    if set(payload) != required_keys:
        raise PublisherError("Generated project has missing or unexpected top-level fields.")

    slug = payload["slug"]
    title = payload["title"]
    description = payload["description"]
    raw_files = payload["files"]

    if slug != expected_slug:
        raise PublisherError(f"Generated slug {slug!r} does not match {expected_slug!r}.")
    if not isinstance(title, str) or not 3 <= len(title) <= 80:
        raise PublisherError("Generated title has an invalid length.")
    if not isinstance(description, str) or not 20 <= len(description) <= 220:
        raise PublisherError("Generated description has an invalid length.")
    if not isinstance(raw_files, list) or not 5 <= len(raw_files) <= 14:
        raise PublisherError("Generated project must contain between 5 and 14 files.")

    seen: set[str] = set()
    project_files: list[ProjectFile] = []
    total_chars = 0
    for item in raw_files:
        if not isinstance(item, dict) or set(item) != {"path", "content"}:
            raise PublisherError("Every generated file needs only path and content fields.")
        raw_path = item["path"]
        content = item["content"]
        if not isinstance(raw_path, str) or not isinstance(content, str):
            raise PublisherError("Generated file path and content must be strings.")
        path = validate_path(raw_path)
        if path in seen:
            raise PublisherError(f"Duplicate generated file: {path}")
        if len(content) > MAX_FILE_CHARS:
            raise PublisherError(f"Generated file is too large: {path}")

        for pattern, label in BLOCKED_TEXT_PATTERNS.items():
            if pattern.lower() in content.lower():
                raise PublisherError(f"Generated file {path} contains {label}.")
        if re.search(r"\bsk-[A-Za-z0-9_-]{20,}\b", content):
            raise PublisherError(f"Generated file {path} contains an OpenAI key-like value.")
        if path.endswith(".py"):
            validate_python(path, content)
        if path == "plc/MAIN.st":
            upper_content = content.upper()
            if "PROGRAM MAIN" not in upper_content or "END_PROGRAM" not in upper_content:
                raise PublisherError(
                    "plc/MAIN.st must contain PROGRAM MAIN and END_PROGRAM."
                )

        seen.add(path)
        total_chars += len(content)
        project_files.append(ProjectFile(path=path, content=content))

    missing_files = REQUIRED_FILES - seen
    if missing_files:
        raise PublisherError(f"Generated project is missing: {', '.join(sorted(missing_files))}")
    if total_chars > MAX_TOTAL_CHARS:
        raise PublisherError("Generated project exceeds the total size limit.")

    return GeneratedProject(
        slug=slug,
        title=title,
        description=" ".join(description.split()),
        files=tuple(project_files),
    )


def write_build(project: GeneratedProject, repo_name: str) -> Path:
    build_dir = ROOT / "build" / repo_name
    if build_dir.exists():
        shutil.rmtree(build_dir)
    for project_file in project.files:
        destination = build_dir / project_file.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(project_file.content, encoding="utf-8")
    return build_dir


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "daily-industrial-automation-factory",
        }
        self.base_url = "https://api.github.com"

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        attempts: int = 3,
    ) -> tuple[int, dict[str, Any]]:
        return http_json(
            method,
            f"{self.base_url}{path}",
            headers=self._headers,
            payload=payload,
            attempts=attempts,
        )

    def current_user(self) -> str:
        _, payload = self.request("GET", "/user")
        login = payload.get("login")
        if not isinstance(login, str) or not login:
            raise PublisherError("GitHub /user response did not contain a login.")
        return login

    def get_repository(self, owner: str, repo: str) -> dict[str, Any] | None:
        path = f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
        try:
            _, payload = self.request("GET", path, attempts=1)
            return payload
        except PublisherError as exc:
            if "HTTP 404" in str(exc):
                return None
            raise

    def create_repository(
        self,
        *,
        repo_name: str,
        description: str,
    ) -> dict[str, Any]:
        _, payload = self.request(
            "POST",
            "/user/repos",
            payload={
                "name": repo_name,
                "description": description,
                "private": False,
                "auto_init": True,
                "has_issues": True,
                "has_projects": False,
                "has_wiki": False,
                "delete_branch_on_merge": True,
            },
        )
        return payload

    def upload_project(
        self,
        *,
        owner: str,
        repo: str,
        branch: str,
        project: GeneratedProject,
        target_date: date,
    ) -> str:
        owner_q = urllib.parse.quote(owner)
        repo_q = urllib.parse.quote(repo)
        branch_q = urllib.parse.quote(branch, safe="")

        ref_payload: dict[str, Any] | None = None
        for attempt in range(4):
            try:
                _, ref_payload = self.request(
                    "GET",
                    f"/repos/{owner_q}/{repo_q}/git/ref/heads/{branch_q}",
                    attempts=1,
                )
                break
            except PublisherError:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
        if ref_payload is None:
            raise PublisherError("Could not read the initialized repository branch.")

        parent_sha = ref_payload["object"]["sha"]
        _, commit_payload = self.request(
            "GET",
            f"/repos/{owner_q}/{repo_q}/git/commits/{parent_sha}",
        )
        base_tree_sha = commit_payload["tree"]["sha"]
        tree_entries = [
            {
                "path": project_file.path,
                "mode": "100644",
                "type": "blob",
                "content": project_file.content,
            }
            for project_file in project.files
        ]
        _, tree_payload = self.request(
            "POST",
            f"/repos/{owner_q}/{repo_q}/git/trees",
            payload={"base_tree": base_tree_sha, "tree": tree_entries},
        )
        _, new_commit = self.request(
            "POST",
            f"/repos/{owner_q}/{repo_q}/git/commits",
            payload={
                "message": f"feat: publish {project.title} ({target_date.isoformat()})",
                "tree": tree_payload["sha"],
                "parents": [parent_sha],
            },
        )
        self.request(
            "PATCH",
            f"/repos/{owner_q}/{repo_q}/git/refs/heads/{branch_q}",
            payload={"sha": new_commit["sha"], "force": False},
        )
        return new_commit["sha"]

    def set_topics(self, owner: str, repo: str, topics: list[str]) -> None:
        owner_q = urllib.parse.quote(owner)
        repo_q = urllib.parse.quote(repo)
        self.request(
            "PUT",
            f"/repos/{owner_q}/{repo_q}/topics",
            payload={"names": topics[:20]},
        )

    def update_profile(
        self,
        *,
        owner: str,
        project: GeneratedProject,
        project_url: str,
        limit: int,
    ) -> bool:
        owner_q = urllib.parse.quote(owner)
        path = f"/repos/{owner_q}/{owner_q}/contents/README.md"
        try:
            _, payload = self.request("GET", path, attempts=1)
        except PublisherError as exc:
            if "HTTP 404" in str(exc):
                print("Profile README repository was not found; skipping profile update.")
                return False
            raise

        encoded_content = payload.get("content")
        sha = payload.get("sha")
        if not isinstance(encoded_content, str) or not isinstance(sha, str):
            raise PublisherError("Profile README response was missing content or sha.")
        current = base64.b64decode(encoded_content).decode("utf-8")
        updated = update_profile_block(
            current,
            title=project.title,
            description=project.description,
            url=project_url,
            limit=limit,
        )
        if updated == current:
            return False
        self.request(
            "PUT",
            path,
            payload={
                "message": f"docs: add {project.title} to latest projects",
                "content": base64.b64encode(updated.encode("utf-8")).decode("ascii"),
                "sha": sha,
            },
        )
        return True


def update_profile_block(
    readme: str,
    *,
    title: str,
    description: str,
    url: str,
    limit: int,
) -> str:
    if readme.count(PROFILE_START) != 1 or readme.count(PROFILE_END) != 1:
        raise PublisherError("Profile README needs exactly one daily projects marker pair.")
    start_index = readme.index(PROFILE_START) + len(PROFILE_START)
    end_index = readme.index(PROFILE_END)
    if start_index > end_index:
        raise PublisherError("Profile README markers are in the wrong order.")

    existing_block = readme[start_index:end_index]
    existing_lines = [
        line.strip()
        for line in existing_block.splitlines()
        if line.strip().startswith("- [") and f"]({url})" not in line
    ]
    clean_description = " ".join(description.split())
    new_line = f"- [{title}]({url}) — {clean_description}"
    lines = [new_line, *existing_lines][: max(1, limit)]
    replacement = "\n" + "\n".join(lines) + "\n"
    return readme[:start_index] + replacement + readme[end_index:]


def record_history(
    *,
    target_date: date,
    repo_name: str,
    project_url: str,
    project: GeneratedProject,
    idea: ProjectIdea,
    model: str,
    commit_sha: str | None,
) -> Path:
    history_dir = ROOT / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    destination = history_dir / f"{target_date.isoformat()}.json"
    payload = {
        "date": target_date.isoformat(),
        "repository": repo_name,
        "url": project_url,
        "title": project.title,
        "description": project.description,
        "idea": {
            "slug": idea.slug,
            "category": idea.category,
        },
        "model": model,
        "commit_sha": commit_sha,
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def require_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise PublisherError(f"{name} is required for --publish.")
    return value


def run(args: argparse.Namespace) -> int:
    settings = load_settings()
    ideas = load_ideas()
    target_date = parse_date(args.date, settings["timezone"])
    launch_date = date.fromisoformat(settings["launch_date"])
    idea = select_idea(target_date, launch_date, ideas)
    repo_name = repository_name(settings, target_date, idea)
    model = os.getenv("OPENAI_MODEL", "").strip() or settings["model"]

    print(f"Date: {target_date.isoformat()}")
    print(f"Idea: {idea.title} ({idea.slug})")
    print(f"Repository: {repo_name}")

    if args.dry_run:
        payload = render_fixture(idea)
        project = validate_project(payload, idea.slug)
        build_dir = write_build(project, repo_name)
        print(f"Dry run complete: {build_dir}")
        return 0

    api_key = require_environment("OPENAI_API_KEY")
    github_token = require_environment("GH_PROFILE_TOKEN")
    github = GitHubClient(github_token)
    owner = github.current_user()
    existing = github.get_repository(owner, repo_name)
    if existing is not None:
        print(f"Repository already exists; nothing to publish: {existing.get('html_url')}")
        return 0

    payload = call_openai(
        api_key=api_key,
        model=model,
        idea=idea,
        target_date=target_date,
        max_output_tokens=int(settings["max_output_tokens"]),
    )
    project = validate_project(payload, idea.slug)

    created = github.create_repository(repo_name=repo_name, description=project.description)
    branch = created.get("default_branch") or "main"
    commit_sha = github.upload_project(
        owner=owner,
        repo=repo_name,
        branch=branch,
        project=project,
        target_date=target_date,
    )
    topics = list(dict.fromkeys([*settings["topics"], idea.category]))
    github.set_topics(owner, repo_name, topics)
    project_url = created.get("html_url") or f"https://github.com/{owner}/{repo_name}"
    github.update_profile(
        owner=owner,
        project=project,
        project_url=project_url,
        limit=int(settings["profile_project_limit"]),
    )
    history_path = record_history(
        target_date=target_date,
        repo_name=repo_name,
        project_url=project_url,
        project=project,
        idea=idea,
        model=model,
        commit_sha=commit_sha,
    )
    print(f"Published: {project_url}")
    print(f"History: {history_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Build a deterministic fixture locally without network access.",
    )
    mode.add_argument(
        "--publish",
        action="store_true",
        help="Generate with OpenAI and publish to GitHub.",
    )
    parser.add_argument("--date", help="Override the local date (YYYY-MM-DD).")
    return parser


def main() -> int:
    try:
        return run(build_parser().parse_args())
    except PublisherError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
