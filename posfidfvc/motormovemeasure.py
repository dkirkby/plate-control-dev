'''
motormovemeasure.py

Command functions for operating motortest.py
'''


import fvchandler
import numpy as np
import fitcircle
import time
import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import petalcomm
import posconstants as pc

class MotorMoveMeasure(object):
    def __init__(self, petal_id):
        self.comm = petalcomm.PetalComm(petal_id)
        self.fvc = fvchandler.FVCHandler(fvc_type = 'SBIG')
        self.radius = None
        self.angle_offset = None
        self.offset_x = None
        self.offset_y = None
        self.axis = None
        self.n_fiducial_dots = 1
        self.n_pos_dots = 1 #Do not change, does not support more than 1 positioner
        self.ref_dist_tol = .1 #same as posmovemeasure 
        self.expected_posXY = [[self.offset_x, self.offset_y]]
        self.fiducials_xy = []
        self.allow_cruise = True
        #Configuration
        self.antibacklash = 3 #Degrees from _genl_settings_DEFAULT.conf
        self.hardstop_clearence = 3
        self._gear_ratio = pc.gear_ratio['namiki']
        self._gear_calib = 1 #Will be 1 for a while as we do not currently calibrate gear ratio
        self._ccw_direction = -1 #-1 is the standard wiring for theta and phi since UM00051
        self._stepsize_creep = .1 #posmodel
        self._stepsize_cruise = 3.3 #posmodel
        self._spindown_period = 12 #_genl_setting_DEFAULT.conf
        self._min_distance_cruise = 180.0 #_genl_setting_DEFAULT.conf in motor not shaft degrees
        self._spindown_distance = sum(range(round(self._stepsize_cruise/self._stepsize_creep)+1))*self._stepsize_creep*self._spindown_period
        self._cruise_adjustment = -self._motor_to_shaft(2*self._spindown_distance)
        self._timer_update_rate    = 18e3   # Hz posmodel
        self._motor_speed_creep = self._timer_update_rate * self._stepsize_creep / 2 #2 found from _genl_settings_DEFAULT.conf  # deg/sec posmodel
        self._motor_speed_cruise = 9900.0 * 360.0 / 60.0  # deg/sec (= RPM *360/60) posmodel    
        self.sync_mode = self.sync_mode = 'soft' # 'hard' --> hardware sync line, 'soft' --> CAN sync signal to start positioners #petal.py
        
        self.temporary_move_time_margin = 0.1 # seconds posmodel
        
                
        
    def rehome(self, can_id, axis):
        print('REHOMING can id:', can_id)
        if axis == 'theta':
            self.comm.move(can_id, 'ccw', 'cruise', axis, 507) #507 degrees is 390*1.3 as done in posmodel
            self._wait_while_moving(can_id, 'cruise')
            self.comm.move(can_id, 'cw', 'creep', axis, self.antibacklash + self.hardstop_clearence)
            self._wait_while_moving(can_id, 'creep')
        else:
            self.comm.move(can_id, 'ccw', 'cruise', axis, 247) #247 degrees is 190*1.3 as done in posmodel
            self._wait_while_moving(can_id, 'cruise')
            self.comm.move(can_id, 'cw', 'creep', axis, self.antibacklash + self.hardstop_clearence)
            self._wait_while_moving(can_id, 'creep')
        return
    
    def move(self, can_id, direction, axis, amount):
        #Move Command with built in antibacklash and final creep logic
        print('Moving', axis, direction, str(amount), 'degrees.')
        move_dist = amount #account for spin up and down
        if direction == 'ccw':
            direction_opp = 'cw'
            if amount < 0: #comm.move doesn't take negative values, I want to be able to take them.
                amount = abs(amount) 
                direction = 'cw'
                direction_opp = 'ccw'
        else:
            direction_opp = 'ccw'
            if amount < 0:
                amount = abs(amount)
                direction = 'ccw'
                direction_opp = 'cw'
        true_dist = self._true_move(amount, allow_cruise=self.allow_cruise)
        if true_dist['speed_mode'] == 'cruise':
            move_dist -= self._cruise_adjustment
        self.comm.move(can_id, direction, true_dist['speed_mode'], axis, move_dist)
        self._wait_while_moving(can_id, true_dist['speed_mode'])
        
        true_anti_backlash = self._true_move(self.antibacklash, allow_cruise=self.allow_cruise)
        self.comm.move(can_id, direction, true_anti_backlash['speed_mode'], axis, self.antibacklash)
        self._wait_while_moving(can_id,true_anti_backlash['speed_mode'])
        
        final_creep = amount - (true_dist['distance'] + true_anti_backlash['distance'])
        if final_creep < 0:
            final_creep = abs(final_creep)
            direction = direction_opp
        true_final_creep = self._true_move(final_creep, allow_cruise=False)
        self.comm.move(can_id, direction, 'creep', axis, final_creep)
        self._wait_while_moving(can_id,'creep')
        return
        
    def measure(self):
        meas_posXY, meas_fidXY = self.fvc.measure_and_identify(self.expected_posXY, self.fiducials_xy)
        return meas_posXY[0]
        
    def move_measure(self, can_id, direction, axis, amount):
        self.move(can_id, direction, axis, amount)
        return self.measure()
        
    def calibrate(self,can_id,axis,mode):
        self._identify(can_id=can_id, axis=axis, identify_fiducials = False)
        print('CALIBRATE')
        meas = self._measure_calibration_arc(canid=can_id, axis=axis, mode=mode)
        data = self._calculate_and_set_arms_and_offsets_from_arc_data(meas)
        self.radius = data['radius']
        self.offset_x = data['offset_x']
        self.offset_y = data['offset_y']
        self.axis = axis
        self.angle_offset = data['angle_offset']
        self.expected_posXY = [[self.offset_x, self.offset_y]]
        print('Calibration proposes radius:', self.radius, 'angle offset:', np.rad2deg(self.angle_offset), 'offset x:', self.offset_x, 'offset y:', self.offset_y)
        return data

    def obsXY_to_posPolar(self, xy):
        return self.posXY_to_posPolar(self.obsXY_to_posXY(xy))
    
    def obsXY_to_posXY(self, xy):
        posX = xy[0] - self.offset_x
        posY = xy[1] - self.offset_y
        return [posX, posY]
        
    def posXY_to_posPolar(self, xy):
        arccos_arg = np.dot(xy,[1,0])/np.linalg.norm(xy)
        #sign = np.sign(xy[1])
        angle = np.arccos(arccos_arg)
        if xy[1] < 0:
                angle = 2*np.pi - angle
        return np.rad2deg(angle - self.angle_offset)
        
    def posPolar_to_obsXY(self, angle):
        return self.posXY_to_obsXY(self.posPolar_to_posXY(angle))
    
    def posPolar_to_posXY(self, angle):
        x = self.radius*np.cos(np.deg2rad(angle) + self.angle_offset)
        y = self.radius*np.sin(np.deg2rad(angle) + self.angle_offset)
        return [x,y]
        
    def posXY_to_obsXY(self, xy):
        obsX = xy[0] + self.offset_x
        obsY = xy[1] + self.offset_y
        return [obsX, obsY]
      
    def _measure_calibration_arc(self,canid='all',axis='theta',mode='quick'):
            data = {'target_angle':[], 'measured_obsXY':[], 'xy_center':[0,0], 'radius':0, 'axis':axis}
            if axis == 'theta':
                n_pts = 4 if mode == 'quick' else 11
                initial = -180
                final = 180 #Assume full range is 0,360 (realistically +-190)
            else:
                n_pts = 3 if mode == 'quick' else 7
                initial = 0
                final = 180 #Assume full range is 0,180 (realistically it is ~0,190)
            angles = np.linspace(initial, final, n_pts)
            for angle in angles:
                data['target_angle'].append(angle)
    
            # make the measurements
            print('\'' + mode + '\' calibration arc on ' + axis + ' axis: point 1 of ' + str(n_pts))
            self.rehome(canid, axis)
            xy = self.fvc.measure_and_identify(self.expected_posXY, self.fiducials_xy)
            data['measured_obsXY'] = pc.concat_lists_of_lists(data['measured_obsXY'],xy[0])
            for i in range(1, n_pts):
                print('\'' + mode + '\' calibration arc on ' + axis + ' axis: point ' + str(i+1) + ' of ' + str(n_pts))
                dist = data['target_angle'][i] - data['target_angle'][i-1]
                self.move(canid, 'cw', axis, dist)
                xy = self.fvc.measure_and_identify(self.expected_posXY, self.fiducials_xy)
                data['measured_obsXY'] = pc.concat_lists_of_lists(data['measured_obsXY'],xy[0])
    
            # circle fits
            (xy_ctr,radius) = fitcircle.FitCircle().fit(data['measured_obsXY'])
            data['xy_center'] = xy_ctr
            data['radius'] = radius
            
            return data
    
    def _calculate_and_set_arms_and_offsets_from_arc_data(self, meas_data):
            """Helper function for arc method of calibration. T and P are data dictionaries taken on the
            theta and phi axes. See the _measure_calibration_arc method for more information.
            """
            data = {}
            # gather targets data
            target_angle = meas_data['target_angle']       
            meas_obsXY = meas_data['measured_obsXY']
            
            # arms and offsets
            ctr = np.array(meas_data['xy_center'])
            home_posXY = np.array(meas_obsXY[0]) - ctr
            #sign = np.sign(home_posXY[1])
            arccos_arg = np.dot(home_posXY,[1,0])/np.linalg.norm(home_posXY)
            angle_offset = np.arccos(arccos_arg)
            if home_posXY[1] < 0:
                angle_offset = 2*np.pi - angle_offset
            if meas_data['axis'] == 'theta':
                #petal.set(pos_id,'LENGTH_R1',meas_data['radius'])
                radius = meas_data['radius']
                angle_offset += np.pi
            else:
                #petal.set(pos_id,'LENGTH_R2',meas_data['radius'])
                radius = meas_data['radius']
            #petal.set(pos_id,'OFFSET_X',ctr[0])
            #petal.set(pos_id,'OFFSET_Y',ctr[1])
            
            meas_angle = []
            for point in meas_obsXY:
                point_pXY = np.array(point)-ctr
                arccos_arg = np.dot(point_pXY,[1,0])/np.linalg.norm(point_pXY)
                angle = np.arccos(arccos_arg)
                if home_posXY[1] < 0:
                    angle = 2*np.pi - angle
                meas_angle.append(np.rad2deg(angle - angle_offset))
            
            # gather data to return in an organized fashion (used especially for plotting)
            data = {}
            data['xy_ctr'] = ctr
            data['radius'] = meas_data['radius']
            data['measured_obsXY'] = meas_obsXY
            data['target_angle'] = target_angle
            data['measured_angle'] = meas_angle
            data['axis'] = meas_data['axis']
            data['offset_x'] = ctr[0]
            data['offset_y'] = ctr[1]
            data['angle_offset'] = angle_offset
            return data
       
    def _identify(self, can_id=None, axis='phi', identify_fiducials = True):
        """Generic function for identifying either all fiducials or a single positioner's location.
        """
        print('IDENTIFY')
        nudges = [-10, 10]
        xy_ref = []
        n_dots = self.n_fiducial_dots + self.n_pos_dots
        for i in range(len(nudges)):
            self.move(can_id, 'cw', axis, nudges[i])
            if i == 0:
                xy_init = self.fvc.measure(n_dots)
            else:
                xy_test = self.fvc.measure(n_dots)
            
        ref_idxs = []
        for i in range(len(xy_test)):
            test_delta = np.array(xy_test[i]) - np.array(xy_init)
            test_dist = np.sqrt(np.sum(test_delta**2,axis=1))
            if any(test_dist < self.ref_dist_tol):
                xy_ref = pc.concat_lists_of_lists(xy_ref,xy_test[i])
                ref_idxs.append(i)
        #if identify_fiducials:
        if len(xy_ref) != self.n_fiducial_dots:
            print('warning: number of ref dots detected (' + str(len(xy_ref)) + ') is not equal to expected number of fiducial dots (' + str(self.n_fiducial_dots) + ')')
        self.fiducials_xy = xy_ref
        
        #else:
        if n_dots - len(ref_idxs) != 1:
            print('warning: more than one moving dots detected')
        else:
            ref_idxs.sort(reverse=True)
            for i in ref_idxs:
                xy_test.pop(i) # get rid of all but the moving pos
            self.expected_posXY = xy_test
            
    def _true_move(self, distance, allow_cruise = False):
        true_move = {'motor_step':0,'move_time':0,'speed_mode':0,'distance':0}
        true_dist = self._shaft_to_motor(distance)
        if not(allow_cruise) or abs(true_dist) < abs((2*self._spindown_distance) + self._min_distance_cruise):
            mode = 'creep'
            motor_steps = int(round(true_dist/self._stepsize_creep))
            true_dist = motor_steps * self._stepsize_creep
            speed = self._motor_speed_creep
            move_time = (abs(motor_steps)*self._stepsize_creep + 4*self._spindown_distance) / speed
        else:
            mode = 'cruise'
            motor_steps = int(round(true_dist/self._stepsize_cruise))
            true_dist = motor_steps * self._stepsize_cruise
            speed = self._motor_speed_cruise
            move_time = (abs(motor_steps)*self._stepsize_cruise + 4*self._spindown_distance) / speed
        true_dist = self._motor_to_shaft(true_dist)
        true_move['motor_step'] = motor_steps
        true_move['move_time'] = move_time + self.temporary_move_time_margin
        true_move['speed_mode'] = mode
        true_move['distance'] = true_dist
        return true_move
        
    def _shaft_to_motor(self, distance):
        return distance*self._ccw_direction*(self._gear_ratio*self._gear_calib)
        
    def _motor_to_shaft(self, distance):
        return distance*self._ccw_direction/(self._gear_ratio*self._gear_calib)
    
    def _wait_while_moving(self, can_id, mode):
        """Blocking implementation, to not send move tables while any positioners are still moving.

        Inputs:     canids ... integer CAN id numbers of all the positioners to check whether they are moving

        The implementation has the benefit of simplicity, but it is acknowledged there may be 'better',
        i.e. multi-threaded, ways to achieve this, to be implemented later.
        """
        #Normal wait function works intermittently, implemented manual wait with conservative time estimates.
        if mode == 'cruise':
            time.sleep(3)
        elif mode == 'creep':
            time.sleep(5)
        else:
            timeout = 30.0 # seconds
            poll_period = 0.5 # seconds
            keep_waiting = True
            start_time = time.time()
            #time.sleep(5)
    
            while keep_waiting:
    
                if (time.time()-start_time) >= timeout:
                    print('Timed out at ' + str(timeout) + ' seconds waiting to send next move table.')
                    keep_waiting = False
    
                if self.comm.ready_for_tables([can_id]):
                    print('ready for tables')
                    keep_waiting = False
                 
                else:
                    print('sleeping')
                    time.sleep(poll_period)
        