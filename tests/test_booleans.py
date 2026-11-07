"""Filled set operations through real Region calculations and GDS readback."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import (Array, Difference, Intersection, LineSegment, Parameter,
                     Point, Polygon, Project, Rectangle, Rotate, Union, Vertices)


def region(geometry, dbu=0.001):
    result = kdb.Region()
    for polygon in geometry if isinstance(geometry, tuple) else (geometry,):
        result.insert(polygon.to_itype(dbu))
    return result.merged()


def saved_region(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    return kdb.Region(layout.top_cell().shapes(layout.layer(1, 0))).merged()


class TestBooleans(unittest.TestCase):
    def test_union_difference_intersection_areas_in_both_modes(self):
        with TemporaryDirectory() as folder:
            for live in (False, True):
                for kind, area in ((Union, 24), (Difference, 8), (Intersection, 8)):
                    with self.subTest(live=live, kind=kind.__name__):
                        project = Project(live=live, output=Path(folder)/f"{kind.__name__}_{live}")
                        layer = project.add_layer("metal", comsol=False)
                        a = Rectangle(project, layer=layer, size=(4, 4))
                        b = Rectangle(project, layer=layer, size=(4, 4), position=(2, 0))
                        result = kind(a, b) if kind is Difference else kind([a, b])
                        project.build()
                        project.build()
                        self.assertEqual(project._final_objects(project.objects), [result])
                        self.assertAlmostEqual(saved_region(project).area()*project.dbu**2, area)

    def test_holes_disconnected_pieces_and_empty_footprints(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/"hole")
            layer = project.add_layer("metal", comsol=False)
            outer = Rectangle(project, layer=layer, size=(10, 10))
            inner = Rectangle(project, layer=layer, size=(4, 4))
            hole = Difference(outer, inner)
            polygon = hole.to_klayout()
            self.assertEqual(polygon.holes(), 1)
            self.assertAlmostEqual(polygon.area(), 84)
            project.build()
            self.assertAlmostEqual(saved_region(project).area()*project.dbu**2, 84)
            # The output can be transformed while preserving its hole.
            rotated = hole.rotate(angle=90)
            project.build()
            self.assertEqual(rotated.to_klayout().holes(), 1)
            self.assertAlmostEqual(saved_region(project).area()*project.dbu**2, 84)
            cutter = Rectangle(project, layer=layer, size=(20, 20))
            empty = Difference(rotated, cutter)
            project.build()
            self.assertEqual(empty.to_klayout(), ())
            self.assertTrue(saved_region(project).is_empty())

            separate = Project(output=Path(folder)/"pieces")
            layer = separate.add_layer("metal", comsol=False)
            a = Rectangle(separate, layer=layer, size=(2, 2))
            b = Rectangle(separate, layer=layer, size=(2, 2), position=(10, 0))
            merged = Union([a, b])
            self.assertEqual(len(merged.to_klayout()), 2)
            separate.build()
            self.assertAlmostEqual(saved_region(separate).area()*separate.dbu**2, 8)

    def test_disjoint_and_touching_intersections_are_empty_area(self):
        for offset in (2, 10):
            with TemporaryDirectory() as folder:
                project = Project(output=Path(folder)/"empty")
                layer = project.add_layer("metal", comsol=False)
                a = Rectangle(project, layer=layer, size=(2, 2))
                b = Rectangle(project, layer=layer, size=(2, 2), position=(offset, 0))
                result = Intersection([a, b])
                project.build()
                self.assertEqual(result.to_klayout(), ())
                self.assertTrue(saved_region(project).is_empty())

    def test_independent_difference_retention_and_tool_reuse(self):
        with TemporaryDirectory() as folder:
            for keep_base, keep_tools in ((False, False), (False, True), (True, False), (True, True)):
                project = Project(output=Path(folder)/f"keep_{keep_base}_{keep_tools}")
                layer = project.add_layer("metal", comsol=False)
                base = Rectangle(project, layer=layer, size=(10, 10))
                tool = Rectangle(project, layer=layer, size=(2, 20))
                result = Difference(base, tool, keep_base=keep_base, keep_tools=keep_tools)
                final = project._final_objects(project.objects)
                self.assertEqual(base in final, keep_base)
                self.assertEqual(tool in final, keep_tools)
                self.assertIn(result, final)
                if keep_tools:
                    tool.move(delta=(30, 0))
                else:
                    with self.assertRaisesRegex(ValueError, "consumed"):
                        tool.move(delta=(30, 0))
                project.build()

    def test_union_of_array_is_one_intersection_operand(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/"clip")
            layer = project.add_layer("metal", comsol=False)
            a = Rectangle(project, layer=layer, size=(4, 4))
            array = Array(a, size=2, displacement=(10, 0))
            mask = Rectangle(project, layer=layer, size=(20, 2), position=(5, 0))
            with self.assertRaisesRegex(ValueError, "Union"):
                Intersection([array, mask])
            joined = Union(array)
            clipped = Intersection([joined, mask])
            project.build()
            self.assertEqual(len(clipped.to_klayout()), 2)
            self.assertAlmostEqual(saved_region(project).area()*project.dbu**2, 16)

    def test_parameters_vertices_rebuild_and_invalid_updates(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/"updates")
            layer = project.add_layer("metal", comsol=False)
            width = Parameter(10, "width", unit="um")
            outline = Vertices([[0, 0], [1, 0], [1, 1], [0, 1]], width)
            base = Polygon(project, layer=layer, vertices=outline)
            tool = Rectangle(project, layer=layer, size=(2, 20), position=(5, 5))
            result = Difference(base, tool)
            project.build()
            self.assertAlmostEqual(saved_region(project).area()*project.dbu**2, 80)
            width.value = 12
            project.build()
            self.assertAlmostEqual(saved_region(project).area()*project.dbu**2, 120)
            outline[2] = outline[2] + (0, 2)
            project.build()
            self.assertGreater(saved_region(project).area()*project.dbu**2, 120)
            old_file = project.gds_path.read_bytes()
            result.keep_tools = "yes"
            with self.assertRaises(ValueError):
                project.build()
            self.assertEqual(project.gds_path.read_bytes(), old_file)

    def test_grid_stages_cannot_hide_operand_rounding(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/"grid")
            layer = project.add_layer("metal", comsol=False)
            a = Rectangle(project, layer=layer, size=(4, 4), position=(0.0004, 0))
            b = Rectangle(project, layer=layer, size=(4, 4), position=(2, 0))
            joined = Union([a, b])
            Rotate(joined, angle=30)
            project.build()
            report = project.grid_report()
            self.assertTrue(report["complete"])
            self.assertIn(a.tag, report["affected_objects"])
            self.assertEqual({entry["stage"] for entry in report["objects"]},
                             {"boolean_input", "export"})
            self.assertEqual(report["boolean_operations"][0]["tag"], joined.tag)
            joined.to_klayout()
            self.assertEqual(project.grid_report(), report)
            old_file = project.gds_path.read_bytes()
            project.grid_policy = "error"
            with patch("geompype.project.get_client", side_effect=AssertionError("Connected")):
                with self.assertRaisesRegex(ValueError, "off the GDS grid"):
                    project.build()
            self.assertEqual(project.gds_path.read_bytes(), old_file)
            previous = project.grid_report()
            with self.assertRaisesRegex(ValueError, "off the GDS grid"):
                joined.to_klayout()
            self.assertEqual(project.grid_report(), previous)

    def test_integer_intersections_have_explicit_report_limit(self):
        # On-grid edge endpoints can intersect between DBU coordinates. Region
        # still computes on its integer lattice; strict checks explicit input
        # conversions, not an exact rational version of the Boolean algorithm.
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/"lattice", dbu=1, grid_policy="error")
            layer = project.add_layer("metal", comsol=False)
            a = Polygon(project, layer=layer, vertices=[(0, 0), (5, 0), (0, 3)])
            b = Rectangle(project, layer=layer, size=(2, 2), base="corner", position=(1, 1))
            Intersection([a, b])
            project.build()
            self.assertFalse(project.grid_report()["boolean_operations"][0]
                             ["internal_intersection_rounding_measured"])

    def test_rejects_curves_points_mixed_layers_and_duplicates(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        other = project.add_layer("other", comsol=False, gds=False)
        a = Rectangle(project, layer=layer, size=(2, 2))
        b = Rectangle(project, layer=other, size=(2, 2))
        point = Point(project, layer=layer, position=(0, 0))
        line = LineSegment(project, layer=layer, p1=(0, 0), p2=(1, 0))
        for inputs in ([a, b], [a, a], [a, point], [a, line]):
            before = list(project.objects)
            with self.assertRaises((ValueError, TypeError)):
                Union(inputs)
            self.assertEqual(project.objects, before)
