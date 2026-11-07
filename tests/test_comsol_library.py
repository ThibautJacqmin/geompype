"""Native library contours, placement expressions and saved selections."""

import os
from math import fsum, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from comsol_support import get_client
from geompype import Parameter, Project
from geompype.library import x_diamond_mark, two_inch_wafer
from test_comsol_curves import selected_measure
from test_library import asset


def asset_area(name):
    """Independent shoelace area from the frozen polygon coordinates in um."""
    from math import fsum
    area = 0
    for points in asset(name)['polygons'].values():
        terms = [a[0]*b[1] - b[0]*a[1] for a, b in zip(points, points[1:] + points[:1])]
        area += abs(fsum(terms))/2
    return area


@unittest.skipUnless(os.environ.get('GEOMPYPE_TEST_COMSOL') == '1',
                     'Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.')
class TestComsolLibrary(unittest.TestCase):
    def setUp(self):
        self.client = get_client()
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(client=self.client, output=Path(self.folder.name)/'library')
        self.addCleanup(self.clean_model)

    def clean_model(self):
        if self.project.model is not None:
            self.client.remove(self.project.model)

    def assert_bounds(self, model, group, expected):
        # These test models contain only one library asset. Read its actual
        # final geometric vertices: measureFinal().getBoundingBox() uses a
        # float32 display box, whose wafer-scale rounding can exceed 1 nm.
        # Selection membership is checked separately in each test.
        coordinates = model.java.component('comp1').geom('geom1').getVertexCoord()
        actual = tuple(value for row in coordinates for value in (min(row), max(row)))
        self.assertEqual(len(actual), 6)
        for value, target in zip(actual, expected):
            self.assertAlmostEqual(value, target, delta=1e-8)

    def assert_area(self, model, group, expected):
        # Match the existing native transform tests' 1 ppm tolerance for
        # measureFinal().getArea(). Vertex coordinates and defining Polygon
        # expressions are checked separately, at their full precision.
        self.assertAlmostEqual(selected_measure(model, group).getArea(), expected,
                               delta=max(1e-5, expected*1e-6))

    def assert_wafer_vertices(self, model, expected):
        # Six decimal places only select the candidate; the actual assertion
        # below remains 1e-8 um. Repair
        # may remove collinear samples, but must not move surviving vertices.
        by_position = {(round(x, 6), round(y, 6)): (x, y) for x, y in expected}
        coordinates = model.java.component('comp1').geom('geom1').getVertexCoord()
        self.assertGreaterEqual(len(coordinates[0]), 4)
        for x, y, z in zip(*coordinates):
            key = (round(x, 6), round(y, 6))
            self.assertIn(key, by_position)
            px, py = by_position[key]
            self.assertAlmostEqual(x, px, delta=1e-8)
            self.assertAlmostEqual(y, py, delta=1e-8)
            self.assertAlmostEqual(z, 0, delta=1e-8)

    def test_mark_transform_parameters_and_selections_on_upper_workplane(self):
        project = self.project
        upper = project.add_workplane('upper', position=(7, 11, 4))
        layer = project.add_layer('marks', workplane=upper, gds=False)
        selected = project.add_selection('alignment')
        scale = Parameter(2, 'mark_scale')
        angle = Parameter(90, 'mark_angle', unit='deg')
        shift = Parameter(200, 'mark_x', unit='um')
        mark = x_diamond_mark(project, layer=layer, selections=(selected,))
        rotated = mark.scale(factor=scale).rotate(angle=angle)
        rotated.move(delta=(shift, 300))
        project.build()
        self.assertEqual(len(selected.entities()), 5)
        self.assertEqual(set(selected.entities()), set(layer.selection.entities()))
        self.assert_bounds(project.model, selected, (31.908, 382.092, 135.908, 486.092, 4, 4))
        self.assert_area(project.model, selected, 4*asset_area('x_diamond_mark'))
        feature = upper.native.geom().feature(rotated.tag)
        self.assertIn('mark_angle', str(feature.getString('rot')))

        shift.value = 500
        project.build()
        self.assert_bounds(project.model, selected, (331.908, 682.092, 135.908, 486.092, 4, 4))
        project.model.java.param().set('mark_scale', '3')
        project.geometry.run()
        self.assert_bounds(project.model, selected, (244.362, 769.638, 48.362, 573.638, 4, 4))
        self.assert_area(project.model, selected, 9*asset_area('x_diamond_mark'))

    def test_wafer_native_contour_and_saved_selection(self):
        project = self.project
        layer = project.add_layer('wafer', gds=False)
        selected = project.add_selection('outline')
        wafer = two_inch_wafer(project, layer=layer, selections=(selected,))
        project.build()
        expected = (-25400, 25400, -25400, sqrt(25400**2-7940**2), 0, 0)
        self.assertEqual(len(selected.entities()), 1)
        self.assert_bounds(project.model, selected, expected)
        feature = project.workplane.geom().feature(wafer.tag)
        self.assertEqual(str(feature.getType()), 'Polygon')
        # Also verify every defining coordinate, including collinear vertices
        # COMSOL may remove from the final topology during geometry repair.
        expected_x = wafer.vertices.comsol_string_x()
        expected_y = wafer.vertices.comsol_string_y()
        self.assertEqual(list(feature.getStringArray('x')), expected_x)
        self.assertEqual(list(feature.getStringArray('y')), expected_y)
        points = wafer.vertices.value
        self.assert_wafer_vertices(project.model, points)
        expected_area = abs(fsum(a[0]*b[1]-b[0]*a[1]
                                for a,b in zip(points, points[1:]+points[:1])))/2
        self.assert_area(project.model, selected, expected_area)
        saved = self.client.load(str(project.mph_path))
        try:
            self.assert_bounds(saved, layer.selection, expected)
            self.assert_area(saved, selected, expected_area)
            self.assert_wafer_vertices(saved, points)
            saved_feature = saved.java.component('comp1').geom('geom1').feature('wp1').geom().feature(wafer.tag)
            self.assertEqual(list(saved_feature.getStringArray('x')), expected_x)
            self.assertEqual(list(saved_feature.getStringArray('y')), expected_y)
        finally:
            self.client.remove(saved)

