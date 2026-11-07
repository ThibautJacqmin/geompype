"""Native asymmetric routing gallery, live constraints and saved selections."""

import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from geompype import Project
from comsol_support import get_client
from test_comsol_curves import selected_measure


@unittest.skipUnless(os.environ.get('GEOMPYPE_TEST_COMSOL') == '1', 'Native COMSOL opt-in')
class TestComsolRoutingExamples(unittest.TestCase):
    def test_asymmetric_constraints_example_native_and_saved_rebuild(self):
        client = get_client()
        root = Path(__file__).resolve().parents[1] / 'examples'
        created = []
        original = Project.__init__
        with TemporaryDirectory() as folder:
            def initialise(project, **kwargs):
                kwargs['client'] = client
                kwargs['output'] = Path(folder)/'constraints'
                original(project, **kwargs)
                created.append(project)
            try:
                with patch.object(Project, '__init__', initialise), patch.object(Project, 'show'):
                    state = runpy.run_path(str(root/'example_routing_constraints.py'))
                project = state['project']
                self.assertEqual(len(state['detour_selection'].entities()), 2)
                self.assertTrue(state['resonator_selection'].entities())
                for layer, width, y_bounds in ((state['lower_layer'], 6, (-15, 241)),
                                             (state['upper_layer'], 10, (20, 280))):
                    measure = selected_measure(project.model, layer.selection)
                    self.assertAlmostEqual(measure.getArea(), width*state['detour'].length,
                                           delta=.002*width*state['detour'].length)
                    bounds = list(measure.getBoundingBox())
                    for actual, expected in zip(bounds[:4], (0, 1000, *y_bounds)):
                        self.assertAlmostEqual(actual, expected, delta=.001)
                state['target_length'].value = 2400
                state['upper_width'].value = 12
                project.build()
                self.assertEqual(state['resonator'].report()['meander_count'], 8)
                self.assertAlmostEqual(state['resonator'].length, 2400, places=7)
                self.assertEqual(len(state['detour_selection'].entities()), 2)
                saved = client.load(str(project.mph_path))
                try:
                    area = selected_measure(saved, state['upper_layer'].selection).getArea()
                    self.assertAlmostEqual(area, 12*state['detour'].length,
                                           delta=.002*12*state['detour'].length)
                finally:
                    client.remove(saved)
                before_gds, before_mph = project.gds_path.read_bytes(), project.mph_path.read_bytes()
                state['obstacle_x'].value = 200
                with self.assertRaisesRegex(ValueError, 'intersects obstacle'):
                    project.build()
                self.assertEqual(project.gds_path.read_bytes(), before_gds)
                self.assertEqual(project.mph_path.read_bytes(), before_mph)
            finally:
                for project in created:
                    if project.model is not None:
                        client.remove(project.model)
