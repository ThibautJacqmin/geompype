"""Export grid policy, diagnostics and atomic failures through real GDS files."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import DependentParameter, Parameter, Point, Project, Square, round_nearest


class TestGrid(unittest.TestCase):
    def test_default_rounds_final_vertices_without_changing_design(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "round")
            layer = project.add_layer("metal", comsol=False)
            side = Parameter(3, "side", unit="nm")
            square = Square(project, layer=layer, side=side)
            self.assertIsNone(project.grid_report())
            project.build()
            layout = kdb.Layout()
            layout.read(str(project.gds_path))
            self.assertEqual(layout.top_cell().bbox(), kdb.Box(-2, -2, 2, 2))
            self.assertEqual(side.value, 3)
            self.assertAlmostEqual(square.to_klayout().bbox().width(), 0.003)
            report = project.grid_report()
            self.assertTrue(report["complete"])
            self.assertEqual(report["affected_objects"], [square.tag])
            self.assertAlmostEqual(report["max_coordinate_displacement_um"], 0.0005)
            self.assertEqual(report["objects"][0]["affected_vertices"], 4)
            report["objects"].clear()
            self.assertEqual(len(project.grid_report()["objects"]), 1)
            project.build()
            self.assertEqual(project.grid_report()["objects"][0]["vertices"], 4)

    def test_strict_failure_preserves_previous_gds_and_never_connects(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "strict", grid_policy="error")
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=1, base="corner")
            project.build()
            previous = project.gds_path.read_bytes()
            square.position = (0.0004, 0)
            project.add_layer("native", comsol=True, gds=False)
            with patch("geompype.project.get_client", side_effect=AssertionError("Connected")):
                with self.assertRaisesRegex(ValueError, "off the GDS grid"):
                    project.build()
            self.assertEqual(project.gds_path.read_bytes(), previous)
            self.assertFalse(project.grid_report()["complete"])
            self.assertEqual(project.grid_report()["affected_objects"], [square.tag])
            self.assertFalse(project.output.with_name("strict.writing.gds").exists())

    def test_strict_checks_final_consuming_transform_only(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "final", grid_policy="error")
            layer = project.add_layer("metal", comsol=False)
            source = Square(project, layer=layer, side=1, base="corner", position=(0.0004, 0))
            rotated = source.rotate(angle=180, origin=(0.0002, 0))
            project.build()
            self.assertEqual(project.layout.top_cell().bbox(), kdb.Box(-1000, -1000, 0, 0))
            self.assertEqual([entry["tag"] for entry in project.grid_report()["objects"]],
                             [rotated.tag])
            self.assertEqual(project.grid_report()["affected_objects"], [])

    def test_strict_accepts_numerical_noise_but_rejects_arbitrary_rotation(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "rotate", grid_policy="error")
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=20, position=(1000, -2000))
            rotation = square.rotate(angle=90, origin=(1000, -2000))
            project.build()
            self.assertEqual(project.grid_report()["affected_objects"], [])
            rotation.angle = 30
            with self.assertRaisesRegex(ValueError, "off the GDS grid"):
                project.build()

    def test_finer_dbu_can_represent_an_off_grid_design(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "fine", grid_policy="error")
            layer = project.add_layer("metal", comsol=False)
            Square(project, layer=layer, side=0.003)
            with self.assertRaisesRegex(ValueError, "off the GDS grid"):
                project.build()
            project.dbu = 0.0005
            project.build()
            self.assertEqual(project.layout.top_cell().bbox(), kdb.Box(-3, -3, 3, 3))
            self.assertEqual(project.grid_report()["dbu_um"], 0.0005)
            self.assertEqual(project.grid_report()["affected_objects"], [])

    def test_points_and_disabled_layers_are_not_grid_checked(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "points", grid_policy="error")
            layer = project.add_layer("coordinates", comsol=False)
            hidden = project.add_layer("hidden", comsol=False, gds=False)
            point = Point(project, layer=layer, position=(0.0004, 0.0002))
            Square(project, layer=hidden, side=0.003)
            project.build()
            self.assertEqual(point.to_klayout(), kdb.DPoint(0.0004, 0.0002))
            self.assertEqual(project.grid_report()["objects"], [])
            self.assertEqual(project.layout.top_cell().shapes(project.layout.layer(1, 0)).size(), 0)

    def test_collection_export_reports_one_object_and_preserves_dimensions(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "collection")
            layer = project.add_layer("mixed", comsol=False)
            obj = Square(project, layer=layer, side=1)
            polygon = kdb.DPolygon(kdb.DBox(0, 0, 1, 1))
            path = kdb.DPath([kdb.DPoint(2, 0), kdb.DPoint(2.0003, 0.0001),
                              kdb.DPoint(3, 0)], 0)
            with patch.object(obj, "to_klayout", return_value=(polygon, path, kdb.DPoint(0.0002, 0))):
                project.build()
            shapes = list(project.layout.top_cell().shapes(project.layout.layer(1, 0)).each())
            self.assertEqual(sum(shape.is_polygon() for shape in shapes), 1)
            self.assertEqual(sum(shape.is_path() for shape in shapes), 1)
            entry, = project.grid_report()["objects"]
            self.assertEqual(entry["shapes"], 2)
            self.assertEqual(entry["vertices"], 7)
            self.assertEqual(entry["collapsed_vertices"], 1)
            exported_path = next(shape.path for shape in shapes if shape.is_path())
            self.assertEqual(exported_path.width, 0)
            self.assertEqual(list(exported_path.each_point()), [kdb.Point(2000, 0), kdb.Point(3000, 0)])

    def test_grid_collapse_and_coordinate_overflow_are_errors(self):
        with TemporaryDirectory() as folder:
            for side, position, message in [(0.0001, (0, 0), "too small"),
                                             (1, (3e6, 0), "coordinate range")]:
                with self.subTest(message=message):
                    project = Project(output=Path(folder) / message)
                    layer = project.add_layer("metal", comsol=False)
                    Square(project, layer=layer, side=side, position=position)
                    with self.assertRaisesRegex(ValueError, message):
                        project.build()
                    self.assertFalse(project.gds_path.exists())
                    self.assertFalse(project.grid_report()["complete"])

    def test_invalid_settings_at_construction_and_rebuild(self):
        for value in [0, -1, float("nan"), float("inf"), True, None]:
            with self.subTest(dbu=value), self.assertRaisesRegex(ValueError, "dbu"):
                Project(dbu=value)
        for value in ["none", "ROUND", False, None, []]:
            with self.subTest(policy=value), self.assertRaisesRegex(ValueError, "grid_policy"):
                Project(grid_policy=value)
        project = Project()
        for name, value in [("dbu", -1), ("grid_policy", "none")]:
            old = getattr(project, name)
            setattr(project, name, value)
            with self.assertRaisesRegex(ValueError, name):
                project.build()
            setattr(project, name, old)

    def test_explicit_snapped_parameter_remains_live(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "parameter", grid_policy="error")
            layer = project.add_layer("metal", comsol=False)
            grid = Parameter(1, "design_grid", unit="nm")
            requested = Parameter(100.4, "requested", unit="nm")
            snapped = DependentParameter(round_nearest(requested/grid)*grid, "snapped")
            Square(project, layer=layer, side=snapped, base="corner")
            project.build()
            self.assertEqual(project.layout.top_cell().bbox(), kdb.Box(0, 0, 100, 100))
            self.assertEqual(requested.value, 100.4)
            requested.value = 101.6
            project.build()
            self.assertEqual(project.layout.top_cell().bbox(), kdb.Box(0, 0, 102, 102))
            self.assertIn("requested", snapped.definition)
            self.assertEqual(set(project.parameters), {"design_grid", "requested", "snapped"})
