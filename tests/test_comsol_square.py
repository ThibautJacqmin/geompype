"""Opt-in integration test against the user's running COMSOL server."""

import os
from pathlib import Path
import tempfile
import unittest

from comsol_support import get_client
from geompype import Project
from geompype.primitives import Square


@unittest.skipUnless(os.environ.get("GEOMPYPE_TEST_COMSOL") == "1",
                     "Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.")
class ComsolSquareTest(unittest.TestCase):
    def test_both_modes_and_layer_destinations(self):
        import klayout.db as kdb

        client = get_client()
        with tempfile.TemporaryDirectory() as directory:
            for live in (False, True):
                with self.subTest(live=live):
                    project = Project(live=live, client=client,
                                      output=Path(directory) / f"square_{live}")
                    both = project.add_layer("both")
                    comsol = project.add_layer("comsol", gds=False)
                    gds = project.add_layer("gds", comsol=False, gds_layer=2)
                    disabled = project.add_layer("disabled", comsol=False, gds=False)
                    try:
                        Square(project, layer=both, side=20, position=(10, 5))
                        self.assertEqual(project.model is not None, live)
                        Square(project, layer=comsol, side=10, position=(50, 0), angle=30)
                        Square(project, layer=gds, side=5, position=(100, 0))
                        Square(project, layer=disabled, side=100, position=(200, 0))
                        project.build()
                        project.build()  # A second call must not duplicate geometry.
                        self.assertEqual(project.geometry.getSDim(), 3)
                        self.assertEqual(project.workplane.getType(), "WorkPlane")
                        plane = project.workplane.geom()
                        self.assertEqual(plane.getSDim(), 2)
                        tags = list(plane.feature().tags())
                        self.assertIn("sq1", tags)
                        self.assertIn("sq2", tags)
                        self.assertNotIn("sq3", tags)
                        self.assertNotIn("sq4", tags)
                        self.assertNotIn("sq1", list(project.geometry.feature().tags()))
                        self.assertEqual(plane.feature("sq1").getType(), "Square")
                        measure = project.geometry.measureFinal()
                        measure.selection().geom(2)
                        measure.selection().all()
                        # COMSOL measurements use a rendering mesh (manual p.269).
                        self.assertAlmostEqual(measure.getArea(), 500.0, delta=0.001)

                        layout = kdb.Layout()
                        layout.read(str(project.gds_path))
                        total = sum(kdb.Region(layout.top_cell().begin_shapes_rec(i)).area()
                                    for i in layout.layer_indices()) * layout.dbu**2
                        self.assertAlmostEqual(total, 425.0, places=7)
                        self.assertTrue(project.mph_path.is_file())
                    finally:
                        if project.model is not None:
                            client.remove(project.model)  # Only this test's model.


if __name__ == "__main__":
    unittest.main()
