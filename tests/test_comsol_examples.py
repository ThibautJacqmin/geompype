"""Run student scripts twice and preserve an independently opened MPH file."""

import os
from math import pi
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from comsol_support import get_client
from geompype import Project
from geompype.primitives import Square


def comsol_area(model):
    measure = model.java.component("comp1").geom("geom1").measureFinal()
    measure.selection().geom(2)
    measure.selection().all()
    return measure.getArea()


def gds_area(path):
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(str(path))
    region = kdb.Region()
    for index in layout.layer_indices():
        region += kdb.Region(layout.top_cell().begin_shapes_rec(index))
    region.merge()
    return region.area() * layout.dbu**2


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolExamples(unittest.TestCase):
    def test_plain_scripts_run_twice_in_one_interpreter(self):
        client = get_client()
        scripts = Path(__file__).resolve().parents[1] / 'examples'
        old_directory = Path.cwd()
        projects = []
        original_init = Project.__init__

        def remember_project(project, *args, **kwargs):
            original_init(project, *args, **kwargs)
            projects.append(project)  # Also clean up if a script raises during build.

        cases = [("square", 1, 400), ("rotation", 2, 800),
                 ("selections", 3, 900), ("live", 2, None),
                 ("parameters", 2, None), ("vertices", 4, 64),
                 ("primitives", 4, None), ("curves", 7, 0)]
        with TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.object(Project, "__init__", remember_project), \
                        patch.object(Project, "show", autospec=True, return_value=None) as show:
                    for name, count, expected_area in cases:
                        with self.subTest(example=name):
                            previous = None
                            for repetition in range(2):
                                namespace = runpy.run_path(str(scripts / f"example_{name}.py"))
                                project = namespace["project"]
                                self.assertIs(project.client, client)
                                self.assertEqual(len(project.objects), count)
                                self.assertTrue(project.mph_path.is_file())
                                self.assertTrue(project.gds_path.is_file())
                                area = comsol_area(project.model)
                                # COMSOL measures curved faces using a rendering mesh.
                                delta = 0.005 * (57*pi) + 0.2 if name == "primitives" else 0.2
                                self.assertAlmostEqual(area, gds_area(project.gds_path), delta=delta)
                                if expected_area is not None:
                                    self.assertAlmostEqual(area, expected_area, delta=0.001)
                                if name == "selections":
                                    self.assertIs(namespace["square1"].project, project)
                                    self.assertEqual(len(namespace["conductors"].entities()), 3)
                                    self.assertEqual(len(namespace["rotated_only"].entities()), 1)
                                elif name == "primitives":
                                    self.assertIs(namespace["rectangle"].project, project)
                                    self.assertEqual(len(namespace["conductors"].entities()), 4)
                                    self.assertAlmostEqual(area, 350 + 57*pi, delta=0.005 * (57*pi))
                                elif name == "curves":
                                    import klayout.db as kdb

                                    self.assertIs(namespace["point"].project, project)
                                    self.assertEqual(len(namespace["edges"].members), 6)
                                    self.assertGreaterEqual(len(namespace["edges"].entities()), 6)
                                    layout = kdb.Layout()
                                    layout.read(str(project.gds_path))
                                    shapes = list(layout.top_cell().shapes(layout.layer(1, 0)).each())
                                    self.assertEqual(len(shapes), 6)
                                    self.assertTrue(all(shape.is_path() and shape.path.width == 0
                                                        for shape in shapes))
                                else:
                                    self.assertIs(namespace["square"].project, project)
                                if previous is not None:
                                    self.assertIs(previous.client, project.client)
                                    self.assertNotEqual(str(previous.model.java.tag()),
                                                        str(project.model.java.tag()))
                                    self.assertEqual(previous.mph_path, project.mph_path)
                                    self.assertEqual(previous.gds_path, project.gds_path)
                                previous = project
                    self.assertEqual(show.call_count, 2 * len(cases))
            finally:
                os.chdir(old_directory)
                for project in projects:
                    if project.model is not None:
                        client.remove(project.model)

    def test_open_mph_is_preserved_and_rebuild_reuses_alternate_path(self):
        client = get_client()
        projects = []
        opened = None
        with TemporaryDirectory() as folder:
            try:
                first = Project(output=Path(folder) / "drawing")
                projects.append(first)
                Square(first, layer=first.add_layer("metal"), side=2)
                first.build()
                original_path = first.mph_path
                original_contents = original_path.read_bytes()
                opened = client.load(str(original_path))

                second = Project(output=Path(folder) / "drawing")
                projects.append(second)
                Square(second, layer=second.add_layer("metal"), side=3)
                second.build()
                alternate = second.mph_path
                self.assertIs(first.client, second.client)
                self.assertNotEqual(alternate, original_path)
                self.assertEqual(alternate.parent, original_path.parent)
                self.assertTrue(alternate.is_file())
                self.assertEqual(first.gds_path, second.gds_path)
                self.assertAlmostEqual(comsol_area(second.model), 9, delta=0.001)
                self.assertAlmostEqual(comsol_area(opened), 4, delta=0.001)
                self.assertEqual(original_path.read_bytes(), original_contents)

                second.build()
                self.assertEqual(second.mph_path, alternate)
                self.assertEqual(original_path.read_bytes(), original_contents)
                self.assertAlmostEqual(comsol_area(opened), 4, delta=0.001)
            finally:
                if opened is not None:
                    client.remove(opened)
                for project in projects:
                    if project.model is not None:
                        client.remove(project.model)


if __name__ == "__main__":
    unittest.main()
