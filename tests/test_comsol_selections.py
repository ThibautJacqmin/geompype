"""Opt-in checks of actual selected COMSOL entities, not only node names."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from comsol_support import get_client
from geompype import Project
from geompype.primitives import Square
from geompype.transforms import Rotate


def measure_selection(project, group):
    from jpype import JArray, JInt

    measure = project.geometry.measureFinal()
    measure.selection().geom(JInt(group.dimension))
    measure.selection().set(JArray(JInt)(group.entities()))
    return measure


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolSelections(unittest.TestCase):
    def assert_area_and_bounds(self, project, group, area, bounds):
        self.assertTrue(group.entities())
        measure = measure_selection(project, group)
        self.assertAlmostEqual(measure.getArea(), area, delta=0.001)
        actual = list(measure.getBoundingBox())
        self.assertEqual(len(actual), len(bounds))
        for value, expected in zip(actual, bounds):
            self.assertAlmostEqual(value, expected, delta=0.00001)

    def test_groups_both_modes_membership_changes_and_saved_selections(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(client=client, live=live,
                                      output=Path(folder) / f"groups_{live}")
                    first = project.add_layer("first", gds=False)
                    second = project.add_layer("second", gds=False)
                    hidden = project.add_layer("gds_only", comsol=False)
                    all_metal = project.add_selection("all metal")
                    source = project.add_selection("source")
                    terminal = project.add_selection("terminal")
                    edges = project.add_selection("outline", entity="edge")
                    points = project.add_selection("corners", entity="point")
                    try:
                        a = Square(project, layer=first, side=2, position=(10, 0),
                                   selections=[all_metal, source, edges, points])
                        b = Square(project, layer=second, side=3, position=(30, 0),
                                   selections=[all_metal])
                        ignored = Square(project, layer=hidden, side=100,
                                         selections=[all_metal])
                        rotated = Rotate(a, angle=90, selections=[terminal])
                        project.build()
                        self.assertEqual(all_metal.members, (a, b, ignored))
                        self.assertEqual(len(all_metal.entities()), 2)
                        self.assert_area_and_bounds(project, all_metal, 13,
                                                    (-1, 31.5, -1.5, 11, 0, 0))
                        self.assert_area_and_bounds(project, source, 4,
                                                    (-1, 1, 9, 11, 0, 0))
                        self.assertEqual(set(source.entities()), set(terminal.entities()))
                        self.assertEqual(len(edges.entities()), 4)
                        self.assertAlmostEqual(measure_selection(project, edges).getLength(),
                                               8, delta=0.001)
                        self.assertEqual(len(points.entities()), 4)

                        tags = tuple(group.tag for group in project.selections.values())
                        a.side, a.position = 4, (20, 0)
                        project.build()
                        self.assert_area_and_bounds(project, source, 16,
                                                    (-2, 2, 18, 22, 0, 0))
                        terminal.add(b)
                        if not live:
                            project.build()
                        self.assertAlmostEqual(measure_selection(project, terminal).getArea(),
                                               25, delta=0.001)
                        terminal.remove(rotated, b)
                        if not live:
                            project.build()
                        self.assertEqual(terminal.entities(), [])
                        terminal.add(rotated)
                        if not live:
                            project.build()
                        self.assert_area_and_bounds(project, terminal, 16,
                                                    (-2, 2, 18, 22, 0, 0))
                        self.assertEqual(tags, tuple(group.tag for group in
                                                     project.selections.values()))
                        component = project.model.java.component("comp1")
                        for tag in tags:
                            self.assertEqual(list(component.selection().tags()).count(tag), 1)
                        self.assertEqual(str(component.selection(all_metal.tag).label()),
                                         "all metal")

                        reloaded = client.load(str(project.mph_path))
                        try:
                            saved = reloaded.java.component("comp1")
                            self.assertEqual(len(saved.selection(all_metal.tag).entities()), 2)
                            self.assertEqual(len(saved.selection(terminal.tag).entities()), 1)
                            self.assertEqual(saved.selection(edges.tag).dim(), 1)
                            self.assertEqual(len(saved.selection(points.tag).entities()), 4)
                        finally:
                            client.remove(reloaded)
                    finally:
                        if project.model is not None:
                            client.remove(project.model)

    def test_keep_and_propagation_select_the_correct_original_and_copy(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            for keep in (False, True):
                for propagate in (False, True):
                    with self.subTest(keep=keep, propagate=propagate):
                        project = Project(client=client,
                                          output=Path(folder) / f"rotation_{keep}_{propagate}")
                        layer = project.add_layer("metal", gds=False)
                        source = project.add_selection("source")
                        result = project.add_selection("result")
                        try:
                            a = Square(project, layer=layer, side=2, position=(10, 0),
                                       selections=[source])
                            Rotate(a, angle=90, keep=keep, propagate_selections=propagate,
                                   selections=[result])
                            project.build()
                            self.assertEqual(len(result.entities()), 1)
                            self.assert_area_and_bounds(project, result, 4,
                                                        (-1, 1, 9, 11, 0, 0))
                            count = int(keep) + int(propagate)
                            self.assertEqual(len(source.entities()), count)
                            if count:
                                bounds = ((-1, 11, -1, 11, 0, 0) if count == 2 else
                                          (9, 11, -1, 1, 0, 0) if keep else
                                          (-1, 1, 9, 11, 0, 0))
                                self.assert_area_and_bounds(project, source, 4 * count, bounds)
                        finally:
                            if project.model is not None:
                                client.remove(project.model)

    def test_planar_member_cannot_be_selected_as_a_volume(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder) / "domain")
            layer = project.add_layer("metal", gds=False)
            domains = project.add_selection("volumes", entity="domain")
            try:
                square = Square(project, layer=layer, side=2)
                project.build()
                self.assertEqual(domains.entities(), [])
                domains.add(square)
                with self.assertRaisesRegex(ValueError, "domain|volume"):
                    project.build()
                domains.remove(square)
                project.build()
                self.assertEqual(domains.entities(), [])
            finally:
                if project.model is not None:
                    client.remove(project.model)


if __name__ == "__main__":
    unittest.main()
