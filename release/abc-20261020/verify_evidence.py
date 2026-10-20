"""Read back the accepted evidence archive; never execute its contents."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import sys
import zipfile

HERE = Path(__file__).resolve().parent


def main():
    archive = Path(sys.argv[1])
    receipt = json.loads((HERE / "asset.json").read_text())
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    assert archive.stat().st_size == receipt["bytes"]
    assert digest == receipt["sha256"], "ARCHIVE_DIGEST_MISMATCH"
    expected = json.loads((HERE / "evidence-manifest.json").read_text())
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert len(names) == len(set(names)), "DUPLICATE_ARCHIVE_PATH"
        assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts for n in names)
        assert json.loads(bundle.read("evidence-manifest.json")) == expected
        included = {"evidence-manifest.json"}
        for entry in expected["files"]:
            name = "bf-abc-20261020/" + entry["path"]
            data = bundle.read(name)
            assert len(data) == entry["bytes"]
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
            included.add(name)
        assert set(names) == included, "UNMANIFESTED_ARCHIVE_FILE"
    print(json.dumps({"ok": True, "files": len(expected["files"]), "sha256": digest}))


if __name__ == "__main__":
    main()
