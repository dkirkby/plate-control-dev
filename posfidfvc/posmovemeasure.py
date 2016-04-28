import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import postransforms
import poscollider
import numpy as np
import fitcircle
import posconstants as pc

class PosMoveMeasure(object):
    """Coordinates moving fiber positioners with fiber view camera measurements.
    """
    def __init__(self, petals, fvc):
        if not isinstance(petals,list):
            petals = [petals]
        self.petals = petals # list of petal objects
        self.fvc = fvc # fvchandler object
        self.n_fiducial_dots = 1
        self.ref_dist_tol = 0.1   # [mm] used for identifying fiducial dots
        self.nudge_dist   = 10.0  # [deg] used for identifying fiducial dots
        self.fiducials_xy = []    # list of locations of the dots in the obsXY coordinate system
        self.n_points_full_calib_T = 7 # number of points in a theta calibration arc
        self.n_points_full_calib_P = 7 # number of points in a phi calibration arc
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
        """Measure positioner locations with the FVC and return the values.

        Return data is a dictionary with:   keys ... pos_id
                                          values ... [measured_obs_x, measured_obs_y]

        (In a future revision, if useful we may consider having fiducial ids (and dot sub-ids)
        returned also as keys, with corresponding measured values. As of April 2016, only
        positioner measurements are currently returned by this method.)
        """
        data = {}
        expected_pos_xy = []
        expected_ref_xy = []
        petals = []
        pos_ids = []
        for petal in self.petals:
            these_pos_ids = petal.posids
            pos_ids.extend(these_pos_ids)
            petals.extend([petal]*len(these_pos_ids))
            expected_pos_xy = pc.concat_lists_of_lists(expected_pos_xy, petal.expected_current_position(these_pos_ids,'obsXY'))
        expected_ref_xy = self.fiducials_xy
        (measured_pos_xy, measured_ref_xy) = self.fvc.measure_and_identify(expected_pos_xy, expected_ref_xy)
        for i in range(len(measured_pos_xy)):
            petals[i].set(pos_ids[i],'LAST_MEAS_OBS_X',measured_pos_xy[i][0])
            petals[i].set(pos_ids[i],'LAST_MEAS_OBS_Y',measured_pos_xy[i][1])
        for i in range(len(pos_ids)):
            data[pos_ids[i]] = measured_pos_xy[i]
        return data

    def move(self, pos_ids, commands, values):
        """Move positioners.
        INPUTS:     pos_ids      ... list of positioner ids to move
                    commands     ... single command or list of move command arguments, see comments in petal.py
                    targets      ... single coordinate pair or list of target coordinates of the form [[u1,v2],[u2,v2],...]
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        n_total_pos = sum([len(pos_ids_by_ptl[petal]) for petal in pos_ids_by_ptl.keys()])
        if not(isinstance(commands,list)):
            commands = [commands]*n_total_pos
        elif not(len(commands) == n_total_pos):
            commands = [commands[0]]*n_total_pos # just use the first one in the list in this case
        if len(values) == 2 and not(isinstance(values[0],list)):
            values = [values]*n_total_pos
        elif not(len(values) == n_total_pos):
            values = [values[0]]*n_total_pos  # just use the first one in the list in this case
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

        OUTPUT:     data ... dictionary of dictionaries

                    return dictionary format:
                        key:   pos_id (referencing a single subdictionary for that positioner)
                        value: subdictionary (see below)

                    subdictionary format:
                        KEYS    VALUES
                        ----    ------
                        targ_obsXY  [x,y]                       ... target coordinates in obsXY system
                        meas_obsXY  [[x0,y0],[x1,y1],...]       ... measured xy coordinates for each submove
                        errXY       [[ex0,ey0],[ex1,ey1],...]   ... error in x and y for each submove
                        err2D       [e0,e1,...]                 ... error distance (errx^2 + erry^2)^0.5 for each submove
        """
        data = {}
        def fmt(number):
            return format(number,'.3f') # for consistently printing floats in terminal output
        if coordinates == 'obsXY':
            targ_obsXY = targets
        elif coordinates == 'QS':
            trans = postransforms.PosTransforms()
            targ_obsXY = [trans.QS_to_obsXY(target) for target in targets]
        else:
            print('coordinates \'' + coordinates + '\' not recognized')
            return None
        for i in range(len(targ_obsXY)):
            print(str(pos_ids[i]) + ': blind move to (obsX,obsY)=(' + fmt(targ_obsXY[i][0]) + ',' + fmt(targ_obsXY[i][1]) + ')')
        this_meas_data = self.move_measure(pos_ids, 'obsXY', targ_obsXY)
        for p in this_meas_data.keys():
            data[p] = {}
            data[p]['targ_obsXY'] = targ_obsXY[pos_ids.index(p)]
            data[p]['meas_obsXY'] = [this_meas_data[p]]
            data[p]['errXY'] = [[data[p]['meas_obsXY'][0] - data[p]['targ_obsXY'][0],
                                 data[p]['meas_obsXY'][1] - data[p]['targ_obsXY'][1]]]
            data[p]['err2D'] = [(data[p]['errXY'][0]**2 + data[p]['errXY'][1]**2)**0.5]
        for i in range(1,num_corr_max+1):
            dxdy = {}
            for p in pos_ids:
                dxdy[p] = [-data[p]['errXY'][0],-data[p]['errXY'][1]]
                print(str(p) + ': correction move ' + str(i) + ' of ' + str(num_corr_max) + ' by (dx,dy)=(' + fmt(dxdy[p][0]) + ',' + fmt(dxdy[p][1]) + '), distance=' + fmt(data[p]['err2D'][-1]))
            this_meas_data = self.move_measure(pos_ids, 'dXdY', dxdy)
            for p in this_meas_data.keys():
                data[p]['meas_obsXY'].append(this_meas_data[p])
                data[p]['errXY'].append([data[p]['meas_obsXY'][0] - data[p]['targ_obsXY'][0],
                                         data[p]['meas_obsXY'][1] - data[p]['targ_obsXY'][1]])
                data[p]['err2D'].append((data[p]['errXY'][0]**2 + data[p]['errXY'][1]**2)**0.5)
        return data

    def retract_phi(self,pos_ids='all'):
        """Get all phi arms within their clear rotation envelopes for positioners
        identified by pos_ids.
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids, key='POS_ID')
        pos_ids = []
        targets = []
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            pos_ids.extend(these_pos_ids)
            posT = petal.expected_current_position(these_pos_ids,'posT')
            posP = self.phi_clear_angle # uniform value in all cases
            targets = pc.concat_lists_of_lists(targets, [[t,posP] for t in posT])
        self.move(pos_ids,'posTP',targets)

    def rehome(self,pos_ids='all'):
        """Find hardstops and reset current known positions.
        INPUTS:     pos_ids ... 'all' or a list of specific pos_ids
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        print('rehoming')
        for petal in pos_ids_by_ptl.keys():
            petal.request_homing(pos_ids_by_ptl[petal])
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal

    def measure_range(self,pos_ids='all',axis='theta'):
        """Expert usage. Sweep several points about axis ('theta' or 'phi') on
        positioners identified by pos_ids, striking the hard limits on either end.
        Calculate the total available travel range. Note that for axis='phi', the
        positioners must enter the collisionable zone, so the range seeking may
        occur in several successive stages.

        Typically one does NOT call measure_range unless the theta offsets are already
        reasonably well known. That can be achieved by first doing a 'quick' mode
        calibration.
        """
        if axis == 'phi':
            axisid = pc.P
            parameter_name = 'PHYSICAL_RANGE_P'
            batches = pos_ids # implement later some selection of smaller batches of positioners guaranteed not to collide
        else:
            axisid = pc.T
            parameter_name = 'PHYSICAL_RANGE_T'
            batches = pos_ids
        data = {}
        batches = pc.listify(batches, keep_flat=True)[0]
        for batch in batches:
            batch_data = self._measure_range_arc(batch,axis)
            data.update(batch_data)

        # unwrapping code here
        for pos_id in data.keys():
            delta = data[pos_id]['target_dtdp'][axisid]
            obsXY = data[pos_id]['measured_obsXY']
            center = data[pos_id]['xy_center']
            xy_ctrd = np.array(obsXY) - np.array(center)
            angles_measured = np.arctan2(xy_ctrd[:,1], xy_ctrd[:,0]) * 180/np.pi
            total_angle = 0
            direction = np.sign(delta)
            for i in range(len(angles_measured) - 1):
                step_measured = angles_measured[i+1] - angles_measured[i]
                if np.sign(step_measured) != direction:
                    step_measured += direction * 360
                total_angle += step_measured
            total_angle = abs(total_angle)
            data[pos_id]['petal'].set(pos_id,parameter_name,total_angle)

    def calibrate(self,pos_ids='all',mode='quick'):
        """Sweep a circle of points about theta and phi to measure positioner center
        locations, R1 and R2 arm lengths, theta and phi offsets, and then set all these
        calibration values for each positioner.

        INPUTS:  pos_ids  ... list of pos_ids or 'all'
                 mode     ... 'full' or 'quick', see detailed comments in _measure_calibration_arc method

        Typically one does NOT call 'full' mode unless the theta offsets are already
        reasonably well known. That can be achieved by first doing a 'quick' mode
        calibration.
        """
        T = self._measure_calibration_arc(pos_ids,'theta',mode)
        P = self._measure_calibration_arc(pos_ids,'phi',mode)
        self._calculate_and_set_arms_and_offsets(T,P)
        ptls_of_pos_ids = self.ptls_of_pos_ids(pos_ids)
        if mode == 'full':
            for pos_id in T.keys():
                # gear ratio calibration calculations
                trans = T[pos_id]['trans']
                measured_obsXY = pc.concat_lists_of_lists(T[pos_id]['measured_obsXY'], P[pos_id]['measured_obsXY'])
                target_posTP   = pc.concat_lists_of_lists(T[pos_id]['target_posTP'],   P[pos_id]['target_posTP'])
                measured_obsXY = np.transpose(measured_obsXY).tolist()
                measured_posTP = np.transpose(trans.obsXY_to_posTP(measured_obsXY)[0])
                scale_TP = np.divide(measured_posTP,target_posTP)
                scale_T = np.median(scale_TP[:,pc.T])
                scale_P = np.median(scale_TP[:,pc.P])
                petal = ptls_of_pos_ids[pos_id]
                petal.set(pos_id,'GEAR_CALIB_T',scale_T)
                petal.set(pos_id,'GEAR_CALIB_P',scale_P)

    def identify_fiducials(self):
        """Nudge positioners forward/back to determine which centroid dots are fiducials.
        """
        print('Nudging positioners to identify reference dots. Distance tol for identifying a ref dot is ' + str(self.ref_dist_tol))
        pos_ids_by_ptl = self.pos_data_listed_by_ptl('all','POS_ID')
        nudges = [self.nudge_dist, -self.nudge_dist]
        xy_ref = []
        for i in range(len(nudges)):
            n_pos = 0
            for petal in pos_ids_by_ptl.keys():
                pos_ids = pos_ids_by_ptl[petal]
                n_pos += len(pos_ids)
                petal.request_direct_dtdp(pos_ids, [0,nudges[i]], cmd_prefix='nudge to identify fiducials ')
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
                xy_ref = pc.concat_lists_of_lists(xy_ref,xy_test[i])
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
            all_pos_on_ptl = petal.get(key='POS_ID')
            if pos_ids == 'all':
                these_pos_ids = all_pos_on_ptl
            elif isinstance(pos_ids,list):
                these_pos_ids = [p for p in pos_ids if p in all_pos_on_ptl]
            else:
                print('invalid argument ' + str(pos_ids) + ' for pos_ids')
                these_pos_ids = []
            this_data = petal.get(these_pos_ids,key)
            this_data = pc.listify(this_data, keep_flat=True)[0]
            data_by_ptl[petal] = this_data
        return data_by_ptl

    def ptls_of_pos_ids(self, pos_ids='all'):
        """Returns a dictionary with keys = pos_ids and values = corresponding petal
        on which each pos_id lives.
        """
        ptls_of_pos_ids = {}
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        for ptl in pos_ids_by_ptl.keys():
            for pos_id in pos_ids_by_ptl[ptl]:
                ptls_of_pos_ids[pos_id] = ptl
        return ptls_of_pos_ids


    def _measure_calibration_arc(self,pos_ids='all',axis='theta',mode='quick'):
        """Expert usage. Sweep an arc of points about axis ('theta' or 'phi')
        on positioners identified by pos_ids. Measure these points with the FVC
        and do a best fit of them.401

        INPUTS:   pos_ids ... list of pos_ids or 'all'
                  axis    ... 'theta' or 'phi'

        'quick' mode: phi never exceeds Eo envelope, 3 points measured on phi axis, 4 points on theta,
        'full' mode: phi covers full range, n points per parameter 'n_points_full_calib_T' or 'n_points_full_calib_P'

        Full mode assumes all the positioners can be placed such that their phi will not interfere. This means
        that the thetas can be made homogenous, which means having reasonably theta offsets already known. Therefore
        quick mode ought to have been run at least once before full mode, if there is doubt as to approximate theta offsets.

        OUTPUTS:  data ... see comments below

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
            posmodels = petal.get(these_pos_ids)
            initial_tp = []
            final_tp = []
            if axis == 'theta':
                n_pts = 4 if mode == 'quick' else self.n_points_full_calib_T
                for posmodel in posmodels:
                    targetable_range_T = posmodel.targetable_range_T
                    initial_tp = pc.concat_lists_of_lists(initial_tp, [min(targetable_range_T), phi_clear_angle])
                    final_tp   = pc.concat_lists_of_lists(final_tp,   [max(targetable_range_T), initial_tp[-1][1]])
            else:
                n_pts = 3 if mode == 'quick' else self.n_points_full_calib_P
                for posmodel in posmodels:
                    if mode == 'quick':
                        phi_min = phi_clear_angle
                        theta = 0
                    else:
                        phi_min = min(posmodel.targetable_range_P)
                        theta = posmodel.trans.obsTP_to_posTP([0,0])[pc.T] # when doing phi axis, want obsT to all be uniform (simplifies anti-collision), which means have to figure out appropriate posT for each positioner -- depends on already knowing theta offset reasonably well
                    initial_tp = pc.concat_lists_of_lists(initial_tp, [theta, phi_min])
                    final_tp   = pc.concat_lists_of_lists(final_tp,   [initial_tp[-1][0], max(posmodel.targetable_range_P)])
            for i in range(len(these_pos_ids)):
                t = np.linspace(initial_tp[i][0], final_tp[i][0], n_pts)
                p = np.linspace(initial_tp[i][1], final_tp[i][1], n_pts)
                data[these_pos_ids[i]] = {'target_posTP':[[t[j],p[j]] for j in range(n_pts)], 'measured_obsXY':[], 'petal':petal, 'trans':posmodels[i].trans}
        all_pos_ids = list(data.keys())

        # make the measurements
        for i in range(n_pts):
            targets = [data[pos_id]['target_posTP'][i] for pos_id in all_pos_ids]
            print('\'' + mode + '\' calibration arc on ' + axis + ' axis: point ' + str(i+1) + ' of ' + str(n_pts))
            (sorted_pos_ids, measured_obsXY) = self.move_measure(all_pos_ids,'posTP',targets)
            for j in range(len(measured_obsXY)):
                temp = data[sorted_pos_ids[j]]['measured_obsXY']
                data[sorted_pos_ids[j]]['measured_obsXY'] = pc.concat_lists_of_lists(temp, measured_obsXY)

        # circle fits
        for pos_id in all_pos_ids:
            (xy_ctr,radius) = fitcircle.FitCircle().fit(data[pos_id]['measured_obsXY'])
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
            'initial_posTP'   ... starting theta,phi position
            'target_dtdp'     ... delta moves which were attempted
            'measured_obsXY'  ... resulting measured xy positions
            'xy_center'       ... best fit arc's xy center
            'radius'          ... best fit arc's radius
            'petal'           ... petal this pos_id is on
            'trans'           ... postransform object associated with this particular positioner
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        phi_clear_angle = self.phi_clear_angle
        n_intermediate_pts = 2
        data = {}
        initial_tp = []
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            if axis == 'theta':
                delta = 360/(n_intermediate_pts + 1)
                initial_tp = [-150, phi_clear_angle]
                dtdp = [delta,0]
                axisid = pc.T
            else:
                delta = -180/(n_intermediate_pts + 1)
                posmodels = petal.get(these_pos_ids)
                for posmodel in posmodels:
                    this_initial_tp = posmodel.trans.obsTP_to_posTP([0,phi_clear_angle]) # when doing phi axis, want obsT to all be uniform (simplifies anti-collision), which means have to figure out appropriate posT for each positioner -- depends on already knowing theta offset reasonably well
                    initial_tp = pc.concat_lists_of_lists(initial_tp, this_initial_tp)
                dtdp = [0,delta]
                axisid = pc.P
            for i in range(len(these_pos_ids)):
                data[these_pos_ids[i]] = {'target_dtdp':dtdp, 'measured_obsXY':[], 'petal':petal}
        all_pos_ids = list(data.keys())

        prefix = 'range measurement on ' + axis + ' axis'
        # go to initial point
        print(prefix + ': initial point')
        self.move(all_pos_ids, 'posTP', initial_tp)

        # seek first limit
        print(prefix + ': seeking first limit')
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            petal.request_limit_seek(these_pos_ids, axisid, -np.sign(delta), cmd_prefix='seeking first ' + axis + ' limit ')
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal
        meas_data = self.measure()
        for p in meas_data.keys():
            data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],meas_data[p])

        # intermediate points
        for i in range(n_intermediate_pts):
            print(prefix + ': intermediate point ' + str(i+1) + ' of ' + n_intermediate_pts)
            # Note that anticollision is NOT done here. The reason is that phi location is not perfectly
            # well-known at this point (having just struck a hard limit). So externally need to have made
            # sure there was a clear path for the phi arm ahead of time.
            petal.request_direct_dtdp(all_pos_ids, dtdp, cmd_prefix='intermediate ' + axis + ' point ')
            petal.schedule_send_and_execute_moves()
            meas_data = self.measure()
            for p in meas_data.keys():
                data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],meas_data[p])

        # seek second limit
        print(prefix + ': seeking second limit')
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            petal.request_limit_seek(these_pos_ids, axisid, np.sign(delta), cmd_prefix='seeking second ' + axis + ' limit ')
            petal.schedule_send_and_execute_moves()
        meas_data = self.measure()
        for p in meas_data.keys():
            data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],meas_data[p])

        # circle fits
        for pos_id in all_pos_ids:
            (xy_ctr,radius) = fitcircle.FitCircle().fit(data[pos_id]['measured_obsXY'])
            data[pos_id]['xy_center'] = xy_ctr

        # get phi axis well back in clear envelope, as a best practice housekeeping thing to do
        if axis == 'phi' and np.sign(delta) == -1:
            for petal in pos_ids_by_ptl.keys():
                these_pos_ids = pos_ids_by_ptl[petal]
                petal.request_limit_seek(these_pos_ids, axisid, -np.sign(delta), cmd_prefix='housekeeping extra ' + axis + ' limit seek ')
                petal.schedule_send_and_execute_moves()

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
            petal.set(pos_id,'LENGTH_R1',length_r1)
            petal.set(pos_id,'LENGTH_R2',P[pos_id]['radius'])
            petal.set(pos_id,'OFFSET_X',t_ctr[0])
            petal.set(pos_id,'OFFSET_Y',t_ctr[1])
            obsT = np.arctan2(p_ctr[1]-t_ctr[1], p_ctr[0]-t_ctr[0]) * 180/np.pi
            posT = P[pos_id]['target_posTP'][0][pc.T] # just using the first target theta angle in the phi sweep
            offset_t = obsT - posT
            petal.set(pos_id,'OFFSET_T',offset_t)
            p_xymeas = np.array(P[pos_id]['measured_obsXY'])
            p_angles = np.arctan2(p_xymeas[:,1]-p_ctr[1], p_xymeas[:,0]-p_ctr[0]) * 180/np.pi
            p_angles_wrapped = [p if p >=0 else p + 360 for p in p_angles]
            obsP = p_angles_wrapped - obsT
            posP = [posTP[pc.P] for posTP in P[pos_id]['target_posTP']]
            offset_p = np.median(obsP - posP)
            petal.set(pos_id,'OFFSET_P',offset_p)

    @property
    def phi_clear_angle(self):
        """Returns the phi angle in degrees for which two positioners cannot collide
        if they both have phi at this angle or greater.
        """
        phi_Eo_angle = poscollider.PosCollider().config['PHI_EO']
        phi_clear = phi_Eo_angle + self.phi_Eo_margin
        return phi_clear