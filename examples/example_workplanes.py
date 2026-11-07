"""Two independent planar drawings separated by a native COMSOL parameter.

Synthetic geometry only: two lower electrodes and two upper pads within a
rectangular outline. The outlines are surfaces, with no solid thickness or
simulation physics. Each workplane exports its own GDS in local coordinates.
"""

# %% Common geometry project and placement parameters
from geompype import Parameter, Project, Rectangle

gap = Parameter(1, 'vacuum_gap', unit='um')
offset_x = Parameter(0, 'upper_offset_x', unit='um')
upper_angle = Parameter(0, 'upper_angle', unit='deg')
project = Project(output='output/workplanes')
upper = project.add_workplane('membrane', position=(offset_x, 0, gap), angle=upper_angle)

# %% Each drawing has its own layers; fabrication numbers can be reused
lower_metal = project.add_layer('lower_metal', gds_layer=1)
upper_metal = project.add_layer('upper_metal', gds_layer=1, workplane=upper)
upper_outline = project.add_layer('upper_outline', gds_layer=2, workplane=upper)
all_electrodes = project.add_selection('all_electrodes')

# %% Geometry is expressed in each workplane's local x/y coordinates
Rectangle(project, layer=lower_metal, size=(40, 60), position=(-30, 0), selections=(all_electrodes,))
Rectangle(project, layer=lower_metal, size=(40, 60), position=(30, 0), selections=(all_electrodes,))
Rectangle(project, layer=upper_metal, size=(30, 40), position=(-30, 0), selections=(all_electrodes,))
Rectangle(project, layer=upper_metal, size=(30, 40), position=(30, 0), selections=(all_electrodes,))
Rectangle(project, layer=upper_outline, size=(140, 100))

# %% One COMSOL model; output/workplanes.gds and output/workplanes_membrane.gds
project.build()
print(project.gds_path)
print(upper.gds_path)
project.show()

# To change the separation: gap.value = 2; project.build()
# Changing vacuum_gap directly in COMSOL also moves the upper geometry when
# rebuilding there. A later Python build writes the Python parameter values.
