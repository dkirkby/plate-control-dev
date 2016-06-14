import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import postransforms
import poscollider
import numpy as np
import fitcircle
import posconstants as pc
import poscalibplot
import scipy.optimize

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
        self.calib_arc_margin = 3.0 # [deg] margin on calibration arc range
        self.general_trans = postransforms.PosTransforms() # general transformation object (not specific to calibration of any one positioner), useful for things like obsXY to QS or QS to obsXY coordinate transforms
        self.grid_calib_param_keys = ['LENGTH_R1','LENGTH_R2','OFFSET_T','OFFSET_P','OFFSET_X','OFFSET_Y']
        self.grid_calib_keep_phi_within_Eo = False # during grid calibration method, whether to keep phi axis always within the non-collidable envelope

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

    def move(self, requests):
        """Move positioners.
        See request_targets method in petal.py for description of format of the 'requests' dictionary.
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(list(requests.keys()),'POS_ID')
        for petal in pos_ids_by_ptl.keys():
            these_requests = {}
            for pos_id in pos_ids_by_ptl[petal]:
                these_requests[pos_id] = requests[pos_id]
            petal.request_targets(these_requests)            
            petal.schedule_send_and_execute_moves() # in future, may do this in a different thread for each petal

    def move_measure(self, requests):
        """Move positioners and measure output with FVC.
        See comments on inputs from move method.
        See comments on outputs from measure method.
        """
        self.move(requests)
        return self.measure()

    def move_and_correct(self, requests, num_corr_max=2):
        """Move positioners to requested target coordinates, then make a series of correction
        moves in coordination with the fiber view camera, to converge.

        INPUTS:     
            requests      ... dictionary of dictionaries
                                ... formatted the same as any other move request
                                ... see request_targets method in petal.py for description of format
                                ... however, only 'obsXY' or 'QS' commands are allowed here
            num_corr_max  ... maximum number of correction moves to perform on any positioner

        OUTPUT:
            The measured data gets stored into into a new dictionary, which is a shallow copy of
            'requests', but with new fields added to each positioner's subdictionary:

                KEYS        VALUES
                ----        ------
                targ_obsXY  [x,y]                       ... target coordinates in obsXY system
                meas_obsXY  [[x0,y0],[x1,y1],...]       ... measured xy coordinates for each submove
                errXY       [[ex0,ey0],[ex1,ey1],...]   ... error in x and y for each submove
                err2D       [e0,e1,...]                 ... error distance (errx^2 + erry^2)^0.5 for each submove
                posTP       [[t0,p0],[t1,p1],...]       ... internally-tracked expected angular positions of the (theta,phi) shafts at the outputs of their gearboxes
        """
        data = requests.copy()
        ptls_of_pos_ids = self.ptls_of_pos_ids([p for p in data.keys()])
        def fmt(number):
            return format(number,'.3f') # for consistently printing floats in terminal output
        for pos_id in data.keys():
            m = data[pos_id] # for terseness below
            if m['command'] == 'obsXY':
                m['targ_obsXY'] = m['target']
            elif m['command'] == 'QS':
                m['targ_obsXY'] = self.general_trans.QS_to_obsXY(m['target'])
            else:
                print('coordinates \'' + m['command'] + '\' not valid or not allowed')
                return
            m['log_note'] = 'blind move'
            print(str(pos_id) + ': blind move to (obsX,obsY)=(' + fmt(m['targ_obsXY'][0]) + ',' + fmt(m['targ_obsXY'][1]) + ')')
        this_meas = self.move_measure(data)
        for pos_id in this_meas.keys():
            m = data[pos_id] # again, for terseness
            m['meas_obsXY'] = [this_meas[pos_id]]
            m['errXY'] = [[m['meas_obsXY'][-1][0] - m['targ_obsXY'][0],
                           m['meas_obsXY'][-1][1] - m['targ_obsXY'][1]]]
            m['err2D'] = [(m['errXY'][-1][0]**2 + m['errXY'][-1][1]**2)**0.5]
            m['posTP'] = ptls_of_pos_ids[pos_id].expected_current_position(pos_id,'posTP')
        for i in range(1,num_corr_max+1):
            correction = {}
            for pos_id in data.keys():
                correction[pos_id] = {}
                dxdy = [-data[pos_id]['errXY'][-1][0],-data[pos_id]['errXY'][-1][1]]
                correction[pos_id]['command'] = 'dXdY'
                correction[pos_id]['target'] = dxdy
                correction[pos_id]['log_note'] = 'correction move ' + str(i)
                print(str(pos_id) + ': correction move ' + str(i) + ' of ' + str(num_corr_max) + ' by (dx,dy)=(' + fmt(dxdy[0]) + ',' + fmt(dxdy[1]) + '), \u221A(dx\u00B2+dy\u00B2)=' + fmt(data[pos_id]['err2D'][-1]))
            this_meas = self.move_measure(correction)
            for pos_id in this_meas.keys():
                m = data[pos_id] # again, for terseness
                m['meas_obsXY'].append(this_meas[pos_id])
                m['errXY'].append([m['meas_obsXY'][-1][0] - m['targ_obsXY'][0],
                                   m['meas_obsXY'][-1][1] - m['targ_obsXY'][1]])
                m['err2D'].append((m['errXY'][-1][0]**2 + m['errXY'][-1][1]**2)**0.5)
                m['posTP'].append(ptls_of_pos_ids[pos_id].expected_current_position(pos_id,'posTP'))
        for pos_id in data.keys():
            print(str(pos_id) + ': final error distance=' + fmt(data[pos_id]['err2D'][-1]))
        return data

    def retract_phi(self,pos_ids='all'):
        """Get all phi arms within their clear rotation envelopes for positioners
        identified by pos_ids.
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids, key='POS_ID')
        requests = {}
        posP = self.phi_clear_angle # uniform value in all cases
        for petal in pos_ids_by_ptl.keys():
            for pos_id in pos_ids_by_ptl[petal]:
                posT = petal.expected_current_position(pos_id,'posT')
                requests[pos_id] = {'command':'posTP', 'target':[posT,posP]}
        self.move(requests)

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

    def calibrate(self,pos_ids='all',mode='quick',save_file_dir='./',save_file_timestamp='sometime'):
        """Sweep a circle of points about theta and phi to measure positioner center
        locations, R1 and R2 arm lengths, theta and phi offsets, and then set all these
        calibration values for each positioner.

        INPUTS:  pos_ids  ... list of pos_ids or 'all'
                 mode     ... 'full' or 'quick' -- see detailed comments in _measure_calibration_arc method
                              'grid' -- error minimizer on grid of points to find best fit calibration parameters

        Typically one does NOT call 'full' mode unless the theta offsets are already
        reasonably well known. That can be achieved by first doing a 'quick' mode
        calibration.
        """
        def save_file(pos_id):
            return save_file_dir + os.path.sep + pos_id + '_' + save_file_timestamp + '_calib_' + mode + '.png'
        if mode == 'grid':
            if self.grid_calib_num_DOF >= self.grid_calib_num_constraints: # the '=' in >= comparison is due to some places in the code where I am requiring at least one extra point more than exact constraint 
                print('Not enough points requested to constrain grid calibration. Defaulting to arc calibration method.')
                self.calibrate(pos_ids,'quick',save_file_dir,save_file_timestamp)
                return
            grid_data = self._measure_calibration_grid(pos_ids, keep_phi_within_Eo=self.grid_calib_keep_phi_within_Eo)
            grid_data = self._calculate_and_set_arms_and_offsets_from_grid_data(grid_data, set_gear_ratios=False)
            for pos_id in grid_data.keys():
                poscalibplot.plot_grid(save_file(pos_id), pos_id, grid_data)
        else:
            T = self._measure_calibration_arc(pos_ids,'theta',mode)
            P = self._measure_calibration_arc(pos_ids,'phi',mode)
            #set_gear_ratios = False if mode == 'quick' else True
            set_gear_ratios = False # not sure yet if we really want to adjust gear ratios automatically, hence by default False here
            unwrapped_data = self._calculate_and_set_arms_and_offsets_from_arc_data(T,P,set_gear_ratios)
            for pos_id in T.keys():
                poscalibplot.plot_arc(save_file(pos_id), pos_id, unwrapped_data)

    def identify_fiducials(self):
        """Nudge positioners (all together) forward/back to determine which centroid dots are fiducials.
        """
        print('Nudging positioners to identify reference dots.')
        requests = {}
        for pos_id in self.all_pos_ids():
            requests[pos_id] = {'command':'posTP', 'target':[0,180], 'log_note':'identify fiducials starting point'}
        self.move(requests) # go to starting point
        self._identify(None)

    def identify_positioner_locations(self):
        """Nudge positioners (one at a time) forward/back to determine which positioners are where on the FVC.
        """
        print('Nudging positioners to identify their starting locations.')
        requests = {}
        for pos_id in self.all_pos_ids():
            requests[pos_id] = {'command':'posTP', 'target':[0,180], 'log_note':'identify positioners starting point'}
        self.move(requests) # go to starting point
        for pos_id in self.all_pos_ids():
            print('Identifying location of positioner ' + pos_id)
            self._identify(pos_id)

    def pos_data_listed_by_ptl(self, pos_ids='all', key=''):
        """Returns a dictionary with keys = petal objects and values = lists of data
        (the particular data to retrieve is identified by key) on each petal.  If
        pos_ids argument == 'all', then each list contains all the data on that petal.
        If pos_ids argument is a list of pos_ids, then in the returned dictionary, each list
        contains only the data for those positioners which are in the intersection set of
        pos_ids with that petal's positioner ids.
        """
        data_by_ptl = {}
        if pos_ids != 'all':
            pos_ids = pc.listify(pos_ids,keep_flat=True)[0]
        for petal in self.petals:
            all_pos_on_ptl = pc.listify(petal.get(key='POS_ID'),keep_flat=True)[0]
            if pos_ids == 'all':
                these_pos_ids = all_pos_on_ptl
            else:
                these_pos_ids = [p for p in pos_ids if p in all_pos_on_ptl]
            this_data = petal.get(these_pos_ids,key)
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
    
    def all_pos_ids(self):
        """Returns a list of all the pos_ids on all the petals.
        """
        all_pos_ids = []
        pos_ids_by_ptl = self.pos_data_listed_by_ptl('all','POS_ID')
        for petal in pos_ids_by_ptl.keys():
            all_pos_ids.extend(pos_ids_by_ptl[petal])
        return all_pos_ids

    def _measure_calibration_grid(self,pos_ids='all',keep_phi_within_Eo=True):
        """Expert usage. Send positioner(s) to a series of commanded (theta,phi) positions. Measure
        the (x,y) positions of these points with the FVC.

        INPUTS:   pos_ids             ... list of pos_ids or 'all'
                  keep_phi_within_Eo  ... True, to guarantee no anticollision needed
                                          False, to cover the full range of phi with the grid

        OUTPUTS:  data ... see comments below

        Returns a dictionary of dictionaries containing the data. The primary
        keys for the dict are the pos_id. Then for each pos_id, each subdictionary
        contains the keys:
            'target_posTP'    ... the posTP targets which were attempted
            'measured_obsXY'  ... the resulting measured xy positions
            'petal'           ... the petal this pos_id is on
            'trans'           ... the postransform object associated with this particular positioner
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        data = {}
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            for pos_id in these_pos_ids:
                data[pos_id] = {}
                posmodel = petal.get(pos_id)
                range_T = posmodel.targetable_range_T
                range_P = posmodel.targetable_range_P
                if keep_phi_within_Eo:
                    range_P[0] = self.phi_clear_angle
                t_cmd = np.linspace(min(range_T),max(range_T),self.n_points_full_calib_T + 1) # the +1 is temporary, remove that extra point in next line
                t_cmd = t_cmd[:-1] # since theta covers +/-180, it is kind of redundant to hit essentially the same points again
                p_cmd = np.linspace(min(range_P),max(range_P),self.n_points_full_calib_P + 1) # the +1 is temporary, remove that extra point in next line
                p_cmd = p_cmd[:-1] # since there is very little useful data right near the center
                data[pos_id]['target_posTP'] = [[t,p] for t in t_cmd for p in p_cmd]
                data[pos_id]['trans'] = posmodel.trans
                data[pos_id]['petal'] = petal
                data[pos_id]['measured_obsXY'] = []
                n_pts = len(data[pos_id]['target_posTP'])
        all_pos_ids = list(data.keys())
        
        # make the measurements
        for i in range(n_pts):
            requests = {}
            for pos_id in all_pos_ids:
                requests[pos_id] = {'command':'posTP', 'target':data[pos_id]['target_posTP'][i], 'log_note':'calib grid point ' + str(i+1)}
            print('calibration grid point ' + str(i+1) + ' of ' + str(n_pts))
            this_meas_data = self.move_measure(requests)
            for p in this_meas_data.keys():
                data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],this_meas_data[p])
        return data 

    def _measure_calibration_arc(self,pos_ids='all',axis='theta',mode='quick'):
        """Expert usage. Sweep an arc of points about axis ('theta' or 'phi')
        on positioners identified by pos_ids. Measure these points with the FVC
        and do a best fit of them.

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
                    initial_tp = pc.concat_lists_of_lists(initial_tp, [min(targetable_range_T) + self.calib_arc_margin, phi_clear_angle])
                    final_tp   = pc.concat_lists_of_lists(final_tp,   [max(targetable_range_T) - self.calib_arc_margin, initial_tp[-1][1]])
            else:
                n_pts = 3 if mode == 'quick' else self.n_points_full_calib_P
                for posmodel in posmodels:
                    if mode == 'quick':
                        phi_min = phi_clear_angle
                        theta = 0
                    else:
                        phi_min = min(posmodel.targetable_range_P)
                        theta = posmodel.trans.obsTP_to_posTP([0,0])[pc.T] # when doing phi axis, want obsT to all be uniform (simplifies anti-collision), which means have to figure out appropriate posT for each positioner -- depends on already knowing theta offset reasonably well
                    initial_tp = pc.concat_lists_of_lists(initial_tp, [theta, phi_min + self.calib_arc_margin])
                    final_tp   = pc.concat_lists_of_lists(final_tp,   [initial_tp[-1][0], max(posmodel.targetable_range_P) - self.calib_arc_margin])
            
            for i in range(len(these_pos_ids)):
                t = np.linspace(initial_tp[i][0], final_tp[i][0], n_pts)
                p = np.linspace(initial_tp[i][1], final_tp[i][1], n_pts)
                data[these_pos_ids[i]] = {'target_posTP':[[t[j],p[j]] for j in range(n_pts)], 'measured_obsXY':[], 'petal':petal, 'trans':posmodels[i].trans}
        all_pos_ids = list(data.keys())

        # make the measurements
        for i in range(n_pts):
            requests = {}
            for pos_id in all_pos_ids:
                requests[pos_id] = {'command':'posTP', 'target':data[pos_id]['target_posTP'][i], 'log_note':'calib arc on ' + axis + ' point ' + str(i+1)}
            print('\'' + mode + '\' calibration arc on ' + axis + ' axis: point ' + str(i+1) + ' of ' + str(n_pts))
            this_meas_data = self.move_measure(requests)
            for p in this_meas_data.keys():
                data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],this_meas_data[p])

        # circle fits
        for pos_id in all_pos_ids:
            (xy_ctr,radius) = fitcircle.FitCircle().fit(data[pos_id]['measured_obsXY'])
            data[pos_id]['xy_center'] = xy_ctr
            data[pos_id]['radius'] = radius
        
        return data

    def _measure_range_arc(self,pos_ids='all',axis='theta'):
        """Expert usage. Measure physical range of an axis by sweep a brief arc of points
        on positioners identified bye unwrapped  pos_ids. Measure these points with the FVC
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
            'radius'          ... best fit arc's raTruedius
            'petal'           ... petal this pos_id is on
            'trans'           ... postransform object associated with this particular positioner
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        phi_clear_angle = self.phi_clear_angle
        n_intermediate_pts = 2
        data = {}
        initial_tp_requests = {}
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            if axis == 'theta':
                delta = 360/(n_intermediate_pts + 1)
                dtdp = [delta,0]
                axisid = pc.T
                for pos_id in these_pos_ids:
                    initial_tp = [-150, phi_clear_angle]
                    initial_tp_requests[pos_id] = {'command':'posTP', 'target':initial_tp, 'log_note':'range arc ' + axis + ' initial point'}
            else:
                delta = -180/(n_intermediate_pts + 1)
                dtdp = [0,delta]
                axisid = pc.P
                for pos_id in these_pos_ids:
                    posmodel = petal.get(pos_id)
                    initial_tp = posmodel.trans.obsTP_to_posTP([0,phi_clear_angle]) # when doing phi axis, want obsT to all be uniform (simplifies anti-collision), which means have to figure out appropriate posT for each positioner -- depends on already knowing theta offset reasonably well
                    initial_tp_requests[pos_id] = {'command':'posTP', 'target':initial_tp,  'log_note':'range arc ' + axis + ' initial point'}
            for i in range(len(these_pos_ids)):
                data[these_pos_ids[i]] = {'target_dtdp':dtdp, 'measured_obsXY':[], 'petal':petal}
        all_pos_ids = list(data.keys())

        prefix = 'range measurement on ' + axis + ' axis'
        # go to initial point
        print(prefix + ': initial point')
        self.move(initial_tp_requests)

        # seek first limit
        print(prefix + ': seeking first limit')
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            petal.request_limit_seek(these_pos_ids, axisid, -np.sign(delta), log_note='seeking first ' + axis + ' limit')
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal
        meas_data = self.measure()
        for p in meas_data.keys():
            data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],meas_data[p])

        # intermediate points
        for i in range(n_intermediate_pts):
            print(prefix + ': intermediate point ' + str(i+1) + ' of ' + str(n_intermediate_pts))
            # Note that anticollision is NOT done here. The reason is that phi location is not perfectly
            # well-known at this point (having just struck a hard limit). So externally need to have made
            # sure there was a clear path for the phi arm ahead of time.
            for petal in pos_ids_by_ptl.keys():
                requests = {}
                for pos_id in pos_ids_by_ptl[petal]:
                    requests[pos_id] = {'target':dtdp, 'log_note':'intermediate ' + axis + ' point ' + str(i)}
                petal.request_direct_dtdp(requests)
                petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal
            meas_data = self.measure()
            for p in meas_data.keys():
                data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],meas_data[p])

        # seek second limit
        print(prefix + ': seeking second limit')
        for petal in pos_ids_by_ptl.keys():
            these_pos_ids = pos_ids_by_ptl[petal]
            petal.request_limit_seek(these_pos_ids, axisid, np.sign(delta), log_note='seeking second ' + axis + ' limit')
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
                petal.request_limit_seek(these_pos_ids, axisid, -np.sign(delta), log_note='housekeeping extra ' + axis + ' limit seek')
                petal.schedule_send_and_execute_moves()

        return data

    def _calculate_and_set_arms_and_offsets_from_grid_data(self, data, set_gear_ratios=False):
        """Helper function for grid method of calibration. See the _measure_calibration_grid method for
        more information on format of the dictionary 'data'. This method adds the fields 'ERR_NORM' and
        'final_expected_obsXY' to the data dictionary for each positioner.
        """
        param_keys = self.grid_calib_param_keys
        for pos_id in data.keys():
            trans = data[pos_id]['trans']   
            trans.alt_override = True
            for key in param_keys:
                data[pos_id][key] = []
            data[pos_id]['ERR_NORM'] = []
            data[pos_id]['point_numbers'] = []
            initial_params_dict = postransforms.PosTransforms().alt
            params0 = [initial_params_dict[key] for key in param_keys]
            point0 = self.grid_calib_num_DOF - 1
            for pt in range(point0,len(data[pos_id]['measured_obsXY'])):
                meas_xy = np.array([data[pos_id]['measured_obsXY'][j] for j in range(pt+1)]).transpose()
                targ_tp = np.array([data[pos_id]['target_posTP'][j] for j in range(pt+1)]).transpose()
                def expected_xy(params):
                    for j in range(len(param_keys)):
                        trans.alt[param_keys[j]] = params[j]
                    return trans.posTP_to_obsXY(targ_tp.tolist())
                def err_norm(params):
                    expected = np.array(expected_xy(params))
                    all_err = expected - meas_xy
                    return np.linalg.norm(all_err,ord='fro')
                    
                # apply some forced characteristics of parameters
                params0[param_keys.index('LENGTH_R1')] = abs(params0[param_keys.index('LENGTH_R1')]) # don't let the radii flip signs
				length_r2_idx = param_keys.index('LENGTH_R2')
				if params0[length_r2_idx] < 0:
					params0[length_r2_idx] = abs(params0[param_keys.index('LENGTH_R2')]) # don't let the radii flip signs
					offset_p_idx = param_keys.index('OFFSET_P')
					if params0[offset_p_idx] < -180:
						params0[offset_p_idx] += 180 # prevent combined phi / R2 sign flip
					elif params0[offset_p_idx] > 180:
						params0[offset_p_idx] -= 180 # prevent combined phi / R2 sign flip
                offset_t_idx = param_keys.index('OFFSET_T')
                if params0[offset_t_idx] > 180:
                    params0[offset_t_idx] -= 360 # keep theta offset within +/-180
                elif params0[offset_t_idx] < -180:
                    params0[offset_t_idx] += 360 # keep theta offset within +/-180
				
                params_optimized = scipy.optimize.fmin(func=err_norm, x0=params0, disp=False)
                params0 = params_optimized
                if pt > point0: # don't bother logging first point, which is always junk and just getting the (x,y) offset in the ballpark
                    data[pos_id]['ERR_NORM'].append(err_norm(params_optimized))
                    data[pos_id]['point_numbers'].append(pt+1)
                    debug_str = 'Grid calib on ' + str(pos_id) + ' point ' + str(data[pos_id]['point_numbers'][-1]) + ':'
                    debug_str += ' ERR_NORM=' + format(data[pos_id]['ERR_NORM'][-1],'.3f')
                    for j in range(len(param_keys)):
                        data[pos_id][param_keys[j]].append(params_optimized[j])
                        debug_str += '  ' + param_keys[j] +': ' + format(data[pos_id][param_keys[j]][-1],'.3f')
                    print(debug_str)
            trans.alt_override = False
            petal = data[pos_id]['petal']
            for key in param_keys:
                petal.set(pos_id,key,data[pos_id][key][-1])
                print('Grid calib on ' + str(pos_id) + ': ' + key + ' set to ' + format(data[pos_id][key][-1],'.3f'))
            data[pos_id]['final_expected_obsXY'] = np.array(expected_xy(params_optimized)).transpose().tolist()
        return data

    def _calculate_and_set_arms_and_offsets_from_arc_data(self, T, P, set_gear_ratios=False):
        """Helper function for arc method of calibration. T and P are data dictionaries taken on the
        theta and phi axes. See the _measure_calibration_arc method for more information.
        """
        data = {}
        for pos_id in T.keys():
            # gather targets data
            t_targ_posT = [posTP[pc.T] for posTP in T[pos_id]['target_posTP']]
            t_targ_posP = [posTP[pc.P] for posTP in T[pos_id]['target_posTP']]
            p_targ_posP = [posTP[pc.P] for posTP in P[pos_id]['target_posTP']]
            p_targ_posT = [posTP[pc.T] for posTP in P[pos_id]['target_posTP']]        
            t_meas_obsXY = T[pos_id]['measured_obsXY']
            p_meas_obsXY = P[pos_id]['measured_obsXY']
            
            # arms and offsets
            petal = T[pos_id]['petal']
            t_ctr = np.array(T[pos_id]['xy_center'])
            p_ctr = np.array(P[pos_id]['xy_center'])
            length_r1 = np.sqrt(np.sum((t_ctr - p_ctr)**2))
            petal.set(pos_id,'LENGTH_R1',length_r1)
            petal.set(pos_id,'LENGTH_R2',P[pos_id]['radius'])
            petal.set(pos_id,'OFFSET_X',t_ctr[0])
            petal.set(pos_id,'OFFSET_Y',t_ctr[1])
            p_meas_obsT = np.arctan2(p_ctr[1]-t_ctr[1], p_ctr[0]-t_ctr[0]) * 180/np.pi
            offset_t = p_meas_obsT - p_targ_posT[0] # just using the first target theta angle in the phi sweep
            petal.set(pos_id,'OFFSET_T',offset_t)
            xy = np.array(p_meas_obsXY)
            angles = np.arctan2(xy[:,1]-p_ctr[1], xy[:,0]-p_ctr[0]) * 180/np.pi
            p_meas_obsP = angles - p_meas_obsT
            expected_sign_of_first_angle = np.sign(p_targ_posP[0])
            expected_direction = np.sign(p_targ_posP[1] - p_targ_posP[0])
            p_meas_obsP_wrapped = self._wrap_consecutive_angles(p_meas_obsP.tolist(), expected_sign_of_first_angle, expected_direction)
            offset_p = np.median(np.array(p_meas_obsP_wrapped) - np.array(p_targ_posP))
            petal.set(pos_id,'OFFSET_P',offset_p)
            p_meas_posP_wrapped = (np.array(p_meas_obsP_wrapped) - offset_p).tolist()
            
            # unwrap thetas
            t_meas_posTP = T[pos_id]['trans'].obsXY_to_posTP(np.transpose(t_meas_obsXY).tolist())[0]
            t_meas_posT = t_meas_posTP[pc.T]
            expected_sign_of_first_angle = np.sign(t_targ_posT[0])
            expected_direction = np.sign(t_targ_posT[1] - t_targ_posT[0])
            t_meas_posT_wrapped = self._wrap_consecutive_angles(t_meas_posT, expected_sign_of_first_angle, expected_direction)
            
            # gather data to return in an organized fashion (used especially for plotting)
            data[pos_id] = {}
            data[pos_id]['xy_ctr_T'] = t_ctr
            data[pos_id]['xy_ctr_P'] = p_ctr
            data[pos_id]['radius_T'] = T[pos_id]['radius']
            data[pos_id]['radius_P'] = P[pos_id]['radius']
            data[pos_id]['measured_obsXY_T'] = t_meas_obsXY
            data[pos_id]['measured_obsXY_P'] = p_meas_obsXY
            data[pos_id]['targ_posT_during_T_sweep'] = t_targ_posT
            data[pos_id]['targ_posP_during_P_sweep'] = p_targ_posP
            data[pos_id]['meas_posT_during_T_sweep'] = t_meas_posT_wrapped
            data[pos_id]['meas_posP_during_P_sweep'] = p_meas_posP_wrapped
            data[pos_id]['targ_posP_during_T_sweep'] = t_targ_posP[0]
            data[pos_id]['targ_posT_during_P_sweep'] = p_targ_posT[0]
            
            # gear ratios
            ratios_T = np.divide(np.diff(t_meas_posT_wrapped),np.diff(t_targ_posT))
            ratios_P = np.divide(np.diff(p_meas_posP_wrapped),np.diff(p_targ_posP))
            ratio_T = np.median(ratios_T)
            ratio_P = np.median(ratios_P)
            data[pos_id]['gear_ratio_T'] = ratio_T
            data[pos_id]['gear_ratio_P'] = ratio_P
            print('Measurement proposes GEAR_CALIB_T = ' + format(ratio_T,'.6f'))
            print('Measurement proposes GEAR_CALIB_P = ' + format(ratio_P,'.6f'))
            if set_gear_ratios:
                petal.set(pos_id,'GEAR_CALIB_T',ratio_T)
                petal.set(pos_id,'GEAR_CALIB_P',ratio_P)
        return data

    def _identify(self, pos_id=None):
        """Generic function for identifying either all fiducials or a single positioner's location.
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl('all','POS_ID')
        n_dots = len(self.all_pos_ids()) + self.n_fiducial_dots
        nudges = [-self.nudge_dist, self.nudge_dist]
        xy_ref = []
        for i in range(len(nudges)):
            dtdp = [0,nudges[i]]
            if pos_id == None:
                identify_fiducials = True
                log_note = 'nudge to identify fiducials '
                for petal in pos_ids_by_ptl.keys():
                    requests = {}
                    for p in pos_ids_by_ptl[petal]:
                        if identify_fiducials or p == pos_id:
                            requests[p] = {'target':[0,nudges[i]], 'log_note':log_note}
                    petal.request_direct_dtdp(requests)
                    petal.schedule_send_and_execute_moves()
            else:
                identify_fiducials = False
                log_note = 'nudge to identify positioner location '
                request = {pos_id:{'target':dtdp, 'log_note':log_note}}
                this_petal = self.ptls_of_pos_ids(pos_id)[pos_id]
                this_petal.request_direct_dtdp(request)
                this_petal.schedule_send_and_execute_moves()
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
        if identify_fiducials:
            if len(xy_ref) != self.n_fiducial_dots:
                print('warning: number of ref dots detected (' + str(len(xy_ref)) + ') is not equal to expected number of fiducial dots (' + str(self.n_fiducial_dots) + ')')
            self.fiducials_xy = xy_ref
        else:
            if n_dots - len(ref_idxs) != 1:
                print('warning: more than one moving dots detected')
            else:
                ref_idxs.sort(reverse=True)
                for i in ref_idxs:
                    xy_test.pop(i) # get rid of all but the moving pos
                expected_obsXY = this_petal.expected_current_position(pos_id,'obsXY')
                measured_obsXY = xy_test[0]
                err_x = measured_obsXY[0] - expected_obsXY[0]
                err_y = measured_obsXY[1] - expected_obsXY[1]
                prev_offset_x = this_petal.get(pos_id,'OFFSET_X')
                prev_offset_y = this_petal.get(pos_id,'OFFSET_Y')
                this_petal.set(pos_id,'OFFSET_X', prev_offset_x + err_x) # this works, assuming we have reasonable knowledge of theta and phi (having re-homed or quick-calibrated)
                this_petal.set(pos_id,'OFFSET_Y', prev_offset_y + err_y) # this works, assuming we have reasonable knowledge of theta and phi (having re-homed or quick-calibrated)
                this_petal.set(pos_id,'LAST_MEAS_OBS_X',measured_obsXY[0])
                this_petal.set(pos_id,'LAST_MEAS_OBS_Y',measured_obsXY[1])

    @property
    def phi_clear_angle(self):
        """Returns the phi angle in degrees for which two positioners cannot collide
        if they both have phi at this angle or greater.
        """
        phi_Eo_angle = poscollider.PosCollider().config['PHI_EO']
        phi_clear = phi_Eo_angle + self.phi_Eo_margin
        return phi_clear
        
    @property
    def grid_calib_num_DOF(self):
        return len(self.grid_calib_param_keys) # need at least this many points to exactly constrain the TP --> XY transformation function
    
    @property
    def grid_calib_num_constraints(self):
        return self.n_points_full_calib_T * self.n_points_full_calib_P
        
    def _wrap_consecutive_angles(self, angles, expected_sign_of_first_angle, expected_direction):
        """Wrap angles in one expected direction. It is expected that the physical deltas
        we are trying to wrap all increase or all decrease sequentially. In other words, that
        the sequence of angles is only going one way around the circle.
        """
        wrapped = [angles[0]]
        if np.sign(angles[0]) != expected_sign_of_first_angle and np.sign(angles[0]) != 0:
            wrapped[0] -= expected_sign_of_first_angle * 360
        for i in range(1,len(angles)):
            delta = angles[i] - wrapped[i-1]
            while np.sign(delta) != expected_direction and np.sign(delta) != 0:
                delta += expected_direction * 360
            wrapped.append(wrapped[-1] + delta)
        return wrapped
