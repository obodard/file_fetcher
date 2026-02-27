"""Configuration loader — reads .env, config.yaml, and the file list."""

from __future__ import annotations

import os
import sys
import logging
import logging.handlers
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

    # Host-key verification (None = skip verification)
    sftp_host_key_fingerprint: Optional[str] = None

    # Retry
    max_retries: int = 3
    retry_delay: float = 5.0  # seconds

@dataclass
class SearchConfig:
    """Holds configuration for ADK-based intelligent search."""
    google_api_key: str
    gemini_model: str
    omdb_api_key: str


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
    sftp_host_key_fingerprint = os.getenv("SFTP_HOST_KEY_FINGERPRINT") or None

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
        sftp_host_key_fingerprint=sftp_host_key_fingerprint,
        file_list_path=file_list_path,
        download_dir=download_dir,
        remote_paths=remote_paths,
        scheduled_at=scheduled_at,
    )


def load_search_config(env_path: str | Path = ".env") -> SearchConfig:
    """Build a ``SearchConfig`` from .env."""
    load_dotenv(env_path)

    google_api_key = os.getenv("GOOGLE_API_KEY", "")
    if not google_api_key:
        print("❌  Missing GOOGLE_API_KEY — required for ADK agent.", file=sys.stderr)
        sys.exit(1)

    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    omdb_api_key = _require_env("OMDB_API_KEY")

    return SearchConfig(
        google_api_key=google_api_key,
        gemini_model=gemini_model,
        omdb_api_key=omdb_api_key,
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


class MaskingFilter(logging.Filter):
    """Filter to mask sensitive information in log records."""
    
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        # Filter out empty strings to avoid destroying all logs
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for secret in self.secrets:
                record.msg = record.msg.replace(secret, "***MASKED***")
        
        # If the log involves arguments
        if isinstance(record.args, tuple):
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    for secret in self.secrets:
                        arg = arg.replace(secret, "***MASKED***")
                new_args.append(arg)
            record.args = tuple(new_args)
            
        elif isinstance(record.args, dict):
            new_args = {}
            for k, v in record.args.items():
                if isinstance(v, str):
                    for secret in self.secrets:
                        v = v.replace(secret, "***MASKED***")
                new_args[k] = v
            record.args = new_args
            
        return True


def setup_logging(app_config: AppConfig, search_config: Optional[SearchConfig] = None) -> None:
    """Configure the root logger with a rotating file handler and masking filter."""
    logger = logging.getLogger("file_fetcher")
    logger.setLevel(logging.DEBUG)

    # Avoid adding multiple handlers if setup is called multiple times
    if logger.handlers:
        return

    # Rotating file handler (10 MB max, up to 3 backups)
    log_file = Path("file_fetcher.log")
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    
    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    
    # Secrets to mask
    secrets = [
        app_config.sftp_user,
        app_config.sftp_password,
    ]
    if search_config:
        secrets.extend([
            search_config.google_api_key,
            search_config.omdb_api_key
        ])

    masking_filter = MaskingFilter(secrets=secrets)
    handler.addFilter(masking_filter)
    
    logger.addHandler(handler)
    logger.info("Logging initialized.")
