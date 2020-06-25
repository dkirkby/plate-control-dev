# -*- coding: utf-8 -*-
import os
import inspect
import numpy as np
import math
from datetime import datetime, timedelta
import pytz
import collections
import csv

"""Constants, environment variables, and convenience methods used in the
plate_control code for fiber positioners.
"""

# Required environment variables
POSITIONER_LOGS_PATH = os.environ.get('POSITIONER_LOGS_PATH') # corresponds to https://desi.lbl.gov/svn/code/focalplane/positioner_logs
FP_SETTINGS_PATH = os.environ.get('FP_SETTINGS_PATH') # corresponds to https://desi.lbl.gov/svn/code/focalplane/fp_settings

# Interpreter settings
np.set_printoptions(suppress=True) # suppress auto-scientific notation when printing np arrays

# Verson of plate_control code we are running
# Determined by reading what path in the directory structure we are running from.
# This works on assumption of the particular directory structure that we have set up in the SVN, true as of 2017-02-07.
# Should result in either 'trunk' or 'v0.31' or the like.
petal_directory = os.path.dirname(os.path.abspath(inspect.getframeinfo(inspect.currentframe()).filename))
code_version = petal_directory.split(os.path.sep)[-2]

# Directory locations
dirs = {}
if 'DESI_HOME' in os.environ:
    home = os.environ.get('DESI_HOME')
elif 'HOME' in os.environ:
    home = os.environ.get('HOME')
else:
    home = petal_directory
dirs['temp_files'] = os.path.join(home, 'fp_temp_files')
dir_keys_logs = ['pos_logs', 'fid_logs', 'ptl_logs', 'xytest_data',
                 'xytest_logs', 'xytest_plots', 'xytest_summaries',
                 'calib_logs', 'kpno', 'sequence_logs']
dir_keys_settings = ['pos_settings', 'fid_settings', 'test_settings',
                     'collision_settings', 'hwsetups', 'ptl_settings',
                     'other_settings']
for key in dir_keys_logs:
    dirs[key] = os.path.join(POSITIONER_LOGS_PATH, key)
for key in dir_keys_settings:
    dirs[key] = os.path.join(FP_SETTINGS_PATH, key)
for directory in dirs.values():
    if not os.path.isfile(directory):
        os.makedirs(directory, exist_ok=True)
        
# File locations
positioner_locations_file = os.path.join(petal_directory, 'positioner_locations_0530v14.csv')
small_array_locations_file = os.path.join(dirs['hwsetups'], 'SWIntegration_XY.csv')

# Lookup tables for focal plane coordinate conversions
R_lookup_path = petal_directory + os.path.sep + 'focal_surface_lookup.csv'
R_lookup_data = np.genfromtxt(R_lookup_path, comments="#", delimiter=",")

# Mapping of radial coordinate R to pseudo-radial coordinate S
# (distance along focal surface from optical axis)
def R2S_lookup(R):
    return np.interp(R,R_lookup_data[:,0],R_lookup_data[:,2],left=float('nan'))
def S2R_lookup(S):
    return np.interp(S,R_lookup_data[:,2],R_lookup_data[:,0],left=float('nan'))
def R2Z_lookup(R):
    return np.interp(R,R_lookup_data[:,0],R_lookup_data[:,1],left=float('nan'))
def Z2R_lookup(S):
    return np.interp(S,R_lookup_data[:,1],R_lookup_data[:,0],left=float('nan'))
def R2N_lookup(R):
    return np.interp(R,R_lookup_data[:,0],R_lookup_data[:,3],left=float('nan'))
def N2R_lookup(S):
    return np.interp(S,R_lookup_data[:,3],R_lookup_data[:,0],left=float('nan'))

# composite focal surface lookup methods for 3D out-of-shell QST transforms
def S2N_lookup(S):
    return R2N_lookup(S2R_lookup(S))  # return nutation angles in degrees

def S2Z_lookup(S):
    return R2Z_lookup(S2R_lookup(S))

def Z2S_lookup(Z):
    return R2S_lookup(Z2R_lookup(Z))

def N2S_lookup(N):
    return R2S_lookup(N2R_lookup(N))  # takes nutation angles in degrees

# Generic map of positioner device locs to their neighboring locs
generic_pos_neighbor_locs_path = os.path.join(petal_directory, 'generic_pos_neighbor_locs.csv')
generic_pos_neighbor_locs = {}
if os.path.exists(generic_pos_neighbor_locs_path):
    with open(generic_pos_neighbor_locs_path, 'r', newline='') as file:
        reader = csv.DictReader(file)
        neighbor_fields = [f for f in reader.fieldnames if f != 'DEVICE_LOC']
        for row in reader:
            neighbors = {int(row[f]) for f in neighbor_fields if row[f] not in ['']}
            generic_pos_neighbor_locs[int(row['DEVICE_LOC'])] = neighbors
else:
    generic_pos_neighbor_locs = 'not found: ' + generic_pos_neighbor_locs_path

# Mapping of positioner power supplies to can channels
#  2020-06-25 [JHS] For usage of new petalboxes with 20 can channels, an alternate
#  map will need to be provided here. Selection of which map to use will need to
#  be given by some configuration argument during petal initialization.
power_supply_canbus_map = {'V1':{'can10', 'can11', 'can13', 'can22', 'can23'},
                           'V2':{'can12', 'can14', 'can15', 'can16', 'can17'}}

# Constants
deg = '\u00b0'
mm = 'mm'
um_per_mm = 1000
deg_per_rad = 180./math.pi
rad_per_deg = math.pi/180.
timestamp_format = '%Y-%m-%dT%H:%M:%S%z' # see strftime documentation
filename_timestamp_format = '%Y%m%dT%H%M%S%z'
gear_ratio = {}
gear_ratio['namiki'] = (46.0/14.0+1)**4  # namiki    "337:1", output rotation/motor input
gear_ratio['maxon'] = 4100625.0/14641.0  # maxon     "280:1", output rotation/motor input
gear_ratio['faulhaber'] = 256.0  		 # faulhaber "256:1", output rotation/motor input
T = 0  # theta axis idx -- NOT the motor axis ID!!
P = 1  # phi axis idx -- NOT the motor axis ID!!
axis_labels = ('theta', 'phi')
schedule_checking_numeric_angular_tol = 0.01 # deg, equiv to about 1 um at full extension of both arms
near_full_range_reduced_hardstop_clearance_factor = 0.75 # applies to hardstop clearance values in special case of "near_full_range" (c.f. Axis class in posmodel.py)

# Nominal and tolerance calibration values
nominals = collections.OrderedDict()
nominals['LENGTH_R1']        = {'value':   3.0, 'tol':    1.0}
nominals['LENGTH_R2']        = {'value':   3.0, 'tol':    1.0}
nominals['OFFSET_T']         = {'value':   0.0, 'tol':  200.0}
nominals['OFFSET_P']         = {'value':   0.0, 'tol':   50.0}
nominals['OFFSET_X']         = {'value':   0.0, 'tol': 1000.0}
nominals['OFFSET_Y']         = {'value':   0.0, 'tol': 1000.0}
nominals['PHYSICAL_RANGE_T'] = {'value': 370.0, 'tol':   50.0}
nominals['PHYSICAL_RANGE_P'] = {'value': 190.0, 'tol':   50.0}
nominals['GEAR_CALIB_T']     = {'value':   1.0, 'tol':    0.05}
nominals['GEAR_CALIB_P']     = {'value':   1.0, 'tol':    0.05}

# Conservatively accessible angle ranges (intended to be valid for any basically
# functional postioner, and for which a seed calibration is at least roughly known).
# All angles in deg.
conservative_min_posintP_extended = 10.0
conservative_min_posintP_retracted = 120.0
conservative_max_posintP = 170.0
conservative_min_posintT = -170.0
conservative_max_posintT = 170.0

# keepout envelope expansion parameter keys
keepout_expansion_keys = ['KEEPOUT_EXPANSION_PHI_RADIAL',
                          'KEEPOUT_EXPANSION_PHI_ANGULAR',
                          'KEEPOUT_EXPANSION_THETA_RADIAL',
                          'KEEPOUT_EXPANSION_THETA_ANGULAR']

# test for whether certain posstate keys are classified as "calibration" vals
calib_keys = set(nominals.keys()) | set(keepout_expansion_keys)
calib_keys.add('CLASSIFIED_AS_RETRACTED')
def is_calib_key(key):
    return key.upper() in calib_keys

# state data fields associated with "late" committing to database
late_commit_defaults = {'OBS_X':None,
                        'OBS_Y':None,
                        'PTL_X':None,
                        'PTL_Y':None,
                        'PTL_Z':None,
                        'FLAGS':None}

# performance grade letters
grades = ['A', 'B', 'C', 'D', 'F', 'N/A']

# move command strings
valid_move_commands = {'QS', 'dQdS', 'obsXY', 'obsdXdY', 'ptlXY', 'poslocXY',
                       'poslocdXdY', 'poslocTP', 'posintTP', 'dTdP'}

def decipher_posflags(flags):
    '''translates posflag to readable reasons, bits taken from petal.py
    simple problem of locating the leftmost set bit, always 0b100 on the
    right input flags. presence of non-positioner bits from FVC/PM is OK
    input flags must be an array-like or list-like object'''
    pos_bit_dict = {0:  'Matched',
                    2:  'Normal positioner',
                    16: 'Control disabled',
                    17: 'Fibre nonintact',
                    18: 'CAN communication error',
                    19: 'Overlapping targets',
                    20: 'Frozen by anticollision',
                    21: 'Unreachable by positioner',
                    22: 'Out of petal boundaries',
                    23: 'Multiple requests',
                    24: 'Device nonfunctional',
                    25: 'Move table rejected',
                    26: 'Exceeded patrol limits'}

    def decipher_flag(flag):
        bit = np.floor(np.log2(flag)).astype(int)
        if bit in pos_bit_dict:
            return pos_bit_dict[bit]
        elif bit < 26:  # not a positioner bit, but probably valid from FVC/PM
            flag_cleared = flag & ~(1 << bit)  # namely, flag - (1<<bit)
            return decipher_flag(flag_cleared)
        else:
            return (f'Invalid input flag {flags} with leftmost '
                    f'set bit at {bit} further than 26')

    flags = np.array(flags).reshape(-1,).astype(int)  # 1d to enable indexing
    return [decipher_flag(flag) for flag in flags]


class collision_case(object):
    """Enumeration of collision cases. The I, II, and III cases are described in
    detail in DESI-0899.
    """
    def __init__(self):
        self.I    = 0  # no collision
        self.II   = 1  # phi arm against neighboring phi arm
        self.III  = 2  # phi arm against neighboring central body
        self.IV   = 3  # phi arm against neighboring circular keepout
        self.GFA  = 4  # phi arm against the GFA fixed keepout envelope
        self.PTL  = 5  # phi arm against the Petal edge keepout envelope
        self.fixed_cases = {self.PTL,self.GFA}
case = collision_case()

# Collision resolution methods
nonfreeze_adjustment_methods = ['pause',
                                'extend_A','retract_A',
                                'extend_B','retract_B',
                                'rot_ccw_A','rot_cw_A',
                                'rot_ccw_B','rot_cw_B',
                                'repel_ccw_A','repel_cw_A',
                                'repel_ccw_B','repel_cw_B']
all_adjustment_methods = nonfreeze_adjustment_methods + ['freeze']
num_timesteps_clearance_margin = 2 # this value * PosCollider.timestep --> small extra wait for a neighbor to move out of way

# Convenience methods
rotmat2D = lambda angle: [math.cos(angle*rad_per_deg), - math.sin(angle*rad_per_deg), math.sin(angle*rad_per_deg), math.cos(angle*rad_per_deg)]
transpose = lambda matrix: [list(x) for x in zip(*matrix)] # slower than numpy.transpose() if you *already* have a numpy array, but much faster on small python lists

def sign(x):
    """Return the sign of the value x as +1, -1, or 0."""
    if x > 0.:
        return 1
    elif x < 0.:
        return -1
    else:
        return 0

def join_notes(*args):
    '''Concatenate items into a "note" string with standard format. A list or
    tuple arg is treated as a single "item". So for example if you want the
    subelements of a list "joined", then argue it expanded, like *mylist
    '''
    separator = '; '
    if len(args) == 0:
        return ''
    elif len(args) == 1:
        return str(args[0])
    strings = (str(x) for x in args if x != '')
    return separator.join(strings)

def linspace(start,stop,num):
    """Return a list of floats linearly spaced from start to stop (inclusive).
    List has num elements."""
    return [i*(stop-start)/(num-1)+start for i in range(num)]

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
def now():
    # current TZ unaware local time (), then TZ aware in local timezone
    return datetime.now().astimezone()


def utcnow():
    return datetime.now().astimezone(pytz.timezone('UTC'))


def timestamp_str(t=None):
    if t is None:
        t = utcnow()
    return t.strftime(timestamp_format)


def filename_timestamp_str(t=None):
    if t is None:
        t = utcnow()
    return t.strftime(filename_timestamp_format)


def dir_date_str(t=None):
    '''returns date string for the directory name, changes at noon Arizona'''
    if t is None:
        t = now()
    t = t.astimezone(pytz.timezone('America/Phoenix')) - timedelta(hours=12)
    return f'{t.year:04}{t.month:02}{t.day:02}'


# other misc functions
def ordinal_str(number):
    '''
    Returns a string of the number plus 'st', 'nd', 'rd', 'th' as appropriate.
    '''
    numstr = str(number)
    last_digit = numstr[-1]
    if last_digit == '1':
        return numstr + 'st'
    if last_digit == '2':
        return numstr + 'nd'
    if last_digit == '3':
        return numstr + 'rd'
    return numstr + 'th'
