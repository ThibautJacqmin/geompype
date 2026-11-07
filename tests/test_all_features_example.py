"""Read back the integrated live gallery without opening GUIs or COMSOL."""

from math import cos, pi, radians, sin
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Project


class TestAllFeaturesExample(unittest.TestCase):
    def assert_saved_geometry(self, project, width, height, roof_extra=0):
        layout = kdb.Layout()
        layout.read(str(project.gds_path))
        self.assertEqual({(info.layer, info.datatype) for info in layout.layer_infos()},
                         {(1, 0), (2, 0), (3, 0)})
        metal = layout.top_cell().shapes(layout.layer(1, 0))
        dielectric = layout.top_cell().shapes(layout.layer(2, 0))
        construction = list(layout.top_cell().shapes(layout.layer(3, 0)).each())
        self.assertEqual(metal.size(), 3)
        self.assertEqual(dielectric.size(), 2)
        self.assertTrue(all(shape.is_polygon() or shape.is_box()
                            for shapes in (metal, dielectric) for shape in shapes.each()))
        self.assertEqual(len(construction), 7)
        self.assertTrue(all(shape.is_path() and shape.path.width == 0 for shape in construction))
        metal_region = kdb.Region(metal).merged()
        dielectric_region = kdb.Region(dielectric).merged()
        self.assertEqual(metal_region.count(), 3)
        self.assertEqual(dielectric_region.count(), 2)
        expected_metal = 1.75*width**2 + width*height + width*roof_extra/2
        expected_dielectric = pi*(width**2/4 + width*height/4)
        self.assertAlmostEqual(metal_region.area()*layout.dbu**2, expected_metal, delta=0.2)
        self.assertAlmostEqual(dielectric_region.area()*layout.dbu**2,
                               expected_dielectric, delta=0.25)
        return layout

    def assert_rotations(self, namespace, width, height, pitch, angle):
        # Rectangle rotation replaces its source and stays centred at (-pitch, 2*pitch).
        box = namespace["rotated_rectangle"].to_klayout().bbox()
        c, s = abs(cos(radians(angle))), abs(sin(radians(angle)))
        dx, dy = (width*c + height*s)/2, (width*s + height*c)/2
        for actual, expected in zip((box.left, box.bottom, box.right, box.top),
                                    (-pitch-dx, 2*pitch-dy, -pitch+dx, 2*pitch+dy)):
            self.assertAlmostEqual(actual, expected, places=9)

        # A 180-degree rotation around (pitch, -pitch/2) moves the arc centre
        # from (pitch, 0) to (pitch, -pitch), preserving the original arc too.
        arc_points = list(namespace["rotated_arc"].to_klayout().each_point())
        self.assertAlmostEqual(arc_points[0].x, pitch-width/2, places=9)
        self.assertAlmostEqual(arc_points[0].y, -pitch, places=9)
        self.assertAlmostEqual(arc_points[-1].x, pitch+width/4, places=9)
        self.assertAlmostEqual(arc_points[-1].y, -pitch-width*sin(2*pi/3)/2, places=9)

        # The point copy rotates about a displaced origin; neither point becomes a GDS marker.
        rotated_point = namespace["rotated_point"].to_klayout()
        self.assertIsInstance(rotated_point, kdb.DPoint)
        self.assertAlmostEqual(rotated_point.x, 2*pitch-width*sin(radians(angle)), places=9)
        self.assertAlmostEqual(rotated_point.y,
                               -pitch-width+width*cos(radians(angle)), places=9)

    def test_gallery_twice_live_offline_then_parameter_and_vertices_edits(self):
        script = Path(__file__).resolve().parents[1] / 'examples' / "example_all_features.py"
        original_add_layer, original_build = Project.add_layer, Project.build
        builds = {}

        def offline_layer(project, *args, **kwargs):
            kwargs["comsol"] = False
            return original_add_layer(project, *args, **kwargs)

        def remember_build(project, *args, **kwargs):
            result = original_build(project, *args, **kwargs)
            builds.setdefault(project, []).append(len(project.objects))
            return result

        old_directory = Path.cwd()
        with TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.object(Project, "add_layer", offline_layer), \
                        patch.object(Project, "build", remember_build), \
                        patch.object(Project, "show") as show, \
                        patch("geompype.project.get_client",
                              side_effect=AssertionError("Unexpected COMSOL connection")):
                    for repetition in range(2):
                        with self.subTest(repetition=repetition):
                            namespace = runpy.run_path(str(script))
                            project = namespace["project"]
                            self.assertTrue(project.live)
                            self.assertEqual(len(project.objects), 15)
                            self.assertEqual({type(obj).__name__ for obj in project.objects},
                                             {"Square", "Rectangle", "Circle", "Ellipse", "Polygon",
                                              "Point", "LineSegment", "QuadraticBezier", "CubicBezier",
                                              "CircularArc", "InterpolationCurve", "ParametricCurve", "Rotate"})
                            self.assertTrue(set(range(1, 16)).issubset(builds[project]))
                            final_objects = project._final_objects(project.objects)
                            self.assertEqual(len(final_objects), 14)
                            self.assertNotIn(namespace["rectangle"], final_objects)
                            self.assertIn(namespace["arc"], final_objects)
                            self.assertIn(namespace["point"], final_objects)
                            self.assertEqual(len(namespace["surfaces"].members), 5)
                            self.assertEqual(len(namespace["curve_edges"].members), 6)
                            self.assertEqual(namespace["anchors"].members, (namespace["point"],))
                            self.assertEqual(namespace["rotated_surfaces"].members,
                                             (namespace["rotated_rectangle"],))
                            self.assertEqual(namespace["rotated_curves"].members,
                                             (namespace["rotated_arc"],))
                            self.assertIs(project.parameters["rounded_ratio"], namespace["rounded_ratio"])
                            self.assertEqual(namespace["rounded_ratio"].value, 4)
                            self.assertEqual(namespace["radius"].value, 10)
                            self.assertEqual(namespace["pitch"].value, 50)
                            self.assert_saved_geometry(project, 20, 10)
                            self.assert_rotations(namespace, 20, 10, 50, 30)

                            old_gds = project.gds_path.read_bytes()
                            namespace["width"].value = 24
                            namespace["height"].value = 12
                            namespace["gap"].value = 6000
                            namespace["angle"].value = 45
                            self.assertEqual(project.gds_path.read_bytes(), old_gds)
                            project.build()
                            self.assertEqual(namespace["radius"].value, 12)
                            self.assertEqual(namespace["pitch"].value, 60)
                            self.assertEqual(namespace["shape_centres"].value[4], [120, 120])
                            self.assert_saved_geometry(project, 24, 12)
                            self.assert_rotations(namespace, 24, 12, 60, 45)
                            self.assertAlmostEqual(namespace["parametric"].to_klayout().length(),
                                                   24*pi, delta=0.01)

                            # Editing the actual shared Vertices reaches the polygon.
                            # Extracted rows and translated arrays are separate containers.
                            outline = namespace["outline"]
                            self.assertIs(namespace["polygon"].vertices, outline)
                            old_gds = project.gds_path.read_bytes()
                            outline[3] = outline[3] + (0, 5)
                            self.assertEqual(project.gds_path.read_bytes(), old_gds)
                            project.build()
                            self.assertIs(namespace["polygon"].vertices, outline)
                            self.assertEqual(outline.value[3], [120, 137])
                            self.assert_saved_geometry(project, 24, 12, roof_extra=5)
                            self.assertIsNone(project.client)
                            self.assertIsNone(project.model)
                            self.assertFalse(project.mph_path.exists())
                    self.assertEqual(show.call_count, 4)
            finally:
                os.chdir(old_directory)
