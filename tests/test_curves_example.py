"""The flat seven-primitive curve example works offline and rebuilds its paths."""

from math import pi
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Project


class TestCurvesExample(unittest.TestCase):
    def test_example_twice_offline_then_parameter_rebuild(self):
        script = Path(__file__).resolve().parents[1] / 'examples' / "example_curves.py"
        original_add_layer = Project.add_layer

        def offline_layer(project, *args, **kwargs):
            kwargs["comsol"] = False
            return original_add_layer(project, *args, **kwargs)

        def assert_saved_paths(project):
            layout = kdb.Layout()
            layout.read(str(project.gds_path))
            shapes = list(layout.top_cell().shapes(layout.layer(1, 0)).each())
            self.assertEqual(len(shapes), 6)  # The Point has no GDS marker.
            self.assertTrue(all(shape.is_path() and shape.path.width == 0 for shape in shapes))

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
                        self.assertEqual(len(project.objects), 7)
                        self.assertEqual(len(namespace["edges"].members), 6)
                        assert_saved_paths(project)
                        namespace["radius"].value = 12
                        namespace["pitch"].value = 25
                        project.build()
                        assert_saved_paths(project)
                        self.assertEqual(namespace["interpolation"].points.value[-1], [-25, -50])
                        self.assertAlmostEqual(namespace["parametric"].to_klayout().length(),
                                               24*pi, delta=0.01)
                        self.assertIsNone(project.client)
                    self.assertEqual(show.call_count, 2)
            finally:
                os.chdir(old_directory)
