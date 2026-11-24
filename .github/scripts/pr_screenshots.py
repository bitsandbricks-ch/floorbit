#!/usr/bin/env python3
"""Show a pull request's screenshots in one comment on it, kept up to date on every push (#1400).

Screenshots linked in a description written by a coding agent can come out wrapped in backticks,
so GitHub shows them as text. CI writes this comment instead. It shows:

- every image the pull request added under .pr-screenshots/ (agents add them in one commit and
  remove them in the next), linked by the sha of the commit that added it;
- otherwise the screenshots CI took (the `screenshots` job), pushed to the `pr-screenshots`
  branch under pr-<number>/.

Links go to raw.githubusercontent.com, never github.com/.../blob/...?raw=true, which github.com
throttles. Usage (CI): pr_screenshots.py <ci-screenshots-dir>
Env: GITHUB_TOKEN, GITHUB_REPOSITORY, PR, BASE_SHA, HEAD_SHA.
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

MARKER = "<!-- pr-screenshots -->"
IMAGE = (".png", ".jpg", ".jpeg", ".gif", ".webp")
BRANCH = "pr-screenshots"
REPO = os.environ["GITHUB_REPOSITORY"]
PR = os.environ["PR"]
RAW = f"https://raw.githubusercontent.com/{REPO}"


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def api(method, path, body=None):
    req = urllib.request.Request(
        f"https://api.github.com/{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def committed():
    """{path: sha of the newest commit in the PR that added it} for .pr-screenshots images."""
    log = git("log", "--reverse", "--diff-filter=A", "--name-only", "--format=%H",
              f"{os.environ['BASE_SHA']}..{os.environ['HEAD_SHA']}", "--", ".pr-screenshots")
    found, sha = {}, None
    for line in log.splitlines():
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
            sha = line
        elif line.lower().endswith(IMAGE):
            found[line] = sha
    return found


def push_ci(shots):
    """Commit CI's screenshots to the pr-screenshots branch under pr-<n>/; return {path: sha}."""
    files = sorted(p for p in shots.iterdir() if p.suffix.lower() in IMAGE)
    if not files:
        return {}
    work = Path("pr-screenshots-branch")
    git("fetch", "--depth=1", "origin", BRANCH)
    git("worktree", "add", "--detach", str(work), "FETCH_HEAD")
    target = work / f"pr-{PR}"
    subprocess.run(["rm", "-rf", str(target)], check=True)
    target.mkdir(parents=True)
    for f in files:
        (target / f.name).write_bytes(f.read_bytes())
    os.chdir(work)
    git("add", "-A", f"pr-{PR}")
    git("-c", "user.name=github-actions[bot]", "-c", "user.email=github-actions[bot]@users.noreply.github.com",
        "commit", "--quiet", "--allow-empty", "-m", f"pr-{PR}: CI screenshots")
    git("push", "--quiet", "origin", f"HEAD:refs/heads/{BRANCH}")
    sha = git("rev-parse", "HEAD").strip()
    os.chdir("..")
    return {f"pr-{PR}/{f.name}": sha for f in files}


def body(images, from_ci):
    lines = [MARKER, "## Screenshots", ""]
    if from_ci:
        lines += ["Taken by CI (`scripts/screenshots.py`, demo data). Commit your own under "
                  "`.pr-screenshots/<topic>/` to show them here instead.", ""]
    for path, sha in sorted(images.items()):
        name = Path(path).stem.replace("-", " ")
        lines += [f"**{name}**", "", f"![{name}]({RAW}/{sha}/{path})", ""]
    return "\n".join(lines)


def main():
    images, from_ci = committed(), False
    if not images:
        images, from_ci = push_ci(Path(sys.argv[1])), True
    if not images:
        print("No screenshots to show.")
        return
    text = body(images, from_ci)
    comments = api("GET", f"repos/{REPO}/issues/{PR}/comments?per_page=100")
    mine = next((c for c in comments if c["body"].startswith(MARKER)), None)
    if mine:
        api("PATCH", f"repos/{REPO}/issues/comments/{mine['id']}", {"body": text})
    else:
        api("POST", f"repos/{REPO}/issues/{PR}/comments", {"body": text})
    print(f"{len(images)} screenshots in the comment.")


if __name__ == "__main__":
    main()
