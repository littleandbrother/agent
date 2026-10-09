"""Native EDA edits invalidate only the delivery checks that consume them.

This supplements existing semantic assembly hashes. It never launches checks.
Unknown writes remain changes until reconciled; query/export/help are observations.
"""
import json

READS = {'info','get','list','read','query','inspect','check','drc','export','export-source',
         'export-dsn','export-specctra','save','reload','snapshot','screenshot','search',
         'resolve','pins','netlist','nets','pages','docs','ls','current','status','open','switch',
         'summary','diff','validate','bridge-check','module-check','board-info','drc-rules','dump',
         'escape-plan','floorplan','layout-lint','layout-plan','layout-score','module-owned','net-classes',
         'net-path','outline-get','pour-list','poured-list','report','track-list','via-list','view-filter',
         'view-side','layer-set','layer-visibility','layers','stage-snapshot','attribute-inspect','clusters',
         'connectivity','connectivity-diff','design-diff','designator-geometry','export-image','extract-layout',
         'layout-render','layout-sheet-plan','lib-layout','plan','power-layout','sheet-geometry','text-list',
         'titleblock-get','zone-arrange','zone-plan','zone-review'}


def change_domains(argv):
    if not argv or '--help' in argv or '-h' in argv or '--dry-run' in argv: return set()
    head, operation = argv[0], argv[1] if len(argv) > 1 else ''
    if head in ('api','spec','view','lib','bom','project','actions'): return set()
    if head == 'call':
        argv = operation.split('.')
        head, operation = argv[0], argv[1] if len(argv) > 1 else ''
        if argv[-1] in READS:return set()
    if operation in READS: return set()
    if head in ('pcb','board'):
        geometry=operation.startswith('outline-') or operation in ('outline','component','place','move','layout','resize','import','apply','sync','rebind',
            'add-component','align','arrange','auto-place','clear','delete','distribute','grid-snap','import-changes','modify','mount-holes','new-board','place-constrained','refine','slot','stackup')
        return {'pcb_geometry','pcb_electrical'} if geometry or head == 'board' else {'pcb_electrical'}
    if head in ('sch','schematic'):
        return set() if operation in ('layout','annotate','align') else {'circuit'}
    # Typed playbooks/doc imports may contain several changes; inspect the
    # actual artifacts before rebinding, rather than silently keeping a PASS.
    if head in ('apply','doc'): return {'circuit','pcb_geometry','pcb_electrical'}
    return set()


def dimensions(task):
    if task in ('cad','drawings','clearance','presentation'): return {'pcb_geometry'}
    if task in ('schematic','circuit-selection','spice','electrical-checks','firmware','firmware-resources','joint'):
        return {'circuit'}
    if task in ('pcb','pcb-checks','manufacturing'): return {'circuit','pcb_geometry','pcb_electrical'}
    if task in ('release','system-acceptance'): return {'circuit','pcb_geometry','pcb_electrical'}
    return set()


def native_inputs(app, owner, task):
    required = dimensions(task)
    if not required: return {}
    with app.store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='eda_cli_jobs'").fetchone(): return {}
        rows = db.execute('SELECT id,request,status,result FROM eda_cli_jobs WHERE owner=? ORDER BY created,id', (owner,)).fetchall()
    latest = {}
    for row in rows:
        request = json.loads(row['request'])
        for key in change_domains(request.get('argv', [])) & required:
            latest[key] = {'job_id': row['id'], 'status': row['status'], 'project': request.get('project')}
    return latest
