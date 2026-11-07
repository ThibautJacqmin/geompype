"""Keep a square and create a rotated copy using a separate transformation."""

from geompype import Project
from geompype.primitives import Square
from geompype.transforms import Rotate

# Parameters — lengths in µm, angles in degrees
side = 20
position = (40, 0)
angle = 45
origin = (0, 0)

# Project and layer
project = Project(output="output/example_rotation")
metal = project.add_layer("metal", gds_layer=1, comsol=True, gds=True)

# Geometry
square = Square(project, layer=metal, side=side, position=position)
rotated = Rotate(square, angle=angle, origin=origin, keep=True)

# Build and display
project.build()
project.show()
