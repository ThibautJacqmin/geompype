"""Planar COMSOL transformations, retaining floating-point KLayout geometry.

Lengths are in um, angles in degrees, and positive angles turn anticlockwise.
One input/output returns one D geometry; multiple outputs return a flat tuple.
Transforms add no grid conversion. Boolean operands and final GDS export do.
"""

from math import atan2, degrees
from numbers import Integral

from .geometry import GeometryObject
from .parameters import comsol_expression, evaluate
from .vertices import Vertices, coordinate_pair

__all__ = ["Array", "Copy", "Mirror", "Move", "Rotate", "Scale"]


def _values(value):
    """Accept a scalar expression or a sequence without evaluating references."""
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _result(items):
    items = tuple(items)
    return items[0] if len(items) == 1 else items


def _transformed(geometry, transform):
    import klayout.db as kdb

    if isinstance(geometry, kdb.DPoint):
        return transform * geometry
    return geometry.transformed(transform)


class _Transform(GeometryObject):
    """Small shared input/selection handling for the native transformations."""

    def __init__(self, target, *, keep=False, selections=(), propagate_selections=True):
        if isinstance(target, GeometryObject):
            inputs = (target,)
        else:
            try:
                inputs = tuple(target)
            except TypeError as error:
                raise TypeError("A transformation requires geometry objects.") from error
        if not inputs or any(not isinstance(obj, GeometryObject) for obj in inputs):
            raise TypeError("A transformation requires one or more geometry objects.")
        super().__init__(inputs[0].project, inputs[0].layer, selections=selections)
        self.inputs = inputs
        self.keep = keep
        self.propagate_selections = propagate_selections

    @property
    def target(self):
        """The first input, preserving the original single-object API."""
        return self.inputs[0]

    def validate(self):
        if not isinstance(self.keep, bool):
            raise ValueError(f"{type(self).__name__}.keep must be a boolean.")
        if not isinstance(self.propagate_selections, bool):
            raise ValueError("propagate_selections must be a boolean.")
        if len(set(self.inputs)) != len(self.inputs):
            raise ValueError("Transformation inputs must not contain duplicates.")
        if any(obj.project is not self.project or obj.layer is not self.layer for obj in self.inputs):
            raise ValueError("Transformation inputs must share their project and layer.")

    def _feature(self, workplane_geometry, tag, native_type, *, set_keep=True):
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, native_type)
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.selection("input").set([obj.tag for obj in self.inputs])
        feature.set("propagatesel", "on" if self.propagate_selections else "off")
        if set_keep:
            feature.set("keep", "on" if self.keep else "off")
        return feature

    def _geometries(self):
        result = []
        for obj in self.inputs:
            geometry = obj.to_klayout()
            result.extend(geometry if isinstance(geometry, tuple) else (geometry,))
        return result


class Rotate(_Transform):
    """Rotate about origin, once for each angle in angle.

    A scalar angle gives one rotated result; a sequence gives several copies.
    keep=True additionally preserves the inputs. Angles and coordinates
    accept live parameters and expressions.
    """

    tag_prefix = "rot"

    def __init__(self, target, *, angle=0, origin=(0, 0), keep=False,
                 selections=(), propagate_selections=True):
        super().__init__(target, keep=keep, selections=selections,
                         propagate_selections=propagate_selections)
        self.angle = angle
        self.origin = origin if isinstance(origin, Vertices) else tuple(origin)
        self.validate()
        self.project.add(self)

    def validate(self):
        super().validate()
        angles = _values(self.angle)
        if not angles:
            raise ValueError("Rotate requires at least one angle.")
        for angle in angles:
            evaluate(angle, "deg")
        coordinate_pair(self.origin)

    def parameter_values(self):
        return (*_values(self.angle), *coordinate_pair(self.origin))

    def to_comsol(self, workplane_geometry, tag):
        feature = self._feature(workplane_geometry, tag, "Rotate")
        angles = [comsol_expression(angle, "deg") for angle in _values(self.angle)]
        feature.set("rot", angles[0] if len(angles) == 1 else angles)
        feature.set("pos", [comsol_expression(value, "um") for value in coordinate_pair(self.origin)])

    def to_klayout(self):
        import klayout.db as kdb

        x, y = (evaluate(value, "um") for value in coordinate_pair(self.origin))
        geometries = self._geometries()
        results = []
        for angle in _values(self.angle):
            transform = (kdb.DCplxTrans(x, y)
                         * kdb.DCplxTrans(1, evaluate(angle, "deg"), False, 0, 0)
                         * kdb.DCplxTrans(-x, -y))
            results.extend(_transformed(geometry, transform) for geometry in geometries)
        return _result(results)


class Move(_Transform):
    """Translate inputs by delta and consume the original objects.

    delta is a pair or an N-by-2 table (including a shared Vertices).
    A table produces one translated result per row for each input.
    Use Copy to preserve the original objects.
    """

    tag_prefix = "mov"
    _native_type = "Move"
    _keeps_input = False

    def __init__(self, target, *, delta=(0, 0), selections=(), propagate_selections=True):
        super().__init__(target, keep=self._keeps_input, selections=selections,
                         propagate_selections=propagate_selections)
        self.delta = delta if isinstance(delta, Vertices) else Vertices(delta)
        self.validate()
        self.project.add(self)

    def _displacements(self):
        return self.delta if isinstance(self.delta, Vertices) else Vertices(self.delta)

    def validate(self):
        super().validate()
        if self.keep != self._keeps_input:
            raise ValueError(f"{type(self).__name__} has fixed input retention; use Move or Copy.")
        points = self._displacements()
        points.validate()
        if len(points) == 0:
            raise ValueError("Move/Copy requires at least one displacement.")

    def parameter_values(self):
        return self._displacements().parameter_values()

    def to_comsol(self, workplane_geometry, tag):
        feature = self._feature(workplane_geometry, tag, self._native_type, set_keep=False)
        rows = self._displacements().to_comsol()
        feature.set("specify", "displ")
        feature.set("displx", [row[0] for row in rows])
        feature.set("disply", [row[1] for row in rows])

    def to_klayout(self):
        import klayout.db as kdb

        geometries = self._geometries()
        return _result(_transformed(geometry, kdb.DCplxTrans(x, y))
                       for x, y in self._displacements().value for geometry in geometries)


class Copy(Move):
    """Make displaced copies while keeping the input objects.

    delta accepts a pair or an N-by-2 table, as in Move.
    """

    tag_prefix = "cpy"
    _native_type = "Copy"
    _keeps_input = True


class Mirror(_Transform):
    """Reflect in the line through origin perpendicular to normal.

    normal=(1, 0) reflects across a vertical line; (0, 1) across a
    horizontal line. The normal is dimensionless and need not have unit length.
    """

    tag_prefix = "mir"

    def __init__(self, target, *, normal=(1, 0), origin=(0, 0), keep=False,
                 selections=(), propagate_selections=True):
        super().__init__(target, keep=keep, selections=selections,
                         propagate_selections=propagate_selections)
        self.normal = tuple(normal)
        self.origin = origin if isinstance(origin, Vertices) else tuple(origin)
        self.validate()
        self.project.add(self)

    def validate(self):
        super().validate()
        normal = tuple(self.normal)
        if len(normal) != 2:
            raise ValueError("Mirror.normal requires two dimensionless components.")
        values = [evaluate(value, "") for value in normal]
        if values == [0, 0]:
            raise ValueError("Mirror.normal must be nonzero.")
        coordinate_pair(self.origin)

    def parameter_values(self):
        return (*self.normal, *coordinate_pair(self.origin))

    def to_comsol(self, workplane_geometry, tag):
        feature = self._feature(workplane_geometry, tag, "Mirror")
        feature.set("specify", "pointnormal")
        feature.set("axis", [comsol_expression(value, "") for value in self.normal])
        feature.set("pos", [comsol_expression(value, "um") for value in coordinate_pair(self.origin)])

    def to_klayout(self):
        import klayout.db as kdb

        x, y = (evaluate(value, "um") for value in coordinate_pair(self.origin))
        nx, ny = (evaluate(value, "") for value in self.normal)
        angle = 2 * degrees(atan2(ny, nx)) + 180
        transform = (kdb.DCplxTrans(x, y) * kdb.DCplxTrans(1, angle, True, 0, 0)
                     * kdb.DCplxTrans(-x, -y))
        return _result(_transformed(geometry, transform) for geometry in self._geometries())


class Scale(_Transform):
    """Scale about origin by one factor or separate (x, y) factors.

    Factors are dimensionless and nonzero; negative factors reflect an axis.
    The source's sampling error is scaled with its geometry. GDS rounding still
    happens only on the final result.
    """

    tag_prefix = "sca"

    def __init__(self, target, *, factor=1, origin=(0, 0), keep=False,
                 selections=(), propagate_selections=True):
        super().__init__(target, keep=keep, selections=selections,
                         propagate_selections=propagate_selections)
        self.factor = factor
        self.origin = origin if isinstance(origin, Vertices) else tuple(origin)
        self.validate()
        self.project.add(self)

    def validate(self):
        super().validate()
        factors = _values(self.factor)
        if len(factors) not in (1, 2):
            raise ValueError("Scale.factor requires one factor or an (x, y) pair.")
        if any(evaluate(value, "") == 0 for value in factors):
            raise ValueError("Scale factors must be nonzero.")
        coordinate_pair(self.origin)

    def parameter_values(self):
        return (*_values(self.factor), *coordinate_pair(self.origin))

    def to_comsol(self, workplane_geometry, tag):
        feature = self._feature(workplane_geometry, tag, "Scale")
        factors = [comsol_expression(value, "") for value in _values(self.factor)]
        feature.set("factor", factors[0] if len(factors) == 1 else factors)
        feature.set("pos", [comsol_expression(value, "um") for value in coordinate_pair(self.origin)])

    def to_klayout(self):
        import klayout.db as kdb

        factors = [evaluate(value, "") for value in _values(self.factor)]
        sx, sy = factors * 2 if len(factors) == 1 else factors
        x, y = (evaluate(value, "um") for value in coordinate_pair(self.origin))

        def point(p):
            return kdb.DPoint(x + sx * (p.x - x), y + sy * (p.y - y))

        results = []
        for geometry in self._geometries():
            if isinstance(geometry, kdb.DPoint):
                result = point(geometry)
            elif isinstance(geometry, kdb.DPath):
                if geometry.width != 0 or geometry.bgn_ext != 0 or geometry.end_ext != 0:
                    raise ValueError("Scale currently accepts centreline paths without extensions.")
                result = kdb.DPath([point(p) for p in geometry.each_point()], 0)
            elif isinstance(geometry, kdb.DPolygon):
                result = kdb.DPolygon([point(p) for p in geometry.each_point_hull()])
                for hole in range(geometry.holes()):
                    result.insert_hole([point(p) for p in geometry.each_point_hole(hole)])
            else:
                raise TypeError("Scale expects DPoint, DPath or DPolygon geometry.")
            results.append(result)
        return _result(results)



class Array(_Transform):
    """Repeat geometry in a linear or rectangular array.

    ``size=3`` makes three copies along ``displacement=(dx, dy)``.
    ``size=(3, 2)`` makes a rectangular array, spaced by dx in x and dy in y.
    Counts include the copy at the original position. As in COMSOL, the input
    features are consumed and replaced by these copies; there is no ``keep``
    option. Counts and displacement may contain live parameters.

    ``exclude=[0, 2]`` omits zero-based sites in a linear array;
    ``exclude=[(0, 0), (2, 1)]`` omits (x, y) sites in a rectangular array.
    An exclusion removes all input objects at that site, without subtracting
    overlapping geometry from surviving sites. At least one site must remain.
    Excluded arrays use a native Move with the retained displacement list;
    changing counts or exclusions requires a Python ``project.build()``.
    """

    tag_prefix = "arr"

    def __init__(self, target, *, size=1, displacement=(1, 1), exclude=(), selections=(),
                 propagate_selections=True):
        super().__init__(target, selections=selections,
                         propagate_selections=propagate_selections)
        self.size = size
        self.displacement = (displacement if isinstance(displacement, Vertices)
                             else tuple(displacement))
        self.exclude = exclude
        self.validate()
        self.project.add(self)

    @property
    def exclude(self):
        """Immutable zero-based indices (linear) or (x, y) pairs (rectangular)."""
        return self._exclude

    @exclude.setter
    def exclude(self, values):
        # Snapshot iterables so a generator or later list edits cannot change
        # which sites are retained midway through one build.
        try:
            values = tuple(values)
        except TypeError as error:
            raise ValueError("Array.exclude must be a sequence of indices or index pairs.") from error
        result = []
        for value in values:
            if not isinstance(value, Integral):
                try:
                    value = tuple(value)
                except TypeError as error:
                    raise ValueError("Array.exclude requires integer indices or index pairs.") from error
            result.append(value)
        self._exclude = tuple(result)

    def _size_values(self):
        try:
            values = tuple(self.size)
        except TypeError:
            return (self.size,)
        if len(values) != 2:
            raise ValueError("Array.size must be a count or a pair of counts.")
        return values

    def _counts(self):
        counts = []
        for value in self._size_values():
            number = evaluate(value, "")
            if number < 1 or not number.is_integer():
                raise ValueError("Array counts must be positive dimensionless integers.")
            counts.append(int(number))
        return tuple(counts)

    def validate(self):
        super().validate()
        if self.keep:
            raise ValueError("Array consumes its inputs and includes the original-position copy.")
        counts = self._counts()
        excluded = self._excluded_indices(counts)
        if len(excluded) == counts[0] * (counts[1] if len(counts) == 2 else 1):
            raise ValueError("Array.exclude must leave at least one array site.")
        coordinate_pair(self.displacement)

    def _excluded_indices(self, counts):
        excluded = set()
        for value in self.exclude:
            indices = (value,) if len(counts) == 1 else value
            if (not isinstance(indices, tuple) or len(indices) != len(counts)
                    or any(isinstance(index, bool) or not isinstance(index, Integral)
                           for index in indices)):
                kind = "integer indices" if len(counts) == 1 else "integer (x, y) pairs"
                raise ValueError(f"Array.exclude requires zero-based {kind}.")
            if any(index < 0 or index >= count for index, count in zip(indices, counts)):
                raise ValueError("Array.exclude index is outside the current array size.")
            excluded.add(tuple(int(index) for index in indices))
        return excluded

    def _retained_sites(self):
        """Return x/y pitch multipliers, including both components for linear arrays."""
        counts = self._counts()
        excluded = self._excluded_indices(counts)
        if len(counts) == 1:
            return ((i, i) for i in range(counts[0]) if (i,) not in excluded)
        return ((i, j) for j in range(counts[1]) for i in range(counts[0])
                if (i, j) not in excluded)

    def parameter_values(self):
        return (*self._size_values(), *coordinate_pair(self.displacement))

    def reset_comsol(self, geometry):
        """Replace the native feature only when switching exclusion mode."""
        kind = "Move" if self.exclude else "Array"
        if (self.tag in list(geometry.feature().tags())
                and str(geometry.feature(self.tag).getType()) != kind):
            geometry.feature().remove(self.tag)
            return True
        return False

    def to_comsol(self, workplane_geometry, tag):
        if self.exclude:
            # One Move duplicates only retained sites and consumes the input.
            # Unlike subtracting unwanted copies, this works for overlapping
            # surfaces and for zero-width curves and points as well.
            feature = self._feature(workplane_geometry, tag, "Move", set_keep=False)
            dx, dy = (comsol_expression(value, "um")
                      for value in coordinate_pair(self.displacement))
            sites = tuple(self._retained_sites())
            feature.set("specify", "displ")
            feature.set("displx", [f"{i}*({dx})" for i, _ in sites])
            feature.set("disply", [f"{j}*({dy})" for _, j in sites])
            return
        feature = self._feature(workplane_geometry, tag, "Array", set_keep=False)
        sizes = self._size_values()
        if len(sizes) == 1:
            feature.set("type", "linear")
            feature.set("linearsize", comsol_expression(sizes[0], ""))
        else:
            feature.set("type", "rectangular")
            feature.set("fullsize", [comsol_expression(value, "") for value in sizes])
        feature.set("displ", [comsol_expression(value, "um")
                              for value in coordinate_pair(self.displacement)])

    def to_klayout(self):
        import klayout.db as kdb

        dx, dy = (evaluate(value, "um") for value in coordinate_pair(self.displacement))
        geometries = self._geometries()
        offsets = ((i*dx, j*dy) for i, j in self._retained_sites())
        return _result([_transformed(geometry, kdb.DCplxTrans(x, y))
                        for x, y in offsets for geometry in geometries])
