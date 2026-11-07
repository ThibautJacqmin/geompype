"""Group geometry for FEM independently of the drawing layers."""

from geompype import Project
from geompype.primitives import Square
from geompype.transforms import Rotate

# Parameters — lengths in µm, angles in degrees
side = 20
second_side = 10
angle = 45

# Project and layers
project = Project(output="output/example_selections")
metal1 = project.add_layer("metal1", gds_layer=1, comsol=True, gds=True)
metal2 = project.add_layer("metal2", gds_layer=2, comsol=True, gds=True)

# FEM selections
conductors = project.add_selection("conductors", entity="boundary")
rotated_only = project.add_selection("rotated_only", entity="boundary")

# Geometry
square1 = Square(project, layer=metal1, side=side, position=(40, 0),
                 selections=[conductors])
square2 = Square(project, layer=metal2, side=second_side, position=(100, 0),
                 selections=[conductors])
rotated = Rotate(square1, angle=angle, keep=True, selections=[rotated_only])

# conductors contains both squares and the copy; rotated_only contains the copy.
project.build()
project.show()
