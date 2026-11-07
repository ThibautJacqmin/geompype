"""Native planar transformation geometry, parameters and GDS grid independence."""

import os
from math import pi
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from comsol_support import get_client
from geompype import (Array, Copy, Mirror, Move, Parameter, Point, Project,
                     Rectangle, Rotate, Scale, LineSegment, Vertices)
from test_comsol_curves import selected_measure


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolTransforms(unittest.TestCase):
    def assert_faces(self, model, group, count, area, bounds):
        selection = model.java.component("comp1").selection(group.tag)
        self.assertEqual(selection.dim(), 2)
        self.assertEqual(len(selection.entities()), count)
        measure = selected_measure(model, group)
        self.assertAlmostEqual(measure.getArea(), area, delta=max(1e-5, area*1e-6))
        for actual, expected in zip(measure.getBoundingBox(), (*bounds, 0, 0)):
            self.assertAlmostEqual(actual, expected, delta=5e-5)

    def test_excluded_array_parameters_mode_changes_and_saved_model(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder)/"excluded")
            layer = project.add_layer("metal")
            inherited = project.add_selection("inherited")
            group = project.add_selection("result")
            count = Parameter(4, "count")
            pitch = Parameter(5, "pitch", unit="um")
            try:
                source = Rectangle(project, layer=layer, size=(2, 2), selections=[inherited])
                array = Array(source, size=count, displacement=(pitch, 0), exclude=[0, 2])
                Move(array, delta=(0, 10), selections=[group])
                project.build()
                project.build()
                self.assert_faces(project.model, group, 2, 8, (4, 16, 9, 11))
                self.assert_faces(project.model, inherited, 2, 8, (4, 16, 9, 11))
                self.assertEqual(str(project.workplane.geom().feature(array.tag).getType()), "Move")
                self.assertTrue(all("pitch" in str(value) for value in
                                    project.workplane.geom().feature(array.tag).getStringArray("displx")))
                count.value, pitch.value = 6, 6
                project.build()
                self.assert_faces(project.model, group, 4, 16, (5, 31, 9, 11))
                old_gds = project.gds_path.read_bytes()
                count.value = 2
                with self.assertRaisesRegex(ValueError, "outside"):
                    project.build()
                self.assertEqual(project.gds_path.read_bytes(), old_gds)
                self.assert_faces(project.model, group, 4, 16, (5, 31, 9, 11))
                count.value = 6
                array.exclude = ()
                project.build()
                self.assert_faces(project.model, group, 6, 24, (-1, 31, 9, 11))
                self.assertEqual(str(project.workplane.geom().feature(array.tag).getType()), "Array")
                array.size, array.displacement = (3, 2), (pitch, 8)
                array.exclude = [(0, 0), (1, 1)]
                project.build()
                self.assert_faces(project.model, group, 4, 16, (-1, 13, 9, 19))
                self.assert_faces(project.model, inherited, 4, 16, (-1, 13, 9, 19))
                self.assertEqual(len(layer.selection.entities()), 4)
                saved = client.load(str(project.mph_path))
                try:
                    self.assert_faces(saved, group, 4, 16, (-1, 13, 9, 19))
                finally:
                    client.remove(saved)
            finally:
                if project.model is not None:
                    client.remove(project.model)

    def test_excluded_arrays_support_mixed_entities_and_overlapping_survivors(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder)/"mixed_excluded")
            layer = project.add_layer("mixed")
            faces = project.add_selection("faces")
            edges = project.add_selection("edges", entity="edge")
            points = project.add_selection("points", entity="point")
            overlap = project.add_selection("overlap")
            try:
                source = Rectangle(project, layer=layer, size=(2, 2), selections=[faces])
                line = LineSegment(project, layer=layer, p1=(0, 5), p2=(2, 5), selections=[edges])
                point = Point(project, layer=layer, position=(0, 10), selections=[points])
                Array((source, line, point), size=(2, 2), displacement=(10, 20),
                      exclude=[(0, 0), (1, 1)])
                wide = Rectangle(project, layer=layer, size=(4, 2), position=(50, 0))
                Array(wide, size=4, displacement=(1, 0), exclude=[1], selections=[overlap])
                project.build()
                self.assert_faces(project.model, faces, 2, 8, (-1, 11, -1, 21))
                self.assertEqual(len(edges.entities()), 2)
                self.assertEqual(len(points.entities()), 2)
                coords = project.geometry.getVertexCoord()
                actual = sorted((float(coords[0][i-1]), float(coords[1][i-1]))
                                for i in points.entities())
                for position, expected in zip(actual, [(0, 30), (10, 10)]):
                    for value, wanted in zip(position, expected):
                        self.assertAlmostEqual(value, wanted, delta=1e-8)
                self.assertAlmostEqual(selected_measure(project.model, overlap).getArea(), 14,
                                       delta=1e-5)
                layout = kdb.Layout()
                layout.read(str(project.gds_path))
                shapes = list(layout.top_cell().shapes(layout.layer(1, 0)).each())
                self.assertEqual(sum(s.is_polygon() or s.is_box() for s in shapes), 5)
                self.assertEqual(sum(s.is_path() for s in shapes), 2)
            finally:
                if project.model is not None:
                    client.remove(project.model)

    def test_all_planar_features_and_propagated_selections(self):
        # Independent analytic answers for a 2 x 2 square centred at (10, 3).
        cases = [
            (Move, {"delta": (4, 7)}, 1, (13, 15, 9, 11)),
            (Copy, {"delta": ((4, 7), (10, 14))}, 2, (13, 21, 9, 18)),
            (Mirror, {"normal": (1, 1), "origin": (2, 1)}, 1, (-1, 1, -8, -6)),
            (Scale, {"factor": (2, 0.5), "origin": (2, 1)}, 1, (16, 20, 1.5, 2.5)),
            (Scale, {"factor": (-2, 0.5), "origin": (2, 1)}, 1, (-16, -12, 1.5, 2.5)),
            (Rotate, {"angle": (90, 180)}, 2, (-11, -2, -4, 11)),
            (Array, {"size": 3, "displacement": (5, 4)}, 3, (9, 21, 2, 12)),
            (Array, {"size": (2, 3), "displacement": (5, 4)}, 6, (9, 16, 2, 12)),
        ]
        client = get_client()
        with TemporaryDirectory() as folder:
            for index, (kind, options, count, bounds) in enumerate(cases):
                with self.subTest(kind=kind.__name__, options=options):
                    project = Project(client=client, output=Path(folder)/f"case_{index}")
                    layer = project.add_layer("metal")
                    inherited = project.add_selection("inherited")
                    result = project.add_selection("result")
                    try:
                        source = Rectangle(project, layer=layer, size=(2, 2),
                                           position=(10, 3), selections=[inherited])
                        transform = kind(source, **options, selections=[result])
                        project.build()
                        project.build()
                        self.assertEqual(project.workplane.geom().feature(transform.tag).getType(),
                                         kind.__name__)
                        self.assert_faces(project.model, result, count, 4*count, bounds)
                        total_count = count + int(transform.keep)
                        inherited_bounds = (min(9, bounds[0]), max(11, bounds[1]),
                                            min(2, bounds[2]), max(4, bounds[3])) if transform.keep else bounds
                        self.assert_faces(project.model, inherited, total_count,
                                          4*total_count, inherited_bounds)
                        layout = kdb.Layout()
                        layout.read(str(project.gds_path))
                        shapes = layout.top_cell().shapes(layout.layer(1, 0))
                        self.assertEqual(shapes.size(), total_count)
                        self.assertAlmostEqual(kdb.Region(shapes).area()*layout.dbu**2,
                                               4*total_count)
                    finally:
                        if project.model is not None:
                            client.remove(project.model)

    def test_array_chain_parameter_edits_and_saved_model(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, live=True, output=Path(folder)/"chain")
            layer = project.add_layer("metal")
            group = project.add_selection("result")
            count = Parameter(3, "count")
            pitch = Parameter(5000, "pitch", unit="nm")
            shift = Vertices((0, 10))
            try:
                source = Rectangle(project, layer=layer, size=(2, 2))
                array = Array(source, size=count, displacement=(pitch, 0))
                moved = Move(array, delta=shift, selections=[group])
                self.assert_faces(project.model, group, 3, 12, (-1, 11, 9, 11))
                count.value, pitch.value = 4, 6000
                shift[0] = (0, 20)
                project.build()
                self.assert_faces(project.model, group, 4, 16, (-1, 19, 19, 21))
                self.assertEqual(str(project.workplane.geom().feature(array.tag)
                                     .getString("linearsize")), "count")
                self.assertIn("pitch", str(project.workplane.geom().feature(array.tag)
                                            .getStringArray("displ")))
                # Change the same feature from linear to rectangular, and back.
                array.size = (2, 2)
                array.displacement = (pitch, pitch)
                project.build()
                self.assert_faces(project.model, group, 4, 16, (-1, 7, 19, 27))
                array.size = count
                array.displacement = (pitch, 0)
                project.build()
                saved = client.load(str(project.mph_path))
                try:
                    self.assert_faces(saved, group, 4, 16, (-1, 19, 19, 21))
                    self.assertEqual(str(saved.java.param().get("pitch")), pitch.definition)
                finally:
                    client.remove(saved)
            finally:
                if project.model is not None:
                    client.remove(project.model)

    def test_mixed_points_paths_and_polygons_remain_distinct(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder)/"mixed")
            layer = project.add_layer("mixed")
            faces = project.add_selection("faces")
            edges = project.add_selection("edges", entity="edge")
            points = project.add_selection("points", entity="point")
            try:
                rectangle = Rectangle(project, layer=layer, size=(2, 2), selections=[faces])
                segment = LineSegment(project, layer=layer, p1=(0, 5), p2=(2, 5), selections=[edges])
                point = Point(project, layer=layer, position=(0, 10), selections=[points])
                mirrored = Mirror([rectangle, segment, point], normal=(1, 0), origin=(3, 0))
                Array(mirrored, size=2, displacement=(20, 0))
                project.build()
                self.assert_faces(project.model, faces, 2, 8, (5, 27, -1, 1))
                self.assertEqual(len(edges.entities()), 2)
                self.assertEqual(len(points.entities()), 2)
                coords = project.geometry.getVertexCoord()
                actual = sorted((float(coords[0][i-1]), float(coords[1][i-1])) for i in points.entities())
                self.assertEqual(actual, [(6, 10), (26, 10)])
                layout = kdb.Layout()
                layout.read(str(project.gds_path))
                shapes = list(layout.top_cell().shapes(layout.layer(1, 0)).each())
                self.assertEqual(sum(s.is_polygon() or s.is_box() for s in shapes), 2)
                self.assertEqual(sum(s.is_path() for s in shapes), 2)
                self.assertTrue(all(s.path.width == 0 for s in shapes if s.is_path()))
            finally:
                if project.model is not None:
                    client.remove(project.model)

    def test_flat_gallery_and_parameter_edits(self):
        client = get_client()
        script = Path(__file__).resolve().parents[1] / 'examples'/"example_transforms.py"
        previous_directory = Path.cwd()
        projects = []
        original_init = Project.__init__

        def remember(project, *args, **kwargs):
            original_init(project, *args, **kwargs)
            projects.append(project)

        with TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                with patch.object(Project, "__init__", remember), patch.object(Project, "show"), \
                        patch("builtins.print"):
                    namespace = runpy.run_path(str(script))
                project = namespace["project"]
                self.assertEqual(len(namespace["surfaces"].entities()), 19)
                self.assertEqual(len(namespace["curves"].entities()), 3)
                self.assertEqual(len(namespace["anchors"].entities()), 4)
                self.assertEqual(len(namespace["copies"].entities()), 2)
                # Eighteen 8 um² rectangles/triangles and one scaled disk.
                expected_area = 144 + 4*pi
                self.assertAlmostEqual(selected_measure(project.model, namespace["surfaces"])
                                       .getArea(), expected_area, delta=0.005*4*pi)
                self.assertTrue(project.grid_report()["complete"])
                namespace["count"].value = 4
                namespace["pitch"].value = 10000
                namespace["factor"].value = 1.5
                namespace["angle"].value = 45
                offsets = namespace["offsets"]
                offsets[1] = offsets[1] + (0, 5)
                project.build()
                self.assertEqual(len(namespace["surfaces"].entities()), 22)
                self.assertEqual(len(namespace["curves"].entities()), 4)
                self.assertEqual(len(namespace["anchors"].entities()), 4)
                layout = kdb.Layout()
                layout.read(str(project.gds_path))
                self.assertEqual(layout.top_cell().shapes(layout.layer(1, 0)).size(), 22)
                self.assertEqual(layout.top_cell().shapes(layout.layer(2, 0)).size(), 4)
            finally:
                os.chdir(previous_directory)
                for project in projects:
                    if project.model is not None:
                        client.remove(project.model)

    def test_grid_policy_keeps_native_values_and_strict_failure_preserves_model(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder)/"grid")
            layer = project.add_layer("metal")
            group = project.add_selection("rectangle")
            width = Parameter(2.0004, "width", unit="um")
            try:
                Rectangle(project, layer=layer, size=(width, 1), base="corner",
                          position=(0.0004, 0), selections=[group])
                project.build()
                self.assert_faces(project.model, group, 1, 2.0004, (0.0004, 2.0008, 0, 1))
                self.assertAlmostEqual(project.model.java.param().evaluate("width"), 2.0004e-6)
                old_gds = project.gds_path.read_bytes()
                project.grid_policy = "error"
                width.value = 3.0004
                with self.assertRaisesRegex(ValueError, "off the GDS grid"):
                    project.build()
                self.assertEqual(project.gds_path.read_bytes(), old_gds)
                self.assert_faces(project.model, group, 1, 2.0004, (0.0004, 2.0008, 0, 1))
            finally:
                if project.model is not None:
                    client.remove(project.model)
