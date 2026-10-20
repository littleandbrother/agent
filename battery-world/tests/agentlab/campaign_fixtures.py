"""Portable, capability-disabled fixtures; never live campaign registrations.

Historical contracts and sealed inputs retain their original bytes. Only the
test mount resolves their recorded workspace paths to this checkout.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
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
