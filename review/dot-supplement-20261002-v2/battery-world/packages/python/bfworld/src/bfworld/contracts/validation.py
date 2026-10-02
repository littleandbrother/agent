"""Validation against the repository's language-neutral JSON contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema


def repository_root() -> Path:
    return Path(__file__).resolve().parents[6]


def schema_root() -> Path:
    return repository_root() / "contracts" / "schemas" / "v1"


def load_schema(name: str) -> dict[str, Any]:
    with (schema_root() / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_document(name: str, document: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator(load_schema(name)).validate(document)

