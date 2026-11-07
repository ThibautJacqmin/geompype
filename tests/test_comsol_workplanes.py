"""Native placement, parameter-only rebuilds and selections across workplanes."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from comsol_support import get_client
from geompype import Parameter, Project, Rectangle
from test_comsol_curves import selected_measure


@unittest.skipUnless(os.environ.get('GEOMPYPE_TEST_COMSOL') == '1',
                     'Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.')
class TestComsolWorkplanes(unittest.TestCase):
    def setUp(self):
        self.client = get_client()
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.projects = []
        self.addCleanup(self.clean_models)

    def clean_models(self):
        for project in self.projects:
            if project.model is not None:
                self.client.remove(project.model)

    def project(self, *, live=False):
        project = Project(client=self.client, live=live,
                          output=Path(self.folder.name)/str(len(self.projects)))
        self.projects.append(project)
        return project

    def assert_bounds(self, model, group, expected):
        actual = selected_measure(model, group).getBoundingBox()
        self.assertEqual(len(actual), 6)
        for value, target in zip(actual, expected):
            self.assertAlmostEqual(value, target, delta=1e-6)

    def test_native_gap_rotation_and_parameter_only_rebuild(self):
        project = self.project()
        gap = Parameter(500, 'vacuum_gap', unit='nm')
        angle = Parameter(90, 'upper_angle', unit='deg')
        upper = project.add_workplane('membrane', position=(10, 20, gap), angle=angle)
        lower_layer = project.add_layer('fluxonium', gds=False)
        upper_layer = project.add_layer('membrane', workplane=upper, gds=False)
        together = project.add_selection('both_electrodes')
        Rectangle(project, layer=lower_layer, size=(4, 2), selections=(together,))
        Rectangle(project, layer=upper_layer, size=(4, 2), selections=(together,))
        project.build()
        self.assertEqual(str(project.workplane.tag()), project.default_workplane.tag)
        self.assertEqual(str(upper.native.tag()), upper.tag)
        self.assertIn('vacuum_gap', str(upper.native.getString('quickz')))
        self.assertIn('upper_angle', str(upper.native.getString('rot')))
        self.assert_bounds(project.model, lower_layer.selection, (-2, 2, -1, 1, 0, 0))
        self.assert_bounds(project.model, upper_layer.selection, (9, 11, 18, 22, .5, .5))
        self.assertAlmostEqual(selected_measure(project.model, together).getArea(), 16, delta=1e-6)
        self.assertEqual(len(together.entities()), 2)

        gap.value = 750
        project.build()
        self.assert_bounds(project.model, upper_layer.selection, (9, 11, 18, 22, .75, .75))
        # Changing the native gap and rebuilding COMSOL geometry must suffice;
        # no Python geometry regeneration should be needed for plane movement.
        project.model.java.param().set('vacuum_gap', '2[um]')
        project.geometry.run()
        self.assert_bounds(project.model, upper_layer.selection, (9, 11, 18, 22, 2, 2))
        self.assert_bounds(project.model, lower_layer.selection, (-2, 2, -1, 1, 0, 0))
        self.assertAlmostEqual(selected_measure(project.model, together).getArea(), 16, delta=1e-6)

    def test_live_added_plane_and_same_plane_layer_operations(self):
        project = self.project(live=True)
        lower = project.add_layer('lower', gds=False)
        Rectangle(project, layer=lower, size=(4, 4))
        gap = Parameter(1, 'live_gap', unit='um')
        upper = project.add_workplane('upper', position=(0, 0, gap))
        source = project.add_layer('upper_source', workplane=upper, gds=False)
        mask = project.add_layer('upper_mask', workplane=upper, gds=False)
        output = project.add_layer('upper_result', workplane=upper, gds=False)
        Rectangle(project, layer=source, size=(4, 4))
        Rectangle(project, layer=mask, size=(2, 2))
        project.subtract_layers(source, mask, output=output)
        self.assertEqual(source.selection.entities(), [])
        self.assertEqual(mask.selection.entities(), [])
        self.assertAlmostEqual(selected_measure(project.model, output.selection).getArea(), 12, delta=1e-6)
        self.assert_bounds(project.model, output.selection, (-2, 2, -2, 2, 1, 1))
        self.assertAlmostEqual(selected_measure(project.model, lower.selection).getArea(), 16, delta=1e-6)
        Rectangle(project, layer=source, size=(2, 2), position=(10, 0))
        self.assertAlmostEqual(selected_measure(project.model, source.selection).getArea(), 4, delta=1e-6)
        gap.value = 3
        project.build()
        self.assert_bounds(project.model, output.selection, (-2, 2, -2, 2, 3, 3))
        self.assert_bounds(project.model, source.selection, (9, 11, -1, 1, 3, 3))
        planes = [str(tag) for tag in project.geometry.feature().tags()
                  if str(project.geometry.feature(tag).getType()) == 'WorkPlane']
        self.assertEqual(planes, ['wp1', upper.tag])

    def test_saved_model_retains_plane_specific_and_combined_selections(self):
        project = self.project()
        upper = project.add_workplane('upper', position=(0, 0, 2))
        lower_layer = project.add_layer('lower', gds=False)
        upper_layer = project.add_layer('upper', workplane=upper, gds=False)
        group = project.add_selection('stack')
        Rectangle(project, layer=lower_layer, size=(4, 2), selections=(group,))
        Rectangle(project, layer=upper_layer, size=(2, 2), selections=(group,))
        project.build()
        saved = self.client.load(str(project.mph_path))
        try:
            self.assert_bounds(saved, lower_layer.selection, (-2, 2, -1, 1, 0, 0))
            self.assert_bounds(saved, upper_layer.selection, (-1, 1, -1, 1, 2, 2))
            self.assertAlmostEqual(selected_measure(saved, group).getArea(), 12, delta=1e-6)
        finally:
            self.client.remove(saved)

    def test_geometry_only_on_upper_plane_with_empty_default_layer(self):
        project = self.project()
        empty = project.add_layer('empty_default', gds=False)
        upper = project.add_workplane('upper', position=(3, 4, 2))
        upper_layer = project.add_layer('upper_metal', workplane=upper, gds=False)
        selected = project.add_selection('upper_only')
        Rectangle(project, layer=upper_layer, size=(4, 2), selections=(selected,))
        project.build()
        self.assertEqual(empty.selection.entities(), [])
        self.assert_bounds(project.model, upper_layer.selection, (1, 5, 3, 5, 2, 2))
        self.assert_bounds(project.model, selected, (1, 5, 3, 5, 2, 2))
        self.assertAlmostEqual(selected_measure(project.model, selected).getArea(), 8, delta=1e-6)
        self.assertEqual(len(selected.entities()), 1)
        self.assertEqual(str(project.workplane.tag()), 'wp1')
        Rectangle(project, layer=empty, size=(2, 2))
        project.build()
        self.assert_bounds(project.model, empty.selection, (-1, 1, -1, 1, 0, 0))
        self.assert_bounds(project.model, upper_layer.selection, (1, 5, 3, 5, 2, 2))

    def test_gds_only_plane_and_placement_parameters_stay_out_of_comsol(self):
        project = self.project()
        native_gap = Parameter(2, 'native_gap', unit='um')
        native = project.add_workplane('native', position=(0, 0, native_gap))
        native_layer = project.add_layer('native_metal', workplane=native, gds=False)
        Rectangle(project, layer=native_layer, size=(4, 2))
        drawing_x = Parameter(50, 'drawing_x', unit='um')
        drawing_gap = Parameter(3, 'drawing_gap', unit='um')
        drawing_angle = Parameter(45, 'drawing_angle', unit='deg')
        drawing = project.add_workplane('fabrication', position=(drawing_x, 0, drawing_gap),
                                         angle=drawing_angle)
        drawing_layer = project.add_layer('fabrication', workplane=drawing, comsol=False)
        Rectangle(project, layer=drawing_layer, size=(10, 10))
        project.build()
        self.assertTrue(drawing.gds_path.exists())
        self.assertIsNone(drawing.native)
        self.assertNotIn(drawing.tag, [str(tag) for tag in project.geometry.feature().tags()])
        parameters = project.model.java.param()
        self.assertAlmostEqual(parameters.evaluate('native_gap'), 2e-6)
        for name in ('drawing_x', 'drawing_gap', 'drawing_angle'):
            with self.subTest(parameter=name), self.assertRaises(Exception):
                parameters.evaluate(name)
        self.assert_bounds(project.model, native_layer.selection, (-2, 2, -1, 1, 2, 2))
