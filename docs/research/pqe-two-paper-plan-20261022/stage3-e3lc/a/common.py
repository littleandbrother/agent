"""Small A-owned immutable-artifact helpers, with no execution on import."""
from pathlib import Path
import hashlib
import importlib.util
import json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
CAN=ROOT/'workbench/bf-campaign-s0-20261019/battery-world'
STUDY=CAN/'studies/pqe20261022/e3lc'
SRC=CAN/'packages/python/bfworld/src/bfworld/agentlab/pqe20261022'
PACKAGE='BF-PQE-S3-E3LC-20261023-001'


def identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    path.chmod(0o444)


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result
