import os
import sys
sys.path.append(os.path.abspath('../petal/'))
import postransforms

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
        self.trans = postransforms.PosTransforms() # generic coordinate transformations object

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
        return self.measure()

    def rehome(self,pos_ids='all'):
        """Find hardstops and reset current known positions.
        INPUTS:     pos_ids ... 'all' or a list of specific pos_ids
        """
        pos_ids_by_ptl = self.pos_data_listed_by_ptl(pos_ids,'POS_ID')
        for petal in pos_ids_by_ptl.keys():
            petal.request_homing(pos_ids_by_ptl[petal])
            petal.schedule_send_and_execute_moves() # in future, do this in a different thread for each petal

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