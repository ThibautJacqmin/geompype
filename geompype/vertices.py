"""Planar coordinates with live parameter references and explicit length units."""

from collections.abc import Mapping, Set
from numbers import Integral, Real

from .parameters import (
    _Scalar, _UnitValue, _UNITS, _number, _quantity, _unit,
    collect_parameters, comsol_expression, evaluate,
)


def _nested(data):
    """Copy rectangular input containers, retaining scalar parameter objects."""
    if isinstance(data, Vertices):
        return data.array, (len(data), 2)
    if isinstance(data, _Scalar):
        return data, ()
    if isinstance(data, Real):
        return _number(data), ()
    if isinstance(data, (str, bytes, Mapping, Set)):
        raise ValueError("Vertices require ordered real coordinates, not strings or mappings.")
    # This also preserves the shape of empty NumPy arrays, without importing NumPy.
    shape = getattr(data, "shape", None)
    if shape == ():
        return _number(data.item()), ()
    try:
        items = tuple(data)
    except TypeError as error:
        raise ValueError("Each coordinate must be a real number or scalar parameter.") from error
    if not items:
        return (), tuple(shape) if shape is not None else (0,)
    children = [_nested(item) for item in items]
    child_shape = children[0][1]
    if any(size != child_shape for _, size in children):
        raise ValueError("Vertices cannot contain ragged rows.")
    return tuple(item for item, _ in children), (len(items), *child_shape)


def _rows(data):
    if isinstance(data, Vertices):
        return data.array
    items, shape = _nested(data)
    if shape == (0,):
        return ()
    if shape == (2,):
        return (items,)
    if len(shape) == 2 and shape[-1] == 2:
        return items
    if len(shape) == 3 and shape[-1] == 2:
        return tuple(point for group in items for point in group)
    raise ValueError("Vertices must be [x, y], N x 2 or N x M x 2 coordinates.")


def _coordinate(value, unit):
    _, dimensions = _quantity(value, set())
    if dimensions == (0, 0):
        return _UnitValue(value, unit)
    if dimensions == (1, 0):
        return value
    raise ValueError("A vertex coordinate must be a length, not an angle or another dimension.")


class Vertices:
    """One or more 2D points, e.g. ``Vertices([[width, 0], [0, height]])``.

    Bare coordinates use um unless ``unit`` is supplied. Length parameters
    retain their own units; values are never inferred from a neighbouring point.
    ``Vertices([[1, 0], [0, 1]], pitch)`` uses a shared length prefactor.
    Arrays shaped N x M x 2 are flattened in Python row-major order.

    ``value`` is always an N x 2 list in um. Indexing a row returns a Vertices;
    indexing [row, column] returns its scalar expression. Arithmetic and slices
    copy coordinate expressions while keeping their underlying parameter refs.
    """

    __array_priority__ = 1000  # NumPy operands defer to our reflected arithmetic.

    def __init__(self, data=(0, 0), prefactor=None, *, unit=None):
        self._default_unit = "um" if unit is None else _unit(unit)
        if _UNITS[self._default_unit][1] != (1, 0):
            raise ValueError("Vertices.unit must be a length unit: nm, um, mm or m.")
        rows = _rows(data)
        self._coefficients = None
        if prefactor is not None:
            factor = _coordinate(prefactor, self._default_unit)
            for row in rows:
                for value in row:
                    if _quantity(value, set())[1] != (0, 0):
                        raise ValueError("A shared prefactor requires dimensionless coefficients.")
            self._points = tuple(tuple(value * factor for value in row) for row in rows)
        else:
            self._points = tuple(tuple(_coordinate(value, self._default_unit) for value in row)
                                 for row in rows)
            if isinstance(data, Vertices):
                self._coefficients = data._coefficients
                self._default_unit = data._default_unit
            elif unit is None and all(_quantity(v, set())[1] == (0, 0) for row in rows for v in row):
                # Retain dimensionless coefficients for multiplication by a length parameter.
                self._coefficients = rows
        self.validate()

    @classmethod
    def _from_rows(cls, rows, coefficients=None, unit="um"):
        result = cls(rows, unit=unit)
        result._coefficients = coefficients
        return result

    @classmethod
    def xy(cls, x, y, *, unit=None):
        """Create one point from two scalar coordinates, preserving expressions."""
        return cls((x, y), unit=unit)

    @classmethod
    def from_components(cls, components, *, unit=None):
        """Construct from coordinate rows using the same shapes as Vertices(...)."""
        return cls(components, unit=unit)

    @property
    def array(self):
        """Immutable rows of coordinate expressions; use indexing to edit entries."""
        return self._points

    @property
    def nvertices(self):
        """Number of coordinate rows after any input-array flattening."""
        return len(self._points)

    def __len__(self):
        return self.nvertices

    def __iter__(self):
        for index in range(len(self)):
            yield self[index]

    def parameter_values(self):
        return tuple(value for row in self._points for value in row)

    @property
    def parameters(self):
        """Named parameters and their dependencies, indexed by name."""
        return collect_parameters(self.parameter_values())

    def parameter_dependencies(self):
        return tuple(self.parameters.values())

    def validate(self):
        for value in self.parameter_values():
            if _quantity(value, set())[1] != (1, 0):
                raise ValueError("Vertex coordinates must remain lengths.")
        self.parameters

    def values(self, unit="um"):
        """Evaluate an N-by-2 numeric snapshot in the requested length unit."""
        unit = _unit(unit)
        if _UNITS[unit][1] != (1, 0):
            raise ValueError("Vertices values require a length unit.")
        self.validate()
        return [[evaluate(value, unit) for value in row] for row in self._points]

    @property
    def value(self):
        """Numeric N-by-2 snapshot in um; edits to this list do not edit vertices."""
        return self.values()

    @property
    def xvalue(self):
        """Current x coordinates as a numeric list in um."""
        return [row[0] for row in self.value]

    @property
    def yvalue(self):
        """Current y coordinates as a numeric list in um."""
        return [row[1] for row in self.value]

    def to_comsol(self):
        """Return N-by-2 native expressions retaining parameter names and units."""
        self.validate()
        return [[comsol_expression(value, "um") for value in row] for row in self._points]

    def comsol_string_x(self):
        """Return one native x-coordinate expression per point."""
        return [row[0] for row in self.to_comsol()]

    def comsol_string_y(self):
        """Return one native y-coordinate expression per point."""
        return [row[1] for row in self.to_comsol()]

    def comsol_string(self):
        """Return a list of comma-separated native ``x,y`` expressions."""
        return [",".join(row) for row in self.to_comsol()]

    def __getitem__(self, key):
        if isinstance(key, tuple):
            if len(key) != 2:
                raise IndexError("Use vertices[row, column].")
            row, column = key
            if any(isinstance(i, bool) or not isinstance(i, (Integral, slice)) for i in key):
                raise TypeError("Use integer indices or slices.")
            if isinstance(row, slice):
                return tuple(point[column] for point in self._points[row])
            return self._points[row][column]
        if isinstance(key, slice):
            coefficients = None if self._coefficients is None else self._coefficients[key]
            return self._from_rows(self._points[key], coefficients, self._default_unit)
        if isinstance(key, Integral) and not isinstance(key, bool):
            coefficients = None if self._coefficients is None else (self._coefficients[key],)
            return self._from_rows((self._points[key],), coefficients, self._default_unit)
        raise TypeError("Use an integer row index, a slice or [row, column].")

    def get_sub_vertex(self, index):
        """Extract a point, using Python's zero-based indexing."""
        return self[index]

    def __setitem__(self, key, value):
        rows = [list(row) for row in self._points]
        coefficients = None if self._coefficients is None else [list(row) for row in self._coefficients]
        if isinstance(key, tuple):
            if len(key) != 2 or not all(isinstance(i, Integral) and not isinstance(i, bool) for i in key):
                raise IndexError("Scalar assignment uses vertices[row, column] with integer indices.")
            row, column = key
            rows[row][column] = _coordinate(value, self._default_unit)
            if coefficients is not None:
                if _quantity(value, set())[1] == (0, 0):
                    coefficients[row][column] = value
                else:
                    coefficients = None
        else:
            replacement = Vertices(value, unit=None if self._default_unit == "um" else self._default_unit)
            if isinstance(key, slice):
                indices = list(range(len(self)))[key]
            elif isinstance(key, Integral) and not isinstance(key, bool):
                # Access first to reject invalid indices even when replacement is empty.
                self._points[key]
                indices = [key]
            else:
                raise TypeError("Use a row index, slice or [row, column].")
            if len(indices) != len(replacement):
                raise ValueError("Assignment must preserve the number of points.")
            for index, point in zip(indices, replacement.array):
                rows[index] = list(point)
            if coefficients is not None and replacement._coefficients is not None:
                for index, point in zip(indices, replacement._coefficients):
                    coefficients[index] = list(point)
            else:
                coefficients = None
        result = self._from_rows(rows, unit=self._default_unit)
        self._points = result._points
        self._coefficients = None if coefficients is None else tuple(tuple(row) for row in coefficients)

    def concat(self, *others):
        """Append coordinate rows into new Vertices, sharing scalar parameters."""
        rows = list(self._points)
        coefficients = None if self._coefficients is None else list(self._coefficients)
        for other in others:
            other = other if isinstance(other, Vertices) else Vertices(other)
            rows.extend(other.array)
            if coefficients is not None and other._coefficients is not None:
                coefficients.extend(other._coefficients)
            else:
                coefficients = None
        return self._from_rows(rows, None if coefficients is None else tuple(coefficients))

    def _add_subtract(self, other, subtract=False):
        other = other if isinstance(other, Vertices) else Vertices(other)
        count = len(other) if len(self) == 1 else len(self)
        if len(self) not in (1, count) or len(other) not in (1, count):
            raise ValueError("Add/subtract requires equal point counts or a single translation point.")
        rows, coefficients = [], []
        for index in range(count):
            i, j = (0 if len(self) == 1 else index), (0 if len(other) == 1 else index)
            a, b = self._points[i], other._points[j]
            rows.append(tuple(x - y if subtract else x + y for x, y in zip(a, b)))
            if self._coefficients is not None and other._coefficients is not None:
                a, b = self._coefficients[i], other._coefficients[j]
                coefficients.append(tuple(x - y if subtract else x + y for x, y in zip(a, b)))
        if self._coefficients is None or other._coefficients is None:
            coefficients = None
        return self._from_rows(rows, None if coefficients is None else tuple(coefficients))

    def __add__(self, other):
        return self._add_subtract(other)

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        return self._add_subtract(other, subtract=True)

    def __rsub__(self, other):
        return Vertices(other) - self

    def _scale(self, scalar, divide=False):
        _, dimensions = _quantity(scalar, set())
        if dimensions == (1, 0) and not divide and self._coefficients is not None:
            return Vertices(self._coefficients, scalar)
        if dimensions != (0, 0):
            raise ValueError("Scale factors must be dimensionless; a length prefactor needs raw coefficients.")
        if divide and evaluate(scalar, "") == 0:
            raise ValueError("Cannot divide Vertices by zero.")
        rows = [tuple(v / scalar if divide else v * scalar for v in row) for row in self._points]
        coefficients = None
        if self._coefficients is not None:
            coefficients = tuple(tuple(v / scalar if divide else v * scalar for v in row)
                                 for row in self._coefficients)
        return self._from_rows(rows, coefficients)

    def __mul__(self, scalar):
        return self._scale(scalar)

    def __rmul__(self, scalar):
        return self * scalar

    def __truediv__(self, scalar):
        return self._scale(scalar, divide=True)

    def __neg__(self):
        return self * -1

    def centroid(self):
        """Arithmetic mean of the physical points, with parameter dependencies."""
        if not self._points:
            raise ValueError("An empty Vertices has no centroid.")
        return Vertices([sum(row[column] for row in self._points) / len(self)
                         for column in range(2)])

    def isobarycentre(self):
        """Return the same parameter-preserving arithmetic mean as centroid()."""
        return self.centroid()


def coordinate_pair(value):
    """Validate a single 2D feature position without losing its live references."""
    if isinstance(value, Vertices):
        value.validate()
        if len(value) != 1:
            raise ValueError("A position or origin requires exactly one vertex.")
        return value.array[0]
    pair = tuple(value)
    if len(pair) != 2:
        raise ValueError("A position or origin requires two coordinates.")
    for item in pair:
        evaluate(item, "um")
    return pair
