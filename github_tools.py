"""GitHub tools for Teena. Uses the git + gh command line tools, so no token is stored in code.

One-time setup (you do this, not Teena):
    1) install Git (git-scm.com) and GitHub CLI (cli.github.com)
    2) run:  gh auth login
"""
import re
import shutil
import subprocess
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SECRET_PATTERNS = (".env", "*.pem", "*.key", "id_rsa*", "*secret*", "*token*", "credentials*", "*.pfx")
_safe = None  # set by register()


def _need():
    miss = [t for t in ("git", "gh") if not shutil.which(t)]
    if miss:
        return ("Install aagala: " + ", ".join(miss) + ". git-scm.com and cli.github.com install panni, "
                "apparam Command Prompt-la 'gh auth login' run pannunga.")
    return None


def _name_err(name):
    if not NAME_RE.match(str(name)):
        return "Repo peru-la letters, numbers, - _ . mattum irukkalaam (space / slash vendaam)."
    return None


def _run(args, cwd=None, timeout=120):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def _flag(v):
    return str(v).strip().lower() in ("true", "1", "yes", "y", "public")


def github_list_repos():
    err = _need()
    if err:
        return err
    code, out = _run(["gh", "repo", "list", "--limit", "20"])
    return out if code == 0 else f"gh error: {out}\n(gh auth login panninaa nu paarunga)"


def github_create_repo(name, public=False, description=""):
    err = _need() or _name_err(name)
    if err:
        return err
    cmd = ["gh", "repo", "create", str(name), "--public" if _flag(public) else "--private"]
    if description:
        cmd += ["--description", str(description)[:200]]
    code, out = _run(cmd)
    return (out or f"Repo '{name}' create aayiduchu") if code == 0 else f"gh error: {out}"


def _secret_files(folder):
    found, count = [], 0
    for p in folder.rglob("*"):
        if ".git" in p.parts or "node_modules" in p.parts:
            continue
        count += 1
        if count > 5000:
            break
        if p.is_file() and any(p.match(pat) for pat in SECRET_PATTERNS):
            found.append(str(p.relative_to(folder)))
    return found


def github_push(folder, repo, message="Update from Teena"):
    err = _need() or _name_err(repo)
    if err:
        return err
    d = _safe(folder)
    if not d.is_dir():
        return "Andha folder illa"
    secrets = _secret_files(d)
    if secrets:
        return ("PUSH NIRUTHTHAPPATTADHU: secret maathiri files irukku: " + ", ".join(secrets[:5]) +
                ". Avatrai folder-la irundhu eduthuttu thirumba sollunga.")
    message = str(message)[:200] or "Update from Teena"

    code, login = _run(["gh", "api", "user", "-q", ".login"])
    if code != 0 or not login:
        return "gh login aagala. Command Prompt-la 'gh auth login' run pannunga."
    full = f"{login}/{repo}"
    _run(["gh", "auth", "setup-git"])

    if not (d / ".git").exists():
        code, out = _run(["git", "init", "-b", "main"], cwd=d)
        if code != 0:
            return f"git init error: {out}"
    _run(["git", "add", "-A"], cwd=d)
    code, status = _run(["git", "status", "--porcelain"], cwd=d)
    if status.strip():
        code, out = _run(["git", "commit", "-m", message], cwd=d)
        if code != 0:
            if "tell me who you are" in out or "user.email" in out:
                return ('git-ku un peru venum. Oru thadavai run pannunga:\n'
                        'git config --global user.name "Un Peru"\n'
                        'git config --global user.email "you@gmail.com"')
            return f"git commit error: {out}"
    code, _ = _run(["git", "rev-parse", "HEAD"], cwd=d)
    if code != 0:
        return "Push panna files illa (folder kaali)."
    _run(["git", "branch", "-M", "main"], cwd=d)

    code, _ = _run(["gh", "repo", "view", full])
    created = ""
    if code != 0:
        code, out = _run(["gh", "repo", "create", repo, "--private"])
        if code != 0:
            return f"Repo create aagala: {out}"
        created = " (pudhu private repo create pannen)"
    url = f"https://github.com/{full}.git"
    code, _ = _run(["git", "remote", "get-url", "origin"], cwd=d)
    _run(["git", "remote", "set-url" if code == 0 else "add", "origin", url], cwd=d)
    code, out = _run(["git", "push", "-u", "origin", "main"], cwd=d, timeout=180)   # never --force
    if code != 0:
        return f"git push error: {out}"
    return f"Push aayiduchu{created}: https://github.com/{full}"


def github_delete_repo(name):
    err = _need() or _name_err(name)
    if err:
        return err
    code, out = _run(["gh", "repo", "delete", str(name), "--yes"])
    if code != 0:
        hint = ""
        if "delete_repo" in out:
            hint = "\nPermission illa. Neenga venumna: gh auth refresh -h github.com -s delete_repo"
        return f"gh error: {out}{hint}"
    return f"Repo '{name}' delete aayiduchu."


def _tool(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required}}}


def register(registry, schemas, describers, danger, safe_path):
    global _safe
    _safe = safe_path
    S = {"type": "string"}
    registry["github_list_repos"] = (github_list_repos, False)
    registry["github_create_repo"] = (github_create_repo, True)
    registry["github_push"] = (github_push, True)
    registry["github_delete_repo"] = (github_delete_repo, True)
    danger.add("github_delete_repo")
    schemas += [
        _tool("github_list_repos", "List my GitHub repositories", {}, []),
        _tool("github_create_repo", "Create a new GitHub repository (private unless public=true)",
              {"name": S, "public": {"type": "boolean"}, "description": S}, ["name"]),
        _tool("github_push", "Commit and push a workspace folder to a GitHub repo (creates private repo if missing)",
              {"folder": S, "repo": S, "message": S}, ["folder", "repo"]),
        _tool("github_delete_repo", "Permanently delete a GitHub repository. Only when user clearly asks.",
              {"name": S}, ["name"]),
    ]
    describers["github_create_repo"] = lambda a: (
        f"GitHub repo create:\nName: {a.get('name')}\n"
        f"Visibility: {'PUBLIC (ellarum paakkalaam!)' if _flag(a.get('public', False)) else 'private'}")
    describers["github_push"] = lambda a: (
        f"Folder '{a.get('folder')}' files-a GitHub repo '{a.get('repo')}'-ku push pannum.\n"
        f"Commit message: {a.get('message', 'Update from Teena')}\n"
        "Repo illa na private-ah create pannum. Force push illa.")
    describers["github_delete_repo"] = lambda a: (
        f"DANGER: GitHub repo '{a.get('name')}' PERMANENT-ah delete aagum.\n"
        "Thirumba edukka mudiyaadhu.\n\nConfirm panna, repo peru-a keezha type pannunga.")
