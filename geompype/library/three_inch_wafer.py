"""Nominal 76.2 mm wafer outline with configurable orientation flats."""

from ..primitives import Polygon
from ._wafer_outline import wafer_vertices


def three_inch_wafer(project, *, layer, flats=1, flat_length=22220,
                     secondary_flat_length=11180, secondary_flat_angle=90,
                     tolerance=1.0, selections=()):
    """Create a filled 76.2 mm wafer polygon centered at local zero.

    The primary flat lies at +y. Its default length is 22.22 mm; with flats=2,
    the second flat is 11.18 mm and its outward normal defaults to -x.
    secondary_flat_angle is measured anticlockwise from +y, in degrees.
    These are nominal outline dimensions, not a crystal/doping convention.
    Both flats must remain visible; a cut hidden by the other is rejected.

    Lengths and tolerance are fixed numbers in um chosen at construction.
    tolerance=1 bounds circular chord error to 1 um before the GDS grid.
    With flats=1, flat_length=0 produces a full disk. Use the returned Polygon's
    scale, move and rotate methods for parameterized size and placement.
    """
    vertices = wafer_vertices(76200, flats=flats, flat_length=flat_length,
                              secondary_flat_length=secondary_flat_length,
                              secondary_flat_angle=secondary_flat_angle,
                              tolerance=tolerance)
    return Polygon(project, layer=layer, vertices=vertices, selections=selections)
