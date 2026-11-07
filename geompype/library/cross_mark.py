"""A centred cross for optical or electron-beam alignment."""

from ..components import _length
from ..parameters import evaluate
from ..primitives import Polygon


class _CrossMark(Polygon):
    """A Polygon retaining the dimensional constraints of a cross."""

    def __init__(self, project, *, layer, size, width, selections):
        self._size = _length(size)
        self._width = _length(width)
        s, w = self._size / 2, self._width / 2
        points = [(-w, -s), (w, -s), (w, -w), (s, -w), (s, w), (w, w),
                  (w, s), (-w, s), (-w, w), (-s, w), (-s, -w), (-w, -w)]
        super().__init__(project, layer=layer, vertices=points, selections=selections)

    def validate(self):
        size, width = evaluate(self._size, 'um'), evaluate(self._width, 'um')
        if not 0 < width < size:
            raise ValueError('cross_mark requires 0 < width < size.')
        super().validate()


def cross_mark(project, *, layer, size=100, width=10, selections=()):
    """Create a filled plus-shaped Polygon centred at local (0, 0).

    ``size`` is the full horizontal and vertical tip-to-tip span; ``width``
    is the width of both arms. Numeric dimensions are in um and must satisfy
    ``0 < width < size``. Parameter dimensions remain live after construction;
    call ``project.build()`` after editing their values. Ordinary geometry
    transforms place or rotate the mark, including a 45-degree X orientation.
    """
    return _CrossMark(project, layer=layer, size=size, width=width,
                      selections=selections)
