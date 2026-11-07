"""Selection ownership and GDS behavior without a COMSOL connection."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import GeometryObject, Project, Selection
from geompype.primitives import Square
from geompype.transforms import Rotate


def read_regions(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    regions = {(layout.get_info(i).layer, layout.get_info(i).datatype):
               kdb.Region(layout.top_cell().begin_shapes_rec(i))
               for i in layout.layer_indices()}
    return layout, regions  # Recursive regions retain a dependency on their layout.


class TestSelections(unittest.TestCase):
    def test_named_selections_register_with_explicit_entity_dimensions(self):
        project = Project()
        for entity, dimension in (("domain", 3), ("boundary", 2),
                                  ("edge", 1), ("point", 0)):
            selection = Selection(project, entity, entity=entity)
            self.assertIs(project.selections[entity], selection)
            self.assertEqual(selection.dimension, dimension)
            self.assertEqual(selection.members, ())
        default = project.add_selection("conductors")
        self.assertIsInstance(default, Selection)
        self.assertEqual(default.dimension, 2)
        self.assertEqual(len({s.tag for s in project.selections.values()}), 5)
        self.assertIsNone(project.client)
        with self.assertRaises(RuntimeError):
            default.entities()

    def test_invalid_selection_definitions_leave_registry_unchanged(self):
        project = Project()
        existing = project.add_selection("metal")
        for name in ("", "   ", None, 42):
            with self.subTest(name=name):
                with self.assertRaises((TypeError, ValueError)):
                    Selection(project, name)
        with self.assertRaises(ValueError):
            project.add_selection("metal")
        for entity in ("face", "all", "", None, 2):
            with self.subTest(entity=entity):
                with self.assertRaises((TypeError, ValueError)):
                    project.add_selection("invalid", entity=entity)
        self.assertEqual(project.selections, {"metal": existing})

    def test_multiple_groups_span_layers_and_accept_transform_results(self):
        project = Project()
        layer_a = project.add_layer("a", comsol=False)
        layer_b = project.add_layer("b", comsol=False, gds_layer=2)
        conductors = project.add_selection("conductors")
        terminal = project.add_selection("terminal")
        a = Square(project, layer=layer_a, side=2, position=(10, 0),
                   selections=[conductors, terminal])
        b = Square(project, layer=layer_b, side=3, position=(30, 0),
                   selections=[conductors])
        rotated = a.rotate(angle=90, keep=True, selections=[terminal],
                           propagate_selections=False)
        self.assertIsInstance(rotated, Rotate)
        self.assertFalse(rotated.propagate_selections)
        self.assertEqual(conductors.members, (a, b))
        self.assertEqual(terminal.members, (a, rotated))
        self.assertEqual(rotated.selections, (terminal,))
        self.assertIs(conductors.add(rotated), conductors)
        self.assertEqual(conductors.members, (a, b, rotated))
        self.assertIsNone(project.client)

    def test_invalid_batch_add_and_remove_are_atomic(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False)
        selection = project.add_selection("conductors")
        a = Square(project, layer=layer, side=2, selections=[selection])
        b = Square(project, layer=layer, side=3)
        other = Project()
        other_layer = other.add_layer("other", comsol=False)
        foreign = Square(other, layer=other_layer, side=4)
        unregistered = GeometryObject(project, layer)

        for invalid in (foreign, unregistered, object()):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaises((TypeError, ValueError)):
                    selection.add(b, invalid)
                self.assertEqual(selection.members, (a,))
                self.assertEqual(b.selections, ())
                with self.assertRaises((TypeError, ValueError)):
                    selection.remove(a, invalid)
                self.assertEqual(selection.members, (a,))
        self.assertIs(selection.remove(a), selection)
        self.assertEqual(selection.members, ())

    def test_invalid_geometry_memberships_do_not_register_objects(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False)
        selection = project.add_selection("conductors")
        foreign = Project().add_selection("foreign")
        square = Square(project, layer=layer, side=2, selections=[selection])

        for groups in ([foreign], [selection, foreign], [object()], "conductors"):
            with self.subTest(groups=groups):
                with self.assertRaises((TypeError, ValueError)):
                    Square(project, layer=layer, side=3, selections=groups)
                with self.assertRaises((TypeError, ValueError)):
                    Rotate(square, angle=90, selections=groups)
                self.assertEqual(project.objects, [square])
                self.assertEqual(selection.members, (square,))
        for propagate in (1, "on", None):
            with self.subTest(propagate=propagate):
                with self.assertRaises((TypeError, ValueError)):
                    Rotate(square, angle=90, propagate_selections=propagate)
                self.assertEqual(project.objects, [square])

    def test_membership_changes_build_only_when_live_and_changed(self):
        with TemporaryDirectory() as folder:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(live=live, output=Path(folder) / str(live))
                    layer = project.add_layer("metal", comsol=False)
                    selection = project.add_selection("conductors")
                    square = Square(project, layer=layer, side=2, selections=[selection])
                    self.assertEqual(project.gds_path.exists(), live)
                    with patch.object(project, "build", wraps=project.build) as build:
                        selection.add(square)  # Already present: no change.
                        selection.remove(square)
                        selection.remove(square)  # Already absent: no change.
                        selection.add(square, square)
                        self.assertEqual(build.call_count, 2 if live else 0)
                    self.assertEqual(selection.members, (square,))
                    self.assertEqual(square.selections, (selection,))
                    self.assertEqual(project.gds_path.exists(), live)
                    project.build()
                    layout, regions = read_regions(project)
                    self.assertEqual(regions[(1, 0)].area(), 4000000)

    def test_gds_only_memberships_do_not_connect_or_change_geometry(self):
        with TemporaryDirectory() as folder:
            outputs = []
            with patch("geompype.project.get_client",
                       side_effect=AssertionError("Unexpected COMSOL connection")):
                for grouped in (False, True):
                    project = Project(output=Path(folder) / str(grouped))
                    a_layer = project.add_layer("a", comsol=False, gds_layer=7)
                    b_layer = project.add_layer("b", comsol=False, gds_layer=11,
                                                gds_datatype=3)
                    selection = project.add_selection("conductors")
                    groups = [selection] if grouped else []
                    square = Square(project, layer=a_layer, side=2,
                                    position=(10, 0), selections=groups)
                    Rotate(square, angle=90, selections=groups)
                    Square(project, layer=b_layer, side=3, position=(30, 0),
                           selections=groups)
                    project.build()
                    outputs.append(read_regions(project))
                    self.assertIsNone(project.client)
                    self.assertIsNone(project.model)
                    self.assertFalse(project.mph_path.exists())
                    with self.assertRaises(RuntimeError):
                        selection.entities()
            plain, grouped = outputs[0][1], outputs[1][1]
            self.assertEqual(set(plain), {(7, 0), (11, 3)})
            self.assertEqual(set(plain), set(grouped))
            for layer in plain:
                self.assertTrue((plain[layer] ^ grouped[layer]).is_empty())


if __name__ == "__main__":
    unittest.main()
