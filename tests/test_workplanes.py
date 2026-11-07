"""Planar ownership and live placement parameters without a COMSOL connection."""

import os
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Parameter, Port, PortProfile, Project, Rectangle, connect


class TestWorkplanes(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name)/'planes')

    def test_existing_layers_use_the_default_workplane(self):
        project = self.project
        lower = project.add_layer('lower', comsol=False)
        self.assertEqual(project.default_workplane.tag, 'wp1')
        self.assertEqual(project.default_workplane.name, 'default')
        self.assertIs(project.workplanes['default'], project.default_workplane)
        self.assertIs(lower.workplane, project.default_workplane)
        self.assertIsNone(project.workplane)
        self.assertIsNone(project.default_workplane.native)
        Rectangle(project, layer=lower, size=(4, 2))
        with patch.object(project, '_connect_comsol') as connect:
            project.build()
        connect.assert_not_called()
        self.assertTrue(project.gds_path.exists())
        self.assertIs(project.layout, project.default_workplane.layout)
        self.assertEqual(project.default_workplane.gds_path, project.gds_path)
        self.assertEqual(project.layout.top_cell().name, 'TOP')
        self.assertIsNone(project.model)

    def test_named_workplanes_and_layer_assignment_are_explicit(self):
        project = self.project
        gap = Parameter(500, 'vacuum_gap', unit='nm')
        upper = project.add_workplane('membrane', position=(0, 0, gap))
        a = project.add_layer('membrane_metal', workplane=upper, comsol=False)
        b = project.add_layer('membrane_mask', workplane='membrane', comsol=False)
        self.assertIs(a.workplane, upper)
        self.assertIs(b.workplane, upper)
        self.assertNotEqual(upper.tag, project.default_workplane.tag)
        self.assertIs(project.parameters['vacuum_gap'], gap)
        self.assertIsNone(upper.native)
        with self.assertRaises(ValueError):
            project.add_workplane('membrane')
        with self.assertRaises(ValueError):
            project.add_layer('membrane_metal', workplane=project.default_workplane)

    def test_invalid_workplane_definitions_do_not_register(self):
        project = self.project
        positions = ((1, 2), (1, 2, 3, 4), 'xyz', (0, 0, float('nan')),
                     (0, float('inf'), 0), (0, 0, Parameter(90, 'wrong_z', unit='deg')))
        for position in positions:
            with self.subTest(position=position):
                before = dict(project.workplanes)
                with self.assertRaises((TypeError, ValueError)):
                    project.add_workplane('invalid', position=position)
                self.assertEqual(project.workplanes, before)
        for name in ('', '   ', '../upper', 'with space', 'upper-plane'):
            with self.assertRaises((TypeError, ValueError)):
                project.add_workplane(name)
        with self.assertRaises((TypeError, ValueError)):
            project.add_workplane('wrong_angle', angle=Parameter(2, 'length_angle', unit='um'))

    def test_unknown_or_foreign_workplane_does_not_register_layer(self):
        project = self.project
        other = Project().add_workplane('other')
        for plane in ('missing', other, object()):
            with self.subTest(workplane=plane):
                before = dict(project.layers)
                with self.assertRaises((TypeError, ValueError)):
                    project.add_layer('invalid', workplane=plane)
                self.assertEqual(project.layers, before)

    def test_workplane_parameter_conflicts_are_checked_before_build(self):
        project = self.project
        gap = Parameter(1, 'shared_name', unit='um')
        upper = project.add_workplane('upper', position=(0, 0, gap))
        layer = project.add_layer('upper_metal', workplane=upper, comsol=False)
        with patch.object(project, '_connect_comsol') as connect:
            with self.assertRaises(ValueError):
                Rectangle(project, layer=layer,
                          size=(Parameter(2, 'shared_name', unit='um'), 3))
                project.build()
        connect.assert_not_called()

    def test_cross_workplane_operations_reject_even_coincident_planes(self):
        project = self.project
        upper = project.add_workplane('upper')  # Same height is still a distinct drawing.
        lower = project.add_layer('lower', comsol=False)
        top = project.add_layer('upper', workplane=upper, comsol=False)
        shape = Rectangle(project, layer=lower, size=(4, 4))
        Rectangle(project, layer=top, size=(2, 2))
        count = len(project.objects)
        calls = (
            lambda: project.merge_layers((lower, top), output=lower),
            lambda: project.subtract_layers(lower, top, output=lower),
            lambda: project.intersect_layers((lower, top), output=lower),
            lambda: project.copy_layer(lower, output=top),
            lambda: shape.copy_to(top),
        )
        for call in calls:
            with self.assertRaisesRegex(ValueError, '[Ww]orkplane|[Ww]ork plane'):
                call()
            self.assertEqual(len(project.objects), count)

    def test_port_profile_cannot_mix_physical_planes(self):
        project = self.project
        upper = project.add_workplane('upper', position=(0, 0, 1))
        lower = project.add_layer('lower', comsol=False)
        top = project.add_layer('upper', workplane=upper, comsol=False)
        with self.assertRaisesRegex(ValueError, '[Ww]orkplane|[Ww]ork plane'):
            PortProfile.cpw(2, 1, lower, top)

    def test_user_selection_can_group_both_workplanes(self):
        project = self.project
        upper = project.add_workplane('upper', position=(0, 0, 1))
        lower = project.add_layer('lower', comsol=False, gds=False)
        top = project.add_layer('upper', workplane=upper, comsol=False, gds=False)
        selected = project.add_selection('both_electrodes')
        a = Rectangle(project, layer=lower, size=(4, 4), selections=(selected,))
        b = Rectangle(project, layer=top, size=(2, 2), selections=(selected,))
        project.build()
        self.assertEqual(selected.members, (a, b))
        self.assertEqual(lower.selection.members, (a,))
        self.assertEqual(top.selection.members, (b,))
        self.assertNotEqual(lower.selection.tag, top.selection.tag)
        self.assertIsNone(project.model)

    def test_separate_gds_files_keep_local_drawings_on_identical_layer_numbers(self):
        project = self.project
        gap = Parameter(600, 'gap', unit='nm')
        upper = project.add_workplane('membrane', position=(10, 20, gap), angle=30)
        lower_layer = project.add_layer('lower', comsol=False, gds_layer=1)
        upper_layer = project.add_layer('upper', workplane=upper, comsol=False, gds_layer=1)
        Rectangle(project, layer=lower_layer, size=(4, 2), position=(2, 1))
        Rectangle(project, layer=upper_layer, size=(2, 2), position=(20, 0))
        with patch.object(project, '_connect_comsol') as connection:
            project.build()
        connection.assert_not_called()
        self.assertNotEqual(project.gds_path, upper.gds_path)
        self.assertEqual(upper.gds_path, project.output.with_name('planes_membrane.gds'))
        before = []
        for plane, expected in ((project.default_workplane, (0, 0, 4000, 2000)),
                                (upper, (19000, -1000, 21000, 1000))):
            layout = kdb.Layout()
            layout.read(str(plane.gds_path))
            self.assertEqual([cell.name for cell in layout.top_cells()], ['TOP'])
            self.assertEqual(plane.layout.top_cell().name, 'TOP')
            region = kdb.Region(layout.top_cell().shapes(layout.layer(1, 0)))
            self.assertEqual(region.bbox(), kdb.Box(*expected))
            before.append(region)
        # Assembly position and rotation belong to COMSOL. Fabrication retains
        # each chip's original local coordinates and same numerical layer IDs.
        gap.value = 1200
        upper.position = (100, 200, gap)
        upper.angle = 90
        project.build()
        for plane, expected in zip((project.default_workplane, upper), before):
            actual = kdb.Region(plane.layout.top_cell().shapes(plane.layout.layer(1, 0)))
            self.assertTrue((actual ^ expected).is_empty())

    def test_gds_disabled_plane_has_no_fabrication_file(self):
        project = self.project
        upper = project.add_workplane('upper', position=(0, 0, 1))
        hidden = project.add_workplane('construction', position=(0, 0, 2))
        upper_layer = project.add_layer('upper', workplane=upper, comsol=False)
        hidden_layer = project.add_layer('hidden', workplane=hidden, comsol=False, gds=False)
        Rectangle(project, layer=upper_layer, size=(4, 2))
        Rectangle(project, layer=hidden_layer, size=(10, 10))
        project.build()
        self.assertTrue(project.gds_path.exists())  # Existing default path remains valid.
        self.assertTrue(upper.gds_path.exists())
        self.assertFalse(hidden.gds_path.exists())
        self.assertTrue(project.layout.top_cell().is_empty())

    def test_routes_reject_cross_plane_endpoints_and_obstacles_before_registration(self):
        project = self.project
        upper = project.add_workplane('upper', position=(0, 0, 1))
        lower = project.add_layer('lower', comsol=False)
        top = project.add_layer('upper', workplane=upper, comsol=False)
        lower_profile = PortProfile(widths=(2,), layers=(lower,), names=('wire',))
        top_profile = PortProfile(widths=(2,), layers=(top,), names=('wire',))
        start = Port(pos=(0, 0), orientation=(1, 0), profile=lower_profile)
        end_lower = Port(pos=(20, 0), orientation=(-1, 0), profile=lower_profile)
        end_top = Port(pos=(20, 0), orientation=(-1, 0), profile=top_profile)
        obstacle = Rectangle(project, layer=top, size=(4, 4), position=(100, 100))
        before = tuple(project.objects)
        for call in (lambda: connect(start, end_top),
                     lambda: connect(start, end_lower, obstacles=(obstacle,))):
            with self.assertRaisesRegex(ValueError, '[Ww]orkplane|[Ww]ork plane'):
                call()
            self.assertEqual(tuple(project.objects), before)
        wire = connect(start, end_lower)
        self.assertEqual(wire.length, 20)
        self.assertIs(wire.geometry['wire'].layer.workplane, project.default_workplane)

    def test_two_workplane_example_runs_offline_and_preserves_fabrication_on_gap_edit(self):
        example = Path(__file__).resolve().parents[1] / 'examples'/'example_workplanes.py'
        add_layer = Project.add_layer

        def offline_layer(project, *args, **kwargs):
            kwargs['comsol'] = False
            return add_layer(project, *args, **kwargs)

        previous = Path.cwd()
        try:
            os.chdir(self.folder.name)
            with patch.object(Project, 'add_layer', offline_layer), \
                    patch.object(Project, 'show'), patch('builtins.print'):
                namespace = runpy.run_path(str(example))
            project, upper = namespace['project'], namespace['upper']
            self.assertIsNone(project.model)
            self.assertTrue(project.gds_path.exists())
            self.assertTrue(upper.gds_path.exists())
            lower_metal = kdb.Region(project.layout.top_cell().shapes(project.layout.layer(1, 0)))
            upper_metal = kdb.Region(upper.layout.top_cell().shapes(upper.layout.layer(1, 0)))
            self.assertAlmostEqual(lower_metal.area()*project.dbu**2, 4800)
            self.assertAlmostEqual(upper_metal.area()*project.dbu**2, 2400)
            namespace['gap'].value = 2
            namespace['offset_x'].value = 15
            namespace['upper_angle'].value = 90
            project.build()
            actual = kdb.Region(upper.layout.top_cell().shapes(upper.layout.layer(1, 0)))
            self.assertTrue((actual ^ upper_metal).is_empty())
        finally:
            os.chdir(previous)
