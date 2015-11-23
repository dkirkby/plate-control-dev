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
        self.posmodel = posmodel       # the particular positioner this table applies to
        self.final_backlash_on = True  # whether to do anti-backlash submoves on the final move
        self.final_creep_on    = True  # whether to do precision creep submoves on the final move
        self.__rows = [] # internal representation of the move data

        
    # getters
    def for_scheduler(self):
        """Version of the table suitable for move scheduling.
        Distances are given at the output shafts, in degrees.
        Times are given in seconds.
        """
        # note to self... always return the quantized obs vals
        #             ... always include the extra submoves if the top-level flags say so
        
    def for_hardware(self):
        """Version of the table suitable for the hardware side.
        Distances are given at the motor shafts, in discrete steps.
        Times are given in milliseconds.
        """
        # note to self... organize the pauses so that there are only "postpauses", the way we're implementing the firmware
        #             ... always include the extra submoves if the top-level flags say so

    # setters
    def set_move_in_obs_degrees(self, rowidx, axisid, distance):
        """Scheduler uses this method to get move distances into the table.
        If row index does not exist yet, then it will be added.
        """
        
    def set_move_in_motor_steps(self, rowidx, axisid, nsteps, speed_mode):
        """PosModel uses this method to update existing move distances in the
        table with their quantized values.
        """
        
    def set_prepause(self, rowidx, axisid, prepause):
        """For use by scheduler to get pauses before moves in.
        """
        
    def set_postpause(self, rowidx, axisid, postpause):
        """For use by scheduler to get pauses after moves in.
        """
                
    # row manipulations            
    def insert_row(self,index,posmoverow):
        if index >= 0:
            if index > self.__nrows:  # fill in some blanks in-between
                for i in range(index - self.__nrows - 1):
                    self.append_row(self.blankrow())
            self.__table.insert(index,posmove_row)
            
        else:
            print "bad row index " + repr(index) + " for insertion"

    def append_row(self,posmoverow):
        self.insert(self.__nrows,posmoverow)
        
    def delete_row(self,index):
        if index >= 0 and index < self.__nrows:
            del self.__table[index]
        else:
            print "error: no row at index " + repr(index) + " to delete"

    # internal helper methods
    @property
    def __nrows(self):
        """For internal operations, not general use.
        """
        return len(self.__table)

        
class PosMoveRow(object):
    """Essentially this is a wrapper around a dictionary. The purpose is the
    validations and updates in using the "setval" method. Values should not be
    set in any other way. The general user should not ever directly use the
    internal values of a PosMoveRow instance, but rather should rely on the
    higher level table forms exportable by PosMoveTable.
    """
    def __init__(self, posmodel=PosModel.PosModel()):
        self._posmodel = posmodel
        self._data = self.defaultrow()

    def defaultrow():
        return {'obs_dT_continuous'  :0,        # [deg] ideal theta distance to move (as seen by external observer)
                'obs_dP_continuous'  :0,        # [deg] ideal phi distance to move (as seen by external observer)
                'obs_dT_quantized'   :0,        # [deg] real theta distance, quantized and calibrated to a particular number of motor steps
                'obs_dP_quantized'   :0,        # [deg] real phi distance, quantized and calibrated to a particular number of motor steps
                'motor_steps_T'      :0,        # [-] number of steps the hardware should move the theta motor shaft
                'motor_steps_P'      :0,        # [-] number of steps the hardware should move the phi motor shaft
                'speed_mode_T'       :'cruise', # ['cruise' or 'creep'] theta, whether to cruise (fast, coarse resolution) or creep (slow, fine resolution)
                'speed_mode_P'       :'cruise', # ['cruise' or 'creep'] phi, whether to cruise (fast, coarse resolution) or creep (slow, fine resolution)
                'speed_continuous_T' :self.posmodel.speed_cruise_T, # [deg/sec] ideal speed of theta rotation
                'speed_continuous_P' :self.posmodel.speed_cruise_P, # [deg/sec] ideal speed of phi rotation
                'prepause'           :0,        # [sec] delay for this number of seconds before executing the move
                'move_time'          :0,        # [sec] time it takes the move to execute
                'postpause'          :0,        # [sec] delay for this number of seconds after the move has completed
                'add_antibacklash_T' :False,    # [bool] whether to add/replace this move with additional anti-backlash submoves
                'add_antibacklash_P' :False,    # [bool] whether to add/replace this move with additional anti-backlash submoves
                'add_final_creep_T'  :False,    # [bool] whether to add/replace this move with additional final creep submoves
                'add_final_creep_P'  :False}    # [bool] whether to add/replace this move with additional final creep submoves

    def setval(self,key,val):
        """All value setting should be done via this method, so that validations
        and updates to related fields can be performed."""
        updates_list = []
        if key == 'obs_dT_continuous' or key == 'obs_dP_continuous':
            # update motor steps
        if key == 'motor_steps_T' or key == 'motor_steps_P':
            # update quantized vals
        if key == 'obs_dT_quantized' or key == 'obs_dP_quantized':
            # update move time
        if key == 'speed_mode_T'
            # update theta continuous speed
        if key == 'speep_mode_P'
            # update phi continuous speed
        