"""Planar drawings placed in a shared three-dimensional COMSOL geometry."""

import re

from .parameters import comsol_expression, evaluate


class WorkPlane:
    """An XY-parallel drawing with its own local coordinates and GDS file.

    Create through Project.add_workplane(). ``position=(x, y, z)`` places the
    local origin in COMSOL; ``angle`` rotates its local axes about global Z.
    Bare lengths use um and angles use degrees. Parameters stay symbolic in
    COMSOL. Placement does not transform the drawing's fabrication coordinates.

    Change position, angle or their Parameters, then call project.build().
    ``native`` exposes the Java WorkPlane after a native build; ``layout``
    exposes the KLayout layout after GDS export. Neither backend is connected
    merely by declaring a workplane.
    """

    def __init__(self, project, name, tag, *, position=(0, 0, 0), angle=0):
        if not isinstance(name, str) or re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name) is None:
            raise ValueError('A workplane name must start with a letter and contain only letters, digits or underscores.')
        self.project, self.name, self.tag = project, name, tag
        self.position, self.angle = position, angle
        self.native = None
        self.layout = None
        self.validate()

    @property
    def gds_path(self):
        """The default drawing keeps Project.gds_path; others append their name."""
        if self is self.project.default_workplane:
            return self.project.gds_path
        output = self.project.output
        return output.with_name(f'{output.name}_{self.name}.gds')

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        if isinstance(value, (str, bytes, dict, set)):
            raise ValueError('WorkPlane.position requires three ordered coordinates (x, y, z).')
        try:
            coordinates = tuple(value)
        except TypeError as error:
            raise ValueError('WorkPlane.position requires three coordinates (x, y, z).') from error
        if len(coordinates) != 3:
            raise ValueError('WorkPlane.position requires three coordinates (x, y, z).')
        for coordinate in coordinates:
            evaluate(coordinate, 'um')
        self._position = coordinates

    def parameter_values(self):
        return (*self.position, self.angle)

    def validate(self):
        for value in self.position:
            evaluate(value, 'um')
        evaluate(self.angle, 'deg')

    def to_comsol(self, geometry):
        """Create/update the documented Quick XY placement and local geometry."""
        self.validate()
        if self.tag not in list(geometry.feature().tags()):
            geometry.create(self.tag, 'WorkPlane')
        plane = geometry.feature(self.tag)
        plane.label(self.name)
        plane.set('unite', True)
        plane.set('selplaneshow', 'on')
        plane.set('planetype', 'quick')
        plane.set('quickplane', 'xy')
        plane.set('quickoffsettype', 'distance')
        plane.set('quickorigin', 'global')
        plane.set('quickaxis', 'natural')
        x, y, z = self.position
        plane.set('quickz', comsol_expression(z, 'um'))
        plane.set('displ', [comsol_expression(x, 'um'), comsol_expression(y, 'um')])
        plane.set('rot', comsol_expression(self.angle, 'deg'))
        self.native = plane
        return plane
