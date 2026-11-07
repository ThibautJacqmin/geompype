"""Long centreline exports retain all segments within GDS record limits."""

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import CircularArc, Project


class TestCurveGds(unittest.TestCase):
    def test_long_path_readback_preserves_every_segment(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "long_curve", dbu=0.0000001)
            layer = project.add_layer("curve", comsol=False)
            arc = CircularArc(project, layer=layer, radius=100,
                              end_angle=270, tolerance=0.000001)
            expected = arc.to_klayout().to_itype(project.dbu)
            self.assertGreater(expected.num_points(), 16000)
            project.build()
            layout = kdb.Layout()
            layout.read(str(project.gds_path))
            paths = [shape.path for shape in layout.top_cell().shapes(layout.layer(1, 0)).each()]
            self.assertGreater(len(paths), 1)
            self.assertTrue(all(path.width == 0 and 2 <= path.num_points() <= 4000
                                for path in paths))

            def edges(path):
                points = [(point.x, point.y) for point in path.each_point()]
                return list(zip(points, points[1:]))

            self.assertEqual(Counter(edge for path in paths for edge in edges(path)),
                             Counter(edges(expected)))
