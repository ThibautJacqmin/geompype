"""A table of parametric positions, with a common pitch and an offset."""

from geompype import Project, Parameter, Vertices
from geompype.primitives import Square
from geompype.transforms import Rotate

# Parameters
width = Parameter(4, "width", unit="um")
pitch = Parameter(20, "pitch", unit="um")
gap = Parameter(500, "gap", unit="nm")

# Three positions — coefficient table times pitch, then a common translation
centres = Vertices([[0, 0], [1, 0], [2, 1]], pitch)
centres = centres + Vertices([gap, 0])

# Project, layer and FEM group
project = Project(output="output/example_vertices")
metal = project.add_layer("metal", comsol=True, gds=True)
conductors = project.add_selection("conductors")

# Each row is a position; the parameter references are retained
for position in centres:
    square = Square(project, layer=metal, side=width,
                    position=position, selections=[conductors])

rotated = Rotate(square, angle=45, origin=centres[0], keep=True)

project.build()
project.show()

# In the interactive console: pitch.value = 30; project.build()
# All positions and the rotated copy will follow the new pitch.
