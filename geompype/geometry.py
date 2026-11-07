"""Common base for geometrical features."""

from .selection import Selection


class GeometryObject:
    """Common project/layer ownership for geometry objects."""

    def __init__(self, project, layer, *, selections=()):
        if project.layers.get(layer.name) is not layer:
            raise ValueError("The layer must belong to this project.")
        self.project = project
        self.layer = layer
        self.inputs = ()
        self.keep = False
        self.tag = None
        self.selections = tuple(selections)
        self.validate_selections()
        self.selections = tuple(dict.fromkeys(self.selections))

    def validate_selections(self):
        for selection in self.selections:
            if (not isinstance(selection, Selection) or selection.project is not self.project
                    or self.project.selections.get(selection.name) is not selection):
                raise ValueError("Object selections must belong to this project.")

    def rotate(self, *, angle=0, origin=(0, 0), keep=False,
               selections=(), propagate_selections=True):
        """Return a new Rotate feature in the same project and layer."""
        from .transforms import Rotate
        return Rotate(self, angle=angle, origin=origin, keep=keep,
                      selections=selections, propagate_selections=propagate_selections)

    def parameter_values(self):
        """Scalar inputs to inspect for named parameters and dependencies."""
        return ()

    def consumed_inputs(self):
        """Inputs replaced by this feature; Difference retains each side separately."""
        return () if self.keep else self.inputs

    def union(self, *others, keep=False, interior_boundaries=True, selections=(),
              propagate_selections=True):
        """Union filled operands on this layer; keep=True also retains the inputs."""
        from .booleans import Union
        return Union((self, *others), keep=keep, interior_boundaries=interior_boundaries,
                     selections=selections, propagate_selections=propagate_selections)

    def difference(self, tools, *, keep_base=False, keep_tools=False,
                   interior_boundaries=True, selections=(), propagate_selections=True):
        """Subtract same-layer tools; retain base/tools only with their keep flags."""
        from .booleans import Difference
        return Difference(self, tools, keep_base=keep_base, keep_tools=keep_tools,
                          interior_boundaries=interior_boundaries, selections=selections,
                          propagate_selections=propagate_selections)

    def intersection(self, *others, keep=False, interior_boundaries=True,
                     selections=(), propagate_selections=True):
        """Intersect filled operands on this layer, replacing inputs unless kept."""
        from .booleans import Intersection
        return Intersection((self, *others), keep=keep,
                            interior_boundaries=interior_boundaries,
                            selections=selections, propagate_selections=propagate_selections)

    def move(self, *, delta=(0, 0), selections=(), propagate_selections=True):
        """Translate this object; the Move feature replaces its input."""
        from .transforms import Move
        return Move(self, delta=delta, selections=selections,
                    propagate_selections=propagate_selections)

    def copy(self, *, delta=(0, 0), selections=(), propagate_selections=True):
        """Make translated copies while retaining this object."""
        from .transforms import Copy
        return Copy(self, delta=delta, selections=selections,
                    propagate_selections=propagate_selections)

    def copy_to(self, layer, *, delta=(0, 0), selections=(), propagate_selections=True):
        """Copy this feature to another layer, retaining its parameters and source.

        Unlike Project.copy_layer, this copies only this object's outputs. It
        is useful for component-local mask and keepout operations. Both layers
        must belong to this project and the same workplane, and use the same
        COMSOL/GDS flags. It does not transfer geometry between physical planes.
        """
        from .layer_operations import ObjectLayerCopy
        return ObjectLayerCopy(self, output=layer, delta=delta, selections=selections,
                               propagate_selections=propagate_selections)

    def mirror(self, *, normal=(1, 0), origin=(0, 0), keep=False,
               selections=(), propagate_selections=True):
        """Reflect about the line through origin perpendicular to normal."""
        from .transforms import Mirror
        return Mirror(self, normal=normal, origin=origin, keep=keep,
                      selections=selections, propagate_selections=propagate_selections)

    def scale(self, *, factor=1, origin=(0, 0), keep=False,
              selections=(), propagate_selections=True):
        """Scale around origin using one factor or separate x/y factors."""
        from .transforms import Scale
        return Scale(self, factor=factor, origin=origin, keep=keep,
                     selections=selections, propagate_selections=propagate_selections)

    def array(self, *, size=1, displacement=(1, 1), exclude=(), selections=(),
              propagate_selections=True):
        """Repeat this object, optionally excluding zero-based indices or (x, y) sites."""
        from .transforms import Array
        return Array(self, size=size, displacement=displacement, exclude=exclude,
                     selections=selections, propagate_selections=propagate_selections)

    def to_comsol(self, workplane_geometry, tag):
        """Create the feature in the 2D workplane of the project's 3D geometry."""
        raise NotImplementedError

    def fillet(self, *, radius, corners=None, tolerance=0.001, max_trim_fraction=None,
               selections=()):
        """Round all corners, or corners selected by their coordinates."""
        from .operations import Fillet
        return Fillet(self, radius=radius, corners=corners, tolerance=tolerance,
                      max_trim_fraction=max_trim_fraction, selections=selections)

    def chamfer(self, *, distance, corners=None, selections=()):
        """Bevel corners by equal distances along both incident edges."""
        from .operations import Chamfer
        return Chamfer(self, distance=distance, corners=corners, selections=selections)

    def offset(self, *, distance, reverse=False, corner="fillet", tolerance=0.001,
               keep=False, selections=(), propagate_selections=True):
        """Grow a shape or move a curve left by a nonnegative distance in um.

        reverse=True shrinks shapes or moves curves right. See Offset for
        corner handling and the supported contour types.
        """
        from .operations import Offset
        return Offset(self, distance=distance, reverse=reverse, corner=corner,
                      tolerance=tolerance, keep=keep, selections=selections,
                      propagate_selections=propagate_selections)

    def thicken(self, *, width, ends="straight", corner="fillet", tolerance=0.001,
                keep=False, selections=(), propagate_selections=True):
        """Return a filled band of total width in um around the input boundary.

        Thickening is symmetric around curves or filled-shape contours. See
        Thicken2D for cap/join options; the input is consumed unless keep=True.
        """
        from .operations import Thicken2D
        return Thicken2D(self, width=width, ends=ends, corner=corner,
                         tolerance=tolerance, keep=keep, selections=selections,
                         propagate_selections=propagate_selections)

    def to_klayout(self):
        """Return DPoint, zero-width DPath or filled DPolygon geometry in um.

        Features producing multiple objects return a flat tuple of geometries.

        Boolean operands and final exports use the project's GDS grid; points
        are kept as coordinates and do not create GDS marker shapes.
        """
        raise NotImplementedError
