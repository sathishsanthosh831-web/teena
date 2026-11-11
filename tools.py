"""Teena tools: file, command, app, url. Safety rules live here."""
import json
import re
import subprocess
import datetime
import webbrowser
from pathlib import Path

import github_tools
import linkcheck

BASE = Path(__file__).resolve().parent
WORKSPACE = BASE / "workspace"          # Teena can only touch files inside this folder
LOG_FILE = BASE / "teena_log.jsonl"
WORKSPACE.mkdir(exist_ok=True)

# Commands that are blocked even if the user presses Allow
BLOCKED = [
    r"\brm\s+(-\w*\s+)*-\w*[rf]", r"\bdel\b.*\s/[sqf]", r"\brmdir\b.*\s/s", r"\brd\b.*\s/s",
    r"\bformat\b", r"\bdiskpart\b", r"\bmkfs\b", r"\bshutdown\b", r"\brestart-computer\b",
    r"\breg\s+(delete|add)", r"remove-item.*-recurse", r"\bgh\s+repo\s+delete",
    r"\bgit\s+push\b.*--force", r"\bgit\s+push\b.*\s-f\b", r"\bgit\s+reset\s+--hard",
    r"\bcipher\s+/w", r"\btakeown\b", r"\bicacls\b", r"\bnet\s+user\b",
    r"\bcurl\b.*\|\s*(sh|bash|powershell)", r"\biwr\b.*\|\s*iex", r"invoke-expression",
    r"\bsudo\b", r"\bchmod\s+-R\s+777",
]

DANGER = set()      # tools that need type-to-confirm (filled by github_tools)
DESCRIBERS = {}    # extra popup texts

APPS = {  # app name -> command (allowlist)
    "notepad": "notepad", "calculator": "calc", "chrome": "start chrome",
    "vscode": "code", "explorer": "explorer", "paint": "mspaint",
}


def log(tool, args, decision, result=""):
    row = {"time": datetime.datetime.now().isoformat(timespec="seconds"),
           "tool": tool, "args": args, "decision": decision, "result": str(result)[:300]}
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def safe_path(p):
    """Resolve p inside WORKSPACE. Raise if it tries to escape."""
    full = (WORKSPACE / str(p)).resolve()
    try:
        full.relative_to(WORKSPACE.resolve())
    except ValueError:
        raise PermissionError("Path is outside the Teena workspace folder")
    return full


def is_blocked(cmd):
    c = cmd.lower()
    return any(re.search(p, c) for p in BLOCKED)


# ---------------- tool functions ----------------
def list_folder(path="."):
    d = safe_path(path)
    if not d.is_dir():
        return "Not a folder"
    items = [("[dir] " if x.is_dir() else "") + x.name for x in sorted(d.iterdir())]
    return "\n".join(items) or "(empty)"


def read_file(path):
    f = safe_path(path)
    if not f.is_file():
        return "File not found"
    return f.read_text(encoding="utf-8", errors="replace")[:6000]


def write_file(path, content):
    f = safe_path(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return f"Saved {path} ({len(content)} chars)"


def create_folder(path):
    d = safe_path(path)
    d.mkdir(parents=True, exist_ok=True)
    return f"Folder ready: {path}"


def run_command(command):
    if is_blocked(command):
        return "BLOCKED by Teena safety rules. Do not retry this command."
    try:
        r = subprocess.run(command, shell=True, cwd=WORKSPACE, capture_output=True,
                           text=True, timeout=60)
        out = (r.stdout + r.stderr).strip()
        return (out[:4000] or "(no output)") + f"\n[exit code {r.returncode}]"
    except subprocess.TimeoutExpired:
        return "Command timed out after 60 seconds"


def open_app(name):
    cmd = APPS.get(str(name).lower())
    if not cmd:
        return "App not allowed. Allowed: " + ", ".join(APPS)
    subprocess.Popen(cmd, shell=True)
    return f"Opened {name}"


def open_url(url):
    if not re.match(r"^https?://", str(url)):
        return "Only http/https links are allowed"
    webbrowser.open(url)
    return "Opened in browser"


# name -> (function, needs_user_approval)
REGISTRY = {
    "list_folder": (list_folder, False),
    "read_file": (read_file, False),
    "write_file": (write_file, True),
    "create_folder": (create_folder, True),
    "run_command": (run_command, True),
    "open_app": (open_app, True),
    "open_url": (open_url, True),
}


def _tool(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required}}}


S = {"type": "string"}
SCHEMAS = [
    _tool("list_folder", "List files in a folder inside the workspace", {"path": S}, []),
    _tool("read_file", "Read a text file from the workspace", {"path": S}, ["path"]),
    _tool("write_file", "Create or overwrite a file in the workspace",
          {"path": S, "content": S}, ["path", "content"]),
    _tool("create_folder", "Create a new empty folder inside the workspace", {"path": S}, ["path"]),
    _tool("run_command", "Run a shell command inside the workspace folder",
          {"command": S}, ["command"]),
    _tool("open_app", "Open an app: " + ", ".join(APPS), {"name": S}, ["name"]),
    _tool("open_url", "Open an http/https link in the browser", {"url": S}, ["url"]),
]


def describe(name, args):
    """Human readable text for the Allow popup."""
    if name == "create_folder":
        return f"Create folder:\n{args.get('path')}"
    if name == "write_file":
        c = str(args.get("content", ""))
        return f"Create / overwrite file:\n{args.get('path')}\n\n--- content preview ---\n{c[:500]}"
    if name == "run_command":
        return f"Run command:\n{args.get('command')}"
    if name == "open_app":
        return f"Open app: {args.get('name')}"
    if name == "open_url":
        return f"Open link:\n{args.get('url')}"
    if name in DESCRIBERS:
        return DESCRIBERS[name](args)
    return f"{name} {args}"


def execute(name, args, ask, ask_typed=None):
    """Run a tool. ask(text)->bool = Allow/Deny popup. ask_typed(text, expected)->bool = danger confirm."""
    if name not in REGISTRY:
        return f"Unknown tool: {name}"
    fn, needs_ok = REGISTRY[name]
    args = args or {}
    if name == "run_command" and is_blocked(str(args.get("command", ""))):
        log(name, args, "blocked")
        return "BLOCKED by Teena safety rules. Do not retry this command."
    if name in DANGER:
        expected = str(args.get("name", ""))
        if not expected or ask_typed is None or not ask_typed(describe(name, args), expected):
            log(name, args, "denied")
            return "User denied this action."
    elif needs_ok and not ask(describe(name, args)):
        log(name, args, "denied")
        return "User denied this action."
    try:
        result = fn(**args)
        log(name, args, "allowed" if needs_ok else "auto", result)
        return result
    except Exception as e:  # report to the model so it can fix its call
        log(name, args, "error", e)
        return f"Error: {e}"


# ---------------- Step 3 tools: Link Checker + GitHub ----------------
def check_link(text):
    return linkcheck.check_text(str(text))


REGISTRY["check_link"] = (check_link, False)
SCHEMAS.append(_tool("check_link", "Check if a link (from WhatsApp etc.) is safe or a scam. Never opens it in browser.",
                     {"text": S}, ["text"]))
github_tools.register(REGISTRY, SCHEMAS, DESCRIBERS, DANGER, safe_path)
