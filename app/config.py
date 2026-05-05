from __future__ import annotations

import os
import pathlib
import subprocess
import tomllib

_TOML_NAME = "codemitra.toml"
_RULES_NAME = "CODEMITRA.md"

_DEFAULTS: dict = {
    "model": "",          # legacy fallback; prefer local_model
    "local_model": "",    # empty = prompt user to pick at startup
    "codegen_model": "",  # empty = use local_model for code generation too
    "temperature": 0.2,
    "memory_enabled": False,
    "require_diff_approval": False,
    "auto_compact_threshold": 8000,   # combined tokens before auto-compact
    "ollama_api_key": "",
    "ollama_local_base_url": "http://localhost:11434",
    "ollama_cloud_base_url": "https://ollama.com",
}


def _load_dotenv(path: pathlib.Path) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from a .env file if present."""
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def list_local_models() -> list[str]:
    """Return model names available in the local Ollama installation."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().splitlines()[1:]  # skip header
        models = []
        for line in lines:
            parts = line.split()
            if parts:
                name = parts[0]
                # skip cloud/remote-only entries that have no local size
                size_col = parts[3] if len(parts) > 3 else ""
                if size_col and size_col != "-":
                    models.append(name)
        return models
    except Exception:
        return []


def load(cwd: str | None = None) -> dict:
    """
    Load config from the current (or given) directory.

    Returns a dict with keys from _DEFAULTS, overridden by codemitra.toml if
    present, plus:
      - 'rules'     : contents of CODEMITRA.md, or None
      - 'workspace' : resolved path of the project root
    """
    root = pathlib.Path(cwd).resolve() if cwd else pathlib.Path.cwd()
    cfg = dict(_DEFAULTS)
    dotenv_vars = _load_dotenv(root / ".env")

    toml_path = root / _TOML_NAME
    if toml_path.exists():
        with open(toml_path, "rb") as f:
            cfg.update(tomllib.load(f))

    cfg["ollama_api_key"] = (
        os.getenv("OLLAMA_API_KEY")
        or dotenv_vars.get("OLLAMA_API_KEY")
        or cfg.get("ollama_api_key", "")
    )

    rules_path = root / _RULES_NAME
    cfg["rules"] = rules_path.read_text(encoding="utf-8") if rules_path.exists() else None
    cfg["workspace"] = str(root)

    return cfg
