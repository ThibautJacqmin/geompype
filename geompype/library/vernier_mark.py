"""Two-layer linear vernier for measuring relative alignment along one axis."""

from numbers import Integral

from ..booleans import Union
from ..components import Component, _assembly, _length
from ..layer import Layer
from ..parameters import evaluate
from ..primitives import Rectangle
from ..selection import Selection


def _check_dimensions(pitch, resolution, width, length, gap):
    values = {name: evaluate(value, 'um') for name, value in
              (('pitch', pitch), ('resolution', resolution), ('width', width),
               ('length', length), ('gap', gap))}
    if any(value <= 0 for value in values.values()):
        raise ValueError('Vernier dimensions must be positive lengths.')
    if values['resolution'] >= values['pitch']:
        raise ValueError('Vernier resolution must be smaller than pitch.')
    if values['width'] >= values['pitch'] - values['resolution']:
        raise ValueError('Vernier width must be smaller than pitch minus resolution.')


class _VernierTick(Rectangle):
    """A native rectangle that also validates the complete vernier dimensions."""

    def __init__(self, project, *, layer, dimensions, position):
        self._dimensions = dimensions
        _, _, width, length, _ = dimensions
        super().__init__(project, layer=layer, size=(width, length), position=position)

    def validate(self):
        _check_dimensions(*self._dimensions)
        super().validate()

    def parameter_values(self):
        return (*self._dimensions, *super().parameter_values())


def vernier_mark(project, *, reference_layer, moving_layer, pitch=10,
                 resolution=1, ticks=11, width=2, length=20, gap=4,
                 selections=()):
    """Create two rows of vernier ticks on separate layers of one workplane.

    All lengths are in micrometres and may be live Parameters. ``ticks`` is a
    fixed odd integer of at least three. The reference row has pitch ``pitch``;
    the moving row has pitch ``pitch-resolution``. Each tick is ``width`` wide
    and ``length`` tall. The rows face each other across a positive ``gap``.

    At nominal alignment, the middle ticks share x=0. Tick indices run from
    ``-(ticks-1)/2`` to ``+(ticks-1)/2`` from left to right. Coincidence of the
    same-index ticks at index i indicates an x displacement of the moving layer
    by ``i*resolution``. The indexed readout range is therefore
    ``+/-((ticks-1)/2)*resolution``. These are geometric graduations, not a
    guarantee of the alignment instrument's measurement accuracy.

    Returns a Component with two Union outputs in ``geometry['reference']``
    and ``geometry['moving']``. The reference row is below y=0 and the moving
    row above it. Use ``.move((x, y))`` to place the complete pair or
    ``.rotate(90)`` for a y-direction vernier. Supplied selections include both
    outputs. Each layer retains its independent COMSOL/GDS settings.
    """
    if isinstance(ticks, bool) or not isinstance(ticks, Integral) or ticks < 3 or ticks % 2 != 1:
        raise ValueError('Vernier ticks must be a fixed odd integer of at least three.')
    for layer in (reference_layer, moving_layer):
        if not isinstance(layer, Layer) or project.layers.get(layer.name) is not layer:
            raise ValueError('Vernier layers must belong to this project.')
    if reference_layer is moving_layer:
        raise ValueError('Vernier reference and moving layers must be distinct.')
    if reference_layer.workplane is not moving_layer.workplane:
        raise ValueError('Vernier layers must belong to the same workplane.')
    selections = tuple(selections)
    for selection in selections:
        if (not isinstance(selection, Selection) or selection.project is not project
                or project.selections.get(selection.name) is not selection):
            raise ValueError('Vernier selections must belong to this project.')
    dimensions = tuple(_length(value) for value in (pitch, resolution, width, length, gap))
    _check_dimensions(*dimensions)
    pitch, resolution, width, length, gap = dimensions
    half_count = int(ticks) // 2
    with _assembly(project):
        rows = {}
        for name, layer, spacing, sign in (
                ('reference', reference_layer, pitch, -1),
                ('moving', moving_layer, pitch-resolution, 1)):
            pieces = [_VernierTick(project, layer=layer, dimensions=dimensions,
                                  position=(index*spacing, sign*(gap+length)/2))
                      for index in range(-half_count, half_count+1)]
            rows[name] = Union(pieces, interior_boundaries=False, selections=selections)
        result = Component(project, geometry=rows, name='vernier_mark')
    return result
