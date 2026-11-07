"""Numeric and symbolic parameter calculations used in geometry construction."""

from math import nextafter, pi
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from geompype import DependentParameter, Parameter, Project, Square, Vertices, maximum, round_nearest
from geompype.parameters import collect_parameters, comsol_expression, evaluate
from test_parameter_geometry import RecordedGeometry, read_region


class TestParameterPatterns(unittest.TestCase):
    def test_tower_widths_centres_and_sampling_count(self):
        um = Parameter(1, "u_ex1", unit="um")
        pitch = Parameter(36, "pitch_y1", unit="um")
        base = Parameter(260, "tower_w0", unit="um")
        step = Parameter(32, "tower_dw", unit="um")
        widths = [base - step * k for k in range(6)]
        centres = [Vertices([0, k]) * pitch for k in range(6)]
        corner = um * Vertices([-190, -10])
        radius = Parameter(8, "fillet_r", unit="um")
        count = DependentParameter(maximum(8, round(3 * radius / um)), "fillet_n")
        self.assertEqual([evaluate(w, "um") for w in widths], [260, 228, 196, 164, 132, 100])
        self.assertEqual([p.yvalue[0] for p in centres], [0, 36, 72, 108, 144, 180])
        self.assertEqual(corner.value, [[-190, -10]])
        self.assertEqual(count.value, 24)
        self.assertIn("fillet_r", count.definition)
        radius.value, base.value, pitch.value = 2, 300, 40
        self.assertEqual(count.value, 8)
        self.assertEqual(evaluate(widths[-1], "um"), 140)
        self.assertEqual(centres[-1].value, [[0, 200]])

    def test_array_steps_and_explicit_numeric_snapshot(self):
        nx, ny = Parameter(5, "arr_nx"), Parameter(3, "arr_ny")
        px = Parameter(70, "arr_pitch_x", unit="um")
        py = Parameter(70, "arr_pitch_y", unit="um")
        dx, dy = px * Vertices([1, 0]), Vertices([0, 1], py)
        far_corner = dx * (nx - 1) + dy * (ny - 1)
        self.assertEqual(far_corner.value, [[280, 140]])
        py.value, nx.value = 80, 6
        self.assertEqual(far_corner.value, [[350, 160]])
        lattice = Parameter(46, "lat_a", unit="um")
        snapshot = lattice.value
        point = Vertices([1, 0], lattice)
        lattice.value = 50
        self.assertEqual(snapshot, 46)
        self.assertEqual(point.value, [[50, 0]])

    def test_curve_points_and_dependent_thickness(self):
        um = Parameter(1, "u_ex3", unit="um")
        seed = Parameter(0.25, "line_thk_seed", unit="um")
        thickness = DependentParameter(seed + 0.15 * um, "line_thk")
        raw_points = [[-300, -155], [-255, -125], [-205, -165], [-145, -130]]
        points = Vertices(raw_points, um)
        self.assertAlmostEqual(thickness.value, 0.4)
        self.assertEqual(points.value, raw_points)
        self.assertEqual(list(points.parameters), ["u_ex3"])
        seed.value = 0.5
        self.assertAlmostEqual(thickness.value, 0.65)
        # Constants used as parametric-curve bounds are dimensionless.
        bound = Parameter(2*pi, "pc2_smax")
        self.assertAlmostEqual(evaluate(bound, ""), 2*pi)

    def test_named_ratio_can_be_registered_without_a_feature(self):
        um = Parameter(1, "u_ex4", unit="um")
        offset_seed = Parameter(0.35, "off_seed", unit="um")
        thickness_seed = Parameter(0.25, "line_thk_seed", unit="um")
        offset = DependentParameter(offset_seed + 0.15 * um, "off_dist")
        thickness = DependentParameter(thickness_seed + 0.1 * um, "line_thk")
        ratio = DependentParameter(thickness / offset, "dummy", unit="")
        with TemporaryDirectory() as folder, patch("geompype.project.get_client") as connect:
            project = Project(live=True, output=Path(folder) / "ratio")
            project.add_layer("gds_only", comsol=False)
            self.assertIs(project.add_parameter(ratio), ratio)
            self.assertIs(project.add_parameter(ratio), ratio)
            self.assertAlmostEqual(ratio.value, 0.7)
            self.assertEqual(list(project.parameters).count("dummy"), 1)
            project.build()
            thickness_seed.value = 0.4
            project.build()
            self.assertAlmostEqual(ratio.value, 1)
            self.assertIn("line_thk", ratio.definition)
            self.assertIn("off_dist", ratio.definition)
            connect.assert_not_called()

    def test_width_offset_lists_and_shared_marker_parameter(self):
        widths = [Parameter(16, "bus_wL", unit="um"), Parameter(16, "bus_wR", unit="um"),
                  Parameter(42, "bus_shield", unit="um")]
        offsets = [Parameter(-24, "bus_off_L", unit="um"), Parameter(24, "bus_off_R", unit="um"), 0]
        edges = [offset + width / 2 for offset, width in zip(offsets, widths)]
        self.assertEqual([evaluate(v, "um") for v in edges], [-16, 32, 21])
        reversed_offsets = [-v for v in offsets]
        self.assertEqual([evaluate(v, "um") for v in reversed_offsets], [24, -24, 0])
        widths[0].value = 20
        self.assertEqual(evaluate(edges[0], "um"), -14)
        marker = Parameter(8, "ex5_tip_E", unit="um")
        self.assertEqual(list(collect_parameters([marker, marker])), ["ex5_tip_E"])
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            collect_parameters([marker, Parameter(8, "ex5_tip_E", unit="um")])

    def test_numeric_nm_coordinates_need_explicit_conversion(self):
        centres = Vertices([[2500, 0], [1700, 300], [200, -1200]], unit="nm")
        self.assertEqual(centres.value, [[2.5, 0], [1.7, 0.3], [0.2, -1.2]])
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "nm")
            layer = project.add_layer("metal", comsol=False)
            Square(project, layer=layer, side=Parameter(7000, "width", unit="nm"),
                   position=centres[0])
            project.build()
            layout, region = read_region(project)
            self.assertAlmostEqual(region.area() * layout.dbu**2, 49)
            self.assertAlmostEqual(region.bbox().right * layout.dbu, 6)

    def test_rounding_ties_function_dependencies_and_bad_units(self):
        value = Parameter(0, "input_value")
        rounded = DependentParameter(round_nearest(value), "rounded")
        limited = DependentParameter(maximum(0, rounded), "limited")
        for number, expected in [(0.5, 1), (-0.5, -1), (2.5, 3), (-2.5, -3),
                                 (nextafter(0.5, 0), 0), (4503599627370497, 4503599627370497)]:
            value.value = number
            self.assertEqual(rounded.value, expected)
            self.assertEqual(limited.value, max(0, expected))
        self.assertEqual(list(collect_parameters([limited])), ["input_value", "rounded", "limited"])
        length = Parameter(1, "length", unit="um")
        with self.assertRaises(ValueError):
            maximum(length, 8)
        with self.assertRaises(ValueError):
            round(length)
        with self.assertRaises(ValueError):
            round(value, 2)
        with self.assertRaises(ValueError):
            limited.expression = maximum(limited, 1)
        with self.assertRaises(ValueError):
            rounded.expression = maximum(rounded, 1)

    def test_registered_parameters_are_emitted_refreshed_and_checked_atomically(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "registered")
            layer = project.add_layer("metal", gds=False)
            width = Parameter(4, "width", unit="um")
            unused = DependentParameter(width / width, "unused")
            project.add_parameter(unused)
            Square(project, layer=layer, side=width)
            before = project.parameters
            with self.assertRaises(ValueError):
                project.add_parameter(Parameter(5, "width", unit="um"))
            with self.assertRaises(TypeError):
                project.add_parameter(width * 2)
            self.assertEqual(project.parameters, before)
            events, params = [], Mock()
            plane = RecordedGeometry(events)
            # This recorder checks parameters; it does not implement native topology.
            project._layer_selections.clear()
            project.model = SimpleNamespace(java=SimpleNamespace(
                param=lambda: params, component=lambda tag: object()))
            project.geometry = RecordedGeometry(events)
            workplane = project.geometry.create('wp1', 'WorkPlane')
            workplane.geom = lambda: plane
            project.geometry.run = Mock()
            with patch.object(project, "_save_comsol"):
                project.build()
                params.set.assert_any_call("unused", "(width/width)", "")
                width.value = 10
                project.build()
                params.set.assert_any_call("width", "10[um]", "")
