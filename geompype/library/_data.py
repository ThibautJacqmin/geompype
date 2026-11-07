"""Load independent coordinate lists from packaged geometry assets."""

from importlib.resources import files
import json

from ..vertices import Vertices


def polygons(name):
    resource = files('geompype.library').joinpath('data', name + '.json')
    data = json.loads(resource.read_text(encoding='utf-8'))
    return [Vertices(points, unit=data['unit']) for points in data['polygons'].values()]
