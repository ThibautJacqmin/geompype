"""An X-shaped alignment mark with four diamond satellites."""

from ..booleans import Union
from ..components import _assembly
from ..primitives import Polygon
from ._data import polygons


def x_diamond_mark(project, *, layer, selections=()):
    """Create an X and four diamond satellites as one Union feature.

    Its five polygons form an X and four diamond satellites, centred on local
    zero, spanning 175.092 um in x and y, with sampled rounded corners.
    Inputs are consumed, so the mark exports once.
    Layer flags and its workplane apply as for any other geometry.

    Example: ``x_diamond_mark(project, layer=marks).move(delta=(1000, 2000))``.
    """
    with _assembly(project):
        pieces = [Polygon(project, layer=layer, vertices=vertices)
                  for vertices in polygons('x_diamond_mark')]
        mark = Union(pieces, selections=selections)
    return mark
