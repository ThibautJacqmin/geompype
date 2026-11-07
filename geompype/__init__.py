"""A small Python geometry interface for COMSOL and KLayout."""

from .geometry import GeometryObject
from .layer import Layer
from .workplane import WorkPlane
from .project import Project
from .selection import Selection
from .parameters import Parameter, DependentParameter, maximum, round_nearest
from .vertices import Vertices
from .primitives import (Square, Rectangle, Circle, Ellipse, Polygon, Point,
                         LineSegment, CircularArc, QuadraticBezier, CubicBezier,
                         InterpolationCurve, ParametricCurve)
from .transforms import Array, Copy, Mirror, Move, Rotate, Scale
from .booleans import Union, Difference, Intersection
from .operations import Fillet, Chamfer, Offset, Thicken2D
from .routing import PortProfile, Port, Route, Connection, connect
from .configuration import ConfigNode, load_config
from .library import (x_diamond_mark, two_inch_wafer, three_inch_wafer, four_inch_wafer,
                      cross_mark, l_mark, box_mark, vernier_mark)

__all__ = ["Project", "Layer", "WorkPlane", "GeometryObject", "Selection", "Fillet", "Chamfer", "Offset", "Thicken2D",
           "PortProfile", "Port", "Route", "Connection", "connect",
           "ConfigNode", "load_config", "x_diamond_mark", "two_inch_wafer",
           "three_inch_wafer", "four_inch_wafer", "cross_mark", "l_mark", "box_mark", "vernier_mark",
           "Parameter", "DependentParameter", "Vertices", "Square", "Rectangle",
           "Circle", "Ellipse", "Polygon", "Array", "Copy", "Mirror", "Move", "Rotate", "Scale",
           "Union", "Difference", "Intersection", "maximum", "round_nearest", "Point", "LineSegment", "CircularArc",
           "QuadraticBezier", "CubicBezier", "InterpolationCurve", "ParametricCurve"]
