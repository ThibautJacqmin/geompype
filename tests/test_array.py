"""Linear/rectangular arrays retain geometry, dimensions and parameter updates."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import Project, Parameter, DependentParameter, Vertices
from geompype.primitives import Square, Point, LineSegment, Rectangle
from geompype.transforms import Array, Rotate
from test_parameter_geometry import RecordedGeometry


def read_shapes(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    return layout, list(layout.top_cell().shapes(layout.layer(1, 0)).each())


def items(geometry):
    return geometry if isinstance(geometry, tuple) else (geometry,)


class TestArray(unittest.TestCase):
    def test_exclusions_skip_sites_without_cutting_overlapping_survivors(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/"overlapping")
            layer = project.add_layer("metal", comsol=False)
            source = Rectangle(project, layer=layer, size=(4, 2))
            array = source.array(size=4, displacement=(1, 0), exclude=[1])
            shapes = items(array.to_klayout())
            self.assertEqual([shape.bbox().center().x for shape in shapes], [0, 2, 3])
            self.assertEqual([shape.area() for shape in shapes], [8, 8, 8])
            project.build()
            layout, shapes = read_shapes(project)
            occupied = kdb.Region()
            for shape in shapes:
                occupied.insert(shape.polygon)
            self.assertAlmostEqual(occupied.merged().area()*layout.dbu**2, 14)
            self.assertEqual(project._final_objects(project.objects), [array])

    def test_rectangular_exclusions_and_parameter_rebuilds_preserve_grid_sites(self):
        with TemporaryDirectory() as folder:
            for live in (False, True):
                project = Project(output=Path(folder)/str(live), live=live)
                layer = project.add_layer("metal", comsol=False)
                nx = Parameter(3, "nx")
                pitch = Parameter(5, "pitch", unit="um")
                source = Square(project, layer=layer, side=2)
                supplied = [[0, 0], [1, 1], [1, 1]]
                array = Array(source, size=(nx, 2), displacement=(pitch, 8), exclude=supplied)
                supplied[0][0] = 2  # Constructor retains an independent immutable snapshot.
                project.build()
                _, shapes = read_shapes(project)
                self.assertEqual({(s.dbbox().center().x, s.dbbox().center().y) for s in shapes},
                                 {(5, 0), (10, 0), (0, 8), (10, 8)})
                nx.value, pitch.value = 4, 6
                project.build()
                _, shapes = read_shapes(project)
                self.assertEqual({(s.dbbox().center().x, s.dbbox().center().y) for s in shapes},
                                 {(6, 0), (12, 0), (18, 0), (0, 8), (12, 8), (18, 8)})
                previous = project.gds_path.read_bytes()
                nx.value = 1
                with self.assertRaisesRegex(ValueError, "outside"):
                    project.build()
                self.assertEqual(project.gds_path.read_bytes(), previous)
                nx.value = 3
                array.exclude = ()
                project.build()
                self.assertEqual(len(read_shapes(project)[1]), 6)

    def test_exclusions_apply_to_every_nested_input_and_preserve_geometry_types(self):
        project = Project()
        layer = project.add_layer("mixed", comsol=False, gds=False)
        sources = (Point(project, layer=layer, position=(0, 0)),
                   LineSegment(project, layer=layer, p1=(0, 2), p2=(1, 2)),
                   Square(project, layer=layer, side=1, position=(0, 4)))
        inner = Array(sources, size=2, displacement=(2, 0))
        outer = Array(inner, size=(2, 2), displacement=(10, 20), exclude=[(0, 0), (1, 1)])
        geometry = items(outer.to_klayout())
        self.assertEqual([type(g) for g in geometry], [kdb.DPoint, kdb.DPath, kdb.DPolygon]*4)
        self.assertEqual({(g.x, g.y) for g in geometry if isinstance(g, kdb.DPoint)},
                         {(10, 0), (12, 0), (0, 20), (2, 20)})

    def test_excluded_native_translations_keep_parameter_expressions(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        count = Parameter(4, "count")
        pitch = Parameter(5, "pitch", unit="um")
        square = Square(project, layer=layer, side=2)
        array = Array(square, size=count, displacement=(pitch, -pitch), exclude=[0, 2])
        plane = RecordedGeometry([])
        for _ in range(2):
            array.to_comsol(plane, array.tag)
        feature = plane.features[array.tag]
        self.assertEqual(feature.kind, "Move")
        self.assertEqual(feature.values["displx"], ["1*(pitch)", "3*(pitch)"])
        self.assertTrue(all("pitch" in value for value in feature.values["disply"]))
        self.assertNotIn("keep", feature.values)
        self.assertEqual(set(project.parameters), {"pitch", "count"})
        self.assertEqual(len(plane.features), 1)

    def test_invalid_exclusions_do_not_register_or_replace_output(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/"invalid_exclude")
            layer = project.add_layer("metal", comsol=False)
            source = Square(project, layer=layer, side=2)
            project.build()
            previous = project.gds_path.read_bytes()
            for size, excluded in ((3, [-1]), (3, [3]), (3, [True]), (3, [1.5]),
                                   (3, [(1, 1)]), (3, [0, 1, 2]), (3, 1),
                                   ((2, 2), [0]), ((2, 2), [(0,)]),
                                   ((2, 2), [(0, 2)]), ((2, 2), [(1, False)]),
                                   ((1, 1), [(0, 0)]), (3, [Parameter(1, "index")])):
                with self.subTest(size=size, exclude=excluded):
                    with self.assertRaises(ValueError):
                        Array(source, size=size, exclude=excluded)
                    self.assertEqual(project.objects, [source])
                    self.assertEqual(project.gds_path.read_bytes(), previous)

    def test_linear_counts_include_original_and_consume_source(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "linear")
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=2, position=(1, 2))
            array = Array(square, size=3, displacement=(5, -3))
            project.build()
            layout, shapes = read_shapes(project)
            self.assertEqual(len(shapes), 3)
            self.assertEqual({(s.dbbox().center().x, s.dbbox().center().y) for s in shapes},
                             {(1, 2), (6, -1), (11, -4)})
            self.assertEqual(sum(s.polygon.area() for s in shapes)*layout.dbu**2, 12)
            self.assertEqual(project._final_objects(project.objects), [array])
            with self.assertRaisesRegex(ValueError, "consum|keep"):
                Array(square, size=2)

    def test_rectangular_parameter_updates_and_vertices_in_both_build_modes(self):
        with TemporaryDirectory() as folder:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(output=Path(folder) / f"rect_{live}", live=live)
                    layer = project.add_layer("metal", comsol=False)
                    nx = Parameter(2, "nx")
                    ny = DependentParameter(nx + 1, "ny")
                    pitch = Parameter(5000, "pitch", unit="nm")
                    step = Vertices((pitch, 2*pitch))
                    array = Array(Square(project, layer=layer, side=2),
                                  size=(nx, ny), displacement=step)
                    project.build()
                    layout, shapes = read_shapes(project)
                    self.assertEqual(len(shapes), 6)
                    self.assertEqual({(s.dbbox().center().x, s.dbbox().center().y) for s in shapes},
                                     {(x, y) for x in (0, 5) for y in (0, 10, 20)})
                    nx.value = 3
                    pitch.value = 6000
                    project.build()
                    project.build()
                    layout, shapes = read_shapes(project)
                    self.assertEqual(len(shapes), 12)
                    self.assertEqual({(s.dbbox().center().x, s.dbbox().center().y) for s in shapes},
                                     {(x, y) for x in (0, 6, 12) for y in (0, 12, 24, 36)})
                    # A size change can switch the same feature to a linear array.
                    array.size = 2
                    step[0] = step[0] + (1, -2)
                    project.build()
                    layout, shapes = read_shapes(project)
                    self.assertEqual(len(shapes), 2)
                    self.assertEqual({(s.dbbox().center().x, s.dbbox().center().y) for s in shapes},
                                     {(0, 0), (7, 10)})

    def test_points_curves_and_shapes_survive_a_mixed_array_then_rotation(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "mixed")
            layer = project.add_layer("metal", comsol=False)
            source = [Square(project, layer=layer, side=1, position=(2, 1)),
                      Point(project, layer=layer, position=(0, 0)),
                      LineSegment(project, layer=layer, p1=(0, 2), p2=(1, 2))]
            array = Array(source, size=2, displacement=(10, 0))
            result = Rotate(array, angle=90)
            geometry = items(result.to_klayout())
            self.assertEqual(sum(isinstance(g, kdb.DPoint) for g in geometry), 2)
            self.assertEqual(sum(isinstance(g, kdb.DPath) for g in geometry), 2)
            self.assertEqual(sum(isinstance(g, kdb.DPolygon) for g in geometry), 2)
            self.assertEqual({(round(g.x, 10), round(g.y, 10))
                              for g in geometry if isinstance(g, kdb.DPoint)}, {(0, 0), (0, 10)})
            paths = [g for g in geometry if isinstance(g, kdb.DPath)]
            self.assertTrue(all(g.width == 0 for g in paths))
            self.assertEqual({tuple((round(p.x, 10), round(p.y, 10)) for p in g.each_point())
                              for g in paths}, {((-2, 0), (-2, 1)), ((-2, 10), (-2, 11))})
            project.build()
            _, shapes = read_shapes(project)
            # KLayout may read axis-aligned polygon records as Box objects.
            self.assertEqual(sum(s.is_polygon() or s.is_box() for s in shapes), 2)
            self.assertEqual(sum(s.is_path() for s in shapes), 2)
            self.assertEqual(len(shapes), 4)  # Points do not create GDS markers.

    def test_single_copy_and_nested_array_round_only_at_export(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "nested", dbu=0.001)
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=2)
            first = Array(square, size=1, displacement=(0.0004, 0))
            self.assertIsInstance(first.to_klayout(), kdb.DPolygon)
            second = Array(first, size=3, displacement=(0.0004, 0))
            third = Array(second, size=(1, 2), displacement=(0, 5))
            floating = items(third.to_klayout())
            self.assertEqual(len(floating), 6)
            self.assertAlmostEqual(max(g.bbox().center().x for g in floating), 0.0008)
            project.build()
            _, shapes = read_shapes(project)
            self.assertEqual(len(shapes), 6)
            self.assertAlmostEqual(max(s.dbbox().center().x for s in shapes), 0.001)

    def test_invalid_count_or_displacement_preserves_existing_output(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "invalid")
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=2)
            project.build()
            previous = project.gds_path.read_bytes()
            for size in (0, -1, 2.5, True, (), (1,), (1, 2, 3), (1, 0),
                         float("nan"), Parameter(2, "length_count", unit="um")):
                with self.subTest(size=size):
                    with self.assertRaises((TypeError, ValueError)):
                        Array(square, size=size)
                    self.assertEqual(project.objects, [square])
                    self.assertEqual(project.gds_path.read_bytes(), previous)
            for displacement in ((0,), (0, 1, 2), (float("inf"), 0)):
                with self.subTest(displacement=displacement):
                    with self.assertRaises((TypeError, ValueError)):
                        Array(square, size=2, displacement=displacement)
                    self.assertEqual(project.objects, [square])
            count = Parameter(2, "count")
            Array(square, size=count, displacement=(5, 0))
            project.build()
            previous = project.gds_path.read_bytes()
            count.value = 1.5
            with self.assertRaisesRegex(ValueError, "integer"):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
