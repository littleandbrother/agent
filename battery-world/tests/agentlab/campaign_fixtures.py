"""Portable, capability-disabled fixtures; never live campaign registrations.

Historical contracts and sealed inputs retain their original bytes. Only the
test mount resolves their recorded workspace paths to this checkout.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
RECORDED_WORKSPACE = Path("/Users/depengsu/Documents/Long-Horizon AI Agent")


def published_path(recorded: str | Path) -> Path:
    path = Path(recorded)
    relative = path.relative_to(RECORDED_WORKSPACE)
    target = ROOT.parent / relative
    if not target.resolve().is_relative_to(ROOT.parent.resolve()):
        raise ValueError("Recorded artifact escapes the published checkout")
    return target


@contextmanager
def archived_ar_reference():
    """Mount the exact old success/failure receipts, with no solver execution."""
    archive = ROOT / "tests/fixtures/campaign20261019/ar-reference.zip"
    with tempfile.TemporaryDirectory(prefix="bf-ar-readback-") as name:
        mount = Path(name).resolve()
        with zipfile.ZipFile(archive) as saved:
            if sum(info.file_size for info in saved.infolist()) > 60_000_000:
                raise ValueError("Archived reference exceeds its fixture cap")
            for info in saved.infolist():
                target = mount / info.filename
                if (Path(info.filename).is_absolute()
                        or ".." in Path(info.filename).parts
                        or not target.resolve().is_relative_to(mount)):
                    raise ValueError("Unsafe archived reference path")
            saved.extractall(mount)
        yield mount / "reference-run-001"


def phase3_initial_cache(mount: Path) -> Path:
    """Remount saved exact-input responses, keeping originals unchanged.

    Only a test projection of result-path fields and the cache index is written.
    No result values, input identities or original artifact bytes are changed.
    """
    fixtures = ROOT / "tests/fixtures/campaign20261019"
    metadata = json.loads((fixtures / "phase3-initial-cache.json").read_text())
    saved = mount / "saved-cache"
    saved.mkdir()
    with zipfile.ZipFile(fixtures / metadata["archive"]) as archive:
        names = {entry["path"] for entry in metadata["files"]}
        if (set(archive.namelist()) != names
                or sum(info.file_size for info in archive.infolist()) > 4_000_000):
            raise ValueError("Unexpected archived cache contents")
        for entry in metadata["files"]:
            name = Path(entry["path"])
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("Unsafe archived cache path")
            data = archive.read(entry["path"])
            if (len(data) != entry["bytes"]
                    or hashlib.sha256(data).hexdigest() != entry["sha256"]):
                raise ValueError("Archived cache artifact drift")
            target = saved / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    prefix = Path("/Users/depengsu/.local/share")

    def remount(path):
        return saved / Path(path).relative_to(prefix)

    index = json.loads((saved / "bf-phase3-20261020/initial-cache.json").read_text())
    projection = mount / "cache-projection"
    projection.mkdir()
    for key, entry in index.items():
        original_result = remount(entry["result_path"])
        value = json.loads(original_result.read_text())
        if value.get("raw_path"):
            value["raw_path"] = str(remount(value["raw_path"]))
        result = projection / (key + ".json")
        result.write_text(json.dumps(value, sort_keys=True) + "\n")
        artifacts = {str(remount(path)): sha for path, sha in entry["artifacts"].items()
                     if remount(path) != original_result}
        entry["result_sha256"] = hashlib.sha256(result.read_bytes()).hexdigest()
        artifacts[str(result)] = entry["result_sha256"]
        entry.update(result_path=str(result), artifacts=artifacts)
    initial = projection / "initial-cache.json"
    initial.write_text(json.dumps(index, sort_keys=True) + "\n")
    return initial


def interface_registration(mount: Path, bf) -> tuple[Path, Path]:
    """Register a unit-test owner over a small set of frozen read-only inputs.

    The production resource gate is exercised without mocking it, enabling any
    execution capability, or impersonating the original B runtime/profile.
    """
    protocol = copy.deepcopy(bf.load_protocol(ROOT))
    root = mount.resolve() / "checkout/battery-world"
    source_names = set(protocol["inputs"]) | {bf.MODULE}
    source_names.update(str(path.relative_to(ROOT))
                        for path in (ROOT / bf.LEGACY).rglob("*")
                        if path.is_file() and not path.is_symlink())
    for name in sorted(source_names):
        source = bf.safe_path(ROOT, name)
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    runtime = mount.resolve() / "disabled-runtime"
    profile = mount.resolve() / "unit-profile.json"
    bf.write_json(profile, {
        "id": "offline-unit-fixture-not-a-campaign-run",
        "source_root": str(root.parent),
        "runtime_root": str(runtime),
        "baseline": {"manifest_sha256": protocol["baseline_manifest_sha256"]},
        "capabilities": {"model": False, "agent": False, "native": False},
    })
    protocol["owner"] = "offline-unit-fixture"
    protocol["profile_sha256"] = bf.sha(profile.read_bytes())
    protocol["runtime_root"] = str(runtime)
    bf.write_json(root / bf.PROTOCOL, protocol)
    (root / bf.OUTPUT).mkdir(parents=True, exist_ok=True)
    return root, profile
