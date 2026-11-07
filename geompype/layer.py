"""Layer settings shared by all its geometrical features."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Layer:
    """Logical geometry group and output settings within one workplane.

    ``selection`` is the automatically maintained FEM group of planar faces.
    ``selection_for(entity='edge')`` or ``'point'`` exposes other entity levels.
    These groups follow current layer ownership, not the history of copied objects.
    """

    name: str
    comsol: bool = True
    gds: bool = True
    gds_layer: int = 1
    gds_datatype: int = 0
    project: object = field(default=None, compare=False, repr=False)
    workplane: object = field(default=None, compare=False, repr=False)

    @property
    def selection(self):
        return self.selection_for(entity="boundary")

    def selection_for(self, *, entity="boundary"):
        """Return a stable derived selection; creating it does not connect COMSOL."""
        from .selection import _LayerSelection
        if self.project is None or self.project.layers.get(self.name) is not self:
            raise ValueError("Create layers with Project.add_layer to use their selections.")
        if entity not in ("boundary", "edge", "point"):
            raise ValueError("Planar layer selections support boundary, edge or point.")
        key = (self.name, entity)
        if key not in self.project._layer_selections:
            self.project._layer_selections[key] = _LayerSelection(self, entity)
        return self.project._layer_selections[key]

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("A layer needs a nonempty name.")
        if not isinstance(self.comsol, bool) or not isinstance(self.gds, bool):
            raise ValueError("The comsol and gds layer flags must be booleans.")
        for name in ("gds_layer", "gds_datatype"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 65535:
                raise ValueError(f"{name} must be an integer between 0 and 65535.")
