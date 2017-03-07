import os
import inspect
import numpy as np
import enum
import datetime

"""Constants and convenience methods used in the control of the Fiber Postioner.
"""

# Interpreter settings
np.set_printoptions(suppress=True) # suppress auto-scientific notation when printing np arrays

# Verson of plate_control code we are running
# Determined by reading what path in the directory structure we are running from.
# This works on assumption of the particular directory structure that we have set up in the SVN, true as of 2017-02-07.
# Should result in either 'trunk' or 'v0.31' or the like.
petal_directory = os.path.dirname(os.path.abspath(inspect.getframeinfo(inspect.currentframe()).filename))
code_version = petal_directory.split(os.path.sep)[-2]

# File location directories
# For environment paths, set the paths in your .bashrc file, by adding the lines:
#    export POSITIONER_LOGS_PATH="/my/path/to/positioner_logs"
#    export FP_SETTINGS_PATH="/my/path/to/fp_settings"
all_logs_directory           = os.environ.get("POSITIONER_LOGS_PATH") # corresponds to https://desi.lbl.gov/svn/code/focalplane/positioner_logs
all_settings_directory       = os.environ.get("FP_SETTINGS_PATH") # corresponds to https://desi.lbl.gov/svn/code/focalplane/fp_settings
pos_logs_directory           = all_logs_directory + os.path.sep + 'pos_logs' + os.path.sep
fid_logs_directory           = all_logs_directory + os.path.sep + 'fid_logs' + os.path.sep
xytest_data_directory        = all_logs_directory + os.path.sep + 'xytest_data' + os.path.sep
xytest_logs_directory        = all_logs_directory + os.path.sep + 'xytest_logs' + os.path.sep
xytest_plots_directory       = all_logs_directory + os.path.sep + 'xytest_plots' + os.path.sep
xytest_summaries_directory   = all_logs_directory + os.path.sep + 'xytest_summaries' + os.path.sep
pos_settings_directory       = all_settings_directory + os.path.sep + 'pos_settings' + os.path.sep
fid_settings_directory       = all_settings_directory + os.path.sep + 'fid_settings' + os.path.sep
test_settings_directory      = all_settings_directory + os.path.sep + 'test_settings' + os.path.sep
collision_settings_directory = all_settings_directory + os.path.sep + 'collision_settings' + os.path.sep
hwsetups_directory           = all_settings_directory + os.path.sep + 'hwsetups' + os.path.sep
# 2017-02-07, Joe: previously there was a function here called 'set_logs_directory()'. It was for being able
# to change these paths above at runtime. This is a bad thing to do, because it breaks our assumptions elsewhere
# about how we are keeping config files and log files up-to-date in the SVN. So I removed that function. We
# still may need a more mature implementation of storing/retrieving these settings and logs, but *whatever* it is,
# it has to be thought through clearly and reviewed.

# Mapping of radial coordinate R to pseudo-radial coordinate S (distance along focal surface from optical axis)
R2Spoly = [5.00010E-01,9.99997E-01,1.91532E-07,1.72104E-09,7.31761E-11,-5.78982E-13,3.30271E-15,-1.11245E-17,1.90376E-20,-1.26341E-23]
R2S_lookup_path = petal_directory + os.path.sep + 'focal_surface_lookup.csv'
R2S_lookup_data = np.genfromtxt(R2S_lookup_path,comments="#",delimiter=",")
def R2S_lookup(R):
    return np.interp(R,R2S_lookup_data[:,0],R2S_lookup_data[:,2],left=float('nan'))
def S2R_lookup(S):
    return np.interp(S,R2S_lookup_data[:,2],R2S_lookup_data[:,0],left=float('nan'))

# Constants
deg = '\u00b0'
mm = 'mm'
um_per_mm = 1000
timestamp_format = '%Y-%m-%d %H:%M:%S.%f' # see strftime documentation
filename_timestamp_format = '%Y-%m-%d_T%H%M%S'
gear_ratio = {}
gear_ratio['namiki'] = (46.0/14.0+1)**4  # namiki    "337:1", output rotation/motor input
gear_ratio['maxon'] = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
gear_ratio['faulhaber'] = 256.0  		 # faulhaber "256:1", output rotation/motor input
T = 0  # theta axis idx -- NOT the motor axis ID!!
P = 1  # phi axis idx -- NOT the motor axis ID!!
axis_labels = ('theta', 'phi')

# Nominal and tolerance calibration values
nominals = {'LENGTH_R1'        : {'value':   3.0, 'tol':    1.0},
            'LENGTH_R2'        : {'value':   3.0, 'tol':    1.0},
            'OFFSET_T'         : {'value':   0.0, 'tol':  200.0},
            'OFFSET_P'         : {'value':   0.0, 'tol':   50.0},
            'GEAR_CALIB_T'     : {'value':   1.0, 'tol':    0.05},
            'GEAR_CALIB_P'     : {'value':   1.0, 'tol':    0.05},
            'OFFSET_X'         : {'value':   0.0, 'tol': 1000.0},
            'OFFSET_Y'         : {'value':   0.0, 'tol': 1000.0},
            'PHYSICAL_RANGE_T' : {'value': 370.0, 'tol':   50.0},
            'PHYSICAL_RANGE_P' : {'value': 190.0, 'tol':   50.0}}

# Types
class case(enum.Enum):
    """Enumeration of collision cases. The I, II, and III cases are described in
    detail in DESI-0899.
    """
    I    = 0  # no collision
    II   = 1  # phi arm against neighboring phi arm
    IIIA = 2  # phi arm of positioner 'A' against neighbor 'B' central body
    IIIB = 3  # phi arm of positioner 'B' against neighbor 'A' central body
    GFA  = 4  # phi arm against the GFA fixed keepout envelope
    PTL  = 5  # phi arm against the Petal edge keepout envelope

# Convenience methods
rotmat2D = lambda angle: [np.cos(np.deg2rad(angle)), - np.sin(np.deg2rad(angle)), np.sin(np.deg2rad(angle)), np.cos(np.deg2rad(angle))]

# Functions for handling mixes of [M][N] vs [M] dimension lists
def listify(uv, keep_flat=False):
    """Turn [u,v] into [[u],[v]], if it isn't already.
    Turn uv into a list [uv] if it isn't already.
    In the special case where uv is a single item list, it remains so in the return.
    A boolean is returned saying whether the item was modified.
    If optional argument 'flat' is true, then [u,v] remains [u,v].
    """
    if not(isinstance(uv,list)):
        return [uv], True
    if len(uv) == 1 or keep_flat:
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
    
def listify2d(uv):
    """If uv is [u,v], return [[u,v]]. Otherwise return uv.
    I.e., so [[u1,v1],[u2,v2],...] would stay the same
    """
    if isinstance(uv,list):
        if not(isinstance(uv[0],list)) and len(uv) == 2:
            return [uv]
        else:
            return uv

def concat_lists_of_lists(L1, L2):
    """Always output an [N][M] list, for M dimensional coordinate inputs initial and new.
    E.g.
    [] + [u,v] --> [[u,v]]
    [] + [[u1,v1],[u2,v2],...] --> same
    [[u1,v1],[u2,v2]] + [u3,v3] --> [[u1,v1],[u2,v2],[u3,v3]]
    [[u1,v1],[u2,v2]] + [[u3,v3],[u4,v4],...] --> [[u1,v1],[u2,v2],[u3,v3],[u4,v4],...]
    """
    if not(L1):
        L1 = []
    elif not(isinstance(L1[0],list)):
        L1 = [L1]
    if not(L2):
        L2 = []
    elif not(isinstance(L2[0],list)):
        L2 = [L2]
    return L1 + L2


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

# timestamp functions
def timestamp_str_now():
    return datetime.datetime.now().strftime(timestamp_format)

def filename_timestamp_str_now():
    return datetime.datetime.now().strftime(filename_timestamp_format)

# other misc functions
def ordinal_str(number):
    '''Returns a string of the number plus 'st', 'nd', 'rd', 'th' as appropriate.
    '''
    numstr = str(number)
    last_digit = numstr[-1]
    if last_digit == 1:
        return numstr + 'st'
    if last_digit == 2:
        return numstr + 'nd'
    if last_digit == 3:
        return numstr + 'rd'
    return numstr + 'th'
