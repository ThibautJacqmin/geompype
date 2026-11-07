"""Point coordinates and line centrelines preserve their native dimensions."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import Parameter, Project, Vertices
from geompype.primitives import LineSegment, Point
from test_parameter_geometry import RecordedGeometry


class TestPointAndLine(unittest.TestCase):
    def test_coordinates_and_native_expressions_remain_live(self):
        project = Project()
        layer = project.add_layer("construction", comsol=False, gds=False)
        x = Parameter(2000, "x", unit="nm")
        distance = Parameter(3, "distance", unit="um")
        start = Vertices([x, 1])
        end = Vertices([x + distance, 1])
        point = Point(project, layer=layer, position=start)
        line = LineSegment(project, layer=layer, p1=start, p2=end)
        self.assertIs(point.position, start)
        self.assertIs(line.p1, start)
        self.assertIs(line.p2, end)
        self.assertIsInstance(point.to_klayout(), kdb.DPoint)
        self.assertEqual(point.to_klayout(), kdb.DPoint(2, 1))
        path = line.to_klayout()
        self.assertIsInstance(path, kdb.DPath)
        self.assertEqual(path.width, 0)
        self.assertEqual(list(path.each_point()), [kdb.DPoint(2, 1), kdb.DPoint(5, 1)])
        self.assertAlmostEqual(path.length(), 3)

        plane = RecordedGeometry([])
        for _ in range(2):
            point.to_comsol(plane, point.tag)
            line.to_comsol(plane, line.tag)
        self.assertEqual(len(plane.features), 2)
        native_point = plane.features[point.tag]
        native_line = plane.features[line.tag]
        self.assertEqual(native_point.kind, "Point")
        self.assertEqual(native_line.kind, "LineSegment")
        self.assertIn("x", native_point.values["p"][0])
        self.assertEqual(native_line.values["specify1"], "coord")
        self.assertEqual(native_line.values["specify2"], "coord")
        self.assertIn("x", native_line.values["coord1"][0])
        self.assertIn("distance", native_line.values["coord2"][0])

        x.value, distance.value = 4000, 7
        start[0, 1] = 2
        self.assertEqual(point.to_klayout(), kdb.DPoint(4, 2))
        self.assertEqual(list(line.to_klayout().each_point()),
                         [kdb.DPoint(4, 2), kdb.DPoint(11, 1)])
        self.assertEqual(set(project.parameters), {"x", "distance"})

    def test_gds_contains_zero_width_path_and_no_point_marker(self):
        with TemporaryDirectory() as directory:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(output=Path(directory) / str(live), live=live)
                    layer = project.add_layer("construction", comsol=False,
                                              gds_layer=21, gds_datatype=3)
                    position = Vertices([4, 7])
                    Point(project, layer=layer, position=position)
                    line = LineSegment(project, layer=layer, p1=(1, 2), p2=(4, 6))
                    project.build()
                    layout = kdb.Layout()
                    layout.read(str(project.gds_path))
                    shapes = layout.top_cell().shapes(layout.layer(21, 3))
                    self.assertEqual(shapes.size(), 1)
                    shape = next(shapes.each())
                    self.assertTrue(shape.is_path())
                    path = shape.path.to_dtype(layout.dbu)
                    self.assertEqual(path.width, 0)
                    self.assertEqual(list(path.each_point()),
                                     [kdb.DPoint(1, 2), kdb.DPoint(4, 6)])
                    self.assertAlmostEqual(path.length(), 5)

                    # A coordinate edit is seen at the next build, without a
                    # cached point/curve snapshot replacing its expressions.
                    line.p2 = position
                    project.build()
                    layout = kdb.Layout()
                    layout.read(str(project.gds_path))
                    paths = list(layout.top_cell().shapes(layout.layer(21, 3)).each())
                    self.assertEqual(paths[0].path.to_dtype(layout.dbu).bbox(),
                                     kdb.DBox(1, 2, 4, 7))

    def test_rotated_points_stay_points_and_lines_stay_paths(self):
        project = Project()
        layer = project.add_layer("construction", comsol=False, gds=False)
        point = Point(project, layer=layer, position=(2, 1))
        rotated_point = point.rotate(angle=90)
        actual = rotated_point.to_klayout()
        self.assertIsInstance(actual, kdb.DPoint)
        self.assertAlmostEqual(actual.x, -1)
        self.assertAlmostEqual(actual.y, 2)
        line = LineSegment(project, layer=layer, p1=(1, 0), p2=(3, 0))
        rotated_line = line.rotate(angle=90)
        path = rotated_line.to_klayout()
        self.assertIsInstance(path, kdb.DPath)
        self.assertEqual(path.width, 0)
        for actual, expected in zip(path.each_point(), ((0, 1), (0, 3))):
            self.assertAlmostEqual(actual.x, expected[0])
            self.assertAlmostEqual(actual.y, expected[1])

    def test_invalid_coordinates_and_degenerate_lines_are_not_registered(self):
        project = Project()
        layer = project.add_layer("construction", comsol=False, gds=False)
        invalid_positions = [(1,), (1, 2, 3), (float("nan"), 1), (1, float("inf")),
                             (Parameter(1, "angle", unit="deg"), 1),
                             Vertices([[0, 0], [1, 1]])]
        for position in invalid_positions:
            with self.subTest(position=position):
                with self.assertRaises(ValueError):
                    Point(project, layer=layer, position=position)
                with self.assertRaises(ValueError):
                    LineSegment(project, layer=layer, p1=position)
                with self.assertRaises(ValueError):
                    LineSegment(project, layer=layer, p2=position)
        with self.assertRaisesRegex(ValueError, "distinct"):
            LineSegment(project, layer=layer, p1=(1, 2), p2=(1, 2))
        with self.assertRaisesRegex(ValueError, "distinct"):
            LineSegment(project, layer=layer, p1=(1, 0),
                        p2=(Parameter(1000, "same_x", unit="nm"), 0))
        self.assertEqual(project.objects, [])

    def test_degenerate_parameter_edit_does_not_replace_previous_gds(self):
        with TemporaryDirectory() as directory:
            project = Project(output=Path(directory) / "line")
            layer = project.add_layer("construction", comsol=False)
            length = Parameter(4, "length", unit="um")
            LineSegment(project, layer=layer, p2=(length, 0))
            project.build()
            previous = project.gds_path.read_bytes()
            length.value = 0
            with self.assertRaisesRegex(ValueError, "distinct"):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), previous)
