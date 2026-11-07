"""Verified curved interpolation and finite-width spline/Bézier tracks."""

# %% Parameters; lengths are micrometres
from geompype import (
    InterpolationCurve, Parameter, Project, QuadraticBezier, Thicken2D, Vertices,
)

span = Parameter(40, 'spline_span', unit='um')
rise = Parameter(10, 'spline_rise', unit='um')
width = Parameter(2, 'track_width', unit='um')
separation = Parameter(35, 'track_separation', unit='um')
project = Project(output='output/curved_tracks')
curves = project.add_layer('centreline', gds_layer=1)
tracks = project.add_layer('tracks', gds_layer=2)
centreline_selection = project.add_selection('spline_centreline', entity='edge')
spline_selection = project.add_selection('spline_track')
bezier_selection = project.add_selection('bezier_track')

# %% A genuinely curved interpolation with an independently known sampler
# For these three symmetric points, COMSOL 6.4 interpolates the parabola below.
# Native edge evaluations verify it before/after changing span and rise.
# This formula is specific to this example, not a general COMSOL spline solver.
points = Vertices([(-span/2, 0), (0, rise), (span/2, 0)])
centreline = InterpolationCurve(
    project, layer=curves, points=points,
    sampler=lambda s: (span*(s-.5), 4*rise*s*(1-s)),
    tolerance=.001, selections=[centreline_selection],
)

# %% The same spline translated down, then given a physical width
track_points = points + Vertices((0, -separation))
spline = InterpolationCurve(
    project, layer=tracks, points=track_points,
    sampler=lambda s: (span*(s-.5), 4*rise*s*(1-s)-separation),
    tolerance=.001,
)
spline_track = Thicken2D(spline, width=width, ends='circular',
                         selections=[spline_selection])

# %% A Bézier track beside it; unit weights select the polynomial Bézier
bezier = QuadraticBezier(
    project, layer=tracks, p0=(1.5*span, -separation),
    p1=(2*span, 3*rise-separation), p2=(2.5*span, -separation),
    weights=(1, 1, 1), tolerance=.001,
)
bezier_track = Thicken2D(bezier, width=width, ends='circular',
                         selections=[bezier_selection])

# %% Rebuild after editing span.value, rise.value or width.value
project.build()
project.show()
