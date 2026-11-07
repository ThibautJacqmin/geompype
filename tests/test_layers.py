"""Layer ownership, current-input capture and actual exported layer footprints."""

import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import LineSegment, Parameter, Point, Project, Rectangle, Vertices
from test_operations import region


class TestLayers(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name)/"layers")
        self.a, self.b, self.out = [self.project.add_layer(name, comsol=False, gds_layer=index)
                                   for index, name in enumerate(("a", "b", "out"), 1)]

    def rectangle(self, layer, size=(4, 4), position=(0, 0)):
        return Rectangle(self.project, layer=layer, size=size, position=position)

    def assert_area(self, result, area):
        self.assertAlmostEqual(region(result).area()*self.project.dbu**2, area, delta=1e-6)

    def test_copy_one_feature_preserves_scope_and_parameters(self):
        width = Parameter(4,'width',unit='um')
        source = self.rectangle(self.a,size=(width,2))
        self.rectangle(self.a,position=(50,0))
        copied = source.copy_to(self.out,delta=(20,0))
        width.value = 6
        self.assert_area(copied,12)
        self.assertEqual(len(self.a.selection.members),2)
        self.assertEqual(self.out.selection.members,(copied,))
        self.project.build()
        other = Project().add_layer('out',comsol=False)
        with self.assertRaisesRegex(ValueError,'registered in this project'):
            source.copy_to(other)
        native = self.project.add_layer('native_only',gds=False)
        with self.assertRaisesRegex(ValueError,'matching COMSOL/GDS flags'):
            source.copy_to(native)

    def test_automatic_groups_are_stable_separate_and_derived(self):
        explicit = self.project.add_selection("Layer: a")
        self.assertEqual(explicit.tag, "sel1")
        group = self.a.selection
        self.assertIs(group, self.a.selection_for(entity="boundary"))
        self.assertNotEqual(group.tag, explicit.tag)
        self.assertEqual(group.members, ())
        shape = self.rectangle(self.a)
        self.assertEqual(group.members, (shape,))
        rotated = shape.rotate(angle=45)
        self.assertEqual(group.members, (rotated,))
        with self.assertRaisesRegex(ValueError, "automatic"):
            group.add(rotated)
        with self.assertRaisesRegex(ValueError, "automatic"):
            group.remove(rotated)
        with self.assertRaisesRegex(ValueError, "boundary, edge or point"):
            self.a.selection_for(entity="domain")

    def test_merge_moves_ownership_and_exports_only_output(self):
        self.rectangle(self.a, position=(-1, 0))
        self.rectangle(self.b, position=(1, 0))
        result = self.project.merge_layers([self.a, self.b], output=self.out)
        self.assert_area(result, 24)
        self.assertEqual(self.a.selection.members, ())
        self.assertEqual(self.b.selection.members, ())
        self.assertEqual(self.out.selection.members, (result,))
        self.project.build()
        layout = kdb.Layout()
        layout.read(str(self.project.gds_path))
        for number, count in ((1, 0), (2, 0), (3, 1)):
            self.assertEqual(layout.top_cell().shapes(layout.layer(number, 0)).size(), count)

    def test_keep_and_destination_already_contains_geometry(self):
        first = self.rectangle(self.a)
        second = self.rectangle(self.b, position=(10, 0))
        existing = self.rectangle(self.out, position=(20, 0))
        result = self.project.merge_layers(["a", "b"], output="out", keep=True)
        self.assert_area(result, 32)
        self.assertEqual(self.a.selection.members, (first,))
        self.assertEqual(self.b.selection.members, (second,))
        self.assertEqual(self.out.selection.members, (existing, result))

    def test_subtract_retains_tools_independently(self):
        self.rectangle(self.a, (10, 10))
        tool = self.rectangle(self.b, (2, 2))
        result = self.project.subtract_layers(self.a, self.b, output=self.out, keep_tools=True)
        self.assert_area(result, 96)
        self.assertEqual(self.a.selection.members, ())
        self.assertEqual(self.b.selection.members, (tool,))
        self.assertEqual(list(region(result).each())[0].holes(), 1)

    def test_subtract_multiple_base_and_tool_layers(self):
        extra = self.project.add_layer("extra", comsol=False, gds_layer=4)
        self.rectangle(self.a, (4, 4), position=(0, 0))
        self.rectangle(extra, (4, 4), position=(10, 0))
        self.rectangle(self.b, (2, 10), position=(0, 0))
        result = self.project.subtract_layers([self.a, extra], self.b, output=self.out)
        self.assert_area(result, 24)

    def test_intersection_unions_each_layer_first(self):
        for x in (0, 10):
            self.rectangle(self.a, (4, 4), position=(x, 0))
            self.rectangle(self.b, (6, 2), position=(x, 0))
        result = self.project.intersect_layers([self.a, self.b], output=self.out)
        self.assert_area(result, 16)
        self.assertEqual(region(result).count(), 2)

    def test_intersection_accepts_array_and_empty_result(self):
        source = self.rectangle(self.a)
        source.array(size=2, displacement=(10, 0))
        mask = self.rectangle(self.b, (30, 2), position=(5, 0))
        result = self.project.intersect_layers([self.a, self.b], output=self.out)
        self.assert_area(result, 16)
        mask.position = (100, 100)
        self.assertEqual(result.to_klayout(), ())
        self.project.build()
        self.assertTrue(self.project.grid_report()["complete"])

    def test_copy_preserves_points_paths_and_source_layer(self):
        shape = self.rectangle(self.a)
        path = LineSegment(self.project, layer=self.a, p1=(10, 0), p2=(20, 0))
        point = Point(self.project, layer=self.a, position=(30, 0))
        result = self.project.copy_layer(self.a, output=self.out, delta=(0, 10))
        self.assertEqual(self.a.selection.members, (shape, path, point))
        self.assertEqual(self.out.selection.members, (result,))
        copied = result.to_klayout()
        self.assertEqual([type(item) for item in copied], [kdb.DPolygon, kdb.DPath, kdb.DPoint])
        self.assertEqual(copied[2], kdb.DPoint(30, 10))
        self.project.build()
        shapes = self.project.layout.top_cell().shapes(self.project.layout.layer(3, 0))
        self.assertEqual(shapes.size(), 2)  # Construction points never create GDS markers.

    def test_captured_members_remain_parametric(self):
        height = Parameter(4, "height", unit="um")
        first = self.rectangle(self.a, (4, height))
        result = self.project.copy_layer(self.a, output=self.out, delta=Vertices((0, height)))
        later = self.rectangle(self.a, (20, 20), position=(50, 0))
        self.assertEqual(result.inputs, (first,))
        self.assertNotIn(later, result.inputs)
        height.value = 6
        self.assert_area(result, 24)
        self.project.build()

    def test_same_layer_destination(self):
        self.rectangle(self.a)
        self.rectangle(self.b, position=(2, 0))
        result = self.project.merge_layers([self.a, self.b], output=self.a)
        self.assertEqual(self.a.selection.members, (result,))
        self.assert_area(result, 24)

    def test_invalid_requests_do_not_modify_graph(self):
        first = self.rectangle(self.a)
        empty = self.project.add_layer("empty", comsol=False)
        disabled = self.project.add_layer("disabled", comsol=False, gds=False)
        count = len(self.project.objects)
        calls = [lambda: self.project.merge_layers([self.a, self.a], output=self.out),
                 lambda: self.project.merge_layers([self.a, empty], output=self.out),
                 lambda: self.project.merge_layers([self.a], output=disabled),
                 lambda: self.project.merge_layers(["missing"], output=self.out),
                 lambda: self.project.intersect_layers([self.a], output=self.out),
                 lambda: self.project.subtract_layers(self.a, self.a, output=self.out)]
        for call in calls:
            with self.assertRaises((TypeError, ValueError)):
                call()
            self.assertEqual(len(self.project.objects), count)
        self.assertEqual(self.a.selection.members, (first,))

    def test_area_operations_reject_curves_and_objects_still_require_same_layer(self):
        first = self.rectangle(self.a)
        line = LineSegment(self.project, layer=self.b)
        with self.assertRaisesRegex(TypeError, "filled"):
            self.project.merge_layers([self.a, self.b], output=self.out)
        second = self.rectangle(self.b)
        with self.assertRaisesRegex(ValueError, "layer"):
            first.union(second)

    def test_example_and_parameter_rebuild_offline(self):
        directory = Path(__file__).resolve().parents[1] / 'examples'
        original = Project.add_layer
        def offline_layer(project, *args, **kwargs):
            kwargs["comsol"] = False
            return original(project, *args, **kwargs)
        previous = Path.cwd()
        try:
            os.chdir(self.folder.name)
            with patch.object(Project, "add_layer", offline_layer), patch.object(Project, "show"), \
                    patch("builtins.print"):
                namespace = runpy.run_path(str(directory/"example_layers.py"))
            project = namespace["project"]
            namespace["height"].value = 16
            namespace["hole_width"].value = 8
            namespace["copy_spacing"].value = 50
            project.build()
            project.build()
            self.assertEqual([layer.name for layer in project.layers.values()
                              if layer.selection.members], ["etched", "window"])
            self.assertAlmostEqual(region(namespace["etched_plate"]).area()*project.dbu**2, 448)
            self.assertAlmostEqual(region(namespace["window_plate"]).area()*project.dbu**2, 128)
        finally:
            os.chdir(previous)
