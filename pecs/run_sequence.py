# -*- coding: utf-8 -*-
"""
Perform a sequence of moves + FVC measurements on hardware.
"""

import os
script_name = os.path.basename(__file__)

# command line argument parsing
import argparse
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-i', '--infile', type=str, required=True, help='Path to sequence file, readable by sequence.py. For some common pre-cooked sequences, run sequence_generator.py.')
parser.add_argument('-d', '--debug', action='store_true', help='suppresses sending "SYNC" to positioners, so they will not actually move')
args = parser.parse_args()

# read sequence file
import sequence
seq = sequence.read(args.infile)

# set up a log file
import logging
import time
try:
    import posconstants as pc
except:
    import sys
    path_to_petal = '../petal'
    sys.path.append(os.path.abspath(path_to_petal))
    print('Couldn\'t find posconstants the usual way, resorting to sys.path.append')
    import posconstants as pc
log_dir = pc.dirs['sequence_logs']
log_name = pc.filename_timestamp_str() + '_set_calibrations.log'
log_path = os.path.join(log_dir, log_name)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
[logger.removeHandler(h) for h in logger.handlers]
fh = logging.FileHandler(filename=log_path, mode='a', encoding='utf-8')
sh = logging.StreamHandler()
formatter = logging.Formatter(fmt='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S %z')
formatter.converter = time.gmtime
fh.setFormatter(formatter)
sh.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(sh)
logger.info(f'Running {script_name} to perform a positioner move + measure sequence.')
logger.info(f'Input file is: {args.infile}')
logger.info(f'Contents are:\n{seq}')

# set up PECS (online control system)
try:
    from pecs import PECS
    pecs = PECS(interactive=False)
    pecs.logger = logger
    logger.info(f'PECS initialized, discovered PC ids {pecs.pcids}')
    posids = set(table['POS_ID'])
    pecs.ptl_setup(pecs.pcids, posids=posids)
    pecs_on = True
except:
    logger.info(f'PECS initialization failed')
    pecs_on = False