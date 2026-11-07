"""Final GDS rounding and explicitly rounded design dimensions."""

# %% Imports and project settings — bare lengths are um
from geompype import Project, Parameter, DependentParameter, Square, round_nearest

project = Project(output="output/example_grid", dbu=0.001, grid_policy="round")
metal = project.add_layer("metal", comsol=True, gds=True)

# %% A deliberate fractional-grid position: COMSOL retains the requested value
width = Parameter(20, "width", unit="um")
square = Square(project, layer=metal, side=width, position=(0.0004, 0))
rotated = square.rotate(angle=30, keep=True)

# %% Explicit design rounding is shared by COMSOL and KLayout
design_grid = Parameter(1, "design_grid", unit="nm")
requested = Parameter(20.0004, "requested", unit="um")
snapped = DependentParameter(round_nearest(requested/design_grid)*design_grid, "snapped")
snapped_square = Square(project, layer=metal, side=snapped,
                        base="corner", position=(40, 0))

# %% Build, inspect the grid report, and display
project.build()
print(project.grid_report())
project.show()

# To reject meaningful final-coordinate rounding, set:
# project.grid_policy = "error"
# project.build()  # rejects this example's fractional position and rotation
#
# Curve tolerance is independent of dbu; a finer dbu does not refine sampling.
# Changing the KLayout GUI display/editing grid does not change these settings.
