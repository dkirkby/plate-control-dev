# -*- coding: utf-8 -*-
"""
Created on Tue Feb 11 16:01:48 2020
@author: jhsilber

Customized script for merging data into posparam format. Data is presumed
pulled from online databases:
    
    "calib" --> http://web.replicator.dev-cattle.stable.spin.nersc.org:60040/DESIPositioners/Positioner_calibration.html
    "moves" --> http://web.replicator.dev-cattle.stable.spin.nersc.org:60040/DESIPositioners/Positioner_moves.html
    
Data is assumed saved as csv using the browser tool.

Sample SQL queries:
    
    "calib" --> select petal_id,pos_id,time_recorded,device_loc,length_r1,length_r2,offset_x,offset_y,offset_t,offset_p,physical_range_t,physical_range_p,gear_calib_t,gear_calib_p from posmovedb.positioner_calibration_p3 PM where EXISTS (select * from posmovedb.positioner_calibration_index_p3 where id = PM.pos_id and last_index=PM.pos_calib_index)
    "moves" --> select petal_id,pos_id,time_recorded,ctrl_enabled from posmovedb.positioner_moves_p3 PM where exists (select * from posmovedb.positioner_moves_index_p3 where id = PM.pos_id and last_index=PM.pos_move_index)

Direct links to db + queries execution:
    
    "calib" --> http://web.replicator.dev-cattle.stable.spin.nersc.org:60040/QE/DESI/app/query?sql_statement=select%20petal_id%2Cpos_id%2Ctime_recorded%2Cdevice_loc%2Clength_r1%2Clength_r2%2Coffset_x%2Coffset_y%2Coffset_t%2Coffset_p%2Cphysical_range_t%2Cphysical_range_p%2Cgear_calib_t%2Cgear_calib_p%20from%20posmovedb.positioner_calibration_p3%20PM%20where%20EXISTS%20%28select%20%2A%20from%20posmovedb.positioner_calibration_index_p3%20where%20id%20%3D%20PM.pos_id%20and%20last_index%3DPM.pos_calib_index%29&dbname=desi&page=0&output_type=HTML&maxrows=550&pagerows=100
    "moves" --> http://web.replicator.dev-cattle.stable.spin.nersc.org:60040/QE/DESI/app/query?sql_statement=select%20petal_id%2Cpos_id%2Ctime_recorded%2Cctrl_enabled%20from%20posmovedb.positioner_moves_p3%20PM%20where%20exists%20%28select%20%2A%20from%20posmovedb.positioner_moves_index_p3%20where%20id%20%3D%20PM.pos_id%20and%20last_index%3DPM.pos_move_index%29&dbname=desi&page=0&output_type=HTML&maxrows=550&pagerows=100

"""

import os
import pandas

posids = 'all' # 'all', for all posids on that petal, or else a limited set
output_file = 'posparams_30001.csv'

data_folder = 'C:/Users/jhsilber/Desktop/anticollision targets'
calibdb_name = 'PTL03 online calib db, retrieved 2020-03-09.csv'
movesdb_name = 'PTL03 online moves db, retrieved 2020-03-09.csv'
calibpath = os.path.join(data_folder, calibdb_name)
movespath = os.path.join(data_folder, movesdb_name)
calib = pandas.read_csv(calibpath)
moves = pandas.read_csv(movespath)

if posids == 'all':
    posids = set(calib['pos_id']).intersection(moves['pos_id'])
posids = sorted(posids)

calib.sort_values('time_recorded', ascending=False, inplace=True)
moves.sort_values('time_recorded', ascending=False, inplace=True)

columns_calib = ['DEVICE_LOC','LENGTH_R1','LENGTH_R2','OFFSET_T',
                 'OFFSET_P','OFFSET_X','OFFSET_Y','PHYSICAL_RANGE_T','PHYSICAL_RANGE_P']
columns_moves = ['CTRL_ENABLED']
columns_calib_upperlower = {C:C.lower() for C in columns_calib}
columns_moves_upperlower = {C:C.lower() for C in columns_moves}

result = pandas.DataFrame(index=posids, columns=columns_calib + columns_moves)

def grab(dataframe, columns_upperlower):
    remaining = set(posids)
    for i in dataframe.index:
        posid = dataframe['pos_id'][i]
        if posid in remaining:
            for C,c in columns_upperlower.items():
                result[C][posid] = dataframe[c][i]
            remaining.remove(posid)
            
grab(calib, columns_calib_upperlower)
grab(moves, columns_moves_upperlower)

result.to_csv(output_file, index_label='POS_ID')
      