"""Exact finite numerical observations of trusted ngspice artifacts.

No design advice, interpolation, circuit acceptance or new solver execution.
"""
import hashlib
import io
import struct
from .engineering_projects import raw_readback


def observe(path):
    integrity=raw_readback(path);data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=integrity['raw_sha256']:raise ValueError('SPICE_OBSERVATION_INPUT_CHANGED')
    stream=io.BytesIO(data);plots=[]
    for plot in integrity['plots']:
        line=stream.readline()
        while not line.strip():line=stream.readline()
        header=[line]
        while True:
            line=stream.readline()
            if line.strip() in (b'Values:',b'Binary:'):break
            header.append(line)
        text=b''.join(header).decode('utf-8').replace('\r\n','\n')
        variables=[s.split() for s in text.split('Variables:\n',1)[1].splitlines() if s.strip()]
        n=plot['variables'];factor=2 if plot['complex'] else 1
        stats=[[None]*factor for _ in range(n)]
        def add(row):
            for j in range(n):
                for k in range(factor):
                    value=row[j*factor+k];s=stats[j][k]
                    if s is None:stats[j][k]=[value,value,value,value]
                    else:s[0]=min(s[0],value);s[1]=max(s[1],value);s[3]=value
        if plot['encoding']=='binary':
            body=stream.read(plot['points']*n*factor*8)
            for row in struct.iter_unpack('='+str(n*factor)+'d',body):add(row)
        else:
            for _ in range(plot['points']):
                row=[]
                for j in range(n):
                    raw=stream.readline().decode('ascii').strip()
                    if j==0:raw=raw.split(None,1)[1]
                    row.extend(float(v) for v in raw.split(','))
                add(row)
        channels=[]
        for j,v in enumerate(variables):
            for k,s in enumerate(stats[j]):
                channels.append({'index':j,'name':v[1],'unit':v[2],'component':'real' if k==0 else 'imaginary',
                                 'minimum':s[0],'maximum':s[1],'first':s[2],'last':s[3]})
        plots.append({**plot,'channels':channels})
    return {'schema_version':'bf-spice-numeric-observation-v1','raw_sha256':integrity['raw_sha256'],
        'plots':plots,'solver_runs_added':0,'scope':'Exact solver samples only; model applicability, energy balance and circuit requirements remain separate checks.'}
