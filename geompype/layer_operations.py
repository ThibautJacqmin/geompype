"""Operations on the current contents of logical layers in one workplane.

The source members are captured when the operation is created. Their geometry
and parameters remain live; objects added to a source layer afterwards are not
retroactively included. Outputs belong to an explicitly chosen layer.
"""

from .booleans import _Boolean, _is_filled
from .geometry import GeometryObject
from .layer import Layer
from .transforms import Copy
from .vertices import Vertices


def _layer(project, value):
    if isinstance(value, str):
        try:
            value = project.layers[value]
        except KeyError as error:
            raise ValueError(f"Unknown layer {value!r}.") from error
    if not isinstance(value, Layer) or project.layers.get(value.name) is not value:
        raise ValueError("Layer operations require layers registered in this project.")
    return value


def _groups(project, layers, output):
    output = _layer(project, output)
    if isinstance(layers, (Layer, str)):
        layers = (layers,)
    else:
        try:
            layers = tuple(layers)
        except TypeError as error:
            raise TypeError("Supply a layer or a sequence of layers.") from error
    layers = tuple(_layer(project, value) for value in layers)
    if not layers:
        raise ValueError("At least one source layer is required.")
    if len({id(layer) for layer in layers}) != len(layers):
        raise ValueError("Source layers must not contain duplicates.")
    final = project._final_objects(project.objects)
    groups = tuple(tuple(obj for obj in final if obj.layer is layer) for layer in layers)
    for layer, group in zip(layers, groups):
        if not group:
            raise ValueError(f"Source layer {layer.name!r} has no remaining geometry.")
        if (layer.comsol, layer.gds) != (output.comsol, output.gds):
            raise ValueError("Source and output layers must have matching COMSOL/GDS flags.")
        if layer.workplane is not output.workplane:
            raise ValueError("Planar layer operations require source and output layers on the same workplane.")
    return output, layers, groups


def _validate_sources(operation):
    if operation.project.layers.get(operation.layer.name) is not operation.layer:
        raise ValueError("The output layer must belong to this project.")
    for layer, group in zip(operation.source_layers, operation.groups):
        if operation.project.layers.get(layer.name) is not layer:
            raise ValueError("Source layers must belong to this project.")
        if (layer.comsol, layer.gds) != (operation.layer.comsol, operation.layer.gds):
            raise ValueError("Source and output layers must have matching COMSOL/GDS flags.")
        if layer.workplane is not operation.layer.workplane:
            raise ValueError("Planar layer operations require source and output layers on the same workplane.")
        if any(obj.project is not operation.project or obj.layer is not layer for obj in group):
            raise ValueError("Layer operation inputs must remain on their original source layers.")
    if tuple(obj for group in operation.groups for obj in group) != operation.inputs:
        raise ValueError("Layer operation inputs must match their captured source groups.")


class _LayerBoolean(_Boolean):
    """Use the existing Boolean emitter with explicit cross-layer ownership."""

    _cross_layer = True
    _area_output = True

    def __init__(self, project, layers, *, output, keep=False, interior_boundaries=True,
                 selections=(), propagate_selections=True):
        output, self.source_layers, self.groups = _groups(project, layers, output)
        GeometryObject.__init__(self, project, output, selections=selections)
        self.inputs = tuple(obj for group in self.groups for obj in group)
        self.keep = keep
        self.interior_boundaries = interior_boundaries
        self.propagate_selections = propagate_selections

    def validate(self):
        _validate_sources(self)
        for name in ("keep", "interior_boundaries", "propagate_selections"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{type(self).__name__}.{name} must be a boolean.")
        if any(not _is_filled(source) for source in self.inputs):
            raise TypeError("Layer Booleans require filled shapes; thicken curves before combining areas.")

    def _group_region(self, group):
        import klayout.db as kdb
        result = kdb.Region()
        for source in group:
            result += self._region(source)
        return result.merged()


class LayerUnion(_LayerBoolean):
    """Merge the current filled contents of one or more layers."""

    tag_prefix = "luni"

    def __init__(self, project, layers, *, output, keep=False, interior_boundaries=True,
                 selections=(), propagate_selections=True):
        super().__init__(project, layers, output=output, keep=keep,
                         interior_boundaries=interior_boundaries, selections=selections,
                         propagate_selections=propagate_selections)
        self.validate()
        project.add(self)

    def to_comsol(self, geometry, tag):
        feature = self._feature(geometry, tag, "Union")
        feature.selection("input").set([source.tag for source in self.inputs])
        feature.set("keep", "on" if self.keep else "off")

    def to_klayout(self):
        return self._result(self._group_region(self.inputs))


class LayerDifference(_LayerBoolean):
    """Subtract the union of tool layers from the union of base layers."""

    tag_prefix = "ldif"

    def __init__(self, project, base, tools, *, output, keep_base=False, keep_tools=False,
                 interior_boundaries=True, selections=(), propagate_selections=True):
        _, base_layers, base_groups = _groups(project, base, output)
        _, tool_layers, tool_groups = _groups(project, tools, output)
        self.bases = tuple(obj for group in base_groups for obj in group)
        self.tools = tuple(obj for group in tool_groups for obj in group)
        self.keep_base, self.keep_tools = keep_base, keep_tools
        super().__init__(project, (*base_layers, *tool_layers), output=output,
                         interior_boundaries=interior_boundaries, selections=selections,
                         propagate_selections=propagate_selections)
        self.validate()
        project.add(self)

    def validate(self):
        super().validate()
        if self.keep:
            raise ValueError("LayerDifference uses keep_base and keep_tools instead of keep.")
        if not isinstance(self.keep_base, bool) or not isinstance(self.keep_tools, bool):
            raise ValueError("keep_base and keep_tools must be booleans.")
        if (*self.bases, *self.tools) != self.inputs:
            raise ValueError("Base/tool inputs must match the captured layer contents.")

    def consumed_inputs(self):
        return (() if self.keep_base else self.bases) + (() if self.keep_tools else self.tools)

    def to_comsol(self, geometry, tag):
        feature = self._feature(geometry, tag, "Difference")
        feature.selection("input").set([source.tag for source in self.bases])
        feature.selection("input2").set([source.tag for source in self.tools])
        feature.set("keepadd", "on" if self.keep_base else "off")
        feature.set("keepsubtract", "on" if self.keep_tools else "off")

    def to_klayout(self):
        return self._result(self._group_region(self.bases) - self._group_region(self.tools))


class LayerIntersection(_LayerBoolean):
    """Intersect each layer's combined footprint, including arrays and islands."""

    tag_prefix = "lint"

    def __init__(self, project, layers, *, output, keep=False, interior_boundaries=True,
                 selections=(), propagate_selections=True):
        super().__init__(project, layers, output=output, keep=keep,
                         interior_boundaries=interior_boundaries, selections=selections,
                         propagate_selections=propagate_selections)
        self.validate()
        project.add(self)

    def validate(self):
        super().validate()
        if len(self.groups) < 2:
            raise ValueError("Layer intersection requires at least two distinct source layers.")

    def to_comsol(self, geometry, tag):
        # Each helper union is a single set, even for an array or disjoint
        # islands. Intersecting every source object directly would erase them.
        helpers = []
        for index, group in enumerate(self.groups, 1):
            helper_tag = f"{tag}g{index}"
            helper = self._feature(geometry, helper_tag, "Union")
            helper.label(f"{self.source_layers[index-1].name}: intersection input")
            helper.selection("input").set([source.tag for source in group])
            helper.set("keep", "on" if self.keep else "off")
            helpers.append(helper_tag)
        feature = self._feature(geometry, tag, "Intersection")
        feature.selection("input").set(helpers)
        feature.set("keep", "off")  # Helpers never remain as exported geometry.
        feature.set("keeplowerdim", "off")

    def to_klayout(self):
        result = self._group_region(self.groups[0])
        for group in self.groups[1:]:
            result &= self._group_region(group)
        return self._result(result)


class LayerCopy(Copy):
    """Copy all current source-layer objects, preserving curves and points too."""

    tag_prefix = "lcpy"
    _cross_layer = True

    def __init__(self, project, source, *, output, delta=(0, 0), selections=(),
                 propagate_selections=True):
        if not isinstance(source, (Layer, str)):
            raise TypeError("copy_layer expects one source layer.")
        output, self.source_layers, self.groups = _groups(project, source, output)
        GeometryObject.__init__(self, project, output, selections=selections)
        self.inputs = self.groups[0]
        self.keep = True
        self.propagate_selections = propagate_selections
        self.delta = delta if isinstance(delta, Vertices) else Vertices(delta)
        self.validate()
        project.add(self)

    def validate(self):
        _validate_sources(self)
        if self.keep is not True:
            raise ValueError("LayerCopy always keeps its source objects.")
        if not isinstance(self.propagate_selections, bool):
            raise ValueError("propagate_selections must be a boolean.")
        self._displacements().validate()
        if len(self._displacements()) == 0:
            raise ValueError("LayerCopy requires at least one displacement.")


class ObjectLayerCopy(LayerCopy):
    """The same native copy, restricted to one feature's outputs."""

    def __init__(self, target, *, output, delta=(0, 0), selections=(),
                 propagate_selections=True):
        output = _layer(target.project, output)
        GeometryObject.__init__(self,target.project,output,selections=selections)
        self.source_layers = (target.layer,)
        self.groups = ((target,),)
        self.inputs = (target,)
        self.keep = True
        self.propagate_selections = propagate_selections
        self.delta = delta if isinstance(delta,Vertices) else Vertices(delta)
        self.validate()
        self.project.add(self)
