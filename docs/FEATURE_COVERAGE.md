# Public geometry and example coverage

The [README](guide.md) is the API guide.
The illustrated [geometry catalogue](LIBRARY.md) presents reusable marks,
wafer outlines and how to contribute an element.
The [environment guide](ENVIRONMENT.md) explains how to run the checks.

| Capability | Public examples |
| --- | --- |
| Filled square, rectangle, disk, ellipse and polygon | [Primitives](../examples/example_primitives.py), [combined gallery](../examples/example_all_features.py) |
| Point, segment, arc, quadratic/cubic Bézier, interpolation and parametric curves | [Curves](../examples/example_curves.py) |
| Curved interpolation with an explicit sampler and finite-width Bézier track | [Curved tracks](../examples/example_curved_tracks.py) |
| Parameters, units and coordinate expressions | [Parameters](../examples/example_parameters.py), [Vertices](../examples/example_vertices.py), [grid](../examples/example_grid.py) |
| Copy, move, rotate, mirror, scale and arrays | [Transforms](../examples/example_transforms.py), [array exclusions](../examples/example_array_exclusions.py) |
| Area Booleans and combinations with transforms | [Booleans](../examples/example_booleans.py), [combined operations](../examples/example_boolean_transforms.py) |
| Fillet, Chamfer, Offset and symmetric Thicken2D | [Planar operations](../examples/example_planar_operations.py) |
| Layer operations and named native selections | [Layers](../examples/example_layers.py), [selections](../examples/example_selections.py) |
| Separate physical drawing planes and separate GDS files | [Workplanes](../examples/example_workplanes.py) |
| X/diamond, cross, L, box-in-box and two-layer x/y verniers | [Mark gallery](../examples/example_library_marks.py), [wafer and marks](../examples/example_library.py) |
| Two-, three- and four-inch wafer outlines, each with one or two flats | [Wafer gallery](../examples/example_library_wafers.py) |
| CPW profiles, tapered connections and prescribed meanders | [Routing](../examples/example_routing.py) |
| Port splitting/markers, general masks and automatic target length | [Routing utilities](../examples/example_routing_utilities.py) |
| Asymmetric bands, target length and obstacle clearance | [Routing constraints](../examples/example_routing_constraints.py) |

Circuit-specific recipes can live in separately installed packages. Their
parameters, examples and tests belong with those packages.

Library elements each have a module in [geompype/library](../geompype/library/__init__.py).
Mark dimensions can retain Parameters. Wafer outline options are fixed at
construction; their placement and scaling can retain Parameters. The 4-inch
template uses a nominal 100 mm diameter. Flat positions are explicit geometry,
without a crystal-orientation or doping convention.

## Limits that remain deliberate

- Geometry only: no physics interfaces, materials, meshing, studies or solvers.
  Workplanes are XY-parallel with in-plane rotation; general 3D solids are deferred.
- Tangent, CompositeCurve and general arbitrary-profile planar sweeps are not
  implemented. Thicken2D is symmetric; arbitrary one-sided band placement is
  available through route profile offsets, not asymmetric Thicken2D arguments.
- Curve solid/closed modes and some join/trim options are not implemented.
  Circle is a full disk; native-only circle sectors are not offered.
- Parameter arithmetic is intentionally small; general symbolic powers/trig
  functions are not provided. ParametricCurve's explicit native expressions
  and Python sampler are a separate API.
- Obstacle checks reject collisions and insufficient clearance. The router
  does not search arbitrary obstacle mazes. Automatic meanders use one segment
  and a bounded count search; geometric length does not predict resonance.
- Curve sampling, native CAD behavior and GDS grid conversion are checked
  separately. A custom interpolation sampler requires native agreement checks.
