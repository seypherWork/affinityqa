"""One globally calibrated scalar; fixed 1:3 movie/artist mixture, no reference inputs."""
import math
from .affinity_repair import normalize
from .errors import SchemaError

def curve(baseline,movie,artist,*,other_movie=None,other_artist=None):
    if len(baseline)!=20 or len(set(baseline))!=20 or set(movie)!=set(baseline) or set(artist)!=set(baseline) or (other_movie is None)!=(other_artist is None):
        raise SchemaError('Complete matching twenty-movie inputs required.')
    m=normalize(movie);a=normalize(artist);signal={i:.25*m[i]+.75*a[i] for i in baseline}
    if other_movie is not None:
        if set(other_movie)!=set(baseline) or set(other_artist)!=set(baseline):raise SchemaError('Pooled catalogs differ.')
        om=normalize(other_movie);oa=normalize(other_artist)
        signal={i:(signal[i]+.25*om[i]+.75*oa[i])/2 for i in baseline}
    local={i:1-n/19 for n,i in enumerate(baseline)}
    return {i:(local[i],signal[i]-local[i]) for i in baseline}

def rank(baseline,movie,artist,weight,*,other_movie=None,other_artist=None):
    if type(weight) not in (int,float) or not math.isfinite(weight) or not .5<=weight<=.75:raise SchemaError('Weight outside frozen calibration domain.')
    values=curve(baseline,movie,artist,other_movie=other_movie,other_artist=other_artist);positions={i:n for n,i in enumerate(baseline)}
    return sorted(baseline,key=lambda i:(-(values[i][0]+weight*values[i][1]),positions[i],i))
