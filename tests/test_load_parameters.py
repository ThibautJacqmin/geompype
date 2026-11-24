"""Flat YAML parameter files preserve names, units and native expressions."""

from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

import yaml

from geompype import ComsolParameter, Parameter, Project, Rectangle, load_parameters
from geompype.configuration import load_parameters as load_from_configuration
from geompype.parameters import evaluate


class TestLoadParameters(unittest.TestCase):
    def test_project_accepts_absolute_and_relative_yaml_paths_without_building(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "parameters.yml"
            source.write_text("width: 8um\npressure: 2[MPa]\n", encoding="utf-8")
            previous_directory = Path.cwd()
            try:
                os.chdir(folder)
                for path in (source, str(source), source.name, Path(source.name)):
                    with self.subTest(path=path), patch("geompype.project.get_client") as connect:
                        project = Project(live=True)
                        with patch.object(project, "build") as build:
                            values = project.add_parameter(path)
                            self.assertEqual(set(values), {"width", "pressure"})
                            self.assertIs(project.parameters["width"], values["width"])
                            self.assertIs(project.parameters["pressure"], values["pressure"])
                            self.assertEqual(values["width"].value, 8)
                            self.assertEqual(values["width"].unit, "um")
                            self.assertEqual(values["pressure"].definition, "2[MPa]")
                            values["width"].value = 11
                            values["pressure"].expression = "3[MPa]"
                            self.assertEqual(project.parameters["width"].definition, "11[um]")
                            self.assertEqual(project.parameters["pressure"].definition, "3[MPa]")
                            build.assert_not_called()
                        connect.assert_not_called()
            finally:
                os.chdir(previous_directory)

    def test_project_file_errors_do_not_partially_register_parameters(self):
        invalid_documents = (
            ("", ValueError),
            ("[1, 2]\n", ValueError),
            ("valid_first: 2um\ninvalid name: 3\n", ValueError),
            ("valid_first: 2um\nnested: {width: 4um}\n", TypeError),
            ("valid_first: 2um\nbroken: [\n", yaml.YAMLError),
        )
        with TemporaryDirectory() as folder:
            source = Path(folder) / "parameters.yaml"
            project = Project()
            existing = project.add_parameter(Parameter(7, "existing"))
            before = project.parameters
            with self.assertRaises(FileNotFoundError):
                project.add_parameter(source)
            self.assertEqual(project.parameters, before)
            for content, error in invalid_documents:
                with self.subTest(content=content):
                    source.write_text(content, encoding="utf-8")
                    with self.assertRaises(error):
                        project.add_parameter(source)
                    self.assertEqual(project.parameters, before)
                    self.assertIs(project.parameters["existing"], existing)

    def test_project_file_conflicts_preserve_geometry_and_registered_objects(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "parameters.yaml"
            project = Project()
            layer = project.add_layer("outline", comsol=False)
            width = Parameter(6, "width", unit="um")
            Rectangle(project, layer=layer, size=(width, 2))
            before = project.parameters
            source.write_text("new_first: 1\nwidth: 9um\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                project.add_parameter(source)
            self.assertEqual(project.parameters, before)
            self.assertIs(project.parameters["width"], width)

            source.write_text("pressure: 2[MPa]\n", encoding="utf-8")
            values = project.add_parameter(source)
            self.assertIs(project.add_parameter(values)["pressure"], values["pressure"])
            before = project.parameters
            with self.assertRaises(ValueError):
                project.add_parameter(source)
            self.assertEqual(project.parameters, before)
            self.assertIs(project.parameters["pressure"], values["pressure"])

    def test_exact_names_types_units_and_formulas_with_bom_and_path_inputs(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "device_parameters.yaml"
            source.write_text(
                "width: 1.25e1[um]\ngap: 250nm\nangle: 90 deg\n"
                "count: 4\nscale: 3e-2\nstress: 25[MPa]\n"
                "normalized_load: stress*width/(1[um])\n",
                encoding="utf-8-sig",
            )
            self.assertIs(load_parameters, load_from_configuration)
            for path in (source, str(source)):
                with self.subTest(path_type=type(path).__name__):
                    values = load_parameters(path)
                    self.assertIsInstance(values, dict)
                    self.assertEqual(list(values), [
                        "width", "gap", "angle", "count", "scale",
                        "stress", "normalized_load",
                    ])
                    self.assertEqual({name: value.name for name, value in values.items()},
                                     {name: name for name in values})
                    self.assertTrue(all(isinstance(values[name], Parameter)
                                        for name in ("width", "gap", "angle", "count", "scale")))
                    self.assertEqual(evaluate(values["width"], "um"), 12.5)
                    self.assertEqual(values["gap"].unit, "nm")
                    self.assertEqual(evaluate(values["gap"], "um"), 0.25)
                    self.assertEqual(evaluate(values["angle"], "deg"), 90)
                    self.assertEqual(values["count"].value, 4)
                    self.assertEqual(values["scale"].value, 0.03)
                    self.assertIsInstance(values["stress"], ComsolParameter)
                    self.assertEqual(values["stress"].definition, "25[MPa]")
                    self.assertEqual(values["normalized_load"].definition,
                                     "stress*width/(1[um])")

    def test_loaded_objects_are_editable_and_registered_without_copying_or_building(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "parameters.yaml"
            source.write_text("width: 8um\npressure: 2[MPa]\n", encoding="utf-8")
            original = source.read_bytes()
            with patch("geompype.project.get_client") as connect:
                values = load_parameters(source)
                project = Project(live=True)
                with patch.object(project, "build") as build:
                    registered = project.add_parameter(values)
                    self.assertIs(registered["width"], values["width"])
                    self.assertIs(project.parameters["pressure"], values["pressure"])
                    values["width"].value = 11
                    values["pressure"].expression = "3[MPa]"
                    self.assertEqual(project.parameters["width"].definition, "11[um]")
                    self.assertEqual(project.parameters["pressure"].definition, "3[MPa]")
                    build.assert_not_called()
                connect.assert_not_called()
            self.assertEqual(source.read_bytes(), original)
            reloaded = load_parameters(source)
            self.assertEqual(reloaded["width"].value, 8)
            self.assertEqual(reloaded["pressure"].definition, "2[MPa]")
            self.assertIsNot(reloaded["width"], values["width"])

    def test_invalid_documents_and_parameter_entries_are_rejected(self):
        invalid = [
            "", "# no values\n", "null\n", "4\n", "[1, 2]\n",
            "width: {value: 4, unit: um}\n", "width: [1, 2]\n",
            "enabled: true\n", "missing: null\n", "width: ''\n",
            "invalid name: 1\n", "2: 3\n", "pi: 3\n", "width: .inf\n",
        ]
        with TemporaryDirectory() as folder:
            source = Path(folder) / "invalid.yaml"
            for content in invalid:
                with self.subTest(content=content):
                    source.write_text(content, encoding="utf-8")
                    with self.assertRaises((TypeError, ValueError)):
                        load_parameters(source)
            for content in ("width: [\n", "width: !Unsupported 4\n"):
                with self.subTest(content=content):
                    source.write_text(content, encoding="utf-8")
                    with self.assertRaises(yaml.YAMLError):
                        load_parameters(source)

    def test_empty_mapping_missing_file_and_opaque_expressions(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "parameters.yaml"
            source.write_text("{}\n", encoding="utf-8")
            self.assertEqual(load_parameters(source), {})
            with self.assertRaises(FileNotFoundError):
                load_parameters(Path(folder) / "missing.yaml")
            source.write_text("formula: 1/0\nreference: absent.yaml\n", encoding="utf-8")
            values = load_parameters(source)
            self.assertEqual(values["formula"].definition, "1/0")
            self.assertEqual(values["reference"].definition, "absent.yaml")
            self.assertTrue(all(isinstance(value, ComsolParameter) for value in values.values()))
