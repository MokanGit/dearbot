#!/usr/bin/env python3
"""Read-only readiness checks for the beginner DearBot onboarding path."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def run(command: list[str], cwd: Path, timeout: int = 10) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (result.stdout or result.stderr).strip()
        return result.returncode == 0, output
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def add(checks: list[dict[str, str]], name: str, status: str, message: str) -> None:
    checks.append({"name": name, "status": status, "message": message})


def inspect(repo: Path) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    required = ["README.md", ".env.example", "docker-compose.yml", "backend", "frontend"]
    missing = [item for item in required if not (repo / item).exists()]
    add(
        checks,
        "repository",
        "error" if missing else "pass",
        f"Missing required paths: {', '.join(missing)}" if missing else "DearBot repository layout detected.",
    )

    docker = shutil.which("docker")
    add(checks, "docker_cli", "pass" if docker else "error", "Docker CLI found." if docker else "Install Docker before continuing.")
    if docker:
        compose_ok, _ = run([docker, "compose", "version"], repo)
        add(checks, "docker_compose", "pass" if compose_ok else "error", "Docker Compose is available." if compose_ok else "Docker Compose is unavailable.")
        engine_ok, _ = run([docker, "info"], repo)
        add(checks, "docker_engine", "pass" if engine_ok else "error", "Docker engine is running." if engine_ok else "Start the Docker engine before launching DearBot.")

    env_path = repo / ".env"
    add(checks, "environment_file", "pass" if env_path.exists() else "action", ".env exists." if env_path.exists() else "Copy .env.example to .env and keep beginner-safe defaults.")

    sync_dir = repo / "backend" / "data" / "synced_docs"
    if not sync_dir.is_dir():
        add(checks, "evidence_directory", "error", "backend/data/synced_docs is missing.")
    else:
        markdown_count = sum(1 for path in sync_dir.glob("*.md") if path.name != ".gitkeep")
        add(checks, "evidence_directory", "pass", "Ignored local evidence directory exists.")
        add(checks, "evidence_documents", "pass" if markdown_count else "action", f"{markdown_count} local Markdown evidence document(s) found." if markdown_count else "Create the internal master evidence bank.")

        ignored_ok, _ = run(["git", "check-ignore", "-q", "backend/data/synced_docs/onboarding-check.md"], repo)
        add(checks, "evidence_gitignore", "pass" if ignored_ok else "error", "Candidate evidence is excluded from Git." if ignored_ok else "Stop: candidate evidence is not excluded from Git.")

    git_ok, git_output = run(["git", "status", "--porcelain"], repo)
    if not git_ok:
        add(checks, "git_status", "warning", "Could not inspect Git status.")
    else:
        add(checks, "git_status", "warning" if git_output else "pass", "Repository has existing changes; preserve unrelated work." if git_output else "Repository working tree is clean.")

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    repo = args.repo.expanduser().resolve()
    checks = inspect(repo)
    if args.as_json:
        print(json.dumps({"repo": str(repo), "checks": checks}, indent=2))
    else:
        for check in checks:
            print(f"[{check['status'].upper():7}] {check['name']}: {check['message']}")

    return 1 if any(check["status"] == "error" for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
