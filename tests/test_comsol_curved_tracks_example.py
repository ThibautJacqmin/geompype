"""Native spline/sampler agreement and finite-width tutorial footprints."""

from math import pi
import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from comsol_support import get_client
from geompype import Project
from test_comsol_curves import distance_to_polyline, native_edge_points, selected_measure
from test_curved_tracks_example import footprint, parabola_length


@unittest.skipUnless(os.environ.get('GEOMPYPE_TEST_COMSOL') == '1', 'Native COMSOL opt-in')
class TestComsolCurvedTracksExample(unittest.TestCase):
    def test_spline_matches_sampler_thickened_boundaries_and_saved_parameters(self):
        from jpype import JArray, JDouble, JInt
        client = get_client()
        with TemporaryDirectory() as folder:
            created = []
            original_init = Project.__init__
            def initialise(project, **options):
                options.update(client=client, output=Path(folder)/'curved')
                original_init(project, **options)
                created.append(project)
            try:
                with patch.object(Project, '__init__', initialise), patch.object(Project, 'show'):
                    state = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'examples'/'example_curved_tracks.py'))
                project = state['project']
                boundaries = {}
                for name in ('spline', 'bezier'):
                    boundaries[name] = project.add_selection(name+'_boundary', entity='edge')
                    boundaries[name].add(state[name+'_track'])
                for span, rise, width in ((40, 10, 2), (60, 12, 3)):
                    state['span'].value, state['rise'].value, state['width'].value = span, rise, width
                    project.build()
                    exact = native_edge_points(project.model, state['centreline_selection'])
                    self.assertLess(max(abs(y-rise*(1-(2*x/span)**2)) for x,y,z in exact), 1e-8)
                    sampled = [(p.x, p.y) for p in state['centreline'].to_klayout().each_point()]
                    self.assertLessEqual(max(distance_to_polyline(p, sampled) for p in exact), .00101)
                    self.assertLessEqual(max(distance_to_polyline(p, exact) for p in sampled), .00101)
                    for name, height in (('spline', rise), ('bezier', 1.5*rise)):
                        feature = state[name+'_track']
                        group = state[name+'_selection']
                        self.assertEqual(str(project.workplane.geom().feature(feature.tag).getType()), 'Thicken2D')
                        expected = width*parabola_length(span, height)+pi*(width/2)**2
                        self.assertAlmostEqual(selected_measure(project.model, group).getArea(), expected, delta=.01*expected)
                        region = footprint(feature)
                        contours = []
                        for polygon in region.each():
                            coords = [(p.x*project.dbu, p.y*project.dbu) for p in polygon.each_point_hull()]
                            contours.append(coords+[coords[0]])
                        # Final boundary selections use exact CAD edges, not render-mesh area.
                        edges = boundaries[name].entities()
                        for edge in edges:
                            lo, hi = map(float, project.geometry.edgeParamRange(JInt(edge)))
                            params = JArray(JDouble)([lo+(hi-lo)*i/80 for i in range(1,80)])
                            for point in project.geometry.edgeX(JInt(edge), params):
                                self.assertLessEqual(min(distance_to_polyline(point, c) for c in contours), .005)
                saved = client.load(str(project.mph_path))
                try:
                    actual = native_edge_points(saved, state['centreline_selection'])
                    self.assertLess(max(abs(y-12*(1-(2*x/60)**2)) for x,y,z in actual), 1e-8)
                    self.assertEqual(str(saved.java.param().get('spline_span')), '60[um]')
                finally:
                    client.remove(saved)
            finally:
                for project in created:
                    if project.model is not None:
                        client.remove(project.model)
