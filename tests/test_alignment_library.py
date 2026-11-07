"""Alignment mark footprints, live dimensions and graph ownership."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Difference, Parameter, Polygon, Project
from geompype.library.box_mark import box_mark
from geompype.library.cross_mark import cross_mark
from geompype.library.l_mark import l_mark


def region(feature):
    shapes = feature.to_klayout()
    result = kdb.Region()
    for shape in shapes if isinstance(shapes, tuple) else (shapes,):
        result.insert(shape.to_itype(feature.project.dbu))
    return result.merged()


def read_region(path, number=1):
    layout = kdb.Layout()
    layout.read(str(path))
    return kdb.Region(layout.top_cell().shapes(layout.layer(number, 0))).merged()


class TestAlignmentLibrary(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name) / 'marks')
        self.layer = self.project.add_layer('marks', comsol=False)

    def test_cross_has_exact_arm_footprint(self):
        selected = self.project.add_selection('cross')
        mark = cross_mark(self.project, layer=self.layer, selections=(selected,))
        expected = (kdb.Region(kdb.Box(-50000, -5000, 50000, 5000))
                    + kdb.Region(kdb.Box(-5000, -50000, 5000, 50000)))
        self.assertIsInstance(mark, Polygon)
        self.assertTrue((region(mark) ^ expected).is_empty())
        self.assertEqual(selected.members, (mark,))
        self.assertAlmostEqual(region(mark).area() * self.project.dbu**2, 1900)
        self.project.build()
        self.assertTrue((read_region(self.project.gds_path) ^ expected).is_empty())

    def test_l_mark_corner_orientation_and_rotated_footprint(self):
        mark = l_mark(self.project, layer=self.layer, size=80, width=8)
        expected = (kdb.Region(kdb.Box(0, 0, 80000, 8000))
                    + kdb.Region(kdb.Box(0, 0, 8000, 80000)))
        self.assertTrue((region(mark) ^ expected).is_empty())
        placed = mark.rotate(angle=90).move(delta=(200, 300))
        self.assertEqual(region(placed).bbox(), kdb.Box(120000, 300000, 200000, 380000))
        self.assertAlmostEqual(region(placed).area() * self.project.dbu**2, 1216)
        self.project.build()
        self.assertTrue((read_region(self.project.gds_path) ^ region(placed)).is_empty())

    def test_box_is_hollow_and_has_exact_wall_width(self):
        selected = self.project.add_selection('frame')
        mark = box_mark(self.project, layer=self.layer, selections=(selected,))
        expected = (kdb.Region(kdb.Box(-50000, -50000, 50000, 50000))
                    - kdb.Region(kdb.Box(-40000, -40000, 40000, 40000)))
        actual = region(mark)
        self.assertIsInstance(mark, Difference)
        self.assertTrue((actual ^ expected).is_empty())
        self.assertEqual(actual.count(), 1)
        self.assertEqual(next(actual.each()).holes(), 1)
        self.assertAlmostEqual(actual.area() * self.project.dbu**2, 3600)
        self.assertEqual(selected.members, (mark,))
        self.assertEqual(self.layer.selection.members, (mark,))

    def test_all_mark_dimensions_and_placement_rebuild_from_parameters(self):
        for make in (cross_mark, l_mark, box_mark):
            with self.subTest(mark=make.__name__):
                project = Project(output=Path(self.folder.name) / make.__name__)
                layer = project.add_layer('mark', comsol=False)
                size = Parameter(.1, 'mark_size', unit='mm')
                width = Parameter(10, 'mark_width', unit='um')
                shift = Parameter(200, 'mark_shift', unit='um')
                mark = make(project, layer=layer, size=size, width=width)
                placed = mark.move(delta=(shift, 0))
                project.build()
                size.value, width.value, shift.value = .2, 10, 300
                project.build()
                # The exact new areas are 2*s*w-w*w and 4*w*(s-w).
                expected_area = 3900 if make is not box_mark else 7600
                self.assertAlmostEqual(region(placed).area() * project.dbu**2, expected_area)
                bounds = (kdb.Box(300000, 0, 500000, 200000) if make is l_mark
                          else kdb.Box(200000, -100000, 400000, 100000))
                self.assertEqual(region(placed).bbox(), bounds)
                self.assertIs(project.parameters['mark_size'], size)
                self.assertIs(project.parameters['mark_width'], width)
                self.assertIs(project.parameters['mark_shift'], shift)
                self.assertTrue((read_region(project.gds_path) ^ region(placed)).is_empty())

    def test_invalid_dimensions_are_rejected_before_registration(self):
        for make in (cross_mark, l_mark, box_mark):
            for size, width in ((0, 1), (100, 0), (100, -1), (100, 100), (100, 120)):
                with self.subTest(mark=make.__name__, size=size, width=width):
                    before = tuple(self.project.objects)
                    with self.assertRaises(ValueError):
                        make(self.project, layer=self.layer, size=size, width=width)
                    self.assertEqual(tuple(self.project.objects), before)
        with self.assertRaises(ValueError):
            box_mark(self.project, layer=self.layer, size=100, width=50)

    def test_invalid_live_edits_preserve_exports_and_recover(self):
        for make in (cross_mark, l_mark, box_mark):
            with self.subTest(mark=make.__name__):
                project = Project(output=Path(self.folder.name) / make.__name__)
                layer = project.add_layer('mark', comsol=False)
                width = Parameter(10, 'width', unit='um')
                make(project, layer=layer, width=width)
                project.build()
                previous = project.gds_path.read_bytes()
                expected = read_region(project.gds_path)
                width.value = 60 if make is box_mark else 120
                with self.assertRaises(ValueError):
                    project.build()
                self.assertEqual(project.gds_path.read_bytes(), previous)
                width.value = 10
                project.build()
                self.assertTrue((read_region(project.gds_path) ^ expected).is_empty())

    def test_box_batches_live_build(self):
        self.project.live = True
        with patch.object(self.project, 'build') as build:
            mark = box_mark(self.project, layer=self.layer)
        build.assert_called_once()
        self.assertTrue(self.project.live)
        self.assertEqual(self.project._final_objects(self.project.objects), [mark])

    def test_ownership_errors_do_not_register_partial_marks(self):
        other = Project(output=Path(self.folder.name) / 'other')
        foreign_selection = other.add_selection('foreign')
        foreign_layer = other.add_layer('foreign', comsol=False)
        self.project.live = True
        for make in (cross_mark, l_mark, box_mark):
            for layer, selections in ((foreign_layer, ()), (self.layer, (foreign_selection,))):
                with self.subTest(mark=make.__name__, layer=layer.name):
                    before = tuple(self.project.objects)
                    with patch.object(self.project, 'build') as build:
                        with self.assertRaises(ValueError):
                            make(self.project, layer=layer, selections=selections)
                    build.assert_not_called()
                    self.assertEqual(tuple(self.project.objects), before)
                    self.assertTrue(self.project.live)

    def test_two_frames_keep_separate_layers_on_an_upper_workplane(self):
        upper = self.project.add_workplane('upper', position=(0, 0, 5))
        first_layer = self.project.add_layer('reference', comsol=False, gds_layer=5, workplane=upper)
        second_layer = self.project.add_layer('overlay', comsol=False, gds_layer=6, workplane=upper)
        first = box_mark(self.project, layer=first_layer, size=100, width=5)
        second = box_mark(self.project, layer=second_layer, size=80, width=5)
        self.project.build()
        self.assertTrue((region(first) & region(second)).is_empty())
        self.assertTrue((read_region(upper.gds_path, 5) ^ region(first)).is_empty())
        self.assertTrue((read_region(upper.gds_path, 6) ^ region(second)).is_empty())
        self.assertEqual(first_layer.selection.members, (first,))
        self.assertEqual(second_layer.selection.members, (second,))
