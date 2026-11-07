"""Filled polygon topology, live coordinates and native expressions."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import Parameter, Project, Vertices
from geompype.primitives import Polygon
from test_parameter_geometry import RecordedGeometry


def read_region(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    return layout, kdb.Region(layout.top_cell().shapes(layout.layer(8, 2)))


class TestPolygon(unittest.TestCase):
    def test_concave_outline_both_orientations_and_explicit_closure(self):
        outline = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 3), (0, 3)]
        with TemporaryDirectory() as folder:
            for reverse in (False, True):
                for close in (False, True):
                    with self.subTest(reverse=reverse, close=close):
                        vertices = list(reversed(outline)) if reverse else outline.copy()
                        if close:
                            vertices.append(vertices[0])
                        project = Project(output=Path(folder) / "concave")
                        layer = project.add_layer("metal", comsol=False,
                                                  gds_layer=8, gds_datatype=2)
                        polygon = Polygon(project, layer=layer, vertices=vertices)
                        project.build()
                        layout, region = read_region(project)
                        self.assertAlmostEqual(region.area() * layout.dbu**2, 6)
                        expected = kdb.Region(kdb.Box(0, 0, 4000, 1000))
                        expected += kdb.Region(kdb.Box(0, 1000, 1000, 3000))
                        self.assertTrue((region ^ expected).is_empty())
                        self.assertEqual(polygon.to_klayout().num_points_hull(), 6)

    def test_vertices_references_mutation_and_rotation(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "live", live=True)
            layer = project.add_layer("metal", comsol=False,
                                      gds_layer=8, gds_datatype=2)
            width = Parameter(4, "width", unit="um")
            height = Parameter(2000, "height", unit="nm")
            points = Vertices([[0, 0], [width, 0], [0, height]])
            polygon = Polygon(project, layer=layer, vertices=points)
            self.assertIs(polygon.vertices, points)
            previous = project.gds_path.read_bytes()
            width.value = 6
            points[2, 1] = 2 * height
            self.assertEqual(project.gds_path.read_bytes(), previous)
            polygon.rotate(angle=90)
            project.build()
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 12)
            self.assertEqual(region.bbox().to_dtype(layout.dbu), kdb.DBox(-4, 0, 0, 6))
            self.assertEqual(layout.top_cell().shapes(layout.layer(8, 2)).size(), 1)
            self.assertEqual(set(project.parameters), {"width", "height"})

    def test_native_vectors_keep_expressions_and_normalize_identical_closure(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        width = Parameter(4, "width", unit="um")
        height = Parameter(2000, "height", unit="nm")
        polygon = Polygon(project, layer=layer,
                          vertices=[[0, 0], [width, 0], [0, height], [0, 0]])
        plane = RecordedGeometry([])
        polygon.to_comsol(plane, polygon.tag)
        polygon.to_comsol(plane, polygon.tag)
        self.assertEqual(len(plane.features), 1)
        feature = plane.features[polygon.tag]
        self.assertEqual(feature.kind, "Polygon")
        self.assertEqual(feature.values["type"], "solid")
        self.assertEqual(feature.values["source"], "vectors")
        self.assertEqual(len(feature.values["x"]), 3)
        self.assertEqual(feature.values["x"][1], "width")
        self.assertEqual(feature.values["y"][2], "height")

    def test_coincident_closure_with_different_parameters_keeps_both_dependencies(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        first = Parameter(0, "first", unit="um")
        last = Parameter(0, "last", unit="um")
        polygon = Polygon(project, layer=layer,
                          vertices=[[first, 0], [4, 0], [4, 3], [0, 3], [last, 0]])
        plane = RecordedGeometry([])
        polygon.to_comsol(plane, polygon.tag)
        values = plane.features[polygon.tag].values
        self.assertEqual(len(values["x"]), 5)
        self.assertEqual(values["x"][0], "first")
        self.assertEqual(values["x"][-1], "last")
        self.assertEqual(set(project.parameters), {"first", "last"})
        self.assertEqual(polygon.to_klayout().num_points_hull(), 4)

    def test_invalid_outlines_are_not_registered(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        invalid = [[], [[0, 0], [1, 0]], [[0, 0], [1, 0], [2, 0]],
                   [[0, 0], [1, 0], [1, 0], [0, 1]],
                   [[0, 0], [2, 0], [2, 2], [0, 0], [0, 2]],
                   [[0, 0], [4, 3], [0, 4], [3, 0]],
                   [[0, 0], [3, 0], [1, 0], [1, 1], [0, 1]],
                   [[0, 0], [3, 0], [3, 3], [1, 0], [0, 3]],
                   [[0, 0], [1, float("nan")], [0, 1]],
                   [[0, 0], [1, 0], [0, float("inf")]],
                   [[0, 0], [1, 0], [0, 1], [0, 0], [0, 0]]]
        for vertices in invalid:
            with self.subTest(vertices=vertices):
                with self.assertRaises(ValueError):
                    Polygon(project, layer=layer, vertices=vertices)
        self.assertEqual(project.objects, [])

    def test_validation_is_translation_and_scale_stable(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        for origin, scale in ((0, 1e-120), (1e9, 0.01), (0, 1e120)):
            with self.subTest(origin=origin, scale=scale):
                Polygon(project, layer=layer,
                        vertices=[[origin, origin], [origin + scale, origin],
                                  [origin + scale, origin + scale],
                                  [origin, origin + scale]])
        # An extra vertex on a straight edge does not make an invalid polygon.
        Polygon(project, layer=layer, vertices=[[0, 0], [1, 0], [2, 0], [2, 1], [0, 1]])

    def test_invalid_coordinate_edit_preserves_previous_output(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "valid")
            layer = project.add_layer("metal", comsol=False)
            points = Vertices([[0, 0], [2, 0], [2, 2], [0, 2]])
            Polygon(project, layer=layer, vertices=points)
            project.build()
            previous = project.gds_path.read_bytes()
            points[1] = [0, 2]
            with self.assertRaises(ValueError):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
