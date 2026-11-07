"""Omit individual sites from parameterized arrays in COMSOL and KLayout."""

# %% Parameters and layers; lengths are in micrometres
from geompype import Array, Circle, Parameter, Project, Rectangle

pitch = Parameter(20, "pitch", unit="um")
columns = Parameter(5, "columns")
project = Project(output="output/array_exclusions")
metal = project.add_layer("metal", gds_layer=1)
disks = project.add_layer("disks", gds_layer=2)
remaining = project.add_selection("remaining_sites")

# %% Linear exclusions are zero-based: skip the first and fourth copies
seed = Rectangle(project, layer=metal, size=(8, 6), position=(0, -35))
linear = Array(seed, size=columns, displacement=(pitch, 0), exclude=[0, 3])

# %% Rectangular exclusions are (x index, y index), also starting at zero
disk = Circle(project, layer=disks, radius=4)
pattern = disk.array(size=(columns, 3), displacement=(pitch, pitch),
                     exclude=[(2, 1), (4, 2)], selections=[remaining])

# %% Build and display both outputs
project.build()
project.show()

# Change pitch.value or columns.value, then call project.build().
# Every excluded index must remain inside the array, and one site must remain.
# To restore all sites: pattern.exclude = (); project.build().
# COMSOL stores excluded arrays as a Move with parameterized translations;
# their count/exclusion changes are applied by the Python build.
