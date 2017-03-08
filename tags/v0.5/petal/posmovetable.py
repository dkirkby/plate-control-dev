import posmodel
import posconstants as pc
import copy

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
        self.posmodel = posmodel # the particular positioner this table applies to
        self.__rows = []         # internal representation of the move data

    # getters
    @property
    def for_schedule(self):
        """Version of the table suitable for move scheduling.
        Distances are given at the output shafts, in degrees.
        Times are given in seconds.
        """
        return self.__for_output_type('schedule')

    @property
    def for_hardware(self):
        """Version of the table suitable for the hardware side.
        Distances are given at the motor shafts, in discrete steps.
        Times are given in milliseconds.
        """
        return self.__for_output_type('hardware')

    @property
    def for_cleanup(self):
        """Version of the table suitable for updating the software internal
        position tracking after the physical move has been performed.
        """
        return self.__for_output_type('cleanup')

    # setters
    def set_move(self, rowidx, axisid, distance):
        """Put or update a move distance into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        dist_label = {pc.T:'dT_ideal', pc.P:'dP_ideal'}
        if rowidx >= len(self.__rows):
            self.insert_new_row(rowidx)
        for key in self.__rows[rowidx]._move_options.keys():
            self.__rows[rowidx]._move_options[key] = self.posmodel.state.read(key)  # snapshot the current state
        self.__rows[rowidx]._data[dist_label[axisid]] = distance

    def set_prepause(self, rowidx, prepause):
        """Put or update a prepause into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        if rowidx >= len(self.__rows):
            self.insert_new_row(rowidx)
        self.__rows[rowidx]._data['prepause'] = prepause

    def set_postpause(self, rowidx, postpause):
        """Put or update a postpause into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        if rowidx >= len(self.__rows):
            self.insert_new_row(rowidx)
        self.__rows[rowidx]._data['postpause'] = postpause

    # row manipulations
    def insert_new_row(self,index):
        newrow = PosMoveRow(self.posmodel)
        self.__rows.insert(index,newrow)
        if index > len(self.__rows):
            self.insert_new_row(index) # to fill in any blanks up to index

    def append_new_row(self):
        self.insert_new_row(len(self.__rows))

    def delete_row(self,index):
        del self.__rows[index]

    def extend(self, other_move_table):
        for otherrow in other_move_table.__rows:
            self.__rows.append(otherrow.copy())

    # internal methods
    def __for_output_type(self,output_type):
        # define the columns that will be filled in
        if output_type == 'schedule':
            table = {'posid':'','nrows':0,'dT':[],'dP':[],'Tdot':[],'Pdot':[],'prepause':[],'move_time':[],'postpause':[]}
        elif output_type == 'hardware':
            table = {'posid':'','nrows':0,'motor_steps_T':[],'motor_steps_P':[],'speed_mode_T':[],'speed_mode_P':[],'move_time':[],'postpause':[]}
        elif output_type == 'cleanup':
            table = {'posid':'','nrows':0,'dT':[],'dP':[]}
        else:
            print( 'bad table output type ' + output_type)

        i = 0
        for row in self.__rows:
            # insert an extra pause-only row if necessary, since hardware commands only really have postpauses
            if output_type == 'hardware' and row._data['prepause']:
                table['motor_steps_T'].append(0)
                table['motor_steps_P'].append(0)
                table['postpause'].append(row._data['prepause'])

            move_options = row._move_options.copy()

            # only allow requesting final backlash / creep moves if it's really a final row
            i += 1
            if i != len(self.__rows):
                move_options['BACKLASH_REMOVAL_ON'] = False
                move_options['FINAL_CREEP_ON']      = False

            # use PosModel instance to get the real, quantized, calibrated values
            true_move_T = self.posmodel.true_move(pc.T, row._data['dT_ideal'], move_options)
            true_move_P = self.posmodel.true_move(pc.P, row._data['dP_ideal'], move_options)

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
            while pad != full and len(true_moves[pad]['motor_step']) < len(true_moves[full]['motor_step']):
                true_moves[pad]['motor_step'].append(0)
                true_moves[pad]['move_time'].append(0)
                true_moves[pad]['obs_distance'].append(0)
                true_moves[pad]['obs_speed'].append(0)
                true_moves[pad]['speed_mode'].append('creep')

            # fill in the output table according to type
            if output_type == 'schedule':
                table['dT'].extend(true_move_T['obs_distance'])
                table['dP'].extend(true_move_P['obs_distance'])
                table['Tdot'].extend(true_move_T['obs_speed'])
                table['Pdot'].extend(true_move_P['obs_speed'])
                table['prepause'].append(row._data['prepause'])
                table['postpause'].append(row._data['postpause'])
            if output_type == 'hardware':
                table['motor_steps_T'].extend(true_move_T['motor_step'])
                table['motor_steps_P'].extend(true_move_P['motor_step'])
                table['speed_mode_T'].extend(true_move_T['speed_mode'])
                table['speed_mode_P'].extend(true_move_P['speed_mode'])
                table['postpause'].append(round(row._data['postpause']*1000)) # hardware postpause in integer milliseconds
            if output_type == 'cleanup':
                table['dT'].extend(true_move_T['obs_distance'])
                table['dP'].extend(true_move_P['obs_distance'])
            if output_type == 'schedule' or output_type == 'hardware':
                while true_move_T['move_time']: # while loop here, since there may be multiple submoves
                    time1 = true_move_T['move_time'].pop(-1)
                    time2 = true_move_P['move_time'].pop(-1)
                    table['move_time'].append(max(time1,time2))
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

    def __init__(self,posmodel=None):
        self._data = {'dT_ideal'     : 0,        # [deg] ideal theta distance to move (as seen by external observer)
                      'dP_ideal'     : 0,        # [deg] ideal phi distance to move (as seen by external observer)
                      'prepause'     : 0,        # [sec] delay for this number of seconds before executing the move
                      'move_time'    : 0,        # [sec] time it takes the move to execute
                      'postpause'    : 0}        # [sec] delay for this number of seconds after the move has completed
        if not(posmodel):
            posmodel = posmodel.Posmodel()
        self._move_options = posmodel.default_move_options

    def copy(self):
        return copy.copy(self)

