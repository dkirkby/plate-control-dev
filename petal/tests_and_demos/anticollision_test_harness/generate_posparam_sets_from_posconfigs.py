"""Reads in config files from pos_settings folder, and generates sets of
corresponding simulated positioners, for testing the anticollision code.
"""

import os
import configobj

petals_to_generate = [2,3,4,5,6,7,8,9,10,11] # petal IDs
pos_settings_dir_rel = '../../../../../fp_settings/pos_settings/'
pos_settings_dir_abs = os.path.abspath(pos_settings_dir_rel)
all_files = os.listdir(pos_settings_dir_abs)
m_files = [file for file in all_files if 'unit_M' in file]
for file in m_files:
    filepath = os.path.join(pos_settings_dir_abs,file)
    conf = configobj.ConfigObj(filepath,unrepr=True,encoding='utf-8')
    if conf['PETAL_ID'] in petals_to_generate:
        