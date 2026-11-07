"""Exact planar centreline geometry used by the routing layer.

Lengths are in um and angles in radians. These classes contain numerical
geometry only: the public routing objects retain parameters and reevaluate this
geometry on each build. A positive offset is to the left of the travelled path.
"""

from dataclasses import dataclass
from math import acos, atan2, ceil, cos, hypot, isfinite, pi, sin, sqrt, tan


_EPS = 1e-9


def _number(value, name, minimum=None):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{name} must be a finite number.") from error
    if not isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{name} must be finite and >= {minimum}.")
    return result


def _point(value):
    try:
        x, y = value
    except (TypeError, ValueError) as error:
        raise ValueError("Route coordinates must be pairs of finite numbers.") from error
    return _number(x, "x"), _number(y, "y")


def _add(a, b, scale=1):
    return a[0] + scale*b[0], a[1] + scale*b[1]


def _sub(a, b):
    return a[0]-b[0], a[1]-b[1]


def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1]


def _cross(a, b):
    return a[0]*b[1] - a[1]*b[0]


def _distance(a, b):
    return hypot(a[0]-b[0], a[1]-b[1])


def _unit(vector):
    vector = _point(vector)
    length = hypot(*vector)
    if length <= _EPS:
        raise ValueError("A routing direction must be nonzero.")
    return vector[0]/length, vector[1]/length


def _normal(vector):
    return -vector[1], vector[0]


@dataclass(frozen=True)
class LinePiece:
    """Straight part of a route, traversed from start to end."""

    start: tuple
    end: tuple

    def __post_init__(self):
        object.__setattr__(self, "start", _point(self.start))
        object.__setattr__(self, "end", _point(self.end))
        if self.length <= _EPS:
            raise ValueError("A route line must have positive length.")

    @property
    def length(self):
        return _distance(self.start, self.end)

    @property
    def start_direction(self):
        return _unit(_sub(self.end, self.start))

    @property
    def end_direction(self):
        return self.start_direction

    def sample(self, tolerance=0.001):
        _positive_tolerance(tolerance)
        return [self.start, self.end]

    def offset(self, distance):
        distance = _number(distance, "offset")
        normal = _normal(self.start_direction)
        return LinePiece(_add(self.start, normal, distance),
                         _add(self.end, normal, distance))

    def reversed(self):
        return LinePiece(self.end, self.start)


@dataclass(frozen=True)
class ArcPiece:
    """Circular part; positive sweep means counterclockwise travel."""

    center: tuple
    radius: float
    start_angle: float
    sweep: float

    def __post_init__(self):
        object.__setattr__(self, "center", _point(self.center))
        object.__setattr__(self, "radius", _number(self.radius, "radius", 0))
        object.__setattr__(self, "start_angle", _number(self.start_angle, "start angle"))
        object.__setattr__(self, "sweep", _number(self.sweep, "sweep"))
        if self.radius <= _EPS or abs(self.sweep) <= 1e-12 or abs(self.sweep) >= 2*pi:
            raise ValueError("A route arc needs positive radius and a sweep between 0 and 2*pi.")

    def _at(self, angle):
        return _add(self.center, (cos(angle), sin(angle)), self.radius)

    @property
    def start(self):
        return self._at(self.start_angle)

    @property
    def end(self):
        return self._at(self.start_angle+self.sweep)

    @property
    def length(self):
        return self.radius*abs(self.sweep)

    @property
    def start_direction(self):
        sign = 1 if self.sweep > 0 else -1
        return -sign*sin(self.start_angle), sign*cos(self.start_angle)

    @property
    def end_direction(self):
        angle = self.start_angle+self.sweep
        sign = 1 if self.sweep > 0 else -1
        return -sign*sin(angle), sign*cos(angle)

    def sample(self, tolerance=0.001):
        tolerance = _positive_tolerance(tolerance)
        # The chord sagitta is <= tolerance. A quadrant limit also keeps very
        # coarse samples from reducing a semicircle to a single diameter.
        step = min(pi/2, 2*acos(max(-1, 1-min(tolerance/self.radius, 1))))
        count = max(1, ceil(abs(self.sweep)/max(step, 1e-12)))
        if count > 100000:
            raise ValueError("Arc sampling exceeds 100000 segments; increase tolerance.")
        return [self._at(self.start_angle+self.sweep*i/count) for i in range(count+1)]

    def offset(self, distance):
        distance = _number(distance, "offset")
        radius = self.radius-(distance if self.sweep > 0 else -distance)
        if radius <= _EPS:
            raise ValueError("Route offset collapses a bend; increase its radius.")
        return ArcPiece(self.center, radius, self.start_angle, self.sweep)

    def reversed(self):
        return ArcPiece(self.center, self.radius, self.start_angle+self.sweep, -self.sweep)


def _positive_tolerance(value):
    result = _number(value, "sampling tolerance", 0)
    if result == 0:
        raise ValueError("Sampling tolerance must be positive.")
    return result


def _clean_points(points):
    cleaned = []
    for point in points:
        point = _point(point)
        if cleaned and _distance(cleaned[-1], point) <= _EPS:
            continue
        while len(cleaned) >= 2:
            before = _unit(_sub(cleaned[-1], cleaned[-2]))
            after = _unit(_sub(point, cleaned[-1]))
            if abs(_cross(before, after)) > 1e-10:
                break
            if _dot(before, after) < 0:
                raise ValueError("Route reverses direction at a vertex.")
            cleaned.pop()
        cleaned.append(point)
    if len(cleaned) < 2:
        raise ValueError("A route requires two distinct points.")
    return tuple(cleaned)


def _turns_and_trims(points, radius):
    turns, trims = [0.0], [0.0]
    for before, vertex, after in zip(points, points[1:], points[2:]):
        u, v = _unit(_sub(vertex, before)), _unit(_sub(after, vertex))
        turn = atan2(_cross(u, v), _dot(u, v))
        if abs(turn) >= pi-1e-10:
            raise ValueError("Route reverses direction at a vertex.")
        turns.append(turn)
        trims.append(radius*tan(abs(turn)/2))
    return turns+[0.0], trims+[0.0]


class RoutePath:
    """A rounded polyline retaining its exact line/arc decomposition.

    Consecutive duplicate points and forward collinear vertices are removed.
    Requested radii are never reduced to fit. Offsets follow the normal of the
    complete rounded route, so every band remains concentric through a bend.
    """

    def __init__(self, points, radius=0):
        self.radius = _number(radius, "bend radius", 0)
        self.points = _clean_points(points)
        turns, trims = _turns_and_trims(self.points, self.radius)
        for index, (a, b) in enumerate(zip(self.points, self.points[1:])):
            if trims[index]+trims[index+1] > _distance(a, b)+_EPS:
                raise ValueError(f"Bend radius {self.radius:g} is too large for route segment {index}.")
        pieces = []
        current = self.points[0]
        for index in range(1, len(self.points)-1):
            vertex = self.points[index]
            u = _unit(_sub(vertex, self.points[index-1]))
            v = _unit(_sub(self.points[index+1], vertex))
            entry = _add(vertex, u, -trims[index])
            exit_ = _add(vertex, v, trims[index])
            if _distance(current, entry) > _EPS:
                pieces.append(LinePiece(current, entry))
            if self.radius > _EPS:
                sign = 1 if turns[index] > 0 else -1
                center = _add(entry, _normal(u), sign*self.radius)
                angle = atan2(entry[1]-center[1], entry[0]-center[0])
                pieces.append(ArcPiece(center, self.radius, angle, turns[index]))
            current = exit_
        if _distance(current, self.points[-1]) > _EPS:
            pieces.append(LinePiece(current, self.points[-1]))
        self.pieces = tuple(pieces)
        _check_intersections(self.pieces)

    @classmethod
    def from_pieces(cls, pieces):
        """Join already calculated pieces, checking continuity and intersections."""
        result = object.__new__(cls)
        result.pieces = tuple(pieces)
        if not result.pieces:
            raise ValueError("A route requires at least one line or arc.")
        for piece in result.pieces:
            if not isinstance(piece, (LinePiece, ArcPiece)):
                raise TypeError("Route pieces must be LinePiece or ArcPiece objects.")
        for a, b in zip(result.pieces, result.pieces[1:]):
            if _distance(a.end, b.start) > _EPS:
                raise ValueError("Route pieces are not connected.")
        result.points = None  # Offsets need not have one common fillet radius.
        result.radius = None
        _check_intersections(result.pieces)
        return result

    @property
    def start(self):
        return self.pieces[0].start

    @property
    def end(self):
        return self.pieces[-1].end

    @property
    def length(self):
        return sum(piece.length for piece in self.pieces)

    @property
    def start_direction(self):
        return self.pieces[0].start_direction

    @property
    def end_direction(self):
        return self.pieces[-1].end_direction

    def sample(self, tolerance=0.001):
        tolerance = _positive_tolerance(tolerance)
        result = []
        for piece in self.pieces:
            samples = piece.sample(tolerance)
            result.extend(samples if not result else samples[1:])
        return result

    def offset(self, distance):
        distance = _number(distance, "offset")
        if distance == 0:
            return self
        for a, b in zip(self.pieces, self.pieces[1:]):
            if _dot(a.end_direction, b.start_direction) < 1-1e-10:
                raise ValueError("Offsetting a sharp route corner requires a positive bend radius.")
        return RoutePath.from_pieces(piece.offset(distance) for piece in self.pieces)

    def reversed(self):
        return RoutePath.from_pieces(piece.reversed() for piece in reversed(self.pieces))

    @classmethod
    def manhattan(cls, start, end, start_direction, end_direction, *, radius=0,
                  start_straight=0, end_straight=0):
        """Select a short route respecting outward endpoint directions.

        Directions may share any rotated orthogonal frame. The last travelled
        tangent is opposite ``end_direction``. Candidate routing is deterministic
        and has no obstacle search; callers check the complete profile footprint.
        Minimum straight lengths apply *after* rounding, not to untrimmed legs.
        """
        start, end = _point(start), _point(end)
        u, out = _unit(start_direction), _unit(end_direction)
        n = _normal(u)
        local_out = (_dot(out, u), _dot(out, n))
        cardinal = min(((1., 0.), (-1., 0.), (0., 1.), (0., -1.)),
                       key=lambda v: _distance(v, local_out))
        if _distance(cardinal, local_out) > 1e-9:
            raise ValueError("Manhattan ports must have parallel or perpendicular orientations.")
        radius = _number(radius, "bend radius", 0)
        s0 = _number(start_straight, "start straight", 0)
        s1 = _number(end_straight, "end straight", 0)
        delta = _sub(end, start)
        finish = (_dot(delta, u), _dot(delta, n))
        if hypot(*finish) <= _EPS:
            raise ValueError("Cannot route between coincident ports.")
        # A small nonzero exploration distance also permits sharp-corner routes.
        pad = max(2*radius, s0, s1, hypot(*finish)/4, 1.0)
        a = (s0+max(radius, _EPS*10), 0.)
        b = _add(finish, cardinal, s1+max(radius, _EPS*10))
        xs = ((a[0]+b[0])/2, min(0, finish[0], a[0], b[0])-pad,
              max(0, finish[0], a[0], b[0])+pad)
        ys = ((a[1]+b[1])/2, min(0, finish[1], a[1], b[1])-pad,
              max(0, finish[1], a[1], b[1])+pad)
        # A direct straight needs no bend clearance. In particular, ports may
        # be closer than twice the requested radius when there is no corner.
        middles = [[], [a, b], [a, (b[0], a[1]), b], [a, (a[0], b[1]), b]]
        middles.extend([a, (x, a[1]), (x, b[1]), b] for x in xs)
        middles.extend([a, (a[0], y), (b[0], y), b] for y in ys)
        for x in xs:
            for y in ys:
                middles.append([a, (x, a[1]), (x, y), (b[0], y), b])
                middles.append([a, (a[0], y), (x, y), (x, b[1]), b])
        choices = []
        for middle in middles:
            local = [(0., 0.), *middle, finish]
            if any(abs(p[0]-q[0]) > _EPS and abs(p[1]-q[1]) > _EPS
                   for p, q in zip(local, local[1:])):
                continue
            world = [_add(_add(start, u, p[0]), n, p[1]) for p in local]
            try:
                candidate = cls(world, radius)
            except ValueError:
                continue
            if _dot(candidate.start_direction, u) < 1-1e-9:
                continue
            if _dot(candidate.end_direction, out) > -1+1e-9:
                continue
            first, last = candidate.pieces[0], candidate.pieces[-1]
            if (first.length if isinstance(first, LinePiece) else 0) < s0-_EPS:
                continue
            if (last.length if isinstance(last, LinePiece) else 0) < s1-_EPS:
                continue
            bends = sum(isinstance(piece, ArcPiece) for piece in candidate.pieces)
            choices.append((candidate.length+radius*bends/10, bends, candidate))
        if not choices:
            raise ValueError("No Manhattan candidate satisfies the endpoint directions, straights and bend radius.")
        return min(choices, key=lambda choice: choice[:2])[2]

    def meander(self, count, amplitude, *, segment=None, offset=0,
                start_straight=0, end_straight=0):
        """Add alternating rectangular excursions to one unrounded segment.

        ``count`` is the number of lateral plateaus, ``amplitude`` their distance
        from the original axis, and ``offset`` shifts their common lateral centre.
        First plateau lies on the left. The endpoints remain fixed. ``segment``
        indexes the cleaned input polyline; by default the longest eligible leg
        is tried first. Bends retain this route's radius; infeasible spacing fails.
        """
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("Meander count must be a nonnegative integer.")
        amplitude = _number(amplitude, "meander amplitude", 0)
        offset = _number(offset, "meander offset")
        start_straight = _number(start_straight, "start straight", 0)
        end_straight = _number(end_straight, "end straight", 0)
        if count == 0:
            return self
        if self.points is None:
            raise ValueError("Insert meanders before offsetting or joining route pieces.")
        if amplitude <= abs(offset)+_EPS:
            raise ValueError("Meander amplitude must exceed the absolute lateral offset.")
        if amplitude-abs(offset) < 2*self.radius-_EPS:
            raise ValueError("Meander amplitude is too small for its bend radius.")
        lengths = [_distance(a, b) for a, b in zip(self.points, self.points[1:])]
        if segment is None:
            indices = sorted(range(len(lengths)), key=lambda i: -lengths[i])
        elif isinstance(segment, int) and not isinstance(segment, bool) and 0 <= segment < len(lengths):
            indices = [segment]
        else:
            raise ValueError("Meander segment is outside the route's input polyline.")
        _, trims = _turns_and_trims(self.points, self.radius)
        errors = []
        for index in indices:
            a, b = self.points[index:index+2]
            u = _unit(_sub(b, a))
            n = _normal(u)
            margin = max(2*self.radius, lengths[index]*0.05, _EPS*10)
            x0, x1 = trims[index]+margin, lengths[index]-trims[index+1]-margin
            if index == 0:
                x0 = max(x0, start_straight+self.radius)
            if index == len(lengths)-1:
                x1 = min(x1, lengths[index]-end_straight-self.radius)
            pitch = (x1-x0)/count
            if pitch < max(2*self.radius, _EPS)-_EPS:
                errors.append("segment is too short for the requested number of bends")
                continue
            local = [(x0, 0.)]
            for number in range(count):
                y = offset + (amplitude if number % 2 == 0 else -amplitude)
                local.extend([(x0+number*pitch, y), (x0+(number+1)*pitch, y)])
            local.append((x1, 0.))
            inserted = [_add(_add(a, u, x), n, y) for x, y in local]
            try:
                return RoutePath((*self.points[:index+1], *inserted,
                                  *self.points[index+1:]), self.radius)
            except ValueError as error:
                errors.append(str(error))
        raise ValueError("Cannot fit the requested meander: "+errors[0]+".")


def _arc_contains(arc, point):
    angle = atan2(point[1]-arc.center[1], point[0]-arc.center[0])
    travel = ((angle-arc.start_angle) if arc.sweep > 0 else
              (arc.start_angle-angle)) % (2*pi)
    return travel <= abs(arc.sweep)+1e-10 or travel >= 2*pi-1e-10


def _intersections(a, b):
    """Intersection points; coincident intervals return their shared endpoints."""
    if isinstance(a, LinePiece) and isinstance(b, LinePiece):
        u, v, delta = _sub(a.end, a.start), _sub(b.end, b.start), _sub(b.start, a.start)
        denominator = _cross(u, v)
        if abs(denominator) <= 1e-12*a.length*b.length:
            if abs(_cross(delta, u)) > _EPS*a.length:
                return []
            answer = []
            for point in (a.start, a.end, b.start, b.end):
                if all(_dot(_sub(point, line.start), _sub(point, line.end)) <= _EPS**2
                       for line in (a, b)):
                    answer.append(point)
            return answer
        t, s = _cross(delta, v)/denominator, _cross(delta, u)/denominator
        return [_add(a.start, u, t)] if -1e-10 <= t <= 1+1e-10 and -1e-10 <= s <= 1+1e-10 else []
    if isinstance(a, ArcPiece) and isinstance(b, LinePiece):
        return _intersections(b, a)
    if isinstance(a, LinePiece):
        # Projection avoids subtracting two large quadratic discriminant terms
        # at a tangent, which could invent intersections next to shared ends.
        direction = a.start_direction
        relative = _sub(b.center,a.start)
        projection = _dot(relative,direction)
        perpendicular = _cross(relative,direction)
        height2 = b.radius*b.radius-perpendicular*perpendicular
        threshold = 1e-12*max(1,b.radius*b.radius)
        if height2 < -threshold:
            return []
        root = 0 if abs(height2) <= threshold else sqrt(height2)
        result = []
        for distance in (projection-root,projection+root):
            if -_EPS <= distance <= a.length+_EPS:
                point = _add(a.start,direction,distance)
                if _arc_contains(b, point):
                    result.append(point)
        return result
    delta = _sub(b.center, a.center)
    distance = hypot(*delta)
    if distance <= _EPS:
        if abs(a.radius-b.radius) > _EPS:
            return []
        return [point for point in (a.start, a.end, b.start, b.end)
                if _arc_contains(a, point) and _arc_contains(b, point)]
    if distance > a.radius+b.radius+_EPS or distance < abs(a.radius-b.radius)-_EPS:
        return []
    x = (a.radius*a.radius-b.radius*b.radius+distance*distance)/(2*distance)
    h = sqrt(max(0., a.radius*a.radius-x*x))
    direction = (delta[0]/distance, delta[1]/distance)
    middle = _add(a.center, direction, x)
    return [point for point in (_add(middle, _normal(direction), h),
                               _add(middle, _normal(direction), -h))
            if _arc_contains(a, point) and _arc_contains(b, point)]


def _check_intersections(pieces):
    for index, a in enumerate(pieces):
        for other in range(index+1, len(pieces)):
            b = pieces[other]
            intersections = _intersections(a, b)
            # Only a neighbouring pair's common endpoint is allowed. Adjacent
            # pieces may otherwise overlap (e.g. reversing arcs).
            if any(other != index+1 or _distance(point, a.end) > 1e-7
                   for point in intersections):
                raise ValueError(f"Route self-intersects between pieces {index} and {other}.")
