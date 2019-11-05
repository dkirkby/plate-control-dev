'''To run harness.py repeatedly.'''

import os
import sys
sys.path.append(os.path.abspath('../../../petal/'))
import posconstants as pc
import configobj


collider_filename = '_collision_settings_DEFAULT.conf'
collider_filepath = os.path.join(pc.dirs['collision_settings'],collider_filename)
collider_config = configobj.ConfigObj(collider_filepath,unrepr=True)

for val in [0.2, 0.3, 0.4, 0.5]:
    collider_config['KEEPOUT_EXPANSION_PHI_RADIAL'] = val
    collider_config.write()
    