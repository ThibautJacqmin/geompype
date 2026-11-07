"""Split a multiconductor port and fit a meander into a bounded height."""

# %% Parameters and layers; lengths are in micrometres.
from geompype import Parameter, Port, PortProfile, Project, connect

project = Project(output='output/routing_utilities')
signal = project.add_layer('signal', gds_layer=1)
gap = project.add_layer('gap', gds_layer=2)
mask = project.add_layer('mask', gds_layer=3)
markers = project.add_layer('port_markers', gds_layer=99)
track = Parameter(8, 'track', unit='um')
separation = Parameter(20, 'band_offset', unit='um')
target = Parameter(2000, 'target_length', unit='um')
maximum = Parameter(100, 'maximum_amplitude', unit='um')

# %% An arbitrary two-conductor profile, with a mask enclosing both bands.
profile = PortProfile(widths=[track, track], offsets=[-separation, separation],
                      layers=[signal, signal], names=['lower', 'upper'])
masked_profile = profile.with_mask(mask, margin=5)
print('Enclosing mask bounds:', Port(profile=masked_profile).bond_params())
start = Port(pos=(0, 0), profile=profile, name='bus_start')
end = Port(pos=(1000, 0), orientation=(-1, 0), profile=profile.reversed(), name='bus_end')
starts = start.split(['lower', 'upper'], gap=4, gap_layer=gap)
ends = end.split(['lower', 'upper'], gap=4, gap_layer=gap)
connections = [connect(a, b, name=a.name) for a, b in zip(starts, ends)]
start.draw_markers(layer=markers, tip_scale=1)
end.draw_markers(layer=markers, tip_scale=1)
print('Upper conductor edges:', [v.value for v in start.track_edges('upper')])

# %% No prescribed count: choose the fewest feasible bends within the amplitude.
cpw = PortProfile.cpw(track, 4, signal, gap)
resonator_start = Port(pos=(0, 500), profile=cpw)
resonator_end = Port(pos=(1000, 500), orientation=(-1, 0), profile=cpw)
resonator = connect(resonator_start, resonator_end, radius=20,
                    target_length=target, meander_max_amplitude=maximum,
                    start_straight=100, end_straight=100, name='resonator')
resonator_selection = project.add_selection('resonator')
resonator_selection.add(resonator.geometry['signal'])
print(resonator.report())

# %% Change target.value to 2400 and build again: the count adapts from 6 to 8.
project.build()
project.show()
