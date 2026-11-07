# Technical references

These sources describe the APIs used by GeomPype. Native validation covers
COMSOL 6.4; references for 6.3 are identified separately and do not establish
whether a property is available in another version. Page numbers below are
those printed in the manuals. Local manuals are optional and are included in
neither the package nor its distributions.

## Curves and grid

[examples/example_curved_tracks.py](./examples/example_curved_tracks.py) uses an open
interpolation through `(-span/2,0)`, `(0,rise)`, `(span/2,0)`. On COMSOL 6.4,
independent `edgeParamRange`/`edgeX` evaluations confirm the parabola
`y=rise*(1-(2*x/span)^2)`, before and after changing its dimensions.
This check supports its KLayout sampler only for this symmetric family.
It does not reconstruct the general InterpolationCurve algorithm.
Native tests also check Thicken2D track boundaries, their selections and the
saved MPH file; areas alone are insufficient.

Sectors and rectangles in the rounded joins of `_planar.stroke` must share
the same vertices before integer conversion. Rounding them separately
produced small triangular gaps. Offline tests check for unwanted holes
without removing the intended hole in a closed track.

An isolated installation with KLayout 0.30.13 also showed a difference of
93 square grid units in an existing full comparison at a DBU of 1 nm.
`requirements.txt` therefore pins 0.30.1; the references and strict XOR equality
remain unchanged. This finding applies to the tested versions and cases,
not to a general error bound. See [ENVIRONMENT.md](./docs/ENVIRONMENT.md).

## Array exclusions and port utilities

The Programming Reference Manual 6.4, pp. 287–289, describes Array without a
generic site-exclusion option. Arrays with exclusions therefore use Move
(pp. 367–368), with specify=displ, displx/disply lists and propagatesel. Move
consumes the input; translation expressions retain their parameters.
A complete array remains a native Array. Omitting a copy does not subtract
its material from neighbouring copies, preserving overlaps, points and
curves. Python indices start at zero; build() recalculates the topology.

Port utilities provide local coordinate systems, band bounds, conductor
splitting and markers. They use Vertices and Polygon without adding a new
native type.
The automatic meander search belongs to the Python router: for a fixed
count n, an amplitude increase da adds 2*n*da to the length, while arc
corrections remain fixed. Counts from 1 to 256 are tried, subject to radius,
straight-section and maximum-amplitude constraints. The length remains
geometric; no propagation model or solver is added.

Native COMSOL 6.4 tests cover exclusions, overlaps, mixed objects, Array/Move
switching, parameters, selections and MPH readback, as well as split ports,
their markers and changes to the number of meanders.

## Wafer and alignment-mark library

The [geompype/library](./geompype/library/__init__.py) catalogue contains one file
per element. Wafers are generated outlines; `x_diamond_mark` loads the only
fixed JSON asset, documented in
[the library data notes](./docs/library-data.md).

The [Pango Semiconductor silicon wafer specifications](https://pgo-tech.com/silicon-wafer/)
give nominal diameters of 50.8, 76.2 and 100 mm, primary flats of
15.88, 22.22 and 32.5 mm, and secondary flats of 8, 11.18 and 18 mm.
These dimensions provide the defaults for the two-, three- and four-inch
functions. Flat lengths remain configurable. These values do not certify
a wafer's compliance or manufacturing tolerances. Flat positions are explicit
in the API; no doping or crystal axis is inferred.

The [SUSS MJB 3 manufacturer's manual](https://ipsiras.ru/Lab/CKPO/Nanofot/doc/SussMJB-3.pdf)
describes optical alignment by symmetry, including nested crosses.
The [EPFL MA6 Gen3 alignment assistance guide](https://www.epfl.ch/research/facilities/cmi/wp-content/uploads/2020/03/ma6gen3.align_.assist.pdf)
illustrates overlay marks and verniers. Catalogue patterns are parametric
geometries: using them does not certify compatibility with a particular
instrument or its measurement accuracy.

Tests compare marks against independent areas and wafers against a circle
clipped by the half-planes defining the flats. They check chord error,
the GDS grid, native Polygon coordinates, parameters, layer selections and
MPH readback separately.

## Layers and selections within a WorkPlane

The [Programming Reference 6.4](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/COMSOL_ProgrammingReferenceManual.pdf),
pp. 332–333, documents the `ExplicitSelection` geometry feature, its
`selection` selection, `selkeep` and `selshow`. The methods `init(dim)`,
`all(objectName)` and `clear()` are documented in Geometry Object Selection
Methods, pp. 140–141. `feature(tag).objectNames()` and `geom.obj(name)` identify
the objects actually available after operations (pp. 258–259).

Automatic layer groups capture entities only from their layer's terminal
objects, after operations. They do not use primitive result groups, because
those can propagate to copies on other layers. The Component group is a Union
of the selections promoted by the WorkPlane.
The contract is checked on COMSOL 6.4 by `tests/test_comsol_layers.py`:
ownership after copy and keep, empty groups, points/curves, intersections
grouped by layer, live additions, parameters and MPH readback.

The same manual, pp. 255–257, states that a new feature is inserted after the
current feature, and that `runPre(tag)` moves this position backwards. Fillet,
Chamfer and Thicken2D therefore build their results after inspecting input
entities; Project also restores the order when adding a feature after an
already-built sequence. Native tests cover this rule for
operation→rotation→scale chains in both deferred and live modes.

## Planar editing

- [Fillet, COMSOL 6.4](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.089.html):
  `point` selection, `radius`. The same manual also describes Chamfer (`point`,
  `dist`). Neither feature exposes `input`, `keep` or `propagatesel`.
  GeomPype's explicit `max_trim_fraction` option computes radius limits in
  Python and emits native Fillet groups; it is not a native COMSOL property.
  Each limit is `fraction * shortest_incident_edge / tan(abs(turn)/2)`.
  Native limits use COMSOL vertex coordinates and boundary-edge endpoints;
  the requested radius expression is retained in `min(radius, limit)`.
  Changing dimensions requires a Python `build()` to recompute the limits.
- [Offset, COMSOL 6.4](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.115.html):
  `distance`, `reverse`, `convexcorner`, `trim`, `keep` and `propagatesel`.
- [Programming Reference 6.4](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/COMSOL_ProgrammingReferenceManual.pdf),
  Thicken2D pp. 412–413: `offset=symmetric`, `totalthick`, `ends`, `convexcorner`.
  Surfaces require an edge selection rather than a solid-object selection.
  The native suite checks bands around a rectangle, segment end caps, arcs and
  offsets. `GeomObject.getEdge()` exposes the domains on either side: only
  edges touching the exterior domain 0 are retained when thickening a surface.
  The test of a union with retained FEM interfaces confirms that those
  interfaces do not become internal tracks.
- [KLayout DPath](https://www.klayout.de/doc/code/class_DPath.html): width,
  extensions, round ends and `polygon()` conversion; rounded joins are
  calculated explicitly and then merged using Region.
- [KLayout Region](https://www.klayout.de/doc/code/class_Region.html): integer
  calculations on the project's public grid; no Shapely dependency is added.

## COMSOL manual versions

- [Programming Reference Manual 6.4](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/COMSOL_ProgrammingReferenceManual.pdf):
  reference for the features used and the version validated by native tests.
- [Programming Reference Manual 6.3](https://doc.comsol.com/6.3/doc/com.comsol.help.comsol/COMSOL_ProgrammingReferenceManual.pdf):
  a separate edition; the page table below supports documentation comparisons
  without claiming tested compatibility.

## Geometry reference points

Planar Booleans:

- [COMSOL 6.4: Compose, Union, Intersection, Difference](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.070.html),
  manual pp. 304–306: `input`, `input2`, `intbnd`, `keep` for Union/Intersection,
  `keepadd`/`keepsubtract` for Difference, `keeplowerdim=off` for surface
  intersections, and `propagatesel`.
- [KLayout Region](https://www.klayout.de/doc-qt5/code/class_Region.html):
  sets of polygons, holes and Boolean operations in database units.
  Operands are rounded to the DBU before each Boolean, without a Shapely
  dependency. The report quantifies explicit conversions, not the rounding
  of new intersections within the integer algorithm.
- Native 6.4 checks: an empty Difference/Intersection result retains a native
  object and empty promoted selections, without changing the Selection code.
  `Union(array)` groups disjoint copies into one operand for Intersection.
  For two overlapping rectangles, `intbnd=on/off` produces three faces/one face
  respectively, with the same occupied area.

Grid and planar transformations:

- The Programming Reference Manual **6.4**, Table 3-6 on p. 250, lists `Array`,
  `Mirror`, `RigidTransform`, `Rotate`, `Scale`, `Move`, `Copy`.
  `RigidTransform` is explicitly **3D** there and is not emitted in the plane.
- `Array` pp. 287–289: `type=linear|rectangular`, `linearsize` or `fullsize`,
  `displ`, `propagatesel`. Copies include the initial position and replace
  the input objects; no `keep` property is emitted.
- `Mirror` pp. 365–366: `specify=pointnormal`, `axis` is the normal to the line,
  `pos`, `keep`, `propagatesel`.
- `Move, Copy` pp. 367–368: `specify=displ`, `displx`, `disply` accept multiple
  values. `Copy` retains the inputs and `Move` replaces them; no `keep`.
- `Rotate` pp. 396–397: one or more angles `rot`, centre `pos`, `keep`.
  `Scale` pp. 398–399: scalar or x/y pair `factor`, centre `pos`, `keep`.
  Negative factors were checked on the 6.4 server.
- [KLayout Database API](https://www.klayout.de/doc/programming/database_api.html):
  layout coordinates are integers multiplied by `dbu` in µm.
  Floating-point objects are rounded when converted to the database.
- [KLayout Geometry API](https://www.klayout.de/doc/programming/geometry_api.html):
  `DCplxTrans` applies floating-point transformations; anisotropic scaling is
  calculated explicitly on the coordinates, including holes.
- [KLayout editor options](https://www.klayout.de/doc/manual/editor_options.html):
  display and editing grids do not define the GDS resolution.

Native tests compare results against expected areas and coordinates, and
check selection propagation, collections of points/curves/surfaces,
parameter changes and MPH readback. Grid tests check final rounding alone
and preservation of previous outputs when a build is rejected.

Points and curves:

- [CircularArc, COMSOL 6.4](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.066.html):
  `specify=center`, `center`, `r`, `angle1`, `angle2`, `clockwise`. The `type`
  property shown on this page is **rejected by the tested 6.4 server**;
  it is not emitted. The native result was verified to be a 1D curve.
- [QuadraticBezier](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.127.html)
  and [CubicBezier](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.078.html):
  control-point matrix `p` and weights `w`; rational quadratic default
  `(1, 1/sqrt(2), 1)`, unit cubic weights by default.
- [InterpolationCurve](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.102.html):
  open native spline, `source=vectors`, `rtol=0`, boundary conditions `none`.
  Because its exact parameterization is undocumented, KLayout evaluation
  requires an explicit Python function; no substitute spline is assumed equivalent.
- [ParametricCurve](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.117.html):
  `coord`, `parname`, `parmin`, `parmax`. Formulas are retained on the COMSOL
  side, with an independent Python function for KLayout sampling.
- [GeomInfo](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/model/GeomInfo.html):
  native tests use `edgeParamRange` and `edgeX` to compare the actual curves
  against GDS paths, independently of the rendering mesh used for measurements.
- [DPath](https://www.klayout.de/doc-qt5/code/class_DPath.html),
  [DPoint](https://www.klayout.de/doc-qt5/code/class_DPoint.html) and
  [the maintainer's confirmation about paths without width](https://www.klayout.de/forum/discussion/2093/making-not-closed-but-connected-lines):
  centrelines are zero-width paths; points are coordinates.
  Paths disappear in surface operations. No substitute square is created
  for a point.

Filled primitives, properties from the Programming Reference Manual 6.4:

| Primitive | Printed page | Properties used |
| --- | ---: | --- |
| `Circle` | 299–301 | `type=solid`, `base=center`, `angle=360`, `r`, `pos` |
| [`Ellipse`](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.084.html) | 328–329 | `type=solid`, `base=center`, `semiaxes`, `pos`, `rot` |
| [`Polygon`](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.125.html) | 384–386 | `type=solid`, `source=vectors`, expressions `x` and `y` |
| [`Rectangle`](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.128.html) | 389–390 | `type=solid`, `base`, `size`, `pos`, `rot` |

These features remain in the 2D plane of a 3D geometry. The GDS contour
sampling tolerance is a separate Python setting that does not change the
analytic COMSOL primitives. Thicken2D and routing now create finite-width
tracks; general profile sweeps remain deferred.

The [COMSOL measurement methods](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.047.html)
(p. 277) calculate areas using a rendering mesh. Tests of the new primitives
use a 0.5% margin for curved areas, with independent checks of native
features, expressions, bounds and selections. This does not relax the
geometric tolerance of GDS export, which is tested separately.

| Programming Reference Manual topic | User edition 6.3 | Official edition 6.4 |
| --- | ---: | ---: |
| Overview of primitives, operations, selections and virtual operations | 240–246 | 248–254 |
| Sequences, creation, properties, building and feature state | 247–253 | 255–261 |
| Units, tolerances and rebuilding | 254–257 | 262–265 |
| Work planes | 258 | 266 |
| Named and cumulative selections | 259–260 | 267–268 |
| Geometry information and measurements | 263–270 | 271–278 |
| Start of the detailed Geometry Commands catalogue | 276 | 284 |
| `Array` | 279 | 287 |
| `Compose`, `Union`, `Intersection`, `Difference` | 295 | 304 |
| `Mirror`; `Move`, `Copy` | 355 ; 357 | 365 ; 367 |
| `RigidTransform`; `Rotate`; `Scale` | 384 ; 385 ; 387 | 394 ; 396 ; 398 |
| `Offset`; `Thicken2D` | 359 ; 401 | 369 ; 412 |
| `CrossSection`; `Extrude`; `Revolve`; `Sweep` | 305 ; 324 ; 381 ; 395 | 315 ; 334 ; 392 ; 406 |
| Detailed description of `WorkPlane` | 407 | 418 |

The catalogue covers 1D, 2D and 3D. The manuals also refer to the Design,
CAD Import and ECAD Import module documentation for their additional commands.
Coverage depends on the version and available modules.

Java 6.4 signatures can be checked on the official
[GeomSequence](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/model/GeomSequence.html)
and [GeomFeature](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/api/com/comsol/model/GeomFeature.html)
pages. These allow checks of `create`, `feature`, `run`, `geom`,
`selection` and `objectNames`, rather than inventing aliases.

## MPh: Python access to COMSOL

The COMSOL 6.4
[Mathematical Functions](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_ref_definitions.21.037.html)
page documents `max`, `round`, `floor`, `abs` and `sign`, among others. Because
it does not specify the rule for half-integers, the export of `round_nearest(x)`
explicitly writes `sign(x)*(floor(abs(x))+(abs(x)-floor(abs(x))>=0.5))`.
Server tests check agreement with Python calculations for positive/negative
half-integers, the floating-point value immediately below 0.5 and a large
exactly representable integer. Both public functions, `maximum` and
`round_nearest`, require dimensionless arguments here.

For parameters,
[`model.param()`](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_general.47.50.html)
documents `set(name, expression, description)`, `get`, `evaluate` and
`evaluateUnit`. Global parameters and feature properties retain their
expressions. `GeomSequence.angularUnit(...)`, documented in the Java API
cited above, complements `lengthUnit(...)` in setting the geometry context.

The MPh version used for native validation is **1.4.0**. The "stable" links
change over time; declared dependencies determine which versions are
accepted at installation.

- [Model API](https://mph.readthedocs.io/en/stable/api/mph.Model.html): `mph.Model.java` exposes the complete COMSOL Java model. Detailed geometry creation can use the Programming Reference Manual commands through this object.
- [Installation](https://mph.readthedocs.io/en/stable/installation.html): JPype and NumPy dependencies, 64-bit Windows Python and the JVM bundled with COMSOL. GeomPype was checked with COMSOL 6.4; consult the MPh documentation for platform and version constraints.
- [Installation discovery](https://mph.readthedocs.io/en/stable/api/mph.discovery.html): MPh already locates COMSOL, including through the Windows registry. This module is internal; avoid copying its logic into the project.
- [Limitations](https://mph.readthedocs.io/en/stable/limitations.html): one client/JVM per process; independent parallel sessions require multiple processes. Standalone and client–server modes have different platform constraints.

## KLayout: main API and guides

Main API reference:
[KLayout class index, Qt 5 documentation](https://www.klayout.de/doc-qt5/code/index.html).
This index distinguishes the `db` (geometry database) and `lay` (graphical
interface) modules, among others.

- [Standalone Python module](https://www.klayout.org/klayout-pypi/): `klayout.db` can create, manipulate and write GDS layouts without depending on the graphical interface.
- [Using Python](https://www.klayout.de/doc-qt5/programming/python.html): reference example with `import klayout.db as kdb` and syntax differences between the Ruby and Python interfaces. The page recommends the `klayout` submodules and states that the old combined `pya` module is deprecated.
- [Geometry API](https://www.klayout.de/doc/programming/geometry_api.html): polygons, regions, polygonal curves, transformations and Boolean operations; consult it for GDS contours and their discretization.
- [Application API](https://www.klayout.de/doc/programming/application_api.html): windows, views and Desktop sessions, useful for previewing. `Layout`, `Cell` and file layers remain accessible in `klayout.db`.

KLayout pages change over time. The properties used are checked against the
version declared in requirements.txt; consult its release notes before
changing this dependency.

## Ports and routing

Python routing produces analytic segments and circular arcs, which are
assembled and then thickened by Thicken2D (manual 6.4, pp. 412–413).
KLayout bands use DPath(width).polygon(), then Region on the public grid for
tapers, collisions and fabrication operations. Native checks compare edges
through edgeParamRange/edgeX; getArea alone is not an exact measurement of
curved contours. The short chords added at arc ends also control the
inclination of the DPath end cap.

The library retains named profiles, signed offsets, reversed ports, linear
tapers, oriented waypoints, meanders and line/arc lengths.
YAML import uses PyYAML.safe_load, with explicit includes, inheritance and
variants; it does not instantiate drawing classes automatically.

Circuit recipes and their parameters can be maintained in a separate
package that depends on GeomPype. The public package and its generic tests
do not import any private recipe package.

[KLayout SaveLayoutOptions](https://www.klayout.de/doc/code/class_SaveLayoutOptions.html)
defines `gds2_max_vertex_count` and `gds2_multi_xy_records`.
The general writer sets a limit of 4000 vertices and disables multi-XY records
to split large perforated contours without long GDS records interpreted as
unsigned. This limit applies to the exported file, not to the floating-point
or native COMSOL geometry.

## Multiple WorkPlanes

[WorkPlane, COMSOL 6.4](https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.143.html)
documents `planetype=quick`, `quickplane=xy`, `quickz`, `displ` and `rot`:
plane height, local-origin displacement and axis rotation.
These properties receive parameter expressions, with `selplaneshow=on`
to promote the groups from each planar geometry. `Project` uses each plane's
own 2D sequence, then builds the shared 3D geometry.
Selections are resolved from each object's owning WorkPlane.
GDS files are separate and retain their local coordinates.
Native tests check the actual bounding boxes after movement, rotation,
changing the gap in Python and then in COMSOL alone, and saving the MPH file.
