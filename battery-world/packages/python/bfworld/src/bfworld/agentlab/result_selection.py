"""Shared browsing/export scopes. Latest means recorded recently, never adopted."""


def latest_ids(results, files):
    rows=sorted(results,key=lambda r:r.get('created',0),reverse=True)
    live=[r for r in rows if not r.get('case_id') and r.get('kind')!='proposal']
    pool=live or rows
    selected=set();seen=set();successful=set()
    for row in pool:
        key=row.get('group_key') or (row.get('source_type'),row.get('kind'),row.get('domain'),
                                    row.get('case_id'),row.get('label') if row.get('case_id') else '')
        if key not in seen:
            selected.add(row['id']);seen.add(key)
        if row['status'] in ('SUCCEEDED','PUBLISHED') and key not in successful and row.get('files'):
            selected.add(row['id']);successful.add(key)
    file_ids={f['id'] for r in rows if r['id'] in selected for f in r.get('files',[])}
    # Individually published files have no result row. Keep the latest same-name
    # publication, while the full-history scope preserves every revision.
    published=set()
    for f in sorted(files,key=lambda f:(f.get('created_revision') or 0,f.get('created') or 0),reverse=True):
        if f.get('result_id')!='published':continue
        key=(f.get('domain'),f['name'])
        if key not in published:file_ids.add(f['id']);published.add(key)
    return selected,file_ids


def choices(catalog):
    options=[{'id':'latest','label':'最近产物 · 各类最新记录'},
             {'id':'session','label':'全部记录 · 含历史与独立运行'}]
    if catalog.get('candidate'):
        options.insert(0,{'id':'candidate','label':catalog['candidate']['label']+' · 同版工程'})
    if catalog['revision'] is not None:
        options.append({'id':'assembly','label':'装配 v'+str(catalog['revision'])+' · 已绑定适用成果'})
    seen=set()
    for row in catalog['results']:
        if not row.get('case_id'):continue
        key='case:'+row['case_id']+':'+row['case_version']
        if key not in seen:options.append({'id':key,'label':row['case_title']+' · '+row['case_version']});seen.add(key)
    return options


def select(catalog, selection):
    if selection not in {x['id'] for x in choices(catalog)}:raise ValueError('STUDIO_SELECTION_NOT_FOUND')
    rows=catalog['results'];files=catalog['files'];verdict=None
    if selection=='candidate':
        design_id=catalog['candidate']['design_id']
        rows=[r for r in rows if r.get('candidate_id')==design_id]
        files=[f for f in files if f.get('candidate_id')==design_id]
        verdict=catalog['candidate'].get('verdict')
    elif selection=='latest':
        ids,file_ids=latest_ids(rows,files)
        rows=[r for r in rows if r['id'] in ids];files=[f for f in files if f['id'] in file_ids]
    elif selection=='assembly':
        files=[f for f in files if f['applicability']['state'] in ('current','reused')]
        ids={f['result_id'] for f in files};rows=[r for r in rows if r['id'] in ids]
        verdict=catalog['verdict']
    elif selection.startswith('case:'):
        rows=[r for r in rows if 'case:'+str(r.get('case_id'))+':'+str(r.get('case_version'))==selection]
        ids={f['id'] for r in rows for f in r['files']};files=[f for f in files if f['id'] in ids]
    else:verdict=catalog['verdict']
    file_ids={f['id'] for f in files}
    rows=[dict(r,files=[f for f in r['files'] if f['id'] in file_ids],
               presentations=[p for p in r.get('presentations',[]) if p.get('file_id') in file_ids]) for r in rows]
    return rows,files,verdict
