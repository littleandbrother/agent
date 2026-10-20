"""Remove only the frozen list of reproducible caches; retain source readback."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import shutil
import subprocess
import zlib

HERE = Path(__file__).resolve().parent
ENV = Path('/Users/depengsu/.local/share/bf-agent-runtime/product-cad')


def source_digest(items):
    digest = hashlib.sha256()
    sources = sorted({x['source'] for x in items})
    for name in sources:
        file_digest = hashlib.sha256()
        with open(name, 'rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                file_digest.update(chunk)
        digest.update((name + '\0' + file_digest.hexdigest() + '\n').encode())
    return digest.hexdigest(), len(sources)


def main():
    if (HERE / 'cache-result.json').exists():
        raise SystemExit('Maintenance already recorded; no automatic repeat.')
    raw = (HERE / 'cache-plan.json').read_bytes()
    plan = json.loads(raw)
    items = plan['items']
    if shutil.disk_usage(ENV).free < 2_000_000_000 + 4_000_000:
        raise SystemExit('MAINTENANCE_RESERVE')
    for item in items:
        path = Path(item['path'])
        source = Path(item['source'])
        stat = path.lstat()
        if (not path.is_relative_to(ENV) or path.parent.name != '__pycache__' or
                path.is_symlink() or source != Path(importlib.util.source_from_cache(str(path))) or
                not source.is_file() or stat.st_flags & 0x40000000 or
                (stat.st_ino, stat.st_size, stat.st_mtime_ns) !=
                (item['inode'], item['bytes'], item['mtime_ns'])):
            raise SystemExit('CACHE_IDENTITY_OR_SOURCE_CHANGED:' + str(path))
    opened = subprocess.run(['/usr/sbin/lsof', '-nP', '-F', 'n', '+D', str(ENV)],
                            capture_output=True, text=True, timeout=20)
    if opened.returncode not in (0, 1) or opened.stderr:
        raise SystemExit('OPEN_HANDLE_AUDIT_UNAVAILABLE')
    cache_paths = {x['path'] for x in items}
    if any(line[1:] in cache_paths for line in opened.stdout.splitlines() if line.startswith('n')):
        raise SystemExit('CACHE_OPEN')
    source_before, count = source_digest(items)
    frozen = HERE / 'cache-plan.json.zlib'
    with frozen.open('xb') as target:
        target.write(zlib.compress(raw))
    if zlib.decompress(frozen.read_bytes()) != raw:
        raise SystemExit('PLAN_READBACK_FAILED')
    before = shutil.disk_usage(ENV).free
    for item in items:
        Path(item['path']).unlink()
    directories = 0
    for directory in {Path(x['path']).parent for x in items}:
        try:
            directory.rmdir()
            directories += 1
        except OSError:
            pass
    after = shutil.disk_usage(ENV).free
    source_after, _ = source_digest(items)
    if source_before != source_after:
        raise SystemExit('SOURCE_READBACK_FAILED')
    (HERE / 'cache-plan.json').unlink()
    result = {'status': 'PASS', 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'removed_cache_files': len(items), 'removed_empty_cache_directories': directories,
        'source_files_verified': count, 'source_digest_before': source_before,
        'source_digest_after': source_after, 'plan_raw_sha256': hashlib.sha256(raw).hexdigest(),
        'plan_encoding': 'zlib JSON; metadata only, no cache or source backup',
        'free_before_bytes': before, 'free_after_bytes': after,
        'actual_free_space_delta_bytes': after - before,
        'original_inventory_estimate_bytes': 2_000_000,
        'original_inventory_metadata_bytes': len(raw),
        'correction_before_cache_mutation': 'Metadata estimate raised to 4 MB; initial 2 MB estimate was low.',
        'dependencies_removed': 0, 'paid_model_requests': 0, 'native_dispatches': 0,
        'restore': 'Bytecode is reproducible from the unchanged .py files with Python 3.11. Runs here use -B to avoid regeneration.'}
    (HERE / 'cache-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
