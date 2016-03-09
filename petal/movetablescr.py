
#Script for putting together a movetable for testing purposes

import numpy as np


"""Strips out information that isn't necessary to send to petalbox, and
178	        formats for sending. Any cases of multiple tables for one positioner are
179	        merged in sequence into a single table.
180	
181	        Output format:
182	            List of dictionaries.
183	
184	            Each dictionary is the move table for one positioner.
185	
186	            The dictionary has the following fields:
187	           {'posid':'','nrows':0,'motor_steps_T':[],'motor_steps_P':[],'speed_mode_T':[],'speed_mode_P':[],'move_time':[],'postpause':[]}
188	
189	            The fields have the following types and meanings:
190	
191	                posid         ... string                    ... identifies the positioner by 'SERIAL_ID'
192	                nrows         ... unsigned integer          ... number of elements in each of the list fields (i.e. number of rows of the move table)
193	                motor_steps_T ... list of signed integers   ... number of motor steps to rotate on theta axis
194	                                                                    ... motor_steps_T > 0 ... ccw rotation
195	                                                                    ... motor_steps_T < 0 ... cw rotation
196	                motor_steps_P ... list of signed integers   ... number of motor steps to rotate on phi axis
197	                                                                    ... motor_steps_P > 0 ... ccw rotation
198	                                                                    ... motor_steps_P < 0 ... cw rotation
199	                speed_mode_T  ... list of strings           ... 'cruise' or 'creep' mode on theta axis
200	                speed_mode_P  ... list of strings           ... 'cruise' or 'creep' mode on phi axis
201	                movetime      ... list of unsigned floats   ... estimated time the row's motion will take, in seconds, not including the postpause
202	                postpause     ... list of unsigned integers ... pause time after the row's motion, in milliseconds, before executing the next row
203	        """

def calc_steps(verbose,angle = [90, 90, 90], speed_mode = ['cruise', 'creep', 'cruise']):
	gear_ratio = 337  #look up and replace
	i=0	
	steps = np.asarray(angle)
	for a in angle:
		if verbose: print(i)
		if speed_mode[i] == 'cruise':
			steps[i] = int(gear_ratio*steps[i]/3.3)
		elif speed_mode[i] == 'creep':
			steps[i] = int(gear_ratio*steps[i]/.1)
		else:
			steps[i] = 0
		i+=1
		if verbose: print(steps)
		steps = np.array(steps).tolist()
	return steps


def get_tables(verbose=True):
	#Positioner 1
	posid = str(20000)
	nrows = 3

	angle_T = [90, 0, -90]
	speed_mode_T = ['cruise', 'None', 'cruise']
	motor_steps_T = calc_steps(verbose,angle_T, speed_mode_T)

	angle_P = [0, 90, -90]
	speed_mode_P = ['None', 'cruise', 'cruise']
	motor_steps_P = calc_steps(verbose,angle_P, speed_mode_P)


	move_time = [2, 2, 2]
	postpause = [1, 1, 1]


	pos1 = {'posid': posid,'nrows': nrows,'motor_steps_T':motor_steps_T,'motor_steps_P':motor_steps_P,'speed_mode_T':speed_mode_T,'speed_mode_P': speed_mode_P,'move_time':move_time,'postpause':postpause}
	#Positioner 1
	
	pos2 = pos1
	mtables = [pos1, pos2]

	return(mtables)
