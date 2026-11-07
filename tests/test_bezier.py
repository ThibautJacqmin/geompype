"""Rational Bezier centreline geometry and retained native expressions."""

from math import comb, hypot, sqrt
import unittest

import klayout.db as kdb

from geompype import Parameter, Project, Vertices
from geompype.primitives import CubicBezier, QuadraticBezier, _bezier_sample
from test_parameter_geometry import RecordedGeometry


def rational_point(controls, weights, parameter):
    degree = len(controls) - 1
    factors = [weight * comb(degree, index) * parameter**index
               * (1 - parameter)**(degree - index)
               for index, weight in enumerate(weights)]
    return tuple(sum(factor * point[axis] for factor, point in zip(factors, controls))
                 / sum(factors) for axis in range(2))


def distance_to_polyline(point, vertices):
    distances = []
    for first, second in zip(vertices, vertices[1:]):
        dx, dy = second[0] - first[0], second[1] - first[1]
        squared = dx*dx + dy*dy
        fraction = (0 if squared == 0 else min(1, max(0,
                    ((point[0] - first[0])*dx + (point[1] - first[1])*dy) / squared)))
        distances.append(hypot(point[0] - first[0] - fraction*dx,
                               point[1] - first[1] - fraction*dy))
    return min(distances)


class TestBezier(unittest.TestCase):
    def setUp(self):
        self.project = Project()
        self.layer = self.project.add_layer("curves", comsol=False, gds=False)

    def test_quadratic_native_default_is_a_rational_quarter_circle(self):
        curve = QuadraticBezier(self.project, layer=self.layer,
                                p0=(1, 0), p1=(1, 1), p2=(0, 1), tolerance=0.0001)
        path = curve.to_klayout()
        self.assertIsInstance(path, kdb.DPath)
        self.assertEqual(path.width, 0)
        points = [(point.x, point.y) for point in path.each_point()]
        self.assertEqual(points[0], (1, 0))
        self.assertEqual(points[-1], (0, 1))
        self.assertGreater(len(points), 2)
        for x, y in points:
            self.assertAlmostEqual(hypot(x, y), 1, places=14)
        for first, second in zip(points, points[1:]):
            midpoint_radius = hypot((first[0] + second[0])/2, (first[1] + second[1])/2)
            self.assertLessEqual(1 - midpoint_radius, 0.0001)

    def test_polynomial_and_rational_curves_meet_geometric_tolerance(self):
        cases = [
            (QuadraticBezier, [(0, 0), (8, 12), (10, 0)], (1, 1, 1)),
            (CubicBezier, [(0, 0), (2, 8), (6, -5), (10, 1)], (1, 1, 1, 1)),
            (CubicBezier, [(0, 0), (2, 8), (6, -5), (10, 1)], (1, 0.2, 3, 2)),
            (CubicBezier, [(0, 0), (8, 10), (-8, 10), (0, 0)], (1, 1, 1, 1)),
        ]
        tolerance = 0.002
        for kind, controls, weights in cases:
            with self.subTest(kind=kind.__name__, controls=controls, weights=weights):
                curve = kind(self.project, layer=self.layer, weights=weights,
                             tolerance=tolerance,
                             **{f"p{index}": point for index, point in enumerate(controls)})
                path = curve.to_klayout()
                vertices = [(point.x, point.y) for point in path.each_point()]
                self.assertEqual(path.width, 0)
                self.assertEqual(vertices[0], controls[0])
                self.assertEqual(vertices[-1], controls[-1])
                for index in range(1001):
                    point = rational_point(controls, weights, index / 1000)
                    self.assertLessEqual(distance_to_polyline(point, vertices), tolerance * 1.000001)

    def test_collinear_reversal_is_not_replaced_by_endpoint_chord(self):
        curve = QuadraticBezier(self.project, layer=self.layer,
                                p0=(0, 0), p1=(10, 0), p2=(1, 0), weights=(1, 1, 1))
        vertices = list(curve.to_klayout().each_point())
        # The analytic extremum occurs at t=10/19, x=100/19.
        self.assertAlmostEqual(max(point.x for point in vertices), 100 / 19, delta=0.001)
        self.assertGreater(len(vertices), 2)

    def test_parameter_vertices_and_weights_are_re_evaluated(self):
        span = Parameter(4000, "span", unit="nm")
        height = Parameter(3, "height", unit="um")
        weight = Parameter(1, "weight")
        control = Vertices([span, height])
        curve = CubicBezier(self.project, layer=self.layer,
                            p0=(0, 0), p1=control, p2=(6, -2), p3=(2*span, 0),
                            weights=(1, weight, 1, 1))
        self.assertIs(curve.p1, control)
        self.assertIs(curve.weights[1], weight)
        original = curve.to_klayout()
        self.assertEqual(list(original.each_point())[-1], kdb.DPoint(8, 0))
        span.value = 6000
        weight.value = 2
        control[0, 1] = height * 2
        changed = curve.to_klayout()
        self.assertEqual(list(changed.each_point())[-1], kdb.DPoint(12, 0))
        self.assertNotEqual(changed, original)
        self.assertEqual(set(self.project.parameters), {"span", "height", "weight"})
        # Parametric mutation also reaches validation without freezing numbers.
        weight.value = 0
        with self.assertRaisesRegex(ValueError, "weights"):
            curve.validate()

    def test_native_types_expressions_and_repeated_emission(self):
        distance = Parameter(2000, "distance", unit="nm")
        weight = Parameter(0.7, "weight")
        for kind, arguments in [
            (QuadraticBezier, dict(p0=(0, 0), p1=Vertices([distance, distance]),
                                   p2=(2*distance, 0), weights=(1, weight, 1))),
            (CubicBezier, dict(p0=(0, 0), p1=(distance, distance), p2=(2*distance, -distance),
                               p3=(3*distance, 0), weights=(1, weight, 1, 1))),
        ]:
            with self.subTest(kind=kind.__name__):
                curve = kind(self.project, layer=self.layer, **arguments)
                plane = RecordedGeometry([])
                curve.to_comsol(plane, curve.tag)
                curve.to_comsol(plane, curve.tag)
                self.assertEqual(len(plane.features), 1)
                feature = plane.features[curve.tag]
                self.assertEqual(feature.kind, kind.__name__)
                self.assertEqual(len(feature.values["p"]), 2)
                self.assertIn("distance", feature.values["p"][0][1])
                self.assertIn("distance", feature.values["p"][1][1])
                self.assertEqual(feature.values["w"][1], "weight")
                self.assertNotIn("type", feature.values)

    def test_rotation_retains_a_zero_width_curve(self):
        curve = QuadraticBezier(self.project, layer=self.layer,
                                p0=(1, 0), p1=(1, 1), p2=(0, 1))
        result = curve.rotate(angle=90).to_klayout()
        self.assertIsInstance(result, kdb.DPath)
        self.assertEqual(result.width, 0)
        points = list(result.each_point())
        self.assertAlmostEqual(points[0].x, 0)
        self.assertAlmostEqual(points[0].y, 1)
        self.assertAlmostEqual(points[-1].x, -1)
        self.assertAlmostEqual(points[-1].y, 0)

    def test_invalid_input_does_not_register_geometry(self):
        defaults = dict(layer=self.layer, p0=(0, 0), p1=(1, 2), p2=(2, 0))
        invalid = [dict(weights=(1, 1)), dict(weights=(1, 0, 1)),
                   dict(weights=(1, -1, 1)), dict(weights=(1, float("inf"), 1)),
                   dict(weights=(1e-300, 1e300, 1)),
                   dict(weights=(1, Parameter(1, "bad", unit="um"), 1)),
                   dict(tolerance=0), dict(tolerance=-1), dict(tolerance=float("nan")),
                   dict(p1=(1,)), dict(p1=Vertices([[0, 0], [1, 1]])),
                   dict(p0=(0, 0), p1=(0, 0), p2=(0, 0)),
                   dict(p0=(-1e308, 0), p1=(0, 1), p2=(1e308, 0))]
        for arguments in invalid:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    QuadraticBezier(self.project, **(defaults | arguments))
        self.assertEqual(self.project.objects, [])

    def test_sampling_limit_is_explicit(self):
        # A quarter-circle cannot meet this tolerance with at most eight points.
        with self.assertRaisesRegex(ValueError, "more than 8"):
            _bezier_sample([(1, 0), (1, 1), (0, 1)], (1, 1/sqrt(2), 1), 1e-6, maximum=8)

