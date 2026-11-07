"""Parameter expressions retain references and use compatible physical units."""

from math import pi
import unittest

from geompype import DependentParameter, Parameter
from geompype.parameters import collect_parameters, comsol_expression, evaluate


class TestParameters(unittest.TestCase):
    def test_dependency_chain_recalculates_after_an_edit(self):
        width = Parameter(20, "width", unit="um", description="Conductor width")
        gap = Parameter(500, "gap", unit="nm")
        pitch = DependentParameter(width + 2 * gap, "pitch")
        span = DependentParameter(3 * pitch - gap, "span", unit="nm")
        self.assertAlmostEqual(pitch.value, 21)
        self.assertAlmostEqual(span.value, 62500)
        self.assertEqual(pitch.unit, "um")
        self.assertEqual(span.unit, "nm")

        width.value = 10
        gap.value = 1000
        self.assertAlmostEqual(pitch.value, 12)
        self.assertAlmostEqual(span.value, 35000)
        self.assertEqual(width.description, "Conductor width")
        self.assertIn("width", pitch.definition)
        self.assertIn("gap", pitch.definition)
        self.assertIn("pitch", span.definition)

    def test_arithmetic_precedence_reflected_operators_and_ratios(self):
        count = Parameter(3, "count")
        self.assertEqual(evaluate(12 / (count + 1), ""), 3)
        self.assertEqual(evaluate(10 - 2 * count, ""), 4)
        self.assertEqual(evaluate(-count + 5, ""), 2)
        self.assertEqual(evaluate((count + 1) * (count - 1), ""), 8)
        width = Parameter(20, "width", unit="um")
        gap = Parameter(500, "gap", unit="nm")
        self.assertEqual(evaluate(width / gap, ""), 40)
        self.assertAlmostEqual(evaluate(width * gap / width, "um"), 0.5)
        count.value = 5
        self.assertEqual(evaluate(12 / (count + 1), ""), 2)

    def test_length_and_angle_conversions(self):
        for unit, value in (("nm", 1000), ("um", 1), ("mm", 0.001),
                            ("m", 0.000001)):
            with self.subTest(unit=unit):
                length = Parameter(value, "length", unit=unit)
                self.assertAlmostEqual(evaluate(length, "um"), 1)
        angle = Parameter(pi / 2, "angle", unit="rad")
        self.assertAlmostEqual(evaluate(angle, "deg"), 90)
        self.assertAlmostEqual(evaluate(angle / 2, "rad"), pi / 4)
        self.assertAlmostEqual(evaluate(Parameter(90, "turn", unit="deg"), "rad"), pi / 2)

    def test_dimensionless_geometry_values_use_the_requested_unit(self):
        size = Parameter(20, "size")
        self.assertEqual(evaluate(size, "um"), 20)
        self.assertEqual(evaluate(size, "deg"), 20)
        self.assertEqual(evaluate(20, "um"), 20)
        self.assertEqual(comsol_expression(size, "um"), "size")
        self.assertEqual(comsol_expression(size, "deg"), "size")

    def test_incompatible_units_are_rejected_and_zero_is_neutral(self):
        length = Parameter(2, "length", unit="um")
        angle = Parameter(30, "angle", unit="deg")
        for operation in (lambda: evaluate(length + angle, "um"),
                          lambda: evaluate(length + 2, "um"),
                          lambda: evaluate(angle, "um"),
                          lambda: comsol_expression(length, "deg")):
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    operation()
        self.assertEqual(evaluate(0 + length, "um"), 2)
        self.assertEqual(evaluate(length - 0, "um"), 2)

    def test_numeric_values_are_finite_and_invalid_edits_are_atomic(self):
        for value in (float("inf"), float("nan"), "20 + 1"):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    Parameter(value, "invalid")
        size = Parameter(20, "size", unit="um")
        with self.assertRaises((TypeError, ValueError)):
            size.value = float("nan")
        self.assertEqual(size.value, 20)
        with self.assertRaises(ValueError):
            Parameter(1, "temperature", unit="K")

    def test_division_by_zero_is_detected_after_dependency_edits(self):
        divisor = Parameter(2, "divisor")
        result = DependentParameter(10 / divisor, "result")
        self.assertEqual(result.value, 5)
        divisor.value = 0
        with self.assertRaises((ValueError, ZeroDivisionError)):
            _ = result.value
        divisor.value = 5
        self.assertEqual(result.value, 2)

    def test_names_are_safe_comsol_identifiers(self):
        for name in ("", "2width", "width gap", "width-gap", "a.b", "pi", "i"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    Parameter(1, name)
        self.assertEqual(Parameter(1, "width_2").name, "width_2")

    def test_collection_orders_dependencies_and_rejects_name_collisions(self):
        width = Parameter(20, "width", unit="um")
        gap = Parameter(2, "gap", unit="um")
        pitch = DependentParameter(width + 2 * gap, "pitch")
        span = DependentParameter(pitch * 3, "span")
        parameters = collect_parameters([span, width, gap, pitch / 2])
        self.assertEqual(list(parameters), ["width", "gap", "pitch", "span"])
        self.assertIs(parameters["width"], width)
        with self.assertRaisesRegex(ValueError, "[Nn]ame|[Dd]uplicate|[Cc]onflict|width"):
            collect_parameters([span, Parameter(20, "width", unit="um")])

    def test_comsol_definitions_keep_units_and_parameter_references(self):
        width = Parameter(20, "width", unit="um")
        gap = Parameter(2, "gap", unit="um")
        pitch = DependentParameter(width + 2 * gap, "pitch")
        self.assertIn("[um]", width.definition)
        self.assertEqual(float(width.definition.split("[")[0]), 20)
        self.assertEqual(comsol_expression(pitch, "um"), "pitch")
        expression = comsol_expression(pitch / 2 + gap, "um")
        self.assertIn("pitch", expression)
        self.assertIn("gap", expression)
        before = pitch.definition
        width.value = 40
        self.assertEqual(pitch.definition, before)
        self.assertEqual(float(width.definition.split("[")[0]), 40)

    def test_dependent_expression_edits_and_cycles_are_transactional(self):
        width = Parameter(20, "width", unit="um")
        pitch = DependentParameter(2 * width, "pitch")
        span = DependentParameter(3 * pitch, "span")
        pitch.expression = 4 * width
        self.assertEqual(span.value, 240)
        for invalid in (pitch + width, span + width, float("nan")):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaises(ValueError):
                    pitch.expression = invalid
                self.assertEqual(pitch.value, 80)
                self.assertEqual(span.value, 240)
        with self.assertRaises(AttributeError):
            pitch.value = 5

    def test_explicit_dependent_unit_is_checked_without_changing_the_formula(self):
        width = Parameter(20, "width", unit="um")
        doubled = DependentParameter(2 * width, "doubled", unit="nm")
        self.assertEqual(doubled.value, 40000)
        self.assertEqual(evaluate(doubled, "um"), 40)
        self.assertEqual(doubled.definition, "(2*width)")
        with self.assertRaises(ValueError):
            doubled.expression = Parameter(90, "angle", unit="deg")
        self.assertEqual(doubled.value, 40000)
        with self.assertRaises(ValueError):
            DependentParameter(2 * width, "bad", unit="deg")
        with self.assertRaises(AttributeError):
            width.name = "other"
        with self.assertRaises(AttributeError):
            width.unit = "nm"

    def test_derived_units_and_finite_expression_results(self):
        width = Parameter(20, "width", unit="um")
        area = DependentParameter(width * width, "area")
        self.assertEqual(area.unit, "um^2")
        self.assertEqual(area.value, 400)
        self.assertEqual(evaluate(area / width, "um"), 20)
        with self.assertRaises(ValueError):
            evaluate(area, "um")
        large = Parameter(1e308, "large")
        with self.assertRaises(ValueError):
            evaluate(large * 2, "")


if __name__ == "__main__":
    unittest.main()
