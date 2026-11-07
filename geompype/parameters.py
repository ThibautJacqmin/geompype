"""Small arithmetic expressions shared by COMSOL and the numerical GDS export.

No expression strings are evaluated as Python. Arithmetic retains references to
parameters, so changing a value also changes every dependent expression.
"""

from math import copysign, floor, isfinite, pi
from numbers import Real
import re


# Scale to the geometry's canonical units (um and degrees), and dimensions
# represented by the exponents of length and angle.
_UNITS = {
    "": (1.0, (0, 0)),
    "nm": (0.001, (1, 0)),
    "um": (1.0, (1, 0)),
    "mm": (1000.0, (1, 0)),
    "m": (1e6, (1, 0)),
    "deg": (1.0, (0, 1)),
    "rad": (180 / pi, (0, 1)),
}


def _unit(unit):
    if not isinstance(unit, str):
        raise ValueError("A unit must be a string such as 'um', 'deg' or ''.")
    aliases = {"1": "", "µm": "um", "μm": "um"}
    unit = aliases.get(unit, unit)
    if unit not in _UNITS:
        raise ValueError(f"Unsupported unit {unit!r}; use nm, um, mm, m, deg, rad or ''.")
    return unit


def _number(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("A parameter or coordinate must be a real number, not a string.")
    try:
        value = float(value)
    except OverflowError as error:
        raise ValueError("Parameter values must be finite.") from error
    if not isfinite(value):
        raise ValueError("Parameter values and expression results must be finite.")
    return value


def _name(name):
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) is None:
        raise ValueError("A parameter name must start with a letter and use letters, digits or '_'.")
    if name in {"e", "pi", "i", "j", "eps", "inf", "Inf", "nan", "NaN"}:
        raise ValueError(f"Parameter name {name!r} is a reserved COMSOL constant.")
    return name


def _canonical_unit(dimensions):
    parts = []
    for unit, power in zip(("um", "deg"), dimensions):
        if power:
            parts.append(unit if power == 1 else f"{unit}^{power}")
    return "*".join(parts)


class _Scalar:
    """Ordinary arithmetic builds expression objects, without copying values."""

    def _binary(self, operator, other, reverse=False):
        # Let containers (notably Vertices) implement their reflected operation.
        if not isinstance(other, (_Scalar, Real)):
            return NotImplemented
        left, right = (other, self) if reverse else (self, other)
        return _Expression(operator, left, right)

    def __add__(self, other):
        return self._binary("+", other)

    def __radd__(self, other):
        return self._binary("+", other, reverse=True)

    def __sub__(self, other):
        return self._binary("-", other)

    def __rsub__(self, other):
        return self._binary("-", other, reverse=True)

    def __mul__(self, other):
        return self._binary("*", other)

    def __rmul__(self, other):
        return self._binary("*", other, reverse=True)

    def __truediv__(self, other):
        return self._binary("/", other)

    def __rtruediv__(self, other):
        return self._binary("/", other, reverse=True)

    def __neg__(self):
        return _Expression("*", -1, self)

    def __pos__(self):
        return self

    def __round__(self, ndigits=None):
        if ndigits not in (None, 0):
            raise ValueError("Parametric rounding currently supports integer rounding only.")
        return round_nearest(self)


class _Expression(_Scalar):
    def __init__(self, operator, left, right):
        self.operator = operator
        self.left = left if isinstance(left, _Scalar) else _number(left)
        self.right = right if isinstance(right, _Scalar) else _number(right)


class _UnitValue(_Scalar):
    """Give a unitless coordinate its explicit unit, retaining any dependencies."""

    def __init__(self, source, unit):
        self.source = source if isinstance(source, _Scalar) else _number(source)
        self.unit = _unit(unit)
        _quantity(self, set())


class _Function(_Scalar):
    """A live scalar function with numeric evaluation and a COMSOL expression."""

    def __init__(self, name, *arguments):
        self.name = name
        self.arguments = tuple(v if isinstance(v, _Scalar) else _number(v) for v in arguments)
        _quantity(self, set())


def maximum(left, right):
    """A live maximum of two dimensionless expressions, exported as COMSOL max."""
    return _Function("max", left, right)


def round_nearest(value):
    """Round a dimensionless expression to an integer, with halves away from zero.

    ``round(parameter_expression)`` is also accepted. Normalize lengths by a
    reference length before rounding.
    """
    return _Function("round", value)


class Parameter(_Scalar):
    """An editable named number, e.g. ``Parameter(20, 'width', unit='um')``.

    ``value`` is expressed in ``unit``. Names and units stay fixed; change the
    value then call ``project.build()`` to update both exports, also in live mode.
    """

    def __init__(self, value, name, *, unit="", description=""):
        self._name = _name(name)
        self._unit = _unit(unit)
        self.description = str(description)
        self.value = value

    @property
    def name(self):
        return self._name

    @property
    def unit(self):
        return self._unit

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = _number(value)

    @property
    def definition(self):
        """The expression used in COMSOL's global Parameters table."""
        suffix = f"[{self.unit}]" if self.unit else ""
        return f"{self.value:.17g}{suffix}"


class DependentParameter(_Scalar):
    """Name an expression, e.g. ``DependentParameter(width + 2*gap, 'pitch')``.

    ``value`` is calculated each time it is read. Its default unit is um for a
    length, deg for an angle, or the corresponding product for derived units.
    Supply ``unit`` to read the value in another compatible unit. This does not
    change the underlying formula exported to COMSOL.
    """

    def __init__(self, expression, name, *, unit=None, description=""):
        self._name = _name(name)
        self._unit = None if unit is None else _unit(unit)
        self.description = str(description)
        self._expression = None
        self.expression = expression

    @property
    def name(self):
        return self._name

    @property
    def expression(self):
        return self._expression

    @expression.setter
    def expression(self, expression):
        if not isinstance(expression, _Scalar):
            expression = _number(expression)
        previous = self._expression
        self._expression = expression
        try:
            _quantity(self, set())
            collect_parameters([self])
        except (ValueError, ZeroDivisionError, OverflowError):
            self._expression = previous
            raise

    @property
    def unit(self):
        _, dimensions = _quantity(self, set())
        return self._unit if self._unit is not None else _canonical_unit(dimensions)

    @property
    def value(self):
        value, _ = _quantity(self, set())
        return _number(value / _UNITS[self._unit][0]) if self._unit is not None else value

    @property
    def definition(self):
        _quantity(self, set())
        return _expression_text(self.expression)


def _literal_zero(value):
    # A named zero can change later, so only a literal zero is unit-neutral.
    return not isinstance(value, _Scalar) and value == 0


def _quantity(value, active):
    """Return a current numerical value in um/deg and its dimensions."""
    if not isinstance(value, _Scalar):
        return _number(value), (0, 0)
    if value in active:
        raise ValueError("Circular parameter dependency.")
    active.add(value)
    try:
        if isinstance(value, Parameter):
            scale, dimensions = _UNITS[value.unit]
            result = value.value * scale
        elif isinstance(value, _UnitValue):
            result, dimensions = _quantity(value.source, active)
            if dimensions != (0, 0):
                raise ValueError("A coordinate coefficient must remain dimensionless.")
            scale, dimensions = _UNITS[value.unit]
            result *= scale
        elif isinstance(value, DependentParameter):
            result, dimensions = _quantity(value.expression, active)
            if value._unit is not None and _UNITS[value._unit][1] != dimensions:
                raise ValueError(f"Unit {value._unit!r} is incompatible with {value.name!r}.")
        elif isinstance(value, _Function):
            arguments = [_quantity(v, active) for v in value.arguments]
            if any(d != (0, 0) for _, d in arguments):
                raise ValueError(f"{value.name} requires dimensionless arguments; divide by a reference unit.")
            numbers = [v for v, _ in arguments]
            dimensions = (0, 0)
            if value.name == "max":
                result = max(numbers)
            else:
                magnitude = abs(numbers[0])
                integer = floor(magnitude)
                result = copysign(integer + (magnitude - integer >= 0.5), numbers[0])
        else:
            left, ld = _quantity(value.left, active)
            right, rd = _quantity(value.right, active)
            if value.operator in ("+", "-"):
                if ld != rd:
                    if _literal_zero(value.left):
                        ld = rd
                    elif _literal_zero(value.right):
                        rd = ld
                    else:
                        raise ValueError("Addition and subtraction require compatible units.")
                dimensions = ld
                result = left + right if value.operator == "+" else left - right
            elif value.operator == "*":
                dimensions = tuple(a + b for a, b in zip(ld, rd))
                result = left * right
            else:
                if right == 0:
                    raise ValueError("Division by zero in a parameter expression.")
                dimensions = tuple(a - b for a, b in zip(ld, rd))
                result = left / right
        return _number(result), dimensions
    finally:
        active.remove(value)


def evaluate(value, unit):
    """Read a scalar in a geometry unit; unitless values use that unit directly."""
    unit = _unit(unit)
    result, dimensions = _quantity(value, set())
    scale, expected = _UNITS[unit]
    if dimensions == (0, 0):
        return result
    if dimensions != expected:
        raise ValueError(f"Expected unit {unit!r}, got {_canonical_unit(dimensions)!r}.")
    return _number(result / scale)


def _expression_text(value):
    if isinstance(value, (Parameter, DependentParameter)):
        return value.name
    if isinstance(value, _Expression):
        return f"({_expression_text(value.left)}{value.operator}{_expression_text(value.right)})"
    if isinstance(value, _UnitValue):
        return f"({_expression_text(value.source)}*1[{value.unit}])"
    if isinstance(value, _Function):
        arguments = [_expression_text(v) for v in value.arguments]
        if value.name == "max":
            return f"max({arguments[0]},{arguments[1]})"
        # Explicit tie rule, independent of COMSOL/Python versions' round defaults.
        x = arguments[0]
        return f"(sign({x})*(floor(abs({x}))+(abs({x})-floor(abs({x}))>=0.5)))"
    number = _number(value)
    text = f"{number:.17g}"
    return f"({text})" if number < 0 else text


def comsol_expression(value, unit):
    """Keep symbols and arithmetic intact in a COMSOL geometry property."""
    evaluate(value, unit)
    return _expression_text(value)


def collect_parameters(values):
    """Collect named dependencies first; reject conflicting names and cycles."""
    parameters = {}
    active = set()
    visited = set()

    def visit(value):
        if not isinstance(value, _Scalar):
            _number(value)
            return
        if value in active:
            raise ValueError("Circular parameter dependency.")
        if value in visited:
            return
        active.add(value)
        if isinstance(value, _Expression):
            visit(value.left)
            visit(value.right)
        elif isinstance(value, _UnitValue):
            visit(value.source)
        elif isinstance(value, _Function):
            for argument in value.arguments:
                visit(argument)
        else:
            if isinstance(value, DependentParameter):
                visit(value.expression)
            if value.name in parameters and parameters[value.name] is not value:
                raise ValueError(f"Conflicting parameters named {value.name!r}; reuse the same object.")
            parameters[value.name] = value
        active.remove(value)
        visited.add(value)

    for value in values:
        visit(value)
    return parameters
