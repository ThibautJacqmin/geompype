"""Repeated Run reuses a live viewer and reopens one that was closed."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import geompype
from geompype import Project
from geompype.primitives import Square


class TestViewers(unittest.TestCase):
    def test_projects_with_same_output_reuse_the_viewer(self):
        with TemporaryDirectory() as folder:
            first_process = Mock()
            first_process.poll.return_value = None
            replacement = Mock()
            replacement.poll.return_value = None
            with patch.object(Project, "_executable", return_value="klayout"), \
                    patch("geompype.project.subprocess.Popen",
                          side_effect=[first_process, replacement]) as launch:
                first = Project(output=Path(folder) / "example")
                layer = first.add_layer("metal", comsol=False)
                Square(first, layer=layer, side=2)
                first.build()
                first.show()
                arguments = launch.call_args.args[0]
                self.assertEqual(arguments[:2], ["klayout", "-rr"])
                script = Path(arguments[2])
                self.assertEqual(script, Path(geompype.__file__).with_name("_klayout_preview.py"))
                self.assertTrue(script.is_file())

                second = Project(output=first.output)
                layer = second.add_layer("metal", comsol=False)
                Square(second, layer=layer, side=3)
                second.build()
                second.show()
                self.assertEqual(launch.call_count, 1)
                self.assertIs(second._gui_processes["gds"], first_process)

                first_process.poll.return_value = 0
                second.show()
                self.assertEqual(launch.call_count, 2)
                self.assertIs(second._gui_processes["gds"], replacement)
