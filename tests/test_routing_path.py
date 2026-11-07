"""Independent geometric checks for exact rounded routing centrelines."""
from math import hypot, pi
import unittest
from geompype._routing_path import ArcPiece, RoutePath


class TestRoutingPath(unittest.TestCase):
    def test_short_straight_does_not_require_room_for_unused_bends(self):
        path = RoutePath.manhattan((0,0),(100,0),(1,0),(-1,0),radius=200)
        self.assertEqual(path.length,100)
        self.assertEqual(len(path.pieces),1)

    def test_quarter_turn_and_concentric_offsets(self):
        path = RoutePath([(0,0),(100,0),(100,100)],20)
        self.assertAlmostEqual(path.length,160+10*pi)
        arc = next(p for p in path.pieces if isinstance(p,ArcPiece))
        self.assertEqual(arc.center,(80,20))
        left = path.offset(3)
        shifted = next(p for p in left.pieces if isinstance(p,ArcPiece))
        self.assertEqual(shifted.center,arc.center)
        self.assertEqual(shifted.radius,17)
        self.assertAlmostEqual(left.length,path.length-3*pi/2)
        self.assertEqual(left.start,(0,3))

    def test_both_turn_directions_and_sampling(self):
        path = RoutePath([(0,0),(100,0),(100,100),(200,100)],20)
        self.assertAlmostEqual(path.offset(5).length,path.length)
        for piece in path.pieces:
            if isinstance(piece,ArcPiece):
                pts = piece.sample(.001)
                for a,b in zip(pts,pts[1:]):
                    midpoint = ((a[0]+b[0])/2,(a[1]+b[1])/2)
                    sagitta = piece.radius-hypot(midpoint[0]-piece.center[0],midpoint[1]-piece.center[1])
                    self.assertLessEqual(sagitta,.001000001)

    def test_invalid_radius_intersection_and_offset(self):
        with self.assertRaisesRegex(ValueError,"too large"):
            RoutePath([(0,0),(10,0),(10,10)],11)
        with self.assertRaisesRegex(ValueError,"self-intersects"):
            RoutePath([(0,0),(10,10),(0,10),(10,0)])
        with self.assertRaisesRegex(ValueError,"collapses"):
            RoutePath([(0,0),(100,0),(100,100)],20).offset(20)

    def test_manhattan_tangents_and_post_rounding_straights(self):
        for orientation in [(1,0),(-1,0),(0,1),(0,-1)]:
            path = RoutePath.manhattan((0,0),(400,300),(1,0),orientation,
                                      radius=20,start_straight=30,end_straight=40)
            self.assertEqual(path.start,(0,0))
            self.assertEqual(path.end,(400,300))
            self.assertEqual(path.start_direction,(1,0))
            self.assertEqual(path.end_direction,tuple(-v for v in orientation))
            self.assertGreaterEqual(path.pieces[0].length,30-1e-8)
            self.assertGreaterEqual(path.pieces[-1].length,40-1e-8)

    def test_meander_length_and_reversal(self):
        path = RoutePath([(0,0),(1000,0)],20)
        first = path.meander(4,100)
        second = path.meander(4,150)
        self.assertAlmostEqual(second.length-first.length,400)
        self.assertEqual(first.start,path.start)
        self.assertEqual(first.end,path.end)
        self.assertAlmostEqual(first.reversed().length,first.length)
        with self.assertRaises(ValueError):
            path.meander(4,10)
