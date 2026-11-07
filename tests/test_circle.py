"""Analytic disks, bounded GDS approximation and live parameter references."""

from math import hypot, pi, sin
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import Parameter, Project, Vertices
from geompype.primitives import Circle
from geompype.transforms import Rotate
from test_parameter_geometry import RecordedGeometry


class TestCircle(unittest.TestCase):
    def test_disk_round_trip_and_rotation(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "disk")
            layer = project.add_layer("metal", comsol=False,
                                      gds_layer=12, gds_datatype=3)
            circle = Circle(project, layer=layer, radius=10, position=(4, 5))
            Rotate(circle, angle=90)
            project.build()

            layout = kdb.Layout()
            layout.read(str(project.gds_path))
            shapes = layout.top_cell().shapes(layout.layer(12, 3))
            self.assertEqual(shapes.size(), 1)
            region = kdb.Region(shapes)
            self.assertEqual(region.bbox(), kdb.Box(-15000, -6000, 5000, 14000))
            self.assertAlmostEqual(region.area() * layout.dbu**2, pi * 100,
                                   delta=0.1)
            self.assertIsNone(project.client)

    def test_chord_error_respects_tolerance_before_grid_rounding(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False)
        circle = Circle(project, layer=layer, radius=23,
                        position=(7, -3), tolerance=0.005)
        polygon = circle.to_klayout()
        points = list(polygon.each_point_hull())
        self.assertEqual(len(points) % 4, 0)
        for start, end in zip(points, points[1:] + points[:1]):
            distance = hypot((start.x + end.x) / 2 - 7,
                             (start.y + end.y) / 2 + 3)
            self.assertLessEqual(23 - distance, 0.005 + 1e-12)
        circle.tolerance = 0.0005
        self.assertGreater(circle.to_klayout().num_points_hull(), len(points))

    def test_parameter_and_vertices_changes_rebuild_the_disk(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "parameters", live=True)
            layer = project.add_layer("metal", comsol=False)
            radius = Parameter(2000, "radius", unit="nm")
            pitch = Parameter(4, "pitch", unit="um")
            position = Vertices([pitch, -pitch])
            circle = Circle(project, layer=layer, radius=radius, position=position)
            self.assertIs(circle.radius, radius)
            self.assertIs(circle.position, position)
            self.assertIs(project.parameters["radius"], radius)
            self.assertIs(project.parameters["pitch"], pitch)
            self.assertEqual(circle.to_klayout().bbox(), kdb.DBox(2, -6, 6, -2))
            old_file = project.gds_path.read_bytes()

            radius.value = 3000
            pitch.value = 8
            self.assertEqual(project.gds_path.read_bytes(), old_file)
            project.build()
            self.assertEqual(circle.to_klayout().bbox(), kdb.DBox(5, -11, 11, -5))
            position[0, 0] = -1
            project.build()
            self.assertEqual(circle.to_klayout().bbox(), kdb.DBox(-4, -11, 2, -5))

    def test_native_feature_keeps_expressions_and_is_reused(self):
        project = Project()
        layer = project.add_layer("metal", gds=False)
        radius = Parameter(10, "radius", unit="um")
        circle = Circle(project, layer=layer, radius=radius,
                        position=Vertices([radius / 2, 0]))
        geometry = RecordedGeometry([])
        circle.to_comsol(geometry, circle.tag)
        circle.to_comsol(geometry, circle.tag)
        self.assertEqual(len(geometry.features), 1)
        feature = geometry.features[circle.tag]
        self.assertEqual(feature.kind, "Circle")
        self.assertEqual(feature.values["type"], "solid")
        self.assertEqual(feature.values["base"], "center")
        self.assertEqual(feature.values["angle"], "360")
        self.assertEqual(feature.values["r"], "radius")
        self.assertIn("radius", feature.values["pos"][0])
        self.assertNotIn("tolerance", feature.values)

    def test_sampling_cap_accepts_fine_outlines_and_only_limits_gds(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False)
        circle = Circle(project, layer=layer, radius=10,
                        tolerance=20 * sin(pi / (2 * 50000))**2)
        count = circle.to_klayout().num_points_hull()
        self.assertGreaterEqual(count, 50000)
        self.assertLessEqual(count, 50004)

        boundary = 20 * sin(pi / (2 * 65536))**2
        circle.tolerance = boundary * 1.000001
        self.assertEqual(circle.to_klayout().num_points_hull(), 65536)
        circle.tolerance = boundary * 0.999999
        with self.assertRaisesRegex(ValueError, "65536 GDS vertices"):
            circle.to_klayout()

        native = project.add_layer("native", gds=False)
        circle = Circle(project, layer=native, radius=10, tolerance=1e-20)
        geometry = RecordedGeometry([])
        circle.to_comsol(geometry, circle.tag)
        self.assertEqual(geometry.features[circle.tag].values["r"], "10")

    def test_invalid_values_and_excessive_sampling_are_rejected(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False)
        invalid = [
            {"radius": 0}, {"radius": -1}, {"radius": float("inf")},
            {"radius": float("nan")}, {"tolerance": 0},
            {"tolerance": -1}, {"tolerance": float("inf")},
            {"position": (0,)}, {"position": (float("nan"), 0)},
            {"radius": 1e308, "position": (1e308, 0)},
            {"radius": Parameter(30, "wrong_unit", unit="deg")},
        ]
        for options in invalid:
            with self.subTest(options=options), self.assertRaises(ValueError):
                Circle(project, layer=layer, **({"radius": 10} | options))
        self.assertEqual(project.objects, [])

        circle = Circle(project, layer=layer, radius=10, tolerance=1e-20)
        with self.assertRaisesRegex(ValueError, "65536 GDS vertices"):
            circle.to_klayout()


if __name__ == "__main__":
    unittest.main()
