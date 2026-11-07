"""All planar COMSOL transformations, with the same geometry exported to GDS."""

# %% Imports and parameters
from geompype import (
    Project, Parameter, Vertices, Rectangle, Circle, Polygon, Point, LineSegment,
    Move, Copy, Mirror, Rotate, Scale, Array,
)

width = Parameter(4, "width", unit="um")
height = Parameter(2, "height", unit="um")
pitch = Parameter(8000, "pitch", unit="nm")
angle = Parameter(30, "angle", unit="deg")
factor = Parameter(2, "factor")
count = Parameter(3, "count")

# %% Project and selections
project = Project(output="output/example_transforms", dbu=0.001, grid_policy="round")
metal = project.add_layer("metal", gds_layer=1, comsol=True, gds=True)
construction = project.add_layer("construction", gds_layer=2, comsol=True, gds=True)
surfaces = project.add_selection("all_surfaces")
curves = project.add_selection("all_curves", entity="edge")
anchors = project.add_selection("anchors", entity="point")
copies = project.add_selection("copied_surfaces")

# %% Move consumes its input; Copy retains it and accepts several offsets
move_source = Rectangle(project, layer=metal, size=(width, height),
                        position=(-60, 40), selections=[surfaces])
moved = Move(move_source, delta=(width, height))
copy_source = Rectangle(project, layer=metal, size=(width, height),
                        position=(-20, 40), selections=[surfaces])
offsets = Vertices([[0, 1], [1, 1]], pitch)
copied = Copy(copy_source, delta=offsets, selections=[copies])

# %% Mirror in the line through origin perpendicular to normal
outline = Vertices([[20, 38], [24, 38], [22, 42]])
triangle = Polygon(project, layer=metal, vertices=outline, selections=[surfaces])
mirrored = Mirror(triangle, normal=(1, 1), origin=(27, 40), keep=True)

# %% Several rotation angles in one native feature
rotate_source = Rectangle(project, layer=metal, size=(width, height),
                          position=(60, 40), selections=[surfaces])
rotated = Rotate(rotate_source, angle=(angle, 90), origin=(60, 30), keep=True)

# %% Different scale factors in x and y, around a fixed centre
disk = Circle(project, layer=metal, radius=height, position=(-60, 0), selections=[surfaces])
scaled = Scale(disk, factor=(factor, 1/factor), origin=(-60, 0))

# %% Linear and rectangular arrays include the original-position copy
linear_source = Rectangle(project, layer=metal, size=(width, height),
                          position=(-20, 0), selections=[surfaces])
linear = Array(linear_source, size=count, displacement=(pitch, pitch/2))
rectangular_source = Rectangle(project, layer=metal, size=(width, height),
                               position=(20, 0), selections=[surfaces])
rectangular = Array(rectangular_source, size=(count, 2), displacement=(pitch, pitch))

# %% Arrays and chained transformations also work for paths and points
line = LineSegment(project, layer=construction, p1=(-60, -30), p2=(-56, -29),
                   selections=[curves])
line_array = line.array(size=count, displacement=(pitch, 0))
moved_lines = line_array.move(delta=(0, -5))
point = Point(project, layer=construction, position=(20, -30), selections=[anchors])
point_array = point.array(size=(2, 2), displacement=(pitch, pitch))

# %% Build, inspect rounding, and show
project.build()
print(project.grid_report())
project.show()

# Try in the interactive console, then rebuild:
# count.value = 4
# pitch.value = 10000  # nm
# factor.value = 1.5
# angle.value = 45
# offsets[1] = offsets[1] + (0, 5)
# project.build()
#
# project.grid_policy = "error" rejects this gallery's off-grid final vertices.
# GUI display/editing grids are independent of the exported database grid.
