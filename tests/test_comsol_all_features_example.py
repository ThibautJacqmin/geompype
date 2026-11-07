"""Validate the combined live example with native selections and saved geometry."""

from math import pi
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from comsol_support import get_client
from geompype import Project
import test_all_features_example as gallery_checks
from test_comsol_curves import native_edge_points, distance_to_polyline, selected_measure


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolAllFeaturesExample(unittest.TestCase):
    def assert_native(self, namespace, model, width, height, roof_extra=0):
        component = model.java.component("comp1")
        expected = {"surfaces": (2, 5), "anchors": (0, 2),
                    "rotated_surfaces": (2, 1), "rotated_curves": (1, 1)}
        for name, (dimension, count) in expected.items():
            selection = component.selection(namespace[name].tag)
            self.assertEqual(selection.dim(), dimension)
            self.assertEqual(len(selection.entities()), count)
        edges = component.selection(namespace["curve_edges"].tag)
        self.assertEqual(edges.dim(), 1)
        # A closed native curve can be split into several topological edges.
        self.assertGreaterEqual(len(edges.entities()), 7)
        expected_area = 1.75*width**2 + width*height + width*roof_extra/2
        curved_area = pi*(width**2/4 + width*height/4)
        area = selected_measure(model, namespace["surfaces"]).getArea()
        self.assertAlmostEqual(area, expected_area + curved_area,
                               delta=0.005*curved_area + 0.01)
        rotated_measure = selected_measure(model, namespace["rotated_surfaces"])
        # COMSOL measurements use finite-precision rendering coordinates.
        self.assertAlmostEqual(rotated_measure.getArea(), width*height,
                               delta=1e-6*width*height)
        box = namespace["rotated_rectangle"].to_klayout().bbox()
        expected_bounds = (box.left, box.right, box.bottom, box.top, 0, 0)
        for actual, expected_value in zip(rotated_measure.getBoundingBox(), expected_bounds):
            self.assertAlmostEqual(actual, expected_value, delta=0.00005)
        self.assertAlmostEqual(model.java.param().evaluate("rounded_ratio"), 4)
        return area

    def test_live_gallery_parameters_vertices_selections_and_saved_model(self):
        client = get_client()
        script = Path(__file__).resolve().parents[1] / 'examples' / "example_all_features.py"
        projects = []
        original_init = Project.__init__
        original_directory = Path.cwd()

        def remember_project(project, *args, **kwargs):
            original_init(project, *args, **kwargs)
            projects.append(project)

        with TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.object(Project, "__init__", remember_project), patch.object(Project, "show"):
                    namespace = runpy.run_path(str(script))
                project = namespace["project"]
                self.assertTrue(project.live)
                self.assertIs(project.client, client)
                plane = project.workplane.geom()
                self.assertEqual(sum(str(plane.feature(tag).getType()) != "ExplicitSelection"
                                     for tag in plane.feature().tags()), 15)
                self.assertEqual({str(plane.feature(obj.tag).getType()) for obj in project.objects},
                                 {"Square", "Rectangle", "Circle", "Ellipse", "Polygon", "Point",
                                  "LineSegment", "QuadraticBezier", "CubicBezier", "CircularArc",
                                  "InterpolationCurve", "ParametricCurve", "Rotate"})
                self.assert_native(namespace, project.model, 20, 10)
                offline_checks = gallery_checks.TestAllFeaturesExample()
                offline_checks.assert_saved_geometry(project, 20, 10)

                namespace["width"].value = 24
                namespace["height"].value = 12
                namespace["gap"].value = 6000
                namespace["angle"].value = 45
                project.build()
                self.assert_native(namespace, project.model, 24, 12)
                offline_checks.assert_saved_geometry(project, 24, 12)
                offline_checks.assert_rotations(namespace, 24, 12, 60, 45)

                outline = namespace["outline"]
                outline[3] = outline[3] + (0, 5)
                project.build()
                self.assert_native(namespace, project.model, 24, 12, roof_extra=5)
                offline_checks.assert_saved_geometry(project, 24, 12, roof_extra=5)
                rotated = [(point.x, point.y) for point in namespace["rotated_arc"].to_klayout().each_point()]
                native = native_edge_points(project.model, namespace["rotated_curves"])
                self.assertLessEqual(max(distance_to_polyline(point, rotated) for point in native), 0.00101)

                saved = client.load(str(project.mph_path))
                try:
                    self.assert_native(namespace, saved, 24, 12, roof_extra=5)
                    self.assertIn("width", str(saved.java.param().get("radius")))
                    self.assertIn("gap", str(saved.java.param().get("pitch")))
                finally:
                    client.remove(saved)
            finally:
                os.chdir(original_directory)
                for project in projects:
                    if project.model is not None:
                        client.remove(project.model)
