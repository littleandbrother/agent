#!/usr/bin/env python3
"""Read back all four attempts; never launches a model or a physical solver."""
import hashlib
import argparse
import json
from pathlib import Path
import time
import zipfile

RUNTIME = Path.home()/'.local/share/bf-campaign-20261019-s0'
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='verify without rewriting the sealed readback receipt')
    args = parser.parse_args()
    repo = RUNTIME/'workbench/design-lab/repository'
    seen = {}
    started = time.time()

    def verify(path, expected, size=None):
        if path not in seen:
            h = hashlib.sha256()
            with path.open('rb') as stream:
                while chunk := stream.read(8*1024*1024):
                    h.update(chunk)
            seen[path] = {'sha256':h.hexdigest(), 'bytes':path.stat().st_size}
        actual = seen[path]
        assert actual['sha256']==expected, str(path)
        assert size is None or actual['bytes']==size, str(path)

    blob_refs = cache_checks = 0
    releases = []
    trials = []
    for trial in sorted((RUNTIME/'trials').iterdir()):
        executions = json.loads((trial/'executions.json').read_text())
        for execution in executions:
            for desc in execution['artifacts'].values():
                verify(repo/'blobs'/desc['sha256'], desc['sha256'], desc['bytes'])
                blob_refs += 1
        for cache in sorted((trial/'cache-after').iterdir()):
            if not (cache/'completed.json').is_file():
                continue
            meta = json.loads((cache/'completed.json').read_text())
            assert meta['status']=='SUCCEEDED'
            for rel, sha in meta['outputs'].items():
                verify(cache/rel, sha)
                cache_checks += 1
        view = json.loads((trial/'view.json').read_text())
        for release in view['releases']:
            assert release['target']==view['project']['submitted']
            archive = repo/'releases'/(release['id']+'.zip')
            with zipfile.ZipFile(archive) as package:
                assert package.testzip() is None, str(archive)
                manifest = json.loads(package.read('manifest.json'))
                assert manifest==release, 'RELEASE_MANIFEST_DRIFT'
                for rel, desc in release['files'].items():
                    verify(repo/'blobs'/desc['sha256'],desc['sha256'],desc['bytes'])
                    assert hashlib.sha256(package.read('engineering/'+rel)).hexdigest()==desc['sha256']
            releases.append({'trial':trial.name, 'release':release['id'],
                             'archive_sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),
                             'archive_bytes':archive.stat().st_size, 'crc':'PASS', 'source_binding':'PASS'})
        trials.append({'trial':trial.name, 'executions':len(executions), 'releases':len(view['releases'])})
    result = {'status':'PASS', 'execution_artifact_references':blob_refs,
              'cache_output_checks':cache_checks, 'unique_files':len(seen),
              'bytes_read':sum(v['bytes'] for v in seen.values()), 'wall_s':time.time()-started,
              'trials':trials, 'releases':releases,
              'files':{str(k.relative_to(RUNTIME)):v for k,v in seen.items()},
              'boundary':'Hash, length, ZIP CRC and source/version readback; no model, new simulation or physical qualification.'}
    if not args.check:
        (HERE/'native-artifact-readback.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','trials','releases')}))


if __name__=='__main__':
    main()
