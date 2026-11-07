"""Build immediately as geometry is created; run the cells one at a time."""

# %% Parameters and project
from geompype import Project
from geompype.primitives import Square
from geompype.transforms import Rotate

# Lengths in µm, angles in degrees
side = 20
updated_side = 30
angle = 45

project = Project(live=True, output="output/example_live")
metal = project.add_layer("metal", gds_layer=1, comsol=True, gds=True)
project.show()

# %% Create the square — built immediately
square = Square(project, layer=metal, side=side, position=(40, 0))

# %% Add a rotated copy — built immediately
rotated = Rotate(square, angle=angle, keep=True)

# %% Change an existing parameter, then rebuild
square.side = updated_side
project.build()
