"""Union, a plate with a hole, and an intersection, in COMSOL and GDS."""

# %% Imports and parameters
from geompype import Project, Parameter, Vertices, Rectangle, Circle, Union, Difference, Intersection

width = Parameter(20, "width", unit="um")
height = Parameter(12, "height", unit="um")
radius = Parameter(3, "radius", unit="um")

# %% Project and result selections
project = Project(output="output/example_booleans", dbu=0.001)
metal = project.add_layer("metal", comsol=True, gds=True)
joined_faces = project.add_selection("joined_faces")
cut_faces = project.add_selection("cut_faces")
overlap_faces = project.add_selection("overlap_faces")

# %% Union — retain interior boundaries for FEM; GDS contains the footprint
left = Rectangle(project, layer=metal, size=(width, height), position=(-30, 20))
right = Rectangle(project, layer=metal, size=(width, height),
                   position=Vertices((-30, 20)) + Vertices((width/2, 0)))
joined = Union([left, right], selections=[joined_faces])

# %% Difference — the result contains a genuine hole
plate = Rectangle(project, layer=metal, size=(width, height), position=(25, 20))
hole = Circle(project, layer=metal, radius=radius, position=(25, 20))
cut = Difference(plate, hole, selections=[cut_faces])

# %% Intersection — only the shared area survives
first = Rectangle(project, layer=metal, size=(width, height), position=(-5, -20))
second = Rectangle(project, layer=metal, size=(width, height),
                    position=Vertices((-5, -20)) + Vertices((width/2, 0)))
overlap = Intersection([first, second], selections=[overlap_faces])

# %% Build and inspect
project.build()
report = project.grid_report()
print("Grid (um):", report["dbu_um"], "Maximum coordinate rounding (um):",
      report["max_coordinate_displacement_um"])
project.show()

# width.value = 24
# radius.value = 4
# project.build()
#
# Boolean calculations use KLayout Regions on project.dbu. COMSOL remains native.
# grid_policy="error" checks Boolean operands too; it normally rejects sampled circles.
