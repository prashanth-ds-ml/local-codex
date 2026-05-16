from __future__ import annotations

import ctypes
import os
import pathlib
import subprocess
from dataclasses import dataclass

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

_TOML_NAME = "codemitra.toml"
_RULES_NAME = "CODEMITRA.md"
_DEFAULT_INSTRUCTION_FILES = [
    "AGENTS.md",
    ".codemitra/instructions.md",
    ".github/copilot-instructions.md",
]
_DEFAULT_SKILL_DIRS = [
    "skills",
    ".codemitra/skills",
]
_MAX_INSTRUCTION_CHARS = 12000
_BYTES_PER_GIB = 1024 ** 3

_DEFAULTS: dict = {
    "model": "",          # legacy fallback; prefer local_model
    "local_model": "",    # empty = prompt user to pick at startup
    "codegen_model": "",  # empty = use local_model for code generation too
    "temperature": 0.2,
    "session_mode": "approve",
    "show_reasoning": False,
    "memory_enabled": False,
    "require_diff_approval": True,
    "auto_compact_threshold": 120000,  # combined tokens before auto-compact
    "num_ctx": 131072,                # Ollama context window to request when supported
    "ollama_api_key": "",
    "ollama_local_base_url": "http://localhost:11434",
    "ollama_cloud_base_url": "https://ollama.com",
    "allowed_roots": [],
    "disabled_tools": [],
    "disabled_commands": [],
    "instruction_files": list(_DEFAULT_INSTRUCTION_FILES),
    "skill_dirs": list(_DEFAULT_SKILL_DIRS),
}


@dataclass(frozen=True)
class LocalModelInfo:
    name: str
    size_text: str = ""
    size_gib: float | None = None
    recommended: bool = True


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


def _load_project_instructions(root: pathlib.Path, entries) -> list[dict[str, str]]:
    """Load configured project instruction files from inside the workspace."""
    if not entries:
        return []
    if isinstance(entries, str):
        entries = [entries]

    loaded: list[dict[str, str]] = []
    seen: set[pathlib.Path] = set()
    for raw_entry in entries:
        entry = str(raw_entry).strip()
        if not entry:
            continue
        path = pathlib.Path(entry)
        target = path if path.is_absolute() else root / path
        try:
            resolved = target.resolve()
            resolved.relative_to(root.resolve())
        except (OSError, ValueError):
            continue
        if resolved in seen or not resolved.is_file():
            continue
        try:
            text = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        loaded.append(
            {
                "path": str(resolved.relative_to(root.resolve())),
                "content": text[:_MAX_INSTRUCTION_CHARS],
            }
        )
        seen.add(resolved)
    return loaded


def _parse_size_to_gib(value: str, unit: str) -> float | None:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None

    scale = {
        "B": 1 / _BYTES_PER_GIB,
        "KB": 1 / (1024 ** 2),
        "MB": 1 / 1024,
        "GB": 1,
        "TB": 1024,
    }.get((unit or "").upper())
    if scale is None:
        return None
    return round(amount * scale, 2)


def get_total_system_memory_gib() -> float | None:
    """Return detected physical system RAM in GiB."""
    try:
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return round(status.ullTotalPhys / _BYTES_PER_GIB, 1)
            return None

        page_size = os.sysconf("SC_PAGE_SIZE")
        phys_pages = os.sysconf("SC_PHYS_PAGES")
        return round((page_size * phys_pages) / _BYTES_PER_GIB, 1)
    except Exception:
        return None


def get_available_system_memory_gib() -> float | None:
    """Return currently available physical RAM in GiB."""
    try:
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return round(status.ullAvailPhys / _BYTES_PER_GIB, 1)
            return None

        page_size = os.sysconf("SC_PAGE_SIZE")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        return round((page_size * avail_pages) / _BYTES_PER_GIB, 1)
    except Exception:
        return None


def get_recommended_model_budget_gib() -> float | None:
    """Return the practical local-model size budget for this machine."""
    total_gib = get_total_system_memory_gib()
    if total_gib is None:
        return None
    return round(max(2.0, total_gib * 0.5), 1)


def get_local_model_inventory() -> list[LocalModelInfo]:
    """Return local Ollama models with parsed sizes and hardware guidance."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().splitlines()[1:]  # skip header
        budget_gib = get_recommended_model_budget_gib()
        models: list[LocalModelInfo] = []
        for line in lines:
            parts = line.split()
            if len(parts) < 4:
                continue
            name = parts[0]
            size_value = parts[2]
            size_unit = parts[3]
            if size_value == "-" or size_unit == "-":
                continue
            size_text = f"{size_value} {size_unit}"
            size_gib = _parse_size_to_gib(size_value, size_unit)
            recommended = budget_gib is None or size_gib is None or size_gib <= budget_gib
            models.append(
                LocalModelInfo(
                    name=name,
                    size_text=size_text,
                    size_gib=size_gib,
                    recommended=recommended,
                )
            )
        return models
    except Exception:
        return []


def list_local_models(*, recommended_only: bool = False) -> list[str]:
    """Return model names available in the local Ollama installation."""
    inventory = get_local_model_inventory()
    if recommended_only:
        inventory = [model for model in inventory if model.recommended]
    return [model.name for model in inventory]


def stop_local_model(model_name: str) -> tuple[bool, str]:
    """Ask Ollama to unload a running model from memory."""
    target = (model_name or "").strip()
    if not target:
        return False, "No model name provided."

    try:
        result = subprocess.run(
            ["ollama", "stop", target],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        return False, f"Could not run `ollama stop`: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or f"Failed to stop `{target}`."
        return False, detail

    detail = (result.stdout or "").strip() or f"Stopped `{target}`."
    return True, detail


def remove_local_model(model_name: str) -> tuple[bool, str]:
    """Remove a local Ollama model by name."""
    target = (model_name or "").strip()
    if not target:
        return False, "No model name provided."

    try:
        result = subprocess.run(
            ["ollama", "rm", target],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return False, f"Could not run `ollama rm`: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or f"Failed to remove `{target}`."
        return False, detail

    detail = (result.stdout or "").strip() or f"Removed `{target}`."
    return True, detail


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
    cfg["project_instructions"] = _load_project_instructions(root, cfg.get("instruction_files"))
    cfg["workspace"] = str(root)
    raw_roots = cfg.get("allowed_roots") or []
    if isinstance(raw_roots, str):
        raw_roots = [raw_roots]
    cfg["allowed_roots"] = [
        str((root / entry).resolve()) if not pathlib.Path(entry).is_absolute() else str(pathlib.Path(entry).resolve())
        for entry in raw_roots
    ]
    raw_disabled_tools = cfg.get("disabled_tools") or []
    cfg["disabled_tools"] = list(raw_disabled_tools) if isinstance(raw_disabled_tools, list) else [str(raw_disabled_tools)]
    raw_disabled_commands = cfg.get("disabled_commands") or []
    cfg["disabled_commands"] = list(raw_disabled_commands) if isinstance(raw_disabled_commands, list) else [str(raw_disabled_commands)]
    raw_skill_dirs = cfg.get("skill_dirs") or []
    if isinstance(raw_skill_dirs, str):
        raw_skill_dirs = [raw_skill_dirs]
    cfg["skill_dirs"] = list(raw_skill_dirs)

    return cfg
