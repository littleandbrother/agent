import hashlib,json,unittest
from tests.agentlab import test_product_results as fixtures

class EngineeringCasesTest(unittest.TestCase):
    setUp=fixtures.ProductResultsTest.setUp
    tearDown=fixtures.ProductResultsTest.tearDown
    write=fixtures.ProductResultsTest.write

    def test_historical_board_metadata_cannot_become_current_assembly(self):
        m=self.manifest();g=m['groups'][0]
        g.update(reference_only=True,source_revision='D3',scope='Old routed board, not the current circuit')
        g['files'][0].update(label='D3 board reference',sections=['pcb'])
        self.app.results.cases.publish(self.owner,self.base,m)
        a=self.app.results.inspect(self.owner)
        r=next(r for r in a['results'] if r['source_type']=='engineering-case');f=r['files'][0]
        self.assertTrue(r['reference_only']);self.assertEqual('D3',r['source_revision'])
        self.assertEqual('reference',f['applicability']['state'])
        self.assertEqual(['pcb'],f['sections']);self.assertEqual('D3 board reference',f['label'])
        self.assertFalse(a['verdict']['passed']);self.assertFalse(r['hardware_verified'])

    def test_bad_artifact_navigation_metadata_is_rejected(self):
        m=self.manifest();g=m['groups'][0];g['reference_only']=True
        with self.assertRaisesRegex(ValueError,'REFERENCE_REVISION'):
            self.app.results.cases.publish(self.owner,self.base,m)
        g['source_revision']='D3';g['files'][0]['sections']=['invented']
        with self.assertRaisesRegex(ValueError,'FILE_SECTIONS'):
            self.app.results.cases.publish(self.owner,self.base,m)

    def manifest(self):
        self.base=self.root/'case';self.base.mkdir(exist_ok=True)
        (self.base/'motion.mp4').write_bytes(b'fixture-not-real-video')
        return dict(schema_version='bf-engineering-case-v1',id='fixture',version='D2',authority='operator-assisted',hardware_verified=False,autonomous_agent_verified=False,design_sha256='a'*64,groups=[dict(id='animation',domain='mechanical',title='fixture animation',kind='blender',scope='fixture only',files=[dict(path='motion.mp4',sha256=hashlib.sha256((self.base/'motion.mp4').read_bytes()).hexdigest())])])

    def test_owner_isolation_and_immutable_source_snapshot(self):
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m)
        self.app.results.cases.publish(self.owner,self.base,m)
        a=self.app.results.inspect(self.owner);f=next(f for f in a['files'] if f['id'].startswith('case/'))
        self.assertEqual('case',f['applicability']['state']);self.assertEqual(['D2'],a['engineering_cases']);self.assertFalse(a['verdict']['passed'])
        r=next(r for r in a['results'] if r['source_type']=='engineering-case');self.assertEqual('video',r['presentations'][0]['kind']);self.assertFalse(r['autonomous_agent_verified'])
        (self.base/'motion.mp4').write_bytes(b'mutated original')
        path,_=self.app.results.file(self.owner,f['id']);self.assertEqual(b'fixture-not-real-video',path.read_bytes())
        other=self.app.conversations.create('other',None,'case-other')['id']
        with self.assertRaises(PermissionError):self.app.results.file(other,f['id'])
        path.write_bytes(b'mutated snapshot')
        with self.assertRaises(ValueError):self.app.results.file(self.owner,f['id'])

    def test_hash_path_claim_and_version_fail_closed(self):
        m=self.manifest();m['groups'][0]['files'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'HASH'):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.manifest();m['groups'][0]['files'][0]['path']='../secret'
        with self.assertRaises(PermissionError):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.manifest();m['autonomous_agent_verified']=True
        with self.assertRaisesRegex(ValueError,'CLAIM'):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m);m['groups'][0]['title']='silently changed'
        with self.assertRaisesRegex(ValueError,'IMMUTABLE'):self.app.results.cases.publish(self.owner,self.base,m)

    def test_retired_version_has_no_broken_downloads_and_keeps_publication(self):
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m)
        _,files,_=self.app.results.cases.collect(self.owner);key=files[0]['id']
        with self.app.store.connect() as db:
            before=db.execute('SELECT payload FROM engineering_case_releases WHERE owner=?',(self.owner,)).fetchone()['payload']
            db.execute('INSERT INTO engineering_case_retirements VALUES(?,?,?,?,?)',
                       (self.owner,'fixture','D2','operator retention receipt',0))
        self.assertEqual(([],[],{}),self.app.results.cases.collect(self.owner))
        with self.assertRaisesRegex(ValueError,'RETIRED_BY_RETENTION'):
            self.app.results.file(self.owner,key)
        with self.app.store.connect() as db:
            after=db.execute('SELECT payload FROM engineering_case_releases WHERE owner=?',(self.owner,)).fetchone()['payload']
        self.assertEqual(before,after)

    def test_single_file_read_does_not_recheck_unrelated_artifacts(self):
        from unittest.mock import patch
        m=self.manifest();(self.base/'unrelated.csv').write_bytes(b'fixture only')
        m['groups'][0]['files'].append(dict(path='unrelated.csv',sha256=hashlib.sha256(b'fixture only').hexdigest()))
        self.app.results.cases.publish(self.owner,self.base,m)
        rows,files,paths=self.app.results.cases.collect(self.owner)
        target=next(f for f in files if f['name']=='motion.mp4')
        unrelated=next(f for f in files if f['name']=='unrelated.csv')
        paths[unrelated['id']].write_bytes(b'corrupt unrelated file')
        with patch.object(self.app.results.cases,'collect',side_effect=AssertionError('full catalogue reread')):
            with patch.object(self.app.results,'_integrity',wraps=self.app.results._integrity) as checked:
                path,name=self.app.results.file(self.owner,target['id'])
                self.assertEqual(b'fixture-not-real-video',path.read_bytes());self.assertEqual('motion.mp4',name)
                self.assertEqual(1,checked.call_count)
            with self.assertRaisesRegex(ValueError,'RESULT_FILE_INVALID'):
                self.app.results.file(self.owner,unrelated['id'])
            with self.assertRaises(PermissionError):
                self.app.results.file(self.owner,target['id']+'/../unrelated.csv')

    def test_verified_restore_requires_explicit_owner_and_preserves_claim_boundary(self):
        from scripts.door_case.restore_publication import restore
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m)
        other=self.app.conversations.create('other',None,'case-restore')['id']
        restored=restore(self.app.results,self.owner,other,'fixture','D2')
        self.assertEqual(1,restored['files']);self.assertTrue(restored['integrity'])
        r=next(r for r in self.app.results.inspect(other)['results'] if r['source_type']=='engineering-case')
        self.assertFalse(r['autonomous_agent_verified']);self.assertFalse(r['hardware_verified'])
        self.assertEqual('case',r['applicability']['state'])

    def test_corrupt_restore_does_not_publish_to_another_task(self):
        from scripts.door_case.restore_publication import restore
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m)
        other=self.app.conversations.create('other',None,'case-corrupt')['id']
        _,files,paths=self.app.results.cases.collect(self.owner)
        paths[files[0]['id']].write_bytes(b'corrupt archive')
        with self.assertRaisesRegex(ValueError,'ARCHIVE_CORRUPT'):
            restore(self.app.results,self.owner,other,'fixture','D2')
        self.assertEqual([],self.app.results.cases.collect(other)[0])

    def test_local_archive_migration_preserves_legacy_ids_and_fails_on_corruption(self):
        from bfworld.agentlab.engineering_cases import EngineeringCases
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m)
        _,files,paths=self.app.results.cases.collect(self.owner)
        key=files[0]['id'];legacy=paths[key]
        local=self.root/'local-content'
        (self.app.results.store.root/'engineering-case-storage.json').write_text(json.dumps({
            'schema_version':'bf-engineering-case-storage-v1','root':str(local)}))
        self.app.results.cases=EngineeringCases(self.app.results)
        self.assertEqual(legacy,self.app.results.file(self.owner,key)[0])
        self.app.results.cases.publish(self.owner,self.base,m)
        current=self.app.results.file(self.owner,key)[0]
        self.assertTrue(current.is_relative_to(local.resolve()));self.assertTrue(legacy.exists())
        self.assertEqual(legacy.read_bytes(),current.read_bytes())
        current.write_bytes(b'corrupt local file')
        with self.assertRaisesRegex(ValueError,'RESULT_FILE_INVALID'):
            self.app.results.file(self.owner,key)
        self.assertEqual(b'fixture-not-real-video',legacy.read_bytes())
        other=self.app.conversations.create('other',None,'local-case-other')['id']
        with self.assertRaises(PermissionError):self.app.results.file(other,key)

    def test_local_archive_restore_can_read_unmigrated_legacy_files(self):
        from bfworld.agentlab.engineering_cases import EngineeringCases
        from scripts.door_case.restore_publication import restore
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m)
        local=self.root/'local-content'
        (self.app.results.store.root/'engineering-case-storage.json').write_text(json.dumps({
            'schema_version':'bf-engineering-case-storage-v1','root':str(local)}))
        self.app.results.cases=EngineeringCases(self.app.results)
        other=self.app.conversations.create('restored',None,'local-restored')['id']
        value=restore(self.app.results,self.owner,other,'fixture','D2')
        self.assertTrue(value['integrity'])
        _,files,paths=self.app.results.cases.collect(other)
        self.assertTrue(paths[files[0]['id']].is_relative_to(local.resolve()))
        self.assertFalse(value['autonomous_agent_verified'])

    def test_archive_configuration_requires_explicit_absolute_root(self):
        from bfworld.agentlab.engineering_cases import EngineeringCases
        (self.app.results.store.root/'engineering-case-storage.json').write_text(json.dumps({
            'schema_version':'bf-engineering-case-storage-v1','root':'relative-folder'}))
        with self.assertRaisesRegex(ValueError,'CASE_STORAGE_CONFIG_INVALID'):
            EngineeringCases(self.app.results)

    def test_archive_recovery_requires_exact_bytes_and_never_extracts_member_paths(self):
        import zipfile
        from scripts.door_case.recover_case_storage import recover
        from bfworld.agentlab.engineering_cases import EngineeringCases
        m=self.manifest();self.app.results.cases.publish(self.owner,self.base,m)
        _,files,paths=self.app.results.cases.collect(self.owner)
        key=files[0]['id'];paths[key].unlink()
        bad=self.root/'bad.zip';good=self.root/'good.zip'
        with zipfile.ZipFile(bad,'w') as z:z.writestr('motion.mp4',b'wrong-but-same-size!!!!')
        with zipfile.ZipFile(good,'w') as z:z.writestr('../../motion.mp4',b'fixture-not-real-video')
        target=self.root/'archive';receipt=self.root/'recovery.json'
        with self.assertRaisesRegex(ValueError,'INCOMPLETE_RECOVERY_NOT_ACTIVATED'):
            recover(self.app.results.store.root,self.owner,'fixture','D2',target,[bad],receipt,True)
        self.assertFalse((self.app.results.store.root/'engineering-case-storage.json').exists())
        value=recover(self.app.results.store.root,self.owner,'fixture','D2',target,[bad,good],receipt,True)
        self.assertTrue(value['passed']);self.assertEqual(1,value['files'])
        self.app.results.cases=EngineeringCases(self.app.results)
        path,_=self.app.results.file(self.owner,key)
        self.assertEqual(b'fixture-not-real-video',path.read_bytes())
        self.assertTrue(path.is_relative_to(target.resolve()))
        self.assertFalse((self.root/'motion.mp4').exists())

    def panel_manifest(self):
        m=self.manifest();m['groups']=[]
        for order in range(1,7):
            folder=self.base/str(order);folder.mkdir(exist_ok=True)
            source=dict(id='trace',path='trace.csv',sha256=hashlib.sha256(b'time_s,v\n0,0\n').hexdigest(),columns={'time_s':'s','v':'V'},origin='fixture',scope='fixture only')
            source_identity=hashlib.sha256(json.dumps([source],sort_keys=True).encode()).hexdigest()
            p=dict(id=str(order)+'a',label='a',title='Fixture panel',question='What is preserved?',caption='Fixture metadata, not a real simulation.',evidence_kind='gap',status='missing',reason='No hardware evidence',source_identity=source_identity)
            files=[]
            for name,data in {'plot.png':b'fixture image','plot.pdf':b'fixture PDF','plot.svg':b'fixture SVG','trace.csv':b'time_s,v\n0,0\n','provenance.json':json.dumps(p).encode()}.items():
                rel=str(order)+'/'+name;(self.base/rel).write_bytes(data);files.append(dict(path=rel,sha256=hashlib.sha256(data).hexdigest()))
            p.update(figure=f'{order}/plot.png',pdf=f'{order}/plot.pdf',svg=f'{order}/plot.svg',provenance=f'{order}/provenance.json',dependencies=[f'{order}/trace.csv'],source_records=[{**source,'published_path':f'{order}/trace.csv'}])
            story=dict(order=order,baseline_id=m['id'],baseline_version=m['version'],baseline_source_identity=m['design_sha256'],source_identity=source_identity,title='Fixture',question='Question',conclusion='No physical evidence',limitations=['Fixture only'],dependencies=[f'{order}/trace.csv'],figure=f'{order}/plot.png',panels=[p])
            m['groups'].append(dict(id='group-'+str(order),domain='system',title='Fixture',kind='scientific-figure',scope='fixture only',files=files,evidence_story=story))
        return m

    def test_panel_files_and_source_identity_survive_publication_and_restore(self):
        from scripts.door_case.restore_publication import restore
        m=self.panel_manifest();self.app.results.cases.publish(self.owner,self.base,m)
        rows,files,paths=self.app.results.cases.collect(self.owner)
        self.assertEqual(6,len(rows));self.assertEqual(30,len(files))
        p=rows[0]['evidence_story']['panels'][0]
        self.assertEqual('missing',p['status']);self.assertEqual(1,len(p['source_files']))
        self.assertTrue(all(k in paths for k in (p['figure_id'],p['pdf_id'],p['svg_id'],p['provenance_id'],p['source_files'][0])))
        other=self.app.conversations.create('restored panels',None,'panels')['id']
        restore(self.app.results,self.owner,other,m['id'],m['version'])
        restored=self.app.results.cases.collect(other)[0][0]['evidence_story']['panels'][0]
        self.assertEqual(p['source_identity'],restored['source_identity']);self.assertEqual('missing',restored['status'])
        paths[p['source_files'][0]].write_bytes(b'corrupt data')
        with self.assertRaisesRegex(ValueError,'INVALID'):self.app.results.file(self.owner,p['source_files'][0])

    def test_panel_forgery_unbound_sources_and_duplicate_ids_are_rejected(self):
        m=self.panel_manifest();p=m['groups'][0]['evidence_story']['panels'][0];p['caption']='A false success claim'
        with self.assertRaisesRegex(ValueError,'PROVENANCE_MISMATCH'):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.panel_manifest();p=m['groups'][0]['evidence_story']['panels'][0];p['source_records'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SOURCE_BINDING'):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.panel_manifest();m['groups'][0]['evidence_story']['panels'][0]['source_records'][0]['scope']='forged metadata'
        with self.assertRaisesRegex(ValueError,'SOURCE_IDENTITY'):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.panel_manifest();m['groups'][0]['evidence_story']['panels']*=2
        with self.assertRaisesRegex(ValueError,'PANEL_INVALID'):self.app.results.cases.publish(self.owner,self.base,m)
        m=self.panel_manifest();m['groups'][0]['evidence_story']['panels'][0]['provenance']='../private.json'
        with self.assertRaisesRegex(ValueError,'PANEL_INVALID'):self.app.results.cases.publish(self.owner,self.base,m)
        self.assertEqual([],self.app.results.cases.collect(self.owner)[0])
