"""Coordinate tables keep physical units and live parameter dependencies."""

import unittest

import numpy as np

from geompype import DependentParameter, Parameter, Vertices
from geompype.parameters import evaluate


class TestVertices(unittest.TestCase):
    def assert_values(self, vertices, expected, unit="um"):
        actual = vertices.values(unit=unit)
        self.assertEqual(len(actual), len(expected))
        for row, target in zip(actual, expected):
            self.assertEqual(len(row), 2)
            for value, wanted in zip(row, target):
                self.assertAlmostEqual(value, wanted)

    def test_pairs_matrices_numpy_and_grids_have_a_consistent_row_order(self):
        self.assert_values(Vertices(), [[0, 0]])
        for pair in ([1, 2], (1, 2), np.array([1, 2])):
            with self.subTest(pair=type(pair).__name__):
                self.assert_values(Vertices(pair), [[1, 2]])
        points = [[1, 2], [3, 4], [5, 6], [7, 8]]
        grid = np.array(points).reshape(2, 2, 2)
        for data in (points, np.array(points), grid, grid.tolist()):
            vertices = Vertices(data)
            self.assert_values(vertices, points)
            self.assertEqual(len(vertices), 4)
            self.assertEqual(vertices.nvertices, 4)
            self.assertEqual(vertices.xvalue, [1, 3, 5, 7])
            self.assertEqual(vertices.yvalue, [2, 4, 6, 8])

    def test_numeric_containers_are_copied_but_parameter_references_are_retained(self):
        x = Parameter(10, "xpos", unit="um")
        raw = [[x, 1], [2, 3]]
        vertices = Vertices(raw)
        clone = Vertices(vertices)
        raw[0][0] = 999
        raw[1][1] = 999
        x.value = 20
        self.assert_values(vertices, [[20, 1], [2, 3]])
        self.assert_values(clone, [[20, 1], [2, 3]])
        self.assertIs(vertices.parameters["xpos"], x)
        self.assertIs(clone.parameters["xpos"], x)

    def test_mixed_units_inline_formulas_and_dependent_parameters_recalculate(self):
        width = Parameter(20, "width", unit="um")
        gap = Parameter(500, "gap", unit="nm")
        pitch = DependentParameter(width + 2 * gap, "pitch")
        vertices = Vertices(np.array([[pitch, gap], [0, width - gap]], dtype=object))
        self.assert_values(vertices, [[21, 0.5], [0, 19.5]])
        self.assert_values(vertices, [[21000, 500], [0, 19500]], unit="nm")
        self.assertEqual(list(vertices.parameters), ["width", "gap", "pitch"])
        expressions = vertices.to_comsol()
        self.assertEqual(expressions[0], ["pitch", "gap"])
        self.assertIn("width", expressions[1][1])
        self.assertIn("gap", expressions[1][1])
        gap.value = 1000
        self.assert_values(vertices, [[22, 1], [0, 19]])
        self.assertEqual(vertices.to_comsol(), expressions)

    def test_bare_coordinates_do_not_inherit_a_neighbours_unit(self):
        x = Parameter(500, "xpos", unit="nm")
        count = Parameter(2, "count")
        self.assert_values(Vertices([x, 2]), [[0.5, 2]])
        self.assert_values(Vertices([x, count]), [[0.5, 2]])
        nanometres = Vertices([[x, count], [1000, 2000]], unit="nm")
        self.assert_values(nanometres, [[0.5, 0.002], [1, 2]])
        self.assertIn("count", nanometres.to_comsol()[0][1])
        self.assertIn("[nm]", nanometres.to_comsol()[0][1])
        count.value = 3
        self.assert_values(nanometres, [[0.5, 0.003], [1, 2]])

    def test_shared_prefactor_and_length_scaling_on_either_side(self):
        pitch = Parameter(2, "pitch", unit="um")
        count = Parameter(3, "count")
        pattern = Vertices([[1, 0], [count, -1]])
        variants = [Vertices([[1, 0], [count, -1]], pitch),
                    pattern * pitch, pitch * pattern]
        for vertices in variants:
            self.assert_values(vertices, [[2, 0], [6, -2]])
            self.assertIs(vertices.parameters["pitch"], pitch)
            self.assertIs(vertices.parameters["count"], count)
        pitch.value = 500
        count.value = 4
        for vertices in variants:
            self.assert_values(vertices, [[500, 0], [2000, -500]])
        self.assert_values(Vertices([1, 2], 3, unit="nm"), [[0.003, 0.006]])
        with self.assertRaises((TypeError, ValueError)):
            _ = variants[0] * pitch
        with self.assertRaises((TypeError, ValueError)):
            Vertices([pitch, 0], pitch)

    def test_translation_broadcasts_a_point_on_either_side_and_preserves_units(self):
        x = Parameter(10, "xpos", unit="um")
        offset = Parameter(1000, "offset", unit="nm")
        points = Vertices([[x, 0], [2 * x, 5]])
        shift = Vertices([offset, 3])
        self.assert_values(points + shift, [[11, 3], [21, 8]])
        self.assert_values(shift + points, [[11, 3], [21, 8]])
        self.assert_values([1, 2] + points, [[11, 2], [21, 7]])
        self.assert_values([1, 2] - points, [[-9, 2], [-19, -3]])
        moved = points - shift
        self.assert_values(moved, [[9, -3], [19, 2]])
        x.value = 20
        offset.value = 500
        self.assert_values(moved, [[19.5, -3], [39.5, 2]])
        with self.assertRaises((TypeError, ValueError)):
            _ = points + Vertices([[0, 0], [1, 1], [2, 2]])
        with self.assertRaises((TypeError, ValueError)):
            _ = points + 1

    def test_scalar_arithmetic_keeps_every_coordinate_dependency(self):
        x = Parameter(10, "xpos", unit="um")
        y = Parameter(2000, "ypos", unit="nm")
        factor = Parameter(2, "factor")
        points = Vertices([x, y])
        scaled = factor * points / 4
        negative = -points
        self.assert_values(scaled, [[5, 1]])
        self.assert_values(negative, [[-10, -2]])
        self.assert_values(2 * points, [[20, 4]])
        x.value = 20
        y.value = 4000
        factor.value = 3
        self.assert_values(scaled, [[15, 3]])
        self.assert_values(negative, [[-20, -4]])
        self.assertEqual(set(scaled.parameters), {"xpos", "ypos", "factor"})
        for operation in (lambda: points / 0, lambda: 1 / points,
                          lambda: points / x, lambda: points * points):
            with self.assertRaises((TypeError, ValueError, ZeroDivisionError)):
                operation()

    def test_indexing_slicing_iteration_concat_and_centroid_retain_expressions(self):
        x = Parameter(10, "xpos", unit="um")
        points = Vertices([[x, 0], [2 * x, 4], [3 * x, 8]])
        first = points[0]
        tail = points[1:]
        joined = first.concat(tail)
        centre = joined.centroid()
        self.assertIsInstance(first, Vertices)
        self.assert_values(first, [[10, 0]])
        self.assert_values(points[-1], [[30, 8]])
        self.assertEqual(evaluate(points[1, 0], "um"), 20)
        self.assertEqual([point.value for point in points],
                         [[[10, 0]], [[20, 4]], [[30, 8]]])
        self.assert_values(centre, [[20, 4]])
        x.value = 5
        self.assert_values(joined, [[5, 0], [10, 4], [15, 8]])
        self.assert_values(centre, [[10, 4]])
        with self.assertRaises(IndexError):
            _ = points[3]

    def test_assignment_is_atomic_and_changes_are_visible_on_next_evaluation(self):
        x = Parameter(10, "xpos", unit="um")
        points = Vertices([[x, 1], [2, 3]])
        points[1] = [x / 2, 4]
        points[0, 1] = Parameter(500, "offset", unit="nm")
        self.assert_values(points, [[10, 0.5], [5, 4]])
        before = points.to_comsol()
        with self.assertRaises((TypeError, ValueError)):
            points[0] = [99, float("nan")]
        self.assertEqual(points.to_comsol(), before)
        with self.assertRaises((TypeError, ValueError)):
            points[1, 0] = Parameter(90, "angle", unit="deg")
        self.assertEqual(points.to_comsol(), before)
        x.value = 20
        self.assert_values(points, [[20, 0.5], [10, 4]])

    def test_empty_tables_have_consistent_outputs_and_no_centroid(self):
        for data in ([], np.empty((0, 2)), np.empty((2, 0, 2))):
            with self.subTest(shape=getattr(data, "shape", None)):
                empty = Vertices(data)
                self.assertEqual(empty.nvertices, 0)
                self.assertEqual(empty.value, [])
                self.assertEqual(empty.to_comsol(), [])
                self.assertEqual(empty.parameters, {})
                self.assertEqual(list(empty), [])
                self.assert_values(empty.concat(Vertices([1, 2])), [[1, 2]])
                with self.assertRaises(ValueError):
                    empty.centroid()

    def test_bad_shapes_values_and_units_are_rejected(self):
        invalid = [1, "12", [1], [1, 2, 3], [[1, 2], [3]],
                   [[[1, 2]], [[3, 4], [5, 6]]], [[[[1, 2]]]],
                   [True, 0], [1j, 0], [float("nan"), 0],
                   [0, float("inf")], ["xpos", 0], {0: 1, 1: 2},
                   np.empty((0, 3)), [Parameter(90, "angle", unit="deg"), 0]]
        for data in invalid:
            with self.subTest(data=repr(data)):
                with self.assertRaises((TypeError, ValueError)):
                    Vertices(data)
        with self.assertRaises(ValueError):
            Vertices([1, 2], unit="deg")

    def test_invalid_dependency_edits_are_detected_at_evaluation(self):
        count = Parameter(2, "count")
        coordinate = DependentParameter(10 / count, "coordinate")
        points = Vertices([coordinate, 0])
        self.assert_values(points, [[5, 0]])
        count.value = 0
        with self.assertRaises((ValueError, ZeroDivisionError)):
            _ = points.value
        count.value = 5
        self.assert_values(points, [[2, 0]])
        coordinate.expression = Parameter(90, "angle", unit="deg")
        with self.assertRaises(ValueError):
            points.to_comsol()

    def test_numpy_translation_nested_points_and_named_coordinate_formula(self):
        width = Parameter(10, "width", unit="um")
        first, second = Vertices([width, 1]), Vertices([2 * width, 2])
        points = Vertices([first, second])
        translated = np.array([1, 2]) + points
        self.assert_values(translated, [[11, 3], [21, 4]])
        coordinate = DependentParameter(translated[0, 1], "coordinate")
        self.assertAlmostEqual(coordinate.value, 3)
        width.value = 20
        self.assert_values(translated, [[21, 3], [41, 4]])
        for key in ((True, 0), (0, False)):
            with self.assertRaises(TypeError):
                _ = translated[key]


if __name__ == "__main__":
    unittest.main()
