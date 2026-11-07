"""Planar corner editing, parallel offsets and finite-width curve footprints.

COMSOL retains native geometry and parameter expressions. KLayout uses sampled
contours and Regions on Project.dbu, without an additional geometry dependency.
"""

from math import hypot, isfinite
from numbers import Real

from . import _planar
from .parameters import _quantity, comsol_expression, evaluate
from .transforms import _Transform, _result
from .vertices import Vertices

__all__ = ["Fillet", "Chamfer", "Offset", "Thicken2D"]


def _straight_edges(source):
    """Whether all boundaries are straight, without sampling native curves."""
    from .primitives import Square, Rectangle, Polygon, LineSegment
    from .booleans import _Boolean
    if isinstance(source, (Square, Rectangle, Polygon, LineSegment, Chamfer)):
        return True
    if isinstance(source, Fillet):
        return False
    if isinstance(source, (Offset, Thicken2D)):
        return (source.corner == "extend"
                and (not isinstance(source, Thicken2D) or source.ends == "straight")
                and all(_straight_edges(obj) for obj in source.inputs))
    if isinstance(source, (_Transform, _Boolean)):
        return all(_straight_edges(obj) for obj in source.inputs)
    return False


class _PlanarOperation(_Transform):
    """Reuse the existing ownership, retention and selection conventions."""

    @property
    def _area_output(self):
        from .booleans import _is_filled
        return all(_is_filled(obj) for obj in self.inputs)

    def _polygons(self, region):
        return _result(polygon.to_dtype(self.project.dbu) for polygon in region.each_merged())

    def _region(self, geometry, source):
        return self.project._operation_region(geometry, self, source)


class _CornerOperation(_PlanarOperation):
    """Shared implementation for modifying all or explicitly located corners."""

    def _init_corners(self, target, amount, corners, tolerance, selections):
        super().__init__(target, selections=selections)
        setattr(self, self._amount_name, amount)
        self.corners = None if corners is None else (corners if isinstance(corners, Vertices)
                                                   else Vertices(corners))
        self.tolerance = tolerance
        self.validate()
        self.project.add(self)

    def validate(self):
        from .booleans import _is_filled
        super().validate()
        if self.keep or not self.propagate_selections:
            raise ValueError("Fillet/Chamfer consume their input and propagate selections natively; "
                             "use Copy first to retain the original.")
        if evaluate(getattr(self, self._amount_name), "um") <= 0:
            raise ValueError(f"{type(self).__name__}.{self._amount_name} must be positive.")
        if evaluate(self.tolerance, "um") <= 0:
            raise ValueError("tolerance must be positive.")
        if any(not _is_filled(source) for source in self.inputs):
            raise TypeError("Fillet/Chamfer require filled planar shapes.")
        if self.layer.gds and any(not _straight_edges(source) for source in self.inputs):
            raise ValueError("KLayout Fillet/Chamfer currently require straight-edged inputs; "
                             "editing corners adjoining curved edges is not supported.")
        if self.corners is not None:
            self.corners.validate()
            if not len(self.corners):
                raise ValueError("corners must contain at least one coordinate, or be None for all.")

    def parameter_values(self):
        return (getattr(self, self._amount_name), self.tolerance,
                *(self.corners.parameter_values() if self.corners is not None else ()))

    def to_comsol(self, geometry, tag):
        from jpype import JArray, JInt
        if tag not in list(geometry.feature().tags()):
            geometry.create(tag, type(self).__name__)
        feature = geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("radius" if isinstance(self, Fillet) else "dist",
                    comsol_expression(getattr(self, self._amount_name), "um"))
        geometry.runPre(tag)
        selection = feature.selection("point")
        selection.clear()
        wanted = None if self.corners is None else self.corners.value
        matches = [0]*len(wanted) if wanted is not None else []
        for source in self.inputs:
            for name in geometry.feature(source.tag).objectNames():
                if wanted is None:
                    selection.all(str(name))
                    continue
                coordinates = geometry.obj(name).getVertex()
                ids = []
                for index, (x, y) in enumerate(zip(coordinates[0], coordinates[1]), 1):
                    for number, (px, py) in enumerate(wanted):
                        if hypot(x-px, y-py) <= max(1e-7, self.project.dbu):
                            ids.append(index)
                            matches[number] += 1
                if ids:
                    selection.set(str(name), JArray(JInt)(ids))
        if any(count != 1 for count in matches):
            raise ValueError("Each selected corner must match exactly one COMSOL input vertex.")
        # runPre moved COMSOL's insertion position back to the input. Finish
        # this feature so subsequent geometry is inserted after its result.
        geometry.run(tag)

    def to_klayout(self):
        amount = evaluate(getattr(self, self._amount_name), "um")
        tolerance = evaluate(self.tolerance, "um")
        wanted = None if self.corners is None else self.corners.value
        geometries = self._geometries()
        rings_by_shape = [_planar.contours(shape) for shape in geometries]
        match_tolerance = max(1e-7, self.project.dbu)
        if wanted is not None:
            vertices = [point for rings in rings_by_shape for ring in rings for point in ring]
            if any(sum(hypot(x-px, y-py) <= match_tolerance for x, y in vertices) != 1
                   for px, py in wanted):
                raise ValueError("Each selected corner must match exactly one KLayout input vertex.")
        results = []
        for rings in rings_by_shape:
            edited = [_planar.edit_corners(ring, amount, isinstance(self, Fillet), tolerance,
                                           wanted, match_tolerance,
                                           getattr(self, 'max_trim_fraction', None)) for ring in rings]
            results.append(_planar.polygon(edited))
        return _result(results)


class Fillet(_CornerOperation):
    """Round all corners, or those at coordinates supplied through corners.

    KLayout supports straight-edged filled inputs, including holes and Boolean
    results. radius and tolerance are lengths in um. Copy the input first if
    the original should remain; native Fillet always consumes its inputs.

    max_trim_fraction=None keeps the requested radius unchanged. An explicit
    fraction between 0 and 0.5 limits each tangent trim to that fraction of
    either incident edge, reducing the radius at tight corners. For example,
    0.49 leaves room between neighbouring fillets. This option requires
    one straight-edged input feature in both backends. Use Union first for
    multiple objects; its result may contain holes and disconnected islands.
    The native input must likewise be one geometry object. The trim limit
    does not prevent collisions with other, nonincident edges.

    Native limits come from COMSOL's unsnapped input vertices and edges;
    GDS limits come from its own input contours. COMSOL retains radius as a
    parameter expression, but edge-based limits are recalculated by Python:
    call project.build() after changing dimensions or max_trim_fraction.
    """

    tag_prefix = "fil"
    _amount_name = "radius"

    def __init__(self, target, *, radius, corners=None, tolerance=0.001,
                 max_trim_fraction=None, selections=()):
        self.max_trim_fraction = max_trim_fraction
        self._native_tags = ()
        self._init_corners(target, radius, corners, tolerance, selections)

    def validate(self):
        super().validate()
        fraction = self.max_trim_fraction
        if fraction is not None:
            if len(self.inputs) != 1:
                raise ValueError('A limited Fillet requires one input feature; use Union first for multiple objects.')
            if (isinstance(fraction, bool) or not isinstance(fraction, Real)
                    or not 0 < fraction < 0.5):
                raise ValueError('max_trim_fraction must be None or a number strictly between 0 and 0.5.')
            if any(not _straight_edges(source) for source in self.inputs):
                raise ValueError('A limited Fillet requires straight-edged filled inputs in both backends.')

    def effective_radii(self):
        """Return selected KLayout (corner, radius in um) pairs for inspection.

        These are based on the GDS input contours. Native COMSOL limits are
        calculated independently from its exact vertices, without grid snapping.
        """
        self.validate()
        wanted = None if self.corners is None else self.corners.value
        match_tolerance = max(1e-7, self.project.dbu)
        rings = [ring for shape in self._geometries() for ring in _planar.contours(shape)]
        vertices = [point for ring in rings for point in ring]
        if wanted is not None and any(
                sum(hypot(x-px, y-py) <= match_tolerance for x, y in vertices) != 1
                for px, py in wanted):
            raise ValueError('Each selected corner must match exactly one KLayout input vertex.')
        requested = evaluate(self.radius, 'um')
        result = []
        for ring in rings:
            for index, point in enumerate(ring):
                if wanted is not None and not any(
                        hypot(point[0]-x, point[1]-y) <= match_tolerance for x, y in wanted):
                    continue
                limit = _planar.corner_radius_limit(
                    ring[index-1], point, ring[(index+1) % len(ring)],
                    0.49 if self.max_trim_fraction is None else self.max_trim_fraction)
                if isfinite(limit):
                    result.append((point, requested if self.max_trim_fraction is None
                                   else min(requested, limit)))
        return tuple(result)

    def reset_comsol(self, geometry):
        """Recreate only this fillet's groups when edge-based limits change."""
        if self.max_trim_fraction is None and not self._native_tags:
            return False
        owned = {*self._native_tags, self.tag}
        tags = [str(tag) for tag in geometry.feature().tags() if str(tag) in owned]
        for tag in reversed(tags):
            geometry.feature().remove(tag)
        self._native_tags = ()
        return bool(tags)

    def _native_limits(self, geometry):
        """Use native boundary-edge endpoints, including holes, before rounding."""
        wanted = None if self.corners is None else self.corners.value
        matches = [0]*len(wanted) if wanted is not None else []
        tolerance = max(1e-7, self.project.dbu)
        limits = []
        for source in self.inputs:
            names = list(geometry.feature(source.tag).objectNames())
            if len(names) != 1:
                raise ValueError('A limited Fillet requires one native geometry object; use Union first for multiple objects.')
            for name in names:
                obj = geometry.obj(name)
                coordinates = obj.getVertex()
                points = list(zip(map(float, coordinates[0]), map(float, coordinates[1])))
                edges, endpoints = obj.getEdge(), obj.getStartEnd()
                neighbours = {}
                for index, (start, end) in enumerate(zip(endpoints[0], endpoints[1])):
                    if int(edges[4][index]) > 0 and int(edges[5][index]) > 0:
                        continue  # Zero and negative IDs denote exterior/finite voids.
                    start, end = int(start)-1, int(end)-1
                    neighbours.setdefault(start, []).append(end)
                    neighbours.setdefault(end, []).append(start)
                for index, point in enumerate(points):
                    chosen = wanted is None
                    for number, (x, y) in enumerate(wanted or ()):
                        if hypot(point[0]-x, point[1]-y) <= tolerance:
                            matches[number] += 1
                            chosen = True
                    if not chosen or (wanted is None and index not in neighbours):
                        continue
                    adjacent = neighbours.get(index, [])
                    if len(adjacent) != 2:
                        raise ValueError('Limited Fillet corners require exactly two incident boundary edges.')
                    limit = _planar.corner_radius_limit(points[adjacent[0]], point,
                                                        points[adjacent[1]], self.max_trim_fraction)
                    if isfinite(limit):
                        limits.append((point, limit))
        if any(count != 1 for count in matches):
            raise ValueError('Each selected corner must match exactly one COMSOL input vertex.')
        return limits

    def to_comsol(self, geometry, tag):
        if self.max_trim_fraction is None:
            return super().to_comsol(geometry, tag)
        from jpype import JArray, JInt

        # A temporary terminal feature lets runPre build precisely the inputs.
        geometry.create(tag, 'Fillet')
        self._native_tags = (tag,)
        geometry.runPre(tag)
        groups = {}
        for point, limit in self._native_limits(geometry):
            groups.setdefault(format(limit, '.15g'), []).append(point)
        if not groups:
            return super().to_comsol(geometry, tag)
        geometry.feature().remove(tag)
        self._native_tags = ()
        previous = [source.tag for source in self.inputs]
        requested = comsol_expression(self.radius, 'um')
        if _quantity(self.radius, set())[1] == (0, 0):
            # Inside min(), bare coefficients need the geometry's explicit unit.
            requested = f'({requested})*1[um]'
        for number, (limit, corners) in enumerate(groups.items()):
            current = tag if number == len(groups)-1 else f'{tag}_{number}'
            feature = geometry.create(current, 'Fillet')
            self._native_tags += (current,)
            feature.label(f'{self.layer.name}: {current}')
            feature.set('radius', f'min({requested},{limit}[um])')
            geometry.runPre(current)
            selection = feature.selection('point')
            matches = [0]*len(corners)
            for source_tag in previous:
                for name in geometry.feature(source_tag).objectNames():
                    coordinates = geometry.obj(name).getVertex()
                    ids = []
                    for index, (x, y) in enumerate(zip(coordinates[0], coordinates[1]), 1):
                        for corner, (px, py) in enumerate(corners):
                            if hypot(x-px, y-py) <= max(1e-7, self.project.dbu):
                                ids.append(index)
                                matches[corner] += 1
                    if ids:
                        selection.set(str(name), JArray(JInt)(ids))
            if any(count != 1 for count in matches):
                raise ValueError('Each selected corner must match exactly one COMSOL input vertex.')
            geometry.run(current)
            previous = [current]


class Chamfer(_CornerOperation):
    """Bevel straight-edged filled shapes by equal distance along both edges.

    corners=None edits every corner. Otherwise supply vertex coordinates or
    Vertices, avoiding dependence on backend-specific vertex numbering.
    """

    tag_prefix = "cha"
    _amount_name = "distance"

    def __init__(self, target, *, distance, corners=None, selections=()):
        self._init_corners(target, distance, corners, 0.001, selections)


class _BoundaryOperation(_PlanarOperation):
    def validate(self):
        from .primitives import Point
        super().validate()
        if self.corner not in ("fillet", "extend"):
            raise ValueError("corner must be 'fillet' or 'extend'.")
        if evaluate(self.tolerance, "um") <= 0:
            raise ValueError("tolerance must be positive.")
        def has_point(source):
            return isinstance(source, Point) or any(has_point(obj) for obj in source.inputs)
        if any(has_point(source) for source in self.inputs):
            raise TypeError("Offset/Thicken2D require curves or filled shapes, not points.")

    def _band(self, rings, width, closed, source, ends="straight"):
        import klayout.db as kdb
        result = kdb.Region()
        for ring in rings:
            pieces = _planar.stroke(ring, width, self.corner, ends,
                                    evaluate(self.tolerance, "um"), closed)
            for piece in pieces:
                result += self.project._operation_region(piece, self, source, allow_empty=True)
        result.merge()
        if result.is_empty():
            raise ValueError("The boundary band collapses on the GDS grid; reduce Project.dbu.")
        return result


class Offset(_BoundaryOperation):
    """Grow a filled shape or move a curve to its left by distance (um).

    reverse=True shrinks filled shapes or offsets curves to their right.
    corner='fillet' rounds outward corners; 'extend' intersects adjacent offset
    lines. Native curves remain native in COMSOL and sampled in KLayout.
    """

    tag_prefix = "off"

    def __init__(self, target, *, distance, reverse=False, corner="fillet",
                 tolerance=0.001, keep=False, selections=(), propagate_selections=True):
        super().__init__(target, keep=keep, selections=selections,
                         propagate_selections=propagate_selections)
        self.distance, self.reverse = distance, reverse
        self.corner, self.tolerance = corner, tolerance
        self.validate()
        self.project.add(self)

    def validate(self):
        super().validate()
        if evaluate(self.distance, "um") < 0:
            raise ValueError("Offset.distance must be nonnegative; use reverse=True to reverse direction.")
        if not isinstance(self.reverse, bool):
            raise ValueError("Offset.reverse must be a boolean.")

    def parameter_values(self):
        return self.distance, self.tolerance

    def to_comsol(self, geometry, tag):
        feature = self._feature(geometry, tag, "Offset")
        feature.set("distance", comsol_expression(self.distance, "um"))
        feature.set("reverse", "on" if self.reverse else "off")
        feature.set("convexcorner", self.corner)
        feature.set("trim", "on")

    def to_klayout(self):
        import klayout.db as kdb
        distance = evaluate(self.distance, "um")
        result = []
        for source in self.inputs:
            raw = source.to_klayout()
            for shape in raw if isinstance(raw, tuple) else (raw,):
                if distance == 0:
                    result.append(shape.dup())
                elif isinstance(shape, kdb.DPolygon):
                    base = self._region(shape, source)
                    band = self._band(_planar.contours(shape), 2*distance, True, source)
                    region = base-band if self.reverse else base+band
                    region.merge()
                    result.extend(poly.to_dtype(self.project.dbu) for poly in region.each_merged())
                elif isinstance(shape, kdb.DPath):
                    spine = _planar.points(shape.each_point())
                    closed = spine[0] == spine[-1]
                    if closed:
                        spine.pop()
                    shifted = _planar.parallel(spine, -distance if self.reverse else distance,
                                               self.corner, evaluate(self.tolerance, "um"), closed)
                    if closed:
                        shifted.append(shifted[0])
                    result.append(kdb.DPath([kdb.DPoint(*point) for point in shifted], 0))
                else:
                    raise TypeError("Offset expects a curve or filled polygon.")
        return _result(result)


class Thicken2D(_BoundaryOperation):
    """Symmetric finite-width footprint around curves or filled-shape boundaries.

    width is the total width in um. ends='straight' uses flush ends;
    'circular' adds semicircular caps. corner='fillet' rounds outer joins;
    'extend' uses miter joins. The result is filled polygons, ready for Booleans.
    Asymmetric widths and arbitrary polygon sweeps are outside this initial API.
    """

    tag_prefix = "thi"
    _area_output = True

    def __init__(self, target, *, width, ends="straight", corner="fillet",
                 tolerance=0.001, keep=False, selections=(), propagate_selections=True):
        super().__init__(target, keep=keep, selections=selections,
                         propagate_selections=propagate_selections)
        self.width, self.ends = width, ends
        self.corner, self.tolerance = corner, tolerance
        self.validate()
        self.project.add(self)

    def validate(self):
        super().validate()
        if evaluate(self.width, "um") <= 0:
            raise ValueError("Thicken2D.width must be positive.")
        if self.ends not in ("straight", "circular"):
            raise ValueError("ends must be 'straight' or 'circular'.")

    def parameter_values(self):
        return self.width, self.tolerance

    def to_comsol(self, geometry, tag):
        from jpype import JArray, JInt
        if tag not in list(geometry.feature().tags()):
            geometry.create(tag, "Thicken2D")
        feature = geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("keep", "on" if self.keep else "off")
        feature.set("propagatesel", "on" if self.propagate_selections else "off")
        feature.set("offset", "symmetric")
        feature.set("totalthick", comsol_expression(self.width, "um"))
        feature.set("ends", self.ends)
        feature.set("convexcorner", self.corner)
        # Native whole-object inputs reject solid objects. Selecting all their
        # boundary edges explicitly gives the boundary band for filled shapes.
        geometry.runPre(tag)
        selection = feature.selection("input")
        selection.init(1)
        selection.clear()
        for source in self.inputs:
            for name in geometry.feature(source.tag).objectNames():
                # A filled Boolean can retain interior interfaces for FEM.
                # Only edges bordering the exterior/holes belong to its
                # footprint boundary. Curve edges have domain zero on both sides.
                edges = geometry.obj(name).getEdge()
                ids = [index for index, (left, right) in enumerate(zip(edges[4], edges[5]), 1)
                       if int(left) == 0 or int(right) == 0]
                if ids:
                    selection.set(str(name), JArray(JInt)(ids))

        # New COMSOL features are inserted after the current feature. Restore
        # that position after runPre, before a following transform is created.
        geometry.run(tag)

    def to_klayout(self):
        import klayout.db as kdb
        width = evaluate(self.width, "um")
        results = []
        for source in self.inputs:
            raw = source.to_klayout()
            for shape in raw if isinstance(raw, tuple) else (raw,):
                if isinstance(shape, kdb.DPolygon):
                    rings, closed = _planar.contours(shape), True
                elif isinstance(shape, kdb.DPath):
                    spine = _planar.points(shape.each_point())
                    closed = spine[0] == spine[-1]
                    if closed:
                        spine.pop()
                    rings = [spine]
                else:
                    raise TypeError("Thicken2D expects a curve or filled polygon.")
                band = self._band(rings, width, closed, source, self.ends)
                results.extend(poly.to_dtype(self.project.dbu) for poly in band.each_merged())
        return _result(results)
