"""Nominal 50.8 mm wafer outline with configurable orientation flats."""

from ..primitives import Polygon
from ._wafer_outline import wafer_vertices


def two_inch_wafer(project, *, layer, flats=1, flat_length=15880,
                    secondary_flat_length=8000, secondary_flat_angle=90,
                    tolerance=1.0, selections=()):
    """Create a filled 50.8 mm wafer polygon centered at local zero.

    The 2-inch designation uses the nominal 50.8 mm wafer diameter. The primary
    flat at +y has default length 15.88 mm. With flats=2, the secondary flat is
    8 mm and its outward normal defaults to -x. secondary_flat_angle rotates
    that normal anticlockwise from +y in degrees. No crystal/doping convention
    is inferred from the selected angle.
    Both flats must remain visible; a cut hidden by the other is rejected.

    Lengths and tolerance are fixed numbers in um chosen at construction.
    tolerance=1 bounds circular chord error to 1 um before the GDS grid.
    With flats=1, flat_length=0 produces a full disk. Use the returned Polygon's
    scale, move and rotate methods for parameterized size and placement.
    """
    vertices = wafer_vertices(50800, flats=flats, flat_length=flat_length,
                              secondary_flat_length=secondary_flat_length,
                              secondary_flat_angle=secondary_flat_angle,
                              tolerance=tolerance)
    return Polygon(project, layer=layer, vertices=vertices, selections=selections)
