"""Nominal 100 mm wafer outline with configurable orientation flats."""

from ..primitives import Polygon
from ._wafer_outline import wafer_vertices


def four_inch_wafer(project, *, layer, flats=1, flat_length=32500,
                    secondary_flat_length=18000, secondary_flat_angle=90,
                    tolerance=1.0, selections=()):
    """Create a filled 100 mm wafer polygon centered at local zero.

    The 4-inch designation uses the nominal 100 mm wafer diameter. The primary
    flat at +y has default length 32.5 mm. With flats=2, the secondary flat is
    18 mm and its outward normal defaults to -x. secondary_flat_angle rotates
    that normal anticlockwise from +y in degrees. No crystal/doping convention
    is inferred from the selected angle.
    Both flats must remain visible; a cut hidden by the other is rejected.

    Lengths and tolerance are fixed numbers in um chosen at construction.
    tolerance=1 bounds circular chord error to 1 um before the GDS grid.
    With flats=1, flat_length=0 produces a full disk. Use the returned Polygon's
    scale, move and rotate methods for parameterized size and placement.
    """
    vertices = wafer_vertices(100000, flats=flats, flat_length=flat_length,
                              secondary_flat_length=secondary_flat_length,
                              secondary_flat_angle=secondary_flat_angle,
                              tolerance=tolerance)
    return Polygon(project, layer=layer, vertices=vertices, selections=selections)
