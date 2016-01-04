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
        self.should_final_creep = True

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
        newrow = PosMoveRow(self.posmodel)
        self.rows.insert(index,newrow)
        if index > len(self.rows):
            self.insert_new_row(index) # to fill in any blanks up to index

    def append_new_row(self):
        self.insert_new_row(len(self.rows))

    def delete_row(self,index):
        del self.rows[index]

    def extend(self, other_move_table):
        for otherrow in other_move_table.rows:
            self.rows.append(otherrow.copy())

    # internal methods
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

        expected_prior_dTdP = [0,0]
        i = -1
        for row in self.rows:
            i += 1

            # for hardware type, insert an extra pause-only action if necessary, since hardware commands only really have postpauses
            if output_type == 'hardware' and row.data['prepause']:
                for key in ['motor_steps_T','motor_steps_P','move_time']:
                    table[key].insert(0,0)
                for key in ['speed_mode_T','speed_mode_P']:
                    table[key].insert(0,'creep') # speed mode doesn't matter here
                table['postpause'].insert(0,row.data['prepause'])

            # set move flags
            self._set_creep_after_cruise_flags()
            flags_T = {'allow_cruise':        row.data['allow_cruise'],
                       'creep_after_cruise':  row.data['creep_after_cruise_T'],
                        'allow_exceed_limits': row.data['allow_exceed_limits']}
            flags_P = {'allow_cruise':        row.data['allow_cruise'],
                        'creep_after_cruise':  row.data['creep_after_cruise_P'],
                        'allow_exceed_limits': row.data['allow_exceed_limits']}

            # use PosModel instance to get the real, quantized, calibrated values
            (true_move_T,extra_moves) = self.posmodel.true_move(pc.T, row.data['dT_ideal'], flags_T, expected_prior_dTdP)
            (true_move_P,extra_moves) = self.posmodel.true_move(pc.P, row.data['dP_ideal'], flags_P, expected_prior_dTdP)
            expected_prior_dTdP[0] += sum(true_move_T['obs_distance'])
            expected_prior_dTdP[1] += sum(true_move_P['obs_distance'])
            print('expected_prior:')
            print(expected_prior_dTdP)

            # where one of the axes has fewer or no moves, pad it with blank no-motion default values
            true_moves = [true_move_T,true_move_P]
            if len(true_moves[0]['motor_step']) > len(true_moves[1]['motor_step']):
                full = 0
                pad = 1
            elif len(true_moves[1]['motor_step']) > len(true_moves[0]['motor_step']):
                full = 1
                pad = 0
            else:
                full = 0
                pad = 0
            j = len(true_moves[pad]['motor_step'])
            full_length = len(true_moves[full]['motor_step'])
            while pad != full and j < full_length:
                for key in ['motor_step','move_time','obs_distance','obs_speed']:
                    true_moves[pad][key].append(0)
                true_moves[pad]['speed_mode'].append(true_moves[full]['speed_mode'][j])
                j = len(true_moves[pad]['motor_step'])

            # pad in pauses where new submoves have been added
            true_pauses = {'pre':[row.data['prepause']], 'post':[row.data['postpause']]}
            while len(true_pauses['pre']) < full_length:
                true_pauses['pre'].append(0)
            while len(true_pauses['post']) < full_length:
                true_pauses['post'].insert(0,0)

            # fill in the output table according to type
            if output_type == 'schedule' or output_type == 'cleanup':
                table['dT'].extend(true_move_T['obs_distance'])
                table['dP'].extend(true_move_P['obs_distance'])
            if output_type == 'schedule':
                table['Tdot'].extend(true_move_T['obs_speed'])
                table['Pdot'].extend(true_move_P['obs_speed'])
                table['prepause'].extend(true_pauses['pre'])
                table['postpause'].extend(true_pauses['post'])
            if output_type == 'hardware':
                table['motor_steps_T'].extend(true_move_T['motor_step'])
                table['motor_steps_P'].extend(true_move_P['motor_step'])
                table['speed_mode_T'].extend(true_move_T['speed_mode'])
                table['speed_mode_P'].extend(true_move_P['speed_mode'])
                table['postpause'].extend([round(x*1000) for x in true_pauses['post']]) # hardware postpause in integer milliseconds
            if output_type == 'schedule' or output_type == 'hardware':
                while true_move_T['move_time']: # while loop here, since there may be multiple submoves
                    time1 = true_move_T['move_time'].pop(0)
                    time2 = true_move_P['move_time'].pop(0)
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

    def _set_creep_after_cruise_flags(self):
        for row in self.rows():
            row.data['creep_after_cruise_T'] = False
            row.data['creep_after_cruise_P'] = False
        for row in reversed(self.rows):
            if row.data['allow_cruise'] and row.data['dT_ideal'] and self.should_final_creep:
                row.data['creep_after_cruise_T'] = True
                break
        for row in reversed(self.rows):
            if row.data['allow_cruise'] and row.data['dP_ideal'] and self.should_final_creep:
                row.data['creep_after_cruise_P'] = True
                break

class PosMoveRow(object):
    """The general user does not directly use the internal values of a
    PosMoveRow instance, but rather should rely on the higher level table
    formats that are exported by PosMoveTable.
    """

    def __init__(self,posmodel=None):
        self.data = {'dT_ideal'             : 0,        # [deg] ideal theta distance to move (as seen by external observer)
                     'dP_ideal'             : 0,        # [deg] ideal phi distance to move (as seen by external observer)
                     'prepause'             : 0,        # [sec] delay for this number of seconds before executing the move
                     'move_time'            : 0,        # [sec] time it takes the move to execute
                     'postpause'            : 0,        # [sec] delay for this number of seconds after the move has completed
                     'command'              : '',       # [string] command corresponding to this row
                     'cmd_val1'             : None,     # [-] command argument 1
                     'cmd_val2'             : None,     # [-] command argument 2
                     'cruise'         : True,     # [bool] whether any cruising allowed for this row
                     'creep_after_cruise_T' : False,    # [bool] whether to do a set of final fine creep moves for this row after cruising (if there is cruising)
                     'creep_after_cruise_P' : False,
                     'allow_exceed_limits'  : False,    # [bool] whether to allow moves greater than the software limits (i.e. for hardstop-finding)
                     'is_final_creep_row'   : False}

    def copy(self):
        return copymodule.deepcopy(self)

