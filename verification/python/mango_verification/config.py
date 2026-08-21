from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CommandSpec:
    command: str = ""
    timeout: int = 60


@dataclass
class VerificationConfig:
    build: CommandSpec = field(default_factory=CommandSpec)
    test: CommandSpec = field(default_factory=CommandSpec)
    diagnostics: CommandSpec = field(default_factory=CommandSpec)

    def has_any_command(self) -> bool:
        return bool(self.build.command or self.test.command or self.diagnostics.command)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> VerificationConfig:
        return config_from_dict(data)


CONFIG_NAMES = (
    "mango.verify.yaml",
    "mango.verify.yml",
    "mango.verify.json",
    ".mango/verify.yaml",
    ".mango/verify.yml",
    ".mango/verify.json",
    "mango.verify.yaml",
    "mango.verify.yml",
    "mango.verify.json",
    ".mango/verify.yaml",
    ".mango/verify.yml",
    ".mango/verify.json",
)


def load_verification_config(
    project_path: str | Path,
    config: VerificationConfig | dict | str | Path | None = None,
) -> VerificationConfig:
    if isinstance(config, VerificationConfig):
        return config
    if isinstance(config, dict):
        return config_from_dict(config)
    if isinstance(config, (str, Path)):
        path = Path(config)
        if path.is_file():
            return _read_config_file(path)
    root = Path(project_path).expanduser().resolve()
    for name in CONFIG_NAMES:
        candidate = root / name
        if candidate.is_file():
            return _read_config_file(candidate)
    return VerificationConfig()


def _read_config_file(path: Path) -> VerificationConfig:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text) if text.strip() else {}
    else:
        data = _load_yaml(text)
    return config_from_dict(data if isinstance(data, dict) else {})


def config_from_dict(data: dict[str, Any]) -> VerificationConfig:
    return VerificationConfig(
        build=_spec(data.get("build")),
        test=_spec(data.get("test")),
        diagnostics=_spec(data.get("diagnostics") or data.get("lint")),
    )


def _spec(value: Any) -> CommandSpec:
    if value is None:
        return CommandSpec()
    if isinstance(value, str):
        return CommandSpec(command=value)
    if isinstance(value, dict):
        command = value.get("command") or value.get("cmd") or ""
        timeout = value.get("timeout") or 60
        return CommandSpec(command=str(command), timeout=int(timeout))
    return CommandSpec()


def _load_yaml(text: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return _minimal_yaml(text)
    loaded = yaml.safe_load(text) or {}
    return loaded if isinstance(loaded, dict) else {}


def _minimal_yaml(text: str) -> dict[str, Any]:
    """Tiny subset: section keys plus command/timeout fields."""
    data: dict[str, Any] = {}
    section: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, rest = stripped.split(":", 1)
        key = key.strip()
        rest = rest.strip().strip('"').strip("'")
        if indent == 0:
            if rest:
                data[key] = rest
                section = None
            else:
                data[key] = {}
                section = key
            continue
        if section is None:
            continue
        bucket = data.get(section)
        if not isinstance(bucket, dict):
            bucket = {}
            data[section] = bucket
        bucket[key] = rest
    return data
