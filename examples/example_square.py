"""A square with its angle set directly in its definition."""

from geompype import Project
from geompype.primitives import Square

# Parameters — lengths in µm, angles in degrees
side = 20
position = (10, 5)
angle = 45

# Project and layer
project = Project(output="output/example_square", live=False)
metal = project.add_layer("metal", gds_layer=1, comsol=True, gds=True)

# Geometry
square = Square(project, layer=metal, side=side, position=position, angle=angle)

# Build and display
project.build()
project.show()
