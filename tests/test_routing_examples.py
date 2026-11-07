"""Execute the flat routing examples and exercise their parameter references."""
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import klayout.db as kdb
from geompype import Project


class TestRoutingExamples(unittest.TestCase):
    def test_asymmetric_detour_clearance_target_and_failed_export_preservation(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        add = Project.add_layer
        def offline(project, name, **kwargs):
            kwargs['comsol'] = False
            return add(project, name, **kwargs)
        with TemporaryDirectory() as tmp, patch.object(Project, 'add_layer', offline), patch.object(Project, 'show'):
            previous = Path.cwd()
            try:
                os.chdir(tmp)
                state = runpy.run_path(str(root/'example_routing_constraints.py'))
                project, detour = state['project'], state['detour']
                self.assertEqual(detour.report()['taper_length_um'], 0)
                # Independent endpoint slices protect widths AND signed offsets.
                expected = {'lower': kdb.Box(0, -15000, 10000, -9000),
                            'upper': kdb.Box(0, 20000, 10000, 30000)}
                obstacle = kdb.Region(state['obstacle'].to_klayout().to_itype(project.dbu))
                clip = kdb.Region(kdb.Box(0, -100000, 10000, 100000))
                for name, feature in detour.geometry.items():
                    footprint = kdb.Region(feature.to_klayout().to_itype(project.dbu))
                    self.assertTrue(((footprint & clip) ^ kdb.Region(expected[name])).is_empty())
                    self.assertTrue((footprint.sized(25000) & obstacle).is_empty())
                self.assertAlmostEqual(state['resonator'].length, 2000, places=7)
                self.assertEqual(state['resonator'].report()['meander_count'], 6)
                state['target_length'].value = 2400
                state['detour_height'].value = 300
                project.build()
                self.assertAlmostEqual(state['resonator'].length, 2400, places=7)
                self.assertEqual(state['resonator'].report()['meander_count'], 8)
                self.assertEqual(tuple(detour.route.points.value[2]), (200, 300))
                before = project.gds_path.read_bytes()
                state['obstacle_x'].value = 200
                with self.assertRaisesRegex(ValueError, 'intersects obstacle'):
                    project.build()
                self.assertEqual(project.gds_path.read_bytes(), before)
                state['obstacle_x'].value = 500
                project.build()
            finally:
                os.chdir(previous)

    def test_flat_examples(self):
        root=Path(__file__).resolve().parents[1] / 'examples'
        add=Project.add_layer
        def offline(project,name,**kwargs):
            kwargs['comsol']=False
            return add(project,name,**kwargs)
        with TemporaryDirectory() as tmp,patch.object(Project,'add_layer',offline),patch.object(Project,'show'):
            previous=Path.cwd()
            try:
                os.chdir(tmp)
                state=runpy.run_path(str(root/'example_routing.py'))
                state['config']['track'].value=25
                state['project'].build()
                self.assertTrue(state['project'].gds_path.exists())
                utilities=runpy.run_path(str(root/'example_routing_utilities.py'))
                self.assertEqual(utilities['resonator'].report()['meander_count'],6)
                utilities['target'].value=2400
                utilities['project'].build()
                self.assertEqual(utilities['resonator'].report()['meander_count'],8)
                self.assertTrue(utilities['project'].gds_path.exists())
            finally:
                os.chdir(previous)
