import os
import inspect
import numpy as np
import math
import datetime
import collections

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
dirs = {}
dirs['all_logs']     = os.environ.get('POSITIONER_LOGS_PATH') # corresponds to https://desi.lbl.gov/svn/code/focalplane/positioner_logs
dirs['all_settings'] = os.environ.get('FP_SETTINGS_PATH') # corresponds to https://desi.lbl.gov/svn/code/focalplane/fp_settings
dirs['positioner_locations_file'] = os.environ.get('FP_SETTINGS_PATH')+'/hwsetups/Petal_Metrology.csv' # this is NOT metrology, it is a *bad* naming. it is nominals!
dirs['positioner_neighbors_file'] = os.environ.get('FP_SETTINGS_PATH')+'/hwsetups/neighbor_locs'  # neighbor locations dictionary by DEVICE_LOC
dirs['small_array_locations_file']=os.getenv('FP_SETTINGS_PATH')+'/hwsetups/SWIntegration_XY.csv'
dirs['petal2_fiducials_metrology_file']=os.getenv('FP_SETTINGS_PATH')+'/hwsetups/petal2_fiducials_metrology.csv'
dirs['petalbox_configurations'] = os.getenv('FP_SETTINGS_PATH') + '/ptl_settings/petalbox_configurations_by_ptl_id.json' # temporary until configuration info is sent through petal init 
if 'DESI_HOME' in os.environ:
    dirs['temp_files']   = os.environ.get('DESI_HOME') + os.path.sep + 'fp_temp_files' + os.path.sep
elif 'HOME' in os.environ:
    dirs['temp_files'] = os.environ.get('HOME') + os.path.sep + 'fp_temp_files' + os.path.sep
else:
    print("No DESI_HOME or Home defined in environment, assigning temp file generation to current directory/fp_temp_files")
    dirs['temp_files'] = os.path.abspath('./') + 'fp_temp_files' + os.path.sep
dir_keys_logs        = ['pos_logs','fid_logs','ptl_logs','xytest_data','xytest_logs','xytest_plots','xytest_summaries']
dir_keys_settings    = ['pos_settings','fid_settings','test_settings','collision_settings','hwsetups','ptl_settings','other_settings']
for key in dir_keys_logs:
    dirs[key] = os.path.join(dirs['all_logs'], key)
for key in dir_keys_settings:
    dirs[key] = os.path.join(dirs['all_settings'], key)
try:
    for directory in dirs.values():    
        os.makedirs(directory,exist_ok=True)
except:
    pass

# Lookup tables for focal plane coordinate conversions
R_lookup_path = petal_directory + os.path.sep + 'focal_surface_lookup.csv'
R_lookup_data = np.genfromtxt(R_lookup_path,comments="#",delimiter=",")

# Mapping of radial coordinate R to pseudo-radial coordinate S (distance along focal surface from optical axis)
R2S_poly = [-1.26341e-23,1.90376e-20,-1.11245e-17,3.30271e-15,-5.78982e-13,7.31761e-11,1.72104e-09,1.91532e-07,0.999997,0.50001]
def R2S_lookup(R):
    return np.interp(R,R_lookup_data[:,0],R_lookup_data[:,2],left=float('nan'))
def S2R_lookup(S):
    return np.interp(S,R_lookup_data[:,2],R_lookup_data[:,0],left=float('nan'))

# Mapping of radial coordinate R to Z5 coordinate on the nominal asphere
R2Z_poly = [6.74215e-23,-7.75243e-20,2.9168e-17,-5.23944e-15,1.61621e-12,-4.82781e-10,1.24578e-08,-0.000100884,6.63924e-06,-2.33702e-05]
def R2Z_lookup(R):
    return np.interp(R,R_lookup_data[:,0],R_lookup_data[:,1],left=float('nan'))
def Z2R_lookup(S):
    return np.interp(S,R_lookup_data[:,1],R_lookup_data[:,0],left=float('nan'))

# Mapping of positioner power supplies to can channels
power_supply_can_map = {'V1':{'can10','can11','can13','can22', 'can23'},
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

# Types
class collision_case(object):
    """Enumeration of collision cases. The I, II, and III cases are described in
    detail in DESI-0899.
    """
    def __init__(self):
        self.I    = 0  # no collision
        self.II   = 1  # phi arm against neighboring phi arm
        self.IIIA = 2  # phi arm of positioner 'A' against neighbor 'B' central body
        self.IIIB = 3  # phi arm of positioner 'B' against neighbor 'A' central body
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
@property
def now():
    return datetime.datetime.utcnow().astimezone()

def timestamp_str_now():
    return now().strftime(timestamp_format)

def filename_timestamp_str_now():
    return now().strftime(filename_timestamp_format)

# other misc functions
def ordinal_str(number):
    '''Returns a string of the number plus 'st', 'nd', 'rd', 'th' as appropriate.
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
