"""Run recent flat examples repeatedly and inspect the saved layout geometry."""

from math import pi
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Project


def combined_gds(test, project, height=12, radius=2, pitch=10, count=3, roof_extra=0):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    metal = layout.top_cell().shapes(layout.layer(1, 0))
    construction = list(layout.top_cell().shapes(layout.layer(2, 0)).each())
    test.assertEqual(metal.size(), 3 + 2*count)
    test.assertEqual(len(construction), 1)  # no markers for four point anchors
    test.assertTrue(construction[0].is_path())
    test.assertEqual(construction[0].path.width, 0)
    area = pitch*(count+1)*height - count*pi*radius**2 + 2*height*(height+roof_extra) + 24*count
    test.assertAlmostEqual(kdb.Region(metal).area()*layout.dbu**2, area, delta=0.5)
    report = project.grid_report()
    test.assertTrue(report["complete"])
    test.assertEqual({entry["type"] for entry in report["boolean_operations"]},
                     {"Union", "Difference", "Intersection"})


class TestBooleanExamples(unittest.TestCase):
    def test_all_recent_examples_twice_offline(self):
        directory = Path(__file__).resolve().parents[1] / 'examples'
        previous = Path.cwd()
        original_add_layer = Project.add_layer

        def offline_layer(project, *args, **kwargs):
            kwargs["comsol"] = False
            return original_add_layer(project, *args, **kwargs)

        with TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.object(Project, "add_layer", offline_layer), \
                        patch.object(Project, "show"), patch("builtins.print"), \
                        patch("geompype.project.get_client", side_effect=AssertionError("Connected")):
                    for name in ("example_grid.py", "example_transforms.py", "example_booleans.py",
                                 "example_boolean_transforms.py"):
                        for repetition in range(2):
                            with self.subTest(name=name, repetition=repetition):
                                namespace = runpy.run_path(str(directory/name))
                                project = namespace["project"]
                                self.assertTrue(project.gds_path.exists())
                                self.assertTrue(project.grid_report()["complete"])
                                self.assertIsNone(project.model)
                                if name == "example_boolean_transforms.py":
                                    combined_gds(self, project)
            finally:
                os.chdir(previous)

    def test_combined_example_parameter_and_vertex_edits(self):
        directory = Path(__file__).resolve().parents[1] / 'examples'
        previous = Path.cwd()
        original_add_layer = Project.add_layer

        def offline_layer(project, *args, **kwargs):
            kwargs["comsol"] = False
            return original_add_layer(project, *args, **kwargs)

        with TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.object(Project, "add_layer", offline_layer), \
                        patch.object(Project, "show"), patch("builtins.print"):
                    namespace = runpy.run_path(str(directory/"example_boolean_transforms.py"))
                project = namespace["project"]
                namespace["count"].value = 4
                namespace["pitch"].value = 12000
                namespace["height"].value = 14
                namespace["radius"].value = 2.5
                namespace["factor"].value = 1.2
                namespace["angle"].value = 45
                project.build()
                combined_gds(self, project, height=14, radius=2.5, pitch=12, count=4)
                outline = namespace["outline"]
                outline[2] = outline[2] + (0, 1)
                project.build()
                combined_gds(self, project, height=14, radius=2.5, pitch=12, count=4, roof_extra=1)
            finally:
                os.chdir(previous)
