'''To run harness.py repeatedly.'''

import os
import sys
sys.path.append(os.path.abspath('../../petal/'))
import posconstants as pc
import configobj
import runpy

collider_filename = '_collision_settings_DEFAULT.conf'
collider_filepath = os.path.join(pc.dirs['collision_settings'],collider_filename)
collider_config = configobj.ConfigObj(collider_filepath,unrepr=True)

run_config = {'PHI_RADIAL':    [  0, 0.1, 0.2, 0.3, 0.4,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0],
              'PHI_ANGULAR':   [  0,   0,   0,   0,   0,   0,   0,   0,   0, 1.0, 2.0, 3.0,   0,   0,   0],
              'THETA_RADIAL':  [  0,   0,   0,   0,   0, 0.1, 0.2, 0.3, 0.4,   0,   0,   0,   0,   0,   0],
              'THETA_ANGULAR': [  0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0,   0, 1.0, 2.0, 3.0]}

for i in range(len(run_config['PHI_RADIAL'])):
    for key in run_config.keys():
        full_key = 'KEEPOUT_EXPANSION_' + key
        collider_config[full_key] = run_config[key][i]
        collider_config.write()
    file_globals = runpy.run_path("harness.py")
    