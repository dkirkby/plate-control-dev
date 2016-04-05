import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import postransforms
import poscollider
import numpy as np
import fitcircle

class PosMoveMeasure(object):
    """Coordinates moving fiber positioners with fiber view camera measurements.
    """
    def __init__(self, petals, fvc):
        if not isinstance(petals,list):
            petals = [petals]
        self.petals = petals # list of petal objects
        self.fvc = fvc # fvchandler object
        self.n_fiducial_dots = 1
        self.ref_dist_tol = 0.050 # [mm] used for identifying fiducial dots
        self.nudge_dist   = 5.0   # [deg] used for identifying fiducial dots
        self.fiducials_xy = []    # list of locations of the dots in the obsXY coordinate system
        self.n_points_theta_calib = 5 # number of points in a theta calibration arc
        self.n_points_phi_calib = 5 # number of points in a phi calibration arc
        self.phi_Eo_margin = 3.0 # [deg] margin on staying within Eo envelope

    def fiducials_on(self):
        """Turn on all fiducials on all petals."""
        for petal in self.petals:
            petal.fiducials_on()

    def fiducials_off(self):
        """Turn off all fiducials on all petals."""
        for petal in self.petals:
            petal.fiducials_off()

    def measure(self):
        """Measure positioner locations with the FVC and store the values.
        """
        expected_pos_xy = []
        expected_ref_xy = []
        petals = []
        pos_ids = []
        for petal in self.petals:
            these_pos_ids = petal.pos.posids
            pos_ids.extend(these_pos_ids)
            petals.extend([petal]*len(these_pos_ids))
            expected_pos_xy.extend(petal.pos.expected_current_position(these_pos_ids,'obsXY'))
        expected_ref_xy = self.fiducials_xy
        (measured_pos_xy, measured_ref_xy) = self.fvc.measure_and_identify(expected_pos_xy, expected_ref_xy)
        for i in range(len(measured_pos_xy)):
            petals[i].pos.set(pos_ids[i],'LAST_MEAS_OBS_X',measured_pos_xy[i][0])
            petals[i].pos.set(pos_ids[i],'LAST_MEAS_OBS_Y',measured_pos_xy[i][1])
        return pos_ids, measured_pos_xy

    def move(self, pos_ids, commands, values):
        """Move positioners.
        INPUTS:     pos_ids      ... list of positioner ids to move
                    commands     ... list of move command arguments, see comments in petal.py
                    targets      ... list of target coordinates of the form [[u1,v2],[u2,v2],...]
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        for petal in pos_ids_by_ptl.keys():
            indexes = [pos_ids.index(x) for x in pos_ids if x in pos_ids_by_ptl[petal]]
            these_pos_ids  = [pos_ids[i]  for i in indexes]
            these_commands = [commands[i] for i in indexes]
            these_values   = [values[i]    for i in indexes]
            petal.request_targets(these_pos_ids, these_commands, these_values)
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal

    def move_measure(self, pos_ids, commands, values):
        """Move positioners and measure output with FVC.
        See comments on inputs from move method.
        See comments on outputs from measure method.
        """
        self.move(pos_ids, commands, values)
        return self.measure()

    def move_and_correct(self, pos_ids, targets, coordinates='obsXY', num_corr_max=2):
        """Move positioners to target coordinates, then make a series of correction
        moves in coordination with the fiber view camera, to converge.

        INPUTS:     pos_ids      ... list of positioner ids to move
                    targets      ... list of target coordinates of the form [[u1,v2],[u2,v2],...]
                    coordinates  ... 'obsXY' or 'QS', identifying the coordinate system the targets are in
                    num_corr_max ... maximum number of correction moves to perform on any positioner
        """
        if coordinates == 'QS':
            targets = [self.trans.QS_to_obsXY(target) for target in targets]
        obsXY = []
        errXY = []
        (sorted_pos_ids, measured_pos_xy) = self.move_measure(pos_ids, ['obsXY']*len(pos_ids), targets)
        idx_sort = [sorted_pos_ids.index(p) for p in pos_ids]
        sorted_targets = [targets[idx] for idx in idx_sort]
        obsXY.append(measured_pos_xy)
        errXY.append(np.array(measured_pos_xy) - (np.array(sorted_targets)).tolist())
        for i in range(1,num_corr_max+1):
            dxdy = (-np.array(errXY[i-1])).tolist()
            for j in range(len(dxdy)):
                print(str(corr_move_pos_ids[j]) + ': correction move ' + str(j) + ' by (dx,dy)=(' + str(dxdy[j][0]) + ',' + str(dxdy[j][1]) + '), distance = ' + str((dxdy[j][0]**2 + dxdy[j][1]**2)**.5))
            (sorted_pos_ids, measured_pos_xy) = self.move_measure(sorted_pos_ids, ['dXdY']*len(sorted_pos_ids), dxdy)
            obsXY.append(measured_pos_xy)
            errXY.append(np.array(measured_pos_xy) - (np.array(sorted_targets)).tolist())
        return sorted_pos_ids, sorted_targets, obsXY, errXY


    def rehome(self,pos_ids='all'):
        """Find hardstops and reset current known positions.
        INPUTS:     pos_ids ... 'all' or a list of specific pos_ids
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        for petal in pos_ids_by_ptl.keys():
            petal.request_homing(pos_ids_by_ptl[petal])
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal

    def measure_range(self,pos_ids='all',axis='theta',set_calibration_values=True):
        # BOTH AXES? OR CAN THIS BE DONE INDEPENDENTLY -- AND NO SETTING OF CALIBRATION VALUES...

        """Expert usage. Sweep several points about axis ('theta' or 'phi') on
        positioners identified by pos_ids, striking the hard limits on either end.
        Calculate the total available travel range. Note that for axis='phi', the
        positioners must enter the collisionable zone, so the range seeking will
        occur in several successive stages.

        Calling measure range inherently gathers data sufficient to make at least
        a rough calibration of the positioner. If set_calibration_values is True,
        then those values will get stored.
        """
        T = self._measure_range_arc(pos_ids,'theta')
        P = self._measure_range_arc(pos_ids,'phi')
        if set_calibration_values:
            self._calculate_and_set_arms_and_offsets(T,P)




        'target_dtdp'     ... the delta moves which were attempted
        'measured_obsXY'  ... the resulting measured xy positions
        'xy_center'       ... the best fit arc's xy center
        'radius'          ... the best fit arc's radius
        'petal'           ... the petal this pos_id is on
        'trans'           ... the postransform object associated with this particular positioner

        # matlab code...
        # test_steps(i+1) = diff(range) - sum(test_steps);
        # xy_centered(:,1) = xy(:,1) - xy_ctr(1);
        # xy_centered(:,2) = xy(:,2) - xy_ctr(2);
        # test_steps_abs = [tp_initial(axis_idx),tp_initial(axis_idx)+cumsum(test_steps)]';
        # a_meas = PosMoveMeasure.unwrapped_meas_angle(test_steps_abs,xy_centered);
        # meas_range = a_meas(end) - a_meas(1);


    def calibrate(self,pos_ids='all'):
        """Sweep a circle of points about theta and phi to measure positioner center
        locations, R1 and R2 arm lengths, theta and phi offsets, and then set all these
        calibration values for each positioner.
        """
        T = self._measure_calibration_arc(pos_ids,'theta')
        P = self._measure_calibration_arc(pos_ids,'phi')
        self._calculate_and_set_arms_and_offsets(T,P)
        for pos_id in T.keys():
            # gear ratio calibration calculations
            trans = T[pos_id]['trans']
            measured_obsXY = T[posid]['measured_obsXY'] + P[posid]['measured_obsXY']
            target_posTP = T[posid]['target_posTP'] + P[posid]['target_posTP']
            measured_posTP = trans.obsXY_to_posTP(np.transpose(measured_obsXY)).transpose()
            scale_TP = np.divide(measured_posTP,target_posTP)
            scale_T = np.median(scale_TP[:,pc.T])
            scale_P = np.median(scale_TP[:,pc.P])
            petal.pos.set(pos_id,'GEAR_CALIB_T',scale_T)
            petal.pos.set(pos_id,'GEAR_CALIB_P',scale_P)

    def identify_fiducials(self):
        """Nudge positioners forward/back to determine which centroid dots are fiducials.
        """
        print('Nudging positioners to identify reference fiber(s).\n')
        print('Distance tol for identifying a fixed fiber is set to %g.\n',self.ref_dist_tol)
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        nudges = [self.nudge_dist, -self.nudge_dist]
        xy_ref = []
        for i in range(len(nudges)):
            n_pos = 0
            for petal in pos_ids_by_ptl.keys():
                pos_ids = pos_ids_by_ptl[petal]
                n_pos += len(pos_ids)
                petal.request_direct_dtdp(pos_ids, [nudges[i],0], cmd_prefix='nudge to identify fiducials')
                petal.schedule_send_and_execute_moves()
            n_dots = n_pos + self.n_fiducial_dots
            if i == 0:
                xy_init = self.fvc.measure(n_dots)
            else:
                xy_test = self.fvc.measure(n_dots)
        for i in range(len(xy_test)):
            test_delta = np.array(xy_test[i]) - np.array(xy_init)
            test_dist = np.sqrt(np.sum(test_delta**2,axis=1))
            if any(test_dist < self.ref_dist_tol):
                xy_ref.append(xy_test[i])
        if len(xy_ref) != self.n_fiducial_dots:
            print('warning: number of ref dots detected (' + str(len(xy_ref)) + ') is not equal to expected number of fiducial dots (' + str(self.n_fiducial_dots) + ')')
        self.fiducials_xy = xy_ref

    def pos_data_listed_by_ptl(self, pos_ids='all', key=''):
        """Returns a dictionary with keys = petal objects and values = lists of data
        (the particular data to retrieve is identified by key) on each petal.  If
        pos_ids argument == 'all', then each list contains all the data on that petal.
        If pos_ids argument is a list of pos_ids, then in the returned dictionary, each list
        contains only the data for those positioners which are in the intersection set of
        pos_ids with that petal's positioner ids.
        """
        data_by_ptl = {}
        for petal in self.petals:
            all_pos_on_ptl = petal.pos.get(key='POS_ID')
            if pos_ids == 'all':
                these_pos_ids = all_pos_on_ptl
            elif isinstance(pos_ids,list):
                these_pos_ids = [p for p in pos_ids if p in all_pos_on_ptl]
            else:
                print('invalid argument ' + str(pos_ids) + ' for pos_ids')
                these_pos_ids = []
            data_by_ptl[petal] = petal.pos.get(these_pos_ids,key)
        return data_by_ptl

    def _measure_calibration_arc(self,pos_ids='all',axis='theta'):
        """Expert usage. Sweep an arc of points about axis ('theta' or 'phi')
        on positioners identified by pos_ids. Measure these points with the FVC
        and do a best fit of them.

        INPUTS:   pos_ids ... list of pos_ids or 'all'
                  axis    ... 'theta' or 'phi'

        Returns a dictionary of dictionaries containing the data. The primary
        keys for the dict are the pos_id. Then for each pos_id, each subdictionary
        contains the keys:
            'target_posTP'    ... the posTP targets which were attempted
            'measured_obsXY'  ... the resulting measured xy positions
            'xy_center'       ... the best fit arc's xy center
            'radius'          ... the best fit arc's radius
            'petal'           ... the petal this pos_id is on
            'trans'           ... the postransform object associated with this particular positioner
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        phi_clear_angle = self.phi_clear_angle
        data = {}
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            posmodels = petal.pos.get(these_pos_ids)
            initial_tp = []
            final_tp = []
            if axis == 'theta':
                n_pts = self.n_points_theta_calib
                for posmodel in posmodels:
                    targetable_range = posmodel.targetable_range_T
                    initial_tp.append([min(targetable_range), phi_clear_angle])
                    final_tp.append([max(targetable_range), initial_tp[-1][1]])
            else:
                n_pts = self.n_points_phi_calib
                for posmodel in posmodels:
                    initial_tp.append([np.mean(posmodel.targetable_range_T), phi_clear_angle])
                    final_tp.append([initial_tp[-1][0], max(posmodel.targetable_range_P)])
            for i in range(len(these_pos_ids)):
                t = linspace(initial_tp[i][0], final_tp[i][0], n_pts)
                p = linspace(initial_tp[i][1], final_tp[i][1], n_pts)
                data[these_pos_ids[i]] = {'target_posTP':[[t[j],p[j]] for j in range(n_pts)], 'measured_obsXY':[], 'petal':petal, 'trans':posmodels[i].trans}
        all_pos_ids = data.keys()

        # make the measurements
        for i in range(n_pts):
            targets = [data[pos_id]['target_posTP'][i] for pos_id in all_pos_ids]
            (sorted_pos_ids, measured_obsXY) = self.move_measure(all_pos_ids,['posTP']*len(all_pos_ids),targets)
            for j in range(len(measured_obsXY)):
                data[sorted_pos_ids[j]]['measured_obsXY'] += measured_obsXY

        # circle fits
        for pos_id in all_pos_ids:
            (xy_ctr,radius) = fitcircle.fit(data[pos_id]['measured_obsXY'])
            data[pos_id]['xy_center'] = xy_ctr
            data[pos_id]['radius'] = radius
        return data

    def _measure_range_arc(self,pos_ids='all',axis='theta'):
        """Expert usage. Measure physical range of an axis by sweep a brief arc of points
        on positioners identified by pos_ids. Measure these points with the FVC
        and do a best fit of them.

        INPUTS:   pos_ids ... list of pos_ids or 'all'
                  axis    ... 'theta' or 'phi'

        Returns a dictionary of dictionaries containing the data. The primary
        keys for the dict are the pos_id. Then for each pos_id, each subdictionary
        contains the keys:
            'target_dtdp'     ... the delta moves which were attempted
            'measured_obsXY'  ... the resulting measured xy positions
            'xy_center'       ... the best fit arc's xy center
            'radius'          ... the best fit arc's radius
            'petal'           ... the petal this pos_id is on
            'trans'           ... the postransform object associated with this particular positioner
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        phi_clear_angle = self.phi_clear_angle
        n_intermediate_pts = 2
        data = {}
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            if axis == 'theta':
                delta = 360/(n_intermediate_pts + 1)
                initial_tp = [-180, phi_clear_angle]
                dtdp = [delta,0]
                axisid = pc.T
            else:
                delta = -180/(n_intermediate_pts + 1)
                initial_tp = [0, 0]
                dtdp = [0,delta]
                axisid = pc.P
            for i in range(len(these_pos_ids)):
                data[these_pos_ids[i]] = {'target_dtdp':dtdp, 'measured_obsXY':[], 'petal':petal, 'trans':posmodels[i].trans}
        all_pos_ids = data.keys()

        # go to initial point
        self.move(all_pos_ids, ['posTP']*len(all_pos_ids), [initial_tp]*len(all_pos_ids))

        # seek first limit
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            petal.pos.request_limit_seek(these_pos_ids, axisid, -np.sign(delta), cmd_prefix='seeking first ' + axis + ' limit')
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal
        (sorted_pos_ids, measured_obsXY) = self.measure()
        for j in range(len(measured_obsXY)):
            data[sorted_pos_ids[j]]['measured_obsXY'] += measured_obsXY

        # intermediate points
        for i in range(n_intermediate_pts):
            (sorted_pos_ids, measured_obsXY) = self.move_measure(all_pos_ids,['dTdP']*len(all_pos_ids),[dtdp]*len(all_pos_ids))
            for j in range(len(measured_obsXY)):
                data[sorted_pos_ids[j]]['measured_obsXY'] += measured_obsXY

        # seek second limit
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            petal.pos.request_limit_seek(these_pos_ids, axisid, np.sign(delta), cmd_prefix='seeking second ' + axis + ' limit')
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal
        (sorted_pos_ids, measured_obsXY) = self.measure()
        for j in range(len(measured_obsXY)):
            data[sorted_pos_ids[j]]['measured_obsXY'] += measured_obsXY

        # circle fits
        for pos_id in all_pos_ids:
            (xy_ctr,radius) = fitcircle.fit(data[pos_id]['measured_obsXY'])
            data[pos_id]['xy_center'] = xy_ctr
            data[pos_id]['radius'] = radius
        return data

    def _calculate_and_set_arms_and_offsets(self, T, P):
        """Common helper function for the measure range and calibrate functions.
        T and P are data dictionaries taken on the theta and phi axes. See those
        methods for more information.
        """
        for pos_id in T.keys():
            petal = T[pos_id]['petal']
            t_ctr = np.array(T[pos_id]['xy_center'])
            p_ctr = np.array(P[pos_id]['xy_center'])
            length_r1 = np.sqrt(np.sum((t_ctr - p_ctr)**2))
            petal.pos.set(pos_id,'LENGTH_R1',length_r1)
            petal.pos.set(pos_id,'LENGTH_R2',P[pos_id]['radius'])
            petal.pos.set(pos_id,'OFFSET_X',t_ctr[0])
            petal.pos.set(pos_id,'OFFSET_Y',t_ctr[1])
            obsT = np.arctan2(p_ctr[1]-t_ctr[1], p_ctr[0]-t_ctr[0]) * 180/np.pi
            posT = np.median(P[pos_id]['target_posTP'][pc.T])
            offset_t = obsT - posT
            petal.pos.set(pos_id,'OFFSET_T',offset_t)
            p_xymeas = P[pos_id]['measured_xy']
            p_angles = np.arctan2(p_xymeas[1]-p_ctr[1], p_xymeas[0]-p_ctr[0]) * 180/np.pi
            obsP = p_angles - obsT
            posP = P[pos_id]['target_posTP'][pc.P]
            offset_p = np.median(obsP - posP)
            petal.pos.set(pos_id,'OFFSET_T',offset_p)

    @property
    def phi_clear_angle(self):
        """Returns the phi angle in degrees for which two positioners cannot collide
        if they both have phi at this angle or greater.
        """
        phi_Eo_angle = poscollider.PosCollider().config['PHI_EO']
        phi_clear = phi_Eo_angle + self.phi_Eo_margin
        return phi_clear