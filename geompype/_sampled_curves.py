"""Bounded numerical sampling of an explicitly supplied Python curve function.

The refinement criterion measures sampled chord deviations. Without derivative
bounds it cannot certify the error of an arbitrary callable between samples.
"""

from math import hypot, isfinite
from numbers import Integral

from .parameters import DependentParameter, Parameter, collect_parameters, evaluate
from .vertices import coordinate_pair


def validate_sampling(sampler, tolerance, sampling_intervals):
    if sampler is not None and not callable(sampler):
        raise ValueError("sampler must be a callable accepting one numeric parameter, or None.")
    if evaluate(tolerance, "um") <= 0:
        raise ValueError("Curve tolerance must be a finite positive length.")
    if (isinstance(sampling_intervals, bool) or not isinstance(sampling_intervals, Integral)
            or not 1 <= sampling_intervals <= 16384):
        raise ValueError("sampling_intervals must be an integer from 1 to 16384.")


def named_parameters(parameters):
    """Keep the explicit objects; names in COMSOL text are not parsed as Python."""
    parameters = tuple(parameters)
    if any(not isinstance(p, (Parameter, DependentParameter)) for p in parameters):
        raise ValueError("parameters must contain named Parameter or DependentParameter objects.")
    collect_parameters(parameters)
    return parameters


def parameter_domain(lower, upper):
    lower, upper = evaluate(lower, ""), evaluate(upper, "")
    if upper <= lower or not isfinite(upper - lower):
        raise ValueError("Curve parameter bounds must have a finite positive span.")
    return lower, upper


def _distance_to_segment(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    px, py = point[0] - start[0], point[1] - start[1]
    scale = max(abs(v) for v in (dx, dy, px, py))
    if not isfinite(scale):
        raise ValueError("Curve coordinate span is too large.")
    if scale == 0:
        return 0.0
    dx, dy, px, py = (v / scale for v in (dx, dy, px, py))
    square = dx*dx + dy*dy
    fraction = 0 if square == 0 else min(1, max(0, (px*dx + py*dy) / square))
    return scale * hypot(px - fraction*dx, py - fraction*dy)


def sample_callback(sampler, lower, upper, tolerance, sampling_intervals, maximum=65536):
    """Evaluate a callback in order, retaining endpoints and refining curved spans.

    Bare coordinates returned by the callback are in um; scalar length
    parameters/expressions and a single-point Vertices are also accepted.
    Increasing sampling_intervals helps resolve oscillations before refinement.
    """
    validate_sampling(sampler, tolerance, sampling_intervals)
    if sampler is None:
        raise ValueError("KLayout sampling requires an explicit sampler(s) callback; "
                         "COMSOL expressions and interpolation algorithms are not evaluated in Python.")
    lower, upper = parameter_domain(lower, upper)
    tolerance = evaluate(tolerance, "um")
    cache = {}

    def point_at(parameter):
        if parameter not in cache:
            if len(cache) >= 8 * maximum:
                raise ValueError("Curve sampling exceeded its evaluation limit; increase tolerance "
                                 "or simplify the sampler.")
            try:
                row = coordinate_pair(sampler(parameter))
                cache[parameter] = tuple(evaluate(value, "um") for value in row)
            except (ArithmeticError, TypeError, ValueError) as error:
                raise ValueError(f"Curve sampler failed at parameter {parameter:.17g}: {error}") from error
        return cache[parameter]

    span = upper - lower
    knots = [lower + span * (i / sampling_intervals) for i in range(sampling_intervals)] + [upper]
    stack = [(a, b, 0) for a, b in reversed(list(zip(knots, knots[1:])))]
    result = [point_at(lower)]
    while stack:
        left, right, depth = stack.pop()
        start, end = point_at(left), point_at(right)
        interior = [left + (right-left) * fraction for fraction in (0.25, 0.5, 0.75)]
        error = max(_distance_to_segment(point_at(t), start, end) for t in interior)
        if error <= tolerance:
            if end != result[-1]:
                result.append(end)
            continue
        middle = interior[1]
        if depth >= 40 or middle in (left, right):
            raise ValueError("Curve tolerance cannot be resolved by floating-point subdivision.")
        stack.append((middle, right, depth + 1))
        stack.append((left, middle, depth + 1))
        if len(result) + len(stack) > maximum:
            raise ValueError(f"Curve sampling requires more than {maximum} KLayout vertices; "
                             "increase tolerance.")
    if len(result) < 2:
        raise ValueError("Curve sampler must describe a nonzero-length path.")
    return result
