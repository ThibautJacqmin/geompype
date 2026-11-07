"""Asymmetric conductors, an explicit obstacle detour and a target-length route."""

# %% Named dimensions; lengths are in micrometres
from geompype import Parameter, Port, PortProfile, Project, Rectangle, Vertices, connect

span = Parameter(1000, 'route_span', unit='um')
launch_length = Parameter(200, 'detour_launch', unit='um')
detour_height = Parameter(250, 'detour_height', unit='um')
obstacle_x = Parameter(500, 'obstacle_x', unit='um')
clearance = Parameter(25, 'obstacle_clearance', unit='um')
lower_width = Parameter(6, 'lower_width', unit='um')
upper_width = Parameter(10, 'upper_width', unit='um')
lower_offset = Parameter(-12, 'lower_offset', unit='um')
upper_offset = Parameter(25, 'upper_offset', unit='um')
target_length = Parameter(2000, 'target_length', unit='um')

project = Project(output='output/routing_constraints')
lower_layer = project.add_layer('lower_wire', gds_layer=1)
upper_layer = project.add_layer('upper_wire', gds_layer=2)
resonator_layer = project.add_layer('resonator', gds_layer=3)
gap_layer = project.add_layer('resonator_gap', gds_layer=4)
obstacle_layer = project.add_layer('obstacles', gds_layer=10)

# %% Two unequal conductors, with unequal signed offsets from one centreline
profile = PortProfile(widths=[lower_width, upper_width],
                      offsets=[lower_offset, upper_offset],
                      layers=[lower_layer, upper_layer], names=['lower', 'upper'])
start = Port(pos=(0, 0), profile=profile)
# Ports point out of their components: reversing the destination profile keeps
# both conductors on the same physical side when arriving along positive x.
end = Port(pos=(span, 0), orientation=(-1, 0), profile=profile.reversed())
obstacle = Rectangle(project, layer=obstacle_layer,
                     position=(obstacle_x, 60), size=(260, 140))

# The explicit vertices choose the detour. Obstacles validate the whole width
# of every conductor plus clearance; they do not invoke a maze pathfinder.
detour_points = Vertices([(0, 0), (launch_length, 0), (launch_length, detour_height),
                          (span-launch_length, detour_height), (span-launch_length, 0), (span, 0)])
detour = connect(start, end, points=detour_points, radius=60,
                 obstacles=[obstacle], clearance=clearance, name='asymmetric_detour')
detour_selection = project.add_selection('asymmetric_conductors')
detour_selection.add(*detour.features)

# %% An independent CPW: solve count and amplitude from the required length
cpw = PortProfile.cpw(8, 4, resonator_layer, gap_layer)
resonator_start = Port(pos=(0, 600), profile=cpw)
resonator_end = Port(pos=(span, 600), orientation=(-1, 0), profile=cpw)
resonator = connect(resonator_start, resonator_end, radius=20,
                    target_length=target_length, meander_max_amplitude=100,
                    start_straight=100, end_straight=100,
                    obstacles=[obstacle], clearance=clearance, name='target_length')
resonator_selection = project.add_selection('target_conductor')
resonator_selection.add(resonator.geometry['signal'])
print(detour.report())
print(resonator.report())

# %% Generate both backends, with named layer and conductor selections
project.build()
project.show()

# Edit target_length.value=2400, then project.build(): the meander count adapts.
# Moving obstacle_x.value to 200 blocks the explicit detour. project.build()
# raises a clearance error and preserves the previous exports. Move the obstacle
# back or edit detour_points before rebuilding; the router does not move it for you.
