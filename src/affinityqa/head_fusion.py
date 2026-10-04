"""A single head-aware development adaptation; no network or oracle inputs."""
from fractions import Fraction
from .errors import SchemaError


def head_fuse(baseline, graph, other=None):
    if (len(baseline) != 20 or len(set(baseline)) != 20 or len(graph) != 20 or set(graph) != set(baseline)
            or (other is not None and (len(other) != 20 or set(other) != set(baseline)))):
        raise SchemaError('Head fusion requires equal complete movie permutations.')
    original = {i:n+1 for n,i in enumerate(baseline)}
    positions = {i:n+1 for n,i in enumerate(graph)}
    alternative = {i:n+1 for n,i in enumerate(other)} if other is not None else positions
    # Exact rational scores prevent incidental floating-point tie outcomes.
    scores = {i: Fraction(1,2) / (5+original[i]) + Fraction(1,4) * (
        Fraction(1,5+positions[i]) + Fraction(1,5+alternative[i])) for i in baseline}
    return sorted(baseline,key=lambda i:(-scores[i],original[i],i))
