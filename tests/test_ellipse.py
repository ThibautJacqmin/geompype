"""Ellipse geometry, parameter updates, and native COMSOL expressions offline."""

from math import cos, pi, radians, sin, sqrt, tau
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import DependentParameter, Parameter, Project, Vertices
from geompype.primitives import Ellipse
from test_parameter_geometry import RecordedGeometry


def read_region(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    return layout, kdb.Region(layout.top_cell().shapes(layout.layer(17, 3)))


class TestEllipse(unittest.TestCase):
    def test_rotated_ellipse_area_bounds_and_layer_in_both_modes(self):
        with TemporaryDirectory() as folder:
            for live in (False, True):
                for angle in (0, 33, 90):
                    with self.subTest(live=live, angle=angle):
                        project = Project(output=Path(folder) / f"ellipse_{live}_{angle}",
                                          live=live, dbu=0.0001)
                        layer = project.add_layer("metal", comsol=False,
                                                  gds_layer=17, gds_datatype=3)
                        Ellipse(project, layer=layer, semiaxes=(8, 2),
                                position=(10, -3), angle=angle, tolerance=0.0001)
                        self.assertEqual(project.gds_path.exists(), live)
                        project.build()
                        layout, region = read_region(project)
                        self.assertEqual([(info.layer, info.datatype)
                                          for info in layout.layer_infos()], [(17, 3)])
                        self.assertAlmostEqual(region.area() * layout.dbu**2,
                                               pi * 8 * 2, delta=0.005)
                        bounds = region.bbox().to_dtype(layout.dbu)
                        c, s = cos(radians(angle)), sin(radians(angle))
                        dx, dy = sqrt((8*c)**2 + (2*s)**2), sqrt((8*s)**2 + (2*c)**2)
                        expected = (10-dx, -3-dy, 10+dx, -3+dy)
                        for actual, target in zip((bounds.left, bounds.bottom,
                                                   bounds.right, bounds.top), expected):
                            self.assertAlmostEqual(actual, target, delta=0.0002)

    def test_live_parameter_and_vertices_references_follow_explicit_build(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "parameters", live=True)
            layer = project.add_layer("metal", comsol=False, gds_layer=17, gds_datatype=3)
            major = Parameter(6000, "major", unit="nm")
            minor = DependentParameter(major / 3, "minor")
            theta = Parameter(pi / 2, "theta", unit="rad")
            position = Vertices((major, 3))
            selection = project.add_selection("metal_faces")
            ellipse = Ellipse(project, layer=layer, semiaxes=(major, minor),
                              position=position, angle=theta, selections=(selection,))
            self.assertIs(ellipse.semiaxes[0], major)
            self.assertIs(ellipse.semiaxes[1], minor)
            self.assertIs(ellipse.position, position)
            self.assertIs(ellipse.angle, theta)
            self.assertEqual(selection.members, (ellipse,))
            old_bytes = project.gds_path.read_bytes()
            major.value = 9000
            position[0, 1] = -2
            self.assertEqual(project.gds_path.read_bytes(), old_bytes)
            project.build()
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area() * layout.dbu**2, pi * 9 * 3, delta=0.04)
            self.assertEqual(region.bbox().to_dtype(layout.dbu), kdb.DBox(6, -11, 12, 7))
            self.assertEqual(set(project.parameters), {"major", "minor", "theta"})

    def test_native_feature_retains_symbols_and_uses_centre_and_solid(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False)
        major = Parameter(4, "major", unit="um")
        angle = Parameter(45, "theta", unit="deg")
        ellipse = Ellipse(project, layer=layer, semiaxes=(major, major / 2),
                          position=Vertices((major, 0)), angle=angle)
        geometry = RecordedGeometry([])
        ellipse.to_comsol(geometry, ellipse.tag)
        ellipse.to_comsol(geometry, ellipse.tag)
        self.assertEqual(len(geometry.features), 1)
        feature = geometry.features[ellipse.tag]
        self.assertEqual(feature.kind, "Ellipse")
        self.assertEqual(feature.values["type"], "solid")
        self.assertEqual(feature.values["base"], "center")
        self.assertEqual(feature.values["semiaxes"], ["major", "(major/2)"])
        self.assertEqual(feature.values["pos"], ["major", "(0*1[um])"])
        self.assertEqual(feature.values["rot"], "theta")

    def test_eccentric_ellipse_contour_stays_within_tolerance(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False)
        ellipse = Ellipse(project, layer=layer, semiaxes=(12, 0.3),
                          angle=27, position=(3, -2), tolerance=0.003)
        points = list(ellipse.to_klayout().each_point_hull())
        self.assertEqual(len(points) % 4, 0)
        edges = list(zip(points, points[1:] + points[:1]))
        c, s = cos(radians(27)), sin(radians(27))

        def distance_to_segment(x, y, start, end):
            dx, dy = end.x-start.x, end.y-start.y
            t = max(0, min(1, ((x-start.x)*dx + (y-start.y)*dy) / (dx*dx + dy*dy)))
            return sqrt((x-start.x-t*dx)**2 + (y-start.y-t*dy)**2)

        for index in range(720):
            phase = tau * (index + 0.37) / 720
            x, y = 12*cos(phase), 0.3*sin(phase)
            x, y = 3+c*x-s*y, -2+s*x+c*y
            error = min(distance_to_segment(x, y, a, b) for a, b in edges)
            self.assertLessEqual(error, 0.003 + 1e-12)

    def test_invalid_input_and_sampling_limits_preserve_registry_and_output(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "invalid")
            layer = project.add_layer("metal", comsol=False, gds_layer=17, gds_datatype=3)
            invalid = [{"semiaxes": (0, 2)}, {"semiaxes": (-1, 2)},
                       {"semiaxes": (1,)}, {"semiaxes": (1, 2, 3)},
                       {"semiaxes": (float("inf"), 2)}, {"position": (0,)},
                       {"angle": float("nan")}, {"tolerance": 0},
                       {"tolerance": float("inf")}, {"tolerance": 1e-20}]
            for options in invalid:
                with self.subTest(options=options):
                    with self.assertRaises(ValueError):
                        Ellipse(project, layer=layer, **({"semiaxes": (4, 2)} | options))
            self.assertEqual(project.objects, [])
            ellipse = Ellipse(project, layer=layer, semiaxes=(4, 2))
            project.build()
            previous = project.gds_path.read_bytes()
            ellipse.tolerance = 1e-20
            with self.assertRaisesRegex(ValueError, "too many points"):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), previous)

    def test_gds_sampling_limit_does_not_restrict_native_comsol_geometry(self):
        project = Project()
        layer = project.add_layer("native", comsol=False, gds=False)
        ellipse = Ellipse(project, layer=layer, semiaxes=(4, 2), tolerance=1e-30)
        geometry = RecordedGeometry([])
        ellipse.to_comsol(geometry, ellipse.tag)
        self.assertEqual(geometry.features[ellipse.tag].values["semiaxes"],
                         ["4", "2"])


if __name__ == "__main__":
    unittest.main()
