"""Analytic footprint checks for the curved interpolation tutorial."""

from math import asinh, pi, sqrt
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb
from geompype import Project


def parabola_length(span, rise):
    """Exact arc length of y=rise*(1-(2*x/span)**2)."""
    q = 4*rise/span
    return span/2*(sqrt(1+q*q)+asinh(q)/q)


def footprint(feature):
    shapes = feature.to_klayout()
    region = kdb.Region()
    for polygon in shapes if isinstance(shapes, tuple) else (shapes,):
        region.insert(polygon.to_itype(feature.project.dbu))
    return region.merged()


class TestCurvedTracksExample(unittest.TestCase):
    def test_parabolic_sampler_thickness_and_parameter_rebuild(self):
        with TemporaryDirectory() as folder:
            original_init, original_layer = Project.__init__, Project.add_layer
            def initialise(project, **options):
                options['output'] = Path(folder)/'curved'
                original_init(project, **options)
            def layer(project, name, **options):
                options['comsol'] = False
                return original_layer(project, name, **options)
            with patch.object(Project, '__init__', initialise), patch.object(Project, 'add_layer', layer), \
                    patch.object(Project, 'show'):
                state = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'examples'/'example_curved_tracks.py'))
            project = state['project']
            for span, rise, width in ((40, 10, 2), (60, 12, 3)):
                state['span'].value, state['rise'].value, state['width'].value = span, rise, width
                project.build()
                path = state['centreline'].to_klayout()
                for point in path.each_point():
                    self.assertAlmostEqual(point.y, rise*(1-(2*point.x/span)**2), delta=1e-10)
                self.assertGreater(path.num_points(), 16)
                for name, height in (('spline_track', rise), ('bezier_track', 1.5*rise)):
                    region = footprint(state[name])
                    self.assertEqual(region.count(), 1)
                    self.assertEqual(next(region.each()).holes(), 0)
                    expected = width*parabola_length(span, height)+pi*(width/2)**2
                    self.assertAlmostEqual(region.area()*project.dbu**2, expected, delta=.03)
                layout = kdb.Layout()
                layout.read(str(project.gds_path))
                exported = kdb.Region(layout.top_cell().begin_shapes_rec(layout.layer(2, 0)))
                self.assertTrue((exported ^ (footprint(state['spline_track']) | footprint(state['bezier_track']))).is_empty())
