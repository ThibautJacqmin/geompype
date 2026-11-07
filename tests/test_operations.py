"""Analytic footprints, topology, parameters and grid behavior of planar edits."""

from math import pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import (Chamfer, Circle, CircularArc, Difference, Fillet, LineSegment,
                     Offset, Parameter, Point, Polygon, Project, Rectangle, Thicken2D,
                     Union, Vertices)


def region(obj):
    result = obj.to_klayout()
    result = result if isinstance(result, tuple) else (result,)
    merged = kdb.Region()
    for polygon in result:
        merged.insert(polygon.to_itype(obj.project.dbu))
    return merged.merged()


class TestPlanarOperations(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name)/"operations")
        self.layer = self.project.add_layer("metal", comsol=False)

    def rectangle(self, size=(10, 6), **kwargs):
        return Rectangle(self.project, layer=self.layer, size=size, **kwargs)

    def line(self, **kwargs):
        return LineSegment(self.project, layer=self.layer, p1=(0, 0), p2=(10, 0), **kwargs)

    def assert_area(self, obj, area, delta=0.025):
        self.assertAlmostEqual(region(obj).area()*self.project.dbu**2, area, delta=delta)

    def test_fillet_and_chamfer_analytic_areas(self):
        rounded = self.rectangle().fillet(radius=1)
        beveled = self.rectangle(position=(20, 0)).chamfer(distance=1)
        self.assert_area(rounded, 56+pi)
        self.assert_area(beveled, 58, delta=1e-9)
        self.project.build()
        layout = kdb.Layout()
        layout.read(str(self.project.gds_path))
        self.assertEqual(layout.top_cell().shapes(layout.layer(1, 0)).size(), 2)

    def test_chamfer_uses_edge_distance_on_nonright_angles(self):
        triangle = Polygon(self.project, layer=self.layer, vertices=[(0, 0), (10, 0), (0, 10)])
        self.assert_area(Chamfer(triangle, distance=1), 50-(1+sqrt(2))/2, delta=0.005)

    def test_concave_corners(self):
        outline = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
        shape = Polygon(self.project, layer=self.layer, vertices=outline)
        self.assert_area(Fillet(shape, radius=1), 60+pi)
        other = Polygon(self.project, layer=self.layer, vertices=outline)
        self.assert_area(Chamfer(other, distance=1), 62, delta=1e-9)

    def test_holes_survive_corner_edits(self):
        for operation, options in [(Fillet, {"radius": 1}), (Chamfer, {"distance": 1})]:
            shape = Difference(self.rectangle((20, 20)), self.rectangle((10, 10)))
            result = operation(shape, **options)
            self.assert_area(result, 300)
            self.assertEqual(list(region(result).each())[0].holes(), 1)

    def test_selected_corners_and_parameter_rebuild(self):
        radius = Parameter(1000, "rounding", unit="nm")
        vertices = Vertices([(-5, -3)])
        result = Fillet(self.rectangle(), radius=radius, corners=vertices)
        self.assert_area(result, 59+pi/4)
        radius.value = 2000
        self.assert_area(result, 56+pi)
        vertices[0] = (5, 3)
        self.project.build()
        self.assertEqual(self.project.parameters["rounding"], radius)

    def test_invalid_corner_location_and_oversize_radius(self):
        result = Fillet(self.rectangle(), radius=4)
        with self.assertRaisesRegex(ValueError, "too large"):
            result.to_klayout()
        result = Chamfer(self.rectangle(), distance=1, corners=[(123, 456)])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            result.to_klayout()

    def test_fillet_trim_limit_analytic_radius_and_parameter_rebuild(self):
        height = Parameter(5, "plate_height", unit="um")
        radius = Parameter(10, "corner_radius", unit="um")
        rounded = self.rectangle((10, height)).fillet(
            radius=radius, max_trim_fraction=0.49)
        self.assert_area(rounded, 50-(4-pi)*2.45**2)
        self.assertEqual(len(rounded.effective_radii()), 4)
        for _, actual in rounded.effective_radii():
            self.assertAlmostEqual(actual, 2.45)
        self.project.build()
        height.value = 8
        radius.value = 3
        self.project.build()
        self.assert_area(rounded, 80-(4-pi)*3**2)
        for _, actual in rounded.effective_radii():
            self.assertAlmostEqual(actual, 3)
        self.assertIs(self.project.parameters['plate_height'], height)
        self.assertIs(self.project.parameters['corner_radius'], radius)

    def test_fillet_trim_limit_selected_acute_corner(self):
        triangle = Polygon(self.project, layer=self.layer,
                           vertices=[(0, 0), (10, 0), (0, 10)])
        rounded = Fillet(triangle, radius=10, corners=[(10, 0)],
                         max_trim_fraction=0.49)
        # A 45-degree interior angle has a tangent trim r*(1+sqrt(2)).
        # Limiting the trim to 4.9 um therefore gives this circle radius.
        radius = 4.9*(sqrt(2)-1)
        self.assertEqual(len(rounded.effective_radii()), 1)
        point, actual = rounded.effective_radii()[0]
        self.assertEqual(point, (10, 0))
        self.assertAlmostEqual(actual, radius)
        removed_area = radius**2*(1+sqrt(2)-3*pi/8)
        self.assert_area(rounded, 50-removed_area)
        vertices = {(p.x, p.y) for p in rounded.to_klayout().each_point_hull()}
        self.assertIn((0, 0), vertices)
        self.assertIn((0, 10), vertices)
        self.assertNotIn((10, 0), vertices)

    def test_fillet_trim_limit_preserves_holes_and_disjoint_islands(self):
        outer = self.rectangle((40, 30))
        hole = self.rectangle((10, 6))
        ring = outer.difference(hole)
        island = self.rectangle((20, 8), position=(50, 0))
        rounded = Fillet(Union((ring, island), interior_boundaries=False),
                         radius=10, max_trim_fraction=0.49)
        produced = region(rounded)
        self.assertEqual(produced.count(), 2)
        self.assertEqual(sum(p.holes() for p in produced.each()), 1)
        expected = 1140-(4-pi)*(10**2-2.94**2)+160-(4-pi)*3.92**2
        self.assert_area(rounded, expected, delta=0.08)

    def test_fillet_trim_limit_rejects_invalid_policy_without_registration(self):
        source = self.rectangle()
        count = len(self.project.objects)
        for fraction in (0, -0.1, 0.5, 1, float('nan'), float('inf'), True, '0.49'):
            with self.subTest(fraction=fraction), self.assertRaises((TypeError, ValueError)):
                Fillet(source, radius=1, max_trim_fraction=fraction)
        self.assertEqual(len(self.project.objects), count)
        missing = Fillet(source, radius=1, corners=[(123, 456)], max_trim_fraction=0.49)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            missing.to_klayout()
        other = self.rectangle(position=(20, 0))
        count = len(self.project.objects)
        with self.assertRaisesRegex(ValueError, 'Union'):
            Fillet((source, other), radius=1, max_trim_fraction=0.49)
        self.assertEqual(len(self.project.objects), count)

    def test_curved_corner_inputs_are_explicitly_rejected(self):
        circle = Circle(self.project, layer=self.layer, radius=5)
        with self.assertRaisesRegex(ValueError, "straight-edged"):
            Fillet(circle, radius=1)

    def test_offset_grow_shrink_and_miter(self):
        self.assert_area(Offset(self.rectangle(), distance=1), 92+pi)
        self.assert_area(Offset(self.rectangle(), distance=1, reverse=True), 32)
        self.assert_area(Offset(self.rectangle(), distance=1, corner="extend"), 96)

    def test_offset_preserves_holes(self):
        shape = Difference(self.rectangle((20, 20)), self.rectangle((10, 10)))
        result = shape.offset(distance=1)
        self.assert_area(result, 416+pi)
        self.assertEqual(list(region(result).each())[0].holes(), 1)

    def test_offset_round_shape_and_disappearing_shape(self):
        circle = Circle(self.project, layer=self.layer, radius=10)
        self.assert_area(circle.offset(distance=1), 121*pi, delta=0.1)
        self.assertEqual(Offset(self.rectangle(), distance=10, reverse=True).to_klayout(), ())

    def test_offset_curve_direction_and_retention(self):
        source = self.line()
        left = source.offset(distance=2, keep=True)
        right = source.offset(distance=1, reverse=True)
        self.assertEqual(list(left.to_klayout().each_point()), [kdb.DPoint(0, 2), kdb.DPoint(10, 2)])
        self.assertEqual(list(right.to_klayout().each_point()), [kdb.DPoint(0, -1), kdb.DPoint(10, -1)])
        self.assertEqual(self.project._final_objects(self.project.objects), [left, right])
        with self.assertRaisesRegex(TypeError, "filled"):
            Union(left)

    def test_thicken_line_caps(self):
        self.assert_area(self.line().thicken(width=2), 20, delta=1e-9)
        self.assert_area(self.line().thicken(width=2, ends="circular"), 20+pi)

    def test_thicken_closed_boundary_and_boolean(self):
        thick = self.rectangle().thicken(width=2)
        self.assert_area(thick, 60+pi)
        self.assertEqual(list(region(thick).each())[0].holes(), 1)
        cut = thick.difference(self.rectangle((40, 6), position=(0, 5)))
        self.assertGreater(region(cut).area(), 0)
        moved = cut.scale(factor=(2, 1)).rotate(angle=30)
        self.project.build()
        self.assertEqual(self.project._final_objects(self.project.objects), [moved])

    def test_thicken_curve_and_width_parameter(self):
        width = Parameter(2, "track_width", unit="um")
        arc = CircularArc(self.project, layer=self.layer, radius=10, start_angle=0, end_angle=90)
        thick = Thicken2D(arc, width=width)
        self.assert_area(thick, 10*pi, delta=0.05)
        width.value = 4
        self.assert_area(thick, 20*pi, delta=0.07)

    def test_grid_policy_and_operation_report(self):
        thick = self.line().thicken(width=2, ends="circular")
        self.project.build()
        report = self.project.grid_report()
        self.assertEqual(report["planar_operations"][0]["type"], "Thicken2D")
        self.assertTrue(any(item["stage"] == "operation_input" for item in report["objects"]))
        self.project.grid_policy = "error"
        with self.assertRaisesRegex(ValueError, "off the GDS grid"):
            self.project.build()
        self.assertFalse(self.project.grid_report()["complete"])

    def test_validation_and_no_partial_registration(self):
        source = self.line()
        before = len(self.project.objects)
        for options in ({"width": 0}, {"width": 2, "corner": "unknown"},
                        {"width": 2, "ends": "unknown"}, {"width": 2, "tolerance": 0}):
            with self.assertRaises(ValueError):
                Thicken2D(source, **options)
        self.assertEqual(len(self.project.objects), before)
        point = Point(self.project, layer=self.layer)
        with self.assertRaises(TypeError):
            Thicken2D(point, width=2)

    def test_offset_rejects_curve_collapse(self):
        arc = CircularArc(self.project, layer=self.layer, radius=1,
                          start_angle=0, end_angle=90)
        result = Offset(arc, distance=2)
        with self.assertRaisesRegex(ValueError, "collapses|trimming"):
            result.to_klayout()

    def test_round_caps_are_not_straight_corner_inputs(self):
        thick = self.line().thicken(width=2, corner="extend", ends="circular")
        with self.assertRaisesRegex(ValueError, "straight-edged"):
            thick.chamfer(distance=0.1)

    def test_coarse_cap_sampling_remains_a_polygon(self):
        thick = self.line().thicken(width=0.1, ends="circular", tolerance=1)
        self.assertGreater(region(thick).area(), 0)

    def test_example_offline_and_repeated_builds(self):
        import os
        import runpy
        from unittest.mock import patch
        directory = Path(__file__).resolve().parents[1] / 'examples'
        original = Project.add_layer
        def offline_layer(project, *args, **kwargs):
            kwargs["comsol"] = False
            return original(project, *args, **kwargs)
        previous = Path.cwd()
        try:
            os.chdir(self.folder.name)
            with patch.object(Project, "add_layer", offline_layer), patch.object(Project, "show"):
                namespace = runpy.run_path(str(directory/"example_planar_operations.py"))
            project = namespace["project"]
            namespace["radius"].value = 3
            namespace["width"].value = 3
            namespace["distance"].value = 1.5
            namespace["outline"][2] = (47, 32)
            project.build()
            project.build()
            self.assertTrue(project.grid_report()["complete"])
            self.assertIsNone(project.model)
        finally:
            os.chdir(previous)

