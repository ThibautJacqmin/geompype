"""Planar multi-band ports and connections for microwave circuits.

Ports point out of components. Routes leave the first port along its direction
and arrive opposite the last port's direction. Positive offsets lie to the left
of travel. Parameters are reevaluated on build; routing is performed in Python.
COMSOL receives analytic lines/arcs and native Thicken2D. KLayout receives the
same centreline sampled into a finite-width DPath, converted to polygons when
used as fabrication geometry. All lengths are in micrometres.
"""

from math import ceil, cos, degrees, hypot, sin

from .geometry import GeometryObject
from .parameters import comsol_expression, evaluate, maximum
from .primitives import Polygon
from .vertices import Vertices, coordinate_pair
from ._routing_path import ArcPiece, LinePiece, RoutePath


def _length(value):
    return coordinate_pair(Vertices((value, 0)))[0]


def _xy(value):
    return tuple(evaluate(v, "um") for v in coordinate_pair(value))


def _direction(value):
    x, y = (evaluate(v, "") for v in value)
    norm = hypot(x, y)
    if norm == 0:
        raise ValueError("Port orientation cannot be zero.")
    return x/norm, y/norm


def _shift(point, direction, distance):
    return tuple(p+distance*d for p, d in zip(point, direction))


class PortProfile:
    """Named bands with widths, signed offsets and actual project Layers.

    A gap band is an enclosing footprint, not a pair of slots. Use ``cpw`` to
    turn a signal width and a clearance on each side into the appropriate bands.
    All bands belong to the same workplane; routing uses its local coordinates.
    """

    def __init__(self, *, widths, layers, offsets=0, names=None):
        self.widths = tuple(widths)
        self.layers = tuple(layers)
        self.offsets = (tuple(offsets) if isinstance(offsets, (tuple, list))
                        else (offsets,)*len(self.widths))
        self.names = tuple(names) if names is not None else tuple(f"band{i}" for i in range(len(self.widths)))
        self._nonnegative_lengths = ()
        self.validate()

    @classmethod
    def cpw(cls, track, gap, signal_layer, gap_layer, *, mask_layer=None, mask_margin=0):
        """Signal width track; gap is the clearance on each side."""
        track, gap, mask_margin = map(_length, (track, gap, mask_margin))
        if evaluate(gap, "um") < 0 or evaluate(mask_margin, "um") < 0:
            raise ValueError("CPW gap and mask margin must be nonnegative.")
        widths, layers, names = [track, track+2*gap], [signal_layer, gap_layer], ["signal", "gap"]
        if mask_layer is not None:
            widths.append(track+2*gap+2*mask_margin)
            layers.append(mask_layer)
            names.append("mask")
        result = cls(widths=widths, layers=layers, names=names)
        result._nonnegative_lengths = (gap, mask_margin)
        return result

    @property
    def project(self):
        return self.layers[0].project

    def validate(self):
        n = len(self.widths)
        if not n or len(self.layers) != n or len(self.offsets) != n or len(self.names) != n:
            raise ValueError("Profile widths, offsets, layers and names must have the same nonzero length.")
        if len(set(self.names)) != n or any(not isinstance(name, str) or not name for name in self.names):
            raise ValueError("Profile band names must be unique nonempty strings.")
        project = self.layers[0].project
        if project is None or any(project.layers.get(layer.name) is not layer for layer in self.layers):
            raise ValueError("Profile layers must belong to one project.")
        if any(layer.workplane is not self.layers[0].workplane for layer in self.layers):
            raise ValueError("Profile layers must belong to one workplane.")
        if any(evaluate(width, "um") <= 0 for width in self.widths):
            raise ValueError("Profile band widths must be positive.")
        for offset in self.offsets:
            evaluate(offset, "um")
        if any(evaluate(value, "um") < 0 for value in self._nonnegative_lengths):
            raise ValueError("CPW gap and mask margin must be nonnegative.")

    def parameter_values(self):
        return (*self.widths, *self.offsets)

    def reversed(self):
        result = PortProfile(widths=self.widths, offsets=[-v for v in self.offsets],
                             layers=self.layers, names=self.names)
        result._nonnegative_lengths = self._nonnegative_lengths
        return result

    def outer_bounds(self):
        """Return (upper, lower) transverse bounds as live length expressions."""
        self.validate()
        unit = _length(1)
        upper = lower = None
        for width, offset in zip(self.widths, self.offsets):
            width, offset = _length(width), _length(offset)
            top, bottom = offset+width/2, offset-width/2
            upper = top if upper is None else maximum(upper/unit, top/unit)*unit
            lower = bottom if lower is None else -maximum(-lower/unit, -bottom/unit)*unit
        return upper, lower

    def with_mask(self, layer, *, margin=0, name="mask"):
        """Append an enclosing band, including asymmetric offsets and live bounds."""
        margin = _length(margin)
        if evaluate(margin, "um") < 0:
            raise ValueError("Mask margin must be nonnegative.")
        upper, lower = self.outer_bounds()
        result = PortProfile(widths=(*self.widths, upper-lower+2*margin),
                             offsets=(*self.offsets, (upper+lower)/2),
                             layers=(*self.layers, layer), names=(*self.names, name))
        result._nonnegative_lengths = (*self._nonnegative_lengths, margin)
        return result


class Port:
    """A mutable placement with live coordinates and an optional band profile.

    A port without a profile is an oriented waypoint. ``reversed()`` returns a
    live view: moving the original component also moves its reverse port.
    """

    def __init__(self, *, pos=(0, 0), orientation=(1, 0), profile=None, name="port"):
        self.pos = pos if isinstance(pos, Vertices) else Vertices(pos)
        self.orientation = tuple(orientation)
        self.profile = profile
        self.name = str(name)
        self.validate()

    @property
    def position(self):
        return _xy(self.pos)

    @property
    def direction(self):
        return _direction(self.orientation)

    @property
    def normal(self):
        """Unit normal to the left of the outward port direction."""
        x, y = self.direction
        return -y, x

    def local_point(self, along=0, cross=0):
        """A Vertices point in this frame; scalar length parameters stay live.

        Placement/orientation is read when called. Split ports and drawn markers
        call this again on every build, so they also follow component movement.
        """
        along, cross = _length(along), _length(cross)
        return Vertices([p+along*d+cross*n for p, d, n in
                         zip(coordinate_pair(Vertices(self.pos)), self.direction, self.normal)])

    def _bands(self, bands=None):
        if self.profile is None:
            raise ValueError("This port has no band profile.")
        self.profile.validate()
        if bands is None:
            return tuple(range(len(self.profile.names)))
        bands = (bands,) if isinstance(bands, (str, int)) else tuple(bands)
        indices = []
        for band in bands:
            if isinstance(band, str) and band in self.profile.names:
                index = self.profile.names.index(band)
            elif isinstance(band, int) and not isinstance(band, bool) and 0 <= band < len(self.profile.names):
                index = band
            else:
                raise ValueError(f"Unknown band {band!r}; use a band name or zero-based index.")
            if index in indices:
                raise ValueError("Select each port band only once.")
            indices.append(index)
        return tuple(indices)

    def track_center(self, band, along=0):
        """Centre of a named band (or zero-based band index), as Vertices."""
        index, = self._bands(band)
        return self.local_point(along, self.profile.offsets[index])

    def track_edges(self, band, along=0):
        """Return (upper, lower) band-edge Vertices in the port frame."""
        index, = self._bands(band)
        offset, half = _length(self.profile.offsets[index]), _length(self.profile.widths[index])/2
        return self.local_point(along, offset+half), self.local_point(along, offset-half)

    def bond_params(self):
        """Return numerical (upper, lower) transverse band bounds in um."""
        self._bands()
        return tuple(evaluate(value, "um") for value in self.profile.outer_bounds())

    def split(self, bands=None, *, gap=None, gap_layer):
        """Return live CPW ports centred on selected bands, in selection order.

        Each result has ``signal`` and enclosing ``gap`` bands. ``gap`` is the
        clearance on each side; omitted gap equals that signal's width. Select
        names explicitly when an enclosing mask/gap should not itself be split.
        The results follow the original port and are placed through that port.
        """
        indices = self._bands(bands)
        ports = tuple(_SplitPort(self, index, gap, gap_layer) for index in indices)
        for port in ports:
            port.validate()
        return ports

    def marker_triangles(self, *, bands=None, tip_length=None, tip_scale=1/3):
        """Return one outward-pointing triangular Vertices per selected band."""
        indices = self._bands(bands)
        scale = evaluate(tip_scale, "")
        if tip_length is None and scale <= 0:
            raise ValueError("Marker tip scale must be positive.")
        if tip_length is not None and evaluate(tip_length, "um") <= 0:
            raise ValueError("Marker tip length must be positive.")
        triangles = []
        for index in indices:
            length = _length(self.profile.widths[index])*tip_scale if tip_length is None else tip_length
            top, bottom = self.track_edges(index)
            tip = self.local_point(length, self.profile.offsets[index])
            triangles.append(top.concat(tip, bottom))
        return tuple(triangles)

    def draw_markers(self, *, layer, bands=None, tip_length=None, tip_scale=1/3, selections=()):
        """Draw live Polygon markers on an explicit layer in the same workplane."""
        from .components import _assembly
        indices = self._bands(bands)
        self.marker_triangles(bands=indices, tip_length=tip_length, tip_scale=tip_scale)
        if (layer.project is not self.profile.project
                or layer.workplane is not self.profile.layers[0].workplane):
            raise ValueError("Port markers must belong to the port's project and workplane.")
        with _assembly(layer.project):
            return tuple(_PortMarker(self, index, layer, tip_length, tip_scale, selections)
                         for index in indices)

    def validate(self):
        self.position
        self.direction
        if self.profile is not None:
            self.profile.validate()

    def parameter_values(self):
        return (*coordinate_pair(self.pos), *self.orientation,
                *(self.profile.parameter_values() if self.profile is not None else ()))

    def reversed(self):
        return _ReversePort(self)

    @property
    def r(self):
        return self.reversed()


class _ReversePort(Port):
    def __init__(self, original):
        self.original = original
        self.name = original.name+"_reverse"

    @property
    def pos(self):
        return self.original.pos

    @property
    def orientation(self):
        return tuple(-v for v in self.original.orientation)

    @property
    def profile(self):
        return None if self.original.profile is None else self.original.profile.reversed()

    def reversed(self):
        return self.original


class _SplitPort(Port):
    """A read-only placement view: parent placement and dimensions remain live."""

    def __init__(self, original, index, gap, gap_layer):
        self.original, self.index, self.gap, self.gap_layer = original, index, gap, gap_layer
        self.name = original.name+"_"+original.profile.names[index]

    @property
    def pos(self):
        return self.original.track_center(self.index)

    @property
    def orientation(self):
        return self.original.orientation

    @property
    def profile(self):
        source = self.original.profile
        width = source.widths[self.index]
        return PortProfile.cpw(width, width if self.gap is None else self.gap,
                               source.layers[self.index], self.gap_layer)

    def parameter_values(self):
        return (*self.original.parameter_values(), *super().parameter_values())


class _PortMarker(Polygon):
    """Ordinary native Polygon whose vertices follow its source port."""

    def __init__(self, port, index, layer, tip_length, tip_scale, selections):
        self.port, self.index = port, index
        self.tip_length, self.tip_scale = tip_length, tip_scale
        GeometryObject.__init__(self, layer.project, layer, selections=selections)
        self.validate()
        self.project.add(self)

    @property
    def vertices(self):
        return self.port.marker_triangles(bands=self.index, tip_length=self.tip_length,
                                          tip_scale=self.tip_scale)[0]

    def parameter_values(self):
        return (*self.port.parameter_values(), *super().parameter_values())

    def validate(self):
        self.port.validate()
        if (self.port.profile.project is not self.project
                or self.port.profile.layers[0].workplane is not self.layer.workplane):
            raise ValueError("Port markers must remain in their source port's project and workplane.")
        super().validate()


class Route:
    """A live path request, resolved before either backend emits geometry.

    ``via`` contains oriented Ports without profiles. Their orientation is the
    forward tangent of the route. Alternatively ``points`` supplies the complete
    unrounded polyline (including endpoints). Meanders are prescribed by count
    and amplitude, or fitted exactly to target_length. Omit meander_count to try
    the fewest feasible bends automatically; meander_max_amplitude optionally
    bounds the lateral excursion. The search tries up to 256 plateaus on one
    segment, longest segments first. Length is geometric, not an electrical
    resonance prediction. Obstacles are checked on the project grid.
    """

    def __init__(self, start, end, *, radius=0, via=(), points=None,
                 start_straight=0, end_straight=0, meander_count=None,
                 meander_amplitude=0, meander_segment=None, meander_offset=0,
                 meander_max_amplitude=None,
                 target_length=None, length_tolerance=0.001, taper_slope=0.5,
                 tolerance=0.001, obstacles=(), clearance=0, name="connection"):
        if not isinstance(start, Port) or not isinstance(end, Port):
            raise TypeError("Routes connect Port objects.")
        self.start, self.end, self.radius = start, end, radius
        self.via = tuple(via)
        self.points = None if points is None else (points if isinstance(points, Vertices) else Vertices(points))
        self.start_straight, self.end_straight = start_straight, end_straight
        self.meander_count, self.meander_amplitude = meander_count, meander_amplitude
        self.meander_segment, self.meander_offset = meander_segment, meander_offset
        self.meander_max_amplitude = meander_max_amplitude
        self.target_length, self.length_tolerance = target_length, length_tolerance
        self.taper_slope, self.tolerance = taper_slope, tolerance
        self.obstacles, self.clearance, self.name = tuple(obstacles), clearance, str(name)

    def parameter_values(self):
        values = [*self.start.parameter_values(), *self.end.parameter_values(), self.radius,
                  self.start_straight, self.end_straight,
                  self.meander_amplitude, self.meander_offset, self.taper_slope,
                  self.tolerance, self.clearance, self.length_tolerance]
        if self.meander_count is not None:
            values.append(self.meander_count)
        if self.meander_max_amplitude is not None:
            values.append(self.meander_max_amplitude)
        if self.target_length is not None:
            values.append(self.target_length)
        if self.points is not None:
            values.extend(self.points.parameter_values())
        for port in self.via:
            values.extend(port.parameter_values())
        return tuple(values)

    def _automatic_meander(self, path, target, offset, straights, bands, maximum_amplitude):
        """Search topology, solving amplitude analytically for each candidate."""
        lengths = [hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(path.points, path.points[1:])]
        if self.meander_segment is None:
            segments = sorted(range(len(lengths)), key=lambda i: -lengths[i])
        elif (isinstance(self.meander_segment, int) and not isinstance(self.meander_segment, bool)
              and 0 <= self.meander_segment < len(lengths)):
            segments = [self.meander_segment]
        else:
            raise ValueError("Meander segment is outside the route's input polyline.")
        width = max(o+w/2 for o, w in bands)-min(o-w/2 for o, w in bands)
        minimum_pitch = max(2*path.radius, width, self.start.profile.project.dbu)
        limit = min(256, int(max(lengths[i] for i in segments)/minimum_pitch))
        minimum = 2*path.radius+abs(offset)+1e-7
        last_error = "no segment has enough room for the bends"
        for count in range(1, limit+1):
            for segment in segments:
                options = dict(segment=segment, offset=offset,
                               start_straight=straights[0], end_straight=straights[1])
                try:
                    trial = path.meander(count, minimum, **options)
                    amplitude = minimum+(target-trial.length)/(2*count)
                    if amplitude < minimum-1e-7:
                        last_error = "target is below the minimum rounded meander length"
                        continue
                    if maximum_amplitude is not None and amplitude > maximum_amplitude+1e-8:
                        last_error = "required amplitude exceeds meander_max_amplitude"
                        continue
                    candidate = path.meander(count, amplitude, **options)
                    for band_offset, band_width in bands:
                        candidate.offset(band_offset-band_width/2)
                        candidate.offset(band_offset+band_width/2)
                    return candidate, count, amplitude
                except ValueError as error:
                    last_error = str(error)
        raise ValueError("Cannot fit target length automatically (up to 256 plateaus): "+last_error+".")

    def resolve(self):
        """Return exact centreline, taper length, and destination profile in travel frame."""
        self.start.validate()
        self.end.validate()
        profile, destination = self.start.profile, self.end.profile
        if profile is None or destination is None:
            raise ValueError("Both endpoint ports must have a profile; use via for constraint ports.")
        if (profile.project is destination.project
                and profile.layers[0].workplane is not destination.layers[0].workplane):
            raise ValueError("Planar routes require both endpoint ports on the same workplane.")
        if (len(profile.layers) != len(destination.layers)
                or any(a is not b for a,b in zip(profile.layers,destination.layers))
                or profile.names != destination.names):
            raise ValueError("Connected profiles must have matching named bands and layers.")
        # Reject geometry from another plane before Connection registers any
        # band. Projected coordinates alone cannot define a 3D route obstacle.
        for obstacle in self.obstacles:
            if obstacle.project is not profile.project:
                raise ValueError("Route obstacles must belong to its project.")
            if obstacle.layer.workplane is not profile.layers[0].workplane:
                raise ValueError("Route obstacles must belong to the route's workplane.")
        destination = destination.reversed()  # destination outward normal opposes travel
        radius = evaluate(self.radius, "um")
        slope = evaluate(self.taper_slope, "")
        if slope <= 0 or evaluate(self.tolerance, "um") <= 0:
            raise ValueError("Taper slope and sampling tolerance must be positive.")
        if evaluate(self.clearance, "um") < 0 or evaluate(self.length_tolerance, "um") <= 0:
            raise ValueError("Clearance must be nonnegative and length tolerance positive.")
        straights = tuple(evaluate(v, "um") for v in (self.start_straight, self.end_straight))
        if min(straights) < 0:
            raise ValueError("Minimum straight lengths must be nonnegative.")
        a = [(evaluate(o, "um"), evaluate(w, "um")) for o, w in zip(profile.offsets, profile.widths)]
        b = [(evaluate(o, "um"), evaluate(w, "um")) for o, w in zip(destination.offsets, destination.widths)]
        difference = max(abs(o1+s*w1/2-o2-s*w2/2) for (o1,w1),(o2,w2) in zip(a,b) for s in (-1,1))
        taper = difference/slope if difference > 1e-10 else 0.0
        start = _shift(self.start.position, self.start.direction, taper)
        end = self.end.position
        if self.points is not None:
            if self.via:
                raise ValueError("Choose complete points or oriented via ports, not both.")
            coords = list(self.points.value)
            if len(coords) < 2:
                raise ValueError("Explicit route points require at least two endpoints.")
            if hypot(coords[0][0]-start[0], coords[0][1]-start[1]) > 1e-7 or hypot(coords[-1][0]-end[0], coords[-1][1]-end[1]) > 1e-7:
                raise ValueError("Explicit route points must start after the taper and end at the destination port.")
            path = RoutePath(coords, radius)
        else:
            sections = []
            positions = [(start, self.start.direction)]
            for port in self.via:
                if not isinstance(port, Port) or port.profile is not None:
                    raise ValueError("via entries must be oriented Ports without a profile.")
                port.validate()
                positions.append((port.position, port.direction))
            positions.append((end, tuple(-v for v in self.end.direction)))
            for index, ((p, u), (q, v)) in enumerate(zip(positions, positions[1:])):
                section = RoutePath.manhattan(p, q, u, tuple(-x for x in v), radius=radius,
                        start_straight=evaluate(self.start_straight, "um") if index == 0 else 0,
                        end_straight=evaluate(self.end_straight, "um") if index == len(positions)-2 else 0)
                sections.extend(section.points if not sections else section.points[1:])
            path = RoutePath(sections, radius)
        if sum(x*y for x,y in zip(path.start_direction, self.start.direction)) < 1-1e-8 or sum(x*y for x,y in zip(path.end_direction, self.end.direction)) > -1+1e-8:
            raise ValueError("Route tangents do not match the endpoint ports.")
        count_value = 0 if self.meander_count is None else evaluate(self.meander_count, "")
        if count_value < 0 or int(count_value) != count_value:
            raise ValueError("Meander count must be a nonnegative integer.")
        count = int(count_value)
        amplitude = evaluate(self.meander_amplitude, "um")
        offset = evaluate(self.meander_offset, "um")
        maximum_amplitude = (None if self.meander_max_amplitude is None else
                             evaluate(self.meander_max_amplitude, "um"))
        if maximum_amplitude is not None and maximum_amplitude <= 0:
            raise ValueError("meander_max_amplitude must be positive.")
        fitted = False
        if self.target_length is not None:
            target = evaluate(self.target_length, "um")-taper
            if self.meander_count is None:
                if target < path.length-evaluate(self.length_tolerance, "um"):
                    raise ValueError("Target length is shorter than the base route.")
                if abs(path.length-target) > evaluate(self.length_tolerance, "um"):
                    path, count, amplitude = self._automatic_meander(
                        path, target, offset, straights, b, maximum_amplitude)
                    fitted = True
            elif not count:
                if abs(path.length-target) > evaluate(self.length_tolerance, "um"):
                    raise ValueError("A different target length requires a positive meander_count, or omit it for automatic sizing.")
            else:
                # For fixed topology every additional unit of amplitude adds
                # 2*count units of straight path; rounded-corner corrections stay fixed.
                minimum = 2*radius+abs(offset)+1e-7
                trial = path.meander(count, minimum, segment=self.meander_segment, offset=offset)
                amplitude = minimum+(target-trial.length)/(2*count)
                if amplitude < minimum-1e-7:
                    raise ValueError("Target length is shorter than this meander can achieve.")
        if count and maximum_amplitude is not None and amplitude > maximum_amplitude+1e-8:
            raise ValueError("Required amplitude exceeds meander_max_amplitude.")
        if count and not fitted:
            path = path.meander(count, amplitude, segment=self.meander_segment, offset=offset)
        if self.target_length is not None and abs(path.length+taper-evaluate(self.target_length,"um")) > evaluate(self.length_tolerance,"um"):
            raise ValueError("Requested target length was not achieved.")
        # These constraints also apply to explicit paths and after meandering.
        # A new meander must not quietly consume a required straight launch.
        for piece, required in zip((path.pieces[0], path.pieces[-1]), straights):
            actual = piece.length if isinstance(piece, LinePiece) else 0
            if actual < required-1e-8:
                raise ValueError("Route does not satisfy its minimum straight lengths.")
        # Check both edges of each band, not just the widest centred track.
        for offset, width in b:
            path.offset(offset-width/2)
            path.offset(offset+width/2)
        self._resolved_meander_count = count
        self._resolved_meander_amplitude = amplitude if count else 0.0
        return path, taper, destination


class Connection:
    """A route request and one filled, selectable output feature per band.

    ``geometry`` maps profile-band names to registered features. The connection
    follows its ports and parameters when the project is rebuilt. ``length``
    and ``report()`` evaluate the current path without building either backend.
    """

    def __init__(self, start, end, **options):
        self.route = Route(start, end, **options)
        self.route.resolve()  # Fail before registering any geometry.
        self.project = start.profile.project
        self.name = self.route.name
        self.geometry = {}
        live = self.project.live
        self.project.live = False
        try:
            for index, band in enumerate(start.profile.names):
                self.geometry[band] = _RouteBand(self, index)
        finally:
            self.project.live = live
        if live:
            self.project.build()

    @property
    def length(self):
        """Current centreline length including its taper, in um."""
        path, taper, _ = self.route.resolve()
        return path.length+taper

    @property
    def features(self):
        """Registered output features in profile-band order."""
        return tuple(self.geometry.values())

    def report(self):
        """Return current geometric length, taper, bends and fitted meander data.

        Lengths, amplitudes and endpoint coordinates are in um. These values
        describe the resolved centreline; they are not an electrical model or
        a substitute for the geometry-build obstacle/clearance checks.
        """
        path, taper, _ = self.route.resolve()
        return {"name": self.name, "length_um": path.length+taper,
                "taper_length_um": taper, "bends": sum(isinstance(p,ArcPiece) for p in path.pieces),
                "meander_count": self.route._resolved_meander_count,
                "meander_amplitude_um": self.route._resolved_meander_amplitude,
                "start": self.route.start.position, "end": self.route.end.position}


def connect(start, end, **options):
    """Connect two outward-facing ports; see Route for the routing options."""
    return Connection(start, end, **options)


class _RouteBand(GeometryObject):
    """One terminal band; internal native features are owned by this object."""

    tag_prefix = "route"
    _area_output = True

    def __init__(self, connection, index):
        self.connection, self.index = connection, index
        super().__init__(connection.project, connection.route.start.profile.layers[index])
        self.project.add(self)

    def validate(self):
        self.connection.route.resolve()
        self._check_obstacles()

    def parameter_values(self):
        return self.connection.route.parameter_values()

    def _shape(self):
        path, taper, profile = self.connection.route.resolve()
        offset = evaluate(profile.offsets[self.index], "um")
        width = evaluate(profile.widths[self.index], "um")
        return path.offset(offset), width, taper, profile

    def _taper_points(self, taper, profile):
        source = self.connection.route.start
        direction = source.direction
        normal = (-direction[1], direction[0])
        o0, w0 = (evaluate(values[self.index], "um") for values in (source.profile.offsets, source.profile.widths))
        o1, w1 = (evaluate(values[self.index], "um") for values in (profile.offsets, profile.widths))
        start, end = source.position, _shift(source.position, direction, taper)
        return [_shift(start, normal, o0-w0/2), _shift(end, normal, o1-w1/2),
                _shift(end, normal, o1+w1/2), _shift(start, normal, o0+w0/2)]

    def path(self):
        """Finite-width KLayout DPath, useful for inspection and editing."""
        import klayout.db as kdb
        path, width, _, _ = self._shape()
        tolerance = evaluate(self.connection.route.tolerance,"um")
        points = path.sample(tolerance/2)
        # A DPath cap is perpendicular to its first/last chord. If a route
        # begins directly on an arc, sagitta accuracy alone leaves the cap
        # tilted. Short endpoint chords bound that lateral cap error too.
        for first in (True,False):
            piece = path.pieces[0 if first else -1]
            if isinstance(piece,ArcPiece):
                delta = min(abs(piece.sweep)/4,tolerance/width)
                sign = 1 if piece.sweep > 0 else -1
                angle = (piece.start_angle+sign*delta if first else
                         piece.start_angle+piece.sweep-sign*delta)
                point = (piece.center[0]+piece.radius*cos(angle),
                         piece.center[1]+piece.radius*sin(angle))
                index = 1 if first else -1
                endpoint = points[0 if first else -1]
                neighbor = points[1 if first else -2]
                if hypot(point[0]-endpoint[0],point[1]-endpoint[1]) < hypot(neighbor[0]-endpoint[0],neighbor[1]-endpoint[1]):
                    points.insert(index,point)
        return kdb.DPath([kdb.DPoint(*p) for p in points], width)

    def to_klayout(self):
        import klayout.db as kdb
        _, _, taper, profile = self._shape()
        polygon = self.path().polygon()
        if not taper:
            return polygon
        other = kdb.DPolygon([kdb.DPoint(*p) for p in self._taper_points(taper, profile)])
        region = self.project._operation_region((polygon, other), self, self)
        region.merge()
        polys = tuple(p.to_dtype(self.project.dbu) for p in region.each_merged())
        return polys[0] if len(polys) == 1 else polys

    def _check_obstacles(self):
        import klayout.db as kdb
        from .booleans import _is_filled
        route = self.connection.route
        if not route.obstacles:
            return
        margin = ceil(evaluate(route.clearance,"um")/self.project.dbu)
        area = self.project._operation_region(self.to_klayout(), self, self)
        if margin:
            area = area.sized(margin)
        for obstacle in route.obstacles:
            if obstacle.project is not self.project:
                raise ValueError("Route obstacles must belong to its project.")
            if not _is_filled(obstacle):
                raise TypeError("Route obstacles require filled geometry.")
            region = self.project._operation_region(obstacle.to_klayout(), self, obstacle,
                                                     allow_empty=True)
            if not (area & region).is_empty():
                raise ValueError(f"Route {route.name!r} band {self.index} intersects obstacle {obstacle.tag!r} or its clearance.")

    def reset_comsol(self, geometry):
        """Remove only this band's generated features before rebuilding topology."""
        tags = list(geometry.feature().tags())
        owned = [str(tag) for tag in tags if str(tag) == self.tag or str(tag).startswith(self.tag+"_")]
        for tag in reversed(owned):
            geometry.feature().remove(tag)
        return bool(owned)

    def to_comsol(self, geometry, tag):
        path, _, taper, profile = self._shape()
        curve_tags = []
        for index, piece in enumerate(path.pieces):
            curve_tag = f"{tag}_c{index}"
            curve_tags.append(curve_tag)
            if isinstance(piece, LinePiece):
                feature = geometry.create(curve_tag, "LineSegment")
                feature.set("specify1", "coord")
                feature.set("specify2", "coord")
                feature.set("coord1", [str(v) for v in piece.start])
                feature.set("coord2", [str(v) for v in piece.end])
            else:
                feature = geometry.create(curve_tag, "CircularArc")
                feature.set("specify", "center")
                feature.set("center", [str(v) for v in piece.center])
                feature.set("r", str(piece.radius))
                feature.set("angle1", str(degrees(piece.start_angle)))
                feature.set("angle2", str(degrees(piece.start_angle+piece.sweep)))
                feature.set("clockwise", "on" if piece.sweep < 0 else "off")
        spine_tag = curve_tags[0]
        if len(curve_tags) > 1:
            spine_tag = tag+"_spine"
            feature = geometry.create(spine_tag,"Union")
            feature.selection("input").set(curve_tags)
            feature.set("intbnd","off")
        geometry.run(spine_tag)
        thick_tag = tag+"_thick" if taper else tag
        thick = geometry.create(thick_tag,"Thicken2D")
        thick.set("offset","symmetric")
        thick.set("totalthick", comsol_expression(profile.widths[self.index],"um"))
        thick.set("ends","straight")
        thick.set("convexcorner","extend")
        thick.set("keep","off")
        selection = thick.selection("input")
        selection.init(1)
        for name in geometry.feature(spine_tag).objectNames():
            selection.all(str(name))
        if taper:
            taper_tag = tag+"_taper"
            feature = geometry.create(taper_tag,"Polygon")
            feature.set("type","solid")
            feature.set("source","vectors")
            points = self._taper_points(taper,profile)
            feature.set("x",[str(p[0]) for p in points])
            feature.set("y",[str(p[1]) for p in points])
            feature = geometry.create(tag,"Union")
            feature.selection("input").set([thick_tag,taper_tag])
            feature.set("intbnd","off")
        geometry.feature(tag).label(f"{self.connection.name}: {profile.names[self.index]} ({tag})")
        geometry.run(tag)
