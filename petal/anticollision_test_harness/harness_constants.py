import os
import cProfile
import pstats
import sys
sys.path.append(os.path.abspath('../../petal/'))
import posconstants as pc
import time
import numpy as np
import math

device_locations_path = '../positioner_locations_0530v14.csv'

pos_dir = os.path.join(pc.dirs['all_settings'], 'harness_settings', 'pos_parameter_sets')
req_dir = os.path.join(pc.dirs['all_settings'], 'harness_settings', 'move_request_sets')
pos_prefix = 'posparams_'
req_prefix = 'requests_'

def bool(s):
    if not s or s in {'False','0','None','FALSE','NONE','false','none'}:
        return False
    return True

data_types = {'POS_ID':str, 'DEVICE_LOC':int, 'CTRL_ENABLED':bool,
              'LENGTH_R1':float, 'LENGTH_R2':float, 'OFFSET_T':float,
              'OFFSET_P':float, 'OFFSET_X':float, 'OFFSET_Y':float,
              'PHYSICAL_RANGE_T':float, 'PHYSICAL_RANGE_P':float,
              'command':str, 'u':float, 'v':float}

def filenumber(filename,prefix):
    base = os.path.basename(filename)
    num_str = os.path.splitext(base)[0].split(prefix)[1]
    return int(num_str)

def filename(prefix,integer):
    return prefix + format(integer,'05d') + '.csv'

def filepath(directory,prefix,integer):
    return os.path.join(directory,filename(prefix,integer))

def compact_timestamp(nowtime=None, basetime=1582915648):
    '''Compact, readable time code. Default return string is six characters
    in length; will exceed this length at basetime + 69 years. Precision is
    rounded to seconds. Default argument baselines it at a recent time on
    Feb 28, 2020, 10:47 AM PST. The argument nowtime is just there for testing.
    '''
    maxchar = 6
    nowtime = time.time() if not nowtime else nowtime
    relative_now = math.floor(nowtime - basetime)
    converted = np.base_repr(relative_now, base=36)
    padded = converted.rjust(maxchar,'0') if len(converted) < maxchar else converted
    return padded

# Timing profiler wrapper function
n_stats_lines = 20
statsfile = os.path.join(pc.dirs['temp_files'],'stats_harness')
def profile(evaluatable_string):
    print(evaluatable_string)
    cProfile.run(evaluatable_string,statsfile)
    p = pstats.Stats(statsfile)
    p.strip_dirs()
    p.sort_stats('cumtime')
    p.print_stats(n_stats_lines)