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

    The initial starting position (in positioner local [theta,phi] coordinates)
    of the move table may be specified upon initialization (1x2 list). If it is
    not provided, then the move table will automatically look up the current
    expected position from the posmodel's state object.
    """

    def __init__(self, this_posmodel=None, init_posintTP=None):
        if not(this_posmodel):
            this_posmodel = posmodel.PosModel()
        self.posmodel = this_posmodel    # the particular positioner this table applies to
        self.posid = self.posmodel.posid # the string ID number of the positioner this table applies to
        self._log_note = ''              # optional note string which user can associate with this table, to be stored in any logging
        self.rows = []                   # internal representation of the move data
        self._rows_extra = []            # auto-generated backlash and final creep rows get internally stored here
        if init_posintTP:
            self.init_posintTP = init_posintTP  # initial [theta,phi] position (positioner local coordinates)
        else:
            self.init_posintTP = self.posmodel.expected_current_posintTP
        self.init_poslocTP = self.posmodel.trans.posintTP_to_poslocTP(
            self.init_posintTP)  # initial theta, phi position (in petal CS)
        self.should_antibacklash = self.posmodel.state._val['ANTIBACKLASH_ON']
        self.should_final_creep  = self.posmodel.state._val['FINAL_CREEP_ON']
        self.allow_exceed_limits = self.posmodel.state._val['ALLOW_EXCEED_LIMITS']
        self.allow_cruise = not(self.posmodel.state._val['ONLY_CREEP'])
        self._postmove_cleanup_cmds = {pc.T: '', pc.P: ''}
        self._orig_command = ''

    def as_dict(self):
        """Returns a dictionary containing copies of all the table data."""
        c = self.copy()
        d = {'posid':                 c.posid,
             'log_note':              c.log_note,
             'rows':                  c.rows,
             '_rows_extra':           c._rows_extra,
             'init_posintTP':         c.init_posintTP,
             'init_poslocTP':         c.init_poslocTP,
             'should_antibacklash':   c.should_antibacklash,
             'should_final_creep':    c.should_final_creep,
             'allow_exceed_limits':   c.allow_exceed_limits,
             'allow_cruise':          c.allow_cruise,
             'postmove_cleanup_cmds': c._postmove_cleanup_cmds,
             }
        return d
    
    def __repr__(self):
        return str(self.as_dict())

    def __str__(self):
        return str(self.as_dict())
        
    def display(self,printfunc=print,show_posid=True):
        def fmt(x):
            if x == None:
                x = str(x)
            if type(x) == str:
                return format(x,'>11s')
            elif type(x) == int or type(x) == float:
                return format(x,'>11g')
        output = '  move table for: ' + str(self.posid) + '\n' if show_posid else ''
        output += '  Initial posintTP: ' + str(self.init_posintTP) + '\n'
        output += '  Initial poslocTP: ' + str(self.init_poslocTP) + '\n'
        for axisid, cmd_str in self._postmove_cleanup_cmds.items():
            output += f'  Axis {axisid} postmove cmds: {repr(cmd_str)}\n'
        if self.rows or self._rows_extra:
            output += fmt('row_type')
            headers = PosMoveRow().data.keys()
            for header in headers:
                output += fmt(header)
            for row in self.rows:
                output += '\n' + fmt('normal')
                for header in headers:
                    output += fmt(row.data[header])
            for extra_row in self._rows_extra:
                output += '\n' + fmt('extra')
                for header in headers:
                    output += fmt(extra_row.data[header])
        else:
            output += ' (empty: contains no row data)'
        printfunc(output)

    def copy(self):
        new = copymodule.copy(self) # intentionally shallow, then will deep-copy just the row instances as needed below
        new.rows = [row.copy() for row in self.rows]
        new._rows_extra = [row.copy() for row in self._rows_extra]
        return new

    # getters
    def for_schedule(self, suppress_any_finalcreep_and_antibacklash=True, _output_type='schedule'):
        """Version of the table suitable for move scheduling. Distances are given at
        the output shafts, in degrees. Times are given in seconds.

        An option is provided to select whether final creep and antibacklash
        moves should be suppressed from the schedule-formatted output table.
        Typically this option is left as True, since margin space for these moves
        is included in the geometric envelope of the positioner.
        """
        if suppress_any_finalcreep_and_antibacklash:
            old_finalcreep = self.should_final_creep
            old_antibacklash = self.should_antibacklash
            self.should_final_creep = False
            self.should_antibacklash = False
        output = self._for_output_type(_output_type)
        if suppress_any_finalcreep_and_antibacklash:
            self.should_final_creep = old_finalcreep
            self.should_antibacklash = old_antibacklash
        return output

    def for_collider(self):
        """Version of the table that is same as for_schedule, except with reduced
        amount of data returned (only what the poscollider requires and no more.)
        """
        return self.for_schedule(_output_type='collider')

    def for_hardware(self):
        """Version of the table suitable for the hardware side.
        Distances are given at the motor shafts, in discrete steps.
        Times are given in milliseconds.
        """
        return self._for_output_type('hardware')

    def for_cleanup(self):
        """Version of the table suitable for updating the software internal
        position tracking after the physical move has been performed.
        """
        return self._for_output_type('cleanup')

    def full_table(self):
        """Version of the table with all data.
        """
        return self._for_output_type('full')

    @property
    def n_rows(self):
        """Number of rows in table.
        """
        return len(self.rows)

    @property
    def is_motionless(self):
        """Boolean saying whether the move table contains no motion at all, on
        neither the theta nor phi axis, in any row.
        """
        for row in self.rows:
            if row.data['dP_ideal'] or row.data['dT_ideal']:
                return False
        return True
    
    @property
    def log_note(self):
        '''Returns a copy of property log_note.'''
        return self._log_note
    
    @log_note.setter
    def log_note(self, note):
        '''Sets property log_note. The argument will be converted to str.'''
        self._log_note = str(note)

    def append_log_note(self, note):
        '''Appends a note to the current log_note.'''
        self._log_note = pc.join_notes(self._log_note, note)

    # setters
    def set_move(self, rowidx, axisid, distance):
        """Put or update a move distance into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        dist_label = {pc.T:'dT_ideal', pc.P:'dP_ideal'}
        if rowidx >= len(self.rows):
            self.insert_new_row(rowidx)
        self.rows[rowidx].data[dist_label[axisid]] = distance

    def store_orig_command(self, string, val1=None, val2=None):
        '''To keep a note of original move command associated with this move
        table. If any such notes already exist, the action is like an append.
        args val1 and val2 are optional, and are intended to represent a pair
        of coordinates.
        '''
        if val1 != None or val2 != None:
            string = f'{string}=[{val1}, {val2}]'
        self._orig_command = pc.join_notes(self._orig_command, string)
        
    def append_postmove_cleanup_cmd(self, axisid, cmd_str):
        """Add a posmodel cleanup command for execution after the move has
        been completed.
        """
        if cmd_str:
            separator = '\n'
            existing = self._postmove_cleanup_cmds[axisid]
            if existing and existing[-1] != separator:
                self._postmove_cleanup_cmds[axisid] += separator
            self._postmove_cleanup_cmds[axisid] += str(cmd_str)

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
        Flags for antibacklash, creep, and limits remain the same as self, so if
        you want other_move_table to override these flags, this must be explicitly
        done separately.
        """
        if self == other_move_table:
            return
        for otherrow in other_move_table.rows:
            self.rows.append(otherrow.copy())
        for axisid, cmd_str in other_move_table._postmove_cleanup_cmds.items():
            self.append_postmove_cleanup_cmd(axisid=axisid, cmd_str=cmd_str)
        self.store_orig_command(string=other_move_table._orig_command)
        
    # internal methods
    def _calculate_true_moves(self):
        """Uses PosModel instance to get the real, quantized, calibrated values.
        Anti-backlash and final creep moves are added as necessary.
        """
        latest_TP = [x for x in self.init_posintTP]
        backlash = [0,0]
        true_moves = [[],[]]
        new_moves = [[],[]]
        true_and_new = [[],[]]
        has_moved = [False,False]
        for row in self.rows:
            ideal_dist = [row.data['dT_ideal'],row.data['dP_ideal']]
            for i in [pc.T,pc.P]:
                limits = None if self.allow_exceed_limits else 'debounced'
                true_moves[i].append(self.posmodel.true_move(i, ideal_dist[i], self.allow_cruise, limits, latest_TP))
                latest_TP[i] += true_moves[i][-1]['distance']
                if true_moves[i][-1]['distance']:
                    has_moved[i] = True
        if self.should_antibacklash and any(has_moved):
            backlash_dir = [self.posmodel.state._val['ANTIBACKLASH_FINAL_MOVE_DIR_T'], self.posmodel.state._val['ANTIBACKLASH_FINAL_MOVE_DIR_P']]
            backlash_mag = self.posmodel.state._val['BACKLASH']
            for i in [pc.T,pc.P]:
                backlash[i] = -backlash_dir[i] * backlash_mag * has_moved[i]
                new_moves[i].append(self.posmodel.true_move(i, backlash[i], self.allow_cruise, limits='near_full', init_posintTP=latest_TP))
                new_moves[i][-1]['auto_cmd'] = '(auto backlash backup)'
                latest_TP[i] += new_moves[i][-1]['distance']
        if self.should_final_creep or any(backlash):
            ideal_total = [0,0]
            ideal_total[pc.T] = sum([row.data['dT_ideal'] for row in self.rows])
            ideal_total[pc.P] = sum([row.data['dP_ideal'] for row in self.rows])
            actual_total = [0,0]
            err_dist = [0,0]
            for i in [pc.T,pc.P]:
                actual_total[i] = latest_TP[i] - self.init_posintTP[i]
                err_dist[i] = ideal_total[i] - actual_total[i]
                new_moves[i].append(self.posmodel.true_move(i, err_dist[i], allow_cruise=False, limits='near_full', init_posintTP=latest_TP))
                new_moves[i][-1]['auto_cmd'] = '(auto final creep)'
                latest_TP[i] += new_moves[i][-1]['distance']
        self._rows_extra = []
        for i in range(len(new_moves[0])):
            self._rows_extra.append(PosMoveRow())
            self._rows_extra[i].data = {'dT_ideal': new_moves[pc.T][i]['distance'],
                                        'dP_ideal': new_moves[pc.P][i]['distance'],
                                        'prepause': 0,
                                        'move_time': max(new_moves[pc.T][i]['move_time'],new_moves[pc.P][i]['move_time']),
                                        'postpause': 0,
                                        'auto_cmd': new_moves[pc.T][i]['auto_cmd'],
                                        }
        for i in [pc.T,pc.P]:
            true_and_new[i].extend(true_moves[i])
            true_and_new[i].extend(new_moves[i])
        return true_and_new

    def _for_output_type(self,output_type):
        """Internal function that calculates the various output table formats and
        passes them up to the wrapper functions above.
        """
        true_moves = self._calculate_true_moves()
        rows = self.rows.copy()
        rows.extend(self._rows_extra)
        row_range = range(len(rows))
        table = {}
        if output_type in {'collider', 'schedule', 'full', 'cleanup'}:
            table['dT'] = [true_moves[pc.T][i]['distance'] for i in row_range]
            table['dP'] = [true_moves[pc.P][i]['distance'] for i in row_range]
        if output_type in {'collider', 'schedule', 'full'}:
            table['Tdot'] = [true_moves[pc.T][i]['speed'] for i in row_range]
            table['Pdot'] = [true_moves[pc.P][i]['speed'] for i in row_range]
            table['prepause'] = [rows[i].data['prepause'] for i in row_range]
        if output_type in {'collider', 'schedule', 'full', 'hardware'}:
            table['postpause'] = [rows[i].data['postpause'] for i in row_range]
        if output_type in {'hardware', 'full'}:
            table['motor_steps_T'] = [true_moves[pc.T][i]['motor_step'] for i in row_range]
            table['motor_steps_P'] = [true_moves[pc.P][i]['motor_step'] for i in row_range]
        if output_type in {'hardware', 'full', 'cleanup'}:
            table['speed_mode_T'] = [true_moves[pc.T][i]['speed_mode'] for i in row_range]
            table['speed_mode_P'] = [true_moves[pc.P][i]['speed_mode'] for i in row_range]
        if output_type in {'full', 'cleanup'}:
            table['orig_command'] = self._orig_command
            table['auto_commands'] = [rows[i].data['auto_cmd'] for i in row_range]
        if output_type in {'collider', 'schedule', 'full', 'hardware'}:
            table['move_time'] = [max(true_moves[pc.T][i]['move_time'],
                                      true_moves[pc.P][i]['move_time']) for i in row_range]
        if output_type == 'hardware':
            table['posid'] = self.posmodel.posid
            table['canid'] = self.posmodel.canid
            table['busid'] = self.posmodel.busid
            for i in row_range:  # for hardware type, insert an extra pause-only action if necessary, since hardware commands only really have postpauses
                if rows[i].data['prepause']:
                    for key in ['motor_steps_T','motor_steps_P','move_time']:
                        table[key].insert(i, 0)
                    for key in ['speed_mode_T','speed_mode_P']:
                        table[key].insert(i, 'creep') # speed mode doesn't matter here
                    table['postpause'].insert(i, rows[i].data['prepause'])
            table['nrows'] = len(table['move_time'])
            table['total_time'] = sum(table['move_time'] + table['postpause']) # in seconds
            table['postpause'] = [int(round(x*1000)) for x in table['postpause']] # hardware postpause in integer milliseconds
            return table
        table['nrows'] = len(table['dT'])
        if output_type == 'collider':
            return table
        table['posid'] = self.posmodel.posid
        if output_type in {'schedule', 'full'}:
            table['net_time'] = [table['move_time'][i] + table['prepause'][i] + table['postpause'][i] for i in row_range]
            for i in range(1,table['nrows']):
                table['net_time'][i] += table['net_time'][i-1]
        if output_type in {'schedule', 'cleanup', 'full'}:
            table['net_dT'] = table['dT'].copy()
            table['net_dP'] = table['dP'].copy()
            for i in range(1, table['nrows']):
                table['net_dT'][i] += table['net_dT'][i-1]
                table['net_dP'][i] += table['net_dP'][i-1]
        if output_type in {'cleanup', 'full'}:
            table.update({'TOTAL_CRUISE_MOVES_T':0,'TOTAL_CRUISE_MOVES_P':0,'TOTAL_CREEP_MOVES_T':0,'TOTAL_CREEP_MOVES_P':0})
            for i in row_range:
                table['TOTAL_CRUISE_MOVES_T'] += int(table['speed_mode_T'][i] == 'cruise' and table['dT'] != 0)
                table['TOTAL_CRUISE_MOVES_P'] += int(table['speed_mode_P'][i] == 'cruise' and table['dP'] != 0)
                table['TOTAL_CREEP_MOVES_T'] += int(table['speed_mode_T'][i] == 'creep' and table['dT'] != 0)
                table['TOTAL_CREEP_MOVES_P'] += int(table['speed_mode_P'][i] == 'creep' and table['dP'] != 0)
            table['log_note'] = self.log_note
            table['postmove_cleanup_cmds'] = self._postmove_cleanup_cmds
        if output_type == 'full':
            trans = self.posmodel.trans
            posintT = [self.init_posintTP[pc.T] + table['net_dT'][i]
                       for i in row_range]
            posintP = [self.init_posintTP[pc.P] + table['net_dP'][i]
                       for i in row_range]
            table['posintTP'] = [[posintT[i], posintP[i]] for i in row_range]
            table['poslocTP'] = [trans.posintTP_to_poslocTP(tp) for tp in table['posintTP']]
            table['poslocXY'] = [trans.posintTP_to_poslocXY(tp) for tp in table['posintTP']]
            table['QS'] = [trans.poslocXY_to_QS(xy) for xy in table['poslocXY']]
        return table

class PosMoveRow(object):
    """The general user does not directly use the internal values of a
    PosMoveRow instance, but rather should rely on the higher level table
    formats that are exported by PosMoveTable.
    """
    def __init__(self):
        self.data = {'dT_ideal':  0,  # [deg] ideal theta distance to move (as seen by external observer)
                     'dP_ideal':  0,  # [deg] ideal phi distance to move (as seen by external observer)
                     'prepause':  0,  # [sec] delay for this number of seconds before executing the move
                     'move_time': 0,  # [sec] time it takes the move to execute
                     'postpause': 0,  # [sec] delay for this number of seconds after the move has completed
                     'auto_cmd': '',  # [string] auto-generated command info corresponding to this row
                     }
        
    def __repr__(self):
        return repr(self.data)

    def copy(self):
        return copymodule.deepcopy(self)

