"""Rounded stroke unions must not invent holes at separately rounded seams."""

from math import asinh, pi, sqrt
import unittest

import klayout.db as kdb

from geompype import InterpolationCurve, LineSegment, Project, QuadraticBezier, Rectangle, Thicken2D


def region(feature):
    pieces = feature.to_klayout()
    result = kdb.Region()
    for piece in pieces if isinstance(pieces, tuple) else (pieces,):
        result.insert(piece.to_itype(feature.project.dbu))
    return result.merged()


def parabola_length(span, rise):
    q = 4*rise/span
    return span/2*(sqrt(1+q*q)+asinh(q)/q)


class TestPlanarStrokeGrid(unittest.TestCase):
    def test_straight_stroke_preserves_exact_grid_outline_with_half_grid_centre(self):
        project = Project(grid_policy='error')
        layer = project.add_layer('track', comsol=False)
        line = LineSegment(project, layer=layer, p1=(.0005, .0005), p2=(1.0005, 1.0005))
        footprint = region(Thicken2D(line, width=sqrt(2)*.001))
        # The four offset corners lie exactly on the grid; no join sector is
        # present, so the half-grid centreline endpoints need not be inserted.
        expected = kdb.Region(kdb.Polygon([kdb.Point(0, 1), kdb.Point(1000, 1001),
                                          kdb.Point(1001, 1000), kdb.Point(1, 0)]))
        self.assertTrue((footprint ^ expected).is_empty())

    def test_dense_spline_and_bezier_strokes_have_no_rounding_slits(self):
        for kind in ('spline', 'bezier'):
            for span, rise, width in ((40, 10, 2), (60, 12, 3)):
                for x, y in ((0, -35), (.0003, -.0007)):
                    with self.subTest(kind=kind, span=span, width=width, position=(x, y)):
                        project = Project()
                        layer = project.add_layer('tracks', comsol=False)
                        if kind == 'spline':
                            curve = InterpolationCurve(project, layer=layer,
                                points=[(x-span/2, y), (x, y+rise), (x+span/2, y)],
                                sampler=lambda s: (x+span*(s-.5), y+4*rise*s*(1-s)),
                                tolerance=.001)
                        else:
                            curve = QuadraticBezier(project, layer=layer,
                                p0=(x-span/2, y), p1=(x, y+2*rise), p2=(x+span/2, y),
                                weights=(1, 1, 1), tolerance=.001)
                        footprint = region(Thicken2D(curve, width=width, ends='circular'))
                        self.assertEqual(footprint.count(), 1)
                        self.assertEqual(next(footprint.each()).holes(), 0)
                        expected = width*parabola_length(span, rise)+pi*(width/2)**2
                        self.assertAlmostEqual(footprint.area()*project.dbu**2, expected, delta=.04)

    def test_rotated_sharp_closed_strokes_keep_only_the_intended_hole(self):
        for angle in (17, 37, 73):
            for position in ((0, 0), (.0003, -.0007)):
                with self.subTest(angle=angle, position=position):
                    project = Project()
                    layer = project.add_layer('band', comsol=False)
                    rectangle = Rectangle(project, layer=layer, size=(12, 8),
                                          position=position, angle=angle)
                    footprint = region(Thicken2D(rectangle, width=2))
                    self.assertEqual(footprint.count(), 1)
                    self.assertEqual(next(footprint.each()).holes(), 1)
                    # Rounded outer rectangle minus its sharp inner rectangle.
                    expected = 2*2*(12+8)+(pi-4)
                    self.assertAlmostEqual(footprint.area()*project.dbu**2, expected, delta=.04)
