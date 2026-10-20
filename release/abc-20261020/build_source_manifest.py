"""Record staged source paths with their committed checkout line endings."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = Path(__file__).with_name("source-manifest.json")


def git(*args, data=None):
    return subprocess.check_output(["git", *args], cwd=ROOT, input=data)


def main():
    objects = {}
    for record in git("ls-files", "--stage", "-z").split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, oid, stage = metadata.decode().split()
        assert stage == "0" and mode in ("100644", "100755"), name
        objects[name.decode()] = oid
    names = sorted(objects)
    # Unchanged staged objects retain the previously published checkout bytes.
    # Reuse their verified digests instead of reopening archived old objects.
    baseline_name = "release/abc-20261020/source-manifest.json"
    baseline = subprocess.run(["git", "show", "HEAD:" + baseline_name],
                              cwd=ROOT, capture_output=True)
    if baseline.returncode:
        baseline_name = "release/source-manifest-20261020.json"
        baseline = subprocess.run(["git", "show", "HEAD:" + baseline_name],
                                  cwd=ROOT, capture_output=True, check=True)
    previous = {e["path"]: e for e in json.loads(baseline.stdout)["files"]}
    changed = {n.decode() for n in git("diff", "--cached", "--name-only", "-z", "HEAD").split(b"\0") if n}
    changed_attribute_scopes = [("" if Path(n).parent == Path(".") else str(Path(n).parent) + "/")
                                for n in changed if Path(n).name == ".gitattributes"]
    raw = git("check-attr", "--cached", "-z", "--stdin", "eol", "text",
              data=b"\0".join(n.encode() for n in names) + b"\0").split(b"\0")
    attributes = {}
    for i in range(0, len(raw) - 1, 3):
        name, attribute, value = (s.decode() for s in raw[i:i + 3])
        attributes.setdefault(name, {})[attribute] = value
    files = []
    reader = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for name in names:
            if ROOT / name == DESTINATION:
                continue
            if name in previous and name not in changed and not any(name.startswith(scope) for scope in changed_attribute_scopes):
                files.append(previous[name])
                continue
            # Git objects are the authoritative staged bytes. Reading resident
            # objects avoids hydrating archived working-copy placeholders.
            reader.stdin.write(objects[name].encode() + b"\n")
            reader.stdin.flush()
            oid, kind, size = reader.stdout.readline().decode().split()
            assert oid == objects[name] and kind == "blob", name
            data = reader.stdout.read(int(size))
            assert len(data) == int(size) and reader.stdout.read(1) == b"\n"
            attr = attributes[name]
            if attr["text"] != "unset" and b"\0" not in data:
                if attr["eol"] == "crlf":
                    data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                elif attr["eol"] == "lf":
                    data = data.replace(b"\r\n", b"\n")
            files.append({"path": name, "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest()})
    finally:
        reader.stdin.close()
        reader.stdout.close()
        assert reader.wait(timeout=30) == 0
    manifest = {"schema_version": "bf-source-publication-v1",
                "scope": "Full current BF project and accepted ABC increment; manifest self excluded. Original raw evidence is the version-bound ABC Release asset. Git checkout EOL attributes are respected.",
                "files": files}
    DESTINATION.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"files": len(files), "bytes": sum(f["bytes"] for f in files)}))


if __name__ == "__main__":
    main()
