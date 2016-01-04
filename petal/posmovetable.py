import posmodel
import posconstants as pc
import copy as copymodule

class PosMoveTable(object):
    """A move table contains the information for a single positioner's move
    sequence, in both axes. This object defines the move table structure, and
    presents functions to view or convert the data in the several formats
    required through the move scheduling pipeline.

    The internal representation of the table data should not be directly accessed
    or modified, since there is some extra logic associated with correctly
    appending, inserting, validating, etc. Use the provided setters / getters
    instead.
    """

    def __init__(self, posmodel=None):
        if not(posmodel):
            posmodel = posmodel.PosModel()
        self.posmodel = posmodel         # the particular positioner this table applies to
        self.rows = []                   # internal representation of the move data
        self.rows_extra = []             # auto-generated backlash and final creep rows get stored here
        self.should_antibacklash = self.posmodel.state.read('ANTIBACKLASH_ON')
        self.should_final_creep  = self.posmodel.state.read('FINAL_CREEP_ON')
        self.allow_exceed_limits = self.posmodel.state.read('ALLOW_EXCEED_LIMITS')
        self.allow_cruise = not(self.posmodel.state.read('ONLY_CREEP'))

    # getters
    @property
    def for_schedule(self):
        """Version of the table suitable for move scheduling.
        Distances are given at the output shafts, in degrees.
        Times are given in seconds.
        """
        return self._for_output_type('schedule')

    @property
    def for_hardware(self):
        """Version of the table suitable for the hardware side.
        Distances are given at the motor shafts, in discrete steps.
        Times are given in milliseconds.
        """
        return self._for_output_type('hardware')

    @property
    def for_cleanup(self):
        """Version of the table suitable for updating the software internal
        position tracking after the physical move has been performed.
        """
        return self._for_output_type('cleanup')

    # setters
    def set_move(self, rowidx, axisid, distance):
        """Put or update a move distance into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        dist_label = {pc.T:'dT_ideal', pc.P:'dP_ideal'}
        if rowidx >= len(self.rows):
            self.insert_new_row(rowidx)
        for key in self.rows[rowidx]._move_options.keys():
            self.rows[rowidx]._move_options[key] = self.posmodel.state.read(key)  # snapshot the current state
        self.rows[rowidx].data[dist_label[axisid]] = distance

    def store_orig_command(self, rowidx, cmd_string, val1, val2):
        """To keep a copy of the original move command with the move table.
        """
        self.rows[rowidx].data['command'] = cmd_string
        self.rows[rowidx].data['val1']    = val1
        self.rows[rowidx].data['val2']    = val2

    def set_prepause(self, rowidx, prepause):
        """Put or update a prepause into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        if rowidx >= len(self.rows):
            self.insert_new_row(rowidx)
        self.rows[rowidx].data['prepause'] = prepause

    def set_postpause(self, rowidx, postpause):
        """Put or update a postpause into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        if rowidx >= len(self.rows):
            self.insert_new_row(rowidx)
        self.rows[rowidx].data['postpause'] = postpause

    # row manipulations
    def insert_new_row(self,index):
        newrow = PosMoveRow()
        self.rows.insert(index,newrow)
        if index > len(self.rows):
            self.insert_new_row(index) # to fill in any blanks up to index

    def delete_row(self,index):
        del self.rows[index]

    def extend(self, other_move_table):
        """Extend one move table with another.
        Flags for antibacklash and creep settings are inherited from other_move_table.
        """
        for otherrow in other_move_table.rows:
            self.rows.append(otherrow.copy())
        self.should_antibacklash = other_move_table.should_antibacklash
        self.should_final_creep  = other_move_table.should_final_creep
        self.allow_exceed_limits = other_move_table.allow_exceed_limits
        self.allow_cruise        = other_move_table.allow_cruise

    # internal methods
    def _calculate_true_moves(self):
        """Uses PosModel instance to get the real, quantized, calibrated values.
        Anti-backlash and final creep moves are added as necessary.
        """
        expected_prior_dTdP = [0,0]
        true_moves = [[],[]]
        new_moves = [[],[]]
        true_and_new = [[],[]]
        for row in self.rows:
            true_moves[pc.T] += self.posmodel.true_move(pc.T, row.data['dT_ideal'], self.allow_cruise, self.allow_exceed_limits, expected_prior_dTdP)
            true_moves[pc.P] += self.posmodel.true_move(pc.P, row.data['dP_ideal'], self.allow_cruise, self.allow_exceed_limits, expected_prior_dTdP)
            expected_prior_dTdP[pc.T] += true_moves[pc.T][-1]['obs_distance']
            expected_prior_dTdP[pc.P] += true_moves[pc.P][-1]['obs_distance']
        if self.should_antibacklash and any(expected_prior_dTdP):
            backlash_dir = [self.posmodel.state.read('ANTIBACKLASH_FINAL_MOVE_DIR_T'), self.posmodel.state.read('ANTIBACKLASH_FINAL_MOVE_DIR_P')]
            backlash_mag = self.posmodel.state.read('BACKLASH')
            backlash = [0,0]
            for i in [pc.T,pc.P]:
                backlash[i] = -backlash_dir[i] * backlash_mag * any(expected_prior_dTdP[i])
                new_moves[i] += self.posmodel.true_move(i, backlash[i], self.allow_cruise, self.allow_exceed_limits, expected_prior_dTdP)
                new_moves[i][-1]['command'] = '(auto backlash backup)'
                new_moves[i][-1]['cmd_val'+str(i+1)] = backlash[i]
                expected_prior_dTdP[i] += new_moves[i][-1]['obs_distance']
        if self.should_final_creep or any(backlash):
            ideal_total[pc.T] = sum([row.data['dT_ideal'] for row in self.rows])
            ideal_total[pc.P] = sum([row.data['dP_ideal'] for row in self.rows])
            err_dist = [0,0]
            for i in [pc.T,pcP]:
                err_dist[i] = ideal_total[i] - expected_prior_dTdP[i]
                new_moves[i] += self.posmodel.true_move(i, err_dist[i], False, self.allow_exceed_limits, expected_prior_dTdP)
                new_moves[i][-1]['command'] = '(auto final creep)'
                new_moves[i][-1]['cmd_val'+str(i+1)] = err_dist[i]
                expected_prior_dTdP[i] += new_moves[i][-1]['obs_distance']
        self.rows_extra = []
        for i in range(len(new_moves[0])):
            self.rows_extra += PosMoveRow()
            self.rows_extra[i].data = {'dT_ideal'  : new_moves[pc.T][i]['obs_distance'],
                                       'dP_ideal'  : new_moves[pc.P][i]['obs_distance'],
                                       'prepause'  : 0,
                                       'move_time' : max(new_moves[pc.T][i]['move_time'],new_moves[pc.P][i]['move_time']),
                                       'postpause' : 0,
                                       'command'   : new_moves[pc.P][i]['command'],
                                       'cmd_val1'  : new_moves[pc.P][i]['cmd_val1'],
                                       'cmd_val2'  : new_moves[pc.P][i]['cmd_val1']}
        for i in [pc.T,pc.P]:
            true_and_new[i] += true_moves[i]
            true_and_new[i] += new_moves[i]
        return true_and_new

    def _for_output_type(self,output_type):
        # define the columns that will be filled in
        if output_type == 'schedule':
            table = {'posid':'','nrows':0,'dT':[],'dP':[],'Tdot':[],'Pdot':[],'prepause':[],'move_time':[],'postpause':[]}
        elif output_type == 'hardware':
            table = {'posid':'','nrows':0,'motor_steps_T':[],'motor_steps_P':[],'speed_mode_T':[],'speed_mode_P':[],'move_time':[],'postpause':[]}
        elif output_type == 'cleanup':
            table = {'posid':'','nrows':0,'dT':[],'dP':[],'cmd':[],'cmd_val1':[],'cmd_val2':[]}
        else:
            print( 'bad table output type ' + output_type)

        # calculate the true moves gather any new extra move rows
        true_moves = self._calculate_true_moves()
        rows = [self.rows, self.rows_extra]

        # format and populate the return tables
        for i in range(len(true_moves)):
            row = self.rows[i]

            # for hardware type, insert an extra pause-only action if necessary, since hardware commands only really have postpauses
            if output_type == 'hardware' and row.data['prepause']:
                for key in ['motor_steps_T','motor_steps_P','move_time']:
                    table[key].insert(0,0)
                for key in ['speed_mode_T','speed_mode_P']:
                    table[key].insert(0,'creep') # speed mode doesn't matter here
                table['postpause'].insert(0,row.data['prepause'])

            # fill in the output table according to type
            if output_type == 'schedule' or output_type == 'cleanup':
                table['dT'].extend(true_moves[pc.T][i]['obs_distance'])
                table['dP'].extend(true_moves[pc.P][i]['obs_distance'])
            if output_type == 'schedule':
                table['Tdot'].extend(true_moves[pc.T][i]['obs_speed'])
                table['Pdot'].extend(true_moves[pc.P][i]['obs_speed'])
                table['prepause'].extend(true_pauses['pre'])
                table['postpause'].extend(true_pauses['post'])
            if output_type == 'hardware':
                table['motor_steps_T'].extend(true_moves[pc.T][i]['motor_step'])
                table['motor_steps_P'].extend(true_moves[pc.P][i]['motor_step'])
                table['speed_mode_T'].extend(true_moves[pc.T][i]['speed_mode'])
                table['speed_mode_P'].extend(true_moves[pc.P][i]['speed_mode'])
                table['postpause'].extend([round(x*1000) for x in true_pauses['post']]) # hardware postpause in integer milliseconds
            if output_type == 'schedule' or output_type == 'hardware':
                while true_moves[pc.T][i]['move_time']: # while loop here, since there may be multiple submoves
                    time1 = true_moves[pc.T][i]['move_time'].pop(0)
                    time2 = true_moves[pc.P][i]['move_time'].pop(0)
                    table['move_time'].append(max(time1,time2))
            if output_type == 'cleanup':
                table['cmd'].append(row.data['command'])
                table['cmd_val1'].append(row.data['val1'])
                table['cmd_val2'].append(row.data['val2'])
        table['posid'] = self.posmodel.state.read('SERIAL_ID')
        if output_type == 'schedule' or output_type == 'cleanup':
            table['nrows'] = len(table['dT'])
        if output_type == 'hardware':
            table['nrows'] = len(table['motor_steps_T'])
        return table

class PosMoveRow(object):
    """The general user does not directly use the internal values of a
    PosMoveRow instance, but rather should rely on the higher level table
    formats that are exported by PosMoveTable.
    """
    def __init__(self):
        self.data = {'dT_ideal'             : 0,         # [deg] ideal theta distance to move (as seen by external observer)
                     'dP_ideal'             : 0,         # [deg] ideal phi distance to move (as seen by external observer)
                     'prepause'             : 0,         # [sec] delay for this number of seconds before executing the move
                     'move_time'            : 0,         # [sec] time it takes the move to execute
                     'postpause'            : 0,         # [sec] delay for this number of seconds after the move has completed
                     'command'              : '',        # [string] command corresponding to this row
                     'cmd_val1'             : None,      # [-] command argument 1
                     'cmd_val2'             : None}      # [-] command argument 2

    def copy(self):
        return copymodule.deepcopy(self)

