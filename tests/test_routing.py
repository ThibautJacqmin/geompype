"""Ports, native-ready route bands, widths, tapers, parameters and collisions."""
from math import pi
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as kdb
from geompype import Parameter, Project, Rectangle, Vertices
from geompype.routing import Port, PortProfile, connect


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Project(output=Path(self.tmp.name)/'route')
        self.signal = self.project.add_layer('signal',comsol=False,gds_layer=1)
        self.gap = self.project.add_layer('gap',comsol=False,gds_layer=2)

    def profile(self,track=10,gap=5):
        return PortProfile.cpw(track,gap,self.signal,self.gap)

    def test_rounded_band_width_area_and_boolean(self):
        profile = self.profile()
        a = Port(pos=(0,0),orientation=(1,0),profile=profile)
        b = Port(pos=(100,100),orientation=(0,-1),profile=profile)
        conn = connect(a,b,points=[(0,0),(100,0),(100,100)],radius=20)
        self.assertAlmostEqual(conn.length,160+10*pi)
        self.assertEqual(conn.geometry['signal'].path().width,10)
        self.assertAlmostEqual(conn.geometry['signal'].to_klayout().area(),10*conn.length,delta=.1)
        self.assertAlmostEqual(conn.geometry['gap'].to_klayout().area(),20*conn.length,delta=.1)
        cut = Rectangle(self.project,layer=self.signal,size=(20,20),position=(20,0))
        result = conn.geometry['signal'].difference(cut)
        self.project.build()
        self.assertTrue(self.project.gds_path.exists())
        polygons = result.to_klayout()
        self.assertGreater(sum(p.area() for p in polygons),1000)

    def test_parameter_and_reversed_port_remain_live(self):
        x = Parameter(300,'x',unit='um')
        width = Parameter(10,'width',unit='um')
        profile = self.profile(width)
        start = Port(profile=profile)
        end = Port(pos=(x,0),orientation=(1,0),profile=profile)
        conn = connect(start,end.reversed())
        self.assertEqual(conn.length,300)
        x.value=400
        width.value=20
        self.project.build()
        self.assertEqual(conn.length,400)
        self.assertEqual(conn.geometry['signal'].path().width,20)
        self.assertIn('width',self.project.parameters)

    def test_unequal_profiles_taper_length(self):
        a = Port(profile=self.profile(100,50))
        b = Port(pos=(1000,0),orientation=(-1,0),profile=self.profile(10,5))
        conn = connect(a,b,taper_slope=.5)
        self.assertAlmostEqual(conn.report()['taper_length_um'],180)
        self.assertAlmostEqual(conn.length,1000)
        self.assertAlmostEqual(conn.geometry['signal'].to_klayout().area(),180*55+820*10,delta=.01)

    def test_asymmetric_profile_uses_destination_travel_frame(self):
        profile = PortProfile(widths=[4],offsets=[5],layers=[self.signal],names=['wire'])
        a = Port(profile=profile)
        b = Port(pos=(100,100),orientation=(0,-1),profile=profile.reversed())
        conn = connect(a,b,points=[(0,0),(100,0),(100,100)],radius=20)
        self.assertEqual(conn.report()['taper_length_um'],0)
        self.assertAlmostEqual(conn.geometry['wire'].to_klayout().area(),4*(160+7.5*pi),delta=.05)

    def test_waypoint_target_length_and_clearance(self):
        profile = self.profile()
        a = Port(profile=profile)
        b = Port(pos=(1000,0),orientation=(-1,0),profile=profile)
        conn = connect(a,b,radius=20,meander_count=4,target_length=2000)
        self.assertAlmostEqual(conn.length,2000,places=7)
        self.project.build()
        route = connect(a,b,via=[Port(pos=(500,100),orientation=(1,0))],radius=30)
        self.assertGreater(route.length,1000)
        obstacle = Rectangle(self.project,layer=self.signal,size=(20,20),position=(500,0))
        blocked = connect(a,b,obstacles=[obstacle])
        with self.assertRaisesRegex(ValueError,'intersects obstacle'):
            blocked.geometry['signal'].validate()

    def test_invalid_radius_and_mismatched_layers(self):
        a = Port(profile=self.profile())
        b = Port(pos=(100,100),orientation=(0,-1),profile=self.profile())
        with self.assertRaisesRegex(ValueError,'collapses'):
            connect(a,b,points=[(0,0),(100,0),(100,100)],radius=5)

    def test_cross_project_profiles_and_mutated_clearance(self):
        other = Project()
        other_signal = other.add_layer('signal',comsol=False,gds_layer=1)
        other_gap = other.add_layer('gap',comsol=False,gds_layer=2)
        a = Port(profile=self.profile())
        b = Port(pos=(100,0),orientation=(-1,0),
                 profile=PortProfile.cpw(10,5,other_signal,other_gap))
        with self.assertRaisesRegex(ValueError,'matching named bands and layers'):
            connect(a,b)
        gap = Parameter(5,'clearance',unit='um')
        profile = self.profile(gap=gap)
        b.profile = profile.reversed()
        a.profile = profile
        connection = connect(a,b)
        gap.value = -1  # Overall enclosing width is still positive.
        with self.assertRaisesRegex(ValueError,'gap and mask margin'):
            connection.route.resolve()

    def test_explicit_and_meander_paths_respect_launch_straights(self):
        a = Port(profile=self.profile())
        b = Port(pos=(100,100),orientation=(0,-1),profile=self.profile())
        with self.assertRaisesRegex(ValueError,'minimum straight'):
            connect(a,b,points=[(0,0),(100,0),(100,100)],radius=20,start_straight=90)
        b.pos, b.orientation = (1000,0), (-1,0)
        with self.assertRaisesRegex(ValueError,'minimum straight'):
            connect(a,b,radius=20,meander_count=4,meander_amplitude=100,start_straight=100)
