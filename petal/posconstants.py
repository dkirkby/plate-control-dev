import numpy as np
import itertools

"""Constants used in the control of the Fiber Postioner """

angle_unit = 'deg'  # unless otherwise specified, assume all angles expressed in this unit
deg_char_num = 176  # character number of degree symbol
sqr_char_num = 178  # character number of 2 ^2 symbol
deg_char = chr(deg_char_num)
sqr_char = chr(sqr_char_num)
rotmat2D = lambda angle: [np.cos(np.deg2rad(angle)), - np.sin(np.deg2rad(angle)), np.sin(np.deg2rad(angle)), np.cos(np.deg2rad(angle))]
timestamp_format = 30  # ISO 8601 ' yyyymmddTHHMMSS'

gear_ratio = {}
gear_ratio['namiki'] = (46.0/14.0+1)**4  # namiki    "337:1", output rotation/motor input
gear_ratio['maxon'] = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
gear_ratio['faulhaber'] = 256.0  		  # faulhaber "256:1", output rotation/motor input
T = 0  # theta axis idx -- NOT the motor axis ID!!
P = 1  # phi axis idx -- NOT the motor axis ID!!
axis_labels = ('theta', 'phi')

# Joe can't believe Python makes you type this many characters to do this...
def list_from_one_or_list(one_item_or_list):
    if not(isinstance(one_item_or_list,list)):
        one_item_or_list = [one_item_or_list]
    return one_item_or_list

# enumeration of verbosity level to stdout
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

# Mapping of radial coordinate R to pseudo-radial coordinate S (distance along focal surface from optical axis)
R2Spoly = [5.00010E-01,9.99997E-01,1.91532E-07,1.72104E-09,7.31761E-11,-5.78982E-13,3.30271E-15,-1.11245E-17,1.90376E-20,-1.26341E-23]
R2S_lookup_data = np.genfromtxt('focal_surface_lookup.csv',comments="#",delimiter=",")
def R2S_lookup(R):
    return np.interp(R,R2S_lookup_data[:,0],R2S_lookup_data[:,2],left=float('nan'))
def S2R_lookup(S):
    return np.interp(S,R2S_lookup_data[:,2],R2S_lookup_data[:,0],left=float('nan'))

