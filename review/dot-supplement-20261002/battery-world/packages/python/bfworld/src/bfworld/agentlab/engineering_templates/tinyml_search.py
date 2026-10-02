"""Bounded numpy MLP architecture search; generated data is explicitly a fixture."""
import json, hashlib, time, sys
from pathlib import Path
import numpy as np


def hash_bytes(raw): return hashlib.sha256(raw).hexdigest()
def save(root,name,value): (root/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def dataset(spec,seed):
    if spec.get('demo'):
        rng=np.random.default_rng(seed);X=[];y=[];groups=[]
        for group in range(18):
            for label in range(3):
                for _ in range(12):
                    duration=float(rng.uniform(70,260) if label!=2 else rng.uniform(750,1600))
                    gap=float(rng.uniform(80,350) if label==1 else 0)
                    second=float(rng.uniform(70,260) if label==1 else 0)
                    X.append([duration,gap,second,duration+gap+second+rng.uniform(10,40)])
                    y.append(label);groups.append('synthetic-session-'+str(group))
        spec={'X':X,'y':y,'groups':groups,'labels':['single','double','long'],
              'features':['press_1_ms','gap_ms','press_2_ms','total_ms'],'feature_scale':[2000]*4,
              'source_kind':'synthetic-fixture','source':'Seeded button timing generator, not collected from users or sensors'}
    X=np.asarray(spec.get('X'),dtype=np.float64);y=np.asarray(spec.get('y'),dtype=np.int64)
    groups=spec.get('groups');labels=spec.get('labels');features=spec.get('features');scale=np.asarray(spec.get('feature_scale'),dtype=float)
    if X.ndim!=2 or not 24<=len(X)<=20000 or not 1<=X.shape[1]<=16 or y.shape!=(len(X),): raise ValueError('DATASET_SHAPE_INVALID')
    if not isinstance(labels,list) or not 2<=len(labels)<=8 or len(set(labels))!=len(labels) or not all(isinstance(x,str) for x in labels): raise ValueError('DATASET_LABELS_INVALID')
    if not isinstance(groups,list) or len(groups)!=len(X) or not all(isinstance(x,str) for x in groups): raise ValueError('DATASET_GROUPS_REQUIRED')
    if len(set(groups))<6 or min(y)<0 or max(y)>=len(labels) or set(y)!=set(range(len(labels))): raise ValueError('DATASET_GROUP_OR_CLASS_COVERAGE')
    if scale.shape!=(X.shape[1],) or not np.all(np.isfinite(X)) or not np.all(np.isfinite(scale)) or np.any(scale<=0): raise ValueError('DATASET_SCALE_INVALID')
    if not isinstance(features,list) or len(features)!=X.shape[1] or not all(isinstance(x,str) for x in features): raise ValueError('DATASET_FEATURES_REQUIRED')
    if spec.get('source_kind') not in ('measured','public-dataset','synthetic-fixture') or not isinstance(spec.get('source'),str) or not spec['source'].strip(): raise ValueError('DATASET_PROVENANCE_REQUIRED')
    X=X/scale
    if np.max(np.abs(X))>8:raise ValueError('DATASET_INPUT_RANGE_EXCEEDS_FIXED_POINT_CONTRACT')
    # Entire recording/session groups stay in one split. No adjacent-window leakage.
    unique=sorted(set(groups));np.random.default_rng(seed).shuffle(unique)
    a=max(2,int(.6*len(unique)));b=max(a+1,int(.8*len(unique)))
    split={k:np.where(np.isin(groups,ids))[0] for k,ids in [('train',unique[:a]),('validation',unique[a:b]),('test',unique[b:])]}
    for ids in split.values():
        if set(y[ids])!=set(range(len(labels))):raise ValueError('DATASET_SPLIT_CLASS_COVERAGE')
    # Identical feature vectors cannot cross splits, even with renamed groups.
    seen={}
    for name,ids in split.items():
        for i in ids:
            key=tuple(X[i]);prior=seen.setdefault(key,name)
            if prior!=name:raise ValueError('DATASET_DUPLICATE_ACROSS_SPLITS')
    return spec,X,y,split


def train(X,y,dims,epochs,seed):
    rng=np.random.default_rng(seed)
    weights=[rng.normal(0,np.sqrt(2/a),(a,b)) for a,b in zip(dims,dims[1:])]
    biases=[np.zeros(b) for b in dims[1:]]
    for _ in range(epochs):
        acts=[X]
        for i,(w,b) in enumerate(zip(weights,biases)):
            z=acts[-1]@w+b;acts.append(np.maximum(z,0) if i<len(weights)-1 else z)
        logits=acts[-1]-np.max(acts[-1],axis=1,keepdims=True);e=np.exp(logits);delta=e/e.sum(axis=1,keepdims=True)
        delta[np.arange(len(y)),y]-=1;delta/=len(y)
        grads=[]
        for i in range(len(weights)-1,-1,-1):
            grads.append((acts[i].T@delta,delta.sum(axis=0)))
            if i:delta=(delta@weights[i].T)*(acts[i]>0)
        for i,(dw,db) in enumerate(reversed(grads)):
            weights[i]-=.15*dw;biases[i]-=.15*db
    return weights,biases


def predict(X,weights,biases):
    for i,(w,b) in enumerate(zip(weights,biases)):
        X=X@w+b
        if i<len(weights)-1:X=np.maximum(X,0)
    return X.argmax(axis=1)


def quantize(weights,biases):
    layers=[]
    for w,b in zip(weights,biases):
        shift=max(0,min(14,int(np.floor(np.log2(127/max(float(np.abs(w).max()),1e-9))))))
        qw=np.clip(np.rint(w*2**shift),-127,127).astype(np.int64)
        qb=np.rint(b*1024*2**shift).astype(np.int64)
        layers.append(dict(inputs=w.shape[0],outputs=w.shape[1],shift=shift,weights=qw.tolist(),bias=qb.tolist()))
    return layers


def integer_logits(X,layers):
    x=np.rint(X*1024).astype(np.int64)
    for i,l in enumerate(layers):
        acc=x@np.asarray(l['weights'],dtype=np.int64)+np.asarray(l['bias'],dtype=np.int64)
        x=np.trunc(acc/(2**l['shift'])).astype(np.int64)
        if i<len(layers)-1:x=np.clip(x,0,32767)
    return x


def export_c(root,layers,inputs,classes):
    text=['#include "model.h"','#include <stdint.h>']
    for i,l in enumerate(layers):
        flat=[v for row in l['weights'] for v in row]
        text.append('static const int8_t w%d[]={%s};'%(i,','.join(map(str,flat))))
        text.append('static const int32_t b%d[]={%s};'%(i,','.join(map(str,l['bias']))))
    maxdim=max([inputs,classes]+[l['outputs'] for l in layers]);text.append('void model_logits(const int16_t *input,int32_t *output){int32_t a[%d],b[%d];for(int i=0;i<%d;i++)a[i]=input[i];'%(maxdim,maxdim,inputs))
    for i,l in enumerate(layers):
        text.append('for(int j=0;j<%d;j++){int64_t acc=b%d[j];for(int k=0;k<%d;k++)acc+=(int64_t)a[k]*w%d[k*%d+j];b[j]=(int32_t)(acc/%d);%s}for(int j=0;j<%d;j++)a[j]=b[j];'%(l['outputs'],i,l['inputs'],i,l['outputs'],2**l['shift'],'if(b[j]<0)b[j]=0;if(b[j]>32767)b[j]=32767;' if i<len(layers)-1 else '',l['outputs']))
    text.append('for(int i=0;i<%d;i++)output[i]=a[i];}'%classes)
    text.append('int model_predict(const int16_t *x){int32_t y[%d];model_logits(x,y);int best=0;for(int i=1;i<%d;i++)if(y[i]>y[best])best=i;return best;}'%(classes,classes))
    (root/'model.c').write_text('\n'.join(text)+'\n')
    (root/'model.h').write_text('#pragma once\n#include <stdint.h>\n#define MODEL_INPUTS %d\n#define MODEL_CLASSES %d\nvoid model_logits(const int16_t*,int32_t*);\nint model_predict(const int16_t*);\n'%(inputs,classes))


def run(root):
    job=json.loads((root/'input.json').read_text());p=job['parameters'];seed=p['seed'];spec,X,y,splits=dataset(job['dataset'],seed)
    save(root,'dataset.json',spec)
    save(root,'split.json',{k:ids.tolist() for k,ids in splits.items()})
    candidates=[];models=[];start=time.monotonic();nclasses=len(spec['labels'])
    for index,hidden in enumerate(p['architectures']):
        dims=[X.shape[1],*hidden,nclasses];w,b=train(X[splits['train']],y[splits['train']],dims,p['epochs'],seed+index)
        layers=quantize(w,b);val=splits['validation']
        acc=float((integer_logits(X[val],layers).argmax(1)==y[val]).mean())
        params=sum(a*b+b for a,b in zip(dims,dims[1:]));macs=sum(a*b for a,b in zip(dims,dims[1:]))
        weights_bytes=sum(l['inputs']*l['outputs']+l['outputs']*4 for l in layers)
        candidate=dict(id='mlp-'+ '-'.join(map(str,hidden)),architecture=dims,parameters=params,macs_per_inference=macs,
                       weight_storage_bytes=weights_bytes,activation_workspace_bytes=8*max(dims),validation_int8_accuracy=acc,
                       validation_fp32_accuracy=float((predict(X[val],w,b)==y[val]).mean()),
                       resource_estimate_only=True)
        candidates.append(candidate);models.append(layers)
    # Only validation accuracy and analytical size choose the winner; test is held out.
    feasible=[i for i,c in enumerate(candidates) if c['weight_storage_bytes']<=8192 and c['activation_workspace_bytes']+1024<=8192]
    if not feasible:raise ValueError('NAS_NO_RESOURCE_FEASIBLE_CANDIDATE')
    best=min(feasible,key=lambda i:(-candidates[i]['validation_int8_accuracy'],candidates[i]['parameters']))
    winner=candidates[best];layers=models[best];test=splits['test'];logits=integer_logits(X[test],layers);pred=logits.argmax(1)
    matrix=np.zeros((nclasses,nclasses),dtype=int)
    for truth,guess in zip(y[test],pred):matrix[truth,guess]+=1
    for c in candidates:c['pareto']=not any(o['validation_int8_accuracy']>=c['validation_int8_accuracy'] and o['parameters']<=c['parameters'] and (o['validation_int8_accuracy']>c['validation_int8_accuracy'] or o['parameters']<c['parameters']) for o in candidates)
    export_c(root,layers,X.shape[1],nclasses)
    vectors=np.rint(X[test[:64]]*1024).astype(np.int64);expected=integer_logits(X[test[:64]],layers)
    save(root,'test-vectors.json',dict(input_q10=vectors.tolist(),logits_q10=expected.tolist(),labels=y[test[:64]].tolist()))
    model=dict(schema_version='bf-mlp-int8-v1',architecture=winner['architecture'],layers=layers,input_scale_q=1024,
               features=spec['features'],feature_scale=spec['feature_scale'],labels=spec['labels'],input_range_normalized=[-8,8],
               arithmetic='int8 weights, int32 activations/bias, int64 accumulators, C truncation division, ReLU clamp 32767')
    save(root,'model.json',model);save(root,'architecture.json',{k:v for k,v in model.items() if k!='layers'})
    save(root,'nas-candidates.json',dict(method='bounded exhaustive MLP widths/depths with full-batch training',seed=seed,epochs=p['epochs'],
        split='recording/session group-disjoint train/validation/test',selection='validation INT8 accuracy descending then parameters ascending',
        resource_filter='analytical weight <=8192 bytes, workspace +1024 <=8192; final linked binary checked separately',candidates=candidates,winner=winner['id'],seconds=time.monotonic()-start))
    metrics=dict(schema_version='bf-tinyml-metrics-v1',winner=winner,model_sha256=hash_bytes((root/'model.json').read_bytes()),
                 dataset_sha256=hash_bytes((root/'dataset.json').read_bytes()),split_sha256=hash_bytes((root/'split.json').read_bytes()),
                 source_kind=spec['source_kind'],test_int8_accuracy=float((pred==y[test]).mean()),confusion_matrix=matrix.tolist(),
                 real_world_accuracy_verified=False,latency_ms_mcu=None,power_mw_mcu=None,energy_uj_per_inference=None,
                 measured_on_mcu=False,clock_hz_measured=None,measurement_status='not_measured',
                 claim='Dataset evaluation and generated integer C only; synthetic fixture scores are pipeline checks, not product recognition performance.')
    save(root,'metrics.json',metrics)

if __name__=='__main__':run(Path(sys.argv[1]))
