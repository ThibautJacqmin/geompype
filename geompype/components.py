"""Generic named geometry groups, placement and construction batching."""

from contextlib import contextmanager
from math import atan2, cos, degrees, hypot, radians, sin
from numbers import Real

from .parameters import evaluate, maximum
from .vertices import Vertices, coordinate_pair


def _length(value):
    """Give bare numbers the same length unit as Parameter-based dimensions."""
    return Vertices((value, 0)).array[0][0]


def _maximum_length(a, b):
    unit = _length(1)
    return maximum(a/unit, b/unit)*unit


def _positive(**values):
    for name, value in values.items():
        if evaluate(value, "um") <= 0:
            raise ValueError(f"{name} must be a positive length.")


def _nonnegative(**values):
    for name, value in values.items():
        if evaluate(value, "um") < 0:
            raise ValueError(f"{name} must be a nonnegative length.")


def _direction(orientation):
    values = tuple(orientation)
    if len(values) != 2 or any(isinstance(v, bool) or not isinstance(v, Real) for v in values):
        raise ValueError("Component orientation requires two fixed real numbers.")
    x, y = (evaluate(value, "") for value in values)
    length = hypot(x, y)
    if length == 0:
        raise ValueError("Component orientation cannot be zero.")
    return x / length, y / length


@contextmanager
def _assembly(project):
    """Validate parameters and build once for a complete component assembly.

    Geometry/ownership validation still happens when each feature is added.
    Parameter-name conflicts are checked at the end of the outermost assembly,
    avoiding a complete traversal of the growing graph for every feature.
    """
    live = project.live
    deferred = getattr(project, '_defer_parameter_checks', False)
    project._defer_parameter_checks = True
    project.live = False
    try:
        yield
    except BaseException:
        raise
    else:
        if not deferred:
            project._parameters_for(project.objects)
        if live:
            project.build()
    finally:
        project.live = live
        project._defer_parameter_checks = deferred


class Component:
    """Named output features and ports belonging to one project.

    ``move`` and ``rotate`` update this component in place. They retain the same
    Port instances, so previously declared connections follow the moved ports
    on their next build. Move/Rotate features consume this component's current
    output features. A component whose geometry was consumed by another Boolean
    must be placed before that Boolean.

    Rotation angles are fixed numbers for now. Dimensions and translations may
    be Parameters; they retain their references and COMSOL expressions.
    """

    def __init__(self, project, *, geometry=None, ports=None, name="component"):
        self.project = project
        self.name = str(name)
        self.geometry = dict(geometry or {})
        self.ports = dict(ports or {})
        if any(obj.project is not project for obj in self.geometry.values()):
            raise ValueError("Component geometry must belong to its project.")

    @property
    def features(self):
        return tuple(dict.fromkeys(self.geometry.values()))

    def _check_available(self):
        available = set(self.project._final_objects(self.project.objects))
        if any(obj not in available for obj in self.features):
            raise ValueError("Place a component before consuming its geometry in another operation.")

    def move(self, delta):
        """Translate geometry and ports together; delta may retain parameters."""
        self._check_available()
        delta = Vertices(delta)
        coordinate_pair(delta)
        moved_ports = {name: Vertices(port.pos) + delta for name, port in self.ports.items()}
        with _assembly(self.project):
            replacements = {obj: obj.move(delta=delta) for obj in self.features}
            self.geometry = {name: replacements[obj] for name, obj in self.geometry.items()}
            for name, port in self.ports.items():
                port.pos = moved_ports[name]
        return self

    def rotate(self, angle, *, origin=(0, 0)):
        """Rotate geometry and ports anticlockwise about origin, in degrees."""
        self._check_available()
        if isinstance(angle, bool) or not isinstance(angle, Real):
            raise ValueError("Component.rotate currently requires a fixed numeric angle.")
        angle = evaluate(angle, "deg")
        c, s = cos(radians(angle)), sin(radians(angle))
        origin = Vertices(origin)
        ox, oy = coordinate_pair(origin)
        moved_ports = {}
        for name, port in self.ports.items():
            x, y = coordinate_pair(Vertices(port.pos) - origin)
            dx, dy = port.orientation
            moved_ports[name] = (Vertices((ox + c*x - s*y, oy + s*x + c*y)),
                                 (c*dx - s*dy, s*dx + c*dy))
        with _assembly(self.project):
            replacements = {obj: obj.rotate(angle=angle, origin=origin) for obj in self.features}
            self.geometry = {name: replacements[obj] for name, obj in self.geometry.items()}
            for name, port in self.ports.items():
                port.pos, port.orientation = moved_ports[name]
        return self

    def place(self, *, position=(0, 0), orientation=(1, 0)):
        """Apply a rotation around local zero, then a translation.

        This is a relative operation: calling it twice applies two placements.
        Initial component constructors call it once on their local geometry.
        """
        dx, dy = _direction(orientation)
        coordinate_pair(Vertices(position))
        with _assembly(self.project):
            angle = degrees(atan2(dy, dx))
            if angle:
                self.rotate(angle)
            # Keep parameter-valued zero translations live as well.
            if any(not isinstance(v, Real) or v != 0 for v in coordinate_pair(position)):
                self.move(position)
        return self

