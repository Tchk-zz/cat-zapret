"""Tiny Git front-end for this project, built on dulwich (pure Python).

The machine has no git.exe installed, so this script provides the few
operations we actually need: snapshots (commits), history, diffs against the
last snapshot, and rollback. The repository it creates is a completely normal
``.git`` directory -- if real Git is installed later, every command works on it
unchanged.

Usage (run from the project root):

    python tools/repo.py init                 # create the repository
    python tools/repo.py snapshot "message"   # stage everything + commit
    python tools/repo.py log [n]              # last n snapshots (default 15)
    python tools/repo.py status               # what changed since last snapshot
    python tools/repo.py rollback <sha>       # restore all files from a snapshot

``rollback`` always takes a safety snapshot of the current state first, so it
can itself be undone.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dulwich import porcelain
    from dulwich.repo import Repo
except ImportError:  # pragma: no cover - dependency hint
    print("dulwich is not installed. Run: python -m pip install dulwich")
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parent.parent
AUTHOR = b"Zapret GUI dev <dev@localhost>"


def _repo() -> Repo:
    try:
        return Repo(str(ROOT))
    except Exception:
        print("No repository yet. Run: python tools/repo.py init")
        raise SystemExit(1)


def cmd_init() -> int:
    if (ROOT / ".git").exists():
        print("Repository already exists.")
        return 0
    porcelain.init(str(ROOT))
    print(f"Initialised empty repository in {ROOT / '.git'}")
    return 0


def _tracked_paths(repo: Repo) -> list[str]:
    """All non-ignored files under the project root, relative to it."""
    from dulwich.ignore import IgnoreFilterManager

    ignore = IgnoreFilterManager.from_repo(repo)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        if rel_dir == ".":
            rel_dir = ""
        # Prune ignored directories so we never descend into .git/ or vendor/.
        keep = []
        for d in dirnames:
            if d == ".git":
                continue
            rel = (rel_dir + "/" + d if rel_dir else d).replace(os.sep, "/")
            if ignore.is_ignored(rel + "/"):
                continue
            keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            rel = (rel_dir + "/" + f if rel_dir else f).replace(os.sep, "/")
            if ignore.is_ignored(rel):
                continue
            out.append(rel)
    return sorted(out)


def cmd_snapshot(message: str) -> int:
    repo = _repo()
    paths = _tracked_paths(repo)
    if not paths:
        print("Nothing to commit.")
        return 0
    porcelain.add(repo=str(ROOT), paths=[str(ROOT / p) for p in paths])
    # Drop entries whose file disappeared, so deletions are recorded too.
    index = repo.open_index()
    for entry in list(index):
        rel = entry.decode("utf-8", "replace")
        if not (ROOT / rel).exists():
            del index[entry]
    index.write()
    sha = porcelain.commit(
        repo=str(ROOT),
        message=message.encode("utf-8"),
        author=AUTHOR,
        committer=AUTHOR,
    )
    print(f"Snapshot {sha.decode()[:10]}: {message} ({len(paths)} files tracked)")
    return 0


def cmd_log(count: int = 15) -> int:
    repo = _repo()
    try:
        head = repo.head()
    except KeyError:
        print("No snapshots yet.")
        return 0
    shown = 0
    for entry in repo.get_walker(include=[head]):
        c = entry.commit
        msg = c.message.decode("utf-8", "replace").strip().splitlines()[0]
        import time as _t
        when = _t.strftime("%Y-%m-%d %H:%M", _t.localtime(c.commit_time))
        print(f"{c.id.decode()[:10]}  {when}  {msg}")
        shown += 1
        if shown >= count:
            break
    return 0


def cmd_status() -> int:
    repo = _repo()
    st = porcelain.status(repo=str(ROOT))
    staged = st.staged
    changed = [p.decode("utf-8", "replace") for p in st.unstaged]
    added = [p.decode("utf-8", "replace") for p in staged.get("add", [])]
    modified = [p.decode("utf-8", "replace") for p in staged.get("modify", [])]
    deleted = [p.decode("utf-8", "replace") for p in staged.get("delete", [])]
    if not (changed or added or modified or deleted):
        print("Working tree matches the last snapshot.")
        return 0
    for label, items in (
        ("modified", sorted(set(changed) | set(modified))),
        ("added", added),
        ("deleted", deleted),
    ):
        for item in items:
            print(f"{label:>9}: {item}")
    return 0


def cmd_rollback(sha: str) -> int:
    repo = _repo()
    # Safety net: never lose the current state to a rollback.
    try:
        cmd_snapshot("auto: state before rollback to " + sha)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"Could not take a safety snapshot ({exc}); aborting.")
        return 1

    full = sha.encode()
    if len(full) < 40:
        matches = [
            obj_id
            for obj_id in repo.object_store
            if obj_id.startswith(full)
        ]
        if len(matches) != 1:
            print(f"Ambiguous or unknown snapshot id: {sha}")
            return 1
        full = matches[0]

    commit = repo[full]
    tree = repo[commit.tree]
    restored = 0
    from dulwich.object_store import iter_tree_contents

    for entry in iter_tree_contents(repo.object_store, tree.id):
        rel = entry.path.decode("utf-8", "replace")
        blob = repo[entry.sha]
        target = ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob.data)
        restored += 1
    print(f"Restored {restored} files from {full.decode()[:10]}.")
    print("Review the result, then run: python tools/repo.py snapshot \"rollback\"")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "init":
        return cmd_init()
    if cmd == "snapshot":
        if len(argv) < 3:
            print('Usage: python tools/repo.py snapshot "message"')
            return 1
        return cmd_snapshot(" ".join(argv[2:]))
    if cmd == "log":
        return cmd_log(int(argv[2]) if len(argv) > 2 else 15)
    if cmd == "status":
        return cmd_status()
    if cmd == "rollback":
        if len(argv) < 3:
            print("Usage: python tools/repo.py rollback <sha>")
            return 1
        return cmd_rollback(argv[2])
    print(f"Unknown command: {cmd}")
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
