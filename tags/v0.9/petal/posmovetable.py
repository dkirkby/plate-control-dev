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

    @property
    def full_table(self):
        """Version of the table with all data.
        """
        return self._for_output_type('full')

    # setters
    def set_move(self, rowidx, axisid, distance):
        """Put or update a move distance into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        dist_label = {pc.T:'dT_ideal', pc.P:'dP_ideal'}
        if rowidx >= len(self.rows):
            self.insert_new_row(rowidx)
        self.rows[rowidx].data[dist_label[axisid]] = distance

    def store_orig_command(self, rowidx, cmd_string, val1, val2):
        """To keep a copy of the original move command with the move table.
        """
        self.rows[rowidx].data['command']  = cmd_string
        self.rows[rowidx].data['cmd_val1'] = val1
        self.rows[rowidx].data['cmd_val2'] = val2

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
        has_moved = [False,False]
        for row in self.rows:
            ideal_dist = [row.data['dT_ideal'],row.data['dP_ideal']]
            for i in [pc.T,pc.P]:
                true_moves[i].append(self.posmodel.true_move(i, ideal_dist[i], self.allow_cruise, self.allow_exceed_limits, expected_prior_dTdP))
                expected_prior_dTdP[i] += true_moves[i][-1]['obs_distance']
                if true_moves[i][-1]['obs_distance']:
                    has_moved[i] = True
        if self.should_antibacklash and any(has_moved):
            backlash_dir = [self.posmodel.state.read('ANTIBACKLASH_FINAL_MOVE_DIR_T'), self.posmodel.state.read('ANTIBACKLASH_FINAL_MOVE_DIR_P')]
            backlash_mag = self.posmodel.state.read('BACKLASH')
            backlash = [0,0]
            for i in [pc.T,pc.P]:
                backlash[i] = -backlash_dir[i] * backlash_mag * has_moved[i]
                new_moves[i].append(self.posmodel.true_move(i, backlash[i], self.allow_cruise, self.allow_exceed_limits, expected_prior_dTdP))
                new_moves[i][-1]['command'] = '(auto backlash backup)'
                new_moves[i][-1]['cmd_val'] = backlash[i]
                expected_prior_dTdP[i] += new_moves[i][-1]['obs_distance']
        if self.should_final_creep or any(backlash):
            ideal_total = [0,0]
            ideal_total[pc.T] = sum([row.data['dT_ideal'] for row in self.rows])
            ideal_total[pc.P] = sum([row.data['dP_ideal'] for row in self.rows])
            err_dist = [0,0]
            for i in [pc.T,pc.P]:
                err_dist[i] = ideal_total[i] - expected_prior_dTdP[i]
                new_moves[i].append(self.posmodel.true_move(i, err_dist[i], False, self.allow_exceed_limits, expected_prior_dTdP))
                new_moves[i][-1]['command'] = '(auto final creep)'
                new_moves[i][-1]['cmd_val'] = err_dist[i]
                expected_prior_dTdP[i] += new_moves[i][-1]['obs_distance']
        self.rows_extra = []
        for i in range(len(new_moves[0])):
            self.rows_extra.append(PosMoveRow())
            self.rows_extra[i].data = {'dT_ideal'  : new_moves[pc.T][i]['obs_distance'],
                                       'dP_ideal'  : new_moves[pc.P][i]['obs_distance'],
                                       'prepause'  : 0,
                                       'move_time' : max(new_moves[pc.T][i]['move_time'],new_moves[pc.P][i]['move_time']),
                                       'postpause' : 0,
                                       'command'   : new_moves[pc.T][i]['command'],
                                       'cmd_val1'  : new_moves[pc.T][i]['cmd_val'],
                                       'cmd_val2'  : new_moves[pc.P][i]['cmd_val']}
        for i in [pc.T,pc.P]:
            true_and_new[i].extend(true_moves[i])
            true_and_new[i].extend(new_moves[i])
        return true_and_new

    def _for_output_type(self,output_type):
        # define the columns that will be filled in
        table = {'posid':'','nrows':0,'dT':[],'dP':[],'motor_steps_T':[],'motor_steps_P':[],
                 'Tdot':[],'Pdot':[],'speed_mode_T':[],'speed_mode_P':[],
                 'prepause':[],'move_time':[],'postpause':[],
                 'command':[],'cmd_val1':[],'cmd_val2':[]}
        if output_type == 'schedule':
            remove_keys = ['motor_steps_T','motor_steps_P','speed_mode_T','speed_mode_P','command','cmd_val1','cmd_val2']
        elif output_type == 'hardware':
            remove_keys = ['dT','dP','Tdot','Pdot','prepause','command','cmd_val1','cmd_val2']
        elif output_type == 'cleanup':
            remove_keys = ['motor_steps_T','motor_steps_P','speed_mode_T','speed_mode_P','Tdot','Pdot','prepause','postpause','move_time']
        elif output_type == 'full':
            remove_keys = []
        else:
            print( 'bad table output type ' + output_type)

        # calculate the true moves gather any new extra move rows
        true_moves = self._calculate_true_moves()
        rows = self.rows.copy()
        rows.extend(self.rows_extra)

        # format and populate the return tables
        for i in range(len(rows)):
            # for hardware type, insert an extra pause-only action if necessary, since hardware commands only really have postpauses
            if output_type == 'hardware' and rows[i].data['prepause']:
                for key in ['motor_steps_T','motor_steps_P','move_time']:
                    table[key].insert(0,0)
                for key in ['speed_mode_T','speed_mode_P']:
                    table[key].insert(0,'creep') # speed mode doesn't matter here
                table['postpause'].insert(0,rows[i].data['prepause'])

            table['dT'].append(true_moves[pc.T][i]['obs_distance'])
            table['dP'].append(true_moves[pc.P][i]['obs_distance'])
            table['Tdot'].append(true_moves[pc.T][i]['obs_speed'])
            table['Pdot'].append(true_moves[pc.P][i]['obs_speed'])
            table['prepause'].append(rows[i].data['prepause'])
            table['postpause'].append(rows[i].data['postpause'])
            table['motor_steps_T'].append(true_moves[pc.T][i]['motor_step'])
            table['motor_steps_P'].append(true_moves[pc.P][i]['motor_step'])
            table['postpause'].append(rows[i].data['postpause']*1000) # hardware postpause in integer milliseconds
            time1 = true_moves[pc.T][i]['move_time']
            time2 = true_moves[pc.P][i]['move_time']
            table['move_time'].append(max(time1,time2))
            table['command'].append(rows[i].data['command'])
            table['cmd_val1'].append(rows[i].data['cmd_val1'])
            table['cmd_val2'].append(rows[i].data['cmd_val2'])
            table['speed_mode_T'].append(true_moves[pc.T][i]['speed_mode'])
            table['speed_mode_P'].append(true_moves[pc.P][i]['speed_mode'])
        table['posid'] = self.posmodel.state.read('SERIAL_ID')
        table['nrows'] = len(table['dT'])
        table['stats'] = self._gather_stats(table)
        restricted_table = table.copy()
        for key in remove_keys:
            restricted_table.pop(key)
        return restricted_table

    def _gather_stats(self,table):
        stats = {'net_dT':[],'net_dP':[],'q':[],'s':[],'x':[],'y':[],'t':[],'p':[],
                 'TOTAL_CRUISE_MOVES_T':0,'TOTAL_CRUISE_MOVES_P':0,'TOTAL_CREEP_MOVES_T':0,'TOTAL_CREEP_MOVES_P':0}
        pos = self.posmodel.expected_current_position
        for i in range(table['nrows']):
            stats['net_dT'].append(table['dT'][i])
            stats['net_dP'].append(table['dP'][i])
            if i > 0:
                stats['net_dT'][i] += stats['net_dT'][i-1]
                stats['net_dP'][i] += stats['net_dP'][i-1]
            stats['t'].append(pos['obsT'] + stats['net_dT'][i])
            stats['p'].append(pos['obsP'] + stats['net_dP'][i])
            stats['TOTAL_CRUISE_MOVES_T'] += 1 * (table['speed_mode_T'][i] == 'cruise')
            stats['TOTAL_CRUISE_MOVES_P'] += 1 * (table['speed_mode_P'][i] == 'cruise')
            stats['TOTAL_CREEP_MOVES_T'] += 1 * (table['speed_mode_T'][i] == 'creep')
            stats['TOTAL_CREEP_MOVES_P'] += 1 * (table['speed_mode_P'][i] == 'creep')
        shaftTP = self.posmodel.trans.shaftTP_to_obsTP([stats['t'],stats['p']])
        obsXY = self.posmodel.trans.shaftTP_to_obsXY(shaftTP)
        stats['x'] = obsXY[0]
        stats['y'] = obsXY[1]
        QS = self.posmodel.trans.obsXY_to_QS(obsXY)
        stats['q'] = QS[0]
        stats['s'] = QS[1]
        return stats

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

