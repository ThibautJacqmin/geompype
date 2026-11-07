"""Native planar curves in COMSOL and zero-width DPath centrelines in KLayout."""

# %% Imports
from math import cos, pi, sin

from geompype import Parameter, Project, Vertices
from geompype.primitives import (
    CircularArc, CubicBezier, InterpolationCurve, LineSegment,
    ParametricCurve, Point, QuadraticBezier,
)

# %% Parameters — lengths in um, angles in degrees
pitch = Parameter(20, "curve_pitch", unit="um")
radius = Parameter(10, "curve_radius", unit="um")

# %% Project — set comsol=False on the layer to work offline
project = Project(output="output/example_curves")
curves = project.add_layer("curves", comsol=True, gds=True)
edges = project.add_selection("curve_edges", entity="edge")

# %% Point and analytic curves
# Point creates a native COMSOL point and a KLayout DPoint, with no GDS marker.
point = Point(project, layer=curves, position=(0, -25))
line = LineSegment(project, layer=curves, p1=(-60, 0), p2=(-30, 0), selections=[edges])
quadratic = QuadraticBezier(project, layer=curves,
                            p0=(-60, 20), p1=(-45, 40), p2=(-30, 20), selections=[edges])
cubic = CubicBezier(project, layer=curves,
                    p0=(-20, 20), p1=(-10, 45), p2=(10, 5), p3=(20, 25),
                    selections=[edges])
arc = CircularArc(project, layer=curves, center=(40, 20), radius=radius,
                  start_angle=0, end_angle=270, selections=[edges])

# %% Interpolation curve
# COMSOL builds its native spline. KLayout needs an explicit matching sampler.
# Here all interpolation points stay collinear, so the same straight line is
# known in both backends. A curved callback must be checked against COMSOL's spline.
interpolation_points = Vertices([[-3*pitch, -2*pitch],
                                [-2*pitch, -2*pitch], [-pitch, -2*pitch]])
interpolation = InterpolationCurve(
    project, layer=curves, points=interpolation_points,
    sampler=lambda s: interpolation_points[0] + (interpolation_points[-1] - interpolation_points[0])*s,
    selections=[edges],
)

# %% Parametric curve
# COMSOL formulas and the Python callback must describe the same curve.
# The callback returns length expressions, so radius keeps its unit and remains live.
parametric = ParametricCurve(
    project, layer=curves, coord=("curve_radius*cos(s)", "curve_radius*sin(s)"),
    parmin=0, parmax=2*pi, parameters=(radius,),
    sampler=lambda s: (radius*cos(s), radius*sin(s)), tolerance=0.001,
    selections=[edges],
)

# %% Build and display
# Curves have zero width here; no filled tracks or routing are added.
project.build()
project.show()

# After editing pitch.value or radius.value, call project.build() again.
