"""Circular-arc direction, sampling, expressions and saved zero-width paths."""

from math import atan2, cos, hypot, pi, radians, sin
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import Parameter, Project, Vertices
from geompype.primitives import CircularArc
from test_parameter_geometry import RecordedGeometry


class TestCircularArc(unittest.TestCase):
    def setUp(self):
        self.project = Project()
        self.layer = self.project.add_layer("arcs", comsol=False, gds=False)

    def test_direction_major_arcs_and_wrapped_angles(self):
        cases = [(0, 90, False, 90), (0, 90, True, -270),
                 (90, 0, False, 270), (90, 0, True, -90),
                 (350, 10, False, 20), (10, 350, True, -20),
                 (1070, -350, False, 20)]
        for start, end, clockwise, sweep in cases:
            with self.subTest(start=start, end=end, clockwise=clockwise):
                curve = CircularArc(self.project, layer=self.layer, radius=5, center=(3, -2),
                                    start_angle=start, end_angle=end, clockwise=clockwise)
                path = curve.to_klayout()
                self.assertIsInstance(path, kdb.DPath)
                self.assertEqual(path.width, 0)
                points = [(point.x - 3, point.y + 2) for point in path.each_point()]
                for actual, angle in ((points[0], start), (points[-1], end)):
                    self.assertAlmostEqual(actual[0], 5*cos(radians(angle % 360)), places=12)
                    self.assertAlmostEqual(actual[1], 5*sin(radians(angle % 360)), places=12)
                accumulated = sum(atan2(a[0]*b[1] - a[1]*b[0], a[0]*b[0] + a[1]*b[1])
                                  for a, b in zip(points, points[1:]))
                self.assertAlmostEqual(accumulated, radians(sweep), places=12)

    def test_chord_error_and_length_converge_with_tolerance(self):
        radius, sweep = 7, radians(250)
        lengths = []
        counts = []
        for tolerance in (0.1, 0.01, 0.001):
            curve = CircularArc(self.project, layer=self.layer, radius=radius,
                                start_angle=30, end_angle=280, tolerance=tolerance)
            path = curve.to_klayout()
            vertices = [(point.x, point.y) for point in path.each_point()]
            for first, second in zip(vertices, vertices[1:]):
                midpoint = ((first[0] + second[0])/2, (first[1] + second[1])/2)
                self.assertLessEqual(radius - hypot(*midpoint), tolerance * (1 + 1e-10))
            for point in vertices:
                self.assertAlmostEqual(hypot(*point), radius, places=12)
            lengths.append(path.length())
            counts.append(len(vertices))
        self.assertLess(counts[0], counts[1])
        self.assertLess(counts[1], counts[2])
        self.assertLess(lengths[0], lengths[1])
        self.assertLess(lengths[1], lengths[2])
        self.assertLess(lengths[-1], radius*sweep)
        self.assertAlmostEqual(lengths[-1], radius*sweep, delta=0.01)

    def test_loose_tolerance_does_not_collapse_a_major_arc_to_one_chord(self):
        curve = CircularArc(self.project, layer=self.layer, radius=1,
                            start_angle=0, end_angle=270, tolerance=100)
        points = list(curve.to_klayout().each_point())
        self.assertGreaterEqual(len(points), 3)
        self.assertAlmostEqual(points[-1].x, 0)
        self.assertAlmostEqual(points[-1].y, -1)

    def test_radius_center_and_angle_parameter_references_remain_live(self):
        radius = Parameter(2000, "radius", unit="nm")
        x = Parameter(3, "x", unit="um")
        start = Parameter(0, "start", unit="deg")
        end = Parameter(pi/2, "end", unit="rad")
        center = Vertices([x, 1])
        curve = CircularArc(self.project, layer=self.layer, radius=radius, center=center,
                            start_angle=start, end_angle=end)
        self.assertIs(curve.center, center)
        self.assertIs(curve.radius, radius)
        self.assertIs(curve.start_angle, start)
        self.assertIs(curve.end_angle, end)
        original = list(curve.to_klayout().each_point())
        self.assertEqual(original[0], kdb.DPoint(5, 1))
        self.assertAlmostEqual(original[-1].x, 3)
        self.assertAlmostEqual(original[-1].y, 3)
        radius.value = 4000
        x.value = 5
        center[0, 1] = 2
        start.value = 90
        end.value = pi
        changed = list(curve.to_klayout().each_point())
        self.assertAlmostEqual(changed[0].x, 5)
        self.assertAlmostEqual(changed[0].y, 6)
        self.assertAlmostEqual(changed[-1].x, 1)
        self.assertAlmostEqual(changed[-1].y, 2)
        self.assertEqual(set(self.project.parameters), {"radius", "x", "start", "end"})

    def test_native_properties_keep_expressions_and_reuse_the_feature(self):
        radius = Parameter(2000, "radius", unit="nm")
        start = Parameter(30, "start", unit="deg")
        end = Parameter(pi, "end", unit="rad")
        curve = CircularArc(self.project, layer=self.layer, radius=radius,
                            center=Vertices([2*radius, 0]), start_angle=start,
                            end_angle=end, clockwise=True)
        plane = RecordedGeometry([])
        curve.to_comsol(plane, curve.tag)
        curve.to_comsol(plane, curve.tag)
        self.assertEqual(len(plane.features), 1)
        feature = plane.features[curve.tag]
        self.assertEqual(feature.kind, "CircularArc")
        self.assertEqual(feature.values["specify"], "center")
        self.assertIn("radius", feature.values["center"][0])
        self.assertEqual(feature.values["r"], "radius")
        self.assertEqual(feature.values["angle1"], "start")
        self.assertEqual(feature.values["angle2"], "end")
        self.assertEqual(feature.values["clockwise"], "on")
        curve.clockwise = False
        curve.to_comsol(plane, curve.tag)
        self.assertEqual(feature.values["clockwise"], "off")

    def test_invalid_input_is_not_registered(self):
        invalid = [dict(radius=0), dict(radius=-1), dict(radius=float("nan")),
                   dict(radius=Parameter(1, "angle", unit="deg")), dict(center=(1,)),
                   dict(center=Vertices([[0, 0], [1, 1]])), dict(center=(float("inf"), 0)),
                   dict(radius=1e308, center=(1.7e308, 0)),
                   dict(start_angle=1, end_angle=1), dict(end_angle=360), dict(end_angle=-720),
                   dict(start_angle=float("nan")), dict(end_angle=float("inf")),
                   dict(clockwise=1), dict(clockwise="on"), dict(tolerance=0),
                   dict(tolerance=-1), dict(tolerance=Parameter(1, "angle", unit="deg"))]
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    CircularArc(self.project, **(dict(layer=self.layer, radius=1) | arguments))
        self.assertEqual(self.project.objects, [])

    def test_sampling_cap_accepts_65536_points_and_rejects_more(self):
        # Half-integer segment targets avoid an ambiguous floating-point ceil
        # exactly on the boundary while exercising the actual 65536-point cap.
        sweep = pi/2
        accepted_tolerance = 2*sin(sweep/(4*65534.5))**2
        curve = CircularArc(self.project, layer=self.layer, radius=1,
                            tolerance=accepted_tolerance)
        self.assertEqual(curve.to_klayout().num_points(), 65536)
        curve.tolerance = 2*sin(sweep/(4*65535.5))**2
        with self.assertRaisesRegex(ValueError, "more than 65536"):
            curve.to_klayout()

    def test_gds_readback_in_deferred_and_live_modes(self):
        with TemporaryDirectory() as folder:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(output=Path(folder)/str(live), live=live, dbu=0.0001)
                    layer = project.add_layer("arc", comsol=False, gds_layer=23, gds_datatype=4)
                    curve = CircularArc(project, layer=layer, radius=3, center=(5, 7),
                                        start_angle=0, end_angle=270, clockwise=False,
                                        tolerance=0.0001)
                    project.build()
                    layout = kdb.Layout()
                    layout.read(str(project.gds_path))
                    shapes = list(layout.top_cell().shapes(layout.layer(23, 4)).each())
                    self.assertEqual(len(shapes), 1)
                    self.assertTrue(shapes[0].is_path())
                    saved = shapes[0].path.to_dtype(layout.dbu)
                    self.assertEqual(saved.width, 0)
                    points = list(saved.each_point())
                    self.assertEqual(points[0], kdb.DPoint(8, 7))
                    self.assertEqual(points[-1], kdb.DPoint(5, 4))
                    self.assertGreater(saved.length(), 3*pi)
                    self.assertAlmostEqual(saved.length(), 4.5*pi, delta=0.001)
                    self.assertGreater(curve.to_klayout().num_points(), 2)

    def test_grid_collapse_keeps_previous_file(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/"arc", dbu=1)
            layer = project.add_layer("arc", comsol=False)
            radius = Parameter(3, "radius", unit="um")
            CircularArc(project, layer=layer, radius=radius)
            project.build()
            previous = project.gds_path.read_bytes()
            radius.value = 0.0001
            with self.assertRaisesRegex(ValueError, "collapses on the GDS grid"):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), previous)
