"""Square round trips through the real GDS writer and KLayout reader.

Run from the project root with: python -m unittest discover -s tests -v
COMSOL and Desktop applications are not used by this suite.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Project
from geompype.primitives import Square


def read_gds(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    return layout


class TestSquare(unittest.TestCase):
    def test_center_square_preserves_units_and_layer_on_disk(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "center", dbu=0.005)
            layer = project.add_layer("metal", comsol=False,
                                      gds_layer=17, gds_datatype=3)
            Square(project, layer=layer, side=20, position=(10, 5))
            project.build()

            layout = read_gds(project)
            self.assertAlmostEqual(layout.dbu, 0.005)
            self.assertEqual([(info.layer, info.datatype) for info in layout.layer_infos()],
                             [(17, 3)])
            cell = layout.top_cell()
            self.assertEqual(cell.name, "TOP")
            shapes = cell.shapes(layout.layer(17, 3))
            self.assertEqual(shapes.size(), 1)
            region = kdb.Region(shapes)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 400)
            self.assertEqual(region.bbox(), kdb.Box(0, -1000, 4000, 3000))

    def test_corner_origin_and_rotations(self):
        # The corner stays fixed under a 90-degree rotation. A 45-degree
        # centred square has the same area and a diagonal-sized bounding box.
        cases = [
            ("corner", 0, (10, 5, 30, 25)),
            ("corner", 90, (-10, 5, 10, 25)),
            ("center", 45, (-4.142135624, -9.142135624, 24.142135624, 19.142135624)),
        ]
        with TemporaryDirectory() as folder:
            for base, angle, expected in cases:
                with self.subTest(base=base, angle=angle):
                    project = Project(output=Path(folder) / f"{base}_{angle}")
                    layer = project.add_layer("metal", comsol=False)
                    Square(project, layer=layer, side=20, position=(10, 5),
                           base=base, angle=angle)
                    project.build()
                    layout = read_gds(project)
                    region = kdb.Region(layout.top_cell().shapes(layout.layer(1, 0)))
                    self.assertAlmostEqual(region.area() * layout.dbu**2, 400,
                                           delta=0.08)
                    bounds = region.bbox().to_dtype(layout.dbu)
                    for actual, target in zip(
                            (bounds.left, bounds.bottom, bounds.right, bounds.top), expected):
                        self.assertAlmostEqual(actual, target, delta=layout.dbu)

    def test_deferred_build_and_rebuild_do_not_duplicate_shapes(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "deferred", live=False)
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=10)
            self.assertFalse(project.gds_path.exists())
            self.assertIsNone(project.layout)

            project.build()
            project.build()
            layout = read_gds(project)
            self.assertEqual(layout.top_cell().shapes(layout.layer(1, 0)).size(), 1)

            square.side = 20
            project.build()
            layout = read_gds(project)
            shapes = layout.top_cell().shapes(layout.layer(1, 0))
            self.assertEqual(shapes.size(), 1)
            self.assertAlmostEqual(kdb.Region(shapes).area() * layout.dbu**2, 400)
            self.assertFalse(project.output.with_name("deferred.writing.gds").exists())

    def test_live_writes_each_square_immediately(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "live", live=True)
            layer = project.add_layer("metal", comsol=False)
            self.assertFalse(project.gds_path.exists())
            Square(project, layer=layer, side=10)
            self.assertTrue(project.gds_path.is_file())
            layout = read_gds(project)
            self.assertEqual(layout.top_cell().shapes(layout.layer(1, 0)).size(), 1)

            Square(project, layer=layer, side=20, position=(50, 0))
            layout = read_gds(project)
            shapes = layout.top_cell().shapes(layout.layer(1, 0))
            self.assertEqual(shapes.size(), 2)
            self.assertAlmostEqual(kdb.Region(shapes).area() * layout.dbu**2, 500)

    def test_disabled_gds_layer_is_excluded(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "layers")
            visible = project.add_layer("visible", comsol=False, gds_layer=7)
            hidden = project.add_layer("hidden", comsol=False, gds=False, gds_layer=8)
            Square(project, layer=visible, side=10)
            Square(project, layer=hidden, side=100)
            project.build()
            layout = read_gds(project)
            self.assertEqual([(info.layer, info.datatype) for info in layout.layer_infos()],
                             [(7, 0)])
            region = kdb.Region(layout.top_cell().shapes(layout.layer(7, 0)))
            self.assertAlmostEqual(region.area() * layout.dbu**2, 100)

            disabled = Project(output=Path(folder) / "disabled", live=True)
            layer = disabled.add_layer("off", comsol=False, gds=False)
            Square(disabled, layer=layer, side=10)
            self.assertFalse(disabled.gds_path.exists())
            self.assertIsNone(disabled.layout)

    def test_comsol_disabled_never_connects_or_creates_a_client(self):
        with TemporaryDirectory() as folder:
            with patch("geompype.project.get_client",
                       side_effect=AssertionError("Unexpected COMSOL connection")):
                project = Project(output=Path(folder) / "gds_only", live=True)
                layer = project.add_layer("metal", comsol=False)
                Square(project, layer=layer, side=10)
                project.build()
            self.assertIsNone(project.client)
            self.assertIsNone(project.model)
            self.assertIsNone(project.geometry)
            self.assertFalse(project.mph_path.exists())
            self.assertTrue(project.gds_path.is_file())

    def test_invalid_geometry_and_subgrid_square_are_rejected(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "invalid")
            layer = project.add_layer("metal", comsol=False)
            invalid = [
                {"side": 0}, {"side": -1}, {"side": float("inf")},
                {"side": float("nan")}, {"position": (0,)},
                {"position": (0, float("nan"))}, {"angle": float("inf")},
                {"base": "unknown"},
            ]
            for options in invalid:
                with self.subTest(options=options):
                    with self.assertRaises(ValueError):
                        Square(project, layer=layer, **({"side": 10} | options))
            self.assertEqual(project.objects, [])
            self.assertFalse(project.gds_path.exists())

            Square(project, layer=layer, side=0.0001)
            with self.assertRaisesRegex(ValueError, "GDS grid"):
                project.build()
            self.assertFalse(project.gds_path.exists())


if __name__ == "__main__":
    unittest.main()
