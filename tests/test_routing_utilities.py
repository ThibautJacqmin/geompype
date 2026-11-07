"""Port frames, live fan-outs/markers and bounded automatic length fitting."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from geompype import Parameter, Port, PortProfile, Project, Vertices, connect
from geompype.components import Component
from geompype.parameters import evaluate


class TestRoutingUtilities(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name)/'utilities')
        self.signal = self.project.add_layer('signal', comsol=False, gds_layer=1)
        self.gap = self.project.add_layer('gap', comsol=False, gds_layer=2)
        self.marker = self.project.add_layer('markers', comsol=False, gds_layer=3)

    def test_local_frame_edges_and_live_coordinates(self):
        offset = Parameter(5, 'offset', unit='um')
        profile = PortProfile(widths=[4], offsets=[offset], layers=[self.signal], names=['wire'])
        port = Port(pos=(10, 20), orientation=(0, 2), profile=profile)
        self.assertEqual(port.normal, (-1, 0))
        self.assertEqual(port.local_point(3, 2).value, [[8, 23]])
        center = port.track_center('wire', along=3)
        self.assertEqual(center.value, [[5, 23]])
        upper, lower = port.track_edges(0)
        self.assertEqual(upper.value, [[3, 20]])
        self.assertEqual(lower.value, [[7, 20]])
        self.assertEqual(port.bond_params(), (7, 3))
        offset.value = -5
        self.assertEqual(center.value, [[15, 23]])
        self.assertEqual(port.bond_params(), (-3, -7))

    def test_arbitrary_mask_keeps_extrema_live(self):
        offset = Parameter(8, 'offset', unit='um')
        margin = Parameter(2, 'margin', unit='um')
        source = PortProfile(widths=[4, 6], offsets=[-5, offset],
                             layers=[self.signal]*2, names=['a', 'b'])
        profile = source.with_mask(self.marker, margin=margin)
        self.assertAlmostEqual(evaluate(profile.widths[-1], 'um'), 22)
        self.assertAlmostEqual(evaluate(profile.offsets[-1], 'um'), 2)
        offset.value = -12  # The same band changes from the upper to lower extreme.
        self.assertAlmostEqual(evaluate(profile.widths[-1], 'um'), 16)
        self.assertAlmostEqual(evaluate(profile.offsets[-1], 'um'), -9)
        reversed_profile = profile.reversed()
        self.assertAlmostEqual(evaluate(reversed_profile.offsets[-1], 'um'), 9)
        margin.value = -1
        with self.assertRaisesRegex(ValueError, 'margin'):
            reversed_profile.validate()

    def test_split_follows_component_placement_and_dimensions(self):
        offset = Parameter(15, 'offset', unit='um')
        width = Parameter(4, 'width', unit='um')
        source = PortProfile(widths=[width, 8], offsets=[offset, -20],
                             layers=[self.signal]*2, names=['left', 'right'])
        port = Port(profile=source, name='bus')
        left, right = port.split(['left', 'right'], gap=3, gap_layer=self.gap)
        self.assertEqual(left.position, (0, 15))
        self.assertEqual(right.position, (0, -20))
        reverse = left.r
        component = Component(self.project, ports={'bus': port})
        component.rotate(90).move((100, 200))
        self.assertAlmostEqual(left.position[0], 85)
        self.assertAlmostEqual(left.position[1], 200)
        self.assertAlmostEqual(reverse.direction[1], -1)
        offset.value = 25
        width.value = 10
        self.assertAlmostEqual(left.position[0], 75)
        self.assertEqual([evaluate(w, 'um') for w in left.profile.widths], [10, 16])
        self.assertIs(reverse.r, left)

    def test_markers_follow_ports_and_export_as_polygons(self):
        width = Parameter(12, 'width', unit='um')
        port = Port(profile=PortProfile(widths=[width], layers=[self.signal]))
        selection = self.project.add_selection('port_markers')
        marker, = port.draw_markers(layer=self.marker, tip_scale=.5, selections=[selection])
        self.assertEqual(marker.to_klayout().area(), 36)
        port.pos = (10, 20)  # A reassigned raw pair must retain the default um units.
        port.orientation = (0, 1)
        width.value = 20
        self.project.build()
        box = marker.to_klayout().bbox()
        self.assertEqual((box.left, box.bottom, box.right, box.top), (0, 20, 20, 30))
        self.assertEqual(marker.to_klayout().area(), 100)
        self.assertIn('width', self.project.parameters)
        self.assertTrue(self.project.gds_path.exists())

    def test_split_markers_follow_raw_position_assignment_and_component_movement(self):
        offset = Parameter(5, 'offset', unit='um')
        profile = PortProfile(widths=[4], offsets=[offset], layers=[self.signal])
        source = Port(profile=profile)
        split, = source.split(gap=3, gap_layer=self.gap)
        marker, = split.draw_markers(layer=self.marker, bands='signal', tip_scale=.5)
        source.pos = (30, 40)
        self.project.build()
        self.assertEqual(source.local_point(2, 3).value, [[32, 43]])
        self.assertEqual(split.position, (30, 45))
        box = marker.to_klayout().bbox()
        self.assertEqual((box.left, box.bottom, box.right, box.top), (30, 43, 32, 47))
        component = Component(self.project, ports={'source': source})
        component.rotate(90).move((100, 200))
        offset.value = 7
        self.project.build()
        box = marker.to_klayout().bbox()
        for actual, expected in zip((box.left, box.bottom, box.right, box.top), (51, 230, 55, 232)):
            self.assertAlmostEqual(actual, expected, places=8)

    def test_invalid_port_helpers_do_not_register_geometry(self):
        port = Port(profile=PortProfile(widths=[4], layers=[self.signal], names=['a']))
        for bands in (['missing'], [-1], [True], ['a', 'a']):
            with self.assertRaises(ValueError):
                port.split(bands, gap_layer=self.gap)
        before = len(self.project.objects)
        with self.assertRaisesRegex(ValueError, 'positive'):
            port.draw_markers(layer=self.marker, tip_length=0)
        with self.assertRaisesRegex(ValueError, 'nonnegative'):
            port.split(gap=-1, gap_layer=self.gap)
        other_plane = self.project.add_workplane('upper')
        other_layer = self.project.add_layer('upper', workplane=other_plane, comsol=False)
        with self.assertRaisesRegex(ValueError, 'workplane'):
            port.draw_markers(layer=other_layer)
        self.assertEqual(len(self.project.objects), before)

    def ports(self):
        profile = PortProfile.cpw(10, 5, self.signal, self.gap)
        return Port(profile=profile), Port(pos=(1000, 0), orientation=(-1, 0), profile=profile)

    def test_automatic_count_fits_target_and_rebuilds(self):
        target = Parameter(2000, 'target', unit='um')
        connection = connect(*self.ports(), radius=20, target_length=target,
                             meander_max_amplitude=100, start_straight=100, end_straight=100)
        report = connection.report()
        self.assertEqual(report['meander_count'], 6)
        self.assertLessEqual(report['meander_amplitude_um'], 100)
        self.assertAlmostEqual(connection.length, 2000, places=8)
        path, _, _ = connection.route.resolve()
        self.assertGreaterEqual(path.pieces[0].length, 100-1e-8)
        self.assertGreaterEqual(path.pieces[-1].length, 100-1e-8)
        self.project.build()
        target.value = 2400
        self.project.build()
        self.assertEqual(connection.report()['meander_count'], 8)
        self.assertAlmostEqual(connection.length, 2400, places=8)
        self.assertIn('target', self.project.parameters)

    def test_auto_target_base_shorter_impossible_and_explicit_count(self):
        ports = self.ports()
        straight = connect(*ports, radius=20, target_length=1000)
        self.assertEqual(straight.report()['meander_count'], 0)
        one = connect(*ports, radius=20, target_length=2000)
        self.assertEqual(one.report()['meander_count'], 1)
        with self.assertRaisesRegex(ValueError, 'shorter than the base'):
            connect(*ports, radius=20, target_length=999)
        with self.assertRaisesRegex(ValueError, 'Cannot fit target'):
            connect(*ports, radius=20, target_length=2000, meander_max_amplitude=30)
        with self.assertRaisesRegex(ValueError, 'positive meander_count'):
            connect(*ports, radius=20, target_length=2000, meander_count=0)
        fixed = connect(*ports, radius=20, target_length=2000, meander_count=4)
        self.assertEqual(fixed.report()['meander_count'], 4)
        self.assertAlmostEqual(fixed.length, 2000, places=8)

    def test_automatic_offset_and_failed_rebuild_leave_previous_gds(self):
        maximum = Parameter(150, 'maximum', unit='um')
        connection = connect(*self.ports(), radius=20, target_length=2100,
                             meander_offset=15, meander_max_amplitude=maximum)
        self.project.build()
        self.assertAlmostEqual(connection.length, 2100, places=8)
        old = self.project.gds_path.read_bytes()
        maximum.value = 30
        with self.assertRaisesRegex(ValueError, 'Cannot fit target'):
            self.project.build()
        self.assertEqual(self.project.gds_path.read_bytes(), old)
