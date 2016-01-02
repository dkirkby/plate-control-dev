import numpy as np
import itertools

"""Constants and convenience methods used in the control of the Fiber Postioner.
"""

# Mapping of radial coordinate R to pseudo-radial coordinate S (distance along focal surface from optical axis)
R2Spoly = [5.00010E-01,9.99997E-01,1.91532E-07,1.72104E-09,7.31761E-11,-5.78982E-13,3.30271E-15,-1.11245E-17,1.90376E-20,-1.26341E-23]
R2S_lookup_data = np.genfromtxt('focal_surface_lookup.csv',comments="#",delimiter=",")
def R2S_lookup(R):
    return np.interp(R,R2S_lookup_data[:,0],R2S_lookup_data[:,2],left=float('nan'))
def S2R_lookup(S):
    return np.interp(S,R2S_lookup_data[:,2],R2S_lookup_data[:,0],left=float('nan'))

# Constants
# (some of these may be ancient and no longer needed!)
angle_unit = 'deg'  # unless otherwise specified, assume all angles expressed in this unit
deg_char_num = 176  # character number of degree symbol
sqr_char_num = 178  # character number of 2 ^2 symbol
deg_char = chr(deg_char_num)
sqr_char = chr(sqr_char_num)
timestamp_format = '%Y-%m-%d %H:%M:%S.%f' # see strftime documentation
gear_ratio = {}
gear_ratio['namiki'] = (46.0/14.0+1)**4  # namiki    "337:1", output rotation/motor input
gear_ratio['maxon'] = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
gear_ratio['faulhaber'] = 256.0  		  # faulhaber "256:1", output rotation/motor input
T = 0  # theta axis idx -- NOT the motor axis ID!!
P = 1  # phi axis idx -- NOT the motor axis ID!!
axis_labels = ('theta', 'phi')

# Convenience methods
rotmat2D = lambda angle: [np.cos(np.deg2rad(angle)), - np.sin(np.deg2rad(angle)), np.sin(np.deg2rad(angle)), np.cos(np.deg2rad(angle))]

# Functions for handling mixes of [M][N] vs [M] dimension lists
def listify(uv):
    """Turn [u,v] into [[u],[v]], if it isn't already.
    Turn uv into a list [uv] if it isn't already.
    In the special case where uv is a single item list, it remains so in the return.
    A boolean is returned saying whether the item was modified."""
    if not(isinstance(uv,list)):
        return [uv], True
    if len(uv) == 1:
        return uv, False
    new_uv = []
    was_listified = False
    for i in range(len(uv)):
        if not(isinstance(uv[i],list)):
            new_uv.append([uv[i]])
            was_listified = True
        else:
            new_uv.append(uv[i].copy())
    return new_uv, was_listified

def delistify(uv):
    """Turn [[u],[v]] into [u,v], if it isn't already.
    For a non-list, there is no modification.
    For a list with one item only, the element inside is returned.
    For a list with multiple items, the return is a flat list of multiple items.
    """
    if not(isinstance(uv,list)):
        return uv
    if len(uv) == 1:
        return uv[0]
    new_uv = []
    for i in range(len(uv)):
        if isinstance(uv[i],list):
            new_uv.extend(uv[i][:])
        else:
            new_uv.append(uv[i])
    return new_uv

# Enumeration of verbosity level to stdout
not_verbose = 0
verbose = 1
very_verbose = 2

def is_verbose(verbosity_enum):
    boole = True
    if verbosity_enum == not_verbose:
        boole = False
    return boole

def is_very_verbose(verbosity_enum):
    boole = False
    if verbosity_enum == very_verbose:
        boole = True
    return boole



