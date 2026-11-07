"""Nominal wafer dimensions, orientation flats, sampling and live placement."""

from math import asin, cos, fsum, hypot, nextafter, pi, radians, sin, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import Parameter, Polygon, Project
from geompype.library.two_inch_wafer import two_inch_wafer
from geompype.library.three_inch_wafer import three_inch_wafer
from geompype.library.four_inch_wafer import four_inch_wafer


def area(points):
    return abs(fsum(a[0]*b[1]-b[0]*a[1]
                    for a, b in zip(points, points[1:]+points[:1])))/2


def cap_area(radius, flat):
    half = flat/2
    return radius*radius*asin(half/radius)-half*sqrt(radius*radius-half*half)


def bounds(points):
    return (min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points))


def read_region(path, layer):
    layout = kdb.Layout()
    layout.read(str(path))
    return kdb.Region(layout.top_cell().shapes(layout.layer(layer, 0))).merged()


class TestWaferLibrary(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name)/'wafer')
        self.layer = self.project.add_layer('outline', gds_layer=7, comsol=False)

    def assert_bounds(self, actual, expected):
        for value, target in zip(actual, expected):
            self.assertAlmostEqual(value, target, delta=1e-8)

    def test_nominal_diameters_one_and_two_flats_and_chord_bound(self):
        for helper, diameter, primary, secondary in (
                (two_inch_wafer, 50800, 15880, 8000),
                (three_inch_wafer, 76200, 22220, 11180),
                (four_inch_wafer, 100000, 32500, 18000)):
            for flat_count in (1, 2):
                with self.subTest(helper=helper.__name__, flats=flat_count):
                    project = Project()
                    layer = project.add_layer('outline', comsol=False)
                    selected = project.add_selection('wafer')
                    wafer = helper(project, layer=layer, flats=flat_count,
                                   selections=(selected,))
                    self.assertIs(type(wafer), Polygon)
                    points = wafer.vertices.value
                    radius = diameter/2
                    top = sqrt(radius*radius-(primary/2)**2)
                    left = -sqrt(radius*radius-(secondary/2)**2) if flat_count == 2 else -radius
                    self.assert_bounds(bounds(points), (left, -radius, radius, top))
                    top_edge = [x for x, y in points if abs(y-top) < 1e-8]
                    self.assertAlmostEqual(max(top_edge)-min(top_edge), primary, delta=1e-8)
                    if flat_count == 2:
                        side_edge = [y for x, y in points if abs(x-left) < 1e-8]
                        self.assertAlmostEqual(max(side_edge)-min(side_edge), secondary, delta=1e-8)
                    exact = pi*radius*radius-cap_area(radius, primary)
                    if flat_count == 2:
                        exact -= cap_area(radius, secondary)
                    self.assertGreaterEqual(exact-area(points), -1e-5)
                    self.assertLess(exact-area(points), 2*pi*radius)
                    for a, b in zip(points, points[1:]+points[:1]):
                        if abs(a[1]-top) < 1e-8 and abs(b[1]-top) < 1e-8:
                            continue
                        if flat_count == 2 and abs(a[0]-left) < 1e-8 and abs(b[0]-left) < 1e-8:
                            continue
                        self.assertAlmostEqual(hypot(*a), radius, delta=1e-8)
                        self.assertAlmostEqual(hypot(*b), radius, delta=1e-8)
                        midpoint = ((a[0]+b[0])/2, (a[1]+b[1])/2)
                        self.assertLessEqual(radius-hypot(*midpoint), 1.0+1e-8)
                    self.assertEqual(selected.members, (wafer,))
                    self.assertEqual(layer.selection.members, (wafer,))

    def test_full_disk_and_near_limit_flats(self):
        disk = three_inch_wafer(self.project, layer=self.layer, flat_length=0, tolerance=5)
        self.assert_bounds(bounds(disk.vertices.value), (-38100, -38100, 38100, 38100))
        self.assertLess(pi*38100**2-area(disk.vertices.value), 2*pi*38100*5)
        for flat in (1e-4, nextafter(76200, 0)):
            with self.subTest(flat=flat):
                wafer = three_inch_wafer(self.project, layer=self.layer,
                                         flat_length=flat, tolerance=5)
                self.assertGreater(area(wafer.vertices.value), 0)
                self.assertAlmostEqual(max(y for x, y in wafer.vertices.value),
                                       sqrt((38100-flat/2)*(38100+flat/2)), delta=1e-8)

    def test_rotated_and_intersecting_secondary_flats(self):
        angle = 60
        wafer = four_inch_wafer(self.project, layer=self.layer, flats=2,
                                flat_length=80000, secondary_flat_length=80000,
                                secondary_flat_angle=angle, tolerance=5)
        nx, ny = -sin(radians(angle)), cos(radians(angle))
        height = 30000
        corner = ((height-ny*height)/nx, height)
        points = wafer.vertices.value
        self.assertLess(min(hypot(x-corner[0], y-corner[1]) for x, y in points), 1e-8)
        for x, y in points:
            self.assertLessEqual(y, height+1e-8)
            self.assertLessEqual(nx*x+ny*y, height+1e-8)
            self.assertLessEqual(hypot(x, y), 50000+1e-8)
        self.assertGreater(area(points), 0)

    def test_live_transform_separate_workplane_and_gds_roundtrip(self):
        plane = self.project.add_workplane('upper', position=(50, 60, 5), angle=20)
        layer = self.project.add_layer('upper_outline', workplane=plane, gds_layer=8, comsol=False)
        selected = self.project.add_selection('placed_wafer')
        scale = Parameter(.01, 'wafer_scale')
        shift = Parameter(100, 'wafer_x', unit='um')
        wafer = three_inch_wafer(self.project, layer=layer, flats=2, tolerance=5,
                                 selections=(selected,))
        placed = wafer.scale(factor=scale).rotate(angle=90).move(delta=(shift, 0))
        for factor, x in ((.01, 100), (.02, 200)):
            scale.value, shift.value = factor, x
            self.project.build()
            expected = kdb.Region(placed.to_klayout().to_itype(self.project.dbu))
            actual = read_region(plane.gds_path, 8)
            self.assertTrue((actual ^ expected).is_empty())
            self.assertEqual(actual.count(), 1)
            box = actual.bbox()
            top = sqrt(38100**2-11110**2)
            left = -sqrt(38100**2-5590**2)
            target = (x-factor*top, factor*left, x+factor*38100, factor*38100)
            for value, limit in zip((box.left, box.bottom, box.right, box.top), target):
                self.assertAlmostEqual(value*self.project.dbu, limit, delta=self.project.dbu)
            self.assertTrue(read_region(self.project.gds_path, 7).is_empty())
            self.assertEqual(selected.members, (wafer,))
            self.assertEqual(layer.selection.members, (placed,))
            self.assertIs(self.project.parameters['wafer_scale'], scale)
            self.assertIs(self.project.parameters['wafer_x'], shift)

    def test_invalid_arguments_do_not_register_geometry(self):
        invalid = [dict(flats=0), dict(flats=3), dict(flats=True), dict(flats=1.0),
                   dict(flat_length=-1), dict(flat_length=100000), dict(flat_length=float('nan')),
                   dict(flat_length=Parameter(1000, 'flat', unit='um')),
                   dict(tolerance=0), dict(tolerance=-1), dict(tolerance=float('inf')),
                   dict(tolerance=1e-30), dict(tolerance=Parameter(1, 'sampling', unit='um')),
                   dict(secondary_flat_angle=float('inf')), dict(secondary_flat_angle=True),
                   dict(flats=2, flat_length=0), dict(flats=2, secondary_flat_length=0),
                   dict(flats=2, secondary_flat_length=100000),
                   dict(flats=2, secondary_flat_angle=0), dict(flats=2, secondary_flat_angle=360),
                   dict(flats=2, secondary_flat_angle=1)]
        for options in invalid:
            with self.subTest(options=options):
                before = tuple(self.project.objects)
                with self.assertRaises(ValueError):
                    four_inch_wafer(self.project, layer=self.layer, **options)
                self.assertEqual(tuple(self.project.objects), before)
