"""Parametric geometry through real GDS and an offline COMSOL call recorder."""

from math import pi
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import klayout.db as kdb

from geompype import DependentParameter, Parameter, Project
from geompype.primitives import Square
from geompype.transforms import Rotate


def read_region(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    shapes = layout.top_cell().shapes(layout.layer(1, 0))
    return layout, kdb.Region(shapes)


class RecordedFeature:
    def __init__(self, tag, kind, events):
        self.tag, self.kind, self.events = tag, kind, events
        self.values = {}
        self.input = Mock()

    def label(self, name):
        self.name = name

    def set(self, key, value):
        self.values[key] = value
        self.events.append(("feature", self.tag, key, value))

    def selection(self, name):
        return self.input


class RecordedGeometry:
    def __init__(self, events):
        self.features = {}
        self.events = events
        self._current = ""

    def create(self, tag, kind):
        self.features[tag] = RecordedFeature(tag, kind, self.events)
        self._current = tag
        return self.features[tag]

    def current(self):
        return self._current

    def feature(self, tag=None):
        if tag is None:
            return SimpleNamespace(tags=lambda: list(self.features))
        return self.features[tag]


class TestParameterGeometry(unittest.TestCase):
    def test_mixed_units_inline_expressions_and_rotations_match_numeric_geometry(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "parametric")
            layer = project.add_layer("metal", comsol=False)
            width = Parameter(20, "width", unit="um")
            gap = Parameter(500, "gap", unit="nm")
            angle = Parameter(pi / 2, "angle", unit="rad")
            pitch = DependentParameter(width + 2 * gap, "pitch")
            square = Square(project, layer=layer, side=width,
                            position=(pitch, 3), base="corner", angle=angle)
            rotated = Rotate(square, angle=-angle, origin=(gap, pitch / 2), keep=True)
            self.assertIs(square.side, width)
            self.assertIs(square.position[0], pitch)
            self.assertIs(square.angle, angle)
            self.assertIs(rotated.origin[0], gap)

            cases = [(20, 500, pi / 2, 21, 0.5, 90),
                     (10, 1000, pi / 4, 12, 1, 45)]
            for index, (side, spacing_nm, theta, x, pivot_x, degrees) in enumerate(cases):
                with self.subTest(index=index):
                    width.value, gap.value, angle.value = side, spacing_nm, theta
                    with patch("geompype.project.get_client",
                               side_effect=AssertionError("Unexpected COMSOL connection")):
                        project.build()

                    numeric = Project(output=Path(folder) / f"numeric_{index}")
                    numeric_layer = numeric.add_layer("metal", comsol=False)
                    original = Square(numeric, layer=numeric_layer, side=side,
                                      position=(x, 3), base="corner", angle=degrees)
                    Rotate(original, angle=-degrees, origin=(pivot_x, x / 2), keep=True)
                    numeric.build()
                    actual_layout, actual = read_region(project)
                    expected_layout, expected = read_region(numeric)
                    self.assertEqual(actual_layout.dbu, expected_layout.dbu)
                    self.assertTrue((actual ^ expected).is_empty())
            self.assertIsNone(project.client)
            self.assertIsNone(project.model)
            self.assertIs(project.parameters["width"], width)
            self.assertIs(project.parameters["pitch"], pitch)

    def test_live_parameter_edits_take_effect_at_explicit_build(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "live", live=True)
            layer = project.add_layer("metal", comsol=False)
            width = Parameter(2, "width", unit="um")
            Square(project, layer=layer, side=width)
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 4)
            original_bytes = project.gds_path.read_bytes()
            width.value = 4
            self.assertEqual(project.gds_path.read_bytes(), original_bytes)
            project.build()
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 16)

    def test_invalid_dependency_value_preserves_previous_output(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "validation")
            layer = project.add_layer("metal", comsol=False)
            width = Parameter(20, "width", unit="um")
            gap = Parameter(2, "gap", unit="um")
            inner_width = DependentParameter(width - 2 * gap, "inner_width")
            Square(project, layer=layer, side=inner_width)
            project.build()
            original_bytes = project.gds_path.read_bytes()
            width.value = 3
            with self.assertRaises(ValueError):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), original_bytes)
            width.value = 30
            project.build()
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 26**2)

    def test_conflicting_names_are_rejected_before_overwriting_gds(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "duplicate")
            layer = project.add_layer("metal", comsol=False)
            width = Parameter(10, "width", unit="um")
            Square(project, layer=layer, side=width)
            project.build()
            original_bytes = project.gds_path.read_bytes()
            with self.assertRaises(ValueError):
                Square(project, layer=layer, side=Parameter(20, "width", unit="um"))
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), original_bytes)

    def test_native_comsol_features_keep_symbols_and_refresh_definitions(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "symbolic")
            layer = project.add_layer("metal", gds=False)
            width = Parameter(20, "width", unit="um", description="Conductor width")
            gap = Parameter(2, "gap", unit="um")
            angle = Parameter(pi / 4, "angle", unit="rad")
            pitch = DependentParameter(width + 2 * gap, "pitch")
            square = Square(project, layer=layer, side=width,
                            position=(pitch, -gap), angle=angle)
            rotated = Rotate(square, angle=-angle, origin=(gap, pitch / 2))

            events = []
            plane = RecordedGeometry(events)
            # This recorder checks parameter emission, not native entity ownership.
            project._layer_selections.clear()
            parameters = Mock()
            parameters.set.side_effect = lambda *args: events.append(("parameter", *args))
            java = SimpleNamespace(param=lambda: parameters, component=lambda tag: object())
            project.model = SimpleNamespace(java=java)
            project.geometry = RecordedGeometry(events)
            workplane = project.geometry.create('wp1', 'WorkPlane')
            workplane.geom = lambda: plane
            project.geometry.run = Mock()
            with patch("geompype.project.get_client",
                       side_effect=AssertionError("Unexpected COMSOL connection")), \
                    patch.object(project, "_save_comsol") as save:
                project.build()
                self.assertEqual(save.call_count, 1)
                first_parameter_calls = [event for event in events if event[0] == "parameter"]
                names = [event[1] for event in first_parameter_calls]
                self.assertLess(names.index("width"), names.index("pitch"))
                self.assertLess(names.index("gap"), names.index("pitch"))
                last_parameter = max(i for i, event in enumerate(events) if event[0] == "parameter")
                first_feature = min(i for i, event in enumerate(events) if event[0] == "feature")
                self.assertLess(last_parameter, first_feature)

                features = plane.features
                self.assertEqual(features[square.tag].values["size"], "width")
                self.assertEqual(features[square.tag].values["pos"][0], "pitch")
                self.assertIn("gap", features[square.tag].values["pos"][1])
                self.assertIn("angle", features[square.tag].values["rot"])
                self.assertIn("angle", features[rotated.tag].values["rot"])
                self.assertIn("pitch", features[rotated.tag].values["pos"][1])
                features[rotated.tag].input.set.assert_called_with([square.tag])

                events.clear()
                width.value = 30
                project.build()
                self.assertEqual(len(features), 2)
                self.assertEqual(save.call_count, 2)
                second_parameter_calls = [event for event in events if event[0] == "parameter"]
                width_call = next(event for event in second_parameter_calls if event[1] == "width")
                self.assertIn("[um]", width_call[2])
                self.assertEqual(float(width_call[2].split("[")[0]), 30)
                self.assertEqual(width_call[3], "Conductor width")
                pitch_call = next(event for event in second_parameter_calls if event[1] == "pitch")
                self.assertIn("width", pitch_call[2])
                self.assertIn("gap", pitch_call[2])
                self.assertEqual(features[square.tag].values["size"], "width")
                self.assertEqual(project.geometry.run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
