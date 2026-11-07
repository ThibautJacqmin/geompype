# GeomPype

**GeomPype — One Python-scripted geometry for both COMSOL simulations and lithography GDS masks.**

**[Documentation](./docs/index.md)**: installation, API guide, catalogue and
references. The [build guide](./docs/BUILDING.md) explains how to generate
the HTML site locally and configure it on Read the Docs.

**[Geometry library — browse shapes and contribute](./docs/LIBRARY.md)**:
alignment marks and wafer outlines, with previews and examples.

The Python package `geompype` is distributed under [AGPL-3.0-or-later](./LICENSE),
with its [copyright notice](./COPYRIGHT). This guide presents the API and examples.
The [feature index](./docs/FEATURE_COVERAGE.md) links each capability
to an example and describes the current limits. The [installation guide](./docs/ENVIRONMENT.md)
covers the Python environment, tests and distributions.

This project creates shapes in COMSOL using `mph` and writes their GDS geometry
using `klayout.db`. Available shapes are `Square`, `Rectangle`, `Circle`,
`Ellipse` and `Polygon`, all filled, along with points and zero-width curves
used as the basis for routing. Numeric lengths are in micrometres and numeric
angles are in degrees. Parameters may carry another compatible unit.

Transformations, Booleans, Fillet, Chamfer, Offset and Thicken2D can be
combined in the same graph. Multiple planar drawings can be placed in
separate COMSOL WorkPlanes. Operations between layers stay within their
WorkPlane; a selection can span several planes.
The project generates geometry without creating physics, meshes or studies.

In COMSOL, geometry always belongs to a **3D component**:

```text
Component (comp1)
└── Geometry (geom1, 3D)
    └── Work Plane (wp1)
        └── Plane Geometry (2D)
            └── Square
```

## Installation and first drawing

From the repository root, create an environment and install the package:

```text
python -m venv .venv
```

On Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

On Linux/macOS:

```sh
.venv/bin/python -m pip install -e .
```

Python 3.10 or newer is required. The first example produces a GDS file without
a COMSOL installation or server:

```python
from geompype import Project, Square

project = Project(output="output/square")
metal = project.add_layer("metal", comsol=False, gds=True)
Square(project, layer=metal, side=20, position=(10, 5))
project.build()
print(project.gds_path)
```

The file is `output/square.gds`. The two output destinations are selected
independently **per layer**. With `comsol=True`, the same drawing also creates
COMSOL geometry and an MPH file; a compatible COMSOL installation, a licence
and an available server are required. Server settings are described in
[COMSOL configuration](./docs/COMSOL_CONFIGURATION.md).

With `Project(live=True)`, each shape is built as soon as it is created;
otherwise, call `project.build()`. Changing a parameter always requires
another `build()`.

The optional `project.show()` call opens the installed interfaces. In
COMSOL Desktop, select the model shown in the console through
**File > COMSOL Multiphysics Server > Import Application from Server**.
KLayout reloads the GDS automatically.

## Using the examples

Public scripts are grouped in `examples/`, alongside their YAML parameters.
These are ordinary scripts: edit the parameters at the top,
then press **Run** in the editor. Variables such as `project`, `square` and
`rotated` remain accessible after execution in an interactive console.
They follow the order imports, parameters, project and layers, geometry,
build and display.

Configure the editor to use the project environment's interpreter
(`.venv/Scripts/python.exe` on Windows, `.venv/bin/python` on Linux)
and the project root as its working directory. The parent directory's name
does not matter. Generated files go into `output/`. For example, from the
repository root, using the project interpreter:

```text
python -i examples/example_square.py
```

The `-i` option keeps the console and COMSOL connection open after the script.
The COMSOL server must be available at the configured address before building
a COMSOL layer; the default is `localhost:2036`.

| Script | Example content |
| --- | --- |
| `examples/example_all_features.py` | Complete live-mode gallery: all 12 primitives, parameters, `Vertices`, rotations and FEM selections. |
| `examples/example_grid.py` | Final GDS rounding, grid report and explicit rounding of a parameter shared by both backends. |
| `examples/example_transforms.py` | All six planar transformations, multiple copies, linear/rectangular arrays, parameters and selections. |
| `examples/example_array_exclusions.py` | Exclude sites from a linear or rectangular array, with parameters and selection of the remaining copies. |
| `examples/example_booleans.py` | Union, difference with a hole and intersection, with native selections. |
| `examples/example_boolean_transforms.py` | Combined gallery: plate perforated by an array, mirror/union/scale/copy and an array clipped by a mask. |
| `examples/example_planar_operations.py` | Fillet, Chamfer, Offset and Thicken2D, parameters and selected corners. |
| `examples/example_layers.py` | Merge, subtract, copy and intersect layers, with automatic FEM selections. |
| `examples/example_workplanes.py` | Two drawings on parameterized planes, with separate selections and GDS files. |
| `examples/example_library.py` | Two-inch wafer and four alignment marks, with parameterized rotation and spacing. |
| `examples/example_library_marks.py` | X with diamonds, cross, L, nested frames and x/y verniers on two layers. |
| `examples/example_library_wafers.py` | All three wafer diameters, each with one or two flats. |
| `examples/example_routing.py` | CPW profiles, launches, oriented waypoint, taper, meander, YAML and FEM selection. |
| `examples/example_routing_utilities.py` | Split a multiconductor port, draw its markers and automatically fit a meander to a target length. |
| `examples/example_routing_constraints.py` | Asymmetric bands, target length and clearance checks against obstacles. |
| `examples/example_square.py` | A square with `angle` specified directly in its definition. |
| `examples/example_rotation.py` | A square and its copy created by `Rotate`. |
| `examples/example_selections.py` | FEM selections grouping two layers. |
| `examples/example_live.py` | Immediate construction, one cell at a time. |
| `examples/example_parameters.py` | Parameters and formulas preserved in COMSOL. |
| `examples/example_vertices.py` | An array of parameterized positions, a shared pitch and a translation. |
| `examples/example_primitives.py` | Parameterized rectangle, disk, ellipse and polygon in a FEM selection. |
| `examples/example_curves.py` | Points, segments, arcs, Bézier curves and curves with explicit sampling. |
| `examples/example_curved_tracks.py` | A curved interpolation curve and a Bézier track, with native comparison of the sampling. |

To produce only GDS, set `comsol=False` on the layers.
To build without opening windows, comment out `project.show()`.
Change the output path directly in `Project(output=...)`.
The examples use the [local server settings](./docs/COMSOL_CONFIGURATION.md).
Explicit arguments such as `Project(host="localhost", port=2036, ...)`
override them for a project.

For a complete demonstration, run **`examples/example_all_features.py`**. It opens
both viewers before drawing and uses `Project(live=True)`. The top row contains
the five filled shapes; the other rows show the six curves, a rotated arc copy
and the COMSOL points. The rectangle is replaced by its rotation; the arc and
point also retain their originals.

In COMSOL Desktop, import the `example_all_features` model from the server.
Under **Component 1 > Definitions > Selections**, inspect `all_surfaces`,
`all_curves`, `anchors`, `rotated_surfaces` and `rotated_curves`. A closed curve
may correspond to several COMSOL topological edges. In KLayout,
layers 1 and 2 contain surfaces, while layer 3 contains zero-width paths;
points do not add any GDS markers.

The final commented lines show how to change `width`, `height`,
`gap`, `angle` and a vertex of `outline`, then call `project.build()`.
`gap` uses nm; the other lengths use µm. The `radius` and `pitch`
expressions follow the parameters; `rounded_ratio` illustrates an explicitly
registered parameter using `maximum` and `round_nearest`.

In `examples/example_live.py`, `# %%` comments delimit cells.
Run the project cell first, select its model in COMSOL,
then run the geometry cells to see the successive changes.
Creating objects triggers a build; after changing an existing attribute,
call `project.build()`, as in the final cell.

Rerunning a script in the same console reuses the COMSOL connection and creates
a new model. Windows already opened for this output are reused;
in COMSOL, select the new model shown in the console using
**Import Application from Server**. Previous models remain available.

A new run normally updates the output files. If another model keeps the MPH
file open, export automatically uses a numbered name
(`example_square_2.mph`, etc.) and prints its path. The open file remains
intact. `project.mph_path` always reports the path actually used;
the GDS keeps its usual path for previewing.

## Filled 2D primitives

```python
from geompype import Project, Rectangle, Circle, Ellipse, Polygon, Vertices

project = Project(output="output/primitives")
metal = project.add_layer("metal", comsol=True, gds=True)

rectangle = Rectangle(project, layer=metal, size=(20, 10), position=(-40, 0))
circle = Circle(project, layer=metal, radius=5)
ellipse = Ellipse(project, layer=metal, semiaxes=(8, 4),
                  position=(40, 0), angle=30)
polygon = Polygon(project, layer=metal,
                  vertices=Vertices([[0, 30], [20, 30], [10, 40]]))
project.build()
project.show()
```

`Rectangle.size` contains the width and height. As with `Square`,
`base="center"` is the default; `base="corner"` places the lower-left corner
at `position`. The angle rotates the rectangle about that position.
`Circle` is a complete disk centred at `position`. `Ellipse.semiaxes`
contains the two semiaxes; `angle` rotates the ellipse about its centre.
Sectors and unfilled outlines are not provided in this version.

`Polygon` accepts a `Vertices` object or a list of points. The outline is closed
automatically; repeating the first point at the end is optional. Concave shapes
and either traversal direction are accepted. At least three distinct points
and a nonzero area are required; self-intersections, backtracking along an edge
and repeated interior vertices are rejected. `Polygon` defines a single
outline; holes can be created with `Difference`.

These shapes accept the existing parameters, expressions and FEM selections,
as well as `.rotate(...)`. A directly supplied `Vertices` object remains shared.
After changing dimensions or coordinates, call `build()`, even in live mode.
COMSOL retains the native features and expressions.

For `Circle` and `Ellipse`, `tolerance=0.001` sets the maximum deviation in µm
between the analytical outline and its GDS segments **before** rounding to the
`Project.dbu` grid. This approximation does not change the COMSOL geometry.
A smaller tolerance produces more vertices; a request exceeding 65,536
vertices raises an explicit error. This limit applies to GDS.

## Points and construction curves

The primitives available in `geompype.primitives` and directly in
`geompype` are `Point`, `LineSegment`, `CircularArc`, `QuadraticBezier`,
`CubicBezier`, `InterpolationCurve` and `ParametricCurve`.
They provide the low-level tools for routing. Creating them produces
zero-width curves; `curve.thicken(width=...)` then builds their finite-width
footprint.

| Object | COMSOL | KLayout and GDS |
| --- | --- | --- |
| `Point(position=...)` | Native `Point` feature, with expressions preserved. | `DPoint` for calculations; no marker in GDS. |
| `LineSegment(p1=..., p2=...)` | Native segment. | Zero-width `DPath`, written as a GDS path. |
| `CircularArc(radius=..., center=..., start_angle=..., end_angle=...)` | Native arc, with direction controlled by `clockwise`. | Zero-width path, sampled according to `tolerance`. |
| `QuadraticBezier(p0=..., p1=..., p2=...)` | Native quadratic Bézier curve. | Zero-width path, with adaptive subdivision. |
| `CubicBezier(p0=..., p1=..., p2=..., p3=...)` | Native cubic Bézier curve. | Zero-width path, with adaptive subdivision. |
| `InterpolationCurve(points=..., sampler=...)` | Actual native open spline, `rtol=0`. | Path calculated by the supplied Python function. |
| `ParametricCurve(coord=..., sampler=..., parameters=...)` | Native coordinate formulas. | Path calculated by the supplied Python function. |

References to parameters and `Vertices` remain live; call `build()` after a
change. `.rotate(...)` preserves a point or path as such. A curve FEM selection
uses `entity="edge"`, and a point selection uses `entity="point"`, in the 3D
geometry containing the plane. Zero-width paths are valid in KLayout and GDS,
but have no area and disappear when converted to a surface region.
Long paths are split into connected GDS records of at most 4,000 vertices,
without losing any segment; the in-memory `DPath` object remains whole.

Rational Bézier `weights` must be strictly positive.
The quadratic default follows COMSOL: `(1, sqrt(0.5), 1)`; pass `(1, 1, 1)`
for a polynomial Bézier curve. The cubic default is `(1, 1, 1, 1)`.
For arcs and Bézier curves, `tolerance` bounds the chord error before the GDS
grid; requests exceeding 65,536 points are rejected. `CircularArc`
requires distinct endpoint angles modulo 360.

**Explicit limitation for the last two classes:** COMSOL text is not executed
in Python, and COMSOL's exact spline algorithm is not reconstructed.
KLayout output therefore requires `sampler(s)`, a function that returns
`(x, y)` in µm, length expressions or a single `Vertices` object.
For interpolation, `s` ranges from 0 to 1; for a parametric curve, it ranges
from `parmin` to `parmax`. Declare named parameters used by formulas or by
the function in `parameters=(...)`.

The function's author must ensure that it describes the same curve as COMSOL.
Adaptive sampling checks intermediate points using `tolerance`, without
guaranteeing a mathematical bound for an arbitrary function.
`sampling_intervals` controls the initial discretization and must resolve any
rapid variations. Without a function, COMSOL-only output remains available;
a KLayout request raises an explicit error.

```python
from math import cos, sin, pi
from geompype import Parameter, ParametricCurve

radius = Parameter(10, "radius", unit="um")
curve = ParametricCurve(
    project, layer=metal, coord=("radius*cos(s)", "radius*sin(s)"),
    parmax=pi, parameters=(radius,),
    sampler=lambda s: (radius*cos(s), radius*sin(s)),
)
```

Ports and multiband routing form a higher-level layer using Thicken2D and
finite-width DPaths. Sweeping an arbitrary 2D shape remains deferred;
symmetric thickening is available through Thicken2D.
`CompositeCurve`, the deprecated `BezierPolygon` and 3D primitives
are not implemented.

## GDS grid and precision

```python
project = Project(dbu=0.001, grid_policy="round")  # 0.001 µm = 1 nm
```

Coordinates remain floating-point values during construction and transformations.
Vertices are rounded to the GDS grid before Region calculations: Boolean
operands, outlines and pieces of Offset/Thicken2D bands. Final objects are
also rounded at export. This uses the existing `Region` operations directly,
without adding Shapely or a hidden grid. Points remain construction data and
are not exported as markers. Parameters and native COMSOL geometry are not
rounded. A finer `dbu` must be chosen explicitly; it does not change curve
sampling. The KLayout GUI's display/editing grid is independent.

`grid_policy="error"` rejects off-grid coordinates at these explicit conversions,
while tolerating floating-point calculation noise. This mode may reject arbitrary
rotations and curved outlines. The error preserves the previous GDS and occurs
before any COMSOL changes. In live mode, every addition triggers a build:
use deferred mode if an off-grid intermediate object must be moved onto the grid
by a later transformation.

```python
project.build()
report = project.grid_report()
print(report["dbu_um"], report["max_coordinate_displacement_um"])
print(report["affected_objects"])
```

The report describes the latest GDS build attempt. `complete` indicates whether
the file was written; `objects` details the affected objects, their changed
vertices and adjacent vertices merged by rounding.
Each entry identifies its `stage` (`boolean_input`, `operation_input` or
`export`) and, when it belongs to an operation, its `operation_tag`.
`boolean_operations` and `planar_operations` list calculations on the integer
grid. A direct call to `to_klayout()` checks the policy but does not replace
the report from the latest build. Maximum displacement is measured per
coordinate, in µm. Errors for completely collapsed geometry and values outside
the GDS integer range are explicit. This report is not a DRC check of spacing
or topology; a narrow passage can close without the total area becoming zero.
New intersections calculated **inside Region** also lie on the integer grid.
Their rounding is not quantified by this report, and `"error"` does not compare
the Boolean against an exact rational calculation. The reported maximum
only describes the measured conversions, not a global bound on geometric
deviation after a chain of operations.

To deliberately round a dimension in **both backends**, use an explicit
expression, as in `examples/example_grid.py`:

```python
design_grid = Parameter(1, "design_grid", unit="nm")
requested = Parameter(20.0004, "requested", unit="um")
snapped = DependentParameter(round_nearest(requested/design_grid)*design_grid, "snapped")
```

Dependencies remain editable. This rounding does not guarantee that final
vertices lie on the grid: a centred square with a 3 nm side has vertices at
±1.5 nm and measures 4 nm after rounding to a 1 nm grid.

## Planar transformations

All planar transformations in the COMSOL catalogue are available directly
in `geompype` and in `geompype.transforms`:

| Transformation | Example | Input objects |
| --- | --- | --- |
| `Move` | `Move(shape, delta=(10, 5))` | Replaced by the result. |
| `Copy` | `Copy(shape, delta=((10, 0), (20, 5)))` | Retained alongside the copies. |
| `Rotate` | `Rotate(shape, angle=(30, 90), origin=(2, 3))` | Retained only with `keep=True`. |
| `Mirror` | `Mirror(shape, normal=(1, 1), origin=(2, 3))` | Retained only with `keep=True`. |
| `Scale` | `Scale(shape, factor=(2, 0.5), origin=(2, 3))` | Retained only with `keep=True`. |
| `Array` | `Array(shape, size=(3, 2), displacement=(10, 15))` | Replaced by the array, which includes the initial position. |

The methods `shape.move(...)`, `.copy(...)`, `.rotate(...)`, `.mirror(...)`,
`.scale(...)` and `.array(...)` create the same features. Constructors also
accept a list of objects from the same project and layer.
A result containing multiple geometries can be transformed again;
`to_klayout()` then returns a flat tuple of geometries instead of a single geometry.

`Move` and `Copy` accept a vector or a `Vertices` array of vectors.
`Rotate.angle` accepts an angle or a list of angles. `Mirror.normal` is a
dimensionless vector perpendicular to the reflection line: `(1, 0)` reflects
across a vertical line. `Scale.factor` is a uniform factor or an x/y pair;
negative factors are accepted, while zero is rejected.
`Array.size=3` creates a linear array along the `displacement` vector;
`size=(3, 2)` creates a rectangular array with the specified x/y spacing.
Sizes count the initial copy and must be positive integers.

To omit sites, use **zero-based indices**:

```python
linear = Array(seed, size=5, displacement=(20, 0), exclude=[0, 3])
# For another seed: (x index, y index) pairs.
pattern = disk.array(size=(5, 3), displacement=(20, 20),
                     exclude=[(2, 1), (4, 2)])
```

Each exclusion omits all input objects at that site; it does not cut overlapping
neighbouring copies. Duplicate entries have no effect, indices outside the
array are rejected, and at least one site must remain.
An array with exclusions uses a COMSOL `Move` with the retained translations;
its dimensions and spacing keep their expressions. Changing its count or
`pattern.exclude` requires a Python `project.build()`. An empty list restores
the complete array, emitted as a native `Array`.

Dimensions, directions, factors and sizes retain their parameter references.
Selections propagate by default; `propagate_selections=False` disables native
propagation. Points remain points, paths remain zero-width and surfaces remain
filled. Transformations do not round intermediate results. Scaling also
multiplies the source curve's sampling error: choose its `tolerance` accordingly.

`RigidTransform` is exclusively 3D in COMSOL and remains outside the planar
scope. Modes that define an axis through COMSOL entities and additional
Design Module options are not exposed; coordinate and expression modes
are used here.

## Planar Boolean operations

`Union`, `Difference` and `Intersection` are available in `geompype` and
`geompype.booleans`. They accept filled surfaces from the same project and
layer. Points, zero-width paths and mixed dimensions are explicitly rejected.
COMSOL uses its native features; GDS uses `klayout.db.Region` operations
at the `Project.dbu` resolution.

```python
from geompype import Union, Difference, Intersection

joined = Union([left, right], interior_boundaries=True)
cut = Difference(plate, tools=[hole], keep_tools=True)
overlap = Intersection([first, second])
```

Equivalent methods are `left.union(right)`, `plate.difference(hole)` and
`first.intersection(second)`. Inputs are consumed by default.
`Union` and `Intersection` accept `keep=True`. `Difference` provides two
independent options: `keep_base` and `keep_tools`, both false by default.
This allows a tool to be reused without exporting the original plate again.

`interior_boundaries=True` retains COMSOL interior boundaries, matching the
native default. With `False`, they are removed. The GDS contains the outline
of the occupied area; it does not represent internal FEM interfaces.
`selections` and `propagate_selections` work as they do for transformations.
Holes, disjoint pieces and empty results are accepted. An empty Boolean
returns `()` from `to_klayout()` and has empty native selections; it can become
nonempty again after a parameter change and rebuild.

An operation can use the outputs of an array. To intersect its complete
footprint with a mask, explicitly unite its elements:

```python
tile_set = Union(tile_array)
clipped = Intersection([tile_set, mask])
```

Passing an array with multiple elements directly to `Intersection` is rejected:
COMSOL would intersect the individual objects with each other, producing a
different operation. `Union` and `Difference` accept arrays directly.
`Difference` subtracts the union of its tools from the union of its bases.

Results can be moved, rotated, copied, mirrored, scaled, repeated and reused
in further Booleans. Transformations preserve holes and disjoint pieces.
Calculations run again after changes to parameters or `Vertices`.
`Compose` remains deferred. For operations between separate layers, use the
project methods described below.

To try everything together, run `examples/example_boolean_transforms.py`.
The `perforated_faces`, `assembled_faces` and `clipped_faces` selections let you
inspect the three results in COMSOL. The script also contains a rotated curve,
four anchor points and commented lines for changing parameters and a vertex,
then rebuilding.

## Multiple drawings and WorkPlanes

`Project` retains its default plane, accessible through
`project.default_workplane`. Existing scripts continue to draw there.
To add another drawing parallel to the XY plane:

```python
from geompype import Parameter, Project, Rectangle

project = Project(output='output/two_chips')
gap = Parameter(1, 'vacuum_gap', unit='um')
upper = project.add_workplane('membrane', position=(0, 0, gap))

bottom_metal = project.add_layer('bottom_metal', gds_layer=1)
top_metal = project.add_layer('top_metal', gds_layer=1, workplane=upper)
Rectangle(project, layer=bottom_metal, size=(40, 60))
Rectangle(project, layer=top_metal, size=(30, 40))
project.build()
```

This produces one shared COMSOL model and **two separate GDS files**:

| Access | File or object |
| --- | --- |
| `project.mph_path` | `output/two_chips.mph`, both planes in `comp1/geom1` |
| `project.gds_path` | `output/two_chips.gds`, drawing on the default plane |
| `upper.gds_path` | `output/two_chips_membrane.gds`, drawing on the second plane |
| `project.layout` | KLayout layout of the default plane |
| `upper.layout` | Independent KLayout layout of the second plane |

Each GDS contains a `TOP` cell in local coordinates. The WorkPlane position and
rotation apply only to the COMSOL assembly; changing the gap does not move the
fabrication patterns in KLayout. Both drawings may reuse the same GDS layer
numbers. Layer names are unique within the project; `workplane='membrane'`
also accepts the plane's name. Plane names start with a letter and contain
letters, digits or underscores; they are case-insensitively unique for filenames.

`position=(x, y, z)` places the local origin; `angle=...` orients its axes
within the plane. Numeric values are in µm/degrees. Position and angle accept
`Parameter`/`DependentParameter` and remain native COMSOL expressions.
Changing `gap.value` and calling `project.build()` updates the geometry.
In COMSOL alone, changing `vacuum_gap` and rebuilding is also sufficient;
a later Python build emits the Python values again. This API covers planes
parallel to XY and their rotation about Z, without tilt or solid volumes.

`upper.native` returns the Java WorkPlane after native construction.
`project.workplane` refers to the default Java WorkPlane.
Declaring planes and layers does not start COMSOL. A plane whose layers are
GDS-only is not created in COMSOL. A plane without any GDS layers does not
produce an additional file. The default plane's file is retained whenever
GDS export is requested, even if that first drawing is empty.

`project.show()` opens one KLayout preview per enabled GDS drawing and the
shared COMSOL client. Complete example: [examples/example_workplanes.py](./examples/example_workplanes.py).

## Layers, operations and automatic selections

Each layer belongs to a WorkPlane, **`wp1` by default**. A layer is a logical
drawing group and a GDS destination; it introduces neither height nor physical
thickness. Selections are groups of entities: overlapping surfaces can belong
to several groups after the final COMSOL union. Position belongs to the
WorkPlane; this API does not introduce solid thicknesses.

Booleans, copies between layers and planar routes require the same WorkPlane,
even if two planes temporarily have the same height. Explicit groups created
by `project.add_selection()` can combine objects from several planes.

Each layer created by `project.add_layer(...)` provides `layer.selection`,
an automatic selection of planar surfaces in the final 3D geometry.
Its stable tag, such as `lsel1_2`, can be passed to
`physics.selection().named(layer.selection.tag)` after `build()`.
Its COMSOL label is `Layer: <name>` in the default plane and
`Layer: <plane> / <name>` in other planes. Other entity levels are available
through `layer.selection_for(entity="edge")` and `entity="point"`; call
`build()` after creating them. A layer containing only curves/points has an
empty surface selection. A GDS-only layer creates no COMSOL selection or
implicit connection.

```python
from geompype import Project, Rectangle

project = Project(output="output/layers")
metal = project.add_layer("metal", gds_layer=1)
cuts = project.add_layer("cuts", gds_layer=2)
result = project.add_layer("result", gds_layer=3)
Rectangle(project, layer=metal, size=(20, 10))
Rectangle(project, layer=cuts, size=(4, 4))
plate = project.subtract_layers(metal, cuts, output=result)
project.build()
print(result.selection.tag, result.selection.entities())
```

| `Project` method | Calculated geometry | Input preservation |
| --- | --- | --- |
| `merge_layers([a, b], output=c)` | Union of the source layers' surfaces. | `keep=False` by default. |
| `subtract_layers(base, tools, output=c)` | Union of bases minus union of tools. Each side accepts a layer or a list. | Independent `keep_base=False` and `keep_tools=False`. |
| `intersect_layers([a, b], output=c)` | Intersection of each layer's union. Islands and arrays within a layer form a single operand. | `keep=False` by default. |
| `copy_layer(a, output=b, delta=(dx, dy))` | Translated copy of surfaces, curves and points. | Source always retained. |

Arguments accept Layer objects or their registered names. The `output` layer
must already exist; any geometry it contains is retained, and the result is
added to it. It can also be a source layer. The `comsol` and `gds` flags must
match across all sources and the destination to prevent input consumption
from differing between backends.

Operations capture objects **still available at the time of the call**,
without including their consumed ancestors. Their parameters and `Vertices`
remain live and are reevaluated at `build()`. Adding a new shape to a source
layer afterward does not retroactively include it in the operation. An empty
source layer, repeated layer or mix of projects is rejected before changing
the graph. The three layer Booleans require filled surfaces; thicken curves
before combining them. `copy_layer` preserves their dimensions.

Automatic groups follow the final objects **currently assigned to their layer**.
A consumed layer retains an empty group; keeping/copying a source does not add
another layer's results to its group. These groups cannot be changed through
`add/remove`. Explicit `Selection` objects remain available for custom grouping
and retain their native propagation.

COMSOL uses native Union/Difference/Intersection/Copy features in `wp1`.
Intersection first uses an internal Union per layer. Layer groups are captured
at the end of the sequence by ExplicitSelection features, then promoted to
Component > Definitions. This avoids confusing layer ownership with native
propagation of a source selection. KLayout uses the same Regions and grid as
object Booleans, without Shapely.

## Parameters and formulas

`Parameter` represents an editable value; `DependentParameter` represents a
named formula. Dimensions, positions, angles and rotation centres accept
these objects directly:

```python
from geompype import Project, Parameter, DependentParameter
from geompype.primitives import Square
from geompype.transforms import Rotate

width = Parameter(20, "width", unit="um", description="Square width")
gap = Parameter(500, "gap", unit="nm")
angle = Parameter(45, "angle", unit="deg")
pitch = DependentParameter(width + 2 * gap, "pitch")

project = Project(output="output/parameters")
metal = project.add_layer("metal", comsol=True, gds=True)
square = Square(project, layer=metal, side=width,
                position=(pitch, 0), angle=angle)
rotated = Rotate(square, angle=angle / 2, keep=True)
project.build()
```

Used parameters and their dependencies are detected automatically.
`project.parameters` retrieves these objects by name. A name must start with
a letter and contain ASCII letters, digits or `_`.
Reuse the same object when several features share a parameter;
two distinct objects with the same name in a project are rejected.

For a parameter intended for simulation but not yet used in the geometry,
use `project.add_parameter(parameter)`. Its dependencies are included too.
Registration triggers neither a connection nor a build, even in live mode;
`build()` exports its definition as soon as a COMSOL layer is enabled.

In COMSOL, parameters from COMSOL layers become global parameters:
`width = 20[um]`, `gap = 500[nm]`, `pitch = width + 2*gap`.
The feature keeps `width` as its side and `pitch` as its position. Formulas
therefore remain usable when editing in COMSOL or running a parametric sweep.
The GDS contains the polygons evaluated at build time.

To update both exports from Python:

```python
width.value = 30
project.build()
print(pitch.value)  # 31 µm: the dependency is recalculated.
```

Call `build()` after changing a value, **even in live mode**.
Passing `side=width` preserves the dependency; passing `side=width.value`
fixes a numeric value at that moment. A change in COMSOL is not copied back
to Python; the next `project.build()` reapplies the Python definitions used
by the geometry or registered with `add_parameter`, without erasing other
COMSOL parameters.

Available operations are `+`, `-`, `*`, `/`, parentheses and unary `-`,
as well as `maximum(a, b)` and `round(expression)`. These two functions take
dimensionless arguments and preserve their dependencies:

```python
from geompype import maximum

um = Parameter(1, "um_ref", unit="um")
radius = Parameter(8, "fillet_r", unit="um")
count = DependentParameter(maximum(8, round(3 * radius / um)), "fillet_n")
project.add_parameter(count)
project.build()  # fillet_n = 24; the formula remains editable in COMSOL.
```

Dividing by a reference length makes the argument dimensionless. Parameterized
rounding is to the nearest integer, with half-integers rounded away from zero:
2.5 gives 3, and -2.5 gives -3. `round_nearest(expression)` is its explicit name,
importable from `geompype`; unlike `round(2.5)` on an ordinary Python number,
`round(parameter_expression)` uses this rule. `maximum` compares exactly two
expressions; the ordinary Python `max` does not construct a parameterized formula.

Powers `**`, functions such as `sin`, `cos` or `sqrt`, lambdas and formulas
supplied as text are not supported in this version.

Accepted units are `nm`, `um`, `mm`, `m`, `deg`, `rad` and `""` for a dimensionless
value. Addition converts compatible units: here, `width + 2*gap` initially
equals 21 µm. Adding a length to an angle or a dimensionless number is rejected;
a literal zero is accepted. Products and quotients preserve dimensions;
`width/gap` is dimensionless. At the geometry interface, a dimensionless number
or parameter takes the field's unit: µm for a length, degrees for an angle.

`Parameter.value` is expressed in the declared unit. `DependentParameter.value`
uses µm, degrees or their products by default. For example,
`DependentParameter(width + 2*gap, "pitch_nm", unit="nm")` reads the same length
in nm without changing its COMSOL formula. A dependent parameter's value is
calculated and cannot be assigned; its formula can be changed with
`pitch.expression = width + 3*gap`. Names and units are fixed.

Incompatible units, circular dependencies, division by zero and non-finite
values are rejected before export. To work offline, set `comsol=False`
on the layers; parameter evaluation is independent of COMSOL.

## Corners, offsets and planar thickening

The `Fillet`, `Chamfer`, `Offset` and `Thicken2D` classes are available from
`geompype` and `geompype.operations`. The flat script
[`examples/example_planar_operations.py`](./examples/example_planar_operations.py)
combines all four with parameters, `Vertices`, FEM selections, rotation,
scaling and difference.

```python
rounded = plate.fillet(radius=2)
limited = narrow_shape.fillet(radius=10, max_trim_fraction=0.49)
beveled = other_plate.chamfer(distance=1, corners=Vertices([[10, 5]]))
expanded = shape.offset(distance=1)
contracted = another_shape.offset(distance=1, reverse=True)
track = curve.thicken(width=2, ends="circular")
```

- `Fillet` rounds all corners, or those identified by their coordinates
  in `corners`. `Chamfer` removes the same distance along both incident edges.
  Holes are preserved. For KLayout, inputs must have straight-edged outlines:
  junctions with curved edges remain unsupported. An excessive size that makes
  the cuts overlap is rejected. These COMSOL features consume their input;
  use `Copy` first to retain it.
- `Fillet(..., max_trim_fraction=0.49)` explicitly reduces a corner's radius
  until its tangent trim uses at most 49% of either incident edge. The default
  `None` keeps the requested radius unchanged. The fraction must be greater
  than 0 and less than 0.5; it does not prevent collisions with other edges.
  This option requires one straight-edged input feature; use `Union` first
  to combine objects. Its native result must also be one object, which may
  contain holes and disconnected islands. COMSOL uses
  native Fillet features and computes limits from its actual geometry; GDS
  uses its own contours. Call `build()` after changing dimensions to update
  the edge-based limits. `effective_radii()` reports the selected GDS corner
  coordinates and radii in µm.
- `Offset` expands surfaces or shifts a curve to its left, according to its
  orientation. `reverse=True` reverses this direction. The distance must be
  nonnegative. Curve offsets that collapse or require global trimming are
  explicitly rejected by KLayout.
- `Thicken2D` takes the total `width` and builds a symmetric band.
  For a surface, it thickens its exterior outlines and holes; internal FEM
  interfaces must not become additional tracks. `ends="straight"` creates
  straight caps, while `"circular"` creates semicircular caps. Asymmetric
  widths and arbitrary-profile sweeps remain deferred.
- Offset and Thicken accept `corner="fillet"` (default) or `"extend"` for
  extended joins, as well as `keep` and `propagate_selections`. Other native
  corner modes are not exposed in this initial API.
- Lengths accept parameters. `tolerance=0.001` µm controls sampling of the
  added arcs; discretization of the source curve remains separate. Region
  calculations use `Project.dbu`, without Shapely, and appear in `grid_report()`
  under `planar_operations` / `operation_input`. Thickened outputs are polygons
  that can be used by Booleans.

Native tests check areas, holes, selected corners, saved expressions,
thickened outlines and internal interfaces. The example is run several times,
then rebuilt after changing parameters and a vertex. Outputs can feed a later
transformation, including after an initial build.

## Coordinate arrays: Vertices

`Vertices` groups 2D points made up of numbers, parameters or expressions.
Parameter references are retained after translation, multiplication,
extraction or concatenation.

`Vertices` does not automatically create COMSOL parameters for every coordinate.
Plain numbers become numeric coordinates; named `Parameter` objects used in
the coordinates are registered in COMSOL, and their expressions remain in
the geometry properties. Passing `.value` to a new geometry deliberately
creates a numeric copy without these dependencies.

```python
from geompype import Vertices, Parameter, Square, Rotate

pitch = Parameter(20, "pitch", unit="um")
gap = Parameter(500, "gap", unit="nm")
points = Vertices([[0, 0], [1, 0], [2, 1]], pitch)
points = points + Vertices([gap, 0])

square = Square(project, layer=metal, side=4, position=points[1])
rotated = Rotate(square, angle=45, origin=points[0])
project.build()

pitch.value = 30
project.build()  # Positions and the rotation centre follow pitch.
```

The constructor accepts a point `[x, y]`, an `N × 2` array or an `N × M × 2`
grid flattened in Python order: the second index varies first.
Lists, tuples, numeric NumPy arrays and `dtype=object` arrays are accepted.
The array may mix numbers, `Parameter`, `DependentParameter` and formulas.
`Vertices.xy(x, y)` creates a point; `Vertices.from_components(...)` is another
name for construction from components. An empty array is accepted.

Dimensionless numbers are in **µm**, independently of the other components.
For example, with `gap = 500[nm]`, `Vertices([gap, 2]).value` equals
`[[0.5, 2.0]]` in µm. `Vertices([gap, 2], unit="nm")` equals `[[0.5, 0.002]]`.
An explicit unit applies to dimensionless numbers and parameters; parameters
carrying a length retain their own unit. Compatible length units are converted;
angles are rejected.

The second argument is a shared factor: `Vertices([[1, 0], [0, 1]], pitch)`.
The components must then be dimensionless coefficients. The notation
`Vertices([[1, 0], [0, 1]]) * pitch`, as well as `pitch * Vertices(...)`, is also
accepted for an array of coefficients created without an explicit unit.
Multiplying already dimensioned coordinates by another length is rejected.

| Operation | Result |
| --- | --- |
| `points.value` | `N × 2` list of current values in µm. |
| `points.values(unit="nm")` | The same values in nm, without GDS rounding. |
| `points.xvalue`, `points.yvalue` | Lists of coordinates in µm. |
| `points[0]`, `points[1:]` | New `Vertices` containing the selected rows. |
| `points[0, 1]` | Scalar expression for the first point's y coordinate. |
| `for point in points` | Iterate over points, each as a `Vertices` object. |
| `points + [dx, dy]` | Shared translation; another array of the same size is also accepted. |
| `points * factor`, `points / factor`, `-points` | Coordinate-by-coordinate calculation with a dimensionless factor. |
| `points.concat(other)` | Concatenation, including with different units or factors. |
| `points.centroid()` | Mean of the physical coordinates as a parameterized point. |
| `points.to_comsol()` | Array of COMSOL expressions, including units and names. |
| `points.parameters` | Dictionary of used parameters, including dependencies. |

Indices start at zero. `points[0] = [x, y]` and `points[0, 1] = y` modify the
coordinates; numbers use the unit specified at construction. Slice assignment
preserves the number of points. An invalid assignment leaves the previous
array intact. `points.array` provides an immutable view of the expression rows.

A position or rotation centre must contain **exactly one point**.
If the same `Vertices` object is assigned directly to a feature, its changes
are applied at the next `build()`. An extraction such as `points[0]` copies
that row's expressions: changing the source array's structure does not alter
the copy, while changing shared parameters updates it.
Numeric outputs are copies and do not modify the geometry.
Ragged arrays, non-finite values, incompatible units and division by zero
are rejected; an empty array has no centroid.

## Selections for FEM simulation

A `Selection` groups geometry results independently of layers.
A feature can belong to several groups. These groups are saved in the MPH
file under **Component > Definitions**, with their readable names.

```python
from geompype.transforms import Rotate

conductors = project.add_selection("conductors", entity="boundary")
terminal = project.add_selection("terminal_1", entity="boundary")
square = Square(project, layer=metal, side=20, position=(40, 0),
                selections=[conductors])
rotated = Rotate(square, angle=90, keep=True, selections=[terminal])
project.build()

print(conductors.tag)       # Stable tag for selection().named(...).
print(conductors.entities())  # Current entity numbers, for inspection only.
```

Selections follow transformations by default: here, `conductors` contains
the original square and its copy, while `terminal` contains only the copy.
Setting `propagate_selections=False` on a transformation disables this
propagation. `square.rotate(...)` accepts the same options. The `selections`
argument adds memberships; it does not replace propagated memberships.

`conductors.add(obj)` and `conductors.remove(obj)` change explicit memberships;
call `project.build()` afterward in deferred mode. In live mode, these methods
rebuild immediately. `conductors.members` contains explicitly added objects,
while COMSOL tracks their descendants. Removing an explicit membership from a
transformation therefore does not remove a membership still propagated from
its input.

The entity level refers to the **final 3D geometry**: `boundary` selects the
square surfaces, `edge` their outlines and `point` their vertices. `domain`
is reserved for volumes; adding a planar square to a domain selection raises
a clear error at build time. Members from a `comsol=False` layer remain Python
metadata and are ignored in COMSOL. Selections do not change the GDS geometry.

In `examples/example_selections.py`, `conductors` contains both squares and the
rotated copy; `rotated_only` contains only the copy. The groups are visible
under **Component > Definitions** in COMSOL.

## Code organization

Demonstration scripts and their YAML files are in `examples/`, tests in
`tests/`, guides in `docs/` and maintenance tools in `tools/`.
The root contains installation files and the project overview.

- `geompype/project.py`: project, build and display.
- `geompype/_klayout_preview.py`: internal script launched in KLayout Desktop
  to reload the GDS when it changes.
- `geompype/_comsol.py`: connection reuse within the same Python session.
- `geompype/layer.py`: settings for a layer.
- `geompype/workplane.py`: planar drawing positions and separate GDS outputs.
- `geompype/geometry.py`: shared `GeometryObject` class.
- `geompype/selection.py`: `Selection` class and native COMSOL groups.
- `geompype/parameters.py`: parameters, expressions, units and dependencies.
- `geompype/vertices.py`: coordinate arrays and parameterized operations.
- `geompype/primitives.py`: the five filled primitives, Point and the six
  planar curve primitives.
- `geompype/library/`: one module per alignment mark or wafer outline;
  its fixed data are grouped in `geompype/library/data/`.
- `geompype/transforms.py`: `Array`, `Copy`, `Mirror`, `Move`, `Rotate` and `Scale`.
- `geompype/booleans.py`: filled planar `Union`, `Difference` and `Intersection`.
- `geompype/layer_operations.py`: operations on final layer objects.
- `geompype/operations.py`: Fillet, Chamfer, Offset and Thicken2D; `_planar.py`
  contains their KLayout outline calculations.
- `geompype/routing.py`: profiles, ports, constraints and connections;
  `_routing_path.py` contains segment and arc calculations.
- `geompype/components.py`: geometry groups and placement of their ports.
- `geompype/configuration.py`: YAML parameters, includes and variants.

Example imports are `from geompype.primitives import Square, Circle` and
`from geompype.transforms import Rotate`. All implemented shapes are also
available directly from `geompype`, as are `Project`, `Selection`, `Parameter`,
`DependentParameter` and `Vertices`. The entire library lives in `geompype/`.

## Geometry library

The [illustrated catalogue](./docs/LIBRARY.md) presents alignment marks and wafer
outlines, their dimensions and local coordinate systems, and a usage example.
Each element keeps its own file in
[geompype/library](./geompype/library/__init__.py), with imports from
`geompype.library` or directly from `geompype`.
The catalogue also explains [how to add a geometry](./docs/LIBRARY.md#add-a-geometry).

## Ports, connections and components

A `Port` is a position and a direction pointing out of a component. Its
`PortProfile` describes one or more bands: width, signed offset, layer and
name. A positive offset lies to the left of the port direction. A connection
leaves along the first port's direction and arrives against the second's.

```python
from geompype import Port, PortProfile, connect

profile = PortProfile.cpw(10, 6, metal, clearance)
start = Port(pos=(0, 0), orientation=(1, 0), profile=profile)
end = Port(pos=(1000, 300), orientation=(-1, 0), profile=profile)
wire = connect(start, end, radius=50, name="feedline")
print(wire.report())
```

Here, `metal` and `clearance` are two layers registered in the project.
The CPW profile contains a 10 µm-wide signal and a 22 µm-wide opening band
that includes the signal. Subtracting the ground plane and retaining the
signal are explicit fabrication operations. A third mask band can be added
with `mask_layer` and `mask_margin`.
For an off-centre multiband profile, `profile.with_mask(mask_layer, margin=10)`
adds a band covering the outer bounds of all bands, with a margin on each
side; its centre and width remain parameterized.

Port utilities use band names or zero-based indices:

| Call | Result |
| --- | --- |
| `port.normal` | Unit normal to the left of the direction. |
| `port.local_point(along=20, cross=5)` | A `Vertices` object in the port's coordinate system. |
| `port.track_center('signal')`, `port.track_edges('signal')` | Centre or pair of upper/lower edges as `Vertices`. |
| `port.bond_params()` | Numerical transverse bounds `(upper, lower)` in µm. |
| `port.split(['left', 'right'], gap=6, gap_layer=clearance)` | Separate CPW ports centred on the selected bands. |
| `port.draw_markers(layer=markers, tip_scale=0.5)` | Oriented triangular polygons, one per band; `bands=` selects a subset. |

`split` returns a tuple of views that follow the original port and are placed
through it. Select conducting bands explicitly to avoid also splitting an
enclosing mask. `gap` is the margin on each side; when omitted, it equals the
conductor width. `marker_triangles(...)` returns only the coordinates as
`Vertices`, without drawing. Returned coordinates retain their scalar
parameters and the coordinate system at the time of the call; drawn markers
and split ports recalculate their placement on each build. The marker layer
must belong to the same project and WorkPlane; it can be used for GDS only.

`wire.geometry['signal']` and `wire.geometry['gap']` are filled objects:
they accept transformations, Booleans and selections. COMSOL uses analytic
segments and arcs, followed by **Thicken2D**. KLayout uses a **DPath with
nonzero width**, converted to a polygon for these operations. The GDS grid
remains the project's grid, without Shapely.

- `via=[Port(...), ...]` specifies intermediate positions and tangents; these
  ports have no profile. Alternatively, `points=Vertices(...)` provides a
  complete polyline, including its endpoints; with a taper, it starts after
  the taper.
- `start_straight` and `end_straight` specify straight lengths after corner
  rounding. Ports must share an orthogonal coordinate system for automatic
  Manhattan routing; explicit points accept other angles.
- Two profiles with matching names/layers can have different widths or
  offsets. A linear taper is created at the start; `taper_slope` limits each
  edge's slope and determines its length.
- `meander_count`, `meander_amplitude` and `meander_offset` specify alternating
  excursions. The count is the number of lateral plateaus, and the amplitude
  is their distance from the axis. `meander_segment` selects a segment of the
  cleaned polyline; by default, the longest feasible segment is tried first.
  With `target_length`, a fixed count allows the amplitude to be calculated.
  When `meander_count` is omitted (or set to `None`), the router searches for
  the smallest feasible number of plateaus, up to 256, on a single segment.
  It tries the longest segments first. `meander_max_amplitude` bounds the
  amplitude around `meander_offset`, not the total extent of the bands.
  `meander_count=0` prevents adding a meander. This is an exact geometric
  line/arc length, not an electrical frequency.
- The requested radius is never reduced to make a bend fit. Crossing curves,
  collapsed offsets and impossible constraints produce an error.
  `obstacles=[...]` and `clearance=...` check the drawing on the project grid
  during validation/building. They do not trigger a search for a detour;
  a collision requires adjusting the waypoints.

For example, `connect(start, end, radius=50, target_length=2400,
meander_max_amplitude=400)` chooses the count and adjusts the amplitude to
the available space. `connection.report()` gives the selected
`meander_count` and `meander_amplitude_um`. A target that is too short or an
impossible constraint produces an error without reducing the requested radius.

`port.reversed()` (or `port.r`) reverses the direction and offsets while
following later movements of the original port. Position, width, radius and
amplitude parameters are read again on each `build()`. The Thicken2D width
remains a COMSOL expression; calculated routing coordinates are numerical.
A change made only in the COMSOL GUI therefore does not rerun Python routing.

`geompype.components` provides `Component`, which groups `geometry` and `ports`.
A group's own component recipes belong in its private library and use this
generic container.
`obj.copy_to(layer)` copies an individual object, with its parameters, to
another layer in the same project; COMSOL/GDS flags must match. This allows
masks to be built without including the other components on the source layer.
`move`, `rotate` and `place` move geometry and ports together, preserving port
instances for connections that have already been declared. Place the component
before consuming its outputs in a Boolean. Placement angles are currently
fixed numbers; dimensions and translations accept parameters. Circuit recipes
can be maintained in a separate package that depends on this generic library.
The external ports of a component containing internal connections must be
distinct instances from their internal endpoints: moving the component already
transforms those curves.

## YAML parameters

`load_config('parameters.yaml', name='sample')` reads YAML files with PyYAML,
without importing a drawing framework or executing YAML code.

```yaml
track: 12um
gap: 7um
launch: launch_parameters.yaml
resonator:
  radius: 60um
  count: 4
resonator__0:
  radius: 80um
```

Referenced `.yaml`/`.yml` filenames are resolved relative to the main file's
directory. Includes can contain a dictionary or a list of coordinates; cycles
are rejected. `config.child('resonator')` provides a subset that inherits
missing values from its parents. `config.variations('resonator')` applies
variants `__0`, `__1`, etc. in numerical order, with independent parameters
across variants.

Explicit quantities in `nm`, `um`, `µm`, `μm`, `mm`, `m`, `deg`, `rad` become
named `Parameter` objects. Change `config['track'].value`, then call
`project.build()`. The value remains in the parameter's unit: for
`track: 200nm`, assigning `250` means 250 nm. Counts, booleans and names remain
Python values; other physical units remain metadata strings. A key ending
in `__n` is literal. `raw(key)` returns a copy of the original data, and
`overrides={'resonator.radius': '90um'}` provides overrides without changing
the files. Changing a component count requires rebuilding the assembly;
the loader does not generate classes.

## Tests and development

Install development tools in the project environment:

```text
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

Here, `python` refers to that environment's interpreter. Offline tests check
parameters, geometry, the grid, GDS, examples and native expressions using
call recorders. COMSOL tests are skipped unless explicitly enabled.
The [installation guide](./docs/ENVIRONMENT.md) explains how to run them in
an interactive session that keeps the connection open.

Native coverage was checked with COMSOL 6.4. It checks entities, selections,
rebuilds after parameter changes and MPH readback. Curve tolerances, the
accuracy of COMSOL's measurement mesh and the GDS grid are handled separately.
KLayout is pinned to 0.30.1 for reproducible integer operations; changing this
version requires validation of the exported contours.

The [contribution guidelines](./docs/contributing.md) describe the organization,
useful checks and separation of personal recipes. The
[changelog](./docs/changelog.md) summarizes the public API. The
[references](./docs/references.md) connect geometry choices to the official APIs.
