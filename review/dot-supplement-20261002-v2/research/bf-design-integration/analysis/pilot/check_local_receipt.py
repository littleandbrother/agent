"""Cross-check a supplied local integrity receipt; no large-file access."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
from audit_pilot import Archive, require, sha

RECEIPT_SHA='9c762dcb27edc4f345ede839cf8fada0b3147ce780b80b31362c659d051ef5e1'

def check(archive_path, receipt_path):
    raw=Path(receipt_path).read_bytes()
    require(len(raw)==9633 and sha(raw)==RECEIPT_SHA,'SUPPLIED_RECEIPT_IDENTITY')
    receipt=json.loads(raw)
    archive=Archive(archive_path)
    manifest_raw=archive.read('large-native-artifacts.json')
    require(receipt['source_manifest']=={'path':'report/large-native-artifacts.json','sha256':sha(manifest_raw)},'SOURCE_MANIFEST')
    expected={'runs/'+f['run']+'/'+f['name']:(f['bytes'],f['sha256']) for f in json.loads(manifest_raw)}
    actual={f['path']:f for f in receipt['files']}
    require(len(actual)==len(receipt['files'])==24 and set(actual)==set(expected),'FILE_SET')
    total=0
    for name,(size,digest) in expected.items():
        p=PurePosixPath(name);require(not p.is_absolute() and '..' not in p.parts,'RELATIVE_PATH')
        f=actual[name]
        require(f['expected_bytes']==f['actual_bytes']==size and f['expected_sha256']==f['actual_sha256']==digest and f['status']=='verified','FILE_BINDING')
        total+=size
    require(total==receipt['total_bytes']==688230224 and receipt['file_count']==24,'TOTALS')
    require(receipt['dataset_count']==1 and receipt['path_aliases']['same_dataset'] is True,'DATASET_ALIAS')
    return {'schema':'bf-local-native-integrity-crosscheck-v1','status':'SUPPLIED_LOCAL_RECEIPT_MATCHES_SEALED_MANIFEST',
        'receipt_sha256':RECEIPT_SHA,'source_manifest_sha256':sha(manifest_raw),'files':24,'bytes':total,'dataset_count':1,
        'local_integrity':'24 retained files reported verified and stable by supplied local receipt',
        'cloud_verification':'receipt bytes and manifest cross-reference only',
        'native_bytes_read_by_this_check':0,'raw_artifact_hashes_independently_verified_here':False,
        'raw_replay':False,'missing_channel_flags_changed':False,'energy_recomputed':False,'scientific_admission':False,
        'prior_audit_modified':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if os.path.lexists(args.out) or args.out.resolve() in (args.archive.resolve(),args.receipt.resolve()):p.error('Output must be a new path')
    try:result=check(args.archive,args.receipt);code=0
    except Exception as exc:result={'status':'BLOCKED','error_type':type(exc).__name__,'error':str(exc)};code=1
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'status':result['status']}));return code

if __name__=='__main__':raise SystemExit(main())
