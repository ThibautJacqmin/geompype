"""Named FEM selections, independent of drawing layers."""


class Selection:
    """Group feature results at one entity level of the final 3D geometry.

    Membership refers to feature outputs, so COMSOL can propagate it through
    later transformations. GDS-only members remain Python metadata and are
    omitted from the COMSOL group. Members may belong to different workplanes
    in the same project. Creating a selection never connects to COMSOL.
    """

    def __init__(self, project, name, *, entity="boundary"):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("A selection needs a nonempty name.")
        if name in project.selections:
            raise ValueError(f"Selection {name!r} already exists.")
        dimensions = {"domain": 3, "boundary": 2, "edge": 1, "point": 0}
        if not isinstance(entity, str) or entity not in dimensions:
            raise ValueError("Selection.entity must be domain, boundary, edge, or point.")
        self.project = project
        self.name = name
        self.entity = entity
        self.dimension = dimensions[entity]
        self.tag = f"sel{len(project.selections) + 1}"
        project.selections[name] = self

    @property
    def members(self):
        """Explicit members; inherited membership is tracked by COMSOL."""
        return tuple(obj for obj in self.project.objects if self in obj.selections)

    def _validate_objects(self, objects):
        from .geometry import GeometryObject

        for obj in objects:
            if (not isinstance(obj, GeometryObject) or obj.project is not self.project
                    or obj not in self.project.objects):
                raise ValueError("Selection members must be registered objects of this project.")

    def add(self, *objects):
        """Add existing primitives or transforms; rebuild immediately in live mode."""
        self._validate_objects(objects)
        changed = False
        for obj in objects:
            if self not in obj.selections:
                obj.selections += (self,)
                changed = True
        if changed and self.project.live:
            self.project.build()
        return self

    def remove(self, *objects):
        """Remove direct membership; upstream selections may still propagate."""
        self._validate_objects(objects)
        changed = False
        for obj in objects:
            if self in obj.selections:
                obj.selections = tuple(group for group in obj.selections if group is not self)
                changed = True
        if changed and self.project.live:
            self.project.build()
        return self

    def to_comsol(self, component):
        """Union the native output selections, without storing entity numbers."""
        from jpype import JArray, JInt, JString

        inputs = []
        # Plane-geometry features have no componentSelection() of their own.
        # Each parent WorkPlane exposes its promoted selections in 3D. Cache
        # those lists locally so a group can span planes without repeated calls.
        plane_selections = {}
        for obj in self.members:
            if not obj.layer.comsol:
                continue
            plane = obj.layer.workplane
            if plane.tag not in plane_selections:
                workplane = plane.native
                if workplane is None:
                    raise RuntimeError(f"Build workplane {plane.name!r} before its selections.")
                prefix = f"{self.project.geometry.tag()}_{plane.tag}_"
                tags = [str(tag) for tag in workplane.componentSelection()]
                plane_selections[plane.tag] = prefix, tags
            prefix, tags = plane_selections[plane.tag]
            matches = [tag for tag in tags
                       if tag.startswith(f"{prefix}{obj.tag}_")
                       and component.selection(tag).dim() == self.dimension]
            if not matches:
                raise ValueError(
                    f"Selection {self.name!r}: {type(obj).__name__} {obj.tag} has no "
                    f"{self.entity} selection in the final 3D geometry. "
                    "Planar shapes provide boundaries, edges, and points, not volumes."
                )
            inputs.extend(matches)
        if self.tag not in list(component.selection().tags()):
            component.selection().create(self.tag, "Union")
        selection = component.selection(self.tag)
        selection.label(self.name)
        selection.set("entitydim", JInt(self.dimension))
        # An explicitly typed array also handles an empty group unambiguously.
        selection.set("input", JArray(JString)(list(dict.fromkeys(inputs))))

    def entities(self):
        """Read current COMSOL entity numbers after build(), for inspection only."""
        if self.project.model is None:
            raise RuntimeError("Build this selection in COMSOL before reading its entities.")
        component = self.project.model.java.component("comp1")
        if self.tag not in list(component.selection().tags()):
            raise RuntimeError("Build this selection in COMSOL before reading its entities.")
        return list(component.selection(self.tag).entities())


class _LayerSelection(Selection):
    """Derived ownership group, built after all workplane geometry operations.

    Native feature-result selections propagate into copied descendants. For a
    layer that would select geometry now owned by another layer. Instead an
    ExplicitSelection captures only the actual remaining object names, after
    the geometry operations. COMSOL then maps these entities through finalization.
    User-created Selection groups retain their existing propagation behavior.
    """

    def __init__(self, layer, entity):
        self.layer = layer
        self.project = layer.project
        self.entity = entity
        self.dimension = {"boundary": 2, "edge": 1, "point": 0}[entity]
        number = list(self.project.layers).index(layer.name)+1
        self.tag = f"lsel{number}_{self.dimension}"
        self.geometry_tag = f"lgeo{number}_{self.dimension}"
        suffix = "" if entity == "boundary" else f" ({entity})"
        plane_prefix = ("" if layer.workplane is self.project.default_workplane
                        else f"{layer.workplane.name} / ")
        self.name = f"Layer: {plane_prefix}{layer.name}{suffix}"

    @property
    def members(self):
        """Current terminal features assigned to this layer, including construction data."""
        return tuple(obj for obj in self.project._final_objects(self.project.objects)
                     if obj.layer is self.layer)

    def add(self, *objects):
        raise ValueError("Layer selections are automatic; use a user Selection for custom membership.")

    def remove(self, *objects):
        raise ValueError("Layer selections are automatic; use a user Selection for custom membership.")

    def remove_comsol(self, geometry):
        """Remove the old capture before new operations can be appended after it."""
        if self.geometry_tag in list(geometry.feature().tags()):
            geometry.feature().remove(self.geometry_tag)

    def prepare_comsol(self, geometry):
        """Capture the requested entities of currently owned native objects."""
        from jpype import JInt
        if not self.layer.comsol or not self.members:
            return
        feature = geometry.create(self.geometry_tag, "ExplicitSelection")
        feature.label(self.name)
        feature.set("selshow", "on")
        selection = feature.selection("selection")
        selection.init(JInt(self.dimension))
        for source in self.members:
            for name in geometry.feature(source.tag).objectNames():
                counts = geometry.obj(name).getNEntities()
                if self.dimension < len(counts) and counts[self.dimension] > 0:
                    selection.all(str(name))

    def to_comsol(self, component):
        """Publish this plane's ownership group in the final 3D geometry."""
        from jpype import JArray, JInt, JString
        if not self.layer.comsol:
            return
        plane = self.layer.workplane
        if plane.native is None:
            raise RuntimeError(f"Build workplane {plane.name!r} before its selections.")
        matches = []
        if self.members:
            prefix = f"{self.project.geometry.tag()}_{plane.tag}_{self.geometry_tag}"
            tags = [str(tag) for tag in plane.native.componentSelection()]
            matches = [tag for tag in tags if (tag == prefix or tag.startswith(prefix+"_"))
                       and component.selection(tag).dim() == self.dimension]
            if not matches:
                raise RuntimeError(f"COMSOL did not expose the automatic selection for layer {self.layer.name!r}.")
        # A wholly empty plane cannot host an ExplicitSelection in COMSOL.
        # Its stable component group is simply an empty Union until populated.
        if self.tag not in list(component.selection().tags()):
            component.selection().create(self.tag, "Union")
        selection = component.selection(self.tag)
        selection.label(self.name)
        selection.set("entitydim", JInt(self.dimension))
        selection.set("input", JArray(JString)(matches))
