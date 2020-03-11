import posstate
import postransforms
import posconstants as pc

class PosModel(object):
    """Software model of the physical positioner hardware.
    Takes in local (x,y) or (th,phi) targets, move speeds, converts
    to degrees of motor shaft rotation, speed, and type of move (such
    as cruise / creep / backlash / hardstop approach).

    One instance of PosModel corresponds to one PosState to physical positioner.
    """

    def __init__(self, state=None, petal_alignment=None):
        if not(state):
            self.state = posstate.PosState()
        else:
            self.state = state
        self.trans = postransforms.PosTransforms(
            this_posmodel=self, petal_alignment=petal_alignment)
        self.axis = [None,None]
        self.axis[pc.T] = Axis(self,pc.T)
        self.axis[pc.P] = Axis(self,pc.P)
        self._timer_update_rate          = 18e3   # Hz
        self._stepsize_creep             = 0.1    # deg
        self._stepsize_cruise            = 3.3    # deg
        self._motor_speed_cruise         = 9900.0 * 360.0 / 60.0  # deg/sec (= RPM *360/60)
        self._spinupdown_dist_per_period = sum(range(round(self._stepsize_cruise/self._stepsize_creep) + 1))*self._stepsize_creep
        self._abs_shaft_speed_cruise_T   = abs(self._motor_speed_cruise / self.axis[pc.T].signed_gear_ratio)
        self._abs_shaft_speed_cruise_P   = abs(self._motor_speed_cruise / self.axis[pc.P].signed_gear_ratio)

    @property
    def _motor_speed_creep(self):
        """Returns motor creep speed (which depends on the creep period) in deg/sec."""
        return self._timer_update_rate * self._stepsize_creep / self.state._val['CREEP_PERIOD']  # deg/sec

    @property
    def _spinupdown_distance(self):
        """Returns distance at the motor shaft in deg over which to spin up to cruise speed or down from cruise speed."""
        return self._spinupdown_dist_per_period * self.state._val['SPINUPDOWN_PERIOD']

    @property
    def posid(self):
        """Returns the positioner id string."""
        return self.state._val['POS_ID']

    @property
    def canid(self):
        """Returns the positioner hardware id on the CAN bus."""
        return self.state._val['CAN_ID']

    @property
    def busid(self):
        """Returns the name of the can bus that the positioner belongs to."""
        return self.state._val['BUS_ID']

    @property
    def deviceloc(self):
        """Returns the device location id (on the petal) of the positioner."""
        return self.state._val['DEVICE_LOC']

    @property
    def is_enabled(self):
        """Returns whether the positioner has its control enabled or not."""
        return self.state._val['CTRL_ENABLED']

    @property
    def expected_current_posintTP(self):
        """Returns the internally-tracked expected position of the
        theta and phi shafts at the output of the gearbox."""
        return self.axis[pc.T].pos, self.axis[pc.P].pos

    @property
    def expected_current_poslocTP(self):
        """Returns the expected position of theta and phi bodies, as seen by
        an external observer."""
        posintTP = self.expected_current_posintTP
        return self.trans.posintTP_to_poslocTP(posintTP)

    @property
    def expected_current_position(self):
        """
        Returns a general dictionary of the current expected position in all
        the various coordinate systems.
        The keys are:
            'posintTP'  tuple in deg, independent variable,
                        the internally-tracked expected position of the
                        theta shaft at the output of the gearbox
            'poslocTP'  tuple in deg, pos local coordinates with offsets
            'poslocXY   tuple in, mm, expected local x position
            'QS'        tuple in (deg, mm), expected global Q position
            'flatXY'    tuple in, mm, dependent variable,
                        expected local x in a system where focal surface
                        curvature is flattened out to an approximate plane
            'ptlXY'     tuple in mm, petal local XY projection of ptlXYZ
            'obsXY'     tuple in mm, dependent, expected global x position
            'motTP'     tuple in deg, dependent variable, expected position
                        of theta motor
        """
        posintTP = self.expected_current_posintTP
        QS = self.trans.posintTP_to_QS(posintTP)
        return {'posintTP': posintTP,
                'motTP': (self.axis[pc.T].shaft_to_motor(posintTP[0]),
                          self.axis[pc.P].shaft_to_motor(posintTP[1])),
                'poslocTP': self.trans.posintTP_to_poslocTP(posintTP),
                'poslocXY': self.trans.posintTP_to_poslocXY(posintTP),
                'flatXY': self.trans.posintTP_to_flatXY(posintTP),
                'ptlXY': self.trans.posintTP_to_ptlXY(posintTP),
                'obsXY': tuple(
                        self.trans.QS_to_obsXYZ(QS, cast=True).flatten()[:2]),
                'QS': QS}

    @property
    def expected_current_position_str(self):
        """One-line string summarizing current expected position.
        """
        pos = self.expected_current_position
        s = ('Q:{:8.3f}{}, S:{:8.3f}{} | '
             'flatX:{:8.3f}{}, flatY:{:8.3f}{} | '
             'obsX:{:8.3f}{}, obsY:{:8.3f}{} | '
             'ptlX:{:8.3f}{}, ptlY:{:8.3f}{} |'
             'poslocX:{:8.3f}{}, poslocY:{:8.3f}{} | '
             'poslocT:{:8.3f}{}, poslocP:{:8.3f}{} | '
             'posintT:{:8.3f}{}, posintP:{:8.3f}{} | '
             'motT:{:8.1f}{}, motP:{:8.1f}{}'). \
            format(pos['QS'][0],       pc.deg, pos['QS'][1],       pc.mm,
                   pos['flatXY'][0],   pc.mm,  pos['flatXY'][1],   pc.mm,
                   pos['obsXY'][0],    pc.mm,  pos['obsXY'][1],    pc.mm,
                   pos['ptlXY'][0],    pc.mm,  pos['ptlXY'][1],    pc.mm,
                   pos['poslocXY'][0], pc.mm,  pos['poslocXY'][1], pc.mm,
                   pos['poslocTP'][0], pc.deg, pos['poslocTP'][1], pc.deg,
                   pos['posintTP'][0], pc.deg, pos['posintTP'][1], pc.deg,
                   pos['motTP'][0],    pc.deg, pos['motTP'][1],    pc.deg)
        return s

    @property
    def targetable_range_T(self):
        """Returns a [1x2] array of theta_min, theta_max, after subtracting buffer zones near the hardstops.
        The return is in the posintTP coordinates, not poslocTP. Understand therefore that OFFSET_T is not included in these values.
        """
        return self.axis[pc.T].debounced_range

    @property
    def targetable_range_P(self):
        """Returns a [1x2] array of phi_min, phi_max, after subtracting buffer zones near the hardstops.
        The return is in the posintTP coordinates, not poslocTP. Understand therefore that OFFSET_P is not included in these values.
        """
        return self.axis[pc.P].debounced_range

    @property
    def full_range_T(self):
        """Returns a [1x2] array of [theta_min, theta_max], from hardstop-to-hardstop.
        The return is in the posintTP coordinates, not poslocTP. Understand therefore that OFFSET_T is not included in these values.
        """
        return self.axis[pc.T].full_range

    @property
    def full_range_P(self):
        """Returns a [1x2] array of [phi_min, phi_max], from hardstop-to-hardstop.
        The return is in the posintTP coordinates, not poslocTP. Understand therefore that OFFSET_P is not included in these values.
        """
        return self.axis[pc.P].full_range

    @property
    def abs_shaft_speed_cruise_T(self):
        """Returns the absolute output shaft speed (deg/sec), in cruise mode, of the theta axis.
        """
        return self._abs_shaft_speed_cruise_T

    @property
    def abs_shaft_speed_cruise_P(self):
        """Returns the absolute output shaft speed (deg/sec), in cruise mode, of the phi axis.
        """
        return self._abs_shaft_speed_cruise_P

    def true_move(self, axisid, distance, allow_cruise, limits='debounced', init_posintTP=None):
        """Input move distance on either the theta or phi axis, as seen by the
        observer, in degrees.

        The return values are formatted as a dictionary, with keys:
            'motor_step'   ... integer number of motor steps, signed according to direction
            'move_time'    ... total time the move takes [sec]
            'distance'     ... quantized distance of travel [deg], signed according to direction
            'speed'        ... approximate speed of travel [deg/sec]. unsigned. note 'move_time' is preferred for precision timing calculations
            'speed_mode'   ... 'cruise' or 'creep'

        The argument 'init_posintTP' is used to account for expected
        future shaft position changes. This is necessary for correct checking of
        software travel limits, when a sequence of multiple moves is being planned out.
        
        The argument 'limits' may take values:
            'debounced'
            'near_full'
            None
        See the debounced_range() and near_full_range() methods of Axis class for their
        specific meanings.
        """
        start = self.expected_current_posintTP if not init_posintTP else init_posintTP
        if limits:
            use_near_full_range = (limits == 'near_full')
            distance = self.axis[axisid].truncate_to_limits(distance, start[axisid], use_near_full_range)
        motor_dist = self.axis[axisid].shaft_to_motor(distance)
        move_data = self.motor_true_move(axisid, motor_dist, allow_cruise)
        move_data['distance'] = self.axis[axisid].motor_to_shaft(move_data['distance'])
        move_data['speed']    = self.axis[axisid].motor_to_shaft(move_data['speed'])
        return move_data

    def motor_true_move(self, axisid, distance, allow_cruise):
        """Calculation of cruise, creep, spinup, and spindown details for a move of
        an argued distance on the axis identified by axisid.
        """
        move_data = {}
        dist_spinup = 2 * pc.sign(distance) * self._spinupdown_distance  # distance over which accel / decel to and from cruise speed
        if not(allow_cruise) or abs(distance) <= (abs(dist_spinup) + self.state._val['MIN_DIST_AT_CRUISE_SPEED']):
            move_data['motor_step']   = int(round(distance / self._stepsize_creep))
            move_data['distance']     = move_data['motor_step'] * self._stepsize_creep
            move_data['speed_mode']   = 'creep'
            move_data['speed']        = self._motor_speed_creep
            move_data['move_time']    = abs(move_data['distance']) / move_data['speed']
        else:
            dist_cruise = distance - dist_spinup
            move_data['motor_step']   = int(round(dist_cruise / self._stepsize_cruise))
            move_data['distance']     = move_data['motor_step'] * self._stepsize_cruise + dist_spinup
            move_data['speed_mode']   = 'cruise'
            move_data['speed']        = self._motor_speed_cruise
            move_data['move_time']    = (abs(move_data['motor_step'])*self._stepsize_cruise + 4*self._spinupdown_distance) / move_data['speed']
        return move_data

    def postmove_cleanup(self, cleanup_table):
        """Always perform this after positioner physical moves have been
        completed, to update the internal tracking of shaft positions and
        variables.
        """
        if self.state._val['CTRL_ENABLED'] is False:
            return
        self.state.store('POS_T', self.state._val['POS_T'] + cleanup_table['net_dT'][-1])
        self.state.store('POS_P', self.state._val['POS_P'] + cleanup_table['net_dP'][-1])
        for axis in self.axis:
            exec(axis.postmove_cleanup_cmds)
            axis.postmove_cleanup_cmds = ''
        separator = '; '
        try:
            self.state.store('MOVE_CMD',  separator.join(cleanup_table['command']))
            value = []
            for x in cleanup_table['cmd_val1']:
                try:
                    value.append('{0:.6g}'.format(float(x)))
                except:
                    pass
            self.state.store('MOVE_VAL1', separator.join(x for x in value))
            value = []
            for x in cleanup_table['cmd_val2']:
                try:
                    value.append('{0:.6g}'.format(float(x)))
                except:
                    pass
            self.state.store('MOVE_VAL2', separator.join(x for x in value))
        except Exception as e:
            print('postmove_cleanup: %s' % str(e))
        self.state.store('TOTAL_CRUISE_MOVES_T', self.state._val['TOTAL_CRUISE_MOVES_T']+ cleanup_table['TOTAL_CRUISE_MOVES_T'])
        self.state.store('TOTAL_CRUISE_MOVES_P', self.state._val['TOTAL_CRUISE_MOVES_P'] + cleanup_table['TOTAL_CRUISE_MOVES_P'])
        self.state.store('TOTAL_CREEP_MOVES_T', self.state._val['TOTAL_CREEP_MOVES_T'] + cleanup_table['TOTAL_CREEP_MOVES_T'])
        self.state.store('TOTAL_CREEP_MOVES_P', self.state._val['TOTAL_CREEP_MOVES_P'] + cleanup_table['TOTAL_CREEP_MOVES_P'])
        self.state.store('TOTAL_MOVE_SEQUENCES', self.state._val['TOTAL_MOVE_SEQUENCES'] + 1)
        self.state.append_log_note(cleanup_table['log_note'])

    def clear_postmove_cleanup_cmds_without_executing(self):
        """Useful for example if a positioner is disabled, and we don't want any false post-move
        cleanup to be attempted. The reason this function is needed sometimes is due to a corner
        I backed into, where the postmove_cleanup_cmds need to be stored separate from the cleanup_table.
        So for example if scheduler denies a move request, then even though there was no move_table
        generated, it still needs to separately be able to clear out any of these commands that might
        be lurking.
        """
        for axis in self.axis:
            axis.postmove_cleanup_cmds = ''

class Axis(object):
    """Handler for a motion axis. Provides move syntax and keeps tracks of position.
    """

    def __init__(self, posmodel, axisid):
        self.posmodel = posmodel
        self.axisid = axisid
        self.postmove_cleanup_cmds = ''
        self.antibacklash_final_move_dir = self.calc_antibacklash_final_move_dir()
        self.principle_hardstop_direction = self.calc_principle_hardstop_direction()
        self.backlash_clearance = self.calc_backlash_clearance()
        self.hardstop_clearance = self.calc_hardstop_clearance()
        self.hardstop_clearance_near_full_range = self.calc_hardstop_clearance_near_full_range()
        self.hardstop_debounce = self.calc_hardstop_debounce()
        self.signed_gear_ratio = self.motor_calib_properties['ccw_sign']*self.motor_calib_properties['gear_ratio']

    @property
    def pos(self):
        """Internally-tracked angular position of the axis, at the output of the gear.
        """
        if self.axisid == pc.T:
            return self.posmodel.state._val['POS_T']
        else:
            return self.posmodel.state._val['POS_P']

    @pos.setter
    def pos(self, value):
        if self.axisid == pc.T:
            self.posmodel.state.store('POS_T', value)
        else:
            self.posmodel.state.store('POS_P', value)

    @property
    def full_range(self):
        """Calculated from physical range only, with no subtraction of debounce
        distance.
        Returns [1x2] array of [min,max]
        """
        if self.axisid == pc.T:
            r = abs(self.posmodel.state._val['PHYSICAL_RANGE_T'])
            return [-0.50*r, 0.50*r]  # split theta range such that 0 is essentially in the middle
        else:
            r = abs(self.posmodel.state._val['PHYSICAL_RANGE_P'])
            return [185.0-r, 185.0]  # split phi range such that 0 is essentially at the minimum

    @property
    def debounced_range(self):
        """Calculated from full range, accounting for removal of both the hardstop
        clearance distances and the backlash removal distance.
        Returns [1x2] array of [min,max]
        """
        f = self.full_range
        h = self.hardstop_debounce # includes "backlash" and "clearance"
        return [f[0] + h[0], f[1] + h[1]]

    @property
    def near_full_range(self):
        """In-between full_range and debounced_range. This guarantees sufficient
        backlash clearance, while giving reasonable probability of not contacting
        the hard stop. Intended use case is to allow a small amount of numerical
        margin for making tiny cruise move corrections.
        Returns [1x2] array of [min,max]
        """
        f = self.full_range
        nh = self.hardstop_clearance_near_full_range # does not include "backlash"
        return [f[0] + nh[0], f[1] + nh[1]]

    @property
    def maxpos(self):
        """Max accessible position, as defined by debounced_range.
        """
        return self.get_maxpos() # this redirect is for legacy compatibility with external code

    def get_maxpos(self, use_near_full_range=False):
        """Function to return accessible position. By default this is within
        debounced_range. An option exists to get the min as defined by near_full_range
        instead.
        """
        d = self.near_full_range if use_near_full_range else self.debounced_range
        if self.last_primary_hardstop_dir >= 0:
            return max(d)
        else:
            return self.get_minpos(use_near_full_range) + (d[1] - d[0])

    @property
    def minpos(self, use_near_full_range=False):
        """Min accessible position. By default this is within debounced_range.
        An option exists to get the min as defined by near_full_range instead.
        """
        return self.get_minpos()
        
    def get_minpos(self, use_near_full_range=False):
        """Function to return accessible position. By default this is within
        debounced_range. An option exists to get the min as defined by near_full_range
        instead.
        """
        d = self.near_full_range if use_near_full_range else self.debounced_range
        if self.last_primary_hardstop_dir < 0:
            return min(d)
        else:
            return self.get_maxpos(use_near_full_range) - (d[1] - d[0])

    @property
    def last_primary_hardstop_dir(self):
        if self.axisid == pc.T:
            return self.posmodel.state._val['LAST_PRIMARY_HARDSTOP_DIR_T']
        else:
            return self.posmodel.state._val['LAST_PRIMARY_HARDSTOP_DIR_P']

    @last_primary_hardstop_dir.setter
    def last_primary_hardstop_dir(self,value):
        if self.axisid == pc.T:
            self.posmodel.state.store('LAST_PRIMARY_HARDSTOP_DIR_T',value)
        else:
            self.posmodel.state.store('LAST_PRIMARY_HARDSTOP_DIR_P',value)

    @property
    def total_limit_seeks(self):
        if self.axisid == pc.T:
            return self.posmodel.state._val['TOTAL_LIMIT_SEEKS_T']
        else:
            return self.posmodel.state._val['TOTAL_LIMIT_SEEKS_P']

    @total_limit_seeks.setter
    def total_limit_seeks(self,value):
        if self.axisid == pc.T:
            self.posmodel.state.store('TOTAL_LIMIT_SEEKS_T',value)
        else:
            self.posmodel.state.store('TOTAL_LIMIT_SEEKS_P',value)

    @property
    def limit_seeking_search_distance(self):
        """A distance magnitude that guarantees hitting a hard limit in either direction.
        """
        full_range = self.full_range
        return abs((full_range[1]-full_range[0])*self.posmodel.state._val['LIMIT_SEEK_EXCEED_RANGE_FACTOR'])

    @property
    def motor_calib_properties(self):
        """Return properties for motor calibration.
        """
        prop = {}
        if self.axisid == pc.T:
            prop['gear_ratio'] = pc.gear_ratio[self.posmodel.state._val['GEAR_TYPE_T']]
            prop['ccw_sign'] = self.posmodel.state._val['MOTOR_CCW_DIR_T']
        else:
            prop['gear_ratio'] = pc.gear_ratio[self.posmodel.state._val['GEAR_TYPE_P']]
            prop['ccw_sign'] = self.posmodel.state._val['MOTOR_CCW_DIR_P']
        return prop

    def motor_to_shaft(self, distance):
        """
        Convert a distance in motor angle to shaft angle at the gearbox output.
        """
        return distance / self.signed_gear_ratio

    def shaft_to_motor(self, distance):
        """
        Convert a distance in shaft angle to motor angle at the gearbox output.
        """
        return distance * self.signed_gear_ratio

    def truncate_to_limits(self, distance, start_pos=None, use_near_full_range=False):
        """Return distance after truncating it (if necessary) to the software limits.
        
        An expected starting position can optionally be argued. If None, then the
        internally-tracked position is used as the starting point. 
        
        Can also optionally argue with use_near_full_range=True. This uses a slightly
        wider definiton for the max and min accessible limits at which to truncate.
        See the maxpos and minpos methods, as well as debounced_range vs near_full_range.
        """
        if distance == 0:
            return distance
        maxpos = self.get_maxpos(use_near_full_range)
        minpos = self.get_minpos(use_near_full_range)
        if start_pos == None:
            start_pos = self.pos
        target_pos = start_pos + distance
        if maxpos < minpos:
            distance = 0
        elif target_pos > maxpos:
            new_distance = maxpos - start_pos
            distance = new_distance
        elif target_pos < minpos:
            new_distance = minpos - start_pos
            distance = new_distance
        return distance

    def calc_principle_hardstop_direction(self):
        """The "principle" hardstop is the one which is struck during homing.
        (The "secondary" hardstop is only struck when finding the total available travel range.)
        """
        if self.axisid == pc.T:
            return self.posmodel.state._val['PRINCIPLE_HARDSTOP_DIR_T']
        else:
            return self.posmodel.state._val['PRINCIPLE_HARDSTOP_DIR_P']

    def calc_antibacklash_final_move_dir(self):
        if self.axisid == pc.T:
            return self.posmodel.state._val['ANTIBACKLASH_FINAL_MOVE_DIR_T']
        else:
            return self.posmodel.state._val['ANTIBACKLASH_FINAL_MOVE_DIR_P']

    def calc_hardstop_debounce(self):
        """This is the amount to debounce off the hardstop after striking it.
        It is the hardstop clearance distance plus the backlash removal distance.
        Returns [1x2] array of [min,max]
        """
        h = self.hardstop_clearance
        b = self.backlash_clearance
        return [h[0] + b[0], h[1] + b[1]]

    def calc_hardstop_clearance(self):
        """Minimum distance to stay clear from hardstop.
        Returns [1x2] array of [clearance_at_min_limit, clearance_at_max_limit].
        These are DIRECTIONAL quantities (i.e., the sign indicates the direction
        in which one would debounce after hitting the given hardstop, to get
        back into the accessible range).
        """
        if self.axisid == pc.T:
            if self.principle_hardstop_direction < 0:
                return [+self.posmodel.state._val['PRINCIPLE_HARDSTOP_CLEARANCE_T'],
                        -self.posmodel.state._val['SECONDARY_HARDSTOP_CLEARANCE_T']]
            else:
                return [+self.posmodel.state._val['SECONDARY_HARDSTOP_CLEARANCE_T'],
                        -self.posmodel.state._val['PRINCIPLE_HARDSTOP_CLEARANCE_T']]
        else:
            if self.principle_hardstop_direction < 0:
                return [+self.posmodel.state._val['PRINCIPLE_HARDSTOP_CLEARANCE_P'],
                        -self.posmodel.state._val['SECONDARY_HARDSTOP_CLEARANCE_P']]
            else:
                return [+self.posmodel.state._val['SECONDARY_HARDSTOP_CLEARANCE_P'],
                        -self.posmodel.state._val['PRINCIPLE_HARDSTOP_CLEARANCE_P']]

    def calc_hardstop_clearance_near_full_range(self):
        """Slightly less clearance than provided by the calc_hardstop_clearance
        function.
        Returns 1x2 array of [clearance_from_low_side_of_range, clearance_from_high_side].
        These are DIRECTIONAL quantities (i.e., the sign indicates the direction
        similarly as the hardstop clearance directions).
        """
        h = self.hardstop_clearance
        return [x * pc.near_full_range_reduced_hardstop_clearance_factor for x in h]

    def calc_backlash_clearance(self):
        """Minimum clearance distance required for backlash removal moves.
        Returns 1x2 array of [clearance_from_low_side_of_range, clearance_from_high_side].
        These are DIRECTIONAL quantities (i.e., the sign indicates the direction
        similarly as the hardstop clearance directions).
        """
        if self.antibacklash_final_move_dir > 0:
            return [+self.posmodel.state._val['BACKLASH'],0]
        else:
            return [0,-self.posmodel.state._val['BACKLASH']]
        