"""Configuration loader — reads .env, config.yaml, and the file list."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class AppConfig:
    """Holds all runtime configuration."""

    # SFTP connection
    sftp_host: str
    sftp_port: int
    sftp_user: str
    sftp_password: str

    # Paths
    file_list_path: Path
    download_dir: Path
    remote_paths: list[str] = field(default_factory=list)

    # Scheduling (None = start immediately)
    scheduled_at: Optional[datetime] = None

    # Retry
    max_retries: int = 3
    retry_delay: float = 5.0  # seconds


def load_config(
    env_path: str | Path = ".env",
    config_path: str | Path = "config.yaml",
) -> AppConfig:
    """Build an ``AppConfig`` from .env + config.yaml + file list."""

    # ── .env ──────────────────────────────────────────────────────────
    load_dotenv(env_path)

    sftp_host = _require_env("SFTP_HOST")
    sftp_port = int(os.getenv("SFTP_PORT", "22"))
    sftp_user = _require_env("SFTP_USER")
    sftp_password = _require_env("SFTP_PASSWORD")

    file_list_path = Path(os.getenv("FILE_LIST", "files_to_download.txt"))
    download_dir = Path(os.getenv("DOWNLOAD_DIR", "./downloads"))

    # ── config.yaml (optional) ────────────────────────────────────────
    scheduled_at = _parse_schedule(Path(config_path))

    # ── file list ─────────────────────────────────────────────────────
    remote_paths = _parse_file_list(file_list_path)

    return AppConfig(
        sftp_host=sftp_host,
        sftp_port=sftp_port,
        sftp_user=sftp_user,
        sftp_password=sftp_password,
        file_list_path=file_list_path,
        download_dir=download_dir,
        remote_paths=remote_paths,
        scheduled_at=scheduled_at,
    )


# ── helpers ───────────────────────────────────────────────────────────────


def _require_env(name: str) -> str:
    """Return an env-var value or exit with a clear error."""
    value = os.getenv(name)
    if not value:
        print(f"❌  Missing required environment variable: {name}", file=sys.stderr)
        print(f"   Set it in your .env file.  See .env.example.", file=sys.stderr)
        sys.exit(1)
    return value


def _parse_schedule(config_path: Path) -> Optional[datetime]:
    """Read schedule.date + schedule.time from config.yaml, if present."""
    if not config_path.is_file():
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "schedule" not in data:
        return None

    sched = data["schedule"]
    if not sched:
        return None

    date_str = sched.get("date")
    time_str = sched.get("time", "00:00")

    if not date_str:
        return None

    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError as exc:
        print(
            f"⚠️  Invalid schedule format in {config_path}: {exc}",
            file=sys.stderr,
        )
        return None


def _parse_file_list(path: Path) -> list[str]:
    """Read one remote path per line; skip blanks and comments."""
    if not path.is_file():
        print(f"❌  File list not found: {path}", file=sys.stderr)
        sys.exit(1)

    paths: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            paths.append(line)

    if not paths:
        print(f"⚠️  File list is empty: {path}", file=sys.stderr)

    return paths
