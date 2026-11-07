"""Explicit curve samplers and native expression emission without COMSOL."""

from math import cos, hypot, pi, sin
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import DependentParameter, Parameter, Project, Vertices
from geompype._sampled_curves import sample_callback
from geompype.primitives import InterpolationCurve, ParametricCurve
from test_parameter_geometry import RecordedGeometry


def points_of(path):
    return [(point.x, point.y) for point in path.each_point()]


class TestParametricCurve(unittest.TestCase):
    def setUp(self):
        self.project = Project()
        self.layer = self.project.add_layer("curves", comsol=False)

    def test_quarter_circle_has_zero_width_and_geometric_refinement(self):
        radius = Parameter(2000, "radius", unit="nm")
        curve = ParametricCurve(
            self.project, layer=self.layer, coord=("radius*cos(s)", "radius*sin(s)"),
            parmax=pi/2, sampler=lambda s: (radius*cos(s), radius*sin(s)),
            parameters=(radius,), tolerance=0.0001,
        )
        path = curve.to_klayout()
        self.assertIsInstance(path, kdb.DPath)
        self.assertEqual(path.width, 0)
        points = points_of(path)
        self.assertEqual(points[0], (2, 0))
        self.assertAlmostEqual(points[-1][0], 0, places=12)
        self.assertAlmostEqual(points[-1][1], 2, places=12)
        length = sum(hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(points, points[1:]))
        self.assertLess(length, pi)
        self.assertAlmostEqual(length, pi, delta=0.0002)
        # The midpoint of each chord lies at most tolerance inside the circle.
        for a, b in zip(points, points[1:]):
            sagitta = 2 - hypot((a[0]+b[0])/2, (a[1]+b[1])/2)
            self.assertLessEqual(sagitta, 0.0001 + 1e-12)

    def test_sampler_returns_vertices_and_reads_current_parameter_values(self):
        width = Parameter(3, "width", unit="um")
        twice = DependentParameter(2*width, "twice")
        end = Parameter(1, "end_value")
        curve = ParametricCurve(
            self.project, layer=self.layer, coord=("twice*s", "width"), parmax=end,
            sampler=lambda s: Vertices((twice*s, width)), parameters=(twice,),
        )
        self.assertEqual(points_of(curve.to_klayout())[-1], (6, 3))
        width.value, end.value = 4, 2
        self.assertEqual(points_of(curve.to_klayout())[-1], (16, 4))
        self.assertIs(curve.parameters[0], twice)
        self.assertIs(curve.parmax, end)
        self.assertEqual(set(self.project.parameters), {"width", "twice", "end_value"})

    def test_native_formulas_and_parameter_bounds_are_preserved(self):
        radius = Parameter(5, "radius", unit="um")
        stop = Parameter(2, "stop")
        curve = ParametricCurve(
            self.project, layer=self.layer,
            coord=("radius*special_model_function(s)", "radius*sin(s)"),
            parname="s", parmin=-1, parmax=stop, parameters=(radius,),
        )
        geometry = RecordedGeometry([])
        curve.to_comsol(geometry, curve.tag)
        curve.to_comsol(geometry, curve.tag)
        self.assertEqual(len(geometry.features), 1)
        feature = geometry.features[curve.tag]
        self.assertEqual(feature.kind, "ParametricCurve")
        self.assertEqual(feature.values["coord"],
                         ["radius*special_model_function(s)", "radius*sin(s)"])
        self.assertEqual(feature.values["parname"], "s")
        self.assertEqual(feature.values["parmin"], "(-1)")
        self.assertEqual(feature.values["parmax"], "stop")
        self.assertNotIn("type", feature.values)

    def test_sampler_is_required_only_for_klayout_and_not_called_by_native_emission(self):
        layer = self.project.add_layer("native", gds=False)
        curve = ParametricCurve(self.project, layer=layer, coord=("native_x(s)", "native_y(s)"))
        with patch("geompype.project.get_client", side_effect=AssertionError("No connection expected")):
            curve.to_comsol(RecordedGeometry([]), curve.tag)
            curve.validate()
        with self.assertRaisesRegex(ValueError, "explicit sampler"):
            curve.to_klayout()
        curve.sampler = lambda _: (_ for _ in ()).throw(AssertionError("Sampler must not run"))
        curve.to_comsol(RecordedGeometry([]), curve.tag)

    def test_invalid_definitions_do_not_register_objects(self):
        invalid = [
            {"coord": "xy"}, {"coord": ("x",)}, {"coord": ("x", "")},
            {"coord": (1, "s")}, {"parname": "s;bad"}, {"parname": "pi"},
            {"parname": ""},
            {"parmin": 1, "parmax": 1}, {"parmax": float("inf")},
            {"parmin": -1e308, "parmax": 1e308},
            {"parmax": Parameter(2, "distance", unit="um")},
            {"sampler": "eval me"}, {"tolerance": 0}, {"tolerance": float("nan")},
            {"sampling_intervals": True}, {"sampling_intervals": 0},
            {"sampling_intervals": 1.5}, {"sampling_intervals": 16385},
            {"parameters": (3,)}, {"parameters": (Parameter(1, "s"),)},
            {"parameters": (Parameter(1, "same"), Parameter(2, "same"))},
        ]
        for options in invalid:
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    ParametricCurve(self.project, layer=self.layer,
                                    **({"coord": ("s", "0")} | options))
        self.assertEqual(self.project.objects, [])

    def test_sampler_errors_and_degenerate_paths_are_reported(self):
        for sampler in (lambda s: (s,), lambda s: (s, float("nan")),
                        lambda s: (s, 1j), lambda s: (s, 1/(s-s)), lambda s: (2, 3)):
            with self.subTest(sampler=sampler):
                curve = ParametricCurve(self.project, layer=self.layer,
                                        coord=("s", "0"), sampler=sampler)
                with self.assertRaises(ValueError):
                    curve.to_klayout()

    def test_sampling_handles_closed_curves_without_filling_them(self):
        curve = ParametricCurve(self.project, layer=self.layer,
                                coord=("cos(s)", "sin(s)"), parmax=2*pi,
                                sampler=lambda s: (cos(s), sin(s)), tolerance=0.001)
        path = curve.to_klayout()
        self.assertEqual(path.width, 0)
        self.assertGreater(len(points_of(path)), 32)
        self.assertAlmostEqual(path.length(), 2*pi, delta=0.003)

    def test_sampling_interval_control_and_vertex_limit(self):
        curve = ParametricCurve(self.project, layer=self.layer,
                                coord=("s", "sin(8*pi*s)"),
                                sampler=lambda s: (s, sin(8*pi*s)),
                                sampling_intervals=32, tolerance=0.001)
        ys = [point[1] for point in points_of(curve.to_klayout())]
        self.assertGreater(max(ys), 0.99)
        self.assertLess(min(ys), -0.99)
        with self.assertRaisesRegex(ValueError, "more than 16"):
            sample_callback(lambda s: (s, s*s), 0, 1, 1e-12, 1, maximum=16)

    def test_large_finite_parameter_domain_does_not_overflow_internal_knots(self):
        points = sample_callback(lambda s: (s / 1e308, 0), 0, 1e308, 0.001, 16)
        self.assertEqual(points[0], (0, 0))
        self.assertEqual(points[-1], (1, 0))
        self.assertEqual(len(points), 17)


class TestInterpolationCurve(unittest.TestCase):
    def setUp(self):
        self.project = Project()
        self.layer = self.project.add_layer("curves", comsol=False)

    def test_native_interpolation_uses_vector_expressions_without_polyline_fallback(self):
        pitch = Parameter(2, "pitch", unit="um")
        vertices = Vertices([[0, 0], [1, 1], [2, 0]], pitch)
        curve = InterpolationCurve(self.project, layer=self.layer, points=vertices)
        geometry = RecordedGeometry([])
        curve.to_comsol(geometry, curve.tag)
        feature = geometry.features[curve.tag]
        self.assertEqual(feature.kind, "InterpolationCurve")
        self.assertEqual(feature.values["type"], "open")
        self.assertEqual(feature.values["source"], "vectors")
        self.assertEqual(feature.values["rtol"], "0")
        self.assertEqual(feature.values["startcond"], "none")
        self.assertEqual(feature.values["endcond"], "none")
        self.assertEqual(feature.values["x"], ["(0*pitch)", "(1*pitch)", "(2*pitch)"])
        self.assertEqual(feature.values["y"], ["(0*pitch)", "(1*pitch)", "(0*pitch)"])
        self.assertIs(curve.points, vertices)
        self.assertIs(self.project.parameters["pitch"], pitch)
        vertices[1, 1] = pitch / 2
        curve.to_comsol(geometry, curve.tag)
        self.assertEqual(feature.values["y"][1], "(pitch/2)")

    def test_explicit_sampler_is_a_zero_width_path_and_updates_with_parameters(self):
        scale = Parameter(2000, "scale", unit="nm")
        points = Vertices([[0, 0], [0.5, 0.25], [1, 1]], scale)
        curve = InterpolationCurve(
            self.project, layer=self.layer, points=points,
            sampler=lambda s: (scale*s, scale*s*s), tolerance=0.0001,
        )
        sampled = curve.to_klayout()
        self.assertEqual(sampled.width, 0)
        self.assertEqual(points_of(sampled)[0], (0, 0))
        self.assertEqual(points_of(sampled)[-1], (2, 2))
        self.assertIn((1, 0.5), points_of(sampled))
        scale.value = 4000
        self.assertEqual(points_of(curve.to_klayout())[-1], (4, 4))
        # This tests the supplied evaluator, not equivalence to COMSOL's spline.

    def test_missing_sampler_allows_native_emission_and_fails_only_when_requested(self):
        curve = InterpolationCurve(self.project, layer=self.layer,
                                   points=[[0, 0], [1, 2], [2, 0]])
        curve.validate()
        curve.to_comsol(RecordedGeometry([]), curve.tag)
        with self.assertRaisesRegex(ValueError, "explicit sampler"):
            curve.to_klayout()

    def test_stale_sampler_endpoints_are_rejected_after_vertices_edit(self):
        vertices = Vertices([[0, 0], [1, 0], [2, 0]])
        curve = InterpolationCurve(self.project, layer=self.layer, points=vertices,
                                   sampler=lambda s: (2*s, 0), tolerance=0.001)
        self.assertEqual(points_of(curve.to_klayout())[-1], (2, 0))
        vertices[-1, 0] = 3
        with self.assertRaisesRegex(ValueError, "sampler endpoints"):
            curve.to_klayout()
        curve.sampler = lambda s: vertices[0] + (vertices[-1] - vertices[0])*s
        self.assertEqual(points_of(curve.to_klayout())[-1], (3, 0))
        # This numerical check does not replace checking the interior spline.

    def test_invalid_points_are_rejected_before_registration(self):
        for points in ([], [[0, 0]], [[0, 0], [0, 0], [1, 1]],
                       [[0, 0], [1, 1], [0, 0]], [[0, 0], [1, float("inf")]]):
            with self.subTest(points=points):
                with self.assertRaises(ValueError):
                    InterpolationCurve(self.project, layer=self.layer, points=points)
        self.assertEqual(self.project.objects, [])


if __name__ == "__main__":
    unittest.main()
