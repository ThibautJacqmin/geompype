"""Build the same simple objects in COMSOL and KLayout."""

from copy import deepcopy
from math import isfinite, ulp
from pathlib import Path
import os
import shutil
import subprocess

from ._comsol import get_client
from ._comsol_config import server_settings
from .layer import Layer
from .parameters import DependentParameter, Parameter, collect_parameters
from .selection import Selection
from .workplane import WorkPlane

_viewers = {}


class Project:
    """Draw in named workplanes inside one 3D COMSOL geometry.

    ``live=False`` waits for an explicit build().

    Lengths and ``dbu`` are in um. The default GDS grid is 0.001 um (1 nm).
    ``grid_policy='round'`` rounds Region operands and final GDS coordinates;
    ``'error'`` rejects off-grid conversion inputs, allowing floating-point noise.
    Region's internal integer intersection calculations are not exact predicates
    on the original floating geometry and are not measured by the grid report.
    Neither policy changes parameters or native COMSOL geometry.
    Projects reuse one MPh connection within the Python session.
    Omitted ``host``/``port`` use GEOMPYPE_COMSOL_HOST/PORT, then the local
    ``comsol.local.json`` in the working directory, then localhost:2036.
    Explicit arguments override these settings. An existing MPh ``client``
    bypasses them entirely. Construction validates settings without connecting;
    a COMSOL-enabled build connects when needed.
    The project never clears existing COMSOL models or stops the server.
    """

    def __init__(self, *, live=False, output="output/square", dbu=0.001,
                 grid_policy="round",
                 host=None, port=None, client=None):
        self.live = bool(live)
        self.output = Path(output).resolve()
        self._mph_path = self.output.with_suffix(".mph")
        self.dbu = dbu
        self.grid_policy = grid_policy
        self._validate_grid()
        self._grid_report = None
        self._collect_grid = False
        self.host, self.port = ((client.host, client.port) if client is not None
                               else server_settings(host, port))
        self.layers = {}
        self.selections = {}
        self._layer_selections = {}
        self.objects = []
        self._explicit_parameters = []
        self.client = client
        self.model = None
        self.geometry = None
        self.workplane = None  # Native default WorkPlane, retained for compatibility.
        self.workplanes = {}
        self.default_workplane = self.add_workplane('default')
        self.layout = None
        self._gui_processes = _viewers.setdefault((self.output, self.host, self.port), {})

    @property
    def gds_path(self):
        return self.output.with_suffix(".gds")

    @property
    def mph_path(self):
        """Actual saved path; a numbered name is used if another model holds the file."""
        return self._mph_path

    @property
    def parameters(self):
        """Used and explicitly registered parameters, dependencies before dependants.

        The returned dictionary is rebuilt from the current object attributes.
        Change a parameter's value, then call build(), including in live mode.
        """
        return self._parameters_for(self.objects)

    def _parameters_for(self, objects, extra=(), *, workplanes=None):
        values = list(self._explicit_parameters) + list(extra)
        planes = self.workplanes.values() if workplanes is None else workplanes
        values.extend(value for plane in planes for value in plane.parameter_values())
        values.extend(value for obj in objects for value in obj.parameter_values())
        return collect_parameters(values)

    def add_parameter(self, parameter):
        """Include a named parameter even when no geometry refers to it yet.

        Dependencies are included too. Registration does not connect to COMSOL;
        the definition is sent at build(), when a COMSOL layer is enabled.
        """
        if not isinstance(parameter, (Parameter, DependentParameter)):
            raise TypeError("add_parameter expects a named Parameter or DependentParameter.")
        self._parameters_for(self.objects, extra=(parameter,))
        parameter.definition  # Validate before changing the registry.
        if parameter not in self._explicit_parameters:
            self._explicit_parameters.append(parameter)
        return parameter

    def add_workplane(self, name, *, position=(0, 0, 0), angle=0):
        """Declare an XY-parallel drawing; its placement applies only in COMSOL.

        Each drawing exports a separate GDS file in its local coordinates.
        Names are identifiers and unique ignoring case, for portable filenames.
        This declaration does not connect to COMSOL or build geometry.
        """
        plane = WorkPlane(self, name, f'wp{len(self.workplanes)+1}', position=position, angle=angle)
        if any(existing.casefold() == name.casefold() for existing in self.workplanes):
            raise ValueError(f'Workplane {name!r} already exists.')
        self._parameters_for(self.objects, extra=plane.parameter_values())
        self.workplanes[name] = plane
        return plane

    def _workplane(self, value):
        if value is None:
            return self.default_workplane
        if isinstance(value, str):
            try:
                value = self.workplanes[value]
            except KeyError as error:
                raise ValueError(f'Unknown workplane {value!r}.') from error
        if (not isinstance(value, WorkPlane) or value.project is not self
                or self.workplanes.get(value.name) is not value):
            raise ValueError('A layer workplane must be registered in this project.')
        return value

    def add_layer(self, name, *, comsol=True, gds=True,
                  gds_layer=1, gds_datatype=0, workplane=None):
        """Add a globally named layer to the default or a specified workplane."""
        if name in self.layers:
            raise ValueError(f"Layer {name!r} already exists.")
        plane = self._workplane(workplane)
        layer = Layer(name, comsol, gds, gds_layer, gds_datatype, project=self, workplane=plane)
        self.layers[name] = layer
        layer.selection  # Stable default FEM group, even when the layer is empty.
        return layer

    def merge_layers(self, layers, *, output, keep=False, interior_boundaries=True,
                     selections=(), propagate_selections=True):
        """Union the current filled geometry of layers into an explicit output layer.

        Layers can be registered Layer objects or their names. Inputs are the
        currently available features at this call, not geometry added later.
        Their parameters remain live. keep=True retains the source features.
        """
        from .layer_operations import LayerUnion
        return LayerUnion(self, layers, output=output, keep=keep,
                          interior_boundaries=interior_boundaries, selections=selections,
                          propagate_selections=propagate_selections)

    def subtract_layers(self, base, tools, *, output, keep_base=False, keep_tools=False,
                        interior_boundaries=True, selections=(), propagate_selections=True):
        """Subtract the union of tool layers from the union of base layers.

        Each side accepts one layer or several layers. Source retention is
        controlled independently for base and tools. The result belongs to output.
        """
        from .layer_operations import LayerDifference
        return LayerDifference(self, base, tools, output=output, keep_base=keep_base,
                               keep_tools=keep_tools, interior_boundaries=interior_boundaries,
                               selections=selections, propagate_selections=propagate_selections)

    def intersect_layers(self, layers, *, output, keep=False, interior_boundaries=True,
                         selections=(), propagate_selections=True):
        """Intersect each layer's combined filled footprint with the other layers.

        A layer containing several shapes is one operand, including array outputs.
        """
        from .layer_operations import LayerIntersection
        return LayerIntersection(self, layers, output=output, keep=keep,
                                 interior_boundaries=interior_boundaries, selections=selections,
                                 propagate_selections=propagate_selections)

    def copy_layer(self, source, *, output, delta=(0, 0), selections=(),
                   propagate_selections=True):
        """Copy current source geometry to output, preserving the original layer.

        Points and curves are supported as well as filled shapes. delta accepts
        the same parameters and Vertices displacement tables as Copy.
        """
        from .layer_operations import LayerCopy
        return LayerCopy(self, source, output=output, delta=delta, selections=selections,
                         propagate_selections=propagate_selections)

    def add_selection(self, name, *, entity="boundary"):
        """Create a named FEM group, independent of the drawing layers."""
        return Selection(self, name, entity=entity)

    def add(self, obj):
        if obj.project is not self or self.layers.get(obj.layer.name) is not obj.layer:
            raise ValueError("The object and its layer must belong to this project.")
        if obj in self.objects:
            raise ValueError("This object is already in the project.")
        obj.validate_selections()
        self._final_objects(self.objects + [obj])
        if not getattr(self, '_defer_parameter_checks', False):
            self._parameters_for(self.objects + [obj])
        obj.tag = f"{obj.tag_prefix}{len(self.objects) + 1}"
        self.objects.append(obj)
        if self.live:
            self.build()

    @staticmethod
    def _final_objects(objects):
        """Follow native input retention, including the two sides of Difference."""
        available = set()
        for obj in objects:
            for source in obj.inputs:
                if source not in available:
                    raise ValueError(
                        "Geometry input is missing or already consumed. "
                        "Keep it in the earlier operation to reuse it."
                    )
                cross_layer = getattr(obj, "_cross_layer", False)
                if source.project is not obj.project or (source.layer is not obj.layer and not cross_layer):
                    raise ValueError("An operation must share its input's project and layer.")
                if cross_layer and (source.layer.comsol, source.layer.gds) != (obj.layer.comsol, obj.layer.gds):
                    raise ValueError("Layer operations require matching COMSOL/GDS flags on inputs and output.")
                if source.layer.workplane is not obj.layer.workplane:
                    raise ValueError('Planar operations require inputs and output in the same workplane.')
            available.difference_update(obj.consumed_inputs())
            available.add(obj)
        return [obj for obj in objects if obj in available]

    def _connect_comsol(self):
        if self.model is not None:
            return
        self.client = get_client(self.host, self.port, self.client)

        from jpype import JClass
        # Allow the Desktop to finish a short request before our next command.
        self.client.java.setServerBusyHandler(
            JClass("com.comsol.model.util.ServerBusyHandler")(5000))
        self.model = self.client.create(self.output.name)
        # Component (3D) > Geometry (3D) > Work Plane (2D) > planar features.
        component = self.model.java.component().create("comp1", True)
        self.geometry = component.geom().create("geom1", 3)
        self.geometry.lengthUnit("um")
        self.geometry.angularUnit("deg")
        self.workplane = self.geometry.create("wp1", "WorkPlane")
        self.workplane.set("unite", True)
        self.workplane.set("selplaneshow", "on")
        self.default_workplane.native = self.workplane

    def _validate_grid(self):
        try:
            value = float(self.dbu)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("Project.dbu must be a finite positive length in um.") from error
        if isinstance(self.dbu, bool) or not isfinite(value) or value <= 0:
            raise ValueError("Project.dbu must be a finite positive length in um.")
        if self.grid_policy not in ("round", "error"):
            raise ValueError("Project.grid_policy must be 'round' or 'error'.")
        self.dbu = value

    def grid_report(self):
        """Return diagnostics from the latest GDS build attempt, without printing.

        Lengths are in um. ``complete`` means the GDS was written successfully.
        The maximum displacement is per coordinate (not Euclidean distance).
        Affected vertices exclude floating-point noise; collapsed vertices count
        adjacent vertices that become identical, not a full topology/DRC check.
        Entries distinguish export, Boolean inputs and planar-operation pieces. Region
        calculations themselves use integer coordinates; their internal rounding
        of new intersections is not measured by this displacement report.
        Points are construction data and are excluded because they are not saved
        in GDS. A new build replaces the report rather than accumulating counts.
        """
        return deepcopy(self._grid_report)

    def _record_grid(self, geometry, entry, report=None):
        """Inspect floating-point geometry before an explicit integer conversion."""
        import klayout.db as kdb

        if isinstance(geometry, kdb.DPath):
            contours = [list(geometry.each_point())]
            closed = False
        elif isinstance(geometry, kdb.DPolygon):
            contours = [list(geometry.each_point_hull())]
            contours.extend(list(geometry.each_point_hole(hole))
                            for hole in range(geometry.holes()))
            closed = True
        else:
            raise TypeError("GDS export expects a DPoint, DPath, DPolygon or a tuple of these.")
        entry["shapes"] += 1
        for points in contours:
            integers = []
            for point in points:
                coordinates = (point.x, point.y)
                # Check before calling KLayout: integer overflow must never wrap
                # or silently move an otherwise valid shape to another location.
                if any(not isfinite(value) or not -2147483648 <= value / self.dbu <= 2147483647
                       for value in coordinates):
                    raise ValueError(f"{entry['tag']} exceeds the GDS coordinate range; "
                                     "increase Project.dbu or move the geometry closer to the origin.")
                integer = point.to_itype(self.dbu)
                integers.append((integer.x, integer.y))
                rounded = (integer.x*self.dbu, integer.y*self.dbu)
                deltas = [abs(value - result) for value, result in zip(coordinates, rounded)]
                displacement = max(deltas)
                # Account for a few arithmetic operations, without treating a
                # meaningful fraction of a grid interval as floating-point noise.
                off_grid = any(delta > max(self.dbu*1e-9, 8*ulp(value), 8*ulp(result))
                               for value, result, delta in zip(coordinates, rounded, deltas))
                entry["vertices"] += 1
                entry["affected_vertices"] += int(off_grid)
                entry["max_coordinate_displacement_um"] = max(
                    entry["max_coordinate_displacement_um"], displacement)
            entry["collapsed_vertices"] += sum(a == b for a, b in zip(integers, integers[1:]))
            if closed and len(integers) > 1 and integers[0] == integers[-1]:
                entry["collapsed_vertices"] += 1
        if report is None:
            report = self._grid_report
        report["max_coordinate_displacement_um"] = max(
            report["max_coordinate_displacement_um"], entry["max_coordinate_displacement_um"])
        if entry["affected_vertices"] and entry["tag"] not in report["affected_objects"]:
            report["affected_objects"].append(entry["tag"])
        if self.grid_policy == "error" and entry["affected_vertices"]:
            raise ValueError(
                f"{entry['type']} {entry['tag']} is off the GDS grid "
                f"(dbu={self.dbu:g} um, maximum coordinate displacement "
                f"{entry['max_coordinate_displacement_um']:g} um). "
                "Use grid_policy='round', change the design coordinates, or reduce Project.dbu.")

    def _new_grid_report(self):
        return {
            "dbu_um": self.dbu, "grid_policy": self.grid_policy, "complete": False,
            "max_coordinate_displacement_um": 0.0, "affected_objects": [], "objects": [],
            "boolean_operations": [], "planar_operations": [],
        }

    @staticmethod
    def _grid_entry(obj, stage, operation=None):
        return {"tag": obj.tag, "type": type(obj).__name__, "layer": obj.layer.name,
                "stage": stage, "operation_tag": operation.tag if operation else None,
                "shapes": 0, "vertices": 0, "affected_vertices": 0,
                "collapsed_vertices": 0, "max_coordinate_displacement_um": 0.0}

    def _boolean_region(self, geometry, operation, operand):
        """Convert a filled operand to the same grid used for GDS export.

        Direct to_klayout() calls enforce the policy but leave the last build's
        report intact. No implicit finer working grid or alternative kernel.
        """
        import klayout.db as kdb

        self._validate_grid()
        report = self._grid_report if self._collect_grid else self._new_grid_report()
        if not any(item["tag"] == operation.tag for item in report["boolean_operations"]):
            report["boolean_operations"].append({
                "tag": operation.tag, "type": type(operation).__name__, "dbu_um": self.dbu,
                "internal_intersection_rounding_measured": False,
            })
        entry = self._grid_entry(operand, "boolean_input", operation)
        report["objects"].append(entry)
        region = kdb.Region()
        for polygon in geometry if isinstance(geometry, tuple) else (geometry,):
            if not isinstance(polygon, kdb.DPolygon):
                raise TypeError("Area Booleans require filled polygons, not points or curves.")
            self._record_grid(polygon, entry, report)
            integer = polygon.to_itype(self.dbu)
            if integer.area2() == 0:
                raise ValueError(f"{operand.tag} collapses on the GDS grid before "
                                 f"{operation.tag}; reduce Project.dbu.")
            region.insert(integer)
        return region

    def _operation_region(self, geometry, operation, operand, *, allow_empty=False):
        """Convert planar-operation polygon pieces using the public GDS grid.

        This includes sampled stroke joins/caps. Their explicit rounding is
        reported separately from Boolean operands and final export rounding.
        Region's internal intersection rounding is not measured.
        """
        import klayout.db as kdb

        self._validate_grid()
        report = self._grid_report if self._collect_grid else self._new_grid_report()
        if not any(item["tag"] == operation.tag for item in report["planar_operations"]):
            report["planar_operations"].append({
                "tag": operation.tag, "type": type(operation).__name__, "dbu_um": self.dbu,
                "internal_intersection_rounding_measured": False,
            })
        entry = self._grid_entry(operand, "operation_input", operation)
        report["objects"].append(entry)
        region = kdb.Region()
        for polygon in geometry if isinstance(geometry, tuple) else (geometry,):
            if not isinstance(polygon, kdb.DPolygon):
                raise TypeError("Region calculations require filled polygons.")
            self._record_grid(polygon, entry, report)
            integer = polygon.to_itype(self.dbu)
            if integer.area2() == 0:
                if allow_empty:
                    continue
                raise ValueError(f"{operand.tag} produces a collapsed polygon in {operation.tag}; "
                                 "reduce Project.dbu.")
            region.insert(integer)
        return region

    def _build_gds(self):
        self._validate_grid()
        self._grid_report = self._new_grid_report()
        self._collect_grid = True
        try:
            self._write_gds()
        finally:
            self._collect_grid = False

    def _write_gds(self):
        final = self._final_objects(self.objects)
        for plane in self.workplanes.values():
            if plane is self.default_workplane or any(
                    layer.gds and layer.workplane is plane for layer in self.layers.values()):
                self._write_workplane_gds(plane, final)
        self.layout = self.default_workplane.layout
        self._grid_report['complete'] = True

    def _write_workplane_gds(self, plane, objects):
        """Export one drawing in local coordinates, independently of its 3D pose."""
        import klayout.db as kdb

        layout = kdb.Layout()
        layout.dbu = self.dbu
        cell = layout.create_cell("TOP")
        for obj in objects:
            if obj.layer.gds and obj.layer.workplane is plane:
                layer_index = layout.layer(obj.layer.gds_layer, obj.layer.gds_datatype)
                result = obj.to_klayout()
                geometries = result if isinstance(result, tuple) else (result,)
                entry = self._grid_entry(obj, "export")
                for geometry in geometries:
                    # DPoint is useful construction data, not a GDS marker.
                    if isinstance(geometry, kdb.DPoint):
                        continue
                    if not entry["shapes"]:
                        self._grid_report["objects"].append(entry)
                    self._record_grid(geometry, entry)
                    shape = geometry.to_itype(self.dbu)
                    if isinstance(shape, kdb.Path):
                        # Zero width deliberately represents a centreline. Keep
                        # it as a PATH record; area operations would erase it.
                        points = []
                        for point in shape.each_point():
                            if not points or point != points[-1]:
                                points.append(point)
                        if len(points) < 2 or (geometry.width > 0 and shape.width == 0):
                            raise ValueError(
                                f"{type(obj).__name__} collapses on the GDS grid; reduce Project.dbu."
                            )
                        shape.points = points
                        if shape.width == 0:
                            # GDS XY records have a 16-bit byte length. KLayout
                            # does not split long PATH records automatically.
                            # Share each seam vertex to preserve all segments.
                            for start in range(0, len(points) - 1, 3999):
                                cell.shapes(layer_index).insert(kdb.Path(points[start:start + 4000], 0))
                            continue
                    elif shape.area2() == 0:
                        raise ValueError(
                            f"{type(obj).__name__} is too small for the GDS grid; reduce Project.dbu."
                        )
                    cell.shapes(layer_index).insert(shape)
        # The Desktop reads either the old complete file or the new complete file.
        temporary = plane.gds_path.with_suffix(".writing.gds")
        options = kdb.SaveLayoutOptions()
        options.gds2_max_vertex_count = 4000
        options.gds2_multi_xy_records = False
        layout.write(str(temporary),options)
        os.replace(temporary, plane.gds_path)
        plane.layout = layout

    def _save_comsol(self):
        """Export without tying the server model to a file that blocks the next Run."""
        path = self.mph_path
        requested = self.output.with_suffix(".mph")
        number = 2
        while True:
            try:
                self.model.java.save(str(path), True)  # COMSOL's documented save-copy option.
                break
            except Exception as error:
                if "locked by another model" not in str(error).lower():
                    raise
                # Preserve an open model's file. Other save errors remain visible.
                path = requested.with_name(f"{requested.stem}_{number}.mph")
                while path.exists():
                    number += 1
                    path = requested.with_name(f"{requested.stem}_{number}.mph")
                number += 1
        if path != self.mph_path:
            print(f"COMSOL output is in use; saved the new model to {path}")
            self._mph_path = path

    def build(self):
        """Build/save enabled layers; repeated calls do not duplicate features.

        GDS is also produced if COMSOL is unavailable. The COMSOL exception still
        propagates: a GDS file alone must not be mistaken for a complete build.
        Changing object attributes or parameter values requires build() again.
        Python values overwrite this geometry's COMSOL parameter definitions.
        """
        # Check dependencies/names before changing either output or connecting.
        self._validate_grid()
        self._parameters_for(self.objects)
        for plane in self.workplanes.values():
            plane.validate()
        for obj in self.objects:
            obj.validate()
            obj.validate_selections()
        self._final_objects(self.objects)
        native_planes = [plane for plane in self.workplanes.values()
                         if plane is self.default_workplane or any(
                             layer.comsol and layer.workplane is plane for layer in self.layers.values())]
        comsol_parameters = self._parameters_for(
            (obj for obj in self.objects if obj.layer.comsol), workplanes=native_planes)
        definitions = [(parameter.name, parameter.definition, parameter.description)
                       for parameter in comsol_parameters.values()]
        self.output.parent.mkdir(parents=True, exist_ok=True)
        if any(layer.gds for layer in self.layers.values()):
            self._build_gds()
        if any(layer.comsol for layer in self.layers.values()):
            self._connect_comsol()
            for name, expression, description in definitions:
                self.model.java.param().set(name, expression, description)
            previous_plane = None
            for plane in native_planes:
                if plane.tag not in list(self.geometry.feature().tags()) and previous_plane is not None:
                    self.geometry.run(previous_plane.tag)
                plane.to_comsol(self.geometry)
                self._build_workplane(plane)
                previous_plane = plane
            self.workplane = self.default_workplane.native
            self.geometry.run()
            component = self.model.java.component("comp1")
            for selection in self.selections.values():
                selection.to_comsol(component)
            for group in self._layer_selections.values():
                group.to_comsol(component)
            self._save_comsol()
        return self

    def _build_workplane(self, plane):
        """Emit the graph and layer captures belonging to one drawing."""
        geometry = plane.native.geom()
        objects = [obj for obj in self.objects if obj.layer.workplane is plane and obj.layer.comsol]
        groups = [group for group in self._layer_selections.values() if group.layer.workplane is plane]
        for group in groups:
            group.remove_comsol(geometry)
        # Routes own a variable number of internal features. Reset them before
        # emission so rebuilding preserves downstream references and order.
        reset = False
        for obj in objects:
            if hasattr(obj, 'reset_comsol'):
                reset = obj.reset_comsol(geometry) or reset
        if reset:
            tags = list(geometry.feature().tags())
            if tags:
                geometry.runPre(str(tags[0]))
        previous_tag = None
        for obj in objects:
            # Vertex/edge inspection may move COMSOL's current feature back.
            # Restore the order before appending the next feature.
            if (previous_tag is not None and obj.tag not in list(geometry.feature().tags())
                    and str(geometry.current()) != previous_tag):
                geometry.run(previous_tag)
            obj.to_comsol(geometry, obj.tag)
            feature = geometry.feature(obj.tag)
            feature.set('selresult', 'on')
            feature.set('selresultshow', 'all')
            previous_tag = obj.tag
        if objects and groups:
            geometry.run(objects[-1].tag)
        for group in groups:
            group.prepare_comsol(geometry)

    def show(self, *, comsol_exe=None, klayout_exe=None):
        """Open Desktop viewers, also before the first square in live mode.

        In COMSOL, select this model once with Import Application from Server.
        KLayout reloads the GDS automatically. Executable paths can be supplied
        explicitly when they are not on PATH or in the defaults below.
        """
        self.output.parent.mkdir(parents=True, exist_ok=True)
        for backend, process in list(self._gui_processes.items()):
            if process.poll() is not None:
                del self._gui_processes[backend]
        if (any(layer.comsol for layer in self.layers.values())
                and self.client is not None and not self.client.port):
            raise ValueError("Shared COMSOL Desktop requires a client connected to a server.")
        gds_planes = [plane for plane in self.workplanes.values()
                      if any(layer.gds and layer.workplane is plane for layer in self.layers.values())]
        previews = [('gds' if plane is self.default_workplane else f'gds_{plane.name.casefold()}', plane)
                    for plane in gds_planes]
        missing = [(key, plane) for key, plane in previews if key not in self._gui_processes]
        if missing:
            self._build_gds()
            exe = self._executable(klayout_exe, "klayout", r"C:\Program Files\KLayout\klayout_app.exe")
            script = Path(__file__).resolve().with_name("_klayout_preview.py")
            for key, plane in missing:
                self._gui_processes[key] = subprocess.Popen(
                    [exe, "-rr", str(script), "-rd", f"gds_file={plane.gds_path}"])
        if any(layer.comsol for layer in self.layers.values()):
            self._connect_comsol()
            if "comsol" not in self._gui_processes:
                exe = self._executable(comsol_exe, "comsolmphclient",
                                      r"C:\Program Files\COMSOL\COMSOL64\Multiphysics\bin\win64\comsolmphclient.exe")
                self._gui_processes["comsol"] = subprocess.Popen(
                    [exe, "-server", self.host, "-port", str(self.port)])
            print(f"COMSOL model: {self.model.name()} (tag: {self.model.java.tag()})")
            print("Desktop: File > COMSOL Multiphysics Server > Import Application from Server.")
        return self

    @staticmethod
    def _executable(explicit, command, windows_default):
        candidate = str(explicit) if explicit else shutil.which(command)
        if not candidate and os.name == "nt":
            candidate = windows_default
        if not candidate or not Path(candidate).is_file():
            raise FileNotFoundError(f"Specify the path to the {command} Desktop executable.")
        return candidate
