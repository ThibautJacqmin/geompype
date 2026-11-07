"""Planar COMSOL primitives. Lengths in um, angles in degrees.

Square, Rectangle, Circle, Ellipse and Polygon are filled shapes. Curves are
native COMSOL curves and zero-width KLayout paths; points are native COMSOL
points and KLayout coordinates. Routing and finite-width sweeps build on these.
"""

from math import cos, radians, sin

from .geometry import GeometryObject
from .parameters import comsol_expression, evaluate
from .vertices import Vertices, coordinate_pair

__all__ = ["Circle", "Square", "Rectangle", "CircularArc", "CubicBezier",
           "InterpolationCurve", "LineSegment", "ParametricCurve", "Point",
           "Polygon", "QuadraticBezier", "Ellipse", "BezierPolygon"]


class Square(GeometryObject):
    """A native COMSOL Square and its GDS polygon.

    ``position`` is the centre or lower-left corner, according to ``base``.
    Rotation is about this position, matching COMSOL's Square definition.
    Creation builds immediately only when ``project.live`` is true.
    Dimensions, coordinates and angles accept parameters or expressions.
    """

    tag_prefix = "sq"

    def __init__(self, project, *, layer, side, position=(0, 0),
                 base="center", angle=0, selections=()):
        super().__init__(project, layer, selections=selections)
        self.side = side
        self.position = position if isinstance(position, Vertices) else tuple(position)
        self.angle = angle
        self.base = base
        self.validate()
        project.add(self)

    def validate(self):
        if evaluate(self.side, "um") <= 0:
            raise ValueError("Square.side must be a finite positive length in um.")
        coordinate_pair(self.position)
        evaluate(self.angle, "deg")
        if self.base not in ("center", "corner"):
            raise ValueError("Square.base must be 'center' or 'corner'.")

    def parameter_values(self):
        return (self.side, *coordinate_pair(self.position), self.angle)

    def to_comsol(self, workplane_geometry, tag):
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "Square")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("type", "solid")
        feature.set("base", self.base)
        feature.set("size", comsol_expression(self.side, "um"))
        feature.set("pos", [comsol_expression(value, "um") for value in coordinate_pair(self.position)])
        feature.set("rot", comsol_expression(self.angle, "deg"))

    def to_klayout(self):
        import klayout.db as kdb

        side = evaluate(self.side, "um")
        angle = evaluate(self.angle, "deg")
        start = -side / 2 if self.base == "center" else 0
        end = start + side
        c, s = cos(radians(angle)), sin(radians(angle))
        px, py = (evaluate(value, "um") for value in coordinate_pair(self.position))
        points = [kdb.DPoint(px + c*x - s*y, py + s*x + c*y)
                  for x, y in ((start, start), (end, start), (end, end), (start, end))]
        return kdb.DPolygon(points)


class _PendingPrimitive(GeometryObject):
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(f"{type(self).__name__} is not implemented yet.")


class Circle(GeometryObject):
    """A native COMSOL disk, centred at ``position``.

    ``tolerance`` is the maximum chord error of the GDS outline in um,
    before snapping to the project's GDS grid. COMSOL keeps an exact circle.
    Radius, coordinates and tolerance retain their parameter references.
    """

    tag_prefix = "cir"

    def __init__(self, project, *, layer, radius, position=(0, 0),
                 tolerance=0.001, selections=()):
        super().__init__(project, layer, selections=selections)
        self.radius = radius
        self.position = position if isinstance(position, Vertices) else tuple(position)
        self.tolerance = tolerance
        self.validate()
        project.add(self)

    def validate(self):
        from math import isfinite

        radius = evaluate(self.radius, "um")
        if radius <= 0:
            raise ValueError("Circle.radius must be a finite positive length in um.")
        coordinates = coordinate_pair(self.position)
        if any(not isfinite(evaluate(value, "um") + sign * radius)
               for value in coordinates for sign in (-1, 1)):
            raise ValueError("Circle bounds must be finite.")
        if evaluate(self.tolerance, "um") <= 0:
            raise ValueError("Circle.tolerance must be a finite positive length in um.")

    def parameter_values(self):
        return (self.radius, *coordinate_pair(self.position), self.tolerance)

    def to_comsol(self, workplane_geometry, tag):
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "Circle")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("type", "solid")
        feature.set("base", "center")
        feature.set("angle", "360")
        feature.set("r", comsol_expression(self.radius, "um"))
        feature.set("pos", [comsol_expression(value, "um")
                            for value in coordinate_pair(self.position)])

    def to_klayout(self):
        from math import asin, ceil, pi, sqrt
        import klayout.db as kdb

        self.validate()
        radius = evaluate(self.radius, "um")
        tolerance = evaluate(self.tolerance, "um")
        # sagitta/r = 2*sin(pi/(2*n))**2. The asin form avoids cancellation
        # for tight tolerances, and the cap bounds memory before allocation.
        ratio = min(tolerance / radius, 1.0)
        maximum = 65536
        if ratio < 2 * sin(pi / (2 * maximum))**2:
            raise ValueError(
                "Circle.tolerance requires more than 65536 GDS vertices; "
                "increase the tolerance."
            )
        count = max(8, ceil(pi / (2 * asin(sqrt(ratio / 2)))))
        count = 4 * ceil(count / 4)
        px, py = (evaluate(value, "um") for value in coordinate_pair(self.position))
        points = [kdb.DPoint(px + radius*cos(2*pi*i/count),
                            py + radius*sin(2*pi*i/count))
                  for i in range(count)]
        return kdb.DPolygon(points)


class Rectangle(GeometryObject):
    """A filled rectangle with ``size=(width, height)``.

    ``position`` is its centre or lower-left corner, according to ``base``.
    Rotation is about this position, matching the native COMSOL Rectangle.
    Dimensions, coordinates and angles retain their parameter references.
    """

    tag_prefix = "rect"

    def __init__(self, project, *, layer, size, position=(0, 0),
                 base="center", angle=0, selections=()):
        super().__init__(project, layer, selections=selections)
        self.size = size if isinstance(size, Vertices) else tuple(size)
        self.position = position if isinstance(position, Vertices) else tuple(position)
        self.base = base
        self.angle = angle
        self.validate()
        project.add(self)

    def validate(self):
        size = coordinate_pair(self.size)
        if any(evaluate(value, "um") <= 0 for value in size):
            raise ValueError("Rectangle.size requires two finite positive lengths in um.")
        coordinate_pair(self.position)
        evaluate(self.angle, "deg")
        if self.base not in ("center", "corner"):
            raise ValueError("Rectangle.base must be 'center' or 'corner'.")

    def parameter_values(self):
        return (*coordinate_pair(self.size), *coordinate_pair(self.position), self.angle)

    def to_comsol(self, workplane_geometry, tag):
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "Rectangle")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("type", "solid")
        feature.set("base", self.base)
        feature.set("size", [comsol_expression(value, "um")
                             for value in coordinate_pair(self.size)])
        feature.set("pos", [comsol_expression(value, "um")
                            for value in coordinate_pair(self.position)])
        feature.set("rot", comsol_expression(self.angle, "deg"))

    def to_klayout(self):
        from math import isfinite
        import klayout.db as kdb

        width, height = (evaluate(value, "um") for value in coordinate_pair(self.size))
        left, bottom = (-width / 2, -height / 2) if self.base == "center" else (0, 0)
        right, top = left + width, bottom + height
        angle = radians(evaluate(self.angle, "deg"))
        c, s = cos(angle), sin(angle)
        px, py = (evaluate(value, "um") for value in coordinate_pair(self.position))
        points = []
        for x, y in ((left, bottom), (right, bottom), (right, top), (left, top)):
            x, y = px + c*x - s*y, py + s*x + c*y
            if not isfinite(x) or not isfinite(y):
                raise ValueError("Rectangle coordinates must remain finite.")
            points.append(kdb.DPoint(x, y))
        return kdb.DPolygon(points)


class CircularArc(GeometryObject):
    """A native circular arc and a sampled, zero-width KLayout path.

    Angles are in degrees. The directed arc runs from ``start_angle`` to
    ``end_angle`` anticlockwise, or clockwise when requested. Equal endpoints
    modulo 360 are rejected; use a separate closed-curve definition for a loop.
    ``tolerance`` bounds the chord error in um before the GDS grid is applied.
    """

    tag_prefix = "arc"

    def __init__(self, project, *, layer, radius, center=(0, 0),
                 start_angle=0, end_angle=90, clockwise=False,
                 tolerance=0.001, selections=()):
        super().__init__(project, layer, selections=selections)
        self.radius = radius
        self.center = center if isinstance(center, Vertices) else tuple(center)
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.clockwise = clockwise
        self.tolerance = tolerance
        self.validate()
        project.add(self)

    def _angles(self):
        start = evaluate(self.start_angle, "deg") % 360
        end = evaluate(self.end_angle, "deg") % 360
        sweep = -((start - end) % 360) if self.clockwise else (end - start) % 360
        if sweep == 0:
            raise ValueError("CircularArc endpoints must have different angles modulo 360.")
        return start, sweep

    def validate(self):
        from math import isfinite

        radius = evaluate(self.radius, "um")
        if radius <= 0:
            raise ValueError("CircularArc.radius must be positive.")
        if not isinstance(self.clockwise, bool):
            raise ValueError("CircularArc.clockwise must be a boolean.")
        for value in coordinate_pair(self.center):
            center = evaluate(value, "um")
            if not all(isfinite(center + sign*radius) for sign in (-1, 1)):
                raise ValueError("CircularArc bounds must be finite.")
        self._angles()
        if evaluate(self.tolerance, "um") <= 0:
            raise ValueError("CircularArc.tolerance must be positive.")

    def parameter_values(self):
        return (self.radius, *coordinate_pair(self.center), self.start_angle,
                self.end_angle, self.tolerance)

    def to_comsol(self, workplane_geometry, tag):
        self.validate()
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "CircularArc")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("specify", "center")
        feature.set("center", [comsol_expression(value, "um")
                               for value in coordinate_pair(self.center)])
        feature.set("r", comsol_expression(self.radius, "um"))
        feature.set("angle1", comsol_expression(self.start_angle, "deg"))
        feature.set("angle2", comsol_expression(self.end_angle, "deg"))
        feature.set("clockwise", "on" if self.clockwise else "off")

    def to_klayout(self):
        from math import asin, ceil, sqrt
        import klayout.db as kdb

        self.validate()
        radius = evaluate(self.radius, "um")
        tolerance = evaluate(self.tolerance, "um")
        start, sweep = (radians(value) for value in self._angles())
        maximum = 65535
        # Sagitta = 2*r*sin(step/4)**2; cap each chord at half a circle.
        step = 4*asin(sqrt(min(tolerance / radius, 1) / 2))
        if step == 0 or abs(sweep) / step > maximum:
            raise ValueError("CircularArc requires more than 65536 points; increase tolerance.")
        count = max(1, ceil(abs(sweep) / step))
        x, y = (evaluate(value, "um") for value in coordinate_pair(self.center))
        points = [kdb.DPoint(x + radius*cos(start + sweep*i/count),
                            y + radius*sin(start + sweep*i/count))
                  for i in range(count + 1)]
        return kdb.DPath(points, 0)


def _bezier_sample(points, weights, tolerance, maximum=65536):
    """Subdivide a positive-weight rational Bezier within a chord-error bound.

    Each rational segment stays inside the convex hull of its control points.
    Bounding those points' distances to the endpoint segment therefore bounds
    the entire curve's distance to that segment, including collinear reversals.
    Homogeneous de Casteljau subdivision preserves the rational curve exactly
    up to floating-point arithmetic.
    """
    from math import hypot, isfinite

    origin = points[0]
    relative = [(x - origin[0], y - origin[1]) for x, y in points]
    scale = max(abs(value) for point in relative for value in point)
    if not isfinite(scale) or scale == 0:
        raise ValueError("Bezier control points must have a finite, nonzero span.")
    largest_weight = max(weights)
    weights = [weight / largest_weight for weight in weights]
    if min(weights) == 0:
        raise ValueError("Bezier weights have too large a ratio for floating-point sampling.")
    homogeneous = [(x / scale * weight, y / scale * weight, weight)
                   for (x, y), weight in zip(relative, weights)]
    tolerance /= scale
    sampled = [points[0]]
    stack = [(homogeneous, 0)]
    while stack:
        controls, depth = stack.pop()
        projected = [(x / weight, y / weight) for x, y, weight in controls]
        ax, ay = projected[0]
        bx, by = projected[-1]
        dx, dy = bx - ax, by - ay
        length_squared = dx*dx + dy*dy
        error = 0.0
        for x, y in projected[1:-1]:
            fraction = (0.0 if length_squared == 0 else
                        min(1.0, max(0.0, ((x - ax)*dx + (y - ay)*dy) / length_squared)))
            error = max(error, hypot(x - (ax + fraction*dx), y - (ay + fraction*dy)))
        if error <= tolerance:
            sampled.append((origin[0] + scale*bx, origin[1] + scale*by))
            continue
        if depth >= 64:
            raise ValueError("Bezier tolerance cannot be resolved with floating-point subdivision.")
        left, right = [controls[0]], [controls[-1]]
        row = controls
        while len(row) > 1:
            row = [tuple(0.5*a + 0.5*b for a, b in zip(first, second))
                   for first, second in zip(row, row[1:])]
            left.append(row[0])
            right.append(row[-1])
        stack.append((list(reversed(right)), depth + 1))
        stack.append((left, depth + 1))
        if len(sampled) + len(stack) > maximum:
            raise ValueError(f"Bezier tolerance requires more than {maximum} KLayout vertices; "
                             "increase the tolerance.")
    # Keep the supplied endpoints exact rather than reconstructing their values.
    sampled[-1] = points[-1]
    return sampled


class _BezierCurve(GeometryObject):
    """Shared native emission and numerical sampling for the two degrees."""

    def __init__(self, project, *, layer, weights, tolerance, selections):
        super().__init__(project, layer, selections=selections)
        self.weights = tuple(weights)
        self.tolerance = tolerance
        self.validate()
        project.add(self)

    def _rows(self):
        return [coordinate_pair(point) for point in self._controls()]

    def _numeric_data(self):
        from math import isfinite

        points = [tuple(evaluate(value, "um") for value in row) for row in self._rows()]
        if len(self.weights) != len(points):
            raise ValueError(f"{type(self).__name__}.weights requires {len(points)} values.")
        weights = [evaluate(value, "") for value in self.weights]
        if any(weight <= 0 for weight in weights):
            raise ValueError("Bezier weights must be finite, positive and dimensionless.")
        if min(weights) / max(weights) == 0:
            raise ValueError("Bezier weights have too large a ratio for floating-point sampling.")
        span = max(abs(value - points[0][axis])
                   for point in points for axis, value in enumerate(point))
        if not isfinite(span) or span == 0:
            raise ValueError("Bezier control points must have a finite, nonzero span.")
        tolerance = evaluate(self.tolerance, "um")
        if tolerance <= 0:
            raise ValueError("Bezier tolerance must be a finite positive length.")
        return points, weights, tolerance

    def validate(self):
        self._numeric_data()

    def parameter_values(self):
        return (*[value for row in self._rows() for value in row],
                *self.weights, self.tolerance)

    def to_comsol(self, workplane_geometry, tag):
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, self._feature_type)
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        rows = self._rows()
        feature.set("p", [[comsol_expression(row[axis], "um") for row in rows]
                          for axis in range(2)])
        feature.set("w", [comsol_expression(weight, "") for weight in self.weights])

    def to_klayout(self):
        import klayout.db as kdb

        points, weights, tolerance = self._numeric_data()
        return kdb.DPath([kdb.DPoint(x, y)
                          for x, y in _bezier_sample(points, weights, tolerance)], 0)


class CubicBezier(_BezierCurve):
    """A native rational cubic Bezier curve and zero-width KLayout path.

    Positive dimensionless ``weights`` default to COMSOL's four unit weights.
    ``tolerance`` bounds KLayout chord error in um, before the GDS grid.
    Control-point, weight and tolerance parameter references remain live.
    """

    tag_prefix = "cbez"
    _feature_type = "CubicBezier"

    def __init__(self, project, *, layer, p0, p1, p2, p3,
                 weights=(1, 1, 1, 1), tolerance=0.001, selections=()):
        self.p0 = p0 if isinstance(p0, Vertices) else tuple(p0)
        self.p1 = p1 if isinstance(p1, Vertices) else tuple(p1)
        self.p2 = p2 if isinstance(p2, Vertices) else tuple(p2)
        self.p3 = p3 if isinstance(p3, Vertices) else tuple(p3)
        super().__init__(project, layer=layer, weights=weights,
                         tolerance=tolerance, selections=selections)

    def _controls(self):
        return self.p0, self.p1, self.p2, self.p3


class InterpolationCurve(GeometryObject):
    """A native open COMSOL interpolation curve through parameter-aware points.

    The COMSOL spline algorithm is not reproduced or replaced by a polyline.
    For KLayout, supply ``sampler(s)`` on [0, 1] describing the desired curve;
    its agreement with the COMSOL spline must be checked by the caller.
    The callback returns coordinates in um, length expressions, or one Vertices.
    ``tolerance`` controls sampled chord refinement, not a certified bound for
    arbitrary callbacks. Increase ``sampling_intervals`` for rapid variations.
    """

    tag_prefix = "ic"

    def __init__(self, project, *, layer, points, sampler=None, parameters=(),
                 tolerance=0.001, sampling_intervals=16, selections=()):
        from ._sampled_curves import named_parameters

        super().__init__(project, layer, selections=selections)
        self.points = points if isinstance(points, Vertices) else Vertices(points)
        self.sampler = sampler
        self.parameters = named_parameters(parameters)
        self.tolerance = tolerance
        self.sampling_intervals = sampling_intervals
        self.validate()
        project.add(self)

    def _vertices(self):
        return self.points if isinstance(self.points, Vertices) else Vertices(self.points)

    def validate(self):
        from ._sampled_curves import named_parameters, validate_sampling

        vertices = self._vertices()
        points = vertices.value
        if len(points) < 2:
            raise ValueError("InterpolationCurve.points requires at least two points.")
        if any(a == b for a, b in zip(points, points[1:])):
            raise ValueError("InterpolationCurve points must not have consecutive duplicates.")
        if points[0] == points[-1]:
            raise ValueError("InterpolationCurve currently requires an open curve with distinct endpoints.")
        named_parameters(self.parameters)
        validate_sampling(self.sampler, self.tolerance, self.sampling_intervals)

    def parameter_values(self):
        return (*self._vertices().parameter_values(), *self.parameters, self.tolerance)

    def to_comsol(self, workplane_geometry, tag):
        self.validate()
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "InterpolationCurve")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("type", "open")
        feature.set("source", "vectors")
        feature.set("rtol", "0")
        feature.set("startcond", "none")
        feature.set("endcond", "none")
        rows = self._vertices().to_comsol()
        feature.set("x", [row[0] for row in rows])
        feature.set("y", [row[1] for row in rows])

    def to_klayout(self):
        from math import hypot
        from ._sampled_curves import sample_callback
        import klayout.db as kdb

        self.validate()
        points = sample_callback(self.sampler, 0, 1, self.tolerance, self.sampling_intervals)
        expected = self._vertices().value
        tolerance = evaluate(self.tolerance, "um")
        for actual, target in ((points[0], expected[0]), (points[-1], expected[-1])):
            if hypot(actual[0] - target[0], actual[1] - target[1]) > tolerance:
                raise ValueError("InterpolationCurve sampler endpoints must match the current "
                                 "interpolation points within tolerance.")
        return kdb.DPath([kdb.DPoint(x, y) for x, y in points], 0)


class LineSegment(GeometryObject):
    """A native COMSOL line segment and a zero-width KLayout path.

    The two endpoints accept length parameters or single-vertex ``Vertices``
    objects. Their references remain live until the next ``build()``.
    This centreline has no filled area; routing can give it a width later.
    """

    tag_prefix = "line"

    def __init__(self, project, *, layer, p1=(0, 0), p2=(1, 0), selections=()):
        super().__init__(project, layer, selections=selections)
        self.p1 = p1 if isinstance(p1, Vertices) else tuple(p1)
        self.p2 = p2 if isinstance(p2, Vertices) else tuple(p2)
        self.validate()
        project.add(self)

    def validate(self):
        start = tuple(evaluate(value, "um") for value in coordinate_pair(self.p1))
        end = tuple(evaluate(value, "um") for value in coordinate_pair(self.p2))
        if start == end:
            raise ValueError("LineSegment endpoints must be distinct.")

    def parameter_values(self):
        return (*coordinate_pair(self.p1), *coordinate_pair(self.p2))

    def to_comsol(self, workplane_geometry, tag):
        self.validate()
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "LineSegment")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("specify1", "coord")
        feature.set("specify2", "coord")
        feature.set("coord1", [comsol_expression(value, "um")
                               for value in coordinate_pair(self.p1)])
        feature.set("coord2", [comsol_expression(value, "um")
                               for value in coordinate_pair(self.p2)])

    def to_klayout(self):
        import klayout.db as kdb

        self.validate()
        points = [kdb.DPoint(*(evaluate(value, "um") for value in coordinate_pair(point)))
                  for point in (self.p1, self.p2)]
        return kdb.DPath(points, 0)


class ParametricCurve(GeometryObject):
    """Native COMSOL coordinate formulas plus an explicit Python evaluator.

    ``coord=(x_expression, y_expression)`` is sent unchanged to COMSOL; Python
    never executes those strings. KLayout needs ``sampler(s)`` returning two
    coordinates in um, length expressions, or one Vertices. List any named
    parameters used in the formulas/callback in ``parameters``. The callable
    and COMSOL expressions are two explicit descriptions of the same curve.

    ``tolerance`` is the sampled chord-refinement criterion for KLayout. It is
    not a rigorous bound for arbitrary callables; increase sampling_intervals
    to resolve rapid variations. COMSOL keeps its own native relative tolerance.
    """

    tag_prefix = "pc"

    def __init__(self, project, *, layer, coord, parname="s", parmin=0, parmax=1,
                 sampler=None, parameters=(), tolerance=0.001,
                 sampling_intervals=16, selections=()):
        from ._sampled_curves import named_parameters

        super().__init__(project, layer, selections=selections)
        self.coord = coord if isinstance(coord, (str, bytes)) else tuple(coord)
        self.parname = parname
        self.parmin = parmin
        self.parmax = parmax
        self.sampler = sampler
        self.parameters = named_parameters(parameters)
        self.tolerance = tolerance
        self.sampling_intervals = sampling_intervals
        self.validate()
        project.add(self)

    def validate(self):
        from ._sampled_curves import named_parameters, parameter_domain, validate_sampling
        from .parameters import _name, collect_parameters

        if (isinstance(self.coord, (str, bytes)) or len(self.coord) != 2
                or any(not isinstance(value, str) or not value.strip() for value in self.coord)):
            raise ValueError("ParametricCurve.coord requires two nonempty COMSOL expression strings.")
        _name(self.parname)
        named_parameters(self.parameters)
        if self.parname in collect_parameters(self.parameter_values()):
            raise ValueError("The curve parameter name must differ from named global parameters.")
        parameter_domain(self.parmin, self.parmax)
        validate_sampling(self.sampler, self.tolerance, self.sampling_intervals)

    def parameter_values(self):
        return (*self.parameters, self.parmin, self.parmax, self.tolerance)

    def to_comsol(self, workplane_geometry, tag):
        self.validate()
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "ParametricCurve")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("coord", list(self.coord))
        feature.set("parname", self.parname)
        feature.set("parmin", comsol_expression(self.parmin, ""))
        feature.set("parmax", comsol_expression(self.parmax, ""))

    def to_klayout(self):
        from ._sampled_curves import sample_callback
        import klayout.db as kdb

        self.validate()
        points = sample_callback(self.sampler, self.parmin, self.parmax,
                                 self.tolerance, self.sampling_intervals)
        return kdb.DPath([kdb.DPoint(x, y) for x, y in points], 0)


class Point(GeometryObject):
    """A single native COMSOL point and a KLayout ``DPoint`` coordinate.

    ``position`` accepts length parameters or one row of ``Vertices``.
    A point creates no marker or other shape in the GDS file.
    """

    tag_prefix = "pt"

    def __init__(self, project, *, layer, position=(0, 0), selections=()):
        super().__init__(project, layer, selections=selections)
        self.position = position if isinstance(position, Vertices) else tuple(position)
        self.validate()
        project.add(self)

    def validate(self):
        for value in coordinate_pair(self.position):
            evaluate(value, "um")

    def parameter_values(self):
        return coordinate_pair(self.position)

    def to_comsol(self, workplane_geometry, tag):
        self.validate()
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "Point")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("p", [comsol_expression(value, "um")
                          for value in coordinate_pair(self.position)])

    def to_klayout(self):
        import klayout.db as kdb

        self.validate()
        return kdb.DPoint(*(evaluate(value, "um") for value in coordinate_pair(self.position)))


class Polygon(GeometryObject):
    """A filled simple polygon, with clockwise or anticlockwise vertices.

    A repeated closing vertex is optional. Concave outlines are accepted;
    holes, repeated interior vertices and intersecting edges are rejected.
    A supplied Vertices object remains live, including coordinate assignments.
    """

    tag_prefix = "pol"

    def __init__(self, project, *, layer, vertices, selections=()):
        super().__init__(project, layer, selections=selections)
        self.vertices = vertices if isinstance(vertices, Vertices) else Vertices(vertices)
        self.validate()
        project.add(self)

    def _rows(self):
        vertices = self.vertices if isinstance(self.vertices, Vertices) else Vertices(self.vertices)
        vertices.validate()
        return vertices.array

    def _points(self):
        points = [tuple(evaluate(value, "um") for value in row) for row in self._rows()]
        if len(points) > 1 and points[-1] == points[0]:
            points.pop()
        return points

    @staticmethod
    def _orientation(a, b, c):
        """Signed turn, allowing only the rounding error of its two products."""
        from sys import float_info

        first = (b[0] - a[0]) * (c[1] - a[1])
        second = (b[1] - a[1]) * (c[0] - a[0])
        value = first - second
        error = 8 * float_info.epsilon * (abs(first) + abs(second))
        return 1 if value > error else -1 if value < -error else 0

    @staticmethod
    def _on_segment(a, b, point):
        return (min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
                and min(a[1], b[1]) <= point[1] <= max(a[1], b[1]))

    @classmethod
    def _edges_intersect(cls, a, b, c, d):
        turns = (cls._orientation(a, b, c), cls._orientation(a, b, d),
                 cls._orientation(c, d, a), cls._orientation(c, d, b))
        if turns[0] * turns[1] < 0 and turns[2] * turns[3] < 0:
            return True
        return ((turns[0] == 0 and cls._on_segment(a, b, c))
                or (turns[1] == 0 and cls._on_segment(a, b, d))
                or (turns[2] == 0 and cls._on_segment(c, d, a))
                or (turns[3] == 0 and cls._on_segment(c, d, b)))

    def validate(self):
        from math import fsum, isfinite
        from sys import float_info

        points = self._points()
        if len(points) < 3:
            raise ValueError("Polygon.vertices requires at least three distinct vertices.")
        if len(set(points)) != len(points):
            raise ValueError("Polygon.vertices cannot repeat vertices except the closing vertex.")
        # Work relative to the first vertex and at unit scale. This avoids
        # cancellation at large offsets and overflow in area/intersection tests.
        x0, y0 = points[0]
        relative = [(x - x0, y - y0) for x, y in points]
        scale = max(abs(value) for point in relative for value in point)
        if not isfinite(scale):
            raise ValueError("Polygon coordinate span is too large.")
        normalized = [(x / scale, y / scale) for x, y in relative]
        count = len(normalized)
        terms = [normalized[i][0] * normalized[(i + 1) % count][1]
                 - normalized[(i + 1) % count][0] * normalized[i][1]
                 for i in range(count)]
        if abs(fsum(terms)) <= 8 * float_info.epsilon * fsum(abs(term) for term in terms):
            raise ValueError("Polygon.vertices must enclose a nonzero area.")
        for first in range(count):
            for second in range(first + 1, count):
                # Adjacent edges are allowed to meet at their shared vertex.
                if second == first + 1 or (first == 0 and second == count - 1):
                    continue
                if self._edges_intersect(normalized[first], normalized[(first + 1) % count],
                                         normalized[second], normalized[(second + 1) % count]):
                    raise ValueError("Polygon.vertices must not self-intersect or retrace edges.")

    def parameter_values(self):
        return tuple(value for row in self._rows() for value in row)

    def to_comsol(self, workplane_geometry, tag):
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "Polygon")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("type", "solid")
        feature.set("source", "vectors")
        rows = [[comsol_expression(value, "um") for value in row] for row in self._rows()]
        # Only discard identical expressions: coincident values may depend on
        # different parameters and diverge after an edit made inside COMSOL.
        if rows[-1] == rows[0]:
            rows.pop()
        feature.set("x", [row[0] for row in rows])
        feature.set("y", [row[1] for row in rows])

    def to_klayout(self):
        import klayout.db as kdb

        return kdb.DPolygon([kdb.DPoint(x, y) for x, y in self._points()])


class QuadraticBezier(_BezierCurve):
    """A native rational quadratic Bezier and zero-width KLayout path.

    ``weights`` defaults to COMSOL's ``(1, 1/sqrt(2), 1)``. Pass ``(1, 1, 1)``
    for an ordinary polynomial quadratic. Weights must be positive and
    dimensionless. ``tolerance`` bounds KLayout chord error in um before the
    GDS grid; native COMSOL retains the analytic curve and its expressions.
    """

    tag_prefix = "qbez"
    _feature_type = "QuadraticBezier"

    def __init__(self, project, *, layer, p0, p1, p2,
                 weights=(1, 2**-0.5, 1), tolerance=0.001, selections=()):
        self.p0 = p0 if isinstance(p0, Vertices) else tuple(p0)
        self.p1 = p1 if isinstance(p1, Vertices) else tuple(p1)
        self.p2 = p2 if isinstance(p2, Vertices) else tuple(p2)
        super().__init__(project, layer=layer, weights=weights,
                         tolerance=tolerance, selections=selections)

    def _controls(self):
        return self.p0, self.p1, self.p2


class Ellipse(GeometryObject):
    """A filled ellipse with two semiaxes, rotated about its centre.

    ``tolerance`` bounds the GDS contour approximation in um before snapping
    to the database grid. COMSOL keeps its native, exact Ellipse feature.
    """

    tag_prefix = "ell"

    def __init__(self, project, *, layer, semiaxes, position=(0, 0),
                 angle=0, tolerance=0.001, selections=()):
        super().__init__(project, layer, selections=selections)
        self.semiaxes = semiaxes if isinstance(semiaxes, Vertices) else tuple(semiaxes)
        self.position = position if isinstance(position, Vertices) else tuple(position)
        self.angle = angle
        self.tolerance = tolerance
        self.validate()
        project.add(self)

    def validate(self):
        axes = coordinate_pair(self.semiaxes)
        if any(evaluate(value, "um") <= 0 for value in axes):
            raise ValueError("Ellipse.semiaxes must be two finite positive lengths.")
        coordinate_pair(self.position)
        evaluate(self.angle, "deg")
        if evaluate(self.tolerance, "um") <= 0:
            raise ValueError("Ellipse.tolerance must be a finite positive length.")
        if self.layer.gds:
            self._sample_count()

    def parameter_values(self):
        return (*coordinate_pair(self.semiaxes), *coordinate_pair(self.position),
                self.angle, self.tolerance)

    def to_comsol(self, workplane_geometry, tag):
        if tag not in list(workplane_geometry.feature().tags()):
            workplane_geometry.create(tag, "Ellipse")
        feature = workplane_geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("type", "solid")
        feature.set("base", "center")
        feature.set("semiaxes", [comsol_expression(value, "um")
                                 for value in coordinate_pair(self.semiaxes)])
        feature.set("pos", [comsol_expression(value, "um")
                           for value in coordinate_pair(self.position)])
        feature.set("rot", comsol_expression(self.angle, "deg"))

    def _sample_count(self):
        from math import asin, ceil, pi, sqrt

        radius = max(evaluate(value, "um") for value in coordinate_pair(self.semiaxes))
        relative_tolerance = evaluate(self.tolerance, "um") / radius
        # An ellipse is a scaled unit circle. Its largest semiaxis bounds the
        # distance from every arc to its chord; rotation preserves that bound.
        step = 4 * asin(sqrt(min(relative_tolerance, 1) / 2))
        if step == 0 or 2 * pi / step > 65_536:
            raise ValueError("Ellipse GDS approximation requires too many points; increase tolerance.")
        return max(4, 4 * ceil((2 * pi / step) / 4))

    def to_klayout(self):
        from math import isfinite, tau
        import klayout.db as kdb

        a, b = (evaluate(value, "um") for value in coordinate_pair(self.semiaxes))
        px, py = (evaluate(value, "um") for value in coordinate_pair(self.position))
        angle = radians(evaluate(self.angle, "deg"))
        c, s = cos(angle), sin(angle)
        count = self._sample_count()
        points = []
        for index in range(count):
            phase = tau * index / count
            x, y = a * cos(phase), b * sin(phase)
            x, y = px + c*x - s*y, py + s*x + c*y
            if not isfinite(x) or not isfinite(y):
                raise ValueError("Ellipse coordinates must remain finite.")
            points.append(kdb.DPoint(x, y))
        return kdb.DPolygon(points)


class BezierPolygon(_PendingPrimitive):
    """Legacy COMSOL primitive, deprecated by COMSOL since 5.5."""
