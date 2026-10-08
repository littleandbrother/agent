import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from tests.agentlab.test_engineering_cases import EngineeringCasesTest
from scripts.door_case.build_evidence_dossier import dependencies_for, source_identity, verify_inputs

class EvidencePublicationTest(EngineeringCasesTest):
    def dossier(self):
        m=self.manifest();groups=[]
        for i in range(1,7):
            g=copy.deepcopy(m['groups'][0]);g['id']='figure-'+str(i)
            g['evidence_story']=dict(order=i,title='Test question',question='What does it establish?',conclusion='Not qualified',limitations=['fixture'],dependencies=[],figure='motion.mp4',source_identity='b'*64,baseline_id=m['id'],baseline_version=m['version'],baseline_source_identity=m['design_sha256'])
            groups.append(g)
        m['groups']=groups;return m

    def test_six_groups_are_bound_to_real_owner_files(self):
        m=self.dossier();self.app.results.cases.publish(self.owner,self.base,m)
        rows,files,_=self.app.results.cases.collect(self.owner)
        self.assertEqual(list(range(1,7)),[r['evidence_story']['order'] for r in rows])
        self.assertTrue(all(r['evidence_story']['file_id'] in [f['id'] for f in r['files']] for r in rows))
        self.assertTrue(all(not r['hardware_verified'] for r in rows))

    def test_wrong_identity_missing_sequence_or_unbound_figure_rejected(self):
        for kind in ['identity','sequence','figure']:
            m=self.dossier()
            if kind=='identity':m['groups'][0]['evidence_story']['baseline_source_identity']='c'*64
            elif kind=='sequence':m['groups'].pop()
            else:m['groups'][0]['evidence_story']['figure']='unregistered.png'
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'EVIDENCE'):
                self.app.results.cases.publish(self.owner,self.base,m)

class DossierDependencyTest(unittest.TestCase):
    def test_numeric_source_change_invalidates_affected_figures_only(self):
        paths=['engineering/mechanical-D2/design.json','review/orientation-v3/joint/energy.json','review/orientation-v3/joint/waveform.csv','review/orientation-v3/candidate.json']
        records=[dict(path=p,sha256='a'*64,bytes=5) for p in paths]
        before=[source_identity(dependencies_for(i,records)) for i in range(1,7)]
        changed=copy.deepcopy(records);changed[1]['sha256']='b'*64
        after=[source_identity(dependencies_for(i,changed)) for i in range(1,7)]
        self.assertEqual([4,5,6],[i+1 for i,(a,b) in enumerate(zip(before,after)) if a!=b])

    def test_corrupt_or_missing_source_stops_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'source.txt').write_text('sealed')
            (p/'source-index.json').write_text(json.dumps({'files':[dict(path='source.txt',sha256=hashlib.sha256(b'sealed').hexdigest())]}))
            verify_inputs(p);(p/'source.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):verify_inputs(p)
            (p/'source.txt').unlink()
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):verify_inputs(p)

if __name__=='__main__':unittest.main()
