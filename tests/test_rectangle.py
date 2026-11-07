"""Rectangle geometry, parameter references and native COMSOL expressions."""

from math import pi
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import DependentParameter, Parameter, Project, Vertices
from geompype.primitives import Rectangle
from test_parameter_geometry import RecordedGeometry


def read_region(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    return layout, kdb.Region(layout.top_cell().shapes(layout.layer(17, 3)))


class TestRectangle(unittest.TestCase):
    def test_base_and_rotation_match_gds_bounds_and_area(self):
        cases = [("center", 0, (0, 3, 20, 7)),
                 ("center", 90, (8, -5, 12, 15)),
                 ("corner", 0, (10, 5, 30, 9)),
                 ("corner", 90, (6, 5, 10, 25))]
        with TemporaryDirectory() as folder:
            for base, angle, bounds in cases:
                with self.subTest(base=base, angle=angle):
                    project = Project(output=Path(folder) / "rectangle")
                    layer = project.add_layer("metal", comsol=False,
                                              gds_layer=17, gds_datatype=3)
                    Rectangle(project, layer=layer, size=(20, 4), position=(10, 5),
                              base=base, angle=angle)
                    project.build()
                    layout, region = read_region(project)
                    self.assertAlmostEqual(region.area() * layout.dbu**2, 80)
                    actual = region.bbox().to_dtype(layout.dbu)
                    self.assertEqual((actual.left, actual.bottom, actual.right, actual.top),
                                     bounds)
                    self.assertEqual(layout.top_cell().shapes(layout.layer(17, 3)).size(), 1)

    def test_live_parameters_vertices_and_rotation_follow_rebuild(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "parameters", live=True)
            layer = project.add_layer("metal", comsol=False,
                                      gds_layer=17, gds_datatype=3)
            width = Parameter(20, "width", unit="um")
            height = Parameter(4000, "height", unit="nm")
            pitch = DependentParameter(width + height, "pitch")
            angle = Parameter(pi / 2, "angle", unit="rad")
            position = Vertices([pitch, 2])
            rectangle = Rectangle(project, layer=layer, size=(width, height),
                                  position=position, angle=angle)
            self.assertIs(rectangle.size[0], width)
            self.assertIs(rectangle.position, position)
            self.assertIs(rectangle.angle, angle)
            self.assertTrue(project.gds_path.exists())
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 80)

            previous = project.gds_path.read_bytes()
            width.value = 30
            position[0, 1] = 5
            self.assertEqual(project.gds_path.read_bytes(), previous)
            rectangle.rotate(angle=angle, origin=position)
            project.build()
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 120)
            self.assertEqual(region.bbox().to_dtype(layout.dbu), kdb.DBox(19, 3, 49, 7))
            self.assertEqual(layout.top_cell().shapes(layout.layer(17, 3)).size(), 1)
            self.assertEqual(set(project.parameters), {"width", "height", "pitch", "angle"})

    def test_comsol_emission_keeps_expressions_and_reuses_feature(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        width = Parameter(20, "width", unit="um")
        height = Parameter(4000, "height", unit="nm")
        angle = Parameter(30, "theta", unit="deg")
        rectangle = Rectangle(project, layer=layer, size=(width, 2 * height),
                              position=Vertices([width, height]),
                              base="corner", angle=angle)
        plane = RecordedGeometry([])
        rectangle.to_comsol(plane, rectangle.tag)
        rectangle.to_comsol(plane, rectangle.tag)
        self.assertEqual(len(plane.features), 1)
        feature = plane.features[rectangle.tag]
        self.assertEqual(feature.kind, "Rectangle")
        self.assertEqual(feature.values["type"], "solid")
        self.assertEqual(feature.values["base"], "corner")
        self.assertEqual(feature.values["size"][0], "width")
        self.assertIn("height", feature.values["size"][1])
        self.assertIn("width", feature.values["pos"][0])
        self.assertIn("height", feature.values["pos"][1])
        self.assertEqual(feature.values["rot"], "theta")

    def test_invalid_geometry_is_not_registered(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        invalid = [{"size": (0, 2)}, {"size": (-1, 2)}, {"size": (2,)},
                   {"size": (2, 3, 4)}, {"size": (float("nan"), 2)},
                   {"size": (2, float("inf"))}, {"base": "origin"},
                   {"angle": float("nan")}, {"position": (0,)},
                   {"position": Vertices([[0, 0], [1, 1]])},
                   {"size": (Parameter(1, "bad", unit="deg"), 2)}]
        for options in invalid:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    Rectangle(project, layer=layer, **({"size": (2, 3)} | options))
        self.assertEqual(project.objects, [])

        # Finite dimensions and positions can still overflow when combined.
        rectangle = Rectangle(project, layer=layer, size=(1e308, 1),
                              position=(1.7e308, 0), base="corner")
        with self.assertRaisesRegex(ValueError, "coordinates must remain finite"):
            rectangle.to_klayout()

    def test_invalid_parameter_edit_preserves_previous_gds(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "valid")
            layer = project.add_layer("metal", comsol=False)
            width = Parameter(2, "width", unit="um")
            Rectangle(project, layer=layer, size=(width, 3))
            project.build()
            previous = project.gds_path.read_bytes()
            width.value = 0
            with self.assertRaises(ValueError):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
