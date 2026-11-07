# Changelog

## 0.1.0 — Unreleased

Initial GeomPype package, with one Python geometry graph for COMSOL workplanes
and GDS masks through KLayout.

- Filled 2D primitives, points and construction curves; parameter expressions
  and editable coordinate arrays.
- Planar transforms and arrays with excluded sites; area Booleans, fillets,
  chamfers, offsets and symmetric thickening.
- Explicit per-corner tangent-trim limits on `Fillet`, with native COMSOL
  fillet groups and the same geometric rule for sampled GDS contours.
- Layer operations, named FEM selections and separate GDS files for multiple
  workplanes.
- Ports, multiband routing profiles, tapers, oriented waypoints, meanders,
  target lengths and obstacle-clearance checks.
- YAML parameter loading with includes, inheritance and explicit variants.
- Alignment marks and two-, three- and four-inch wafer outlines with one or
  two flats, each in its own library module.
- Public demonstration scripts and their YAML parameters grouped in `examples/`.
- Local COMSOL connection settings, offline/native checks,
  installation metadata and distribution exclusions for private/local files.

The [feature index](./docs/FEATURE_COVERAGE.md) identifies examples and limits.
Geometry generation is the scope; physics, meshing and simulation studies are
not created by the package.
