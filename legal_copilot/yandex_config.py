"""Shared helpers for loading Yandex GPT configuration from local files."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_YANDEX_API_KEY_PATH = PROJECT_ROOT / "config" / "yandex_api_key.txt"
DEFAULT_YANDEX_FOLDER_ID_PATH = PROJECT_ROOT / "config" / "yandex_folder_id.txt"
DEFAULT_YANDEX_BASE_URL = "https://ai.api.cloud.yandex.net/v1"


def _load_required_text(path: Path, label: str) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, f"{label} file not found: {path}"

    value = path.read_text(encoding="utf-8").strip()
    if not value:
        return None, f"{label} file is empty: {path}"
    return value, None


def get_yandex_api_key_path() -> Path:
    return DEFAULT_YANDEX_API_KEY_PATH


def get_yandex_folder_id_path() -> Path:
    return DEFAULT_YANDEX_FOLDER_ID_PATH


def load_yandex_api_key(api_key_path: Path | None = None) -> tuple[str | None, str | None]:
    return _load_required_text(api_key_path or get_yandex_api_key_path(), "Yandex API key")


def load_yandex_folder_id(folder_id_path: Path | None = None) -> tuple[str | None, str | None]:
    return _load_required_text(folder_id_path or get_yandex_folder_id_path(), "Yandex folder id")


def load_yandex_base_url() -> str:
    return os.getenv("YANDEX_CLOUD_BASE_URL") or DEFAULT_YANDEX_BASE_URL


def load_yandex_model(default_suffix: str = "yandexgpt-lite/latest") -> tuple[str | None, str | None]:
    explicit_model = os.getenv("YANDEX_CLOUD_MODEL")
    if explicit_model:
        return explicit_model, None

    folder_id, error = load_yandex_folder_id()
    if not folder_id:
        return None, error

    return f"gpt://{folder_id}/{default_suffix}", None
