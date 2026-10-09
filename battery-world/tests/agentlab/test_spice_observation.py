import tempfile,unittest
from pathlib import Path
from tests.agentlab.test_spice_readback import plot
from bfworld.agentlab.spice_observation import observe

class NumericObservationTests(unittest.TestCase):
    def read(self,data):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'trace.raw';p.write_bytes(data);return observe(p)
    def test_ascii_transient_values_not_metadata(self):
        q=self.read(plot([[0,4],[1,-2],[2,3]],title='储能 Build'))
        c=q['plots'][0]['channels'][1]
        self.assertEqual((-2,4,4,3),(c['minimum'],c['maximum'],c['first'],c['last']))
        self.assertEqual(0,q['solver_runs_added'])
    def test_multiplot_binary_separates_operating_point(self):
        q=self.read(plot([[7]],binary=True,name='Operating Point')+plot([[0,4],[1,6]],binary=True))
        self.assertEqual(7,q['plots'][0]['channels'][0]['last'])
        self.assertEqual(6,q['plots'][1]['channels'][1]['last'])
    def test_complex_components_do_not_masquerade_as_real(self):
        q=self.read(plot([[(1,0),(2,-3)],[(2,0),(-4,5)]],complex_values=True,binary=True))
        c=q['plots'][0]['channels'];self.assertEqual(-4,c[2]['minimum']);self.assertEqual(-3,c[3]['minimum']);self.assertEqual('imaginary',c[3]['component'])
    def test_bad_last_plot_cannot_produce_numeric_facts(self):
        with self.assertRaises(ValueError):self.read(plot([[7]])+plot([[0,4]],binary=True)[:-1])

if __name__=='__main__':unittest.main()
