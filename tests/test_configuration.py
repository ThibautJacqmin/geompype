"""YAML compatibility without importing the source drawing frameworks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from geompype.configuration import load_config
from geompype.parameters import evaluate


class TestConfiguration(unittest.TestCase):
    def test_includes_inheritance_variations_and_live_values(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder/'base.yaml').write_text('width: 200nm\ncount: 3\n',encoding='utf-8')
            (folder/'chip.yaml').write_text('gap: 2um\nsample_holder__n: demo_holder\nfrequency: 20GHz\narray: base.yaml\narray__0: {count: 7}\narray__1: {width: 0.3um}\nchild: {pos: [1mm, 0]}\n',encoding='utf-8')
            config = load_config(folder/'chip.yaml',name='chip')
            self.assertEqual(config['sample_holder__n'],'demo_holder')
            self.assertEqual(config['frequency'],'20GHz')
            self.assertIs(config.child('child')['gap'],config['gap'])
            a,b = config.variations('array')
            self.assertEqual(a['count'],7)
            self.assertAlmostEqual(evaluate(a['width'],'um'),.2)
            self.assertAlmostEqual(evaluate(b['width'],'um'),.3)
            a['width'].value = 500
            self.assertAlmostEqual(evaluate(b['width'],'um'),.3)
            self.assertEqual(config.raw('array')['width'],'200nm')
            self.assertAlmostEqual(evaluate(config.child('child')['pos'][0],'um'),1000)

    def test_override_and_cycle_errors(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp)/'chip.yaml'
            file.write_text('a: {width: 1um}\n',encoding='utf-8')
            config = load_config(file,overrides={'a.width':'5um'})
            self.assertEqual(evaluate(config.child('a')['width'],'um'),5)
            self.assertIn('1um',file.read_text())
            file.write_text('a: chip.yaml\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Cyclic'):
                load_config(file)
