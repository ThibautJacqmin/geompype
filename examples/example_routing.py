"""Synthetic rectangle pads, a constrained connection and a planar meander."""

# %% Configuration and drawing layers
from pathlib import Path
from geompype import Project, Rectangle, Port, PortProfile, connect, load_config
from geompype.components import Component

config = load_config(Path(__file__).parent/'routing.yaml', name='routing')
project = Project(output='output/routing')
signal = project.add_layer('signal', gds_layer=1)
gap = project.add_layer('gap', gds_layer=2)
mask = project.add_layer('mask', gds_layer=3)

# %% Two independent rectangular fixtures with geometry and named ports
left_config = config.child('left')
left_profile = PortProfile.cpw(config['track'], config['gap'], signal, gap,
                              mask_layer=mask, mask_margin=config['mask_margin'])
left_geometry = {
    name: Rectangle(project, layer=layer, size=(left_config['length'], width))
    for name, layer, width in zip(left_profile.names, left_profile.layers, left_profile.widths)
}
left = Component(project, geometry=left_geometry, ports={
    'route': Port(pos=(left_config['length']/2, 0), orientation=(1, 0),
                  profile=left_profile, name='left_route')}, name='left_rectangle')
left.place(position=left_config['position'])

right_config = config.child('right')
right_profile = PortProfile.cpw(right_config['track'], right_config['gap'], signal, gap,
                               mask_layer=mask, mask_margin=config['mask_margin'])
right_geometry = {
    name: Rectangle(project, layer=layer, size=(right_config['length'], width))
    for name, layer, width in zip(right_profile.names, right_profile.layers, right_profile.widths)
}
right = Component(project, geometry=right_geometry, ports={
    'route': Port(pos=(right_config['length']/2, 0), orientation=(1, 0),
                  profile=right_profile, name='right_route')}, name='right_rectangle')
right.place(position=right_config['position'], orientation=(-1, 0))

# %% Automatic taper and rounded connection through an oriented waypoint
waypoint = Port(pos=(1200, 450), orientation=(1, 0), name='via')
wire = connect(left.ports['route'], right.ports['route'], radius=config['radius'],
               via=[waypoint], taper_slope=.5, name='feedline')
feedline = project.add_selection('feedline')
feedline.add(wire.geometry['signal'])

# %% Prescribed meander; reported length includes exact circular bends
resonator_start = Port(pos=(400, 1800), orientation=(1, 0), profile=left_profile)
resonator_end = Port(pos=(2600, 1800), orientation=(-1, 0), profile=left_profile)
meander = config.child('meander')
resonator = connect(resonator_start, resonator_end, radius=meander['radius'],
                    meander_count=meander['count'], meander_amplitude=meander['amplitude'],
                    name='resonator')
print(wire.report())
print(resonator.report())

# %% Change config['track'].value and call build() to update both outputs.
project.build()
project.show()
