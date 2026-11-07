"""Coordinate integrity and geometry behavior of the packaged library helpers."""

from importlib.resources import files
from hashlib import sha256
from math import sqrt
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Parameter, Polygon, Project, Union
from geompype.library import x_diamond_mark, two_inch_wafer


def asset(name):
    return json.loads(files('geompype.library').joinpath('data', name + '.json').read_text(encoding='utf-8'))


def region(feature):
    geometries = feature.to_klayout()
    if not isinstance(geometries, tuple):
        geometries = (geometries,)
    result = kdb.Region()
    for geometry in geometries:
        result.insert(geometry.to_itype(feature.project.dbu))
    return result.merged()


def read_region(path, layer=1):
    layout = kdb.Layout()
    layout.read(str(path))
    return kdb.Region(layout.top_cell().shapes(layout.layer(layer, 0))).merged()


class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name)/'library')
        self.layer = self.project.add_layer('library', comsol=False, gds_layer=1)

    def test_packaged_contours_retain_units_names_and_vertex_counts(self):
        # Freeze every coordinate and its order, including sampled rounded tips.
        coordinate_digests = {
            'cross': 'd1ea7c13546ca85d6bdd6d84b846b976993dbdb34a1d774bbcf20d2dd4578def',
            'diamond1': 'abc70168e3bae73577013248a3f6a1cb5583f4a44b14e90001c19a555e52323a',
            'diamond2': '1965bc2997b08e9ebc238e7cc346a7d2bf8d6c5aae036f1fe491ea12bb6ea005',
            'diamond3': 'bd5a3b7ea6c285c7d54a6ed26825b59cdbdb667dc9ab7fd7ae9c306531c712bf',
            'diamond4': 'b77ea3cb8c33174e9923fbc3838da4ae29ab77b30f1539ca89d75057de34e914',
        }
        expected = (
            ('x_diamond_mark',
             {'cross': 368, 'diamond1': 130, 'diamond2': 130, 'diamond3': 130, 'diamond4': 130}),
        )
        for name, counts in expected:
            with self.subTest(asset=name):
                data = asset(name)
                self.assertEqual(data['unit'], 'um')
                self.assertEqual({key: len(points) for key, points in data['polygons'].items()}, counts)
                for field, points in data['polygons'].items():
                    encoded = json.dumps(points, separators=(',', ':')).encode()
                    self.assertEqual(sha256(encoded).hexdigest(), coordinate_digests[field])

    def test_x_diamond_mark_is_one_output_with_five_parts(self):
        from geompype import x_diamond_mark as public_mark
        self.assertIs(public_mark, x_diamond_mark)
        selected = self.project.add_selection('mark')
        mark = x_diamond_mark(self.project, layer=self.layer, selections=(selected,))
        self.assertIsInstance(mark, Union)
        self.assertFalse(mark.keep)
        self.assertEqual(len(mark.inputs), 5)
        for part, points in zip(mark.inputs, asset('x_diamond_mark')['polygons'].values()):
            self.assertIsInstance(part, Polygon)
            self.assertEqual(part.vertices.value, points)
        expected = region(mark)
        self.assertEqual(expected.count(), 5)
        self.assertEqual(expected.bbox(), kdb.Box(-87546, -87546, 87546, 87546))
        self.assertEqual(self.layer.selection.members, (mark,))
        self.assertEqual(selected.members, (mark,))
        self.project.build()
        self.assertTrue((read_region(self.project.gds_path) ^ expected).is_empty())

    def test_parameter_transforms_and_arrays_keep_all_mark_parts(self):
        mark = x_diamond_mark(self.project, layer=self.layer)
        scale = Parameter(1, 'mark_scale')
        angle = Parameter(90, 'mark_angle', unit='deg')
        shift = Parameter(200, 'mark_x', unit='um')
        placed = mark.scale(factor=scale).rotate(angle=angle).move(delta=(shift, 300))
        copies = placed.array(size=2, displacement=(500, 0))
        self.project.build()
        self.assertEqual(read_region(self.project.gds_path).count(), 10)
        self.assertEqual(region(copies).bbox(), kdb.Box(112454, 212454, 787546, 387546))
        scale.value, shift.value = 2, 400
        self.project.build()
        actual = read_region(self.project.gds_path)
        self.assertEqual(actual.count(), 10)
        self.assertEqual(actual.bbox(), kdb.Box(224908, 124908, 1075092, 475092))
        self.assertTrue((actual ^ region(copies)).is_empty())
        self.assertIs(self.project.parameters['mark_scale'], scale)
        self.assertIs(self.project.parameters['mark_x'], shift)
        self.assertIs(self.project.parameters['mark_angle'], angle)

    def test_x_diamond_mark_builds_once_in_live_mode(self):
        self.project.live = True
        with patch.object(self.project, 'build') as build:
            mark = x_diamond_mark(self.project, layer=self.layer)
        build.assert_called_once()
        self.assertTrue(self.project.live)
        self.assertEqual(self.layer.selection.members, (mark,))

    def test_repeated_mark_instances_have_independent_vertices(self):
        first = x_diamond_mark(self.project, layer=self.layer)
        second = x_diamond_mark(self.project, layer=self.layer)
        original = second.inputs[0].vertices.value[0]
        first.inputs[0].vertices[0, 0] = -86.57
        self.assertEqual(second.inputs[0].vertices.value[0], original)

    def test_wafer_preserves_sampled_contour_and_workplane_local_coordinates(self):
        from geompype import two_inch_wafer as public_wafer
        self.assertIs(public_wafer, two_inch_wafer)
        plane = self.project.add_workplane('wafer', position=(100, 200, 3), angle=90)
        layer = self.project.add_layer('wafer_edge', workplane=plane, comsol=False, gds_layer=1)
        selected = self.project.add_selection('wafer')
        wafer = two_inch_wafer(self.project, layer=layer, selections=(selected,))
        self.assertIsInstance(wafer, Polygon)
        height = sqrt(25400**2 - 7940**2)
        self.assertGreater(len(wafer.vertices), 100)
        self.assertEqual(layer.selection.members, (wafer,))
        self.assertEqual(selected.members, (wafer,))
        expected = region(wafer)
        self.assertEqual(expected.bbox(), kdb.Box(-25400000, -25400000, 25400000, round(height*1000)))
        self.project.build()
        actual = read_region(plane.gds_path)
        self.assertEqual(actual.count(), 1)
        self.assertTrue((actual ^ expected).is_empty())
        self.assertTrue(read_region(self.project.gds_path).is_empty())
        self.assertIsNone(self.project.model)

