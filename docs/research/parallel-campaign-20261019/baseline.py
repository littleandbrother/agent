#!/usr/bin/env python3
"""Reproduce V2 HEAD plus frozen edits; never write original Git administration.

Cloud placeholders are recovered into a new cache against indexed Git blob
identities. Original placeholder contents remain unread and unchanged.
"""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import urllib.parse
import urllib.request
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT / "workbench/bf-architecture-v2"
ORIGINAL_GIT = ROOT / "workbench/bf-refactor-r0-r2-20261011/.git"
SNAP = HERE / "baseline-v1"
RUNTIME = Path.home() / ".local/share/bf-agent-architecture-v2/parallel-campaign-20261019"
ADMIN = RUNTIME / "campaign.git"
HEAD = "317d40fef0137d3c1ad1873e53c3e9968b31200a"
WORKSPACES = {r: ROOT / f"workbench/bf-campaign-{r}-20261019" for r in ("s0", "a", "b")}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def oid(kind, data):
    return hashlib.sha1(kind.encode() + b" " + str(len(data)).encode() + b"\0" + data).hexdigest()


def cloud(p):
    return bool(p.lstat().st_flags & 0x40000000)


def write_json(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def git(*args, cwd=None, timeout=20):
    cmd = ["git"] if cwd else ["git", "--git-dir=" + str(ADMIN)]
    return subprocess.run(cmd + list(args), cwd=cwd, capture_output=True,
                          check=True, timeout=timeout).stdout


def put_object(kind, data):
    key = oid(kind, data)
    p = ADMIN / "objects" / key[:2] / key[2:]
    if not p.exists():
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(zlib.compress(kind.encode() + b" " + str(len(data)).encode() + b"\0" + data))
    return key


def indexed():
    rows = []
    for raw in (SNAP / "index-entries.nul").read_bytes().decode().split("\0")[:-1]:
        meta, name = raw.split("\t", 1)
        mode, key, stage = meta.split()
        if stage != "0":
            raise ValueError("Unmerged index is not a baseline")
        rows.append((name, mode, key))
    return rows


def exact_blob(name, key):
    cached = SNAP / "recovered-blobs" / key
    if cached.exists():
        data = cached.read_bytes()
    else:
        original = ORIGINAL_GIT / "objects" / key[:2] / key[2:]
        data = None
        if original.exists() and not cloud(original):
            raw = zlib.decompress(original.read_bytes())
            if raw.startswith(b"blob "):
                data = raw.partition(b"\0")[2]
        if data is None:
            url = "https://raw.githubusercontent.com/littleandbrother/agent/" + HEAD + "/" + urllib.parse.quote(name)
            with urllib.request.urlopen(url, timeout=12) as response:
                data = response.read(10_000_000)
        cached.write_bytes(data)
    if oid("blob", data) != key:
        raise ValueError(f"Recovered blob mismatch: {name}")
    return data


def trees(rows):
    root = {}
    for name, mode, key in rows:
        node = root
        parts = name.split("/")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = (mode, key)
    def build(node):
        data = b""
        for name in sorted(node, key=lambda n: n + ("/" if isinstance(node[n], dict) else "")):
            value = node[name]
            mode, key = ("40000", build(value)) if isinstance(value, dict) else value
            data += mode.encode() + b" " + name.encode() + b"\0" + bytes.fromhex(key)
        return put_object("tree", data)
    return build(root)


def describe(base, entry):
    p = base / entry["path"]
    if not p.exists() and not p.is_symlink():
        return None
    if cloud(p):
        return {"placeholder": True, "bytes": p.lstat().st_size,
                "mtime_ns": p.lstat().st_mtime_ns, "flags": p.lstat().st_flags}
    data = os.readlink(p).encode() if p.is_symlink() else p.read_bytes()
    return {"sha256": sha256(data), "bytes": len(data),
            "executable": bool(p.lstat().st_mode & stat.S_IXUSR),
            "kind": "symlink" if p.is_symlink() else "file"}


def freeze():
    if (SNAP / "manifest.json").exists():
        raise SystemExit("Baseline already sealed")
    if shutil.disk_usage(ROOT).free < 5_000_000_000:
        raise SystemExit("Space gate failed")
    if not ADMIN.exists():
        subprocess.run(["git", "init", "--bare", str(ADMIN)], check=True, capture_output=True, timeout=10)
        (ADMIN / "objects/info/alternates").write_text(str(ORIGINAL_GIT / "objects") + "\n")
    original_commit = ORIGINAL_GIT / "objects" / HEAD[:2] / HEAD[2:]
    if cloud(original_commit):
        raise ValueError("Original commit unavailable")
    raw = zlib.decompress(original_commit.read_bytes())
    data = raw.partition(b"\0")[2]
    if put_object("commit", data) != HEAD:
        raise ValueError("Commit identity mismatch")
    rows = indexed()
    expected_tree = data.splitlines()[0].decode().split()[1]
    if trees(rows) != expected_tree:
        raise ValueError("Original index differs from original HEAD tree")
    (ADMIN / "HEAD").write_text(HEAD + "\n")
    entries, changed, placeholders, excluded = [], [], [], []
    overlay = SNAP / "overlay"
    new = (SNAP / "new-paths.nul").read_bytes().decode().split("\0")[:-1]
    known = {n for n, _, _ in rows}
    for name, mode, key in rows + [(n, None, None) for n in new if n not in known]:
        p = SOURCE / name
        origin_stat = {"bytes": p.lstat().st_size, "mtime_ns": p.lstat().st_mtime_ns, "flags": p.lstat().st_flags}
        placeholder = cloud(p)
        if placeholder and key is None:
            excluded.append({"path": name, "reason": "untracked historical receipt is dataless; preserved, not a source input", **origin_stat})
            continue
        content = exact_blob(name, key) if placeholder else (os.readlink(p).encode() if p.is_symlink() else p.read_bytes())
        if placeholder:
            placeholders.append({"path": name, "indexed_blob": key, **origin_stat})
            put_object("blob", content)
        dirty = key is not None and oid("blob", content) != key
        if dirty:
            changed.append(name)
            put_object("blob", exact_blob(name, key))
        e = {"path": name, "sha256": sha256(content), "bytes": len(content),
             "executable": bool(p.lstat().st_mode & stat.S_IXUSR),
             "kind": "symlink" if p.is_symlink() else "file"}
        entries.append(e)
        if dirty or key is None or placeholder:
            dest = overlay / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if e["kind"] == "symlink":
                dest.symlink_to(content.decode())
            else:
                dest.write_bytes(content)
                dest.chmod(0o755 if e["executable"] else 0o644)
    tree_hash = sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())
    m = {"schema_version": "bf-parallel-campaign-baseline-v1", "id": "CB-" + tree_hash,
         "head": HEAD, "head_tree": expected_tree, "source": str(SOURCE),
         "original_git_common_dir": str(ORIGINAL_GIT), "isolated_git_admin": str(ADMIN),
         "manifest_sha256": tree_hash, "entries": entries, "changed": changed,
         "new": [n for n in new if n not in {e["path"] for e in excluded}],
         "excluded_preserved": excluded, "original_placeholders": placeholders,
         "tracked_count": len(rows), "original_new_count": len(new),
         "source_bytes": sum(e["bytes"] for e in entries),
         "original_index_sha256": sha256((ORIGINAL_GIT / "worktrees/bf-architecture-v2/index").read_bytes()),
         "free_bytes_before": shutil.disk_usage(ROOT).free,
         "workspace_peak_upper_bytes": sum(e["bytes"] for e in entries) * 3,
         "runtime_artifact_reservation_bytes": 2_000_000_000,
         "recovery_boundary": "Original placeholder contents unread. Indexed blobs independently restored in new cache and checked against index and HEAD tree. Unrelated dataless new receipts excluded and preserved. No original index or placeholder write."}
    verify_one(SOURCE, m, original=True)
    write_json(SNAP / "manifest.json", m)
    print(json.dumps({k: m[k] for k in ["id", "head", "head_tree", "tracked_count", "original_new_count", "source_bytes", "workspace_peak_upper_bytes"]}, indent=2), flush=True)


def verify_one(base, m, original=False):
    by_placeholder = {e["path"]: e for e in m["original_placeholders"]}
    failures = []
    cloud_readbacks = []
    for e in m["entries"]:
        current = describe(base, e)
        if original and current and current.get("placeholder"):
            prior = by_placeholder.get(e["path"])
            if not prior or any(current[k] != prior[k] for k in ["bytes", "mtime_ns", "flags"]):
                # iCloud may evict an initially resident file during a long run.
                # Do not equate an availability flag with changed contents, and
                # do not accept it on metadata alone: bounded readback must match
                # the original frozen content hash exactly.
                code = "import hashlib,pathlib,sys;print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())"
                try:
                    check = subprocess.run(["python3", "-c", code, str(base/e["path"])],
                        capture_output=True, text=True, timeout=18)
                    ok = check.returncode == 0 and check.stdout.strip() == e["sha256"]
                except subprocess.TimeoutExpired:
                    ok = False
                if not ok:
                    failures.append(e["path"])
                else:
                    cloud_readbacks.append(e["path"])
        elif current != {k: e[k] for k in ["sha256", "bytes", "executable", "kind"]}:
            failures.append(e["path"])
    if failures:
        raise ValueError(f"Content drift in {base}: {failures[:8]}")
    if original and sha256((ORIGINAL_GIT / "worktrees/bf-architecture-v2/index").read_bytes()) != m["original_index_sha256"]:
        raise ValueError("Original index changed")
    return {"path": str(base), "baseline": m["id"], "files": len(m["entries"]), "status": "PASS",
            "changed_cloud_state_with_exact_content_readback": cloud_readbacks,
            "original_placeholder_content_verified": not original}


def materialize():
    m = json.loads((SNAP / "manifest.json").read_text())
    verify_one(SOURCE, m, original=True)
    receipts = []
    for role, target in WORKSPACES.items():
        if target.exists():
            receipts.append({"role": role, **verify_one(target, m)})
            continue
        git("worktree", "add", "--no-checkout", "--detach", str(target), HEAD)
        for e in m["entries"]:
            name = e["path"]
            overlay = SNAP / "overlay" / name
            src = overlay if overlay.exists() or overlay.is_symlink() else SOURCE / name
            dst = target / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if e["kind"] == "symlink":
                dst.symlink_to(os.readlink(src))
            else:
                shutil.copy2(src, dst)
        git("read-tree", HEAD, cwd=target)
        receipts.append({"role": role, **verify_one(target, m)})
    # Build an exact byte-level text patch without asking Git to hydrate global
    # or historical attributes. The overlay also preserves the full changed
    # bytes, including Windows files whose Git attributes normalize line ends.
    keys = {name: key for name, mode, key in indexed()}
    chunks = []
    for name in m["changed"]:
        old = exact_blob(name, keys[name])
        new = (SNAP / "overlay" / name).read_bytes()
        chunks.append(f"diff --git a/{name} b/{name}\nindex {keys[name]}..{oid('blob', new)} 100644\n".encode())
        chunks.extend(difflib.diff_bytes(difflib.unified_diff, old.splitlines(keepends=True),
                      new.splitlines(keepends=True), fromfile=("a/" + name).encode(),
                      tofile=("b/" + name).encode()))
    patch = b"".join(chunks)
    (SNAP / "tracked.patch").write_bytes(patch)
    write_json(SNAP / "materialization.json", {"workspaces": receipts,
        "patch_sha256": sha256(patch), "free_bytes_after": shutil.disk_usage(ROOT).free,
        "git_commit_created": False, "source_index_modified": False,
        "original": verify_one(SOURCE, m, original=True)})
    print(json.dumps(receipts, indent=2), flush=True)


def verify():
    m = json.loads((SNAP / "manifest.json").read_text())
    print(json.dumps([verify_one(SOURCE, m, original=True)] +
                     [verify_one(p, m) for p in WORKSPACES.values() if p.exists()], indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["freeze", "materialize", "verify"])
    globals()[p.parse_args().action]()
