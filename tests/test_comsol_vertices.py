"""Opt-in checks of actual geometry built from Vertices and saved expressions."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from comsol_support import get_client
from geompype import Parameter, Project, Rotate, Square, Vertices
from test_parameter_geometry import read_region


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class TestComsolVertices(unittest.TestCase):
    def test_vertices_in_both_modes_and_native_parameter_edit(self):
        from jpype import JArray, JInt

        client = get_client()
        with TemporaryDirectory() as folder:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(client=client, live=live,
                                      output=Path(folder) / f"vertices_{live}")
                    metal = project.add_layer("metal")
                    group = project.add_selection("conductors")
                    pitch = Parameter(20, "pitch", unit="um")
                    gap = Parameter(500, "gap", unit="nm")
                    count = Parameter(2, "count")
                    position = Vertices([count, 0], pitch) + Vertices([gap, 1000], unit="nm")
                    origin = Vertices([500, 0], unit="nm")
                    try:
                        square = Square(project, layer=metal, side=4,
                                        position=position, selections=[group])
                        rotated = Rotate(square, angle=90, origin=origin)
                        project.build()

                        def assert_bounds(bounds, compare_gds=True):
                            measure = project.geometry.measureFinal()
                            measure.selection().geom(JInt(2))
                            measure.selection().set(JArray(JInt)(group.entities()))
                            self.assertAlmostEqual(measure.getArea(), 16, delta=0.001)
                            for actual, expected in zip(measure.getBoundingBox(), (*bounds, 0, 0)):
                                self.assertAlmostEqual(actual, expected, delta=0.00001)
                            if compare_gds:
                                layout, region = read_region(project)
                                box = region.bbox().to_dtype(layout.dbu)
                                for actual, expected in zip((box.left, box.right, box.bottom, box.top), bounds):
                                    self.assertAlmostEqual(actual, expected, delta=layout.dbu)

                        assert_bounds((-2.5, 1.5, 38, 42))
                        plane = project.workplane.geom()
                        self.assertEqual(list(plane.feature(square.tag).getStringArray("pos")),
                                         position.to_comsol()[0])
                        self.assertEqual(list(plane.feature(rotated.tag).getStringArray("pos")),
                                         origin.to_comsol()[0])
                        project.model.java.param().set("pitch", "30[um]")
                        project.geometry.run()
                        assert_bounds((-2.5, 1.5, 58, 62), compare_gds=False)

                        count.value = 3
                        gap.value = 1000
                        origin[0, 1] = gap
                        project.build()
                        assert_bounds((-1.5, 2.5, 59.5, 63.5))
                        reloaded = client.load(str(project.mph_path))
                        try:
                            saved_plane = reloaded.java.component("comp1").geom("geom1").feature("wp1").geom()
                            self.assertEqual(list(saved_plane.feature(square.tag).getStringArray("pos")),
                                             position.to_comsol()[0])
                            self.assertEqual(list(saved_plane.feature(rotated.tag).getStringArray("pos")),
                                             origin.to_comsol()[0])
                        finally:
                            client.remove(reloaded)
                    finally:
                        if project.model is not None:
                            client.remove(project.model)


if __name__ == "__main__":
    unittest.main()
