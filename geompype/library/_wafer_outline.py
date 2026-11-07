"""Sample a nominal wafer disk clipped by one or two orientation flats."""

from math import asin, atan2, ceil, cos, hypot, isfinite, pi, radians, sin, sqrt, ulp
from numbers import Integral, Real


def _fixed_number(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{name} must be a finite fixed real number; use transforms for live scaling.")
    return float(value)


def _normal(angle):
    """Outward normal, with exact coordinates for quarter-turn angles."""
    angle %= 360
    cardinal = {0: (1.0, 0.0), 90: (0.0, 1.0),
                180: (-1.0, 0.0), 270: (0.0, -1.0)}
    return cardinal[angle] if angle in cardinal else (cos(radians(angle)), sin(radians(angle)))


def _clip(points, normal, height, epsilon):
    """Keep the half-plane normal dot point <= height, retaining shared ends."""
    nx, ny = normal
    result = []
    for a, b in zip(points, points[1:] + points[:1]):
        da = nx*a[0] + ny*a[1] - height
        db = nx*b[0] + ny*b[1] - height
        da = 0.0 if abs(da) <= epsilon else da
        db = 0.0 if abs(db) <= epsilon else db
        if (da <= 0) != (db <= 0):
            fraction = da/(da-db)
            result.append((a[0] + fraction*(b[0]-a[0]),
                           a[1] + fraction*(b[1]-a[1])))
        if db <= 0:
            result.append(b)
    distinct = []
    for point in result:
        if not distinct or hypot(point[0]-distinct[-1][0], point[1]-distinct[-1][1]) > epsilon:
            distinct.append(point)
    if len(distinct) > 1 and hypot(distinct[0][0]-distinct[-1][0],
                                  distinct[0][1]-distinct[-1][1]) <= epsilon:
        distinct.pop()
    return distinct


def clip_half_plane(points, normal, distance):
    """Clip supplied fixed coordinates by a unit outward normal and distance."""
    points = list(points)
    extent = max(abs(distance), *(abs(value) for point in points for value in point))
    return _clip(points, normal, distance, 16*ulp(extent))


def validate_flat_edges(points, cuts):
    """Require every requested flat plane to contribute a visible straight edge."""
    extent = max(abs(value) for point in points for value in point)
    epsilon = 16*ulp(extent)
    for (nx, ny), height in cuts:
        if not any(abs(nx*a[0]+ny*a[1]-height) <= epsilon
                   and abs(nx*b[0]+ny*b[1]-height) <= epsilon
                   and hypot(a[0]-b[0], a[1]-b[1]) > epsilon
                   for a, b in zip(points, points[1:]+points[:1])):
            raise ValueError("The requested flat is hidden by another cut; change its angle or length.")


def wafer_vertices(diameter, *, flats=1, flat_length, secondary_flat_length,
                   secondary_flat_angle=90, tolerance=1.0):
    """Return a counterclockwise wafer polygon in micrometres.

    All dimensions are fixed at construction. The primary outward normal is
    +y; the secondary normal is rotated anticlockwise by secondary_flat_angle
    degrees. Flat lengths specify chords of the uncut circle; overlapping
    cuts can shorten the resulting edges. Their placement makes no assertion about
    crystal orientation or doping. With flats=1, flat_length=0 gives a disk.
    The tolerance bounds arc chord error before any GDS grid conversion.
    """
    diameter = _fixed_number(diameter, 'diameter')
    flat_length = _fixed_number(flat_length, 'flat_length')
    secondary_flat_length = _fixed_number(secondary_flat_length, 'secondary_flat_length')
    secondary_flat_angle = _fixed_number(secondary_flat_angle, 'secondary_flat_angle')
    tolerance = _fixed_number(tolerance, 'tolerance')
    if isinstance(flats, bool) or not isinstance(flats, Integral) or flats not in (1, 2):
        raise ValueError("flats must be the fixed integer 1 or 2.")
    if diameter <= 0 or tolerance <= 0:
        raise ValueError("diameter and tolerance must be positive.")
    if not 0 <= flat_length < diameter or not 0 <= secondary_flat_length < diameter:
        raise ValueError("Flat lengths must be nonnegative and smaller than the diameter.")
    if flats == 2 and (flat_length == 0 or secondary_flat_length == 0):
        raise ValueError("Both flat lengths must be positive when flats=2.")
    if flats == 2 and secondary_flat_angle % 360 == 0:
        raise ValueError("Two flats require distinct outward normals; change secondary_flat_angle.")

    radius = diameter/2
    epsilon = 16*ulp(radius)
    requested = [((0.0, 1.0), flat_length)]
    if flats == 2:
        requested.append((_normal(90 + secondary_flat_angle % 360), secondary_flat_length))
    cuts = []
    # Pin cardinal points and circle/flat intersections before sampling, so
    # clipping cannot shorten the flat by intersecting an approximate chord.
    anchors = {0.0: (radius, 0.0), pi/2: (0.0, radius),
               pi: (-radius, 0.0), 3*pi/2: (0.0, -radius)}
    for (nx, ny), length in requested:
        if length == 0:
            continue
        if length <= 2*epsilon:
            raise ValueError("Flat length is below floating-point resolution for this diameter.")
        half = length/2
        height = sqrt((radius-half)*(radius+half))
        cuts.append(((nx, ny), height))
        for sign in (-1, 1):
            point = (nx*height - sign*ny*half, ny*height + sign*nx*half)
            angle = atan2(point[1], point[0]) % (2*pi)
            anchors[angle] = point

    # This stable form avoids acos(1-tolerance/radius) losing tiny tolerances.
    max_angle = min(pi/2, 4*asin(sqrt(min(tolerance/(2*radius), .5))))
    if max_angle == 0 or 2*pi/max_angle > 65536:
        raise ValueError("Wafer tolerance requires more than 65536 sampled vertices.")
    angles = sorted(anchors)
    spans = [(start, end, ceil((end-start)/max_angle))
             for start, end in zip(angles, angles[1:] + [2*pi])]
    if sum(count for _, _, count in spans) > 65536:
        raise ValueError("Wafer tolerance requires more than 65536 sampled vertices.")
    points = []
    for start, end, count in spans:
        points.append(anchors[start])
        for index in range(1, count):
            angle = start + (end-start)*index/count
            points.append((radius*cos(angle), radius*sin(angle)))
    for normal, height in cuts:
        points = _clip(points, normal, height, epsilon)
    validate_flat_edges(points, cuts)
    return points
