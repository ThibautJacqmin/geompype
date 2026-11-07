"""Vertices stay parametric when used as positions and transformation origins."""

from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from geompype import DependentParameter, Parameter, Project, Rotate, Square, Vertices
from test_parameter_geometry import RecordedGeometry, read_region


class TestVerticesGeometry(unittest.TestCase):
    def test_plain_vertices_example_runs_twice_offline(self):
        script = Path(__file__).resolve().parents[1] / 'examples' / "example_vertices.py"
        original_init, original_add_layer = Project.__init__, Project.add_layer
        with TemporaryDirectory() as folder:
            def offline_init(project, **kwargs):
                kwargs["output"] = Path(folder) / "example_vertices"
                original_init(project, **kwargs)

            def offline_layer(project, name, **kwargs):
                kwargs["comsol"] = False
                return original_add_layer(project, name, **kwargs)

            with patch.object(Project, "__init__", offline_init), \
                    patch.object(Project, "add_layer", offline_layer), \
                    patch.object(Project, "show") as show, \
                    patch("geompype.project.get_client", side_effect=AssertionError("COMSOL connection")):
                for _ in range(2):
                    namespace = runpy.run_path(str(script))
                    project = namespace["project"]
                    self.assertEqual(len(project.objects), 4)
                    layout, region = read_region(project)
                    self.assertAlmostEqual(region.area() * layout.dbu**2, 64, delta=0.01)
                    self.assertEqual(namespace["centres"].value, [[0.5, 0], [20.5, 0], [40.5, 20]])
                    namespace["pitch"].value = 30
                    project.build()
                    self.assertEqual(namespace["square"].position.value, [[60.5, 30]])
                self.assertEqual(show.call_count, 2)

    def test_coordinate_and_parameter_edits_match_numeric_gds(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "vertices")
            layer = project.add_layer("metal", comsol=False)
            x = Parameter(10, "xpos", unit="um")
            dy = Parameter(500, "dy", unit="nm")
            pitch = DependentParameter(2 * x, "pitch")
            position = Vertices([pitch, dy])
            origin = Vertices([1, 2])
            square = Square(project, layer=layer, side=4, position=position, angle=30)
            rotated = Rotate(square, angle=45, origin=origin, keep=True)
            self.assertIs(square.position, position)
            self.assertIs(rotated.origin, origin)
            for index, (x_value, dy_value, origin_y) in enumerate([(10, 500, 2), (20, 1000, 3)]):
                x.value, dy.value = x_value, dy_value
                origin[0, 1] = origin_y
                with patch("geompype.project.get_client",
                           side_effect=AssertionError("Unexpected COMSOL connection")):
                    project.build()
                numeric = Project(output=Path(folder) / f"numeric_{index}")
                numeric_layer = numeric.add_layer("metal", comsol=False)
                source = Square(numeric, layer=numeric_layer, side=4,
                                position=(2*x_value, dy_value/1000), angle=30)
                Rotate(source, angle=45, origin=(1, origin_y), keep=True)
                numeric.build()
                layout, actual = read_region(project)
                expected_layout, expected = read_region(numeric)
                self.assertTrue((actual ^ expected).is_empty())
                self.assertEqual(layout.dbu, expected_layout.dbu)
            self.assertEqual(set(project.parameters), {"xpos", "dy", "pitch"})
            self.assertIsNone(project.client)

    def test_iteration_and_subpoints_make_separate_shapes_without_freezing_parameters(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "points")
            layer = project.add_layer("metal", comsol=False)
            pitch = Parameter(10, "pitch", unit="um")
            centres = Vertices([[0, 0], [1, 0], [2, 0]], pitch)
            squares = [Square(project, layer=layer, side=2, position=point)
                       for point in centres]
            project.build()
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area()*layout.dbu**2, 12)
            self.assertAlmostEqual(region.bbox().right*layout.dbu, 21)
            pitch.value = 20
            project.build()
            layout, region = read_region(project)
            self.assertAlmostEqual(region.bbox().right*layout.dbu, 41)
            self.assertEqual(len(squares), 3)
            self.assertIs(project.parameters["pitch"], pitch)

    def test_geometry_requires_one_point_before_registration_and_preserves_output(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "invalid", live=True)
            layer = project.add_layer("metal", comsol=False)
            square = Square(project, layer=layer, side=2)
            original = project.gds_path.read_bytes()
            for points in (Vertices([]), Vertices([[0, 0], [1, 1]])):
                with self.subTest(count=len(points)):
                    with self.assertRaises(ValueError):
                        Square(project, layer=layer, side=2, position=points)
                    with self.assertRaises(ValueError):
                        Rotate(square, angle=45, origin=points)
                    self.assertEqual(project.objects, [square])
                    self.assertEqual(project.gds_path.read_bytes(), original)
            square.position = Vertices([[0, 0], [1, 1]])
            with self.assertRaises(ValueError):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), original)

    def test_dependency_failure_does_not_overwrite_an_existing_gds(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "invalid_dependency")
            layer = project.add_layer("metal", comsol=False)
            divisor = Parameter(2, "divisor")
            position = Vertices([10/divisor, 0])
            Square(project, layer=layer, side=2, position=position)
            project.build()
            original = project.gds_path.read_bytes()
            divisor.value = 0
            with self.assertRaises((ValueError, ZeroDivisionError)):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), original)

    def test_comsol_recorder_receives_all_dependencies_and_current_coordinate_expressions(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "symbolic")
            layer = project.add_layer("metal", gds=False)
            pitch = Parameter(10, "pitch", unit="um")
            gap = Parameter(500, "gap", unit="nm")
            count = Parameter(2, "count")
            position = Vertices([count, 0], pitch) + Vertices([gap, 1])
            origin = Vertices([gap, count], unit="nm")
            square = Square(project, layer=layer, side=2, position=position)
            rotated = Rotate(square, angle=90, origin=origin)
            events = []
            plane = RecordedGeometry(events)
            # Native automatic layer selections are covered by test_comsol_layers.
            project._layer_selections.clear()
            params = Mock()
            params.set.side_effect = lambda *args: events.append(("parameter", *args))
            project.model = SimpleNamespace(java=SimpleNamespace(
                param=lambda: params, component=lambda tag: object()))
            project.geometry = RecordedGeometry(events)
            workplane = project.geometry.create('wp1', 'WorkPlane')
            workplane.geom = lambda: plane
            project.geometry.run = Mock()
            with patch.object(project, "_save_comsol"), \
                    patch("geompype.project.get_client",
                          side_effect=AssertionError("Unexpected COMSOL connection")):
                project.build()
                self.assertEqual(set(project.parameters), {"pitch", "gap", "count"})
                named = {event[1] for event in events if event[0] == "parameter"}
                self.assertEqual(named, {"pitch", "gap", "count"})
                self.assertEqual(plane.features[square.tag].values["pos"], position.to_comsol()[0])
                self.assertEqual(plane.features[rotated.tag].values["pos"], origin.to_comsol()[0])
                self.assertIn("pitch", plane.features[square.tag].values["pos"][0])
                self.assertIn("gap", plane.features[square.tag].values["pos"][0])
                self.assertIn("[nm]", plane.features[rotated.tag].values["pos"][1])
                origin[0, 1] = gap
                project.build()
                self.assertEqual(plane.features[rotated.tag].values["pos"][1], "gap")
                self.assertEqual(len(plane.features), 2)


if __name__ == "__main__":
    unittest.main()
