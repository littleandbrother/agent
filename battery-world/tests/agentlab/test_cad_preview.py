import contextlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from bfworld.agentlab.engineering_projects import CAD_READBACK_SOURCE


class CADPreviewBoundaryTests(unittest.TestCase):
    def execute(self, triangle_counts=(200001, 12), valid=True, mutate=False):
        imports=[];meshes=[]
        class Shape:
            def Solids(self):return [self]
            def isValid(self):return valid
            def Volume(self):return 24.
            def BoundingBox(self):return types.SimpleNamespace(xlen=2.,ylen=3.,zlen=4.)
            def tessellate(self,linear,angular):
                meshes.append((linear,angular))
                count=triangle_counts[min(len(meshes)-1,len(triangle_counts)-1)]
                if mutate:Path('assembly.step').write_bytes(b'changed during mesh')
                points=[types.SimpleNamespace(x=x,y=0.,z=0.) for x in (0.,1.,2.)]
                return points,[(0,1,2)]*count
        def load(name):imports.append(name);return types.SimpleNamespace(val=lambda:Shape())
        module=types.SimpleNamespace(importers=types.SimpleNamespace(importStep=load))
        with tempfile.TemporaryDirectory() as folder,contextlib.chdir(folder),patch.dict(sys.modules,{'cadquery':module}):
            Path('assembly.step').write_bytes(b'immutable STEP fixture')
            exec(CAD_READBACK_SOURCE,{})
            return json.loads(Path('readback.json').read_text()),imports,meshes,Path('preview-mesh.json').exists()

    def test_each_coarser_attempt_reimports_same_native_geometry(self):
        report,imports,meshes,available=self.execute()
        self.assertEqual(3,len(imports));self.assertEqual([(0.15,0.1),(0.3,0.2)],meshes)
        self.assertTrue(available);self.assertTrue(report['native_valid'])
        self.assertEqual([2.,3.,4.],report['bounds_mm']);self.assertEqual(24.,report['volume_mm3'])
        self.assertEqual(12,report['preview']['triangles'])
        self.assertEqual(report['native_source_sha256'],report['preview']['source_sha256'])
    def test_unavailable_preview_does_not_deform_or_reject_valid_step(self):
        report,imports,meshes,available=self.execute((200001,))
        self.assertFalse(available);self.assertFalse(report['preview']['available'])
        self.assertTrue(report['native_valid']);self.assertEqual(4,len(meshes))
    def test_invalid_native_geometry_cannot_be_promoted_by_mesh(self):
        with self.assertRaises(AssertionError):self.execute(valid=False)
    def test_input_change_during_preview_stops_native_acceptance(self):
        with self.assertRaises(AssertionError):self.execute((12,),mutate=True)

if __name__=='__main__':unittest.main()
