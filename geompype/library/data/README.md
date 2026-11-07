# Geometry library data

`x_diamond_mark.json` contains sampled polygon coordinates in **micrometres**.
It ships in wheels and source distributions and is loaded by the
`geompype.library.x_diamond_mark` helper.

| Asset | Polygon names | Vertices | Bounds in um |
| --- | --- | --- | --- |
| `x_diamond_mark.json` | `cross`, `diamond1`–`diamond4` | 368 + 4 × 130 | (-87.546, -87.546) to (87.546, 87.546) |

The mark has an X and four diamond satellites with sampled rounded corners.
Its five polygons are combined into one Union feature. Other catalogue marks
and the two-, three- and four-inch wafer contours are generated from their
documented dimensions and do not require coordinate assets.

`tests/test_library.py` verifies this asset's coordinate checksums, vertex
order, dimensions, transformations and GDS output. The opt-in
`tests/test_comsol_library.py` checks native geometry, areas, parameters and
selections. `tests/test_wafer_library.py` independently checks nominal wafer
diameters, flat lengths and circular sampling.
