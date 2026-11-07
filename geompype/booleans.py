"""Filled planar Boolean operations, native in COMSOL and grid-based in KLayout.

KLayout Regions operate on Project.dbu. Each Boolean therefore introduces a
grid conversion before its calculation; transforms themselves retain doubles.
"""

from math import prod

from .geometry import GeometryObject
from .primitives import Circle, Ellipse, Polygon, Rectangle, Square
from .transforms import Array, Move, Rotate, _Transform, _values

__all__ = ["Union", "Difference", "Intersection"]


def _members(value):
    if isinstance(value, GeometryObject):
        return (value,)
    try:
        result = tuple(value)
    except TypeError as error:
        raise TypeError("Boolean inputs must be geometry objects.") from error
    if not result or any(not isinstance(obj, GeometryObject) for obj in result):
        raise TypeError("Boolean operations require one or more geometry objects.")
    return result


def _is_filled(obj):
    """Check semantic dimensions without sampling a COMSOL-only curve."""
    if hasattr(obj, "_area_output"):
        return obj._area_output
    if isinstance(obj, (Square, Rectangle, Circle, Ellipse, Polygon, _Boolean)):
        return True
    return isinstance(obj, _Transform) and all(_is_filled(source) for source in obj.inputs)


def _multiple_objects(obj):
    """Whether a feature emits several native objects, rather than one set."""
    if isinstance(obj, _Boolean):
        return False
    if not isinstance(obj, _Transform):
        return False
    if len(obj.inputs) > 1 or any(_multiple_objects(source) for source in obj.inputs):
        return True
    if isinstance(obj, Array):
        return prod(obj._counts()) > 1
    if isinstance(obj, Rotate):
        return len(_values(obj.angle)) > 1
    if isinstance(obj, Move):
        return len(obj._displacements()) > 1
    return False


class _Boolean(GeometryObject):
    """Shared input ownership and native options for filled operations."""

    def __init__(self, inputs, *, keep=False, interior_boundaries=True,
                 selections=(), propagate_selections=True):
        members = _members(inputs)
        super().__init__(members[0].project, members[0].layer, selections=selections)
        self.inputs = members
        self.keep = keep
        self.interior_boundaries = interior_boundaries
        self.propagate_selections = propagate_selections

    def validate(self):
        for name in ("keep", "interior_boundaries", "propagate_selections"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{type(self).__name__}.{name} must be a boolean.")
        if len(set(self.inputs)) != len(self.inputs):
            raise ValueError("Boolean inputs must not contain duplicates.")
        for source in self.inputs:
            if source.project is not self.project or source.layer is not self.layer:
                raise ValueError("Boolean inputs must share their project and layer.")
            if not _is_filled(source):
                raise TypeError("Area Boolean operations require filled shapes; points and curves are unsupported.")

    def _feature(self, geometry, tag, kind):
        if tag not in list(geometry.feature().tags()):
            geometry.create(tag, kind)
        feature = geometry.feature(tag)
        feature.label(f"{self.layer.name}: {tag}")
        feature.set("intbnd", "on" if self.interior_boundaries else "off")
        feature.set("propagatesel", "on" if self.propagate_selections else "off")
        return feature

    def _region(self, source):
        return self.project._boolean_region(source.to_klayout(), self, source)

    def _result(self, region):
        # Region may contain holes, disconnected polygons or no polygons.
        result = tuple(polygon.to_dtype(self.project.dbu) for polygon in region.each_merged())
        return result[0] if len(result) == 1 else result


class Union(_Boolean):
    """Unite one or more filled features, including all outputs of an array.

    COMSOL can preserve interior boundaries; GDS stores the occupied footprint.
    """

    tag_prefix = "uni"

    def __init__(self, inputs, *, keep=False, interior_boundaries=True,
                 selections=(), propagate_selections=True):
        super().__init__(inputs, keep=keep, interior_boundaries=interior_boundaries,
                         selections=selections, propagate_selections=propagate_selections)
        self.validate()
        self.project.add(self)

    def to_comsol(self, workplane_geometry, tag):
        feature = self._feature(workplane_geometry, tag, "Union")
        feature.selection("input").set([source.tag for source in self.inputs])
        feature.set("keep", "on" if self.keep else "off")

    def to_klayout(self):
        import klayout.db as kdb

        result = kdb.Region()
        for source in self.inputs:
            result += self._region(source)
        result.merge()
        return self._result(result)


class Difference(_Boolean):
    """Subtract the union of tools from the union of base objects.

    Base and tools each accept one feature or an iterable of features.
    keep_base and keep_tools independently retain their original objects.
    """

    tag_prefix = "dif"

    def __init__(self, base, tools, *, keep_base=False, keep_tools=False,
                 interior_boundaries=True, selections=(), propagate_selections=True):
        self.bases = _members(base)
        self.tools = _members(tools)
        self.keep_base = keep_base
        self.keep_tools = keep_tools
        super().__init__((*self.bases, *self.tools), interior_boundaries=interior_boundaries,
                         selections=selections, propagate_selections=propagate_selections)
        self.validate()
        self.project.add(self)

    @property
    def base(self):
        return self.bases[0] if len(self.bases) == 1 else self.bases

    def validate(self):
        super().validate()
        if self.keep:
            raise ValueError("Difference uses keep_base and keep_tools instead of keep.")
        if not isinstance(self.keep_base, bool) or not isinstance(self.keep_tools, bool):
            raise ValueError("Difference.keep_base and keep_tools must be booleans.")

    def consumed_inputs(self):
        return (() if self.keep_base else self.bases) + (() if self.keep_tools else self.tools)

    def to_comsol(self, workplane_geometry, tag):
        feature = self._feature(workplane_geometry, tag, "Difference")
        feature.selection("input").set([source.tag for source in self.bases])
        feature.selection("input2").set([source.tag for source in self.tools])
        feature.set("keepadd", "on" if self.keep_base else "off")
        feature.set("keepsubtract", "on" if self.keep_tools else "off")

    def to_klayout(self):
        import klayout.db as kdb

        base, tools = kdb.Region(), kdb.Region()
        for source in self.bases:
            base += self._region(source)
        for source in self.tools:
            tools += self._region(source)
        return self._result(base - tools)


class Intersection(_Boolean):
    """Intersect filled sets; lower-dimensional contacts produce no area.

    Wrap an array or other multiple-object feature in Union first to intersect
    its combined footprint with a mask. This makes the native COMSOL grouping
    explicit instead of intersecting the array elements with one another.
    """

    tag_prefix = "int"

    def __init__(self, inputs, *, keep=False, interior_boundaries=True,
                 selections=(), propagate_selections=True):
        super().__init__(inputs, keep=keep, interior_boundaries=interior_boundaries,
                         selections=selections, propagate_selections=propagate_selections)
        self.validate()
        self.project.add(self)

    def validate(self):
        super().validate()
        if any(_multiple_objects(source) for source in self.inputs):
            raise ValueError("Intersection operands must each be one set; use Union(array) for multiple outputs.")

    def to_comsol(self, workplane_geometry, tag):
        feature = self._feature(workplane_geometry, tag, "Intersection")
        feature.selection("input").set([source.tag for source in self.inputs])
        feature.set("keep", "on" if self.keep else "off")
        feature.set("keeplowerdim", "off")

    def to_klayout(self):
        result = self._region(self.inputs[0])
        for source in self.inputs[1:]:
            result &= self._region(source)
        return self._result(result)
