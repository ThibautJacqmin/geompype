"""Bulk parameter definitions from mappings and flat YAML files."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import klayout.db as kdb
import yaml

from geompype import ComsolParameter, DependentParameter, Parameter, Project, Rectangle
from geompype.parameters import evaluate
from test_parameter_geometry import RecordedGeometry, read_region


class TestParameterMapping(unittest.TestCase):
    def test_named_sequences_preserve_identity_dependencies_and_repeated_objects(self):
        for sequence_type in (list, tuple):
            with self.subTest(sequence_type=sequence_type.__name__):
                width = Parameter(12, "width", unit="um")
                pitch = DependentParameter(2 * width, "pitch")
                native = ComsolParameter("3[K]", "temperature")
                source = sequence_type((pitch, native, pitch))
                with patch("geompype.project.get_client") as connect:
                    project = Project(live=True)
                    with patch.object(project, "build") as build:
                        values = project.add_parameter(source)
                        self.assertEqual(list(values), ["pitch", "temperature"])
                        self.assertIs(values["pitch"], pitch)
                        self.assertIs(values["temperature"], native)
                        self.assertIs(project.parameters["width"], width)
                        self.assertEqual(list(project.parameters),
                                         ["width", "pitch", "temperature"])
                        self.assertEqual(project.add_parameter(source), values)
                        self.assertEqual(project.add_parameter(sequence_type()), {})
                        self.assertEqual(len(source), 3)
                        width.value = 17
                        self.assertEqual(values["pitch"].value, 34)
                        build.assert_not_called()
                    connect.assert_not_called()

    def test_unnamed_sequence_entries_are_rejected_without_partial_registration(self):
        valid = Parameter(2, "new_value")
        for sequence_type in (list, tuple):
            for invalid in (2, "3um", True, None, [], {}, valid * 2):
                with self.subTest(sequence_type=sequence_type.__name__, invalid=invalid):
                    project = Project()
                    existing = project.add_parameter(Parameter(1, "existing"))
                    before = project.parameters
                    with self.assertRaises(TypeError):
                        project.add_parameter(sequence_type((valid, invalid)))
                    self.assertEqual(project.parameters, before)
                    self.assertIs(project.parameters["existing"], existing)

    def test_sequence_name_conflicts_are_atomic_even_before_dictionary_conversion(self):
        project = Project()
        layer = project.add_layer("shape", comsol=False)
        width = Parameter(8, "width", unit="um")
        Rectangle(project, layer=layer, size=(width, 3))
        native = project.add_parameter(ComsolParameter("2[K]", "temperature"))
        before = project.parameters
        valid = Parameter(1, "valid_first")
        conflicts = [
            [valid, Parameter(9, "width", unit="um")],
            [valid, ComsolParameter("3[K]", "temperature")],
            [valid, DependentParameter(Parameter(2, "width", unit="um") * 2, "pitch")],
            [valid, Parameter(3, "duplicate"), Parameter(3, "duplicate")],
            [valid, Parameter(3, "duplicate"), ComsolParameter("3[K]", "duplicate")],
        ]
        for sequence_type in (list, tuple):
            for batch in conflicts:
                with self.subTest(sequence_type=sequence_type.__name__, batch=batch):
                    with self.assertRaises(ValueError):
                        project.add_parameter(sequence_type(batch))
                    self.assertEqual(project.parameters, before)
        self.assertIs(project.parameters["width"], width)
        self.assertIs(project.parameters["temperature"], native)

    def test_mapping_normalizes_values_without_renaming_or_mutating_source(self):
        width = Parameter(12, "width", unit="um")
        pitch = DependentParameter(2 * width, "pitch")
        source = {
            "width": width,
            "pitch": pitch,
            "gap": "250[nm]",
            "turn": "45 deg",
            "offset": "-2um",
            "count": 3,
            "ratio": "2.5e-1",
            "stress": "120[MPa]",
            "gain": "stress/(1[MPa])",
        }
        before = source.copy()
        with patch("geompype.project.get_client") as connect:
            project = Project()
            values = project.add_parameter(MappingProxyType(source))
            self.assertIsInstance(values, dict)
            self.assertEqual(source, before)
            self.assertIs(values["width"], width)
            self.assertIs(values["pitch"], pitch)
            self.assertEqual(set(values), set(source))
            self.assertEqual({key: value.name for key, value in values.items()},
                             {key: key for key in source})
            self.assertAlmostEqual(evaluate(values["gap"], "um"), 0.25)
            self.assertEqual(evaluate(values["turn"], "deg"), 45)
            self.assertEqual(evaluate(values["offset"], "um"), -2)
            self.assertEqual(values["count"].value, 3)
            self.assertEqual(values["ratio"].value, 0.25)
            self.assertIsInstance(values["stress"], ComsolParameter)
            self.assertEqual(values["gain"].definition, source["gain"])
            self.assertEqual(project.parameters, values)
            registered_again = project.add_parameter(values)
            self.assertTrue(all(registered_again[key] is value
                                for key, value in values.items()))
            self.assertEqual(project.parameters, values)
            self.assertEqual(project.add_parameter({}), {})
            connect.assert_not_called()

    def test_single_parameters_and_dependencies_keep_the_existing_contract(self):
        width = Parameter(4, "width", unit="um")
        pitch = DependentParameter(3 * width, "pitch")
        native = ComsolParameter("2[GHz]", "drive", description="Drive frequency")
        project = Project()
        self.assertIs(project.add_parameter(pitch), pitch)
        self.assertIs(project.add_parameter(native), native)
        self.assertIs(project.add_parameter(native), native)
        self.assertIs(project.parameters["width"], width)
        self.assertEqual(list(project.parameters), ["width", "pitch", "drive"])
        width.value = 5
        self.assertEqual(pitch.value, 15)
        self.assertEqual(native.description, "Drive frequency")

    def test_invalid_batches_leave_every_existing_registration_unchanged(self):
        invalid_entries = [
            ("invalid key", 2),
            ("pi", 2),
            (1, 2),
            ("bad", True),
            ("bad", None),
            ("bad", []),
            ("bad", {"value": 2}),
            ("bad", float("nan")),
            ("bad", float("inf")),
            ("bad", ""),
            ("bad", "  "),
            ("wrong_name", Parameter(1, "actual_name")),
            ("wrong_name", ComsolParameter("2[K]", "actual_name")),
        ]
        for key, value in invalid_entries:
            with self.subTest(key=key, value=value):
                project = Project()
                existing = project.add_parameter(Parameter(1, "existing"))
                before = project.parameters
                with self.assertRaises((TypeError, ValueError)):
                    project.add_parameter({"valid_first": "3um", key: value})
                self.assertEqual(project.parameters, before)
                self.assertIs(project.parameters["existing"], existing)

    def test_conflicts_with_features_native_values_and_dependencies_are_atomic(self):
        project = Project()
        layer = project.add_layer("shape", comsol=False)
        width = Parameter(8, "width", unit="um")
        Rectangle(project, layer=layer, size=(width, 3))
        native = project.add_parameter(ComsolParameter("2[K]", "temperature"))
        before = project.parameters
        conflicting = [
            {"valid_first": 1, "width": "9um"},
            {"valid_first": 1, "temperature": "3[K]"},
            {"valid_first": 1, "temperature": Parameter(3, "temperature")},
            {"valid_first": 1, "width": ComsolParameter("9[um]", "width")},
            {"valid_first": 1,
             "pitch": DependentParameter(Parameter(2, "width", unit="um") * 2,
                                         "pitch")},
        ]
        for batch in conflicting:
            with self.subTest(batch=batch):
                with self.assertRaises(ValueError):
                    project.add_parameter(batch)
                self.assertEqual(project.parameters, before)
        self.assertIs(project.parameters["width"], width)
        self.assertIs(project.parameters["temperature"], native)

        separate = Project()
        with self.assertRaises(ValueError):
            separate.add_parameter({
                "width": "4um",
                "pitch": DependentParameter(Parameter(4, "width", unit="um") * 2,
                                            "pitch"),
            })
        self.assertEqual(separate.parameters, {})

    def test_native_expressions_are_editable_but_never_geometry_numbers(self):
        native = ComsolParameter("50[MPa]", "stress")
        native.expression = "75[MPa]"
        self.assertEqual(native.definition, "75[MPa]")
        self.assertEqual(native.expression, "75[MPa]")
        for invalid in ("", "  ", None, 3):
            with self.subTest(invalid=invalid):
                with self.assertRaises((TypeError, ValueError)):
                    native.expression = invalid
                self.assertEqual(native.definition, "75[MPa]")
        with self.assertRaises(AttributeError):
            native.name = "renamed"
        with self.assertRaises(AttributeError):
            native.definition = "100[MPa]"
        with self.assertRaises((TypeError, ValueError)):
            evaluate(native, "um")
        with self.assertRaises(TypeError):
            _ = native * 2
        project = Project()
        layer = project.add_layer("shape", comsol=False)
        with self.assertRaises((TypeError, ValueError)):
            Rectangle(project, layer=layer, size=(native, 2))
        self.assertEqual(project.objects, [])

    def test_yaml_names_formula_and_parameter_changes_survive_real_gds_builds(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "parameters.yaml"
            source.write_text(
                "width: 16um\nheight: 7[um]\nthickness: 40 nm\n"
                "rate: 4[1/nm]\nQ_volume: 9000\n"
                "Q_effective: '1/(1/(rate*thickness)+1/Q_volume)'\n",
                encoding="utf-8",
            )
            data = yaml.safe_load(source.read_text(encoding="utf-8"))
            project = Project(output=Path(folder) / "shape")
            values = project.add_parameter(data)
            layer = project.add_layer("shape", comsol=False)
            Rectangle(project, layer=layer, size=(values["width"], values["height"]),
                      base="corner")
            self.assertEqual(set(project.parameters), set(data))
            self.assertEqual(values["Q_effective"].definition, data["Q_effective"])
            with patch("geompype.project.get_client") as connect:
                for width, height in ((16, 7), (19, 9)):
                    values["width"].value = width
                    values["height"].value = height
                    project.build()
                    layout, region = read_region(project)
                    expected = kdb.Region(kdb.Box(
                        0, 0, round(width / layout.dbu), round(height / layout.dbu)))
                    self.assertTrue((region ^ expected).is_empty())
                    self.assertEqual(region.count(), 1)
                connect.assert_not_called()
            self.assertEqual(yaml.safe_load(source.read_text(encoding="utf-8")), data)

    def test_native_definitions_are_written_before_geometry_and_refreshed_on_build(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "native_recording")
            values = project.add_parameter({
                "width": "6um", "height": "9um", "pressure": "3[MPa]",
                "ratio": "pressure/(1[MPa])",
            })
            layer = project.add_layer("shape", gds=False)
            rectangle = Rectangle(project, layer=layer,
                                  size=(values["width"], values["height"]))
            events = []
            parameters = Mock()
            parameters.set.side_effect = lambda *args: events.append(("parameter", *args))
            project.model = SimpleNamespace(java=SimpleNamespace(
                param=lambda: parameters, component=lambda tag: object()))
            project.geometry = RecordedGeometry(events)
            plane = RecordedGeometry(events)
            workplane = project.geometry.create("wp1", "WorkPlane")
            workplane.geom = lambda: plane
            project.geometry.run = Mock()
            # Parameter emission only: the recorder does not model native selections.
            project._layer_selections.clear()
            with patch.object(project, "_save_comsol") as save:
                for width, pressure in ((6, "3[MPa]"), (10, "5[MPa]")):
                    values["width"].value = width
                    values["pressure"].expression = pressure
                    events.clear()
                    project.build()
                    emitted = {event[1]: event[2] for event in events
                               if event[0] == "parameter"}
                    self.assertEqual(emitted, {
                        "width": f"{width}[um]", "height": "9[um]",
                        "pressure": pressure, "ratio": "pressure/(1[MPa])",
                    })
                    self.assertEqual([event[0] for event in events[:4]],
                                     ["parameter"] * 4)
                    self.assertEqual(plane.feature(rectangle.tag).values["size"],
                                     ["width", "height"])
                self.assertEqual(save.call_count, 2)
