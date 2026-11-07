"""Layer operations and automatic COMSOL selections in a single workplane."""

# %% Parameters and project
from geompype import Project, Parameter, Rectangle, Vertices

height = Parameter(12, "height", unit="um")
hole_width = Parameter(6, "hole_width", unit="um")
copy_spacing = Parameter(40, "copy_spacing", unit="um")
project = Project(output="output/example_layers")

# %% Logical layers: each has a GDS destination and an automatic FEM selection
left = project.add_layer("left", gds_layer=1)
right = project.add_layer("right", gds_layer=2)
joined = project.add_layer("joined", gds_layer=3)
cutters = project.add_layer("cutters", gds_layer=4)
etched = project.add_layer("etched", gds_layer=5)
copied = project.add_layer("copied", gds_layer=6)
mask = project.add_layer("mask", gds_layer=7)
window = project.add_layer("window", gds_layer=8)

# %% Merge the current geometry from two layers into a third
Rectangle(project, layer=left, size=(20, height), position=(-5, 20))
Rectangle(project, layer=right, size=(20, height), position=(5, 20))
merged_plate = project.merge_layers([left, right], output=joined,
                                    interior_boundaries=False)

# %% Subtract a cutter layer; the result belongs to etched
Rectangle(project, layer=cutters, size=(hole_width, 4), position=(0, 20))
etched_plate = project.subtract_layers(joined, cutters, output=etched,
                                       interior_boundaries=False)

# %% Copy keeps the source layer and places its copies on another layer
copied_plate = project.copy_layer(etched, output=copied, delta=(0, -copy_spacing))

# %% Intersect the union of each layer's current objects
Rectangle(project, layer=mask, size=(10, 30),
          position=Vertices((0, 20)) - Vertices((0, copy_spacing)))
window_plate = project.intersect_layers([copied, mask], output=window,
                                        interior_boundaries=False)

# %% Inspect both destinations
project.build()
print("Etched layer FEM selection:", etched.selection.tag)
print("Window layer FEM selection:", window.selection.tag)
project.show()

# height.value = 16
# hole_width.value = 8
# copy_spacing.value = 50
# project.build()
#
# Only etched and window contain final geometry here. Consumed source layers
# retain valid, empty COMSOL selections. All layers share the same wp1.
# Operations capture the current objects; later parameter edits remain live.
