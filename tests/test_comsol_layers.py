"""Native layer ownership, automatic selections and grouped layer operations."""

import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from comsol_support import get_client
from geompype import LineSegment, Parameter, Point, Project, Rectangle
from test_comsol_curves import selected_measure


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolLayers(unittest.TestCase):
    def setUp(self):
        self.client = get_client()
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.projects = []
        self.addCleanup(self.clean_models)

    def clean_models(self):
        for project in self.projects:
            if project.model is not None:
                self.client.remove(project.model)

    def project(self, *, live=False):
        project = Project(client=self.client, live=live,
                          output=Path(self.folder.name)/str(len(self.projects)))
        self.projects.append(project)
        return project

    def assert_layer_area(self, project, layer, expected, *, count=None, model=None):
        model = project.model if model is None else model
        selection = model.java.component("comp1").selection(layer.selection.tag)
        self.assertEqual(selection.dim(), 2)
        if count is not None:
            self.assertEqual(len(selection.entities()), count)
        if expected:
            self.assertAlmostEqual(selected_measure(model, layer.selection).getArea(), expected, delta=1e-4)
        else:
            self.assertEqual(list(selection.entities()), [])

    def assert_layer_box(self, project, layer, bounds):
        actual = selected_measure(project.model, layer.selection).getBoundingBox()
        for value, expected in zip(actual, (*bounds, 0, 0)):
            self.assertAlmostEqual(value, expected, delta=1e-6)

    def test_component_scoped_copy_between_layers(self):
        project = self.project()
        source = project.add_layer('source',gds_layer=1)
        destination = project.add_layer('destination',gds_layer=2)
        width = Parameter(4,'width',unit='um')
        first = Rectangle(project,layer=source,size=(width,2))
        Rectangle(project,layer=source,size=(3,3),position=(50,0))
        copied = first.copy_to(destination,delta=(20,0))
        project.build()
        width.value = 6
        project.build()
        self.assert_layer_area(project,source,21)
        self.assert_layer_area(project,destination,12)
        self.assert_layer_box(project,destination,(17,23,-1,1))
        self.assertEqual(copied.inputs,(first,))

    def test_automatic_selections_and_one_workplane(self):
        project = self.project()
        first = project.add_layer("first", gds_layer=1)
        second = project.add_layer("second", gds_layer=2)
        empty = project.add_layer("empty", gds_layer=3)
        Rectangle(project, layer=first, size=(4, 6))
        Rectangle(project, layer=second, size=(5, 2), position=(20, 0))
        project.build()
        project.build()
        self.assert_layer_area(project, first, 24, count=1)
        self.assert_layer_area(project, second, 10, count=1)
        self.assert_layer_area(project, empty, 0)
        planes = [str(tag) for tag in project.geometry.feature().tags()
                  if str(project.geometry.feature(tag).getType()) == "WorkPlane"]
        self.assertEqual(planes, ["wp1"])

    def test_copy_ownership_parameters_and_saved_selections(self):
        project = self.project()
        source = project.add_layer("source", gds_layer=1)
        destination = project.add_layer("destination", gds_layer=2)
        explicit = project.add_selection("source_and_descendants")
        spacing = Parameter(20, "copy_spacing", unit="um")
        Rectangle(project, layer=source, size=(4, 6), selections=[explicit])
        project.copy_layer(source, output=destination, delta=(spacing, 0))
        project.build()
        self.assert_layer_area(project, source, 24, count=1)
        self.assert_layer_area(project, destination, 24, count=1)
        self.assert_layer_box(project, source, (-2, 2, -3, 3))
        self.assert_layer_box(project, destination, (18, 22, -3, 3))
        # Explicit user groups keep their existing native descendant behavior.
        self.assertAlmostEqual(selected_measure(project.model, explicit).getArea(), 48, delta=1e-4)
        spacing.value = 30
        project.build()
        self.assert_layer_box(project, source, (-2, 2, -3, 3))
        self.assert_layer_box(project, destination, (28, 32, -3, 3))
        saved = self.client.load(str(project.mph_path))
        try:
            self.assert_layer_area(project, source, 24, model=saved)
            self.assert_layer_area(project, destination, 24, model=saved)
        finally:
            self.client.remove(saved)

    def test_merge_consumes_sources_and_keep_retains_owned_regions(self):
        for keep in (False, True):
            project = self.project()
            first = project.add_layer("first", gds_layer=1)
            second = project.add_layer("second", gds_layer=2)
            result = project.add_layer("result", gds_layer=3)
            Rectangle(project, layer=first, size=(4, 4), position=(-2, 0))
            Rectangle(project, layer=second, size=(4, 4), position=(2, 0))
            project.merge_layers([first, second], output=result, keep=keep,
                                 interior_boundaries=False)
            project.build()
            self.assert_layer_area(project, first, 16 if keep else 0)
            self.assert_layer_area(project, second, 16 if keep else 0)
            self.assert_layer_area(project, result, 32)

    def test_subtract_layers_and_retained_tools(self):
        project = self.project()
        base = project.add_layer("base", gds_layer=1)
        tools = project.add_layer("tools", gds_layer=2)
        result = project.add_layer("result", gds_layer=3)
        Rectangle(project, layer=base, size=(10, 10))
        Rectangle(project, layer=tools, size=(2, 2))
        project.subtract_layers(base, tools, output=result, keep_tools=True)
        project.build()
        project.build()
        self.assert_layer_area(project, base, 0)
        self.assert_layer_area(project, tools, 4, count=1)
        self.assert_layer_area(project, result, 96)

    def test_intersection_unites_each_layer_before_intersecting(self):
        project = self.project()
        first = project.add_layer("first", gds_layer=1)
        second = project.add_layer("second", gds_layer=2)
        result = project.add_layer("result", gds_layer=3)
        width = Parameter(4, "tile_width", unit="um")
        for x in (0, 10):
            Rectangle(project, layer=first, size=(width, 4), position=(x, 0))
            Rectangle(project, layer=second, size=(6, 2), position=(x, 0))
        project.intersect_layers([first, second], output=result, interior_boundaries=False)
        project.build()
        project.build()
        self.assert_layer_area(project, first, 0)
        self.assert_layer_area(project, second, 0)
        self.assert_layer_area(project, result, 16, count=2)
        width.value = 6
        project.build()
        self.assert_layer_area(project, result, 24, count=2)
        layout = kdb.Layout()
        layout.read(str(project.gds_path))
        footprint = kdb.Region(layout.top_cell().shapes(layout.layer(3, 0)))
        self.assertAlmostEqual(footprint.area()*layout.dbu**2, 24, delta=1e-6)

    def test_copy_mixed_construction_layer(self):
        project = self.project()
        source = project.add_layer("construction", gds_layer=1)
        destination = project.add_layer("copied_construction", gds_layer=2)
        source_edges = source.selection_for(entity="edge")
        source_points = source.selection_for(entity="point")
        destination_edges = destination.selection_for(entity="edge")
        destination_points = destination.selection_for(entity="point")
        LineSegment(project, layer=source, p1=(0, 0), p2=(10, 0))
        Point(project, layer=source, position=(3, 7))
        project.copy_layer(source, output=destination, delta=(0, 20))
        project.build()
        self.assert_layer_area(project, source, 0)
        self.assert_layer_area(project, destination, 0)
        for group in (source_edges, destination_edges):
            self.assertAlmostEqual(selected_measure(project.model, group).getLength(), 10, delta=1e-6)
        self.assertEqual(len(source_points.entities()), 3)
        self.assertEqual(len(destination_points.entities()), 3)

    def test_example_repeated_and_edited(self):
        directory = Path(__file__).resolve().parents[1] / 'examples'
        original = Project.__init__
        def remember(project, *args, **kwargs):
            original(project, *args, **kwargs)
            self.projects.append(project)
        previous = Path.cwd()
        try:
            os.chdir(self.folder.name)
            for _ in range(2):
                with patch.object(Project, "__init__", remember), patch.object(Project, "show"), \
                        patch("builtins.print"):
                    namespace = runpy.run_path(str(directory/"example_layers.py"))
                project = namespace["project"]
                self.assert_layer_area(project, namespace["etched"], 336)
                self.assert_layer_area(project, namespace["window"], 96)
                self.assertTrue(project.mph_path.exists())
                self.assertTrue(project.gds_path.exists())
            namespace["height"].value = 16
            namespace["hole_width"].value = 8
            namespace["copy_spacing"].value = 50
            project.build()
            self.assert_layer_area(project, namespace["etched"], 448)
            self.assert_layer_area(project, namespace["window"], 128)
        finally:
            os.chdir(previous)

    def test_live_additions_after_existing_layer_captures(self):
        project = self.project(live=True)
        source = project.add_layer("source", gds_layer=1)
        Rectangle(project, layer=source, size=(4, 6))
        original_tag = source.selection.tag
        destination = project.add_layer("destination", gds_layer=2)
        project.copy_layer(source, output=destination, delta=(20, 0))
        self.assert_layer_area(project, source, 24)
        self.assert_layer_area(project, destination, 24)
        Rectangle(project, layer=source, size=(2, 2), position=(10, 0))
        self.assert_layer_area(project, source, 28)
        self.assert_layer_area(project, destination, 24)
        merged = project.add_layer("merged", gds_layer=3)
        project.merge_layers(source, output=merged)
        self.assertEqual(source.selection.tag, original_tag)
        self.assert_layer_area(project, source, 0)
        self.assert_layer_area(project, destination, 24)
        self.assert_layer_area(project, merged, 28)

    def test_empty_layer_intersection_recovers_after_parameter_edit(self):
        project = self.project()
        first = project.add_layer("first", gds_layer=1)
        second = project.add_layer("second", gds_layer=2)
        result = project.add_layer("result", gds_layer=3)
        offset = Parameter(0, "mask_x", unit="um")
        Rectangle(project, layer=first, size=(4, 4))
        Rectangle(project, layer=second, size=(4, 2), position=(offset, 0))
        project.intersect_layers([first, second], output=result)
        for displacement, expected in ((0, 8), (10, 0), (0, 8)):
            offset.value = displacement
            project.build()
            self.assert_layer_area(project, result, expected)
            self.assert_layer_area(project, first, 0)
            self.assert_layer_area(project, second, 0)

    def test_intersection_keep_preserves_source_ownership(self):
        project = self.project()
        first = project.add_layer("first", gds_layer=1)
        second = project.add_layer("second", gds_layer=2)
        result = project.add_layer("result", gds_layer=3)
        Rectangle(project, layer=first, size=(4, 4))
        Rectangle(project, layer=second, size=(2, 6))
        project.intersect_layers([first, second], output=result, keep=True)
        project.build()
        project.build()
        self.assert_layer_area(project, first, 16)
        self.assert_layer_area(project, second, 12)
        self.assert_layer_area(project, result, 8)
