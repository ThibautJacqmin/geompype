"""Fabrication exports retain geometry without oversized GDS XY records."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import klayout.db as kdb
from geompype import Project,Rectangle


class TestGDSRecords(unittest.TestCase):
    def test_perforated_polygon_is_split_into_portable_records(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder)/'perforated')
            layer = project.add_layer('metal',comsol=False,gds_layer=1)
            plate = Rectangle(project,layer=layer,size=(320,110))
            holes = Rectangle(project,layer=layer,size=(1,1),position=(-150,-45)).array(
                size=(100,30),displacement=(3,3))
            plate.difference(holes,interior_boundaries=False)
            project.build()
            data = project.gds_path.read_bytes()
            cursor,xy = 0,0
            while cursor<len(data):
                length = int.from_bytes(data[cursor:cursor+2],'big')
                self.assertGreaterEqual(length,4)
                if data[cursor+2]==0x10:
                    xy += 1
                    self.assertLessEqual(length,32012)
                cursor += length
            self.assertGreater(xy,1)
            actual = kdb.Layout()
            actual.read(str(project.gds_path))
            region = kdb.Region(actual.top_cell().begin_shapes_rec(actual.layer(1,0))).merged()
            self.assertAlmostEqual(region.area()*actual.dbu**2,320*110-3000)
