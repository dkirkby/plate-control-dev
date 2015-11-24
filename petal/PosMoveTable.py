import PosModel
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
    
    def __init__(self, posmodel=PosModel.PosModel()):
        self.posmodel = posmodel          # the particular positioner this table applies to
        self.__rows = []                  # internal representation of the move data

    # getters
    def for_scheduler(self):
        """Version of the table suitable for move scheduling.
        Distances are given at the output shafts, in degrees.
        Times are given in seconds.
        """
        return self.__for_output_type('scheduler')
            
    def for_hardware(self):
        """Version of the table suitable for the hardware side.
        Distances are given at the motor shafts, in discrete steps.
        Times are given in milliseconds.
        """
        return self.__for_output_type('hardware')

    # setters
    def set_move(self, rowidx, axisid, distance):
        """Put or update a move distance into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        if rowidx >= len(self.__rows):
            self.insert_new_row(rowidx)
        if axisid == self.posmodel.T:
            dist_label = 'dT'
        elif axisid == self.posmodel.P:
            dist_label = 'dP'
        else:
            print 'bad axisid ' + repr(axisid)
        for key in self.__rows[rowidx]._move_options.keys():
            self.__rows[rowidx]._move_options[key] = self.posmodel.state.kv[key]  # snapshot the current state
        self.__rows[rowidx]._data[dist_label] = distance

    def set_prepause(self, rowidx, prepause):
        """Put or update a prepause into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        if rowidx >= len(self.__rows):
            self.insert_new_row(rowidx)
        self.__rows[rowidx] = prepause
        
    def set_postpause(self, rowidx, postpause):
        """Put or update a postpause into the table.
        If row index does not exist yet, then it will be added, and any blank filler rows will be generated in-between.
        """
        if rowidx >= len(self.__rows):
            self.insert_new_row(rowidx)
        self.__rows[rowidx] = postpause 
               
    # row manipulations            
    def insert_new_row(self,index):
        newrow = PosMoveRow.PosMoveRow()
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
        if output_type == 'scheduler':
            table = {'nrows':0,'dT':[],'dP':[],'Tdot':[],'Pdot':[],'prepause':[],'move_time':[],'postpause':[]}
        elif output_type == 'hardware':
            table = {'nrows':0,'motor_steps_T':[],'motor_steps_P':[],'speed_mode_T':[],'speed_mode_P':[],'postpause':[]}
        else:
            print 'bad table output type ' + output_type        

        i = 0
        for row in self.__rows:
            # insert an extra pause-only row if necessary, since hardware commands only really have postpauses           
            if output_type == 'hardware' and row['prepause']:
                table['motor_steps_T'].append(0)
                table['motor_steps_P'].append(0)
                table['postpause'].append(row['prepause'])
            
            move_options = row._move_options.copy()
            
            # only do final backlash / creep moves if it's really a final row
            i += 1
            if i != len(self.__rows):
                move_options['BACKLASH_REMOVAL_ON'] = False
                move_options['FINAL_CREEP_ON']      = False
            
            # use PosModel instance to get the real, quantized, calibrated values
            true_move_T = self.posmodel(self.posmodel.T, row['dT'], move_options)
            true_move_P = self.posmodel(self.posmodel.P, row['dP'], move_options)
            
            # fill in the output table according to type
            if output_type == 'scheduler':
                table['dT'].extend(true_move_T['obs_distance'])
                table['dP'].extend(true_move_P['obs_distance'])
                table['Tdot'].extend(true_move_T['obs_speed'])
                table['Pdot'].extend(true_move_P['obs_speed'])
                table['prepause'].extend(row['prepause'])
            if output_type == 'hardware':
                table['motor_steps_T'].extend(true_move_T['motor_step'])
                table['motor_steps_P'].extend(true_move_P['motor_step'])
                table['speed_mode_T'].extend(true_move_T['speed_mode'])
                table['speed_mode_P'].extend(true_move_P['speed_mode'])

            # fill in items general to all table types
            while true_move_T['move_time']: # while loop here, since there may be multiple submoves
                time1 = true_move_T['move_time'].pop(-1)
                time2 = true_move_P['move_time'].pop(-1)
                table['move_time'].extend(max([time1,time2]))            
            table['postpause'].extend(row['postpause'])                  
        table['nrows'] = len(table['dT'])
        return table

        
class PosMoveRow(object):
    """The general user does not directly use the internal values of a
    PosMoveRow instance, but rather should rely on the higher level table
    formats that are exported by PosMoveTable.
    """
                          
    def __init__(self):
        self._data = {'dT'           : 0,        # [deg] ideal theta distance to move (as seen by external observer)
                      'dP'           : 0,        # [deg] ideal phi distance to move (as seen by external observer)
                      'prepause'     : 0,        # [sec] delay for this number of seconds before executing the move
                      'move_time'    : 0,        # [sec] time it takes the move to execute
                      'postpause'    : 0}        # [sec] delay for this number of seconds after the move has completed 
        self._move_options = PosModel.default_move_options
        
    def copy(self):
        return copy.copy(self)

