---
title: Tools Reference
tags: [tools, reference, api]
aliases: [Tools, Tool Reference]
---

# Tools Reference

All tools live in `app/agents/filesystem.py`. Every tool checks the [[Permissions]] guard before executing.

---

## create_folder

```python
create_folder(path: str) -> str
```

Creates a directory and any missing parent directories.

| Arg | Type | Description |
|---|---|---|
| `path` | `str` | Target directory path |

**Returns:** `✓ Created folder: <path>` or `✗ <error>`

**Example:**
```
create_folder("myapi/src/routers")
→ ✓ Created folder: myapi/src/routers
```

---

## create_file

```python
create_file(path: str, content: str = "") -> str
```

Creates a file with optional text content. Parent directories are created automatically.

| Arg | Type | Description |
|---|---|---|
| `path` | `str` | Target file path |
| `content` | `str` | File content (default: empty) |

**Example:**
```
create_file("myapi/main.py", "from fastapi import FastAPI\napp = FastAPI()")
→ ✓ Created file: myapi/main.py
```

---

## read_file

```python
read_file(path: str) -> str
```

Reads and returns the full text content of a file.

| Arg | Type | Description |
|---|---|---|
| `path` | `str` | File to read |

**Returns:** File contents as a string, or `✗ <error>`

---

## list_directory

```python
list_directory(path: str = ".") -> str
```

Lists all files and sub-folders in a directory, sorted with folders first.

| Arg | Type | Description |
|---|---|---|
| `path` | `str` | Directory to list (default: current dir) |

**Returns:**
```
myapi/
  [dir]  src
  [dir]  .venv
  [file] main.py
  [file] requirements.txt
```

---

## delete_file

```python
delete_file(path: str) -> str
```

Deletes a single file.

> [!warning] Off by default
> Must be enabled via `filesystem.configure(allowed_tools=... | {"delete_file"})`.

---

## delete_folder

```python
delete_folder(path: str) -> str
```

Deletes a folder and **all its contents** recursively (`shutil.rmtree`).

> [!warning] Off by default — destructive
> This cannot be undone. Requires explicit opt-in.

---

## move_file

```python
move_file(src: str, dest: str) -> str
```

Moves or renames a file or folder.

| Arg | Type | Description |
|---|---|---|
| `src` | `str` | Source path |
| `dest` | `str` | Destination path |

> [!warning] Off by default

---

## create_venv

```python
create_venv(project_path: str) -> str
```

Runs `python -m venv .venv` inside the given project directory.

| Arg | Type | Description |
|---|---|---|
| `project_path` | `str` | Directory where `.venv` will be created |

**Note:** Must be called before `install_packages`.

---

## install_packages

```python
install_packages(project_path: str, packages: list[str] | None = None) -> str
```

Installs packages into the project's `.venv`.

| Arg | Type | Description |
|---|---|---|
| `project_path` | `str` | Project root containing `.venv` |
| `packages` | `list[str] \| None` | Package names to install. If omitted, installs from `requirements.txt` |

When `packages` is provided, also writes `pip freeze` output to `requirements.txt`.

**Examples:**
```
install_packages("myapi", ["fastapi", "uvicorn"])
→ ✓ Installed fastapi, uvicorn and wrote requirements.txt

install_packages("myapi")   # uses existing requirements.txt
→ ✓ Installed all packages from requirements.txt
```

---

## run_command

```python
run_command(command: str, cwd: str = ".") -> str
```

Runs a shell command in a given directory. The executable must be in the [[Permissions#Command whitelist|command whitelist]].

| Arg | Type | Description |
|---|---|---|
| `command` | `str` | Shell command string |
| `cwd` | `str` | Working directory (default: current dir) |

**Default allowed executables:** `python`, `python3`, `pip`, `pip3`, `git`, `npm`, `node`, `uvicorn`

> [!warning] Off by default
> Enable with `filesystem.configure(allowed_tools=... | {"run_command"})`.

**Example:**
```
run_command("git init", cwd="myapi")
→ ✓ [0]
  Initialized empty Git repository in myapi/.git/
```
