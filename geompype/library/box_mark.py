"""A hollow square frame for optical alignment and overlay comparisons."""

from ..booleans import Difference
from ..components import _assembly, _length
from ..geometry import GeometryObject
from ..parameters import evaluate
from ..primitives import Square


class _FrameOuter(Square):
    """Validate frame wall thickness whenever its outer Square is rebuilt."""

    def __init__(self, project, *, layer, size, width):
        self._width = width
        super().__init__(project, layer=layer, side=size)

    def validate(self):
        size, width = evaluate(self.side, 'um'), evaluate(self._width, 'um')
        if not 0 < 2 * width < size:
            raise ValueError('box_mark requires 0 < 2*width < size.')
        super().validate()


def box_mark(project, *, layer, size=100, width=10, selections=()):
    """Create a centred square frame with outer side ``size`` and wall ``width``.

    The result is a Difference of two native Squares, so its centre is a real
    hole in both backends. Numeric dimensions are in um; ``0 < 2*width < size``
    keeps a positive opening. Parameters remain live after construction.
    Build differently sized frames on two layers for a box-in-box overlay mark.
    """
    size, width = _length(size), _length(width)
    selections = tuple(selections)
    # Check ownership before registering either operand of the Difference.
    GeometryObject(project, layer, selections=selections)
    with _assembly(project):
        outer = _FrameOuter(project, layer=layer, size=size, width=width)
        inner = Square(project, layer=layer, side=size - 2 * width)
        result = Difference(outer, inner, selections=selections)
    return result
