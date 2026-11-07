"""Small contour calculations used by the planar editing operations.

Coordinates remain in um. Region merging and clipping use the project's grid.
"""

from math import acos, atan2, ceil, cos, hypot, pi, sin, tan


def points(contour):
    result = []
    for point in contour:
        xy = (point.x, point.y)
        if not result or xy != result[-1]:
            result.append(xy)
    return result


def contours(polygon):
    return [points(polygon.each_point_hull())] + [
        points(polygon.each_point_hole(index)) for index in range(polygon.holes())]


def unit(a, b):
    x, y = b[0] - a[0], b[1] - a[1]
    length = hypot(x, y)
    if length == 0:
        raise ValueError("A contour contains a zero-length segment.")
    return x / length, y / length


def cross(a, b):
    return a[0]*b[1] - a[1]*b[0]


def arc(center, radius, start, sweep, tolerance):
    # Sagitta <= tolerance; no arbitrary fixed number of circle vertices.
    step = 2*acos(max(-1, 1 - min(tolerance/radius, 1)))
    count = max(1, ceil(abs(sweep)/(pi/2)), ceil(abs(sweep)/max(step, 1e-8)))
    if count > 100000:
        raise ValueError("Arc sampling would exceed 100000 segments; increase tolerance.")
    return [(center[0] + radius*cos(start+sweep*i/count),
             center[1] + radius*sin(start+sweep*i/count)) for i in range(count+1)]


def polygon(rings):
    import klayout.db as kdb
    result = kdb.DPolygon([kdb.DPoint(*point) for point in rings[0]])
    for ring in rings[1:]:
        result.insert_hole([kdb.DPoint(*point) for point in ring])
    return result


def corner_radius_limit(before, point, after, max_trim_fraction):
    """Radius whose tangent trims use at most this fraction of either edge."""
    u, v = unit(before, point), unit(point, after)
    turn = atan2(cross(u, v), u[0]*v[0]+u[1]*v[1])
    if abs(turn) < 1e-10:
        return float('inf')
    if abs(turn) > pi-1e-8:
        raise ValueError("Cannot edit a reversing contour corner.")
    shortest = min(hypot(point[0]-before[0], point[1]-before[1]),
                   hypot(after[0]-point[0], after[1]-point[1]))
    return max_trim_fraction*shortest/tan(abs(turn)/2)


def edit_corners(ring, amount, rounded, tolerance, selected=None, match_tolerance=1e-7,
                 max_trim_fraction=None):
    """Trim straight incident edges and join by an arc or an equal-distance bevel."""
    joins, trims = [], []
    for index, point in enumerate(ring):
        before, after = ring[index-1], ring[(index+1) % len(ring)]
        u, v = unit(before, point), unit(point, after)
        turn = atan2(cross(u, v), u[0]*v[0] + u[1]*v[1])
        chosen = selected is None or any(hypot(point[0]-x, point[1]-y) <= match_tolerance
                                         for x, y in selected)
        if not chosen or abs(turn) < 1e-10:
            joins.append([point])
            trims.append(0)
            continue
        if abs(turn) > pi-1e-8:
            raise ValueError("Cannot edit a reversing contour corner.")
        radius = amount
        if rounded and max_trim_fraction is not None:
            radius = min(amount, corner_radius_limit(before, point, after, max_trim_fraction))
        trim = radius*tan(abs(turn)/2) if rounded else amount
        entry = (point[0]-u[0]*trim, point[1]-u[1]*trim)
        end = (point[0]+v[0]*trim, point[1]+v[1]*trim)
        if rounded:
            sign = 1 if turn > 0 else -1
            center = (entry[0]-sign*u[1]*radius, entry[1]+sign*u[0]*radius)
            join = arc(center, radius, atan2(entry[1]-center[1], entry[0]-center[0]),
                       turn, tolerance)
            join[0], join[-1] = entry, end
        else:
            join = [entry, end]
        joins.append(join)
        trims.append(trim)
    for index, point in enumerate(ring):
        next_point = ring[(index+1) % len(ring)]
        if trims[index] + trims[(index+1) % len(ring)] >= hypot(
                next_point[0]-point[0], next_point[1]-point[1])-1e-10:
            raise ValueError("Corner radius/distance is too large for the incident edges.")
    return [point for join in joins for point in join]


def parallel(points_, distance, corner, tolerance, closed=False):
    """Offset a polyline to its left; closed contours omit a repeated endpoint."""
    if distance == 0:
        return list(points_)
    joins = []
    count = len(points_)
    for index, point in enumerate(points_):
        if not closed and index in (0, count-1):
            u = unit(points_[0], points_[1]) if index == 0 else unit(points_[-2], points_[-1])
            joins.append([(point[0]-u[1]*distance, point[1]+u[0]*distance)])
            continue
        u = unit(points_[index-1], point)
        v = unit(point, points_[(index+1) % count])
        turn = atan2(cross(u, v), u[0]*v[0]+u[1]*v[1])
        a = (point[0]-u[1]*distance, point[1]+u[0]*distance)
        b = (point[0]-v[1]*distance, point[1]+v[0]*distance)
        if abs(turn) < 1e-10:
            joins.append([a])
        elif abs(turn) > pi-1e-8:
            raise ValueError("Cannot offset a path that reverses direction at a vertex.")
        elif corner == "fillet" and turn*distance < 0:
            joins.append(arc(point, abs(distance), atan2(a[1]-point[1], a[0]-point[0]),
                             turn, tolerance))
        else:
            t = cross((b[0]-a[0], b[1]-a[1]), v)/cross(u, v)
            joins.append([(a[0]+t*u[0], a[1]+t*u[1])])
    for index in range(count if closed else count-1):
        next_index = (index+1) % count
        a, b = joins[index][-1], joins[next_index][0]
        u = unit(points_[index], points_[next_index])
        if (b[0]-a[0])*u[0] + (b[1]-a[1])*u[1] <= 1e-10:
            raise ValueError("Curve offset collapses or requires trimming; reduce distance. "
                             "Global curve trimming is not supported in KLayout.")
    result = [point for join in joins for point in join]
    _check_crossings(result, closed)
    return result


def _check_crossings(points_, closed):
    """Reject curve offsets requiring topology-changing trimming."""
    from .primitives import Polygon
    segments = list(zip(points_, points_[1:] + ([points_[0]] if closed else [])))
    ordered = sorted(enumerate(segments), key=lambda item: min(item[1][0][0], item[1][1][0]))
    active = []
    for index, (a, b) in ordered:
        xmin = min(a[0], b[0])
        active = [(j, c, d) for j, c, d in active if max(c[0], d[0]) >= xmin]
        for other, c, d in active:
            if abs(index-other) == 1 or (closed and abs(index-other) == len(segments)-1):
                continue
            if max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1]):
                continue
            if Polygon._edges_intersect(a, b, c, d):
                raise ValueError("Curve offset self-intersects and requires trimming; reduce distance. "
                                 "Global curve trimming is not supported in KLayout.")
        active.append((index, a, b))


def stroke(points_, width, corner, ends, tolerance, closed=False):
    """Return polygon pieces for the footprint of a symmetric polyline stroke."""
    import klayout.db as kdb
    radius = width/2
    if corner == "extend":
        # DPath supplies miter joins and flush ends. Convert to a polygon so
        # subsequent Boolean operations and nonuniform scales see filled area.
        if closed:
            # Put the path seam in a straight edge, not at a corner: DPath's
            # flush start/end would otherwise leave a missing outer wedge.
            midpoint = ((points_[0][0]+points_[1][0])/2, (points_[0][1]+points_[1][1])/2)
            spine = [midpoint] + points_[1:] + [points_[0], midpoint]
        else:
            spine = points_
        path = kdb.DPath([kdb.DPoint(*point) for point in spine], width)
        result = [path.polygon()]
    else:
        result = []
        indices = range(len(points_)) if closed else range(1, len(points_)-1)
        joins = []
        for index in indices:
            center = points_[index]
            u = unit(points_[index-1], center)
            v = unit(center, points_[(index+1) % len(points_)])
            turn = atan2(cross(u, v), u[0]*v[0]+u[1]*v[1])
            if abs(turn) < 1e-10:
                continue
            if abs(turn) > pi-1e-8:
                raise ValueError("Cannot thicken a path that reverses direction at a vertex.")
            joins.append((index, u, v, turn))
        joined_vertices = {index for index, _, _, _ in joins}
        pairs = zip(points_, points_[1:] + ([points_[0]] if closed else []))
        for index, (a, b) in enumerate(pairs):
            u = unit(a, b)
            dx, dy = -u[1]*radius, u[0]*radius
            # Keep each shared centre on its end edge before grid conversion.
            # Rounding just the four corners can move that edge away from the
            # independently rounded join-sector centre, leaving 1-dbu slits.
            # These collinear vertices do not change the floating rectangle.
            outline = [(a[0]+dx, a[1]+dy), (b[0]+dx, b[1]+dy)]
            if (index+1) % len(points_) in joined_vertices:
                outline.append(b)
            outline.extend([(b[0]-dx, b[1]-dy), (a[0]-dx, a[1]-dy)])
            if index in joined_vertices:
                outline.append(a)
            result.append(polygon([outline]))
        for index, u, v, turn in joins:
            center = points_[index]
            sign = -1 if turn > 0 else 1
            start = atan2(sign*u[0], -sign*u[1])
            # Only the outer sector belongs to this join. A full disk would
            # add unwanted round caps near the ends of densely sampled curves.
            join = arc(center, radius, start, turn, tolerance)
            # Use the same arithmetic as the segment rectangles at shared
            # corners; trigonometric reconstruction can round a tie differently.
            join[0] = (center[0]+sign*(-u[1]*radius), center[1]+sign*(u[0]*radius))
            join[-1] = (center[0]+sign*(-v[1]*radius), center[1]+sign*(v[0]*radius))
            result.append(polygon([[center] + join]))
    if not closed and ends == "circular":
        for center in (points_[0], points_[-1]):
            result.append(polygon([arc(center, radius, 0, 2*pi, tolerance)[:-1]]))
    return result
