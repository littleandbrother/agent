"""Measurement admission separate from model-domain checks and method adoption."""
import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
from .contracts import sha,sealed
from ..store import identity

CHANNELS=('time_s','storage_V','supply_V','current_A','event_id','rx_event_id')


def readiness():
    ports=[str(p) for p in Path('/dev').glob('cu.*') if 'Bluetooth' not in p.name and 'debug-console' not in p.name]
    tools={n:shutil.which(n) for n in ('JLinkExe','nrfjprog','openocd','pyocd')}
    architectures={}
    for n,p in tools.items():
        if p:architectures[n]=subprocess.run(['/usr/bin/file',p],capture_output=True,text=True).stdout.strip()
    return {'schema_version':'bf-physical-readiness-v1','observed_at':time.time(),
            'serial_ports':ports,'programming_tools':tools,'tool_architectures':architectures,
            'hardware_connected':'UNCONFIRMED' if not ports else 'SERIAL_PORT_PRESENT_NOT_DEVICE_QUALIFICATION',
            'source_calibration':'NOT_TESTED','flashed_target':'NOT_TESTED','physical_receiver':'NOT_TESTED',
            'physical_end_to_end':'NOT_TESTED','method_RSI':'SEPARATE',
            'required_inputs':['specific harvester/board revision and BOM','approved pin/programmer connection',
                               'instrument identities and calibration uncertainty','raw voltage/current/event/RX captures',
                               'actual target ELF/HEX and immutable build receipt'],
            'no_flashing_or_purchase_performed':True}


def inspect_capture(path, metadata, approved_acquisitions):
    """An acquisition identity must be admitted by the external operator.

    A participant filling in origin=measured never establishes hardware truth.
    Metadata/schema and file checks are admission, not automatic product PASS.
    """
    if not isinstance(metadata,dict) or metadata.get('origin')!='instrument-measurement':
        raise ValueError('PHYSICAL_SYNTHETIC_OR_UNKNOWN_ORIGIN')
    acquisition=metadata.get('acquisition_id')
    approved=approved_acquisitions.get(acquisition)
    if not approved or identity(metadata)!=approved['metadata_sha256']:
        raise ValueError('PHYSICAL_ACQUISITION_NOT_EXTERNALLY_APPROVED')
    path=Path(path)
    if sha(path)!=approved['raw_sha256']:raise ValueError('PHYSICAL_RAW_TAMPER')
    if not metadata.get('instrument_id') or not metadata.get('calibration_receipt') or not metadata.get('design_id'):
        raise ValueError('PHYSICAL_IDENTITY_OR_CALIBRATION_MISSING')
    if set(metadata.get('units',{}))!=set(CHANNELS):raise ValueError('PHYSICAL_CHANNEL_UNITS')
    if metadata['units']!={'time_s':'s','storage_V':'V','supply_V':'V','current_A':'A','event_id':'uint32','rx_event_id':'uint32'}:
        raise ValueError('PHYSICAL_UNIT_MISMATCH')
    with path.open() as stream:
        reader=csv.DictReader(stream)
        if tuple(reader.fieldnames or ())!=CHANNELS:raise ValueError('PHYSICAL_CHANNEL_SET')
        rows=list(reader)
    values=[[float(r[k]) for k in CHANNELS] for r in rows]
    if len(values)<2 or any(not math.isfinite(v) for r in values for v in r):raise ValueError('PHYSICAL_TRACE_INVALID')
    if any(b[0]<=a[0] for a,b in zip(values,values[1:])):raise ValueError('PHYSICAL_CLOCK_INVALID')
    if any(v<0 or v>4294967295 or not v.is_integer() for r in values for v in r[4:]):raise ValueError('PHYSICAL_EVENT_ID_INVALID')
    return {'scope':'Raw capture admission only; physical task/model adjudication still required',
            'acquisition_id':acquisition,'design_id':metadata['design_id'],'rows':len(rows),
            'raw_sha256':sha(path),'file_admission':'PASS','physical_product_passed':False,
            'physical_service':'NOT_CHECKED','model_calibration':'NOT_CHECKED'}
