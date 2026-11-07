"""The flat primitives example also runs offline and supports parameter edits."""

from math import pi
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Project


class TestPrimitivesExample(unittest.TestCase):
    def test_example_twice_offline_then_rebuild_after_parameter_change(self):
        script = Path(__file__).resolve().parents[1] / 'examples' / "example_primitives.py"
        original_add_layer = Project.add_layer

        def offline_layer(project, *args, **kwargs):
            kwargs["comsol"] = False
            return original_add_layer(project, *args, **kwargs)

        def area(project):
            layout = kdb.Layout()
            layout.read(str(project.gds_path))
            shapes = layout.top_cell().shapes(layout.layer(1, 0))
            self.assertEqual(shapes.size(), 4)
            return kdb.Region(shapes).area() * layout.dbu**2

        old_directory = Path.cwd()
        with TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.object(Project, "add_layer", offline_layer), \
                        patch.object(Project, "show") as show, \
                        patch("geompype.project.get_client",
                              side_effect=AssertionError("Unexpected COMSOL connection")):
                    for _ in range(2):
                        namespace = runpy.run_path(str(script))
                        project = namespace["project"]
                        self.assertAlmostEqual(area(project), 350 + 57*pi, delta=0.2)
                        self.assertEqual(len(namespace["conductors"].members), 4)
                        namespace["width"].value = 30
                        project.build()
                        self.assertAlmostEqual(area(project), 525 + 57*pi, delta=0.2)
                        self.assertIsNone(project.client)
                    self.assertEqual(show.call_count, 2)
            finally:
                os.chdir(old_directory)
