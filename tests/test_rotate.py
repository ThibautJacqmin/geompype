"""Rotation geometry and object history, checked through real GDS files."""

from math import sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import Project
from geompype.primitives import Square
from geompype.transforms import Rotate


def read_layer(project, layer=1, datatype=0):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    shapes = layout.top_cell().shapes(layout.layer(layer, datatype))
    return layout, shapes, kdb.Region(shapes)


class TestRotate(unittest.TestCase):
    def assert_polygon(self, region, coordinates, dbu):
        expected = kdb.DPolygon([kdb.DPoint(x, y) for x, y in coordinates])
        expected = kdb.Region(expected.to_itype(dbu))
        self.assertTrue((region ^ expected).is_empty(),
                        f"Unexpected GDS polygon: {region}")

    def test_45_degrees_about_nonzero_origin(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "pivot")
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=4, position=(10, 5))
            Rotate(square, angle=45, origin=(2, 3))
            project.build()

            layout, shapes, region = read_layer(project)
            self.assertEqual(shapes.size(), 1)
            q = sqrt(2)
            self.assert_polygon(region, [(2 + 6/q, 3 + 6/q),
                                         (2 + 10/q, 3 + 10/q),
                                         (2 + 6/q, 3 + 14/q),
                                         (2 + 2/q, 3 + 10/q)], layout.dbu)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 16, delta=0.01)

    def test_signed_90_degrees_about_global_origin(self):
        cases = [(90, (-6, 9, -4, 11)), (-90, (4, -11, 6, -9))]
        with TemporaryDirectory() as folder:
            for angle, bounds in cases:
                with self.subTest(angle=angle):
                    project = Project(output=Path(folder) / f"signed_{angle}")
                    layer = project.add_layer("metal", comsol=False)
                    square = Square(project, layer=layer, side=2, position=(10, 5))
                    Rotate(square, angle=angle)
                    project.build()
                    layout, shapes, region = read_layer(project)
                    left, bottom, right, top = bounds
                    self.assertEqual(shapes.size(), 1)
                    self.assert_polygon(region, [(left, bottom), (right, bottom),
                                                 (right, top), (left, top)], layout.dbu)

    def test_method_returns_new_object_and_preserves_source_geometry(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "method")
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=4, position=(3, 2),
                            base="corner", angle=15)
            original = square.to_klayout()
            rotated = square.rotate(angle=45, origin=(3, 2))
            self.assertIsInstance(rotated, Rotate)
            self.assertIsNot(rotated, square)
            self.assertIs(rotated.target, square)
            self.assertIsInstance(rotated.to_klayout(), kdb.DPolygon)
            self.assertEqual(square.angle, 15)
            self.assertEqual(square.position, (3, 2))
            self.assertEqual(square.to_klayout(), original)
            project.build()

    def test_chained_rotations_round_only_final_geometry(self):
        # Rounding the 45-degree intermediate result to this coarse grid
        # changes the restored square, even though the two angles cancel.
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "chain", dbu=1)
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=4, position=(0.2, 0.3))
            rotated = Rotate(square, angle=45)
            Rotate(rotated, angle=-45)
            project.build()
            layout, shapes, region = read_layer(project)
            self.assertEqual(shapes.size(), 1)
            self.assert_polygon(region, [(-1.8, -1.7), (2.2, -1.7),
                                         (2.2, 2.3), (-1.8, 2.3)], layout.dbu)

    def test_keep_input_and_branch_from_preserved_source(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "keep")
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=2, position=(10, 0))
            Rotate(square, angle=90, keep=True)
            project.build()
            layout, shapes, region = read_layer(project)
            self.assertEqual(shapes.size(), 2)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 8)

            # The first transform preserved its input, so the second may use it.
            Rotate(square, angle=180)
            project.build()
            layout, shapes, region = read_layer(project)
            self.assertEqual(shapes.size(), 2)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 8)
            expected = kdb.Region(kdb.Box(-1000, 9000, 1000, 11000))
            expected += kdb.Region(kdb.Box(-11000, -1000, -9000, 1000))
            self.assertTrue((region ^ expected).is_empty())

    def test_live_deferred_rebuild_and_parameter_changes(self):
        with TemporaryDirectory() as folder:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(output=Path(folder) / f"updates_{live}", live=live)
                    layer = project.add_layer("metal", comsol=False)
                    square = Square(project, layer=layer, side=2, position=(10, 0))
                    rotated = Rotate(square, angle=90)
                    if live:
                        layout, shapes, region = read_layer(project)
                        self.assertEqual(shapes.size(), 1)
                        self.assert_polygon(region, [(-1, 9), (1, 9), (1, 11), (-1, 11)],
                                            layout.dbu)
                    else:
                        self.assertFalse(project.gds_path.exists())

                    project.build()
                    project.build()
                    layout, shapes, region = read_layer(project)
                    self.assertEqual(shapes.size(), 1)
                    self.assert_polygon(region, [(-1, 9), (1, 9), (1, 11), (-1, 11)],
                                        layout.dbu)

                    square.side = 4
                    square.position = (8, 2)
                    rotated.angle = -90
                    rotated.origin = (1, 1)
                    project.build()
                    layout, shapes, region = read_layer(project)
                    self.assertEqual(shapes.size(), 1)
                    self.assert_polygon(region, [(0, -8), (4, -8), (4, -4), (0, -4)],
                                        layout.dbu)

    def test_layers_and_disabled_gds_are_inherited(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "layers")
            metal = project.add_layer("metal", comsol=False, gds_layer=17, gds_datatype=3)
            hidden = project.add_layer("hidden", comsol=False, gds=False, gds_layer=18)
            square = Square(project, layer=metal, side=2, position=(10, 0))
            rotated = Rotate(square, angle=90)
            Rotate(Square(project, layer=hidden, side=100), angle=45)
            self.assertIs(rotated.project, project)
            self.assertIs(rotated.layer, metal)
            project.build()
            layout, shapes, region = read_layer(project, 17, 3)
            self.assertEqual([(info.layer, info.datatype) for info in layout.layer_infos()],
                             [(17, 3)])
            self.assertEqual(shapes.size(), 1)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 4)
            self.assertIsNone(project.client)

            disabled = Project(output=Path(folder) / "disabled", live=True)
            layer = disabled.add_layer("off", comsol=False, gds=False)
            Rotate(Square(disabled, layer=layer, side=10), angle=45)
            self.assertFalse(disabled.gds_path.exists())
            self.assertIsNone(disabled.layout)

    def test_invalid_parameters_do_not_register_or_change_output(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "invalid", live=True)
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=2)
            original_gds = project.gds_path.read_bytes()
            invalid = [{"angle": float("nan")}, {"angle": float("inf")},
                       {"angle": "bad"}, {"origin": (0,)}, {"origin": (0, 1, 2)},
                       {"origin": (0, float("inf"))}, {"origin": (float("nan"), 0)},
                       {"origin": ("bad", 0)}, {"keep": 1}, {"keep": "yes"}]
            for options in invalid:
                with self.subTest(options=options):
                    with self.assertRaises(ValueError):
                        Rotate(square, **({"angle": 45} | options))
                    self.assertEqual(project.objects, [square])
                    self.assertEqual(project.gds_path.read_bytes(), original_gds)

            for target in (None, object(), layer, project):
                with self.subTest(target=type(target).__name__):
                    with self.assertRaises((TypeError, ValueError)):
                        Rotate(target, angle=45)
            self.assertEqual(project.objects, [square])

    def test_consumed_source_is_rejected_before_registration(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "consumed", live=True)
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=2)
            rotated = Rotate(square, angle=45)
            original_gds = project.gds_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "consum|keep"):
                Rotate(square, angle=90)
            self.assertEqual(project.objects, [square, rotated])
            self.assertEqual(project.gds_path.read_bytes(), original_gds)

    def test_invalid_parameter_update_preserves_previous_file(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "invalid_update")
            layer = project.add_layer("metal", comsol=False)
            rotated = Rotate(Square(project, layer=layer, side=2), angle=45)
            project.build()
            original_gds = project.gds_path.read_bytes()
            rotated.angle = float("nan")
            with self.assertRaises(ValueError):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), original_gds)


if __name__ == "__main__":
    unittest.main()
