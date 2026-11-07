"""A right-angle alignment mark with its outside corner at the origin."""

from ..components import _length
from ..parameters import evaluate
from ..primitives import Polygon


class _LMark(Polygon):
    """A Polygon retaining the dimensional constraints of an L mark."""

    def __init__(self, project, *, layer, size, width, selections):
        self._size = _length(size)
        self._width = _length(width)
        s, w = self._size, self._width
        points = [(0, 0), (s, 0), (s, w), (w, w), (w, s), (0, s)]
        super().__init__(project, layer=layer, vertices=points, selections=selections)

    def validate(self):
        size, width = evaluate(self._size, 'um'), evaluate(self._width, 'um')
        if not 0 < width < size:
            raise ValueError('l_mark requires 0 < width < size.')
        super().validate()


def l_mark(project, *, layer, size=100, width=10, selections=()):
    """Create a filled L-shaped Polygon extending along positive x and y.

    The outside corner is (0, 0), and its bounds are (0, 0) to (size, size).
    Both arms have width ``width``. Numeric dimensions are in um and must
    satisfy ``0 < width < size``. Parameters remain live; rebuild after edits.
    Rotate or mirror the result to create the other corner orientations.
    """
    return _LMark(project, layer=layer, size=size, width=width,
                  selections=selections)
