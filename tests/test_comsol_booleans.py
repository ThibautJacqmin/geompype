"""Native Boolean topology, retention, empty selections and example readback."""

from math import pi
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from comsol_support import get_client
from geompype import (Array, Difference, Intersection, Parameter, Project,
                     Rectangle, Union)
from test_comsol_curves import selected_measure
from test_boolean_examples import combined_gds


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolBooleans(unittest.TestCase):
    def assert_area(self, model, group, expected, count=None, tolerance=1e-4):
        selection = model.java.component("comp1").selection(group.tag)
        self.assertEqual(selection.dim(), 2)
        if count is not None:
            self.assertEqual(len(selection.entities()), count)
        if expected:
            self.assertAlmostEqual(selected_measure(model, group).getArea(), expected, delta=tolerance)
        else:
            self.assertEqual(len(selection.entities()), 0)

    def test_native_operations_and_interior_boundaries(self):
        client = get_client()
        cases = [(Union, True, 24, 3), (Union, False, 24, 1),
                 (Difference, True, 8, 1), (Intersection, True, 8, 1)]
        with TemporaryDirectory() as folder:
            for index, (kind, boundaries, area, count) in enumerate(cases):
                with self.subTest(kind=kind.__name__, boundaries=boundaries):
                    project = Project(client=client, output=Path(folder)/str(index))
                    layer = project.add_layer("metal")
                    group = project.add_selection("result")
                    try:
                        a = Rectangle(project, layer=layer, size=(4, 4))
                        b = Rectangle(project, layer=layer, size=(4, 4), position=(2, 0))
                        options = dict(interior_boundaries=boundaries, selections=[group])
                        result = kind(a, b, **options) if kind is Difference else kind([a, b], **options)
                        project.build()
                        project.build()
                        self.assertEqual(project.workplane.geom().feature(result.tag).getType(), kind.__name__)
                        self.assert_area(project.model, group, area, count)
                    finally:
                        if project.model is not None:
                            client.remove(project.model)

    def test_empty_results_and_parameter_recovery(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            for kind in (Intersection, Difference):
                project = Project(client=client, output=Path(folder)/kind.__name__)
                layer = project.add_layer("metal")
                source_group = project.add_selection("source")
                group = project.add_selection("result")
                x = Parameter(10 if kind is Intersection else 0, "offset", unit="um")
                try:
                    a = Rectangle(project, layer=layer, size=(4, 4), selections=[source_group])
                    b = Rectangle(project, layer=layer, size=(4, 4), position=(x, 0))
                    result = kind(a, b, selections=[group]) if kind is Difference else kind([a, b], selections=[group])
                    project.build()
                    self.assert_area(project.model, group, 0)
                    self.assert_area(project.model, source_group, 0)
                    self.assertEqual(result.to_klayout(), ())
                    x.value = 2
                    project.build()
                    self.assert_area(project.model, group, 8, 1)
                    self.assert_area(project.model, source_group, 8, 1)
                finally:
                    if project.model is not None:
                        client.remove(project.model)

    def test_difference_retains_tools_for_reuse(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder)/"keep_tool")
            layer = project.add_layer("metal")
            group = project.add_selection("cut")
            try:
                plate = Rectangle(project, layer=layer, size=(10, 10))
                tool = Rectangle(project, layer=layer, size=(2, 2))
                cut = Difference(plate, tool, keep_tools=True, selections=[group])
                moved_tool = tool.move(delta=(20, 0))
                project.build()
                self.assert_area(project.model, group, 96, 1)
                self.assertEqual(project._final_objects(project.objects), [cut, moved_tool])
                native = project.workplane.geom().feature(cut.tag)
                self.assertEqual(str(native.getString("keepadd")), "off")
                self.assertEqual(str(native.getString("keepsubtract")), "on")
            finally:
                if project.model is not None:
                    client.remove(project.model)

    def test_explicit_union_groups_array_for_intersection(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, live=True, output=Path(folder)/"array")
            layer = project.add_layer("metal")
            group = project.add_selection("clipped")
            count = Parameter(2, "count")
            try:
                a = Rectangle(project, layer=layer, size=(4, 4))
                array = Array(a, size=count, displacement=(10, 0))
                joined = Union(array)
                mask = Rectangle(project, layer=layer, size=(40, 2), position=(10, 0))
                Intersection([joined, mask], selections=[group])
                self.assert_area(project.model, group, 16, 2)
                count.value = 3
                project.build()
                self.assert_area(project.model, group, 24, 3)
            finally:
                if project.model is not None:
                    client.remove(project.model)

    def assert_combined(self, namespace, model, height=12, radius=2, pitch=10, count=3, roof_extra=0):
        holes_area = count*pi*radius**2
        self.assert_area(model, namespace["perforated_faces"], pitch*(count+1)*height-holes_area,
                         1, tolerance=0.005*holes_area+0.001)
        self.assert_area(model, namespace["assembled_faces"], 2*height*(height+roof_extra),
                         2, tolerance=0.001)
        self.assert_area(model, namespace["clipped_faces"], 24*count, 2*count)
        component = model.java.component("comp1")
        self.assertEqual(len(component.selection(namespace["curve_edges"].tag).entities()), 1)
        self.assertEqual(len(component.selection(namespace["anchors"].tag).entities()), 4)

    def test_new_examples_repeated_then_parameter_edits_and_mph_readback(self):
        client = get_client()
        directory = Path(__file__).resolve().parents[1] / 'examples'
        previous = Path.cwd()
        projects = []
        original_init = Project.__init__

        def remember(project, *args, **kwargs):
            original_init(project, *args, **kwargs)
            projects.append(project)

        with TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                for name in ("example_grid.py", "example_booleans.py", "example_boolean_transforms.py"):
                    for repetition in range(2):
                        with self.subTest(name=name, repetition=repetition):
                            with patch.object(Project, "__init__", remember), \
                                    patch.object(Project, "show"), patch("builtins.print"):
                                namespace = runpy.run_path(str(directory/name))
                            project = namespace["project"]
                            self.assertTrue(project.gds_path.exists())
                            self.assertTrue(project.mph_path.exists())
                            if name == "example_booleans.py":
                                self.assert_area(project.model, namespace["joined_faces"], 360, 3)
                                self.assert_area(project.model, namespace["cut_faces"], 240-9*pi, 1,
                                                 tolerance=0.005*9*pi)
                                self.assert_area(project.model, namespace["overlap_faces"], 120, 1)
                            if name == "example_boolean_transforms.py":
                                self.assert_combined(namespace, project.model)
                                combined_gds(self, project)
                            if repetition == 0 or name != "example_boolean_transforms.py":
                                client.remove(project.model)
                                projects.remove(project)
                # The final run is the combined gallery; every recent transform
                # and Boolean participates in the edited result.
                namespace["count"].value = 4
                namespace["pitch"].value = 12000
                namespace["height"].value = 14
                namespace["radius"].value = 2.5
                namespace["factor"].value = 1.2
                namespace["angle"].value = 45
                outline = namespace["outline"]
                outline[2] = outline[2] + (0, 1)
                project.build()
                self.assert_combined(namespace, project.model, height=14, radius=2.5,
                                     pitch=12, count=4, roof_extra=1)
                combined_gds(self, project, height=14, radius=2.5, pitch=12, count=4, roof_extra=1)
                saved = client.load(str(project.mph_path))
                try:
                    self.assert_combined(namespace, saved, height=14, radius=2.5,
                                         pitch=12, count=4, roof_extra=1)
                    self.assertIn("count", str(saved.java.component('comp1').geom('geom1')
                                               .feature('wp1').geom().feature(namespace['hole_array'].tag)
                                               .getString('linearsize')))
                finally:
                    client.remove(saved)
            finally:
                os.chdir(previous)
                for project in projects:
                    if project.model is not None:
                        client.remove(project.model)
