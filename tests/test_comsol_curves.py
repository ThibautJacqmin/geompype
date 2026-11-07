"""Native point/curve dimensions, parameters and saved centreline geometry."""

from math import cos, hypot, pi, sin, sqrt
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from comsol_support import get_client
from geompype import Parameter, Project, Vertices
from geompype.primitives import (
    CircularArc, CubicBezier, InterpolationCurve, LineSegment, ParametricCurve,
    Point, QuadraticBezier,
)


def selected_measure(model, group):
    from jpype import JArray, JInt

    component = model.java.component("comp1")
    selection = component.selection(group.tag)
    measure = component.geom("geom1").measureFinal()
    measure.selection().geom(JInt(group.dimension))
    measure.selection().set(JArray(JInt)(list(selection.entities())))
    return measure


def native_edge_points(model, group, count=1001):
    """Evaluate the real edge, without relying on its internal parameter scale.

    COMSOL 6.4 GeomInfo documents edgeParamRange and edgeX; the latter returns
    one coordinate row per parameter value. Our cases deliberately have one
    uninterrupted edge per named selection.
    """
    from jpype import JArray, JDouble, JInt

    component = model.java.component("comp1")
    selection = component.selection(group.tag)
    edges = list(selection.entities())
    if selection.dim() != 1 or len(edges) != 1:
        raise AssertionError("Expected one native edge in the curve selection.")
    geometry = component.geom("geom1")
    edge = JInt(edges[0])
    start, end = map(float, geometry.edgeParamRange(edge))
    parameters = JArray(JDouble)([start + (end - start)*i/(count - 1)
                                 for i in range(count)])
    return [tuple(map(float, point)) for point in geometry.edgeX(edge, parameters)]


def distance_to_polyline(point, vertices):
    best = float("inf")
    x, y = point[:2]
    for start, end in zip(vertices, vertices[1:]):
        ax, ay = start[:2]
        bx, by = end[:2]
        dx, dy = bx - ax, by - ay
        denominator = dx*dx + dy*dy
        t = 0 if denominator == 0 else max(0, min(1, ((x - ax)*dx + (y - ay)*dy)/denominator))
        best = min(best, hypot(x - ax - t*dx, y - ay - t*dy))
    return best


def sampled_native_length(model, group):
    """Use dense exact-edge evaluations instead of the rendering-mesh measure."""
    points = native_edge_points(model, group)
    return sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def read_paths(path, layer_number):
    import klayout.db as kdb

    layout = kdb.Layout()
    layout.read(str(path))
    shapes = list(layout.top_cell().shapes(layout.layer(layer_number, 0)).each())
    if any(not shape.is_path() for shape in shapes):
        raise AssertionError("Curve output must remain GDS paths, without filled markers.")
    return layout.dbu, [shape.path.to_dtype(layout.dbu) for shape in shapes]


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolCurves(unittest.TestCase):
    def assert_point(self, model, group, expected):
        component = model.java.component("comp1")
        selection = component.selection(group.tag)
        self.assertEqual(selection.dim(), 0)
        entities = list(selection.entities())
        self.assertEqual(len(entities), 1)
        coordinates = component.geom("geom1").getVertexCoord()
        actual = [row[int(entities[0]) - 1] for row in coordinates]
        self.assertEqual(len(actual), 3)
        for value, target in zip(actual, (*expected, 0)):
            self.assertAlmostEqual(value, target, delta=1e-8)

    def assert_curve_matches_gds(self, model, group, gds_path, layer_number, tolerance):
        dbu, paths = read_paths(gds_path, layer_number)
        self.assertEqual(len(paths), 1)
        path = paths[0]
        self.assertEqual(path.width, 0)
        sampled = [(point.x, point.y) for point in path.each_point()]
        actual = native_edge_points(model, group)
        # The native edge is sampled more densely than the test GDS path.
        # Include the final grid error as well as curve discretization.
        limit = tolerance + sqrt(2)*dbu + 1e-5
        self.assertLessEqual(max(distance_to_polyline(point, sampled) for point in actual), limit)
        self.assertLessEqual(max(distance_to_polyline(point, actual) for point in sampled), limit)
        self.assertTrue(all(abs(point[2]) < 1e-8 for point in actual))
        endpoints = (actual[0][:2], actual[-1][:2])
        self.assertLessEqual(min(hypot(sampled[0][0] - p[0], sampled[0][1] - p[1])
                                 for p in endpoints), limit)
        self.assertLessEqual(min(hypot(sampled[-1][0] - p[0], sampled[-1][1] - p[1])
                                 for p in endpoints), limit)

    def test_point_and_line_both_modes_native_edits_and_saved_models(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(client=client, live=live,
                                      output=Path(folder) / f"point_line_{live}")
                    layer = project.add_layer("construction", gds_layer=41)
                    points = project.add_selection("anchor", entity="point")
                    edges = project.add_selection("centreline", entity="edge")
                    length = Parameter(4000, "length", unit="nm")
                    anchor_x = Parameter(20, "anchor_x", unit="um")
                    point_position = Vertices([anchor_x, 1])
                    try:
                        point = Point(project, layer=layer, position=point_position,
                                      selections=[points])
                        line = LineSegment(project, layer=layer, p2=(length, 0),
                                           selections=[edges])
                        point.rotate(angle=90)
                        line.rotate(angle=90)
                        project.build()
                        project.build()
                        plane = project.workplane.geom()
                        self.assertEqual(plane.feature(point.tag).getType(), "Point")
                        self.assertEqual(plane.feature(line.tag).getType(), "LineSegment")
                        self.assertEqual(sum(str(plane.feature(tag).getType()) != "ExplicitSelection"
                                             for tag in plane.feature().tags()), 4)
                        self.assertIn("anchor_x", str(plane.feature(point.tag).getStringArray("p")[0]))
                        self.assertEqual(str(plane.feature(line.tag).getStringArray("coord2")[0]), "length")
                        self.assert_point(project.model, points, (-1, 20))
                        self.assertAlmostEqual(selected_measure(project.model, edges).getLength(),
                                               4, delta=1e-7)
                        self.assert_curve_matches_gds(project.model, edges, project.gds_path, 41, 1e-7)

                        length.value, anchor_x.value = 6000, 30
                        point_position[0, 1] = 2
                        project.build()
                        self.assert_point(project.model, points, (-2, 30))
                        self.assertAlmostEqual(selected_measure(project.model, edges).getLength(),
                                               6, delta=1e-7)
                        self.assert_curve_matches_gds(project.model, edges, project.gds_path, 41, 1e-7)
                        gds_before = project.gds_path.read_bytes()

                        project.model.java.param().set("length", "8[um]")
                        project.model.java.param().set("anchor_x", "40[um]")
                        project.geometry.run()
                        self.assert_point(project.model, points, (-2, 40))
                        self.assertAlmostEqual(selected_measure(project.model, edges).getLength(),
                                               8, delta=1e-7)
                        self.assertEqual(length.value, 6000)
                        self.assertEqual(project.gds_path.read_bytes(), gds_before)

                        saved_path = Path(folder) / f"point_line_native_{live}.mph"
                        project.model.java.save(str(saved_path), True)
                        saved = client.load(str(saved_path))
                        try:
                            self.assert_point(saved, points, (-2, 40))
                            self.assertAlmostEqual(selected_measure(saved, edges).getLength(),
                                                   8, delta=1e-7)
                            saved_plane = saved.java.component("comp1").geom("geom1").feature("wp1").geom()
                            self.assertEqual(str(saved_plane.feature(line.tag).getStringArray("coord2")[0]),
                                             "length")
                            self.assertIn("anchor_x", str(saved_plane.feature(point.tag).getStringArray("p")[0]))
                        finally:
                            client.remove(saved)
                    finally:
                        if project.model is not None:
                            client.remove(project.model)

    def test_arc_and_rational_beziers_match_native_edges_and_saved_gds(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, dbu=0.0001,
                              output=Path(folder) / "curves")
            layers = [project.add_layer(name, gds_layer=number)
                      for name, number in (("arc", 42), ("quadratic", 43), ("cubic", 44))]
            groups = [project.add_selection(name, entity="edge")
                      for name in ("arc", "quadratic", "cubic")]
            radius = Parameter(2, "radius", unit="um")
            weight = Parameter(sqrt(0.5), "middle_weight")
            height = Parameter(3, "height", unit="um")
            quadratic_controls = Vertices([[radius, 0], [radius, radius], [0, radius]]) + [40, 0]
            tolerance = 0.001
            try:
                arc = CircularArc(project, layer=layers[0], center=(20, 0), radius=radius,
                                  start_angle=0, end_angle=90, tolerance=tolerance,
                                  selections=[groups[0]])
                quadratic = QuadraticBezier(project, layer=layers[1],
                                            p0=quadratic_controls[0], p1=quadratic_controls[1],
                                            p2=quadratic_controls[2], weights=(1, weight, 1),
                                            tolerance=tolerance, selections=[groups[1]])
                cubic = CubicBezier(project, layer=layers[2],
                                    p0=(60, 0), p1=(61, height), p2=(63, -1), p3=(64, 0),
                                    tolerance=tolerance, selections=[groups[2]])
                project.build()
                plane = project.workplane.geom()
                curves = (arc, quadratic, cubic)
                for curve, kind in zip(curves, ("CircularArc", "QuadraticBezier", "CubicBezier")):
                    self.assertEqual(plane.feature(curve.tag).getType(), kind)
                self.assertEqual(str(plane.feature(arc.tag).getString("r")), "radius")
                self.assertIn("middle_weight", list(plane.feature(quadratic.tag).getStringArray("w")))
                quadratic_tokens = [str(token) for row in plane.feature(quadratic.tag).getStringMatrix("p")
                                    for token in row]
                cubic_tokens = [str(token) for row in plane.feature(cubic.tag).getStringMatrix("p")
                                for token in row]
                self.assertTrue(any("radius" in token for token in quadratic_tokens))
                self.assertTrue(any("height" in token for token in cubic_tokens))
                for group, number in zip(groups, (42, 43, 44)):
                    self.assert_curve_matches_gds(project.model, group, project.gds_path, number, tolerance)
                for group in groups[:2]:
                    self.assertAlmostEqual(sampled_native_length(project.model, group),
                                           pi, delta=1e-5)

                radius.value, height.value = 3, 5
                project.build()
                for group, number in zip(groups, (42, 43, 44)):
                    self.assert_curve_matches_gds(project.model, group, project.gds_path, number, tolerance)
                arc.clockwise = True
                project.build()
                self.assert_curve_matches_gds(project.model, groups[0], project.gds_path, 42, tolerance)
                self.assertAlmostEqual(sampled_native_length(project.model, groups[0]),
                                       4.5*pi, delta=5e-5)
                arc.clockwise = False
                project.build()
                saved = client.load(str(project.mph_path))
                try:
                    for group, number in zip(groups, (42, 43, 44)):
                        self.assert_curve_matches_gds(saved, group, project.gds_path, number, tolerance)
                    self.assertEqual(str(saved.java.param().get("middle_weight")), weight.definition)
                    saved.java.param().set("radius", "4[um]")
                    saved.java.component("comp1").geom("geom1").run()
                    for group in groups[:2]:
                        self.assertAlmostEqual(sampled_native_length(saved, group),
                                               2*pi, delta=2e-5)
                finally:
                    client.remove(saved)
            finally:
                if project.model is not None:
                    client.remove(project.model)

    def test_interpolation_and_parametric_native_features_and_samplers(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, dbu=0.0001,
                              output=Path(folder) / "sampled_curves")
            interpolation_layer = project.add_layer("interpolation", gds_layer=45)
            parametric_layer = project.add_layer("parametric", gds_layer=46)
            interpolation_group = project.add_selection("interpolation", entity="edge")
            parametric_group = project.add_selection("parametric", entity="edge")
            span = Parameter(10, "span", unit="um")
            radius = Parameter(2000, "radius", unit="nm")
            stop = Parameter(pi/2, "stop")
            points = Vertices([[0, 10], [span/2, 10], [span, 10]])
            tolerance = 0.001
            try:
                # A straight spline has a known locus independently of the
                # interpolation kernel's choice of internal parameterization.
                interpolation = InterpolationCurve(
                    project, layer=interpolation_layer, points=points,
                    sampler=lambda s: (span*s, 10), parameters=(span,),
                    tolerance=tolerance, selections=[interpolation_group])
                parametric = ParametricCurve(
                    project, layer=parametric_layer,
                    coord=("radius*cos(s)", "radius*sin(s)"),
                    parname="s", parmin=0, parmax=stop,
                    sampler=lambda s: (radius*cos(s), radius*sin(s)),
                    parameters=(radius,), tolerance=tolerance,
                    selections=[parametric_group])
                project.build()
                plane = project.workplane.geom()
                self.assertEqual(plane.feature(interpolation.tag).getType(), "InterpolationCurve")
                self.assertEqual(plane.feature(parametric.tag).getType(), "ParametricCurve")
                self.assertEqual(str(plane.feature(interpolation.tag).getString("type")), "open")
                self.assertTrue(any("span" in str(token)
                                    for token in plane.feature(interpolation.tag).getStringArray("x")))
                self.assertEqual(list(plane.feature(parametric.tag).getStringArray("coord")),
                                 ["radius*cos(s)", "radius*sin(s)"])
                self.assertEqual(str(plane.feature(parametric.tag).getString("parmax")), "stop")
                for group, layer_number in ((interpolation_group, 45), (parametric_group, 46)):
                    self.assert_curve_matches_gds(project.model, group, project.gds_path,
                                                  layer_number, tolerance)
                self.assertAlmostEqual(sampled_native_length(project.model, interpolation_group),
                                       10, delta=1e-5)

                span.value, radius.value, stop.value = 12, 3000, pi/3
                project.build()
                for group, layer_number in ((interpolation_group, 45), (parametric_group, 46)):
                    self.assert_curve_matches_gds(project.model, group, project.gds_path,
                                                  layer_number, tolerance)
                saved = client.load(str(project.mph_path))
                try:
                    for group, layer_number in ((interpolation_group, 45), (parametric_group, 46)):
                        self.assert_curve_matches_gds(saved, group, project.gds_path,
                                                      layer_number, tolerance)
                    saved.java.param().set("span", "16[um]")
                    saved.java.param().set("radius", "4[um]")
                    saved.java.param().set("stop", "pi/2")
                    saved.java.component("comp1").geom("geom1").run()
                    self.assertAlmostEqual(sampled_native_length(saved, interpolation_group),
                                           16, delta=1e-5)
                    for x, y, z in native_edge_points(saved, parametric_group):
                        self.assertAlmostEqual(hypot(x, y), 4, delta=0.0001)
                        self.assertAlmostEqual(z, 0, delta=1e-8)
                finally:
                    client.remove(saved)
            finally:
                if project.model is not None:
                    client.remove(project.model)
