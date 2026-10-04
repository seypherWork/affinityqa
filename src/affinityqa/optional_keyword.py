"""Missing optional keyword metadata has no ranking contribution, and stays visible."""
from .keyword_calibrator import cosine_signals,combined_profile
from .errors import SchemaError


def optional_signals(movies,a,b):
    if not isinstance(movies,dict) or len(movies)!=20:raise SchemaError('Complete movie keyword catalog required.')
    zero={i:0. for i in movies}
    observed={'A':a is not None,'B':b is not None,'pooled':a is not None and b is not None}
    values={'A':dict(zero) if a is None else cosine_signals(movies,a),
            'B':dict(zero) if b is None else cosine_signals(movies,b),
            'pooled':cosine_signals(movies,combined_profile(a,b)) if observed['pooled'] else dict(zero)}
    return values,observed
