"""All six planar transformations combined with Union, Difference and Intersection."""

# %% Parameters — all expressions remain editable
from geompype import (
    Project, Parameter, Vertices, Rectangle, Circle, Polygon, LineSegment, Point,
    Move, Copy, Mirror, Rotate, Scale, Array, Union, Difference, Intersection,
)

height = Parameter(12, "height", unit="um")
radius = Parameter(2, "radius", unit="um")
pitch = Parameter(10000, "pitch", unit="nm")
count = Parameter(3, "count")
angle = Parameter(30, "angle", unit="deg")
factor = Parameter(1.5, "factor")

# %% Layers and selections
project = Project(live=True, output="output/example_boolean_transforms", dbu=0.001)
project.show()
metal = project.add_layer("metal", gds_layer=1, comsol=True, gds=True)
construction = project.add_layer("construction", gds_layer=2, comsol=True, gds=True)
perforated_faces = project.add_selection("perforated_faces")
assembled_faces = project.add_selection("assembled_faces")
clipped_faces = project.add_selection("clipped_faces")
curve_edges = project.add_selection("curve_edges", entity="edge")
anchors = project.add_selection("anchors", entity="point")

# %% Array of circular cutters, Difference, Move, then Rotate
plate = Rectangle(project, layer=metal, size=(pitch*(count+1), height), position=(0, 40))
hole = Circle(project, layer=metal, radius=radius,
              position=(-pitch*(count-1)/2, 40))
hole_array = Array(hole, size=count, displacement=(pitch, 0))
perforated = Difference(plate, hole_array, interior_boundaries=False,
                        selections=[perforated_faces])
moved_plate = Move(perforated, delta=(10, 0))
rotated_plate = Rotate(moved_plate, angle=angle, origin=(10, 40))

# %% Mirror a triangle, unite, scale, and make a disconnected copied pair
origin = Vertices((-55, -10))
outline = Vertices([[-1, 0], [0, 0], [0, 1]], height) + origin
triangle = Polygon(project, layer=metal, vertices=outline)
mirrored = Mirror(triangle, normal=(1, 0), origin=origin, keep=True)
roof = Union([triangle, mirrored], interior_boundaries=False)
scaled_roof = Scale(roof, factor=(factor, 1/factor), origin=origin)
copied_roof = Copy(scaled_roof, delta=(0, -3*height))
assembled = Union([scaled_roof, copied_roof], interior_boundaries=False,
                   selections=[assembled_faces])

# %% Rectangular array, explicit Union as one operand, then mask Intersection
tile = Rectangle(project, layer=metal, size=(6, 6), position=(40, -30))
tile_array = Array(tile, size=(count, 2), displacement=(pitch, pitch))
tile_set = Union(tile_array, interior_boundaries=False)
mask_size = Vertices((pitch*(count-1), pitch)) + (6, -2)
mask_position = Vertices((40, -30)) + Vertices((pitch*(count-1)/2, pitch/2))
mask = Rectangle(project, layer=metal, size=mask_size, position=mask_position)
clipped = Intersection([tile_set, mask], interior_boundaries=False,
                       selections=[clipped_faces])

# %% Points and zero-width curves stay construction data through transforms
line = LineSegment(project, layer=construction, p1=(0, -60), p2=(height, -60),
                   selections=[curve_edges])
rotated_line = line.rotate(angle=angle, origin=(0, -60))
point = Point(project, layer=construction, position=(0, -40), selections=[anchors])
point_array = point.array(size=(2, 2), displacement=(5, 5))

# %% Build and display
project.build()
report = project.grid_report()
print("Grid (um):", report["dbu_um"], "Boolean operations:", len(report["boolean_operations"]))
project.show()

# count.value = 4
# pitch.value = 12000  # nm
# height.value = 14
# radius.value = 2.5
# factor.value = 1.2
# angle.value = 45
# outline[2] = outline[2] + (0, 1)
# project.build()
#
# The report distinguishes Boolean-input rounding from final export rounding.
# Region's internal rounding of new intersections is not a measured global error.
