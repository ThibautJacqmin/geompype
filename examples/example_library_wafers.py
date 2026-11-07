"""Two-, three- and four-inch wafer outlines with one or two flats."""

# %% Nominal outlines on independent drawing layers
from geompype import Project, two_inch_wafer, three_inch_wafer, four_inch_wafer

project = Project(output='output/library_wafers')
outlines = project.add_selection('wafer_outlines')
secondary_angle = 90  # Degrees anticlockwise from the primary flat's +y normal.
spacing = 120000     # Micrometres between drawing centres.

# %% Columns are wafer sizes; upper row has one flat, lower row two
wafer_objects = []
for index, (name, make_wafer) in enumerate((
        ('two_inch', two_inch_wafer), ('three_inch', three_inch_wafer),
        ('four_inch', four_inch_wafer))):
    layer = project.add_layer(name, gds_layer=100+index)
    for flat_count in (1, 2):
        wafer = make_wafer(project, layer=layer, flats=flat_count,
                           secondary_flat_angle=secondary_angle,
                           selections=(outlines,))
        wafer_objects.append(wafer.move(delta=(index*spacing, -(flat_count-1)*spacing)))

# %% Filled planar footprints only; no thickness or chip placement
project.build()
project.show()

# Three-inch and four-inch templates use 76200 and 100000 um diameters.
# Their flat_length, secondary_flat_length and tolerance can be chosen when
# creating the geometry. Move/rotate/scale accept the usual live parameters.
