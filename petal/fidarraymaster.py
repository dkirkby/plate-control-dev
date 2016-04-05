import petalcomm
import postransforms
import time

class FidArrayMaster(object):
    """Maintains a list of fiducials and provides the functions to control them.

    initialize with:
        fid_ids ... list of fiducial unique id strings
        comm    ... petalcomm communication object
    """
    def __init__(self, fid_ids, comm):
        self.comm = comm
        self.fid_states = []
        for fid_id in fid_ids:
            state = posstate.PosState(fid_id, logging=True, type='fid')
            self.fid_states.append(state)
        self.fid_ids = fid_ids
        self.trans = postransforms.PosTransforms() # generic coordinate transforms object

    def all_on(self):
        """Turn all fiducials on at their default settings.
        """
        if not self.fid_states:
            return # case where no fiducials have been initialized
        duty_percents = []
        duty_periods = []
        for state in self.fid_states:
            duty_percents.append(state.read('DEFAULT_DUTY_PERCENT'))
            duty_periods.append(state.read('DEFAULT_DUTY_PERIOD'))
        self.set(self.fid_ids, duty_percents, duty_periods)

    def all_off(self):
        """Turn all fiducials off.
        """
        if not self.fid_states:
            return # case where no fiducials have been initialized
        duty_percents = [0]*len(can_ids)
        duty_periods = []
        for state in self.fid_states:
            duty_periods.append(state.read('DEFAULT_DUTY_PERIOD'))
        self.set(self.fid_ids, duty_percents, duty_periods)

    def set_illum_parameters(self, fid_ids, duty_percents, duty_periods):
        """Set illumination settings for a list of fiducials. Input lists of
        corresponding lengths for duty_percents and duty_periods.
        """
        if not self.fid_states:
            return # case where no fiducials have been initialized
        states = [None]*len(fid_ids)
        for state in self.fid_states:
            fid_id = state.read('FID_ID')
            if fid_id in fid_ids:
                idx = fid_ids.index()
                states[idx] = state
        can_ids = []
        for i in range(len(states)):
            s = states[i]
            can_ids.append(s.read('CAN_ID'))
            if duty_percents[i] != 0 and s.read('DUTY_PERCENT') == 0:
                s.write('TOTAL_TURN_ONS', 1 + s.read('TOTAL_TURN_ONS'))
                s.write('START_TIME_ON', time.time())
            if duty_percents[i] == 0 and s.read('DUTY_PERCENT') != 0:
                this_time_on = time.time() - s.read('START_TIME_ON')
                s.write('TOTAL_ON_TIME', this_time_on + s.read('TOTAL_ON_TIME'))
                s.write('START_TIME_ON', 0)
            s.write('DUTY_PERCENT', duty_percents[i])
            s.write('DUTY_PERIOD', duty_periods[i])
        self.comm.set_fiducials(can_ids, duty_percents, duty_periods)

    def expected_position(self, fid_ids='all', coordinates='flatXY'):
        """Get expected xy positions of fiducials.
        INPUT:  fid_ids      ... list of fiducial ids or 'all'
                coordinates  ... 'QS' or 'flatXY'
        """
        if fid_ids == 'all':
            fid_ids = self.fid_ids
        vals = []
        for fid_id in fid_ids:
            i = fid_ids.index(fid_id)
            for j in range(0,self.fid_state[i].read('N_DOTS')):
                x = self.fid_states[i].read('EXPECTED_FLAT_X' + str(j))
                y = self.fid_states[i].read('EXPECTED_FLAT_Y' + str(j))
                vals.append([x,y])
        if coordinates == 'QS':
            for i in range(len(vals)):
                vals[i] = trans.flatXY_to_QS(vals[i])
        return vals

    def set_expected_position(self, fid_id, flatXY, sub_id):
        """Set expected position of dot identified by sub_id in positioner identified
        by fid_id.
        """
        if fid_id in self.fid_ids:
            idx = self.fid_ids.index(fid_id)
            self.fid_states[idx].write('EXPECTED_FLAT_X' + str(sub_id), flatXY[0])
            self.fid_states[idx].write('EXPECTED_FLAT_Y' + str(sub_id), flatXY[1])

    def set_last_measured_position(self, fid_id, flatXY, sub_id):
        """Set last measured position of dot identified by sub_id in positioner identified
        by fid_id.
        """
        if fid_id in self.fid_ids:
            idx = self.fid_ids.index(fid_id)
            self.fid_states[idx].write('LAST_MEAS_FLAT_X' + str(sub_id), flatXY[0])
            self.fid_states[idx].write('LAST_MEAS_FLAT_Y' + str(sub_id), flatXY[1])