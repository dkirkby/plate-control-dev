import os
import sys
if "TEST_LOCATION" in os.environ and os.environ['TEST_LOCATION']=='Michigan':
    basepath=os.environ['TEST_BASE_PATH']+'plate_control/'+os.environ['TEST_TAG']
    sys.path.append(os.path.abspath(basepath+'/petal/'))

else:
    sys.path.append(os.path.abspath('../petal/'))

import postransforms
import numpy as np
import fitcircle
import posconstants as pc
import poscalibplot
import scipy.optimize
import collections

class PosMoveMeasure(object):
    """Coordinates moving fiber positioners with fiber view camera measurements.
    """
    def __init__(self, petals, fvc, printfunc=print):
        self.printfunc = printfunc # allows you to specify an alternate to print (useful for logging the output)
        if not isinstance(petals,list):
            petals = [petals]
        self.petals = petals # list of petal objects
        self._petals_map = {} # maps which petals hold which posids
        for petal in self.petals:
            for posid in petal.posids:
                self._petals_map[posid] = petal
            for fidid in petal.fidids:
                self._petals_map[fidid] = petal
                for dotid in petal.fid_dotids(fidid):
                    self._petals_map[dotid] = petal
        self.fvc = fvc # fvchandler object
        self.ref_dist_tol = 2.0   # [pixels on FVC CCD] used for identifying fiducial dots
        self.nudge_dist   = 10.0  # [deg] used for identifying fiducial dots
        self.extradots_fvcXY = [] # stores [x,y] pixel locations of any "extra" fiducial dots in the field (used for fixed ref fibers in laboratory test stands)
        self.extradots_id = 'EXTRA' # identifier to use in extra dots id string
        self.n_extradots_expected = 0 # number of extra dots to look for in the field of view
        if self.fvc.fvcproxy:
            # This is a temporary hack, since we don't yet support arbitrary device ids in the proxy.
            # The ids assigned here do NOT correspond to physical reality of which dot is generated at which particular device.
            from DOSlib.positioner_index import PositionerIndex
            posindex = PositionerIndex()
            devices = []
            for ptl in self.petals:
                devices += posindex.find_by_arbitrary_keys(PETAL_ID=ptl.petal_id)
            all_device_ids = self.all_posids.union(self.all_fidids)
            self.extradot_ids = [device['DEVICE_ID'] for device in devices if device['DEVICE_ID'] not in all_device_ids]
        self.n_points_calib_T = 7 # number of points in a theta calibration arc
        self.n_points_calib_P = 7 # number of points in a phi calibration arc
        self.should_set_gear_ratios = False # whether to adjust gear ratios after calibration
        self.phi_Eo_margin = 3.0 # [deg] margin on staying within Eo envelope
        self.phi_close_angle = 135.0 # [deg] phi angle where fiber is quite close to the center, within the spot-matching radius tolerance of the fiber view camera. Consider at a later date moving this parameter out into a settings file such as the collider .conf file.
        self.calib_arc_margin = 3.0 # [deg] margin on calibration arc range
        self.use_current_theta_during_phi_range_meas = False # useful for when theta axis is not installed on certain sample positioners
        self.general_trans = postransforms.PosTransforms() # general transformation object (not specific to calibration of any one positioner), useful for things like obsXY to QS or QS to obsXY coordinate transforms
        self.grid_calib_param_keys = ['LENGTH_R1','LENGTH_R2','OFFSET_T','OFFSET_P','OFFSET_X','OFFSET_Y']
        self.err_level_to_save_move0_img = np.inf # value at which to preserve move 0 fvc images (for debugging if a measurement is off by a lot)
        self.err_level_to_save_moven_img = np.inf # value at which to preserve last corr move fvc images (for debugging if a measurement is off by a lot)
        self.tp_updates_mode = 'posTP' # options are None, 'posTP', 'offsetsTP'. see comments in move_measure() function for explanation
        self.tp_updates_tol = 0.065 # [mm] tolerance on error between requested and measured positions, above which to update the POS_T,POS_P or OFFSET_T,OFFSET_P parameters
        self.tp_updates_fraction = 0.8 # fraction of error distance by which to adjust POS_T,POS_P or OFFSET_T,OFFSET_P parameters after measuring an excessive error with FVC
        self.make_plots_during_calib = True # whether to automatically generate and save plots of the calibration data

    def measure(self):
        """Measure positioner locations with the FVC and return the values.

        Return data is a dictionary with:   keys ... posid
                                          values ... [measured_obs_x, measured_obs_y]
        """        
        data = {}
        expected_pos = collections.OrderedDict()
        for posid in self.all_posids:
            ptl = self.petal(posid)
            expected_pos[posid] = {'obsXY':ptl.expected_current_position(posid,'obsXY')}
        expected_ref = self.ref_dots_XY
        if self.fvc.fvc_type in ['FLI','SBIG_Yale']:
            # Consider replacing this implementation with one where instead of "extra dots", we
            # differentiate positioners by their CTRL_ENABLED flag instead. This means doing
            # some detail rework in xytest.py, to make sure we are choosing the correct actions
            # at each step for each positioner, depending on whether it is in fact enabled or not.
            # (Long term, this work is the right thing to do, because we certainly expect that
            # dead positioners will occur on the instrument.)
            extra_dots = {refid:{'obsXY':expected_ref[refid]['obsXY']} for refid in expected_ref.keys() if refid in self.extradot_ids}
            expected_pos.update(extra_dots)
        measured_pos,measured_ref,imgfiles = self.fvc.measure_and_identify(expected_pos,expected_ref)            
        for posid in self.all_posids:
            ptl = self.petal(posid)
            ptl.set_posfid_val(posid,'LAST_MEAS_OBS_X',measured_pos[posid]['obsXY'][0])
            ptl.set_posfid_val(posid,'LAST_MEAS_OBS_Y',measured_pos[posid]['obsXY'][1])
            ptl.set_posfid_val(posid,'LAST_MEAS_PEAK',measured_pos[posid]['peak'])
            ptl.set_posfid_val(posid,'LAST_MEAS_FWHM',measured_pos[posid]['fwhm'])
            data[posid] = measured_pos[posid]['obsXY']
        fid_data = {}
        for refid in measured_ref.keys():
            if self.extradots_id not in refid:
                ptl = self.petal(refid)
                fidid = ptl.extract_fidid(refid)
                if fidid not in fid_data.keys():
                    fid_data[fidid] = {key:[] for key in ['obsX','obsY','peaks','fwhms']}
                fid_data[fidid]['obsX'].append(measured_ref[refid]['obsXY'][0])
                fid_data[fidid]['obsY'].append(measured_ref[refid]['obsXY'][1])
                fid_data[fidid]['peaks'].append(measured_ref[refid]['peak'])
                fid_data[fidid]['fwhms'].append(measured_ref[refid]['fwhm'])
        for fidid in fid_data.keys():
            ptl = self.petal(fidid)
            ptl.set_posfid_val(fidid,'LAST_MEAS_OBS_X',fid_data[fidid]['obsX'])
            ptl.set_posfid_val(fidid,'LAST_MEAS_OBS_Y',fid_data[fidid]['obsY'])
            ptl.set_posfid_val(fidid,'LAST_MEAS_PEAKS',fid_data[fidid]['peaks'])
            ptl.set_posfid_val(fidid,'LAST_MEAS_FWHMS',fid_data[fidid]['fwhms'])
        return data,imgfiles

    def move(self, requests):
        """Move positioners. See request_targets method in petal.py for description
        of format of the 'requests' dictionary.
        """
        posids_by_petal = self.posids_by_petal(requests)
        for petal,posids in posids_by_petal.items():
            these_requests = {}
            for posid in posids:
                these_requests[posid] = requests[posid]
            petal.request_targets(these_requests)            
            petal.schedule_send_and_execute_moves() # in future, may do this in a different thread for each petal

    def move_measure(self, requests, tp_updates=None):
        """Move positioners and measure output with FVC.
        See comments on inputs from move method.
        See comments on outputs from measure method.
        tp_updates  ... This optional setting allows one to turn on a mode where the measured fiber positions
                        will be compared against the expected positions, and then if the error exceeds some
                        tolerance value, we will update internal parameters to mitigate the error on future moves.
                        
                            tp_updates='posTP'     ... updates will be made to the internally-tracked shaft positions, POS_T and POS_P
                            tp_updates='offsetsTP' ... updates will be made to the calibration values OFFSET_T and OFFSET_P
                            tp_updates='offsetsTP_close' ... updates will be made to the calibration values OFFSET_T and OFFSET_P. The difference with 'offsetTP' is that the phi is opend to phi_close_angle instead of the E0 angle specified in poscollider. 
                            tp_updates=None        ... no updating (this is the default)
                        
                        The intention of the 'posTP' option is that if the physical motor shaft hangs up slightly and loses
                        sync with the rotating magnetic field in the motors, then we slightly lose count of where we are. So
                        updating 'posTP' adjusts our internal count of shaft angle to try to mitigate.
                        
                        The usage of the 'offsetsTP' option is expected to be far less common than 'posTP', because
                        we anticipate that the calibration offsets should be quite stable, reflecting the unchanging
                        physical geometry of the fiber positioner as-installed. The purpose of using 'offsetsTP' would be more
                        limited to scenarios of initial calibration, if for some reason we find that the usual calibrations are
                        failing.
        """
        self.move(requests)
        data,imgfiles = self.measure()
        if tp_updates == 'posTP' or tp_updates =='offsetsTP' or tp_updates == 'offsetsTP_close':
            self._test_and_update_TP(data, tp_updates)
        return data,imgfiles

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
                posTP       [[t0,p0],[t1,p1],...]       ... ierr_level_to_save_movei_imgnternally-tracked expected angular positions of the (theta,phi) shafts at the outputs of their gearboxes
        """
        data = requests.copy()
        for posid in data.keys():
            m = data[posid] # for terseness below
            if m['command'] == 'obsXY':
                m['targ_obsXY'] = m['target']
            elif m['command'] == 'QS':
                m['targ_obsXY'] = self.general_trans.QS_to_obsXY(m['target'])
            else:
                self.printfunc('coordinates \'' + m['command'] + '\' not valid or not allowed')
                return
            m['log_note'] = 'blind move'
            self.printfunc(str(posid) + ': blind move to (obsX,obsY)=(' + self.fmt(m['targ_obsXY'][0]) + ',' + self.fmt(m['targ_obsXY'][1]) + ')')
        this_meas,imgfiles = self.move_measure(data, tp_updates=self.tp_updates_mode)
        save_img = False
        for posid in this_meas.keys():
            m = data[posid] # again, for terseness
            m['meas_obsXY'] = [this_meas[posid]]
            m['errXY'] = [[m['meas_obsXY'][-1][0] - m['targ_obsXY'][0],
                           m['meas_obsXY'][-1][1] - m['targ_obsXY'][1]]]
            m['err2D'] = [(m['errXY'][-1][0]**2 + m['errXY'][-1][1]**2)**0.5]
            m['posTP'] = self.petal(posid).expected_current_position(posid,'posTP')
            if m['err2D'][-1] > self.err_level_to_save_move0_img:
                save_img = True
        if save_img:
            timestamp_str = pc.filename_timestamp_str_now()
            for file in imgfiles:
                os.rename(file, pc.dirs['xytest_plots'] + timestamp_str + '_move0' + file)
        for i in range(1,num_corr_max+1):
            correction = {}
            save_img = False
            for posid in data.keys():
                correction[posid] = {}
                dxdy = [-data[posid]['errXY'][-1][0],-data[posid]['errXY'][-1][1]]
                correction[posid]['command'] = 'dXdY'
                correction[posid]['target'] = dxdy
                correction[posid]['log_note'] = 'correction move ' + str(i)
                self.printfunc(str(posid) + ': correction move ' + str(i) + ' of ' + str(num_corr_max) + ' by (dx,dy)=(' + self.fmt(dxdy[0]) + ',' + self.fmt(dxdy[1]) + '), \u221A(dx\u00B2+dy\u00B2)=' + self.fmt(data[posid]['err2D'][-1]))
            this_meas,imgfiles = self.move_measure(correction, tp_updates=self.tp_updates_mode)
            for posid in this_meas.keys():
                m = data[posid] # again, for terseness
                m['meas_obsXY'].append(this_meas[posid])
                m['errXY'].append([m['meas_obsXY'][-1][0] - m['targ_obsXY'][0],
                                   m['meas_obsXY'][-1][1] - m['targ_obsXY'][1]])
                m['err2D'].append((m['errXY'][-1][0]**2 + m['errXY'][-1][1]**2)**0.5)
                m['posTP'].append(self.petal(posid).expected_current_position(posid,'posTP'))
                if m['err2D'][-1] > self.err_level_to_save_moven_img and i == num_corr_max:
                    save_img = True
            if save_img:
                timestamp_str = pc.filename_timestamp_str_now()
                for file in imgfiles:
                    os.rename(file, pc.dirs['xytest_plots'] + timestamp_str + '_move' + str(i) + file)                
        for posid in data.keys():
            self.printfunc(str(posid) + ': final error distance=' + self.fmt(data[posid]['err2D'][-1]))
        return data

    def retract_phi(self,posids='all'):
        """Get all phi arms within their clear rotation envelopes for positioners
        identified by posids.
        """
        posids_by_petal = self.posids_by_petal(posids)
        requests = {}
        posP = self.phi_clear_angle # uniform value in all cases
        for petal,these_posids in posids_by_petal.items():
            for posid in these_posids:
                posT = petal.expected_current_position(posid,'posT')
                requests[posid] = {'command':'posTP', 'target':[posT,posP], 'log_note':'retracting phi'}
        self.move(requests)
    
    def park(self,posids='all'):
        """Fully retract phi arms inward, and put thetas at their neutral theta = 0 position.
        """
        posids_by_petal = self.posids_by_petal(posids)
        requests = {}
        posT = 0
        for petal,these_posids in posids_by_petal.items():
            for posid in these_posids:
                posP = max(petal.posmodels[posid].targetable_range_P)
                requests[posid] = {'command':'posTP', 'target':[posT,posP], 'log_note':'parking'}
        self.move(requests)
        
    def one_point_calibration(self, posids='all', mode='posTP'):
        """Goes to a single point, makes measurement with FVC, and re-calibrates the internally-
        tracked angles for the current theta and phi shaft positions.
        
        This method is attractive after steps like rehoming to hardstops, because it is very
        quick to do, and should be fairly accurate in most cases. But will never be as statistically
        robust as a regular calibration routine, which does arcs of multiple points and then takes
        the best fit circle.
        
          mode ... 'posTP'              --> [common usage] moves positioner to (posT=0,posP=self.phi_clear_angle),
                                                  and then updates our internal counter on where we currently
                                                  expect the theta and phi shafts to be
                                                 
               ... 'offsetsTP'          --> [expert usage] moves to (posT=0,posP=self.phi_clear_angle),
                                                  and then updates setting for theta and phi physical offsets
                                                 
               ... 'offsetsTP_close' --> [expert usage] moves to (posT=0,posP=self.phi_close_angle),
                                                  and then updates setting for theta and phi physical offsets
                                                  
               ... 'offsetsXY' --> [expert usage] moves positioner to (posT=0,posP=180),
                                                  and then updates setting for x and y physical offsets
               
        Prior to calling a mode of 'offsetTP' or 'offsetXY', it is recommended to re-home the positioner
        if there is any uncertainty as to its current location. This is generally not necessary
        in the default case, using 'posTP'.
        """
        self.printfunc('Running one-point calibration of ' + mode)
        posT = 0
        if mode == 'posTP' or mode == 'offsetsTP':
            posP = self.phi_clear_angle
        elif mode == 'offsetsTP_close':
            posP = self.phi_close_angle
        else:
            posP = 180
        posids_by_petal = self.posids_by_petal(posids)
        requests = {}
        for these_posids in posids_by_petal.values():
            for posid in these_posids:
                requests[posid] = {'command':'posTP', 'target':[posT,posP], 'log_note':'one point calibration of ' + mode}
        if mode == 'posTP' or mode == 'offsetsTP' or mode == 'offsetsTP_close':
            old_tp_updates_tol = self.tp_updates_tol
            old_tp_updates_fraction = self.tp_updates_fraction
            self.tp_updates_tol = 0.001
            self.tp_updates_fraction = 1.0
            data,imgfiles = self.move_measure(requests,tp_updates=mode)
            self.tp_updates_tol = old_tp_updates_tol
            self.tp_updates_fraction = old_tp_updates_fraction
        else:
            data,imgfiles = self.move_measure(requests, tp_updates=None)
            for petal,these_posids in posids_by_petal.items():
                for posid in these_posids:
                    xy = data[posid]
                    petal.set_posfid_val(posid,'OFFSET_X',xy[0])
                    petal.set_posfid_val(posid,'OFFSET_Y',xy[1])
                    self.printfunc(posid + ': Set OFFSET_X to ' + self.fmt(xy[0]))
                    self.printfunc(posid + ': Set OFFSET_Y to ' + self.fmt(xy[1]))
        self.commit() # log note is already handled above

    def rehome(self,posids='all'):
        """Find hardstops and reset current known positions.
        INPUTS:     posids ... 'all' or a list of specific posids
        """
        posids_by_petal = self.posids_by_petal(posids)
        self.printfunc('rehoming', str({'petal ' + str(ptl.petal_id):posids_by_petal[ptl] for ptl in posids_by_petal}))
        for petal,these_posids in posids_by_petal.items():
            petal.request_homing(these_posids)
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal

    def measure_range(self,posids='all',axis='theta'):
        """Expert usage. Sweep several points about axis ('theta' or 'phi') on
        positioners identified by posids, striking the hard limits on either end.
        Calculate the total available travel range. Note that for axis='phi', the
        positioners must enter the collisionable zone, so the range seeking may
        occur in several successive stages.
        """
        self.calibrate(posids=posids,mode='rough')
        if axis == 'phi':
            axisid = pc.P
            parameter_name = 'PHYSICAL_RANGE_P'
            batches = posids # implement later some selection of smaller batches of positioners guaranteed not to collide
        else:
            axisid = pc.T
            parameter_name = 'PHYSICAL_RANGE_T'
            batches = posids
        data = {}
        batches = set(batches)
        for batch in batches:
            batch_data = self._measure_range_arc(batch,axis)
            data.update(batch_data)

        # unwrapping code here
        for posid in data.keys():
            delta = data[posid]['target_dtdp'][axisid]
            obsXY = data[posid]['measured_obsXY']
            center = data[posid]['xy_center']
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
            data[posid]['petal'].set_posfid_val(posid,parameter_name,total_angle)
        self.commit(log_note='range measurement complete')
        self.rehome(posids)
        self.one_point_calibration(posids, mode='posTP')

    def calibrate(self,posids='all',mode='arc',save_file_dir='./',save_file_timestamp='sometime',keep_phi_within_Eo=True):
        """Do a series of test points to measure and calulate positioner center
        locations, R1 and R2 arm lengths, theta and phi offsets, and then set all these
        calibration values for each positioner.

        INPUTS:  posids   ... list of posids or 'all'
        
                 mode     ... 'rough' -- very rough calibration using two measured points only, always should be followed by an arc or grid calibration
                              'arc'   -- best-fit circle to arcs of points on the theta and phi axes
                              'grid'  -- error minimizer on grid of points to find best fit calibration parameters
        
                 keep_phi_within_Eo ... boolean, states whether to never let phi outside the free rotation envelope

        Typically one does NOT call keep_phi_within_Eo = False unless the theta offsets are already
        reasonably well known. That can be achieved by first doing a 'rough' or other calibration
        calibration with keep_phi_within_Eo=True.
        
        OUTPUTS:  files  ... set of plot file paths generated by the function
                             (this is an empty set if the parameter make_plots_during_calib == False)
        """
        files = set()

        # 'rough' calibration is ALWAYS run
        self.rehome(posids)
        self.one_point_calibration(posids, mode='offsetsXY')
        posids_by_petal = self.posids_by_petal(posids)
        for petal,these_posids in posids_by_petal.items():
            keys_to_reset = ['LENGTH_R1','LENGTH_R2','OFFSET_T','OFFSET_P','GEAR_CALIB_T','GEAR_CALIB_P']
            for key in keys_to_reset:
                for posid in these_posids:
                    petal.set_posfid_val(posid, key, pc.nominals[key]['value'])
        self.commit(log_note='rough calibration complete')
        if self.fvc.fvcproxy:
                        self.one_point_calibration(posids, mode='offsetsTP_close')
                        self.one_point_calibration(posids, mode='offsetsTP')
        else:
                        self.one_point_calibration(posids, mode='offsetsTP')        
            
        # now do arc or grid calibrations
        if mode == 'arc' or mode == 'grid':
            if self.make_plots_during_calib:
                def save_file(posid):
                    return save_file_dir + posid + '_' + save_file_timestamp + '_calib_' + mode + '.png'
        if mode == 'grid':
            if self.grid_calib_num_DOF >= self.grid_calib_num_constraints: # the '=' in >= comparison is due to some places in the code where I am requiring at least one extra point more than exact constraint 
                new_mode = 'arc'    
                self.printfunc('Not enough points requested to constrain grid calibration. Defaulting to ' + new_mode + ' calibration method.')
                return self.calibrate(posids,new_mode,save_file_dir,save_file_timestamp)
            grid_data = self._measure_calibration_grid(posids, keep_phi_within_Eo)
            grid_data = self._calculate_and_set_arms_and_offsets_from_grid_data(grid_data, set_gear_ratios=self.should_set_gear_ratios)
            if self.make_plots_during_calib:
                for posid in grid_data.keys():
                    file = save_file(posid)
                    poscalibplot.plot_grid(file,posid, grid_data)
                    files.add(file)
        elif mode == 'arc':
            T = self._measure_calibration_arc(posids,'theta', keep_phi_within_Eo)
            P = self._measure_calibration_arc(posids,'phi', keep_phi_within_Eo)
            self.printfunc("Finished measuring calibration arcs.")
            unwrapped_data = self._calculate_and_set_arms_and_offsets_from_arc_data(T,P,set_gear_ratios=self.should_set_gear_ratios)
            if self.make_plots_during_calib:
                for posid in T.keys():
                    file = save_file(posid)
                    poscalibplot.plot_arc(file, posid, unwrapped_data)
                    files.add(file)
                    
        # lastly update the internally-tracked theta and phi shaft angles
        self.one_point_calibration(posids, mode='posTP')
        
        # commit data and return
        self.commit(log_note='full calibration complete')
        return files

    def identify_fiducials(self):
        """Nudge positioners (all together) forward/back to determine which centroid dots are fiducials.
        """
        self.printfunc('Nudging positioners to identify reference dots.')
        requests = {}
        for posid in self.all_posids:
            requests[posid] = {'command':'posTP', 'target':[0,180], 'log_note':'identify fiducials starting point'}
        self.move(requests) # go to starting point
        self._identify(None)

    def identify_positioner_locations(self):
        """Nudge positioners (one at a time) forward/back to determine which positioners are where on the FVC.
        """
        self.printfunc('Nudging positioners to identify their starting locations.')
        requests = {}
        all_posids = self.all_posids # no need to retreive dynamic property multiple times below
        for posid in all_posids:
            requests[posid] = {'command':'posTP', 'target':[0,180], 'log_note':'identify positioners starting point'}
        self.move(requests) # go to starting point
        total = len(all_posids)
        n = 0
        for posid in all_posids:
            n += 1
            self.printfunc('Identifying location of positioner ' + posid + ' (' + str(n) + ' of ' + str(total) + ')')
            self._identify(posid)

    def posids_by_petal(self, posids='all'):
        """Returns a dict that organizes the argued posids by the petals they are
        associated with. Keys = petal objects, values = sets of posids on each petal.
        Arguing 'all' returns all petals, and all posids on those petals.
        """
        if posids == 'all':
            return {petal:petal.posids for petal in self.petals}
        posids = set(posids)
        ptl_map = {posid:self._petals_map[posid] for posid in posids}
        posids_by_petal = {petal:{p for p in ptl_map if ptl_map[p] == petal} for petal in set(ptl_map.values())}
        return posids_by_petal
    
    @property
    def all_posids(self):
        """Returns a set of all the posids on all the petals.
        """
        all_posids = set()
        for ptl in self.petals:
            all_posids = all_posids.union(ptl.posids)
        return all_posids
    
    @property
    def all_fidids(self):
        """Returns a set of all the fidids on all the petals.
        """
        all_fidids = set()
        for ptl in self.petals:
            all_fidids = all_fidids.union(ptl.fidids)
        return all_fidids

    def petal(self, posid_or_fidid_or_dotid):
        """Returns the petal object associated with a single id key.
        """
        return self._petals_map[posid_or_fidid_or_dotid]
    
    def posmodel(self, posid):
        """Returns the posmodel object associated with a single posid.
        """
        return self.petal(posid).posmodels[posid]

    def state(self, posid):
        """Returns the posstate object associated with a single posid.
        """
        return self.posmodel(posid).state
    
    def trans(self, posid):
        """Returns the postransforms object associated with a single posid.
        """
        return self.posmodel(posid).trans
    
    def commit(self,log_note=''):
        """Commit state data controlled by all petals to storage.
        See commit function in petal.py for explanation of optional additional log note.
        """
        for ptl in self.petals:
            ptl.commit(log_note=log_note)
    
    def set_fiducials(self, setting='on'):
        """Apply uniform settings to all fiducials on all petals simultaneously.
        See set_fiducials() comments in petal for further details on argument and
        return formats. The typical usage is:
            set_fiducials('on')
            set_fiducials('off')
        """
        all_settings_done = {}
        for petal in self.petals:
            settings_done = petal.set_fiducials(setting=setting)
            all_settings_done.update(settings_done)
        return all_settings_done
            
    @property
    def ref_dots_XY(self):
        """Ordered dict of ordered dicts of nominal locations of all fixed reference dots in the FOV.
        Primary keys are the dot id strings. See petal.py similarly named function's comments.
        Sub-keys are:
            'fvcXY' --> [x,y] values in the FVC coordinate system (pixels)
            'obsXY' --> [x,y] values in the observer coordinate system (millimeters)
        """
        data = collections.OrderedDict()
        for ptl in self.petals:
            more_data = ptl.fiducial_dots_fvcXY
            for dotid in more_data.keys():
                more_data[dotid]['obsXY'] = self.fvc.fvcXY_to_obsXY([more_data[dotid]['fvcXY']])[0]
            data.update(more_data)
        for i in range(len(self.extradots_fvcXY)):
            if not self.fvc.fvcproxy:
                dotid = ptl.dotid_str(self.extradots_id,i) # any petal instance is fine here (static method)
            else:
                # This is a temporary hack, since we don't yet support arbitrary device ids in the proxy.
                # The ids assigned here do NOT correspond to physical reality of which dot is generated at which particular device.
                dotid = self.extradot_ids[i]
            data[dotid] = collections.OrderedDict()
            data[dotid]['obsXY'] = self.fvc.fvcXY_to_obsXY([self.extradots_fvcXY[i]])[0]
        return data

    def set_motor_parameters(self):
        '''Tells each petal to send all the latest motor settings out to positioners.
        '''
        for petal in self.petals:
            petal.set_motor_parameters()

    def _measure_calibration_grid(self,posids='all',keep_phi_within_Eo=True):
        """Expert usage. Send positioner(s) to a series of commanded (theta,phi) positions. Measure
        the (x,y) positions of these points with the FVC.

        INPUTS:   posids              ... list of posids or 'all'
                  keep_phi_within_Eo  ... True, to guarantee no anticollision needed
                                          False, to cover the full range of phi with the grid

        OUTPUTS:  data ... see comments below

        Returns a dictionary of dictionaries containing the data. The primary
        keys for the dict are the posid. Then for each posid, each subdictionary
        contains the keys:
            'target_posTP'    ... the posTP targets which were attempted
            'measured_obsXY'  ... the resulting measured xy positions
            'petal'           ... the petal this posid is on
            'trans'           ... the postransform object associated with this particular positioner
        """
        posids_by_petal = self.posids_by_petal(posids)
        data = {}
        for petal,these_posids in posids_by_petal.items():
            for posid in these_posids:
                data[posid] = {}
                posmodel = self.posmodel(posid)
                range_T = posmodel.targetable_range_T
                range_P = posmodel.targetable_range_P
                if keep_phi_within_Eo:
                    range_P[0] = self.phi_clear_angle
                t_cmd = np.linspace(min(range_T),max(range_T),self.n_points_calib_T + 1) # the +1 is temporary, remove that extra point in next line
                t_cmd = t_cmd[:-1] # since theta covers +/-180, it is kind of redundant to hit essentially the same points again
                p_cmd = np.linspace(min(range_P),max(range_P),self.n_points_calib_P + 1) # the +1 is temporary, remove that extra point in next line
                p_cmd = p_cmd[:-1] # since there is very little useful data right near the center
                data[posid]['target_posTP'] = [[t,p] for t in t_cmd for p in p_cmd]
                data[posid]['trans'] = posmodel.trans
                data[posid]['petal'] = petal
                data[posid]['measured_obsXY'] = []
                n_pts = len(data[posid]['target_posTP'])
        
        # make the measurements
        for i in range(n_pts):
            requests = {}
            for posid in data:
                requests[posid] = {'command':'posTP', 'target':data[posid]['target_posTP'][i], 'log_note':'calib grid point ' + str(i+1)}
            self.printfunc('calibration grid point ' + str(i+1) + ' of ' + str(n_pts))
            this_meas_data,imgfiles = self.move_measure(requests, tp_updates=None)
            for p in this_meas_data.keys():
                data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],this_meas_data[p])
        return data 

    def _measure_calibration_arc(self,posids='all',axis='theta',keep_phi_within_Eo=True):
        """Expert usage. Sweep an arc of points about axis ('theta' or 'phi')
        on positioners identified by posids. Measure these points with the FVC
        and do a best fit of them.

        INPUTS:   posids  ... list of posids or 'all'
                  axis    ... 'theta' or 'phi'

        keep_phi_within_Eo == True  --> phi never exceeds Eo envelope
        keep_phi_within_Eo == False --> phi can cover the full range (including collidable territory) during calibration

        OUTPUTS:  data ... see comments below

        Returns a dictionary of dictionaries containing the data. The primary
        keys for the dict are the posid. Then for each posid, each subdictionary
        contains the keys:
            'target_posTP'    ... the posTP targets which were attempted
            'measured_obsXY'  ... the resulting measured xy positions
            'xy_center'       ... the best fit arc's xy center
            'radius'          ... the best fit arc's radius
            'petal'           ... the petal this posid is on
            'trans'           ... the postransform object associated with this particular positioner
        """
        posids_by_petal = self.posids_by_petal(posids)
        phi_clear_angle = self.phi_clear_angle
        data = {}
        for petal,these_posids in posids_by_petal.items():
            posmodels = [self.posmodel(posid) for posid in these_posids]
            initial_tp = []
            final_tp = []
            if axis == 'theta':
                n_pts = self.n_points_calib_T
                for posmodel in posmodels:
                    targetable_range_T = posmodel.targetable_range_T
                    initial_tp = pc.concat_lists_of_lists(initial_tp, [min(targetable_range_T) + self.calib_arc_margin, phi_clear_angle])
                    final_tp   = pc.concat_lists_of_lists(final_tp,   [max(targetable_range_T) - self.calib_arc_margin, initial_tp[-1][1]])
            else:
                n_pts = self.n_points_calib_P
                for posmodel in posmodels:
                    if keep_phi_within_Eo:
                        phi_min = phi_clear_angle
                        theta = 0
                    else:
                        phi_min = min(posmodel.targetable_range_P)
                        theta = posmodel.trans.obsTP_to_posTP([0,0])[pc.T] # when doing phi axis, want obsT to all be uniform (simplifies anti-collision), which means have to figure out appropriate posT for each positioner -- depends on already knowing theta offset reasonably well
                    initial_tp = pc.concat_lists_of_lists(initial_tp, [theta, phi_min + self.calib_arc_margin])
                    final_tp   = pc.concat_lists_of_lists(final_tp,   [initial_tp[-1][0], max(posmodel.targetable_range_P) - self.calib_arc_margin])
            
            for i in range(len(these_posids)):
                t = np.linspace(initial_tp[i][0], final_tp[i][0], n_pts)
                p = np.linspace(initial_tp[i][1], final_tp[i][1], n_pts)
                data[these_posids[i]] = {'target_posTP':[[t[j],p[j]] for j in range(n_pts)], 'measured_obsXY':[], 'petal':petal, 'trans':posmodels[i].trans}

        # make the measurements
        for i in range(n_pts):
            requests = {}
            for posid in data:
                requests[posid] = {'command':'posTP', 'target':data[posid]['target_posTP'][i], 'log_note':'calib arc on ' + axis + ' point ' + str(i+1)}
            self.printfunc('calibration arc on ' + axis + ' axis: point ' + str(i+1) + ' of ' + str(n_pts))
            this_meas_data,imgfiles = self.move_measure(requests, tp_updates=None)
            for p in this_meas_data.keys():
                data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],this_meas_data[p])

        # circle fits
        for posid in data:
            (xy_ctr,radius) = fitcircle.FitCircle().fit(data[posid]['measured_obsXY'])
            data[posid]['xy_center'] = xy_ctr
            data[posid]['radius'] = radius
        
        return data

    def _measure_range_arc(self,posids='all',axis='theta'):
        """Expert usage. Measure physical range of an axis by sweep a brief arc of points
        on positioners identified bye unwrapped  posids. Measure these points with the FVC
        and do a best fit of them.

        INPUTS:   posids  ... list of posids or 'all'
                  axis    ... 'theta' or 'phi'

        Returns a dictionary of dictionaries containing the data. The primary
        keys for the dict are the posid. Then for each posid, each subdictionary
        contains the keys:
            'initial_posTP'   ... starting theta,phi position
            'target_dtdp'     ... delta moves which were attempted
            'measured_obsXY'  ... resulting measured xy positions
            'xy_center'       ... best fit arc's xy center
            'radius'          ... best fit arc's raTruedius
            'petal'           ... petal this posid is on
            'trans'           ... postransform object associated with this particular positioner
        """
        posids_by_petal = self.posids_by_petal(posids)
        phi_clear_angle = self.phi_clear_angle
        n_intermediate_pts = 2
        data = {}
        initial_tp_requests = {}
        for petal,these_posids in posids_by_petal.items():
            if axis == 'theta':
                delta = 360/(n_intermediate_pts + 1)
                dtdp = [delta,0]
                axisid = pc.T
                for posid in these_posids:
                    initial_tp = [-150, phi_clear_angle]
                    initial_tp_requests[posid] = {'command':'posTP', 'target':initial_tp, 'log_note':'range arc ' + axis + ' initial point'}
            else:
                delta = -180/(n_intermediate_pts + 1)
                dtdp = [0,delta]
                axisid = pc.P
                for posid in these_posids:
                    if self.use_current_theta_during_phi_range_meas:
                        theta_initial = petal.expected_current_position(posid,'obsT')
                    else:
                        theta_initial = 0
                    trans = self.trans(posid)
                    initial_tp = trans.obsTP_to_posTP([theta_initial,phi_clear_angle]) # when doing phi axis, want obsT to all be uniform (simplifies anti-collision), which means have to figure out appropriate posT for each positioner -- depends on already knowing theta offset reasonably well
                    initial_tp_requests[posid] = {'command':'posTP', 'target':initial_tp,  'log_note':'range arc ' + axis + ' initial point'}
            for i in range(len(these_posids)):
                data[these_posids[i]] = {'target_dtdp':dtdp, 'measured_obsXY':[], 'petal':petal}

        prefix = 'range measurement on ' + axis + ' axis'
        # go to initial point
        self.printfunc(prefix + ': initial point')
        self.move(initial_tp_requests)

        # seek first limit
        self.printfunc(prefix + ': seeking first limit')
        for petal,these_posids in posids_by_petal.items():
            petal.request_limit_seek(these_posids, axisid, -np.sign(delta), log_note='seeking first ' + axis + ' limit')
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal
        meas_data,imgfiles = self.measure()
        for p in meas_data.keys():
            data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],meas_data[p])

        # intermediate points
        for i in range(n_intermediate_pts):
            self.printfunc(prefix + ': intermediate point ' + str(i+1) + ' of ' + str(n_intermediate_pts))
            # Note that anticollision is NOT done here. The reason is that phi location is not perfectly
            # well-known at this point (having just struck a hard limit). So externally need to have made
            # sure there was a clear path for the phi arm ahead of time.
            for petal,these_posids in posids_by_petal.items():
                requests = {}
                for posid in these_posids:
                    requests[posid] = {'target':dtdp, 'log_note':'intermediate ' + axis + ' point ' + str(i)}
                petal.request_direct_dtdp(requests)
                petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal
            meas_data,imgfiles = self.measure()
            for p in meas_data.keys():
                data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],meas_data[p])

        # seek second limit
        self.printfunc(prefix + ': seeking second limit')
        for petal,these_posids in posids_by_petal.items():
            petal.request_limit_seek(these_posids, axisid, np.sign(delta), log_note='seeking second ' + axis + ' limit')
            petal.schedule_send_and_execute_moves()
        meas_data,imgfiles = self.measure()
        for p in meas_data.keys():
            data[p]['measured_obsXY'] = pc.concat_lists_of_lists(data[p]['measured_obsXY'],meas_data[p])

        # circle fits
        for posid in data:
            (xy_ctr,radius) = fitcircle.FitCircle().fit(data[posid]['measured_obsXY'])
            data[posid]['xy_center'] = xy_ctr

        # get phi axis well back in clear envelope, as a best practice housekeeping thing to do
        if axis == 'phi' and np.sign(delta) == -1:
            for petal,these_posids in posids_by_petal.items():
                petal.request_limit_seek(these_posids, axisid, -np.sign(delta), log_note='housekeeping extra ' + axis + ' limit seek')
                petal.schedule_send_and_execute_moves()

        return data

    def _calculate_and_set_arms_and_offsets_from_grid_data(self, data, set_gear_ratios=False):
        """Helper function for grid method of calibration. See the _measure_calibration_grid method for
        more information on format of the dictionary 'data'. This method adds the fields 'ERR_NORM' and
        'final_expected_obsXY' to the data dictionary for each positioner.
        """
        param_keys = self.grid_calib_param_keys
        for posid in data.keys():
            trans = data[posid]['trans']   
            trans.alt_override = True
            for key in param_keys:
                data[posid][key] = []
            data[posid]['ERR_NORM'] = []
            data[posid]['point_numbers'] = []
            initial_params_dict = postransforms.PosTransforms().alt
            params0 = [initial_params_dict[key] for key in param_keys]
            point0 = self.grid_calib_num_DOF - 1
            for pt in range(point0,len(data[posid]['measured_obsXY'])):
                meas_xy = np.array([data[posid]['measured_obsXY'][j] for j in range(pt+1)]).transpose()
                targ_tp = np.array([data[posid]['target_posTP'][j] for j in range(pt+1)]).transpose()
                def expected_xy(params):
                    for j in range(len(param_keys)):
                        trans.alt[param_keys[j]] = params[j]
                    return trans.posTP_to_obsXY(targ_tp.tolist())
                def err_norm(params):
                    expected = np.array(expected_xy(params))
                    all_err = expected - meas_xy
                    return np.linalg.norm(all_err,ord='fro')/np.sqrt(np.size(all_err,axis=1))
 
                bounds = ((2.5,3.5),(2.5,3.5),(-180,180),(-50,50),(None,None),(None,None)) #Ranges which values should be in
                params_optimized = scipy.optimize.minimize(fun=err_norm, x0=params0, bounds=bounds)
                params0 = params_optimized.x
                if pt > point0: # don't bother logging first point, which is always junk and just getting the (x,y) offset in the ballpark
                    data[posid]['ERR_NORM'].append(err_norm(params_optimized.x))
                    data[posid]['point_numbers'].append(pt+1)
                    debug_str = 'Grid calib on ' + str(posid) + ' point ' + str(data[posid]['point_numbers'][-1]) + ':'
                    debug_str += ' ERR_NORM=' + format(data[posid]['ERR_NORM'][-1],'.3f')
                    for j in range(len(param_keys)):
                        if param_keys[j] == 'OFFSET_T' or param_keys[j] == 'OFFSET_P':
                            params_optimized.x[j] = self._centralized_angular_offset_value(params_optimized.x[j])
                        data[posid][param_keys[j]].append(params_optimized.x[j])
                        debug_str += '  ' + param_keys[j] +': ' + format(data[posid][param_keys[j]][-1],'.3f')
                    # print(debug_str)
            trans.alt_override = False
            petal = data[posid]['petal']
            for key in param_keys:
                petal.set_posfid_val(posid, key, data[posid][key][-1])
                self.printfunc('Grid calib on ' + str(posid) + ': ' + key + ' set to ' + format(data[posid][key][-1],'.3f'))
            data[posid]['final_expected_obsXY'] = np.array(expected_xy(params_optimized.x)).transpose().tolist()
        return data

    def _calculate_and_set_arms_and_offsets_from_arc_data(self, T, P, set_gear_ratios=False):
        """Helper function for arc method of calibration. T and P are data dictionaries taken on the
        theta and phi axes. See the _measure_calibration_arc method for more information.
        """
        data = {}
        for posid in T.keys():
            # gather targets data
            t_targ_posT = [posTP[pc.T] for posTP in T[posid]['target_posTP']]
            t_targ_posP = [posTP[pc.P] for posTP in T[posid]['target_posTP']]
            p_targ_posP = [posTP[pc.P] for posTP in P[posid]['target_posTP']]
            p_targ_posT = [posTP[pc.T] for posTP in P[posid]['target_posTP']]        
            t_meas_obsXY = T[posid]['measured_obsXY']
            p_meas_obsXY = P[posid]['measured_obsXY']
            
            # arms and offsets
            ptl = T[posid]['petal']
            t_ctr = np.array(T[posid]['xy_center'])
            p_ctr = np.array(P[posid]['xy_center'])
            length_r1 = np.sqrt(np.sum((t_ctr - p_ctr)**2))
            length_r2 = P[posid]['radius']
            ptl.set_posfid_val(posid,'LENGTH_R1',length_r1)
            ptl.set_posfid_val(posid,'LENGTH_R2',length_r2)
            ptl.set_posfid_val(posid,'OFFSET_X',t_ctr[0])
            ptl.set_posfid_val(posid,'OFFSET_Y',t_ctr[1])
            p_meas_obsT = np.arctan2(p_ctr[1]-t_ctr[1], p_ctr[0]-t_ctr[0]) * 180/np.pi
            offset_t = p_meas_obsT - p_targ_posT[0] # just using the first target theta angle in the phi sweep
            offset_t = self._centralized_angular_offset_value(offset_t)
            ptl.set_posfid_val(posid,'OFFSET_T',offset_t)
            xy = np.array(p_meas_obsXY)
            angles = np.arctan2(xy[:,1]-p_ctr[1], xy[:,0]-p_ctr[0]) * 180/np.pi
            p_meas_obsP = angles - p_meas_obsT
            p_meas_obsP[p_meas_obsP < 0] += 360
            expected_direction = np.sign(p_targ_posP[1] - p_targ_posP[0])
            p_meas_obsP_wrapped = self._wrap_consecutive_angles(p_meas_obsP.tolist(), expected_direction)
            offset_p = np.median(np.array(p_meas_obsP_wrapped) - np.array(p_targ_posP))
            offset_p = self._centralized_angular_offset_value(offset_p)
            ptl.set_posfid_val(posid,'OFFSET_P',offset_p)
            p_meas_posP_wrapped = (np.array(p_meas_obsP_wrapped) - offset_p).tolist()
            
            # unwrap thetas
            t_meas_posTP = T[posid]['trans'].obsXY_to_posTP(np.transpose(t_meas_obsXY).tolist(),range_limits='full')[0]
            t_meas_posT = t_meas_posTP[pc.T]
            expected_direction = np.sign(t_targ_posT[1] - t_targ_posT[0])
            t_meas_posT_wrapped = self._wrap_consecutive_angles(t_meas_posT, expected_direction)
            
            # gather data to return in an organized fashion (used especially for plotting)
            data[posid] = {}
            data[posid]['xy_ctr_T'] = t_ctr
            data[posid]['xy_ctr_P'] = p_ctr
            data[posid]['radius_T'] = T[posid]['radius']
            data[posid]['radius_P'] = P[posid]['radius']
            data[posid]['measured_obsXY_T'] = t_meas_obsXY
            data[posid]['measured_obsXY_P'] = p_meas_obsXY
            data[posid]['targ_posT_during_T_sweep'] = t_targ_posT
            data[posid]['targ_posP_during_P_sweep'] = p_targ_posP
            data[posid]['meas_posT_during_T_sweep'] = t_meas_posT_wrapped
            data[posid]['meas_posP_during_P_sweep'] = p_meas_posP_wrapped
            data[posid]['targ_posP_during_T_sweep'] = t_targ_posP[0]
            data[posid]['targ_posT_during_P_sweep'] = p_targ_posT[0]
            data[posid]['posmodel'] = self.posmodel(posid)
            
            # gear ratios
            ratios_T = np.divide(np.diff(t_meas_posT_wrapped),np.diff(t_targ_posT))
            ratios_P = np.divide(np.diff(p_meas_posP_wrapped),np.diff(p_targ_posP))
            ratio_T = np.median(ratios_T)
            ratio_P = np.median(ratios_P)
            data[posid]['gear_ratio_T'] = ratio_T
            data[posid]['gear_ratio_P'] = ratio_P            
            if set_gear_ratios:
                ptl.set_posfid_val(posid,'GEAR_CALIB_T',ratio_T)
                ptl.set_posfid_val(posid,'GEAR_CALIB_P',ratio_P)
            else:
                self.printfunc(posid + ': measurement proposed GEAR_CALIB_T = ' + format(ratio_T,'.6f'))
                self.printfunc(posid + ': measurement proposed GEAR_CALIB_P = ' + format(ratio_P,'.6f'))
        return data

    def _identify(self, posid=None):
        """Generic function for identifying either all fiducials or a single positioner's location.
        """
        posids_by_petal = self.posids_by_petal('all')
        n_posids = len(self.all_posids)
        n_dots = n_posids + self.n_ref_dots
        nudges = [-self.nudge_dist, self.nudge_dist]
        xy_init = []
        pseudo_xy_ref = []
        for i in range(len(nudges)):
            dtdp = [0,nudges[i]]
            if posid == None:
                identify_fiducials = True
                log_note = 'nudge to identify fiducials '
                for petal,these_posids in posids_by_petal.items():
                    requests = {}
                    for p in these_posids:
                        if identify_fiducials or p == posid:
                            requests[p] = {'target':[0,nudges[i]], 'log_note':log_note}
                    petal.request_direct_dtdp(requests)
                    petal.schedule_send_and_execute_moves()
            else:
                identify_fiducials = False
                log_note = 'nudge to identify positioner location '
                request = {posid:{'target':dtdp, 'log_note':log_note}}
                this_petal = self.petal(posid)
                this_petal.request_direct_dtdp(request)
                this_petal.schedule_send_and_execute_moves()
            xy_meas,peaks,fwhms,imgfiles = self.fvc.measure_fvc_pixels(n_dots)
            if self.fvc.fvc_type == 'simulator':
                xy_meas = self._simulate_measured_pixel_locations(pseudo_xy_ref)
                pseudo_xy_ref = xy_meas[n_posids:]
            if i == 0:
                xy_init = xy_meas
            else:
                xy_test = xy_meas
        xy_ref = []
        for this_xy in xy_test:
            test_delta = np.array(this_xy) - np.array(xy_init)
            test_dist = np.sqrt(np.sum(test_delta**2,axis=1))
            if any(test_dist < self.ref_dist_tol):
                xy_ref.append(this_xy)
        xy_pos = [xy for xy in xy_test if xy not in xy_ref]
        if identify_fiducials:
            if len(xy_ref) != self.n_ref_dots:
                self.printfunc('warning: number of ref dots detected (' + str(len(xy_ref)) + ') is not equal to expected number of fiducial dots (' + str(self.n_ref_dots) + ')')
            all_xyref_detected = []
            for fidid in self.all_fidids:
                ptl = self.petal(fidid)
                num_expected = ptl.get_posfid_val(fidid,'N_DOTS')
                if num_expected > 0:
                    self.printfunc('Temporarily turning off fiducial ' + fidid + ' to determine which dots belonged to it.')
                    ptl.set_fiducials(fidid,'off')
                    xy_meas = self.fvc.measure_fvc_pixels(n_dots - num_expected)[0]
                    if self.fvc.fvc_type == 'simulator':
                        xy_meas = self._simulate_measured_pixel_locations(xy_ref)
                        for j in range(num_expected):
                            for k in range(n_posids,len(xy_meas)):
                                if xy_meas[k] not in all_xyref_detected:
                                    del xy_meas[k] # this is faking turning off that dot
                                    break
                    these_xyref = []
                    for this_xy in xy_ref:
                        test_delta = np.array(this_xy) - np.array(xy_meas)
                        test_dist = np.sqrt(np.sum(test_delta**2,axis=1))
                        matches = [dist < self.ref_dist_tol for dist in test_dist]
                        if not any(matches):
                            these_xyref.append(this_xy)
                            self.printfunc('Ref dot ' + str(len(these_xyref)-1) + ' identified for fiducial ' + fidid + ' at fvc coordinates ' + str(this_xy))
                    num_detected = len(these_xyref)
                    if num_detected != num_expected:
                        self.printfunc('warning: expected ' + str(num_expected) + ' dots for fiducial ' + fidid + ', but detected ' + str(num_detected))
                    ptl.set_posfid_val(fidid,'DOTS_FVC_X',[these_xyref[i][0] for i in range(num_detected)])
                    ptl.set_posfid_val(fidid,'DOTS_FVC_Y',[these_xyref[i][1] for i in range(num_detected)])
                    ptl.set_posfid_val(fidid,'LAST_MEAS_OBS_X',[these_xyref[i][0] for i in range(num_detected)])
                    ptl.set_posfid_val(fidid,'LAST_MEAS_OBS_Y',[these_xyref[i][1] for i in range(num_detected)])
                    all_xyref_detected += these_xyref
                    ptl.set_fiducials(fidid,'on')
            self.extradots_fvcXY = [xy for xy in xy_ref if xy not in all_xyref_detected]
            if self.extradots_fvcXY:
                self.printfunc(str(len(self.extradots_fvcXY)) + ' extra reference dots detected at FVC pixel coordinates: ' + str(self.extradots_fvcXY))
        else:
            if len(xy_pos) > 1:
                self.printfunc('warning: more than one moving dots (' + str(len(xy_pos)) + ') detected when trying to identify positioner ' + posid)
            elif len(xy_pos) < 1:
                self.printfunc('warning: no moving dots detected when trying to identify positioner ' + posid)
            else:
                expected_obsXY = this_petal.expected_current_position(posid,'obsXY')
                measured_obsXY = self.fvc.fvcXY_to_obsXY(xy_pos)[0]
                err_x = measured_obsXY[0] - expected_obsXY[0]
                err_y = measured_obsXY[1] - expected_obsXY[1]
                prev_offset_x = this_petal.get_posfid_val(posid,'OFFSET_X')
                prev_offset_y = this_petal.get_posfid_val(posid,'OFFSET_Y')
                this_petal.set_posfid_val(posid,'OFFSET_X', prev_offset_x + err_x) # this works, assuming we have already have reasonable knowledge of theta and phi (having re-homed or rough-calibrated)
                this_petal.set_posfid_val(posid,'OFFSET_Y', prev_offset_y + err_y) # this works, assuming we have already have reasonable knowledge of theta and phi (having re-homed or rough-calibrated)
                this_petal.set_posfid_val(posid,'LAST_MEAS_OBS_X',measured_obsXY[0])
                this_petal.set_posfid_val(posid,'LAST_MEAS_OBS_Y',measured_obsXY[1])

    def _simulate_measured_pixel_locations(self,xy_ref=[]):
        """Generates simulated locations in fvcXY space.
        Positioner locations are generated by simply looking up current expected positions.
        The optional argument xy_ref allows you to specify a list of [x,y] locations of
        reference points to repeat.
        """
        xy_meas = []
        posids_by_petal = self.posids_by_petal('all')
        for petal,these_posids in posids_by_petal.items():
            positioners_current = [petal.expected_current_position(posid,'obsXY') for posid in these_posids]
            positioners_current = self.fvc.obsXY_to_fvcXY(positioners_current)
            if len(positioners_current) > 1:
                i = 0
                while i < len(positioners_current):
                    this_xy = positioners_current[i]
                    other_xys = positioners_current.copy()
                    other_xys.remove(this_xy)
                    test_delta = np.array(this_xy) - np.array(other_xys)
                    test_dist = np.sqrt(np.sum(test_delta**2,axis=1))
                    matches = [dist < self.ref_dist_tol for dist in test_dist]
                    if any(matches):
                        this_xy[0] += self.ref_dist_tol*10*(i+1)
                        this_xy[1] += self.ref_dist_tol*10*(i+1)
                        positioners_current[i] = this_xy
                    i += 1
            xy_meas = pc.concat_lists_of_lists(xy_meas,positioners_current)
        if not xy_ref:
            for i in range(self.n_ref_dots):
                faraway = 2*np.max(np.abs(xy_meas))
                new_xy = np.random.uniform(low=faraway,high=2*faraway,size=2).tolist()
                xy_meas.append(new_xy)
        else:
            xy_meas.extend(xy_ref)
        return xy_meas

    def _test_and_update_TP(self,measured_data,tp_updates='posTP'):
        """Check if errors between measured positions and expected positions exceeds a tolerance
        value, and if so, then adjust parameters in the direction of the measured error.
        
        By default, this function will only changed the internally-tracked shaft position, POS_T
        and POS_P. The assumption is that we have fairly stable theta and phi offset values, based
        on the mechanical reality of the robot. However there is an option (perhaps useful in limited cases,
        such as when a calibration angle unwrap appears to have gone awry on a new test stand setup) where
        one would indeed want to change the calibration parameters, OFFSET_T and OFFSET_P. Activate
        this by arguing tp_updates='offsetsTP'.
        
        The overall idea here is to be able to deal gracefully with cases where the shaft has slipped
        just a little, and we have slightly lost count of shaft positions, or where the initial
        calibration was just a little off.
        
        The input value 'measured_data' is the same format as produced by the 'measure()' function.
        
        Any updating of parameters that occurs will be written to the move log. Check the notes field for
        a note like 'updated POS_T and POS_P after positioning error of 0.214 mm', to figure out when
        this has occurred.
        
        The return is a dictionary with:
            keys   ... posids 
            values ... 1x2 [delta_theta,delta_phi]
        """
        delta_TP = {}
        for posid in measured_data.keys():
            delta_TP[posid] = [0,0]
            ptl = self.petal(posid)
            measured_obsXY = measured_data[posid]
            expected_obsXY = ptl.expected_current_position(posid,'obsXY')
            err_xy = ((measured_obsXY[0]-expected_obsXY[0])**2 + (measured_obsXY[1]-expected_obsXY[1])**2)**0.5
            if err_xy > self.tp_updates_tol:
                posmodel = self.posmodel(posid)
                expected_posTP = ptl.expected_current_position(posid,'posTP')
                measured_posTP = posmodel.trans.obsXY_to_posTP(measured_data[posid],range_limits='full')[0]
                T_options = measured_posTP[0] + np.array([0,360,-360])
                T_diff = np.abs(T_options - expected_posTP[0])
                T_best = T_options[np.argmin(T_diff)]
                measured_posTP[0] = T_best
                delta_T = (measured_posTP[0] - expected_posTP[0]) * self.tp_updates_fraction
                delta_P = (measured_posTP[1] - expected_posTP[1]) * self.tp_updates_fraction
                if tp_updates == 'offsetsTP' or tp_updates == 'offsetsTP_close':
                    param = 'OFFSET'
                else:
                    param = 'POS'
                old_T = ptl.get_posfid_val(posid,param + '_T')
                old_P = ptl.get_posfid_val(posid,param + '_P')              
                new_T = old_T + delta_T
                new_P = old_P + delta_P
                if tp_updates == 'offsetsTP' or tp_updates == 'offsetsTP_close' :
                    ptl.set_posfid_val(posid,'OFFSET_T',new_T)
                    ptl.set_posfid_val(posid,'OFFSET_P',new_P)
                    self.printfunc(posid + ': Set OFFSET_T to ' + self.fmt(new_T))
                    self.printfunc(posid + ': Set OFFSET_P to ' + self.fmt(new_P))                    
                else:
                    posmodel.axis[pc.T].pos = new_T
                    posmodel.axis[pc.P].pos = new_P
                    self.printfunc(posid + ': xy err = ' + self.fmt(err_xy) + ', changed ' + param + '_T from ' + self.fmt(old_T) + ' to ' + self.fmt(new_T))
                    self.printfunc(posid + ': xy err = ' + self.fmt(err_xy) + ', changed ' + param + '_P from ' + self.fmt(old_P) + ' to ' + self.fmt(new_P))
                delta_TP[posid] = [delta_T,delta_P]
                posmodel.state.next_log_notes.append('updated ' + param + '_T and ' + param + '_P after positioning error of ' + self.fmt(err_xy) + ' mm')
        return delta_TP
                
    @property
    def phi_clear_angle(self):
        """Returns the phi angle in degrees for which two positioners cannot collide
        if they both have phi at this angle or greater.
        """
        phi_Eo_angle = self.petals[0].collider.Eo_phi
        phi_clear = phi_Eo_angle + self.phi_Eo_margin
        return phi_clear
        
    @property
    def grid_calib_num_DOF(self):
        return len(self.grid_calib_param_keys) # need at least this many points to exactly constrain the TP --> XY transformation function
    
    @property
    def grid_calib_num_constraints(self):
        return self.n_points_calib_T * self.n_points_calib_P

    @property
    def n_ref_dots(self):
        """Number of reference dots to expect in the field of view.
        """
        n_dots = 0
        for petal in self.petals:
            n_dots_ptl = petal.n_fiducial_dots
            n_dots += n_dots_ptl
        n_dots += self.n_extradots_expected
        return n_dots
    
    @property
    def n_moving_dots(self):
        """Returns the total number of mobile dots (on functioning positioners) to expect in an fvc image.
        """
        self.printfunc('n_moving_dots() method not yet implemented')
        pass
    
    @property
    def n_fixed_dots(self):
        """Returns the total number of immobile light dots (fiducials or non-functioning positioners) to expect in an fvc image.
        """
        self.printfunc('n_fixed_dots() method not yet implemented')
        pass
            
    def _wrap_consecutive_angles(self, angles, expected_direction):
        """Wrap angles in one expected direction. It is expected that the physical deltas
        we are trying to wrap all increase or all decrease sequentially. In other words, that
        the sequence of angles is only going one way around the circle.
        """
        wrapped = [angles[0]]
        for i in range(1,len(angles)):
            delta = angles[i] - wrapped[i-1]
            while np.sign(delta) != expected_direction and np.sign(delta) != 0:
                delta += expected_direction * 360
            wrapped.append(wrapped[-1] + delta)
        return wrapped
    
    def _centralized_angular_offset_value(self,offset_angle):
        """A special unwrapping check for OFFSET_T and OFFSET_P angles, for which we are always
        going to want to default to the option closer to 0 deg. Hence if our calibration routine
        calculates a best fit value for example of OFFSET_T or OFFSET_P = 351 deg, then the real
        setting we want to apply should clearly instead be -9.
        """
        try_plus = offset_angle % 360
        try_minus = offset_angle % -360
        if abs(try_plus) <= abs(try_minus):
            return try_plus
        else:
            return try_minus

    def fmt(self,number):
        """for consistently printing floats in terminal output
        """
        return format(number,'.3f')
