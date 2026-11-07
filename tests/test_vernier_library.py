"""Independent pitch, readout, ownership and live-edit checks for verniers."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import klayout.db as kdb

from geompype import Parameter, Project
from geompype.library.vernier_mark import vernier_mark
from geompype.parameters import evaluate


def region(feature):
    pieces = feature.to_klayout()
    result = kdb.Region()
    for piece in pieces if isinstance(pieces, tuple) else (pieces,):
        result.insert(piece.to_itype(feature.project.dbu))
    return result.merged()


def read_region(path, layer):
    layout = kdb.Layout()
    layout.read(str(path))
    return kdb.Region(layout.top_cell().shapes(layout.layer(layer, 0))).merged()


class TestVernierLibrary(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.project = Project(output=Path(self.folder.name)/'vernier')
        self.reference = self.project.add_layer('reference', gds_layer=1, comsol=False)
        self.moving = self.project.add_layer('moving', gds_layer=2, comsol=False)

    def create(self, **options):
        return vernier_mark(self.project, reference_layer=self.reference,
                            moving_layer=self.moving, **options)

    def test_dimensions_pitches_readout_selections_and_separate_exports(self):
        selected = self.project.add_selection('vernier')
        mark = self.create(selections=(selected,))
        reference, moving = (mark.geometry[name] for name in ('reference', 'moving'))
        self.assertEqual(selected.members, mark.features)
        self.assertEqual(self.reference.selection.members, (reference,))
        self.assertEqual(self.moving.selection.members, (moving,))
        self.assertEqual(region(reference).bbox(), kdb.Box(-51000, -22000, 51000, -2000))
        self.assertEqual(region(moving).bbox(), kdb.Box(-46000, 2000, 46000, 22000))
        for feature in mark.features:
            footprint = region(feature)
            self.assertEqual(footprint.count(), 11)
            self.assertEqual(footprint.area(), 11*2*20*1000**2)
        x_reference = [evaluate(tick.position[0], 'um') for tick in reference.inputs]
        x_moving = [evaluate(tick.position[0], 'um') for tick in moving.inputs]
        self.assertEqual(x_reference, list(range(-50, 51, 10)))
        self.assertEqual(x_moving, list(range(-45, 46, 9)))
        # A +3 um moving-layer translation aligns tick +3, not tick -3.
        aligned = [index-5 for index, (a, b) in enumerate(zip(x_reference, x_moving))
                   if abs(a-(b+3)) < 1e-12]
        self.assertEqual(aligned, [3])
        self.project.build()
        self.assertTrue((read_region(self.project.gds_path, 1) ^ region(reference)).is_empty())
        self.assertTrue((read_region(self.project.gds_path, 2) ^ region(moving)).is_empty())

    def test_parameters_stay_live_through_placement_and_invalid_edits_preserve_file(self):
        pitch = Parameter(10, 'vernier_pitch', unit='um')
        resolution = Parameter(1, 'vernier_resolution', unit='um')
        width = Parameter(2, 'vernier_width', unit='um')
        length = Parameter(20, 'vernier_length', unit='um')
        gap = Parameter(4, 'vernier_gap', unit='um')
        mark = self.create(pitch=pitch, resolution=resolution, width=width,
                           length=length, gap=gap)
        mark.rotate(90).move((100, 200))
        self.project.build()
        self.assertEqual(read_region(self.project.gds_path, 1).bbox(),
                         kdb.Box(102000, 149000, 122000, 251000))
        pitch.value, resolution.value, width.value = 12, .5, 3
        length.value, gap.value = 30, 6
        self.project.build()
        self.assertEqual(read_region(self.project.gds_path, 1).bbox(),
                         kdb.Box(103000, 138500, 133000, 261500))
        self.assertEqual(read_region(self.project.gds_path, 2).bbox(),
                         kdb.Box(67000, 141000, 97000, 259000))
        for parameter in (pitch, resolution, width, length, gap):
            self.assertIs(self.project.parameters[parameter.name], parameter)
        previous = self.project.gds_path.read_bytes()
        for parameter, invalid in ((resolution, 12), (width, 11.5), (gap, 0)):
            original = parameter.value
            parameter.value = invalid
            with self.assertRaisesRegex(ValueError, 'Vernier'):
                self.project.build()
            self.assertEqual(self.project.gds_path.read_bytes(), previous)
            parameter.value = original
        self.project.build()

    def test_rejects_invalid_dimensions_ownership_and_selection_before_registration(self):
        for options in ({'ticks': 1}, {'ticks': 10}, {'ticks': 3.0}, {'ticks': True},
                        {'pitch': 0}, {'resolution': 10}, {'resolution': -1},
                        {'width': 9}, {'length': 0}, {'gap': -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.create(**options)
            self.assertEqual(self.project.objects, [])
        foreign_project = Project()
        foreign = foreign_project.add_layer('foreign', comsol=False)
        upper = self.project.add_workplane('upper', position=(0, 0, 10))
        upper_layer = self.project.add_layer('upper', workplane=upper, comsol=False)
        for moving in (self.reference, foreign, upper_layer):
            with self.subTest(layer=moving.name), self.assertRaises(ValueError):
                vernier_mark(self.project, reference_layer=self.reference, moving_layer=moving)
            self.assertEqual(self.project.objects, [])
        with self.assertRaises(ValueError):
            self.create(selections=(foreign_project.add_selection('foreign'),))
        self.assertEqual(self.project.objects, [])

    def test_live_assembly_builds_once(self):
        self.project.live = True
        with patch.object(self.project, 'build') as build:
            self.create()
        build.assert_called_once()
        self.assertTrue(self.project.live)
