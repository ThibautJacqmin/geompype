"""Native planar edits compared with analytic areas and saved GDS footprints."""

from math import hypot, pi
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from comsol_support import get_client
from geompype import (Chamfer, CircularArc, Fillet, LineSegment, Offset,
                     Parameter, Project, Rectangle, Thicken2D, Vertices)
from test_comsol_curves import selected_measure, native_edge_points
from test_operations import region


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolPlanarOperations(unittest.TestCase):
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

    def project(self):
        project = Project(client=self.client, output=Path(self.folder.name)/str(len(self.projects)))
        self.projects.append(project)
        return project, project.add_layer("metal")

    def assert_area(self, project, group, result, expected, tolerance=0.05):
        native = selected_measure(project.model, group).getArea()
        self.assertAlmostEqual(native, expected, delta=tolerance)
        self.assertAlmostEqual(region(result).area()*project.dbu**2, native, delta=tolerance)

    def assert_native_arc_radii(self, model, group, expected):
        """Measure circles from exact CAD edge points, independently of render meshes."""
        from jpype import JArray, JDouble, JInt

        component = model.java.component('comp1')
        geometry = component.geom('geom1')
        radii = []
        for number in component.selection(group.tag).entities():
            edge = JInt(number)
            start, stop = map(float, geometry.edgeParamRange(edge))
            parameters = JArray(JDouble)([start+(stop-start)*i/4 for i in range(5)])
            points = [tuple(map(float, p)) for p in geometry.edgeX(edge, parameters)]
            a, b, c = points[0], points[2], points[4]
            cross = (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(cross) < 1e-9:
                continue  # Straight portion between two fillets.
            ab, bc, ca = (hypot(a[0]-b[0], a[1]-b[1]),
                          hypot(b[0]-c[0], b[1]-c[1]),
                          hypot(c[0]-a[0], c[1]-a[1]))
            radii.append(ab*bc*ca/(2*abs(cross)))
        self.assertEqual(len(radii), len(expected))
        for actual, target in zip(sorted(radii), sorted(expected)):
            self.assertAlmostEqual(actual, target, delta=1e-6)

    def test_fillet_trim_limit_native_radii_groups_rebuild_and_readback(self):
        project, layer = self.project()
        inherited = project.add_selection('inherited')
        faces = project.add_selection('rounded_faces')
        edges = project.add_selection('rounded_edges', entity='edge')
        height = Parameter(5, 'plate_height', unit='um')
        radius = Parameter(10, 'corner_radius', unit='um')
        first = Rectangle(project, layer=layer, size=(10, height), selections=[inherited])
        second = Rectangle(project, layer=layer, size=(10, 10), position=(20, 0),
                           selections=[inherited])
        rounded = first.union(second, interior_boundaries=False).fillet(
            radius=radius, max_trim_fraction=0.49, selections=[edges])
        result = rounded.move(delta=(3, 7), selections=[faces])
        # The equal-height case merges the radius caps; restoring unequal
        # heights must recreate the additional native group before the Move.
        for h, requested, first_radius, second_radius, group_count in (
                (5, 10, 2.45, 4.9, 2), (10, 10, 4.9, 4.9, 1),
                (10, 1, 1, 1, 1), (5.0004, 10, 2.450196, 4.9, 2)):
            height.value, radius.value = h, requested
            project.build()
            project.build()
            self.assertEqual(len(faces.entities()), 2)
            self.assertEqual(set(faces.entities()), set(inherited.entities()))
            self.assert_native_arc_radii(project.model, edges,
                                         [first_radius]*4+[second_radius]*4)
            planar = project.workplane.geom()
            fillets = [planar.feature(tag) for tag in planar.feature().tags()
                       if str(planar.feature(tag).getType()) == 'Fillet']
            self.assertEqual(len(fillets), group_count)
            for feature in fillets:
                self.assertIn('corner_radius', str(feature.getString('radius')))
            expected_area = 10*h+100-(4-pi)*(first_radius**2+second_radius**2)
            self.assertAlmostEqual(region(result).area()*project.dbu**2, expected_area, delta=0.08)
            # COMSOL's area uses its rendering mesh. Exact CAD arc radii are
            # checked above; retain a separate 0.5% allowance for this measure.
            self.assert_area(project, faces, result, expected_area, tolerance=expected_area*0.005)
        saved = self.client.load(str(project.mph_path))
        try:
            self.assert_native_arc_radii(saved, edges, [2.450196]*4+[4.9]*4)
            self.assertEqual(len(saved.java.component('comp1').selection(faces.tag).entities()), 2)
        finally:
            self.client.remove(saved)

    def test_fillet_trim_limit_native_hole_and_selected_corner(self):
        project, layer = self.project()
        edges = project.add_selection('hole_edges', entity='edge')
        faces = project.add_selection('hole_face')
        outer = Rectangle(project, layer=layer, size=(40, 30))
        hole = Rectangle(project, layer=layer, size=(10, 6))
        rounded = outer.difference(hole).fillet(
            radius=10, max_trim_fraction=0.49, selections=[edges, faces])
        project.build()
        self.assertEqual(len(faces.entities()), 1)
        self.assert_native_arc_radii(project.model, edges, [10]*4+[2.94]*4)
        expected_area = 1140-(4-pi)*(10**2-2.94**2)
        self.assertAlmostEqual(region(rounded).area()*project.dbu**2, expected_area, delta=0.08)
        self.assert_area(project, faces, rounded, expected_area, tolerance=expected_area*0.005)

        other_project, other_layer = self.project()
        selected_edges = other_project.add_selection('one_corner', entity='edge')
        rectangle = Rectangle(other_project, layer=other_layer, size=(10, 5))
        rectangle.fillet(radius=10, corners=[(-5, -2.5)], max_trim_fraction=0.49,
                         selections=[selected_edges])
        other_project.build()
        self.assert_native_arc_radii(other_project.model, selected_edges, [2.45])

    def test_fillet_trim_limit_numeric_and_nanometre_radius_units(self):
        project, layer = self.project()
        edges = project.add_selection('rounded_edges', entity='edge')
        source = Rectangle(project, layer=layer, size=(10, 6))
        rounded = source.fillet(radius=1, max_trim_fraction=0.49, selections=[edges])
        project.build()
        self.assert_native_arc_radii(project.model, edges, [1]*4)

        radius = Parameter(1000, 'trim_radius_nm', unit='nm')
        rounded.radius = radius
        project.build()
        self.assert_native_arc_radii(project.model, edges, [1]*4)
        self.assertIn('trim_radius_nm', str(project.workplane.geom().feature(rounded.tag).getString('radius')))
        radius.value = 2000
        project.build()
        self.assert_native_arc_radii(project.model, edges, [2]*4)
        rounded.radius = 1
        rounded.max_trim_fraction = None
        project.build()
        self.assert_native_arc_radii(project.model, edges, [1]*4)
        rounded.radius = 10
        rounded.max_trim_fraction = 0.49
        project.build()
        self.assert_native_arc_radii(project.model, edges, [2.94]*4)

    def test_corners_selected_vertices_parameters_and_readback(self):
        for operation, keyword, expected in ((Fillet, "radius", 59+pi/4), (Chamfer, "distance", 59.5)):
            project, layer = self.project()
            group = project.add_selection("result")
            inherited = project.add_selection("inherited")
            amount = Parameter(1000, "amount", unit="nm")
            corners = Vertices([(-5, -3)])
            source = Rectangle(project, layer=layer, size=(10, 6), selections=[inherited])
            result = operation(source, **{keyword: amount}, corners=corners, selections=[group])
            project.build()
            project.build()
            self.assert_area(project, group, result, expected)
            self.assertEqual(group.entities(), inherited.entities())
            amount.value = 2000
            corners[0] = (5, 3)
            project.build()
            expected = 56+pi if operation is Fillet else 58
            self.assert_area(project, group, result, expected)
            saved = self.client.load(str(project.mph_path))
            try:
                feature = saved.java.component('comp1').geom('geom1').feature('wp1').geom().feature(result.tag)
                self.assertEqual(str(feature.getType()), operation.__name__)
                self.assertIn("amount", str(feature.getString("radius" if operation is Fillet else "dist")))
                self.assertAlmostEqual(selected_measure(saved, group).getArea(), expected, delta=0.01)
            finally:
                self.client.remove(saved)

    def test_all_corners_and_holes(self):
        for operation, options in ((Fillet, {"radius": 1}), (Chamfer, {"distance": 1})):
            project, layer = self.project()
            group = project.add_selection("result")
            base = Rectangle(project, layer=layer, size=(20, 20))
            hole = Rectangle(project, layer=layer, size=(10, 10))
            result = operation(base.difference(hole), selections=[group], **options)
            project.build()
            self.assert_area(project, group, result, 300)

    def test_corner_outputs_feed_later_operations_in_sequence(self):
        for operation, options, area in ((Fillet, {"radius": 1}, 56+pi),
                                         (Chamfer, {"distance": 1}, 58)):
            project, layer = self.project()
            group = project.add_selection("transformed")
            source = Rectangle(project, layer=layer, size=(10, 6))
            edited = operation(source, **options)
            result = edited.rotate(angle=30).scale(factor=(2, 1), selections=[group])
            project.build()
            project.build()
            self.assert_area(project, group, result, 2*area, tolerance=0.08)

    def test_append_transform_after_built_corner_or_thicken_chain(self):
        for live in (False, True):
            for kind in ("fillet", "thicken"):
                project, layer = self.project()
                project.live = live
                group = project.add_selection("result")
                if kind == "fillet":
                    source = Rectangle(project, layer=layer, size=(10, 6))
                    edited = source.fillet(radius=1)
                    area = 56+pi
                else:
                    source = LineSegment(project, layer=layer, p1=(0, 0), p2=(10, 0))
                    edited = source.thicken(width=2)
                    area = 20
                rotated = edited.rotate(angle=30)
                project.build()
                # Existing operations are refreshed before this new feature is
                # appended; their inspection builds must not reorder the graph.
                result = rotated.scale(factor=2, selections=[group])
                project.build()
                self.assert_area(project, group, result, 4*area, tolerance=0.1)

    def test_offset_grow_shrink_keep_and_curve_direction(self):
        for reverse, corner, expected in ((False, "fillet", 92+pi), (True, "fillet", 32),
                                           (False, "extend", 96)):
            project, layer = self.project()
            group = project.add_selection("result")
            source = Rectangle(project, layer=layer, size=(10, 6))
            result = Offset(source, distance=1, reverse=reverse, corner=corner, selections=[group])
            project.build()
            self.assert_area(project, group, result, expected)
        project, layer = self.project()
        left_group = project.add_selection("left", entity="edge")
        right_group = project.add_selection("right", entity="edge")
        source = LineSegment(project, layer=layer, p1=(0, 0), p2=(10, 0))
        Offset(source, distance=2, keep=True, selections=[left_group])
        Offset(source, distance=1, reverse=True, selections=[right_group])
        project.build()
        for group, expected_y in ((left_group, 2), (right_group, -1)):
            points = native_edge_points(project.model, group, 3)
            self.assertTrue(all(abs(point[1]-expected_y) < 1e-7 for point in points))

    def test_thicken_caps_curves_boundaries_and_rebuild(self):
        for mode, expected in (("straight", 20), ("circular", 20+pi),
                               ("boundary", 60+pi), ("arc", 10*pi)):
            project, layer = self.project()
            group = project.add_selection("result")
            width = Parameter(2, "width", unit="um")
            if mode == "boundary":
                source = Rectangle(project, layer=layer, size=(10, 6))
            elif mode == "arc":
                source = CircularArc(project, layer=layer, radius=10, start_angle=0, end_angle=90)
            else:
                source = LineSegment(project, layer=layer, p1=(0, 0), p2=(10, 0))
            result = Thicken2D(source, width=width,
                               ends="circular" if mode == "circular" else "straight", selections=[group])
            project.build()
            project.build()
            self.assert_area(project, group, result, expected)
            if mode == "arc":
                width.value = 4
                project.build()
                self.assert_area(project, group, result, 20*pi, tolerance=0.08)

    def test_example_twice_and_parameter_vertex_edits(self):
        directory = Path(__file__).resolve().parents[1] / 'examples'
        original = Project.__init__
        def remember(project, *args, **kwargs):
            original(project, *args, **kwargs)
            self.projects.append(project)
        previous = Path.cwd()
        try:
            os.chdir(self.folder.name)
            for _ in range(2):
                with patch.object(Project, "__init__", remember), patch.object(Project, "show"):
                    namespace = runpy.run_path(str(directory/"example_planar_operations.py"))
                project = namespace["project"]
                self.assertTrue(project.gds_path.exists())
                self.assertTrue(project.mph_path.exists())
            namespace["radius"].value = 3
            namespace["width"].value = 3
            namespace["distance"].value = 1.5
            namespace["outline"][2] = (47, 32)
            project.build()
            # COMSOL getArea uses a rendering mesh; its accuracy depends on
            # the size of the whole gallery, not only this rounded rectangle.
            self.assert_area(project, namespace["rounded_faces"], namespace["rounded"],
                             240-9*(4-pi), tolerance=0.15)
            self.assert_area(project, namespace["track_faces"], namespace["rotated_track"],
                             22.5*pi+2.25*pi, tolerance=0.15)
        finally:
            os.chdir(previous)

    def test_thicken_ignores_boolean_interior_interfaces(self):
        project, layer = self.project()
        group = project.add_selection("band")
        first = Rectangle(project, layer=layer, size=(10, 6), position=(0, 0))
        second = Rectangle(project, layer=layer, size=(10, 6), position=(5, 0))
        joined = first.union(second, interior_boundaries=True)
        result = joined.thicken(width=2, selections=[group])
        project.build()
        # The occupied union is a 15 x 6 rectangle; interior interfaces must
        # not become extra metal strips in the COMSOL footprint.
        self.assert_area(project, group, result, 80+pi)
