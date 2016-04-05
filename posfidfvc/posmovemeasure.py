class PosMoveMeasure(object):
    """Coordinates moving fiber positioners with fiber view camera measurements.
    """
    def __init__(self, petals, fvc):
        if not isinstance(petals,list):
            petals = [petals]
        self.petals = petals # list of petal objects
        self.fvc = fvc # fvchandler object
        self.n_fiducial_dots = 1
##        self.p = positioner_object  # positioner object; initialization
##        self.nom_xy_ref = []        # Nx2, nominal position(s) of reference fiber(s), [] means no ref fiber
##        self.nom_xy_ctr = [0,0]     # for user convenience, PosMoveMeasure can keep it's own xy offset value so user sees things in a "centered" coordinate system
##        self.n_ref_fibers = 1       # number of fixed reference fibers in FVC field of views
##        self.meas_unit_scale = 1    # multiply fvc units (i.e. pixels) by this value to get real lengths (e.g. mm)
##        self.ccd_angle = -90        # [deg] angle of CCD w.r.t. horizontal
##        self.initial_nudge_dist = 2 # [mm] when determining which is the moving fiber and which are refs
##        self.n_cycles = 0           # keeps count of non-tiny moves

    def fiducials_on(self):
        """Turn on all fiducials on all petals."""
        for petal in self.petals:
            petal.fiducials_on()

    def fiducials_off(self):
        """Turn off all fiducials on all petals."""
        for petal in self.petals:
            petal.fiducials_off()

    def measure(self):
        data = {'expected_xy':[], 'measured_xy':[], 'petal':[], 'id':[], 'is_pos':[], 'sub_ids':[]}
        for petal in self.petals:
            pos_ids = petal.pos.posids
            data['ids'].extend(pos_ids)
            data['petal'].extend([petal]*len(pos_ids))
            data['is_pos'].extend([True]*len(pos_ids))
            data['expected_xy'].extend(petal.pos.expected_current_position(pos_ids,'flatXY'))
            data['sub_ids'].extend(0)
            fid_ids = petal.fid.fid_ids
            for fid_id in fid_ids:
                fid_expected_XYs = petal.fid.expected_position(fid_id,'flatXY') # there may be multiple dots of light in a single fiducial
                n_dots = len(fid_expected_XYs)
                data['ids'].extend([fid_id]*n_dots)
                data['petal'].extend([petal]*n_dots)
                data['is_pos'].extend([False]*n_dots)
                data['expected_xy'].extend(fid_expected_XYs)
                data['sub_ids'].extend([i for i in range(0,n_dots)])
        data['measured_xy'] = self.fvc.measure_and_identify(data['expected_xy'], data['ids'], data['sub_ids'])
        for i in range(len(data['id'])):
            if data['is_pos'][i]:
                data['petal'][i].pos.set(data['id'][i],'LAST_MEAS_FLAT_X',data['measured_xy'][i][0])
                data['petal'][i].pos.set(data['id'][i],'LAST_MEAS_FLAT_Y',data['measured_xy'][i][1])
            else:
                data['petal'][i].fid.set_last_measured_position(data[id][i], data['measured_xy'][i], data['sub_ids'][i])

    def move_and_converge(self, pos_ids, targets, coordinates='QS', num_corr_max=2):
        """Move positioners to target coordinates, then make a series of correction
        moves in coordination with the fiber view camera, to converge.

        INPUTS:     pos_ids      ... list of positioner ids to move
                    targets      ... list of target coordinates of the form [[u1,v2],[u2,v2],...]
                    coordinates  ... 'QS' or 'XY', identifying the coordinate system the targets are in
                    num_corr_max ... maximum number of correction moves to perform on any positioner
        """
        pass

    def move_measure(self, pos_ids, commands, values):
        """Move positioners and measure output with FVC.

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
        self.measure()

    def rehome(self,pos_ids='all'):
        """Find hardstops and reset current known positions.
        INPUTS:     pos_ids ... 'all' or a list of specific pos_ids
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        for petal in pos_ids_by_ptl.keys():
            petal.request_homing(pos_ids_by_ptl[petal])
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal
        self.measure()

    def calibrate(self,pos_ids='all'):
        """Find hardstops, then sweep a circle of points about theta and phi to measure
        positioner center locations, R1 and R2 arm lengths, theta and phi offsets, and
        then set all these calibration values for each positioner.
        """
        self.rehome(pos_ids)
        self.measure_calibration_arc(pos_ids,'theta')
        self.measure_calibration_arc(pos_ids,'phi')

    def measure_calibration_arc(self,pos_ids='all',axis='theta'):
        """Expert usage. Sweep an arc of points about axis ('theta' or 'phi')
        on positioners identified by pos_ids. Measure these points with the FVC
        and calculate calibration values.
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        pass

    def measure_range(self,pos_ids='all',axis='theta'):
        """Expert usage. Sweep several points about axis ('theta' or 'phi') on
        positioners identified by pos_ids, striking the hard limits on either end.
        Calculate the total available travel range. Note that for axis='phi', the
        positioners must enter the collisionable zone, so the range seeking will
        occur in several successive stages.
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        pass

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
            pos_ids_by_ptl[petal] = petal.pos.get(these_pos_ids,key)
        return pos_ids_by_ptl

    def identify_fiducials(self):
        """Nudge positioners forward/back to determine which centroid dots are fiducials.
        """
        ref_dist_tol = 0.1 # mm
        nudge_dist = 10.0 # deg
        print('Nudging positioners to identify reference fiber(s).\n')
        print('Distance tol for identifying a fixed fiber is set to %g.\n',ref_dist_tol)
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        nudges = [nudge_dist, -nudge_dist]
        for petal in pos_ids_by_ptl.keys():
            pos_ids = pos_ids_by_ptl[petal]
            xy = []
            for i in range(len(nudges)):
                petal.request_direct_dtdp(pos_ids, [nudges[i],0], cmd_prefix='nudge to identify fiducials')
                petal.schedule_send_and_execute_moves()
                xy[i] = self.fvc.measure(self.n_fiducial_dots)
            xy_init = xy[0]
            xy_test = xy[1]
            xy_ref = []
            for i in range(len(xy_test)):
                test_delta = np.array(xy_test[i]) - np.array(xy_init)
                test_dist = np.sqrt(np.sum(test_delta**2,axis=1))
                if any(test_dist < ref_dist_tol):
                    xy_ref.append()




##    def identify_ref_fibers(self):
##        """
##        Nudge positioner forward/back to determine which fibers are reference fibers
##        """
##
##
##        self.p.move('abs_xy', 0, 0)
##        self.p.move('rel_dxdy', self.initial_nudge_dist, 0)
##        xy_init = self.measure_xy
##        self.p.move('rel_dxdy', -self.initial_nudge_dist, 0)
##        xy_test = self.measure_xy
##        xy_ref = []
##        for i in range(len(xy_test)): # MATLAB: for i = 1:size(xy_test,1)
##            #MATLAB: test_dist = sqrt(sum((ones(size(xy_test,1),1)*xy_test(i,:)-xy_init).^2,2));
##            test_dist = math.pow((np.ones(len(xy_test)) * xy_test[i,:] - xy_init),2) #syntax concern: xy_test[i,:]
##            test_dist = np.asarray(test_dist)
##            test_dist = np.sqrt(np.sum(test_dist,axis = 0)) #axis = 0 is col sum; axis = 1 is row sum
##            test_dist = test_dist.tolist()
##            if test_dist < ref_dist_tol: #MATLAB: if find(test_dist < ref_dist_tol)
##                xy_ref.append(xy_test[i,:]) #syntax concern: xy_test[i,:]
##                print('Refernece fiber detected at (x,y) = (%.3f,%.3f)\n', xy_test[i][0], xy_test[i][1]) #changed from: xy_test[i,0], xy_test[i,1]
##        self.nom_xy_ref = xy_ref
##        n_ref_fibers_found = len(xy_ref)
##        #MATLAB:
##            #if obj.n_ref_fibers ~= n_ref_fibers_found
##                #error('Detected %i reference fiber(s), but expected %i',n_ref_fibers_found,obj.n_ref_fibers);
##            #end
##        if self.n_ref_fibers == n_ref_fibers_found:
##            try:
##                pass
##            except ValueError:
##                print('Detected %i reference fiber(s), but expected %i', n_ref_fibers_found, self.n_ref_fibers)
##        self.n_ref_fibers = n_ref_fibers_found
##        return
##
##    def circle_meas(self, axis_idx, tp_initial, final, tp_between, n_points, note):
##        """
##        measure a circle of points over the positioning range
##            axis_idx     ... identifies whether to use theta (1) or phi (2)
##            tp_initial   ... abs theta phi to start at
##            final        ... abs ending value of the axis that's moving
##            tp_between   ... in between measurements return to this position. if empty, just go straight to next target
##            n_points     ... number of points to take
##            note         ... will be included in log entries for all moves
##
##            xy_ctr       ... best fit circle center
##            radius       ... best fit circle radius
##            xy_meas      ... the points that were measured
##            tp_abs_cmd   ... absolute tp of the points that were commanded to go to
##        """
##        #axis_idx is either 1 or 2
##        #MATLAB: switch/case code
##        if axis_idx == 1:
##            tp_cmd = [np.linspace(tp_initial[0], final, num = n_points).tolist(), (tp_initial[1] * np.ones(n_points)).tolist()]
##            axisname = 'theta'
##        elif axis_idx == 2:
##            tp_cmd = [(tp_initial[0] * np.ones(n_points)).tolist(), np.linspace(tp_initial[1], final, num = n_points).tolist()]
##            axisname = 'phi'
##        xy_meas = []
##        for i in range(n_points):
##            print('Measuring %s circle point %i of %i ...\n', axisname, i, n_points)
##            if tp_between:
##                self.move('abs_tp', tp_between[0], tp_between[1])
##            xy_meas.append(self.move_meas_sub_note('abs_tp', tp_cmd[i,0], tp_cmd[i,1], [], note))
##        xy_ctr, radius = fitcircle(xy_meas) #MATLAB: meas')
##        xy_ctr = xy_ctr #MATLAB = ctr'
##        return xy_ctr, radius, xy_meas, tp_cmd
##
##    def range_seek(self, axis_idx, note):
##        """
##        measure physical range of an axis
##        """
##        #axis_idx is either 1 or 2
##        #MATLAB: switch/case code
##        if axis_idx == 1:
##            range_val = self.p.axes.positioning_range_T
##            tp_initial = [min(range_val), min(self.p.axes.positioning_range_P)]
##            meas_axis = [1,0]
##            axisname = 'theta'
##        elif axis_idx == 2:
##            range_val = self.p.axes.positioning_range_P
##            tp_initial = [math.mean(self.p.axes.positioning_range_T), min(range_val)]
##            meas_axis = [0,1]
##            axisname = 'phi'
##        self.move('abs_tp',tp_initial[0],tp_initial[1])
##        print('Measuring %s min limit...\n', axisname)
##        xy = self.move_meas_sub_note('seek_limit', -meas_axis[0], -meas_axis[1], [], note)
##        old_allow_exceed_limits = self.p.state.kv('ALLOW_EXCEED_LIMITS')
##        self.p.state.kv('ALLOW_EXCEED_LIMITS') = 1 #python does not like this line; no others errors show until this is fixed
##        for i in range(2):
##            print('Measuring intermediate point %i of 2 during %s range seek...\n', i, axisname)
##            test_steps[i] = 0.4 * diff(range_val)
##            xy.append(self.move_meas_sub_note('rel_dtdp', test_steps[i] * meas_axis[0], test_steps[i] * meas_axis[1], [], note))
##        self.p.state.kv('ALLOW_EXCEED_LIMITS') = old_allow_exceed_limits
##        print('Measuring %s max limit...\n', axisname)
##        xy.append(self.move_meas_sub_note('seek_limit', meas_axis[0], meas_axis[1], [], note))
##        xy_ctr, radius = fitcircle(xy) #MATLAB: y')
##        #MATLAB: xy_ctr = xy_ctr' ..... \_O_/
##        '''unwrap and calculate range'''
##        test_steps[i+1] = diff(range_val) - sum(test_steps)
##        xy_centered[:,0] = xy[:,0] - xy_ctr[0] #might not be valid python syntax
##        xy_centered[:,1] = xy[:,1] - xy_ctr[1] #might not be valid python syntax
##        test_steps_abs = [tp_initial[axis_idx], tp_initial[axis_idx] + sum(test_steps)] #MATLAB: cumsum(test_steps)]'
##        a_meas = PosMoveMeasure.unwrapped_meas_angle(test_steps_abs, xy_centered)
##        meas_range = a_meas[-1] - a_meas[0]
##        return meas_range, xy_ctr, radius, xy
##
##    def stability_meas(self, n_meas):
##        """
##        repeated measurements without moving to determine stability
##        """
##        xy = []
##        xyref = []
##        for i in range(n_meas):
##            temp.xy, temp.xyref = self.measure_xy #not sure of the temp.__ name is kosher for python
##            xy.append(temp.xy)
##            xyref.append(temp.xyref)
##        return xy, xyref
##
##    """Static Methods"""
##    def multi_unwrapped_meas_angle(a_cmd, xy_meas, wrap_restart_idxs):
##        a_meas_unwrapped = []
##        for i in range(len(wrap_restart_idxs)):
##            if i == len(wrap_restart_idxs):
##                unwrap_range = range(wrap_restart_idxs[i], len[a_cmd]) #MATLAB: unwrap_range = wrap_restart_idxs(i):length(a_cmd); in python 3: list(range(#,#))
##            else:
##                unwrap_range = range(wrap_restart_idxs[i], (wrap_restart_idxs[i+1]-1))
##            a_meas_unwrapped.append(PosMoveMeasure.unwrapped_meas_angle(a_cmd[unwrap_range],xy_meas[unwrap_range,:]))
##        return a_meas_unwrapped
##
##    def unwrapped_meas_angle(a_cmd, xy_meas):
##        cmd_steps = np.diff(np.asarray(a_cmd), n = 1)
##        a = math.atan2(xy_meas[:,1],xy_meas[:,0]) #MATLAB: a = atan2d(xy_meas(:,2),xy_meas(:,1));
##        da = np.diff(np.asarray(a))
##        wrap_at_180 = list_compare(np.sign(cmd_steps).tolist(), np.sign(da).tolist())
##        for i in range(len(wrap_at_180)):
##            if wrap_at_180[i]:
##                da_options = [360 - da[i], 360 + da[i], da[i] - 360, da[i] + 360]
##                _, da_select = min(abs(da_options - cmd_steps[i]))
##                da[i] = da_options[da_select]
##        first_pt_wrap_cutoff = 340
##        if a[1] - a_cmd[1] > first_pt_wrap_cutoff: #checking for wrapping of first point
##            a[1] = a[1] - 360
##        elif a[1] - a_cmd[1] < -first_pt_wrap_cutoff:
##            a[1] = a[1] + 360
##        a_meas_unwrapped.append(a[1] + sum(da)) # MATLAB: a_meas_unwrapped = [a(1);a(1)+cumsum(da)];
##        return a_meas_unwrapped
##
##    def make_splinefit(cmd, meas, n_pieces, order):
##        if not n_pieces:
##            n_pieces = ceil(len(cmd)/order) #add better logic if technique proves generally useful
##        pp = splinefit(cmd, meas, n_pieces, order, 'r')
##        return pp
##
##
##
##
##
##
##
