"""Native library shapes, vernier layers and nominal wafer outlines."""

from math import asin, fsum, hypot, pi, sqrt
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from comsol_support import get_client
from geompype import Parameter, Project
from geompype.library.box_mark import box_mark
from geompype.library.cross_mark import cross_mark
from geompype.library.four_inch_wafer import four_inch_wafer
from geompype.library.l_mark import l_mark
from geompype.library.three_inch_wafer import three_inch_wafer
from geompype.library.vernier_mark import vernier_mark
from test_comsol_curves import selected_measure


@unittest.skipUnless(os.environ.get('GEOMPYPE_TEST_COMSOL') == '1',
                     'Set GEOMPYPE_TEST_COMSOL=1 to use the COMSOL server.')
class TestComsolLibraryCatalog(unittest.TestCase):
    def setUp(self):
        self.client = get_client()
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.projects = []
        self.addCleanup(self.clean_models)

    def clean_models(self):
        for project in self.projects:
            if project.model is not None:
                self.client.remove(project.model)

    def project(self, name):
        project = Project(client=self.client, output=Path(self.folder.name)/name)
        self.projects.append(project)
        return project

    def assert_area(self, model, selection, expected):
        self.assertAlmostEqual(selected_measure(model, selection).getArea(), expected,
                               delta=max(1e-5, expected*1e-6))

    def assert_bounds(self, model, expected):
        # CAD coordinates avoid the single-precision display bounding box.
        rows = model.java.component('comp1').geom('geom1').getVertexCoord()
        actual = tuple(value for row in rows for value in (min(row), max(row)))
        self.assertEqual(len(actual), 6)
        for value, target in zip(actual, expected):
            self.assertAlmostEqual(value, target, delta=1e-7)

    def assert_layer_selection(self, selection, layer, count):
        self.assertEqual(len(selection.entities()), count)
        self.assertEqual(set(selection.entities()), set(layer.selection.entities()))

    def test_cross_l_and_frame_parameters_upper_workplane_and_saved_geometry(self):
        project = self.project('marks')
        plane = project.add_workplane('upper', position=(7, 11, 4))
        size = Parameter(100, 'mark_size', unit='um')
        width = Parameter(10, 'mark_width', unit='um')
        helpers = {'cross': cross_mark, 'corner': l_mark, 'frame': box_mark}
        groups, layers, shapes = {}, {}, {}
        for index, (name, helper) in enumerate(helpers.items()):
            layers[name] = project.add_layer(name, workplane=plane, gds=False)
            groups[name] = project.add_selection(name)
            shapes[name] = helper(project, layer=layers[name], size=size, width=width,
                                  selections=(groups[name],))
            shapes[name].move(delta=(300*index, 0))
        for s, w in ((100, 10), (120, 12)):
            size.value, width.value = s, w
            project.build()
            for name in helpers:
                self.assert_layer_selection(groups[name], layers[name], 1)
                expected = 2*s*w-w*w if name != 'frame' else s*s-(s-2*w)**2
                self.assert_area(project.model, groups[name], expected)
            self.assert_bounds(project.model, (7-s/2, 607+s/2, 11-s/2, 11+s, 4, 4))
        native = plane.native.geom()
        for name in ('cross', 'corner'):
            feature = native.feature(shapes[name].tag)
            self.assertEqual(str(feature.getType()), 'Polygon')
            coordinates = ' '.join(map(str, feature.getStringArray('x')))
            self.assertIn('mark_size', coordinates)
            self.assertIn('mark_width', coordinates)
        frame = shapes['frame']
        self.assertEqual(str(native.feature(frame.tag).getType()), 'Difference')
        self.assertTrue(all(str(native.feature(obj.tag).getType()) == 'Square'
                            for obj in frame.inputs))
        project.model.java.param().set('mark_width', '8[um]')
        project.geometry.run()
        for name in helpers:
            expected = 2*120*8-8**2 if name != 'frame' else 120**2-104**2
            self.assert_area(project.model, groups[name], expected)
        project.model.save(str(project.mph_path))
        saved = self.client.load(str(project.mph_path))
        try:
            self.assertEqual(str(saved.java.param().get('mark_width')), '8[um]')
            self.assert_area(saved, groups['frame'], 120**2-104**2)
            self.assert_bounds(saved, (-53, 667, -49, 131, 4, 4))
        finally:
            self.client.remove(saved)

    def test_vernier_native_rows_layer_selection_and_live_resolution(self):
        project = self.project('vernier')
        plane = project.add_workplane('upper', position=(5, 7, 9))
        reference = project.add_layer('reference', workplane=plane, gds=False)
        moving = project.add_layer('moving', workplane=plane, gds=False)
        selected = project.add_selection('complete_pair')
        reference_group = project.add_selection('reference_ticks')
        moving_group = project.add_selection('moving_ticks')
        pitch = Parameter(10, 'tick_pitch', unit='um')
        resolution = Parameter(1, 'tick_resolution', unit='um')
        width = Parameter(2, 'tick_width', unit='um')
        length = Parameter(20, 'tick_length', unit='um')
        gap = Parameter(4, 'row_gap', unit='um')
        mark = vernier_mark(project, reference_layer=reference, moving_layer=moving,
                            pitch=pitch, resolution=resolution, width=width,
                            length=length, gap=gap, selections=(selected,))
        rows = dict(mark.geometry)
        reference_group.add(rows['reference'])
        moving_group.add(rows['moving'])
        mark.rotate(90).move((100, 200))
        for p, r, w, h, g in ((10, 1, 2, 20, 4), (12, .5, 3, 30, 6)):
            pitch.value, resolution.value, width.value = p, r, w
            length.value, gap.value = h, g
            project.build()
            self.assert_layer_selection(reference_group, reference, 11)
            self.assert_layer_selection(moving_group, moving, 11)
            self.assertFalse(set(reference_group.entities()) & set(moving_group.entities()))
            self.assertEqual(set(selected.entities()),
                             set(reference_group.entities()) | set(moving_group.entities()))
            self.assert_area(project.model, selected, 22*w*h)
            self.assert_bounds(project.model, (105-g/2-h, 105+g/2+h,
                                                207-5*p-w/2, 207+5*p+w/2, 9, 9))
        native = plane.native.geom()
        for row in rows.values():
            self.assertEqual(str(native.feature(row.tag).getType()), 'Union')
            self.assertTrue(all(str(native.feature(tick.tag).getType()) == 'Rectangle'
                                for tick in row.inputs))
        first_moving_tick = rows['moving'].inputs[0]
        expression = ' '.join(map(str, native.feature(first_moving_tick.tag).getStringArray('pos')))
        self.assertIn('tick_pitch', expression)
        self.assertIn('tick_resolution', expression)
        project.model.java.param().set('tick_width', '1.5[um]')
        project.model.java.param().set('tick_resolution', '1[um]')
        project.geometry.run()
        self.assert_area(project.model, reference_group, 11*1.5*30)
        self.assert_area(project.model, moving_group, 11*1.5*30)
        self.assert_bounds(project.model, (72, 138, 146.25, 267.75, 9, 9))
        project.model.save(str(project.mph_path))
        saved = self.client.load(str(project.mph_path))
        try:
            self.assert_area(saved, selected, 22*1.5*30)
            self.assertEqual(len(saved.java.component('comp1').selection(selected.tag).entities()), 22)
        finally:
            self.client.remove(saved)

    def test_nominal_wafers_flat_coordinates_live_scale_and_saved_polygon(self):
        for helper, radius, primary, secondary, flats in (
                (three_inch_wafer, 38100, 22220, 11180, 1),
                (four_inch_wafer, 50000, 32500, 18000, 2)):
            with self.subTest(helper=helper.__name__, flats=flats):
                project = self.project(helper.__name__)
                plane = project.add_workplane('wafer_plane', position=(7, 11, 4))
                layer = project.add_layer('wafer', workplane=plane, gds=False)
                selected = project.add_selection('wafer_outline')
                scale = Parameter(.01, 'wafer_scale')
                wafer = helper(project, layer=layer, flats=flats, selections=(selected,))
                wafer.scale(factor=scale).rotate(angle=90).move(delta=(100, 200))
                points = wafer.vertices.value
                top = sqrt(radius*radius-(primary/2)**2)
                left = -sqrt(radius*radius-(secondary/2)**2) if flats == 2 else -radius
                for x, y in points:
                    self.assertAlmostEqual(hypot(x, y), radius, delta=1e-7)
                    self.assertLessEqual(y, top+1e-7)
                    self.assertGreaterEqual(x, left-1e-7)
                top_x = [x for x, y in points if abs(y-top) < 1e-7]
                self.assertAlmostEqual(max(top_x)-min(top_x), primary, delta=1e-7)
                if flats == 2:
                    side_y = [y for x, y in points if abs(x-left) < 1e-7]
                    self.assertAlmostEqual(max(side_y)-min(side_y), secondary, delta=1e-7)
                polygon_area = abs(fsum(a[0]*b[1]-b[0]*a[1]
                                        for a, b in zip(points, points[1:]+points[:1])))/2
                exact_area = pi*radius*radius
                for flat in ((primary, secondary) if flats == 2 else (primary,)):
                    half = flat/2
                    exact_area -= radius*radius*asin(half/radius)-half*sqrt(radius*radius-half*half)
                self.assertLessEqual(polygon_area, exact_area+1e-5)
                self.assertLess(exact_area-polygon_area, 2*pi*radius)
                for factor in (.01, .02):
                    scale.value = factor
                    project.build()
                    self.assert_layer_selection(selected, layer, 1)
                    self.assert_area(project.model, selected, polygon_area*factor*factor)
                    self.assert_bounds(project.model, (107-factor*top, 107+factor*radius,
                                                        211+factor*left, 211+factor*radius, 4, 4))
                    feature = plane.native.geom().feature(wafer.tag)
                    self.assertEqual(str(feature.getType()), 'Polygon')
                    self.assertEqual(list(feature.getStringArray('x')), wafer.vertices.comsol_string_x())
                    self.assertEqual(list(feature.getStringArray('y')), wafer.vertices.comsol_string_y())
                project.model.java.param().set('wafer_scale', '0.03')
                project.geometry.run()
                self.assert_area(project.model, selected, polygon_area*.03**2)
                self.assert_bounds(project.model, (107-.03*top, 107+.03*radius,
                                                    211+.03*left, 211+.03*radius, 4, 4))
                project.model.save(str(project.mph_path))
                saved = self.client.load(str(project.mph_path))
                try:
                    self.assert_area(saved, selected, polygon_area*.03**2)
                    self.assert_bounds(saved, (107-.03*top, 107+.03*radius,
                                               211+.03*left, 211+.03*radius, 4, 4))
                    geometry = saved.java.component('comp1').geom('geom1').feature(plane.tag).geom()
                    self.assertEqual(list(geometry.feature(wafer.tag).getStringArray('x')),
                                     wafer.vertices.comsol_string_x())
                    self.assertEqual(list(geometry.feature(wafer.tag).getStringArray('y')),
                                     wafer.vertices.comsol_string_y())
                finally:
                    self.client.remove(saved)
