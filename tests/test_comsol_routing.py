"""Native route widths, topology rebuilds and stable layer selections."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import runpy

from comsol_support import get_client
from geompype import Parameter, Project, Rectangle
from geompype.routing import PortProfile, Port, connect
from test_comsol_curves import selected_measure, distance_to_polyline
from test_components import region


@unittest.skipUnless(os.environ.get('GEOMPYPE_TEST_COMSOL') == '1', 'Native COMSOL opt-in')
class TestComsolRouting(unittest.TestCase):
    def test_auto_count_and_live_split_markers_rebuild(self):
        target = Parameter(2000,'target',unit='um')
        width = Parameter(4,'track_width',unit='um')
        profile = PortProfile(widths=[width],layers=[self.layer],offsets=[10],names=['wire'])
        start = Port(profile=profile)
        marker_layer = self.project.add_layer('markers',gds_layer=99)
        marker, = start.draw_markers(layer=marker_layer,tip_scale=1)
        gap_layer = self.project.add_layer('gap',gds_layer=2)
        split, = start.split(gap=3,gap_layer=gap_layer)
        end = Port(pos=(1000,10),orientation=(-1,0),profile=split.profile)
        connection = connect(split,end,radius=20,target_length=target,
                             meander_max_amplitude=100,start_straight=100,end_straight=100)
        self.project.build()
        self.assertEqual(connection.report()['meander_count'],6)
        self.assertAlmostEqual(selected_measure(self.project.model,marker_layer.selection).getArea(),8,delta=.001)
        native = self.project.workplane.geom().feature(marker.tag)
        self.assertIn('track_width',' '.join(str(x) for x in native.getStringArray('x')))
        target.value=2400
        width.value=6
        start.pos=(0,100)
        end.pos=(1000,110)
        self.project.build()
        self.assertEqual(connection.report()['meander_count'],8)
        self.assertAlmostEqual(connection.length,2400,places=7)
        self.assertAlmostEqual(selected_measure(self.project.model,marker_layer.selection).getArea(),18,delta=.001)
        self.assert_native_boundary(connection.geometry['signal'])

    def test_multiple_connections_can_keep_the_default_name(self):
        profile = PortProfile(widths=[4],layers=[self.layer],names=['signal'])
        connections = [connect(Port(pos=(0,y),profile=profile),
                               Port(pos=(100,y),orientation=(-1,0),profile=profile))
                       for y in (0,20)]
        self.project.build()
        geometry = self.project.workplane.geom()
        labels = [str(geometry.feature(c.geometry['signal'].tag).label()) for c in connections]
        self.assertEqual(len(set(labels)),2)
        self.assertAlmostEqual(selected_measure(self.project.model,self.layer.selection).getArea(),800,delta=.001)

    def setUp(self):
        self.client = get_client()
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(client=self.client,output=Path(self.folder.name)/'route')
        self.addCleanup(self.cleanup)
        self.layer = self.project.add_layer('wire')

    def cleanup(self):
        if self.project.model is not None:
            self.client.remove(self.project.model)

    def assert_native_boundary(self, feature):
        """Compare exact CAD edges to GDS contours, independently of getArea's mesh."""
        from jpype import JArray, JDouble, JInt
        group = self.layer.selection_for(entity='edge')
        self.project.build()
        raw = feature.to_klayout()
        contours = []
        for polygon in raw if isinstance(raw,tuple) else (raw,):
            points = [(p.x,p.y) for p in polygon.each_point_hull()]
            contours.append(points+[points[0]])
        geometry = self.project.geometry
        for edge in group.entities():
            bounds = list(map(float,geometry.edgeParamRange(JInt(edge))))
            # Avoid a one-ulp overshoot of a native edge's parameter interval.
            params = JArray(JDouble)([bounds[0]+(bounds[1]-bounds[0])*i/30 for i in range(1,30)])
            for point in geometry.edgeX(JInt(edge),params):
                self.assertLessEqual(min(distance_to_polyline(point,contour) for contour in contours),.005)

    def test_native_thicken_analytic_bend_offsets_and_rebuild(self):
        width = Parameter(4,'width',unit='um')
        profile = PortProfile(widths=[width],offsets=[5],layers=[self.layer],names=['wire'])
        start = Port(profile=profile)
        end = Port(pos=(100,100),orientation=(0,-1),profile=profile.reversed())
        connection = connect(start,end,radius=20,points=[(0,0),(100,0),(100,100)])
        band = connection.geometry['wire']
        for _ in range(2):
            self.project.build()
            native = selected_measure(self.project.model,self.layer.selection).getArea()
            self.assertAlmostEqual(native,region(band).area()*self.project.dbu**2,delta=.3)
            self.assertEqual(str(self.project.workplane.geom().feature(band.tag).getType()),'Thicken2D')
        width.value = 6
        connection.route.points = None
        end.pos = (300,150)
        self.project.build()
        expected = region(band).area()*self.project.dbu**2
        self.assertAlmostEqual(selected_measure(self.project.model,self.layer.selection).getArea(),
                               expected,delta=.005*expected)
        self.assert_native_boundary(band)
        self.assertIn('width',str(self.project.workplane.geom().feature(band.tag).getString('totalthick')))

    def test_taper_meander_and_downstream_transform_after_topology_change(self):
        a = Port(profile=PortProfile(widths=[30],layers=[self.layer]))
        b = Port(pos=(1000,0),orientation=(-1,0),profile=PortProfile(widths=[10],layers=[self.layer]))
        connection = connect(a,b,radius=20,taper_slope=.5,meander_count=2,meander_amplitude=100)
        transformed = connection.features[0].rotate(angle=15)
        self.project.build()
        connection.route.meander_count = 4
        self.project.build()
        expected = region(transformed).area()*self.project.dbu**2
        self.assertAlmostEqual(selected_measure(self.project.model,self.layer.selection).getArea(),
                               expected,delta=.005*expected)
        self.assert_native_boundary(transformed)
        # A later ordinary feature remains after the rebuilt route internals.
        Rectangle(self.project,layer=self.layer,size=(10,10),position=(2000,2000))
        self.project.build()
        self.assertTrue(self.layer.selection.entities())

    def test_flat_routing_example_native_and_parameter_rebuild(self):
        root = Path(__file__).resolve().parents[1] / 'examples'
        created = []
        original = Project.__init__
        def initialise(project, **kwargs):
            kwargs['client'] = self.client
            kwargs['output'] = Path(self.folder.name)/'example'
            original(project, **kwargs)
            created.append(project)
        try:
            with patch.object(Project,'__init__',initialise), patch.object(Project,'show'):
                state = runpy.run_path(str(root/'example_routing.py'))
            project = state['project']
            self.assertTrue(state['feedline'].entities())
            old_length = state['wire'].length
            state['config']['track'].value = 25
            project.build()
            self.assertTrue(project.gds_path.exists())
            self.assertTrue(state['feedline'].entities())
            self.assertGreaterEqual(state['wire'].length,old_length-1e-6)
            native = project.workplane.geom().feature(state['resonator'].geometry['signal'].tag)
            self.assertEqual(str(native.getType()),'Thicken2D')
        finally:
            for project in created:
                if project.model is not None:
                    self.client.remove(project.model)
