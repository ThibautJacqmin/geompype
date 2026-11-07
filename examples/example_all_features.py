"""Live gallery of every implemented primitive, with parameters and selections.

Top row: Square, rotated Rectangle, Circle, Ellipse, Polygon.
Middle row: LineSegment, QuadraticBezier, CubicBezier, CircularArc, InterpolationCurve.
Bottom row: ParametricCurve, a rotated arc copy, and two COMSOL point anchors.
"""

# %% Imports
from math import cos, pi, sin

from geompype import (
    Project, Parameter, DependentParameter, Vertices, maximum, round_nearest,
    Square, Rectangle, Circle, Ellipse, Polygon, Point, LineSegment,
    QuadraticBezier, CubicBezier, CircularArc, InterpolationCurve, ParametricCurve,
    Rotate,
)

# %% Parameters — bare lengths are um; gap deliberately uses nm
width = Parameter(20, "width", unit="um")
height = Parameter(10, "height", unit="um")
gap = Parameter(5000, "gap", unit="nm")
angle = Parameter(30, "angle", unit="deg")
radius = DependentParameter(width / 2, "radius")
pitch = DependentParameter(2*width + 2*gap, "pitch")
rounded_ratio = DependentParameter(round_nearest(maximum(width / gap, 1)), "rounded_ratio")

# %% Project, layers and FEM selections
# live=True builds each object as it is added. Parameter edits still need build().
project = Project(live=True, output="output/example_all_features")
metal = project.add_layer("metal", gds_layer=1, comsol=True, gds=True)
dielectric = project.add_layer("dielectric", gds_layer=2, comsol=True, gds=True)
construction = project.add_layer("construction", gds_layer=3, comsol=True, gds=True)
surfaces = project.add_selection("all_surfaces", entity="boundary")
curve_edges = project.add_selection("all_curves", entity="edge")
anchors = project.add_selection("anchors", entity="point")
rotated_surfaces = project.add_selection("rotated_surfaces", entity="boundary")
rotated_curves = project.add_selection("rotated_curves", entity="edge")
# Explicit registration also exports design metadata unused by a geometric feature.
project.add_parameter(rounded_ratio)

# Open the viewers before drawing, so the geometry appears progressively.
# COMSOL Desktop: import example_all_features from the connected server once.
project.show()

# %% Shared position tables — coefficients times pitch retain live references
shape_centres = Vertices([[-2, 2], [-1, 2], [0, 2], [1, 2], [2, 2]], pitch)
curve_centres = Vertices([[-2, 0], [-1, 0], [0, 0], [1, 0], [2, 0], [-1, -1]], pitch)

# %% All five filled primitives; one FEM group spans two drawing layers
square = Square(project, layer=metal, side=width,
                position=shape_centres[0], selections=[surfaces])
rectangle = Rectangle(project, layer=metal, size=(width, height),
                      position=shape_centres[1], selections=[surfaces])
# keep=False replaces the original rectangle. Its surface selection propagates.
rotated_rectangle = Rotate(rectangle, angle=angle, origin=shape_centres[1],
                           keep=False, selections=[rotated_surfaces])
circle = Circle(project, layer=dielectric, radius=radius,
                position=shape_centres[2], selections=[surfaces])
ellipse = Ellipse(project, layer=dielectric, semiaxes=(radius, height/2),
                  position=shape_centres[3], angle=angle, selections=[surfaces])
outline = Vertices([[-0.5, -0.5], [0.5, -0.5], [0.5, 0], [0, 0.5], [-0.5, 0]], width)
outline = outline + shape_centres[4]
polygon = Polygon(project, layer=metal, vertices=outline, selections=[surfaces])

# %% Native line, rational quadratic Bezier, cubic Bezier and circular arc
line_points = Vertices([[-0.5, 0], [0.5, 0]], width) + curve_centres[0]
line = LineSegment(project, layer=construction, p1=line_points[0], p2=line_points[1],
                   selections=[curve_edges])
quadratic_points = Vertices([[-0.5, -0.25], [0, 0.75], [0.5, -0.25]], width) + curve_centres[1]
quadratic = QuadraticBezier(project, layer=construction,
                            p0=quadratic_points[0], p1=quadratic_points[1],
                            p2=quadratic_points[2], selections=[curve_edges])
cubic_points = Vertices([[-0.5, -0.25], [-0.25, 0.75], [0.25, -0.75], [0.5, 0.25]], width)
cubic_points = cubic_points + curve_centres[2]
cubic = CubicBezier(project, layer=construction, p0=cubic_points[0], p1=cubic_points[1],
                    p2=cubic_points[2], p3=cubic_points[3], selections=[curve_edges])
arc = CircularArc(project, layer=construction, radius=radius, center=curve_centres[3],
                  start_angle=0, end_angle=120, selections=[curve_edges])

# %% Genuine native interpolation, with an explicitly matching KLayout sampler
# Collinear points give a known straight locus in both backends. For a curved
# spline, the supplied Python sampler must match COMSOL's interpolation curve.
interpolation_points = Vertices([[-0.5, -0.2], [0, 0], [0.5, 0.2]], width) + curve_centres[4]
interpolation = InterpolationCurve(
    project, layer=construction, points=interpolation_points,
    sampler=lambda s: interpolation_points[0] + (interpolation_points[-1] - interpolation_points[0])*s,
    selections=[curve_edges],
)

# %% Parametric circle: native coordinate formulas and matching Python evaluation
parametric = ParametricCurve(
    project, layer=construction,
    coord=("-pitch+radius*cos(s)", "-pitch+radius*sin(s)"),
    parmin=0, parmax=2*pi, parameters=(pitch, radius),
    sampler=lambda s: curve_centres[5] + Vertices((radius*cos(s), radius*sin(s))),
    selections=[curve_edges],
)

# %% Keep an original curve and its rotated copy; the result stays a curve
arc_rotation_origin = curve_centres[3] + Vertices((0, -pitch/2))
rotated_arc = arc.rotate(angle=180, origin=arc_rotation_origin, keep=True,
                         selections=[rotated_curves])

# %% Point coordinates and their rotated copy — visible in COMSOL, no GDS markers
anchor_position = Vertices((2*pitch, -pitch))
point = Point(project, layer=construction, position=anchor_position, selections=[anchors])
rotated_point = point.rotate(angle=angle, origin=anchor_position + Vertices((0, -width)),
                             keep=True)

# %% Final build and viewers
project.build()
project.show()

# In the interactive console, try these lines and then rebuild:
# width.value = 24
# height.value = 12
# gap.value = 6000                 # nm
# angle.value = 45                 # degrees
# project.build()
#
# Editing a supplied Vertices also updates the corresponding object:
# outline[3] = outline[3] + (0, 5)  # translate this vertex upward by 5 um
# project.build()
#
# COMSOL: inspect all_surfaces, all_curves, anchors, rotated_surfaces and
# rotated_curves under Component 1 > Definitions > Selections.
# Points/curves are construction building blocks; see example_routing.py for finite-width routes.
