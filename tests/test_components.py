"""Generic component placement using synthetic rectangles and named ports."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Parameter, Port, PortProfile, Project, Rectangle, connect
from geompype.components import Component


def region(feature):
    geometries = feature.to_klayout()
    if not isinstance(geometries, tuple):
        geometries = (geometries,)
    result = kdb.Region()
    for geometry in geometries:
        if isinstance(geometry, kdb.DPath):
            geometry = geometry.polygon()
        result.insert(geometry.to_itype(feature.project.dbu))
    return result.merged()


class TestComponents(unittest.TestCase):
    def test_nested_assembly_checks_parameter_conflicts_at_exit(self):
        from geompype.components import _assembly
        with self.assertRaisesRegex(ValueError,'Conflicting parameters'):
            with _assembly(self.project):
                Rectangle(self.project,layer=self.layer,size=(Parameter(10,'duplicate',unit='um'),10))
                with _assembly(self.project):
                    Rectangle(self.project,layer=self.layer,size=(Parameter(20,'duplicate',unit='um'),10))
        self.assertFalse(self.project._defer_parameter_checks)
        self.assertFalse(self.project.live)

    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name)/'components')
        self.layer = self.project.add_layer('shapes', comsol=False, gds_layer=1)

    def rectangle_component(self, width=20, height=10):
        shape = Rectangle(self.project, layer=self.layer, size=(width, height))
        profile = PortProfile(widths=[height], layers=[self.layer], names=['signal'])
        port = Port(pos=(width/2, 0), orientation=(1, 0), profile=profile)
        return Component(self.project, geometry={'rectangle': shape},
                         ports={'right': port}, name='rectangle')

    def assert_point(self, actual, expected):
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=9)

    def test_component_move_keeps_existing_port_reference(self):
        component = self.rectangle_component()
        port = component.ports['right']
        component.rotate(90).move((100, 200))
        self.assertIs(port, component.ports['right'])
        self.assert_point(port.position, (100, 210))
        self.assert_point(port.orientation, (0, 1))
        self.assertEqual(region(component.geometry['rectangle']).bbox(),
                         kdb.Box(95000, 190000, 105000, 210000))

    def test_parameter_dimensions_and_placement_remain_live(self):
        width = Parameter(20, 'width', unit='um')
        shift = Parameter(30, 'shift', unit='um')
        component = self.rectangle_component(width=width)
        component.place(position=(shift, 40), orientation=(0, 1))
        self.assert_point(component.ports['right'].position, (30, 50))
        width.value, shift.value = 40, 70
        self.project.build()
        self.assert_point(component.ports['right'].position, (70, 60))
        self.assertAlmostEqual(region(component.geometry['rectangle']).area()*self.project.dbu**2, 400)
        self.assertIn('width', self.project.parameters)

    def test_existing_connection_follows_component_port(self):
        component = self.rectangle_component(height=4)
        port = component.ports['right']
        end = Port(pos=(100, 0), orientation=(-1, 0), profile=port.profile)
        connection = connect(port, end)
        self.assertAlmostEqual(connection.length, 90)
        component.move((20, 0))
        self.project.build()
        self.assertAlmostEqual(connection.length, 70)
        self.assertEqual(region(connection.geometry['signal']).bbox(),
                         kdb.Box(30000, -2000, 100000, 2000))

    def test_live_placement_is_built_once_after_ports_are_ready(self):
        component = self.rectangle_component()
        self.project.live = True
        with patch.object(self.project, 'build') as build:
            component.place(position=(30, 50), orientation=(0, 1))
        build.assert_called_once()
        self.assertTrue(self.project.live)
        self.assert_point(component.ports['right'].position, (30, 60))

    def test_shared_geometry_aliases_are_transformed_once(self):
        component = self.rectangle_component()
        component.geometry['alias'] = component.geometry['rectangle']
        component.move((7, 9))
        self.assertIs(component.geometry['alias'], component.geometry['rectangle'])
        self.assertEqual(len(component.features), 1)
        self.assertEqual(region(component.features[0]).bbox(), kdb.Box(-3000, 4000, 17000, 14000))

    def test_port_only_component_rotates_and_translates(self):
        port = Port(pos=(4, 0), orientation=(1, 0))
        component = Component(self.project, ports={'anchor': port})
        component.place(position=(10, 20), orientation=(-1, 0))
        self.assertIs(component.ports['anchor'], port)
        self.assert_point(port.position, (6, 20))
        self.assert_point(port.orientation, (-1, 0))
        self.assertEqual(component.features, ())

    def test_moving_consumed_component_is_rejected(self):
        component = self.rectangle_component()
        component.geometry['rectangle'].move(delta=(100, 0))
        original_position = component.ports['right'].position
        with self.assertRaisesRegex(ValueError, 'before consuming'):
            component.move((1, 0))
        self.assertEqual(component.ports['right'].position, original_position)

    def test_foreign_geometry_and_invalid_placement_are_rejected(self):
        component = self.rectangle_component()
        other = Project(output=Path(self.folder.name)/'other')
        with self.assertRaisesRegex(ValueError, 'belong'):
            Component(other, geometry=component.geometry)
        with self.assertRaises(ValueError):
            component.place(orientation=(0, 0))
        self.assert_point(component.ports['right'].position, (10, 0))
