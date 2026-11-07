"""Alignment-mark gallery: X, cross, L, box-in-box and x/y verniers."""

# %% Layers and editable mark dimensions; lengths are micrometres
from geompype import (
    Parameter, Project, x_diamond_mark, box_mark, cross_mark, l_mark, vernier_mark,
)

project = Project(output='output/library_marks')
reference = project.add_layer('reference_marks', gds_layer=1)
moving = project.add_layer('moving_marks', gds_layer=2)
marks = project.add_selection('all_marks')
size = Parameter(100, 'mark_size', unit='um')
width = Parameter(8, 'mark_width', unit='um')
resolution = Parameter(.5, 'vernier_resolution', unit='um')

# %% Each helper has its own module in geompype/library
x_mark = x_diamond_mark(project, layer=reference, selections=(marks,))
cross = cross_mark(project, layer=reference, size=size, width=width,
                   selections=(marks,)).move(delta=(300, 0))
corner = l_mark(project, layer=reference, size=size, width=width,
                selections=(marks,)).move(delta=(550, -50))
outer_box = box_mark(project, layer=reference, size=size, width=width,
                     selections=(marks,)).move(delta=(900, 0))
inner_box = box_mark(project, layer=moving, size=.6*size, width=width,
                     selections=(marks,)).move(delta=(900, 0))

# %% Each vernier has two separate layer outputs, grouped for placement
horizontal = vernier_mark(project, reference_layer=reference, moving_layer=moving,
                          resolution=resolution, selections=(marks,)).move((300, -250))
vertical = vernier_mark(project, reference_layer=reference, moving_layer=moving,
                        resolution=resolution, selections=(marks,)).rotate(90).move((600, -250))

# %% Export both fabrication layers and their named COMSOL selections
project.build()
project.show()

# The tick pitch difference is the readout increment; the default is 0.5 um.
# Edit size.value, width.value or resolution.value, then call project.build().
