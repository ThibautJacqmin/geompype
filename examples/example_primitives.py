"""Four filled primitives sharing parameters and a FEM selection."""

from geompype import Project, Parameter, Vertices
from geompype.primitives import Rectangle, Circle, Ellipse, Polygon

# Parameters — lengths in um, angles in degrees
width = Parameter(20, "width", unit="um")
height = Parameter(10, "height", unit="um")
radius = Parameter(5, "radius", unit="um")

# Project and layer — set comsol=False to work offline
project = Project(output="output/example_primitives")
metal = project.add_layer("metal", comsol=True, gds=True)
conductors = project.add_selection("conductors")

# Native filled shapes; tolerance controls only the sampled GDS outlines
rectangle = Rectangle(project, layer=metal, size=(width, height),
                      position=(-40, 0), selections=[conductors])
circle = Circle(project, layer=metal, radius=radius,
                tolerance=0.001, selections=[conductors])
ellipse = Ellipse(project, layer=metal, semiaxes=(8, 4),
                  position=(40, 0), angle=30, tolerance=0.001,
                  selections=[conductors])
outline = Vertices([[-width / 2, 30], [width / 2, 30],
                    [width / 2, 35], [0, 40], [-width / 2, 35]])
polygon = Polygon(project, layer=metal, vertices=outline,
                  selections=[conductors])

project.build()
project.show()

# In the interactive console: width.value = 30; project.build()
# Both the rectangle and polygon follow width; COMSOL retains their formulas.
