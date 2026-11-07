"""Opt-in checks of native filled primitives and their saved parameter formulas."""

from math import pi
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from comsol_support import get_client
from geompype import DependentParameter, Parameter, Project, Vertices
from geompype.primitives import Circle, Ellipse, Polygon, Rectangle
from geompype.transforms import Rotate


def measure_group(model, tag):
    from jpype import JArray, JInt

    component = model.java.component("comp1")
    selection = component.selection(tag)
    measure = component.geom("geom1").measureFinal()
    measure.selection().geom(JInt(2))
    measure.selection().set(JArray(JInt)(list(selection.entities())))
    return measure


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolPrimitives(unittest.TestCase):
    def assert_group(self, model, tag, area, bounds, count=1, curved=False):
        selection = model.java.component("comp1").selection(tag)
        self.assertEqual(selection.dim(), 2)
        self.assertEqual(len(selection.entities()), count)
        measure = measure_group(model, tag)
        # COMSOL's documented measurement API uses a rendering mesh. A disk
        # on 6.4 is about 0.34% below pi*r**2; allow 0.5% for curved faces.
        # Native feature types, formulas and bounds are checked independently.
        # https://doc.comsol.com/6.4/doc/com.comsol.help.comsol/comsol_api_geom.48.047.html
        self.assertAlmostEqual(measure.getArea(), area,
                               delta=0.005*area if curved else 0.00001)
        for actual, expected in zip(measure.getBoundingBox(), (*bounds, 0, 0)):
            self.assertAlmostEqual(actual, expected, delta=0.00001)

    def test_four_primitives_and_rotated_selections_in_both_modes(self):
        import klayout.db as kdb

        client = get_client()
        with TemporaryDirectory() as folder:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(client=client, live=live, dbu=0.0001,
                                      output=Path(folder) / f"primitives_{live}")
                    layer = project.add_layer("metal", gds_layer=11, gds_datatype=2)
                    groups = [project.add_selection(name)
                              for name in ("rectangle", "circle", "ellipse", "polygon")]
                    results = [project.add_selection(f"result_{index}") for index in range(4)]
                    try:
                        rectangle = Rectangle(project, layer=layer, size=(4, 2),
                                              position=(10, 0), angle=90, selections=[groups[0]])
                        self.assertEqual(project.model is not None, live)
                        circle = Circle(project, layer=layer, radius=2, position=(30, 0),
                                        tolerance=0.0001, selections=[groups[1]])
                        ellipse = Ellipse(project, layer=layer, semiaxes=(3, 1),
                                          position=(50, 0), tolerance=0.0001,
                                          selections=[groups[2]])
                        polygon = Polygon(project, layer=layer,
                                          vertices=[[70, 0], [74, 0], [70, 3]],
                                          selections=[groups[3]])
                        originals = (rectangle, circle, ellipse, polygon)
                        for index, obj in enumerate(originals):
                            Rotate(obj, angle=90, keep=index in (1, 3), selections=[results[index]])
                        project.build()
                        project.build()

                        self.assertEqual(project.geometry.getSDim(), 3)
                        self.assertEqual(project.workplane.getType(), "WorkPlane")
                        plane = project.workplane.geom()
                        self.assertEqual(plane.getSDim(), 2)
                        for obj, expected in zip(originals, ("Rectangle", "Circle", "Ellipse", "Polygon")):
                            feature = plane.feature(obj.tag)
                            self.assertEqual(feature.getType(), expected)
                            self.assertEqual(str(feature.getString("type")), "solid")
                            self.assertNotIn(obj.tag, list(project.geometry.feature().tags()))
                        self.assertEqual(sum(str(plane.feature(tag).getType()) != "ExplicitSelection"
                                             for tag in plane.feature().tags()), 8)

                        expected = [
                            (8, (-2, 2, 9, 11), 1),
                            (8*pi, (-2, 32, -2, 32), 2),
                            (3*pi, (-1, 1, 47, 53), 1),
                            (12, (-3, 74, 0, 74), 2),
                        ]
                        for index, (group, (area, bounds, count)) in enumerate(zip(groups, expected)):
                            self.assert_group(project.model, group.tag, area, bounds, count,
                                              curved=index in (1, 2))
                        result_geometry = [
                            (8, (-2, 2, 9, 11)),
                            (4*pi, (-2, 2, 28, 32)),
                            (3*pi, (-1, 1, 47, 53)),
                            (6, (-3, 0, 70, 74)),
                        ]
                        for index, (group, (area, bounds)) in enumerate(zip(results, result_geometry)):
                            self.assert_group(project.model, group.tag, area, bounds,
                                              curved=index in (1, 2))

                        layout = kdb.Layout()
                        layout.read(str(project.gds_path))
                        shapes = layout.top_cell().shapes(layout.layer(11, 2))
                        self.assertEqual(shapes.size(), 6)
                        self.assertAlmostEqual(kdb.Region(shapes).area() * layout.dbu**2,
                                               20 + 11*pi, delta=0.02)
                    finally:
                        if project.model is not None:
                            client.remove(project.model)

    def test_mixed_units_python_rebuild_native_edit_and_saved_expressions(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder) / "parametric_primitives")
            layer = project.add_layer("metal")
            groups = [project.add_selection(name)
                      for name in ("rectangle", "circle", "ellipse", "polygon")]
            width = Parameter(4000, "width", unit="nm")
            height = Parameter(2, "height", unit="um")
            minor = Parameter(1000, "minor", unit="nm")
            angle = Parameter(pi / 2, "angle", unit="rad")
            radius = DependentParameter(width / 2, "radius")
            vertices = Vertices([[0, 0], [1, 0], [1, 1], [0, 1]], width) + [70, 0]
            try:
                rectangle = Rectangle(project, layer=layer, size=(width, height),
                                      position=(10, 0), angle=angle, selections=[groups[0]])
                circle = Circle(project, layer=layer, radius=radius,
                                position=(30, 0), selections=[groups[1]])
                ellipse = Ellipse(project, layer=layer, semiaxes=(width, minor),
                                  position=(50, 0), angle=angle, selections=[groups[2]])
                polygon = Polygon(project, layer=layer, vertices=vertices, selections=[groups[3]])
                project.build()
                plane = project.workplane.geom()
                self.assertEqual(list(plane.feature(rectangle.tag).getStringArray("size")),
                                 ["width", "height"])
                self.assertEqual(str(plane.feature(rectangle.tag).getString("rot")), "angle")
                self.assertEqual(str(plane.feature(circle.tag).getString("r")), "radius")
                self.assertEqual(list(plane.feature(ellipse.tag).getStringArray("semiaxes")),
                                 ["width", "minor"])
                self.assertEqual(str(plane.feature(ellipse.tag).getString("rot")), "angle")
                polygon_x = list(plane.feature(polygon.tag).getStringArray("x"))
                polygon_y = list(plane.feature(polygon.tag).getStringArray("y"))
                self.assertIn("width", polygon_x[1])
                self.assertIn("width", polygon_y[2])
                self.assertEqual(str(project.model.java.param().get("radius")), radius.definition)
                initial = [(8, (9, 11, -2, 2)), (4*pi, (28, 32, -2, 2)),
                           (4*pi, (49, 51, -4, 4)), (16, (70, 74, 0, 4))]
                for index, (group, (area, bounds)) in enumerate(zip(groups, initial)):
                    self.assert_group(project.model, group.tag, area, bounds, curved=index in (1, 2))

                width.value, height.value = 6000, 3
                project.build()
                updated = [(18, (8.5, 11.5, -3, 3)), (9*pi, (27, 33, -3, 3)),
                           (6*pi, (49, 51, -6, 6)), (36, (70, 76, 0, 6))]
                for index, (group, (area, bounds)) in enumerate(zip(groups, updated)):
                    self.assert_group(project.model, group.tag, area, bounds, curved=index in (1, 2))
                gds_before_native_edit = project.gds_path.read_bytes()

                # Change COMSOL alone: Python values and the existing GDS stay unchanged.
                params = project.model.java.param()
                params.set("width", "8[um]")
                params.set("angle", "0[deg]")
                project.geometry.run()
                native = [(24, (6, 14, -1.5, 1.5)), (16*pi, (26, 34, -4, 4)),
                          (8*pi, (42, 58, -1, 1)), (64, (70, 78, 0, 8))]
                for index, (group, (area, bounds)) in enumerate(zip(groups, native)):
                    self.assert_group(project.model, group.tag, area, bounds, curved=index in (1, 2))
                self.assertEqual(width.value, 6000)
                self.assertEqual(angle.value, pi / 2)
                self.assertEqual(project.gds_path.read_bytes(), gds_before_native_edit)

                saved_path = Path(folder) / "native_edit.mph"
                project.model.java.save(str(saved_path), True)
                saved = client.load(str(saved_path))
                try:
                    self.assertEqual(str(saved.java.param().get("width")), "8[um]")
                    self.assertEqual(str(saved.java.param().get("radius")), radius.definition)
                    saved_plane = saved.java.component("comp1").geom("geom1").feature("wp1").geom()
                    self.assertEqual(list(saved_plane.feature(rectangle.tag).getStringArray("size")),
                                     ["width", "height"])
                    self.assertEqual(str(saved_plane.feature(circle.tag).getString("r")), "radius")
                    self.assertEqual(list(saved_plane.feature(ellipse.tag).getStringArray("semiaxes")),
                                     ["width", "minor"])
                    self.assertEqual(list(saved_plane.feature(polygon.tag).getStringArray("x")), polygon_x)
                    self.assertEqual(list(saved_plane.feature(polygon.tag).getStringArray("y")), polygon_y)
                    for index, (group, (area, bounds)) in enumerate(zip(groups, native)):
                        self.assert_group(saved, group.tag, area, bounds, curved=index in (1, 2))
                finally:
                    client.remove(saved)
            finally:
                if project.model is not None:
                    client.remove(project.model)


if __name__ == "__main__":
    unittest.main()
