"""Planar transforms preserve geometry, dependencies and final-only rounding."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import klayout.db as kdb

from geompype import Parameter, Project, Vertices
from geompype.geometry import GeometryObject
from geompype.primitives import LineSegment, Point, Polygon, Rectangle, Square
from geompype.transforms import Copy, Mirror, Move, Rotate, Scale
from test_parameter_geometry import RecordedGeometry


def read_shapes(project):
    layout = kdb.Layout()
    layout.read(str(project.gds_path))
    return layout, list(layout.top_cell().shapes(layout.layer(1, 0)).each())


class TestPlanarTransforms(unittest.TestCase):
    def test_move_and_copy_multiple_offsets_have_native_retention(self):
        with TemporaryDirectory() as folder:
            for transform in (Move, Copy):
                with self.subTest(transform=transform.__name__):
                    project = Project(output=Path(folder) / transform.__name__)
                    layer = project.add_layer("metal", comsol=False)
                    square = Square(project, layer=layer, side=2)
                    result = transform(square, delta=((10, 0), (0, 20)))
                    self.assertEqual(result.keep, transform is Copy)
                    self.assertEqual(len(result.to_klayout()), 2)
                    project.build()
                    layout, shapes = read_shapes(project)
                    self.assertEqual(len(shapes), 3 if transform is Copy else 2)
                    bounds = {str(shape.bbox().to_dtype(layout.dbu)) for shape in shapes}
                    expected = {str(kdb.DBox(9, -1, 11, 1)), str(kdb.DBox(-1, 19, 1, 21))}
                    if transform is Copy:
                        expected.add(str(kdb.DBox(-1, -1, 1, 1)))
                    self.assertEqual(bounds, expected)

    def test_multiple_inputs_and_output_chaining_keep_types(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "mixed")
            layer = project.add_layer("mixed", comsol=False)
            point = Point(project, layer=layer, position=(1, 0))
            line = LineSegment(project, layer=layer, p1=(2, 0), p2=(4, 0))
            box = Rectangle(project, layer=layer, size=(2, 4), position=(8, 0))
            moved = Move((point, line, box), delta=(1, 2))
            rotated = Rotate(moved, angle=(90, 180))
            scaled = Scale(rotated, factor=(2, 3))
            geometry = scaled.to_klayout()
            self.assertEqual(len(geometry), 6)
            self.assertEqual([type(item) for item in geometry],
                             [kdb.DPoint, kdb.DPath, kdb.DPolygon] * 2)
            self.assertAlmostEqual(geometry[0].x, -4)
            self.assertAlmostEqual(geometry[0].y, 6)
            self.assertAlmostEqual(geometry[3].x, -4)
            self.assertAlmostEqual(geometry[3].y, -6)
            self.assertEqual(geometry[1].width, 0)
            self.assertAlmostEqual(geometry[2].area(), 48)
            project.build()
            _, shapes = read_shapes(project)
            self.assertEqual(sum(shape.is_path() for shape in shapes), 2)
            self.assertEqual(sum(shape.is_polygon() or shape.is_box() for shape in shapes), 2)
            self.assertEqual(project._final_objects(project.objects), [scaled])

    def test_mirror_oblique_normal_about_nonzero_origin(self):
        project = Project()
        layer = project.add_layer("construction", comsol=False, gds=False)
        point = Point(project, layer=layer, position=(4, 3))
        mirrored = Mirror(point, normal=(2, 2), origin=(1, 2), keep=True)
        actual = mirrored.to_klayout()
        # Reflection in x+y=3 maps (4,3) to (0,-1).
        self.assertAlmostEqual(actual.x, 0)
        self.assertAlmostEqual(actual.y, -1)
        restored = Mirror(mirrored, normal=(-1, -1), origin=(1, 2)).to_klayout()
        self.assertAlmostEqual(restored.x, 4)
        self.assertAlmostEqual(restored.y, 3)

    def test_negative_anisotropic_scale_and_polygon_holes(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        # Existing public filled primitives have one contour. A geometry object
        # with a hole checks that the generic transform preserves all contours.
        class HoledPolygon(GeometryObject):
            tag_prefix = "hole"

            def validate(self):
                pass

            def to_klayout(self):
                polygon = kdb.DPolygon(kdb.DBox(1, 2, 5, 6))
                polygon.insert_hole(kdb.DBox(2, 3, 3, 4))
                return polygon

        source = HoledPolygon(project, layer)
        project.add(source)
        scaled = Scale(source, factor=(-2, 3), origin=(1, 2))
        geometry = scaled.to_klayout()
        self.assertEqual(geometry.holes(), 1)
        self.assertEqual(geometry.bbox(), kdb.DBox(-7, 2, 1, 14))
        self.assertAlmostEqual(geometry.area(), (16 - 1) * 6)

    def test_shared_parameters_vertices_and_repeated_native_emission(self):
        project = Project()
        layer = project.add_layer("metal", comsol=False, gds=False)
        step = Parameter(2000, "step", unit="nm")
        factor = Parameter(2, "factor")
        theta = Parameter(90, "theta", unit="deg")
        offsets = Vertices(((step, 0), (0, step)))
        point = Point(project, layer=layer, position=(1, 1))
        copied = Copy(point, delta=offsets)
        scaled = Scale(copied, factor=(factor, 1))
        mirrored = Mirror(scaled, normal=(factor, 0), origin=(1, 0))
        rotated = Rotate(mirrored, angle=(theta, -theta))
        self.assertEqual(set(project.parameters), {"step", "factor", "theta"})
        self.assertIs(copied.delta, offsets)
        plane = RecordedGeometry([])
        for _ in range(2):
            for obj in (copied, scaled, mirrored, rotated):
                obj.to_comsol(plane, obj.tag)
        self.assertEqual(len(plane.features), 4)
        native = plane.features[copied.tag]
        self.assertEqual(native.kind, "Copy")
        self.assertNotIn("keep", native.values)
        self.assertIn("step", native.values["displx"][0])
        self.assertEqual(plane.features[scaled.tag].values["factor"], ["factor", "1"])
        self.assertEqual(plane.features[rotated.tag].values["rot"][0], "theta")
        old = [(p.x, p.y) for p in rotated.to_klayout()]
        step.value = 4000
        factor.value = 3
        theta.value = 180
        offsets[1] = (0, 7)
        new = [(p.x, p.y) for p in rotated.to_klayout()]
        self.assertNotEqual(old, new)
        self.assertAlmostEqual(new[0][0], 13)
        self.assertAlmostEqual(new[0][1], -1)
        self.assertAlmostEqual(new[1][0], 1)
        self.assertAlmostEqual(new[1][1], -8)

    def test_displacement_edit_live_and_deferred_updates_gds(self):
        with TemporaryDirectory() as folder:
            for live in (False, True):
                project = Project(output=Path(folder) / str(live), live=live)
                layer = project.add_layer("metal", comsol=False)
                delta = Vertices((5, 2))
                source = Square(project, layer=layer, side=2)
                moved = Move(source, delta=delta)
                project.build()
                first = project.gds_path.read_bytes()
                delta[0] = (8, 3)
                project.build()
                project.build()
                self.assertNotEqual(first, project.gds_path.read_bytes())
                layout, shapes = read_shapes(project)
                self.assertEqual(len(shapes), 1)
                self.assertEqual(shapes[0].bbox().to_dtype(layout.dbu), kdb.DBox(7, 2, 9, 4))
                moved.delta = (10, -2)
                project.build()
                layout, shapes = read_shapes(project)
                self.assertEqual(shapes[0].bbox().to_dtype(layout.dbu), kdb.DBox(9, -3, 11, -1))

    def test_inverse_transforms_round_only_final_geometry(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "inverse", dbu=1)
            layer = project.add_layer("metal", comsol=False)
            source = Polygon(project, layer=layer, vertices=((0.2, 0.3), (4.2, 0.3), (2.2, 4.3)))
            moved = Move(source, delta=(0.6, 0.7))
            scaled = Scale(moved, factor=(2, 3), origin=(0.4, 0.5))
            restored_scale = Scale(scaled, factor=(0.5, 1/3), origin=(0.4, 0.5))
            Move(restored_scale, delta=(-0.6, -0.7))
            project.build()
            _, shapes = read_shapes(project)
            self.assertEqual(len(shapes), 1)
            self.assertTrue((kdb.Region(shapes[0].polygon)
                             ^ kdb.Region(source.to_klayout().to_itype(1))).is_empty())

    def test_invalid_transforms_do_not_register_or_replace_gds(self):
        with TemporaryDirectory() as folder:
            project = Project(output=Path(folder) / "invalid", live=True)
            layer = project.add_layer("metal", comsol=False)
            source = Square(project, layer=layer, side=2)
            before = project.gds_path.read_bytes()
            cases = [(Move, {"delta": ()}), (Copy, {"delta": (1, 2, 3)}),
                     (Mirror, {"normal": (0, 0)}), (Mirror, {"normal": (1,)}),
                     (Mirror, {"normal": (Parameter(1, "length", unit="um"), 1)}),
                     (Scale, {"factor": 0}), (Scale, {"factor": (1, 0)}),
                     (Scale, {"factor": (1, 2, 3)}), (Scale, {"factor": float("nan")}),
                     (Scale, {"factor": Parameter(1, "length", unit="um")}),
                     (Rotate, {"angle": ()}), (Rotate, {"angle": (90, float("inf"))}),
                     (Mirror, {"propagate_selections": "yes"})]
            for transform, options in cases:
                with self.subTest(transform=transform.__name__, options=options):
                    with self.assertRaises((ValueError, TypeError)):
                        transform(source, **options)
                    self.assertEqual(project.objects, [source])
                    self.assertEqual(project.gds_path.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "duplicates"):
                Move((source, source), delta=(2, 0))
            other_layer = project.add_layer("other", comsol=False, gds=False)
            other = Square(project, layer=other_layer, side=2)
            with self.assertRaisesRegex(ValueError, "layer"):
                Copy((source, other), delta=(2, 0))
            moved = Move(source, delta=(5, 0))
            with self.assertRaisesRegex(ValueError, "consum"):
                Mirror(source)
            moved.keep = True
            with self.assertRaisesRegex(ValueError, "retention"):
                project.build()


if __name__ == "__main__":
    unittest.main()
