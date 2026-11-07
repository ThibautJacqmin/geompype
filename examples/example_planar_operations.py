"""Corner edits, offsets and finite-width tracks in COMSOL and KLayout."""

# %% Imports and editable parameters (lengths in um)
from geompype import (Project, Parameter, Vertices, Rectangle, Polygon,
                     CircularArc, LineSegment, Fillet, Chamfer, Offset, Thicken2D)

radius = Parameter(2, "corner_radius", unit="um")
distance = Parameter(1, "offset_distance", unit="um")
width = Parameter(2, "track_width", unit="um")
outline = Vertices([(25, 20), (45, 20), (45, 32), (35, 38), (25, 32)])

# %% Project and FEM result groups
project = Project(output="output/example_planar_operations")
metal = project.add_layer("metal", comsol=True, gds=True)
rounded_faces = project.add_selection("rounded_faces")
beveled_faces = project.add_selection("beveled_faces")
grown_faces = project.add_selection("grown_faces")
band_faces = project.add_selection("band_faces")
track_faces = project.add_selection("track_faces")

# %% Fillet all rectangle corners; chamfer two selected polygon corners
plate = Rectangle(project, layer=metal, size=(20, 12), position=(0, 28))
rounded = Fillet(plate, radius=radius, selections=[rounded_faces])
pentagon = Polygon(project, layer=metal, vertices=outline)
beveled = Chamfer(pentagon, distance=radius, corners=outline[:2],
                  selections=[beveled_faces])

# %% Grow a plate, then cut a hole; fillets follow the native COMSOL radius
base = Rectangle(project, layer=metal, size=(20, 12), position=(0, 0))
grown = Offset(base, distance=distance, selections=[grown_faces])
hole = Rectangle(project, layer=metal, size=(8, 4))
frame = grown.difference(hole)

# %% Thickening a filled shape creates a boundary band, including its hole
boundary = Rectangle(project, layer=metal, size=(20, 12), position=(35, 0))
band = Thicken2D(boundary, width=width, selections=[band_faces])

# %% A native arc becomes a finite-width track with circular end caps
arc = CircularArc(project, layer=metal, radius=10, center=(0, -30),
                   start_angle=0, end_angle=135)
track = Thicken2D(arc, width=width, ends="circular", selections=[track_faces])
rotated_track = track.rotate(angle=15, origin=(0, -30))

# %% Parallel offset of a segment, then thicken it and scale the footprint
segment = LineSegment(project, layer=metal, p1=(25, -30), p2=(45, -30))
parallel = segment.offset(distance=distance)
straight_track = parallel.thicken(width=width, corner="extend")
stretched = straight_track.scale(factor=(1, 1.5), origin=(35, -30))

# %% Build and inspect both native geometry and the fabrication footprint
project.build()
project.show()

# radius.value = 3
# distance.value = 1.5
# width.value = 3
# outline[2] = (47, 32)
# project.build()

# KLayout uses Project.dbu for Region calculations. COMSOL stays native.
# Fillet/Chamfer consume their inputs; use Copy first to retain the original.
# This example uses symmetric thickening; example_routing.py adds multiband routes.
