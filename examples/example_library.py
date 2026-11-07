"""Two-inch wafer footprint and four alignment marks with parameterized placement."""

# %% Project, layers and placement parameters
from geompype import Parameter, Project, x_diamond_mark, two_inch_wafer

project = Project(output='output/library')
# The wafer is a drawing reference here. Set comsol=True to include its filled
# planar footprint in COMSOL too; the helper itself supports both backends.
wafer_layer = project.add_layer('wafer_reference', gds_layer=100, comsol=False)
mark_layer = project.add_layer('alignment', gds_layer=1)
marks_selection = project.add_selection('alignment_marks')
pitch = Parameter(30, 'mark_pitch', unit='mm')
angle = Parameter(0, 'mark_rotation', unit='deg')

# %% Create the wafer outline, then rotate and repeat the complete mark
wafer = two_inch_wafer(project, layer=wafer_layer)
mark = x_diamond_mark(project, layer=mark_layer, selections=(marks_selection,))
placed_mark = mark.rotate(angle=angle).move(delta=(-pitch/2, -pitch/2))
marks = placed_mark.array(size=(2, 2), displacement=(pitch, pitch))

# %% Export the wafer and marks to GDS, and the marks to COMSOL
project.build()
project.show()

# Zoom around (+/-15000, +/-15000) um in KLayout to inspect the marks.
# Edit pitch.value or angle.value and call project.build() to update placement.
