import os
import cProfile
import pstats
import sys
sys.path.append(os.path.abspath('../../../petal/'))
import posconstants as pc

device_locations_path = '../../positioner_locations_0530v14.csv'

pos_dir = 'pos_parameter_sets'
pos_prefix = 'posparams_'

req_dir = 'move_request_sets'
req_prefix = 'requests_'

def bool(s):
    if not s or s in {'False','0','None','FALSE','NONE','false','none'}:
        return False
    return True

data_types = {'POS_ID':str, 'DEVICE_ID':int, 'CTRL_ENABLED':bool,
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

# Timing profiler wrapper function
n_stats_lines = 15
statsfile = os.path.join(pc.dirs['temp_files'],'stats_harness')
def profile(evaluatable_string):
    print(evaluatable_string)
    cProfile.run(evaluatable_string,statsfile)
    p = pstats.Stats(statsfile)
    p.strip_dirs()
    p.sort_stats('tottime')
    p.print_stats(n_stats_lines)