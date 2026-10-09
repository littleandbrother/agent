import math,struct,tempfile,unittest
from pathlib import Path
from bfworld.agentlab.engineering_projects import raw_readback

def plot(values,*,binary=False,complex_values=False,title='Storage stage Build',name='Transient Analysis'):
    n=len(values[0]);count=len(values)
    head=(f'Title: {title}\nDate: preserved\nCommand: ngspice-46, Build\nPlotname: {name}\n'
          f'Flags: {"complex" if complex_values else "real"}\nNo. Variables: {n}\nNo. Points: {count}\nVariables:\n'
          + ''.join(f'\t{i}\t{"time" if i==0 else "v(storage)"}\t{"time" if i==0 else "voltage"}\n' for i in range(n)))
    if binary:
        flat=[v for row in values for x in row for v in (x if complex_values else (x,))]
        return (head+'Binary:\n').encode()+struct.pack('='+str(len(flat))+'d',*flat)
    text=''
    for i,row in enumerate(values):
        for j,x in enumerate(row):
            text+=(str(i)+'\t\t' if j==0 else '\t')+(','.join(map(str,x)) if complex_values else str(x))+'\n'
    return (head+'Values:\n'+text).encode()

class SpiceReadbackTests(unittest.TestCase):
    def read(self,data):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'trace.raw';p.write_bytes(data);return raw_readback(p)
    def test_ascii_real(self):
        result=self.read(plot([[0,1],[1,2]]));self.assertEqual(2,result['points']);self.assertTrue(result['finite_values'])
    def test_binary_real(self):self.assertEqual('binary',self.read(plot([[0,1],[1,2]],binary=True))['plots'][0]['encoding'])
    def test_ascii_complex(self):self.assertTrue(self.read(plot([[(1,0),(2,-3)]],complex_values=True))['plots'][0]['complex'])
    def test_binary_complex(self):self.assertTrue(self.read(plot([[(1,0),(2,-3)]],binary=True,complex_values=True))['plots'][0]['complex'])
    def test_multiple_ascii_plots_have_independent_counts(self):
        result=self.read(plot([[4]],name='Operating Point')+plot([[0,4],[1,5]]))
        self.assertEqual([1,2],[x['points'] for x in result['plots']]);self.assertEqual(2,result['variables'])
    def test_multiple_binary_plots(self):self.assertEqual(2,len(self.read(plot([[4]],binary=True)+plot([[0,4],[1,5]],binary=True))['plots']))
    def test_mixed_encoding_is_bounded_per_plot(self):self.assertEqual(2,len(self.read(plot([[4]])+plot([[0,4]],binary=True))['plots']))
    def test_unicode_title_is_metadata(self):self.assertEqual(1,self.read(plot([[0,4]],title='储能与负载门控 stage'))['points'])
    def test_crlf_headers_and_ascii_body(self):self.assertEqual(1,self.read(plot([[0,4]]).replace(b'\n',b'\r\n'))['points'])
    def test_truncated_last_plot_cannot_hide_behind_first_success(self):
        with self.assertRaises(ValueError):self.read(plot([[4]])+plot([[0,4],[1,5]])[:-5])
    def test_binary_truncation_rejected(self):
        with self.assertRaises(ValueError):self.read(plot([[0,4]],binary=True)[:-1])
    def test_nonfinite_ascii_rejected(self):
        with self.assertRaises(ValueError):self.read(plot([[0,math.nan]]))
    def test_nonfinite_binary_rejected(self):
        with self.assertRaises(ValueError):self.read(plot([[0,math.inf]],binary=True))
    def test_metadata_in_sample_position_rejected(self):
        with self.assertRaises(ValueError):self.read(plot([[0,4]]).replace(b'\t4\n',b'\tBuild\n'))
    def test_extra_trailing_data_rejected(self):
        with self.assertRaises(ValueError):self.read(plot([[0,4]])+b'999\n')
    def test_wrong_point_index_rejected(self):
        with self.assertRaisesRegex(ValueError,'POINT_INDEX'):self.read(plot([[0,4],[1,5]]).replace(b'1\t\t1\n',b'8\t\t1\n'))
    def test_variable_inventory_must_match(self):
        with self.assertRaises(ValueError):self.read(plot([[0,4]]).replace(b'\t1\tv(storage)',b'\t7\tv(storage)'))
    def test_incomplete_header_rejected(self):
        with self.assertRaises(ValueError):self.read(b'Title: good\nPlotname: Operating Point\n')
    def test_contradictory_numeric_flags_rejected(self):
        with self.assertRaises(ValueError):self.read(plot([[0,4]]).replace(b'Flags: real',b'Flags: real complex'))

if __name__=='__main__':unittest.main()
