"""Opt-in proof that the saved COMSOL model remains parametric without Python."""

from math import pi
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from comsol_support import get_client
from geompype import DependentParameter, Parameter, Project, maximum, round_nearest
from geompype.primitives import Square
from geompype.transforms import Rotate


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolParameters(unittest.TestCase):
    def test_round_max_and_explicit_registration(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder) / "functions")
            layer = project.add_layer("metal", gds=False)
            um = Parameter(1, "reference_um", unit="um")
            radius = Parameter(8, "fillet_radius", unit="um")
            count = DependentParameter(maximum(8, round(3 * radius / um)), "fillet_n")
            raw = Parameter(0.5, "raw_value")
            rounded = DependentParameter(round_nearest(raw), "rounded")
            project.add_parameter(count)
            project.add_parameter(rounded)
            Square(project, layer=layer, side=radius)
            try:
                project.build()
                params = project.model.java.param()
                self.assertAlmostEqual(params.evaluate("fillet_n"), 24)
                for value, expected in [(0.5, 1), (-0.5, -1), (2.5, 3), (-2.5, -3),
                                        (0.49999999999999994, 0), (4503599627370497, 4503599627370497)]:
                    params.set("raw_value", repr(value))
                    self.assertEqual(params.evaluate("rounded"), expected)
                params.set("fillet_radius", "2[um]")
                self.assertAlmostEqual(params.evaluate("fillet_n"), 8)
                radius.value = 4
                project.build()
                self.assertAlmostEqual(params.evaluate("fillet_n"), 12)
                saved = client.load(str(project.mph_path))
                try:
                    self.assertEqual(str(saved.java.param().get("fillet_n")), count.definition)
                    self.assertEqual(str(saved.java.param().get("rounded")), rounded.definition)
                finally:
                    client.remove(saved)
            finally:
                if project.model is not None:
                    client.remove(project.model)

    def test_native_parameter_edit_rebuild_and_saved_expressions(self):
        client = get_client()
        with TemporaryDirectory() as folder:
            project = Project(client=client, output=Path(folder) / "parameters")
            metal = project.add_layer("metal")
            group = project.add_selection("conductor")
            width = Parameter(20, "width", unit="um")
            gap = Parameter(500, "gap", unit="nm")
            angle = Parameter(pi / 2, "angle", unit="rad")
            pitch = DependentParameter(width + 2 * gap, "pitch")
            square = Square(project, layer=metal, side=width,
                            position=(pitch, 0), angle=angle, selections=[group])
            Rotate(square, angle=-angle)
            try:
                project.build()
                params = project.model.java.param()
                self.assertEqual(str(params.get("pitch")), pitch.definition)
                plane = project.workplane.geom()
                self.assertEqual(str(plane.feature(square.tag).getString("size")), "width")

                def assert_geometry(area, bounds):
                    from jpype import JArray, JInt
                    measure = project.geometry.measureFinal()
                    measure.selection().geom(JInt(2))
                    measure.selection().set(JArray(JInt)(group.entities()))
                    self.assertAlmostEqual(measure.getArea(), area, delta=0.001)
                    for actual, expected in zip(measure.getBoundingBox(), bounds):
                        self.assertAlmostEqual(actual, expected, delta=0.00001)

                assert_geometry(400, (-10, 10, -31, -11, 0, 0))
                # Equivalent to editing Global Definitions > Parameters in the GUI.
                # Rebuild COMSOL alone: no Python object or GDS rebuild is involved.
                params.set("width", "30[um]")
                project.geometry.run()
                assert_geometry(900, (-15, 15, -46, -16, 0, 0))
                self.assertEqual(width.value, 20)

                width.value = 10
                angle.value = 0
                project.build()
                assert_geometry(100, (6, 16, -5, 5, 0, 0))
                reloaded = client.load(str(project.mph_path))
                try:
                    self.assertEqual(str(reloaded.java.param().get("pitch")), pitch.definition)
                    self.assertEqual(str(reloaded.java.param().get("width")), width.definition)
                finally:
                    client.remove(reloaded)
            finally:
                if project.model is not None:
                    client.remove(project.model)


if __name__ == "__main__":
    unittest.main()
