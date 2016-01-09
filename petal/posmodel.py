import numpy as np
import posstate
import posmovetable
import postransforms
import posconstants as pc

class PosModel(object):
    """Software model of the physical positioner hardware.
    Takes in local (x,y) or (th,phi) targets, move speeds, converts
    to degrees of motor shaft rotation, speed, and type of move (such
    as cruise / creep / backlash / hardstop approach).

    One instance of PosModel corresponds to one PosState to physical positioner.
    But we will consider refactoring to array-wise later on.
    """

    def __init__(self, state=None):
        if not(state):
            self.state = posstate.PosState()
        else:
            self.state = state
        self.trans = postransforms.PosTransforms(self)

        # axes
        self.axis = [None,None]
        self.axis[pc.T] = Axis(self,pc.T)
        self.axis[pc.P] = Axis(self,pc.P)

        # internal motor/driver constants
        self._timer_update_rate    = 18e3   # Hz
        self._stepsize_creep       = 0.1    # deg
        self._stepsize_cruise      = 3.3    # deg
        self._motor_speed_cruise   = 9900.0 * 360.0 / 60.0  # deg/sec (= RPM *360/60)
        self._legacy_spinupdown    = True   # flag to enable using old firmware's fixed spinupdown_distance

    @property
    def _motor_speed_creep(self):
        """Returns motor creep speed (which depends on the creep period) in deg/sec."""
        return self._timer_update_rate * self._stepsize_creep / self.state.read('CREEP_PERIOD')  # deg/sec

    @property
    def _spinupdown_distance(self):
        """Returns distance at the motor shaft in deg over which to spin up to cruise speed or down from cruise speed."""
        if self._legacy_spinupdown:
            return 628.2  # deg
        else:
            return sum(range(round(self._stepsize_cruise/self._stepsize_creep) + 1))*self._stepsize_creep * self.state.read('SPINUPDOWN_PERIOD')

    @property
    def expected_current_position(self):
        """Returns a dictionary of the current expected position in the various coordinate systems.
        The keys are:
            'Q'      ... float, deg, dependent variable, expected global Q position
            'S'      ... float, mm,  dependent variable, expected global S position
            'obsX'   ... float, mm,  dependent variable, expected global x position
            'obsY'   ... float, mm,  dependent variable, expected global y position
            'obsT'   ... float, deg, dependent variable, expected position of theta axis, including offsets as seen by an external observer
            'obsP'   ... float, deg, dependent variable, expected position of phi axis, including offsets as seen by an external observer
            'shaftT' ... float, deg, independent variable, the internally-tracked expected position of the theta shaft at the output of the gearbox
            'shaftP' ... float, deg, independent variable, the internally-tracked expected position of the phi shaft at the output of the gearbox
            'motorT' ... float, deg, dependent variable, expected position of theta motor
            'motorP' ... float, deg, dependent variable, expected position of phi motor
        """
        shaftTP = [self.axis[pc.T].pos, self.axis[pc.P].pos]
        d = {}
        d['shaftT'] = shaftTP[0]
        d['shaftP'] = shaftTP[1]
        d['motorT'] = self.axis[pc.T].shaft_to_motor(d['shaftT'])
        d['motorP'] = self.axis[pc.P].shaft_to_motor(d['shaftP'])
        obsTP = self.trans.shaftTP_to_obsTP(shaftTP)
        d['obsT'] = obsTP[0]
        d['obsP'] = obsTP[1]
        obsXY = self.trans.shaftTP_to_obsXY(shaftTP)
        d['obsX'] = obsXY[0]
        d['obsY'] = obsXY[1]
        QS = self.trans.obsXY_to_QS(obsXY)
        d['Q'] = QS[0]
        d['S'] = QS[1]
        return d

    @property
    def expected_current_position_str(self):
        """One-line string summarizing current expected position.
        """
        deg = '\u00b0'
        mm = 'mm'
        pos = self.expected_current_position
        s = 'Q:{:7.3f}{}, S:{:7.3f}{} | obsX:{:7.3f}{}, obsY:{:7.3f}{} | obsT:{:8.3f}{}, obsP:{:8.3f}{} | motorT:{:8.1f}{}, motorP:{:8.1f}{}'. \
            format(pos['Q'],mm, pos['S'],deg,
                   pos['obsX'],mm, pos['obsY'],mm,
                   pos['obsT'],deg, pos['obsP'],deg,
                   pos['motorT'],deg, pos['motorP'],deg)
        return s

    @property
    def targetable_range_T(self):
        """Returns a [1x2] array of theta_min, theta_max, after subtracting buffer zones near the hardstops."""
        return self.axis[pc.T].debounced_range

    @property
    def targetable_range_P(self):
        """Returns a [1x2] array of phi_min, phi_max, after subtracting buffer zones near the hardstops."""
        return self.axis[pc.P].debounced_range

    @property
    def full_range_T(self):
        """Returns a [1x2] array of [theta_min, theta_max], from hardstop-to-hardstop."""
        return self.axis[pc.T].full_range

    @property
    def full_range_P(self):
        """Returns a [1x2] array of [phi_min, phi_max], from hardstop-to-hardstop."""
        return self.axis[pc.P].full_range

    def true_move(self, axisid, distance, allow_cruise, allow_exceed_limits, expected_prior_dTdP=[0,0]):
        """Input move distance on either the theta or phi axis, as seen by the
        observer, in degrees.

        The return values are formatted as a dictionary, with keys:
            'motor_step'   ... integer number of motor steps, signed according to direction
            'move_time'    ... total time the move takes [sec]
            'distance'     ... quantized distance of travel [deg], signed according to direction
            'speed'        ... approximate speed of travel [deg/sec]. unsigned. note 'move_time' is preferred for precision timing calculations
            'speed_mode'   ... 'cruise' or 'creep'

        The argument 'expected_prior_dTdP' is used to account for expected
        future shaft position changes. This is necessary for correct checking of
        software travel limits, when a sequence of multiple moves is being planned out.
        """
        pos = self.expected_current_position
        shaft_start = self.trans.addto_shaftTP([pos['shaftT'],pos['shaftP']], expected_prior_dTdP, range_wrap_limits='none') # since expected_prior_dTdP is just tracking already-existing commands, do not perform range wrapping on it
        if not(allow_exceed_limits):
            distance = self.axis[axisid].truncate_to_limits(distance,shaft_start[axisid])
        motor_dist = self.axis[axisid].shaft_to_motor(distance)
        move_data = self.motor_true_move(axisid, motor_dist, allow_cruise)
        move_data['distance'] = self.axis[axisid].motor_to_shaft['distance']
        move_data['speed']    = self.axis[axisid].motor_to_shaft['speed']
        return move_data

    def motor_true_move(self, axisid, distance, allow_cruise):
        """Calculation of cruise, creep, spinup, and spindown details for a move of
        an argued distance on the axis identified by axisid.
        """
        move_data = {}
        dist_spinup = 2 * np.sign(distance) * self._spinupdown_distance  # distance over which accel / decel to and from cruise speed
        if not(allow_cruise) or abs(distance) <= (abs(dist_spinup) + self.state.read('MIN_DIST_AT_CRUISE_SPEED')):
            move_data['motor_step']   = round(distance / self._stepsize_creep)
            move_data['distance']     = move_data['motor_step'] * self._stepsize_creep
            move_data['speed_mode']   = 'creep'
            move_data['speed']        = self._motor_speed_creep
            move_data['move_time']    = abs(move_data['distance']) / move_data['speed']
        else:
            dist_cruise = distance - dist_spinup
            move_data['motor_step']   = round(dist_cruise / self._stepsize_cruise)
            move_data['distance']     = move_data['motor_step'] * self._stepsize_cruise + dist_spinup
            move_data['speed_mode']   = 'cruise'
            move_data['speed']        = self._motor_speed_cruise
            move_data['move_time']    = (abs(move_data['motor_step'])*self._stepsize_cruise + 4*self._spinupdown_distance) / move_data['speed']
        return move_data

    def postmove_cleanup(self, cleanup_table, lognote=''):
        """Always perform this after positioner physical moves have been completed,
        to update the internal tracking of shaft positions and variables.
        """
        self.state.write('SHAFT_T', self.state.read('SHAFT_T') + cleanup_table['stats']['net_dT'][-1])
        self.state.write('SHAFT_P', self.state.read('SHAFT_P') + cleanup_table['stats']['net_dP'][-1])
        for axis in self.axis:
            exec(axis.postmove_cleanup_cmds)
            axis.postmove_cleanup_cmds = ''
        separator = '; '
        self.state.write('LAST_MOVE_CMD',  separator.join(cleanup_table['command']))
        self.state.write('LAST_MOVE_VAL1', separator.join(['{0:.6g}'.format(x) for x in cleanup_table['cmd_val1']]))
        self.state.write('LAST_MOVE_VAL2', separator.join(['{0:.6g}'.format(x) for x in cleanup_table['cmd_val2']]))
        self.state.write('TOTAL_CRUISE_MOVES_T', self.state.read('TOTAL_CRUISE_MOVES_T') + cleanup_table['stats']['TOTAL_CRUISE_MOVES_T'])
        self.state.write('TOTAL_CRUISE_MOVES_P', self.state.read('TOTAL_CRUISE_MOVES_P') + cleanup_table['stats']['TOTAL_CRUISE_MOVES_P'])
        self.state.write('TOTAL_CREEP_MOVES_T', self.state.read('TOTAL_CREEP_MOVES_T') + cleanup_table['stats']['TOTAL_CREEP_MOVES_T'])
        self.state.write('TOTAL_CREEP_MOVES_P', self.state.read('TOTAL_CREEP_MOVES_P') + cleanup_table['stats']['TOTAL_CREEP_MOVES_P'])
        self.state.write('TOTAL_MOVE_SEQUENCES', self.state.read('TOTAL_MOVE_SEQUENCES') + 1)
        self.state.log_unit(lognote)

    def make_move_table(self, movecmd, val1, val2, expected_prior_dTdP=[0,0]):
        """Generate a move table for a given move command string. Generally
        for expert or internal use only.

        Move command strings:

          'pq'        ... move to absolute position (P,Q)

          'xy'        ... move to absolute position (x,y)

          'tp'        ... move to absolute position (theta, phi)

          'dpdq'      ... move by a relative amount (delta P, delta Q)

          'dxdy'      ... move by a relative amount (delta x, delta y)

          'dtdp'      ... move by a relative amount (delta theta, delta phi

          'home'      ... find the primary hardstops on both axes, then debounce off them
                              ... val1 and val2 are both ignored

          'seeklimit' ... find the argued hardstop, but do NOT debounce off it
                              ... sign of val1 or val2 says which direction to seek
                              ... finite magnitudes of val1 or val2 are ignored
                              ... val1 == 0 or val2 == 0 says do NOT seek on that axis

        The optional argument 'expected_prior_dTdP' is used to account for expected
        future shaft position changes. This is necessary for correct checking of
        software travel limits, when a sequence of multiple moves is being planned out.
        """
        table = posmovetable.PosMoveTable(self)
        vals = [val1,val2]
        pos = self.expected_current_position
        start_tp = self.trans.addto_shaftTP([pos['shaftT'],pos['shaftP']], expected_prior_dTdP, range_wrap_limits='none') # since expected_prior_dTdP is just tracking already-existing commands, do not perform range wrapping on it
        range_wrap_limits = 'targetable'
        if   movecmd == 'qs':
            (targt_tp,unreachable) = self.trans.QS_to_shaftTP(vals)
        elif movecmd == 'dqds':
            start_qs = self.trans.shaftTP_to_QS(start_tp)
            targt_qs = self.trans.addto_QS(start_qs,vals)
            (targt_tp,unreachable) = self.trans.QS_to_shaftTP(vals)
        elif movecmd == 'xy':
            (targt_tp,unreachable) = self.trans.obsXY_to_shaftTP(vals)
        elif movecmd == 'dxdy':
            start_xy = self.trans.shaftTP_to_obsXY(start_tp)
            targt_xy = self.trans.addto_obsXY(start_xy,vals)
            (targt_tp,unreachable) = self.trans.obsXY_to_shaftTP(targt_xy)
        elif movecmd == 'tp':
            targt_tp = vals
        elif movecmd == 'dtdp':
            range_wrap_limits = 'none'
            targt_tp = self.trans.addto_shaftTP(start_tp,vals,range_wrap_limits)
        elif movecmd == 'home':
            for a in self.axis:
                table.extend(a.seek_and_set_limits_sequence())
            return table
        elif movecmd == 'seeklimit':
            search_dist = []
            search_dist[pc.T] = np.sign(val1)*self.axis[pc.T].limit_seeking_search_distance()
            search_dist[pc.P] = np.sign(val2)*self.axis[pc.P].limit_seeking_search_distance()
            for i in [pc.T,pc.P]:
                table.extend(self.axis[i].seek_one_limit_sequence(search_dist[i], should_debounce_hardstops=False))
            return table
        else:
            print( 'move command ' + repr(movecmd) + ' not recognized')
            return []

        dtdp = self.trans.delta_shaftTP(targt_tp,start_tp,range_wrap_limits)
        table.set_move(0, pc.T, dtdp[0])
        table.set_move(0, pc.P, dtdp[1])
        table.store_orig_command(0,movecmd,val1,val2)
        return table


class Axis(object):
    """Handler for a motion axis. Provides move syntax and keeps tracks of position.
    """

    def __init__(self, posmodel, axisid):
        self.posmodel = posmodel
        if not(axisid == pc.T or axisid == pc.P):
            print( 'warning: bad axis id ' + repr(axisid))
        self.axisid = axisid
        self.postmove_cleanup_cmds = ''

    @property
    def pos(self):
        """Internally-tracked angular position of the axis, at the output of the gear.
        """
        if self.axisid == pc.T:
            return self.posmodel.state.read('SHAFT_T')
        else:
            return self.posmodel.state.read('SHAFT_P')

    @pos.setter
    def pos(self,value):
        if self.axisid == pc.T:
            self.posmodel.state.write('SHAFT_T',value)
        else:
            self.posmodel.state.write('SHAFT_P',value)

    @property
    def full_range(self):
        """Calculated from physical range only, with no subtraction of debounce
        distance.
        Returns [1x2] array of [min,max]
        """
        if self.axisid == pc.T:
            r = abs(self.posmodel.state.read('PHYSICAL_RANGE_T'))
            return [-0.50*r, 0.50*r]  # split theta range such that 0 is essentially in the middle
        else:
            r = abs(self.posmodel.state.read('PHYSICAL_RANGE_P'))
            return [-0.01*r, 0.99*r]  # split phi range such that 0 is essentially at the minimum

    @property
    def debounced_range(self):
        """Calculated from full range, accounting for removal of both the hardstop
        clearance distances and the backlash removal distance.
        Returns [1x2] array of [min,max]
        """
        return (np.array(self.full_range) + np.array(self.hardstop_debounce)).tolist()

    @property
    def maxpos(self):
        if self.last_primary_hardstop_dir >= 0:
            return max(self.debounced_range)
        else:
            return self.minpos + np.diff(self.debounced_range)[0]

    @property
    def minpos(self):
        if self.last_primary_hardstop_dir < 0:
            return min(self.debounced_range)
        else:
            return self.maxpos - np.diff(self.debounced_range)[0]

    @property
    def hardstop_debounce(self):
        """This is the amount to debounce off the hardstop after striking it.
        It is the hardstop clearance distance plus the backlash removal distance.
        Returns [1x2] array of [min,max]
        """
        return (np.array(self.hardstop_clearance) + np.array(self.backlash_clearance)).tolist()

    @property
    def hardstop_clearance(self):
        """Minimum distance to stay clear from hardstop.
        Returns [1x2] array of [clearance_at_min_limit, clearance_at_max_limit].
        These are DIRECTIONAL quantities (i.e., the sign indicates the direction
        in which one would debounce after hitting the given hardstop, to get
        back into the accessible range).
        """
        if self.axisid == pc.T:
            if self.principle_hardstop_direction < 0:
                return [+self.posmodel.state.read('PRINCIPLE_HARDSTOP_CLEARANCE_T'),
                        -self.posmodel.state.read('SECONDARY_HARDSTOP_CLEARANCE_T')]
            else:
                return [+self.posmodel.state.read('SECONDARY_HARDSTOP_CLEARANCE_T'),
                        -self.posmodel.state.read('PRINCIPLE_HARDSTOP_CLEARANCE_T')]
        else:
            if self.principle_hardstop_direction < 0:
                return [+self.posmodel.state.read('PRINCIPLE_HARDSTOP_CLEARANCE_P'),
                        -self.posmodel.state.read('SECONDARY_HARDSTOP_CLEARANCE_P')]
            else:
                return [+self.posmodel.state.read('SECONDARY_HARDSTOP_CLEARANCE_P'),
                        -self.posmodel.state.read('PRINCIPLE_HARDSTOP_CLEARANCE_P')]

    @property
    def backlash_clearance(self):
        """Minimum clearance distance required for backlash removal moves.
        Returns 1x2 array of [clearance_from_low_side_of_range, clearance_from_high_side].
        These are DIRECTIONAL quantities (i.e., the sign indicates the direction
        similarly as the hardstop clearance directions).
        """
        if self.antibacklash_final_move_dir > 0:
            return [+self.posmodel.state.read('BACKLASH'),0]
        else:
            return [0,-self.posmodel.state.read('BACKLASH')]

    @property
    def motor_calib_properties(self):
        """Return properties for motor calibration.
        """
        if self.axisid == pc.T:
            prop['gear_ratio'] = pc.gear_ratio[posmodel.state.read('GEAR_TYPE_T')]
            prop['gear_calib'] = self.posmodel.state.read('GEAR_CALIB_T')
            prop['ccw_sign'] = self.posmodel.state.read('MOTOR_CCW_DIR_T')
        else:
            prop['gear_ratio'] = pc.gear_ratio[posmodel.state.read('GEAR_TYPE_P')]
            prop['gear_calib'] = self.posmodel.state.read('GEAR_CALIB_P')
            prop['ccw_sign'] = self.posmodel.state.read('MOTOR_CCW_DIR_P')
        return prop

    @property
    def antibacklash_final_move_dir(self):
        if self.axisid == pc.T:
            return self.posmodel.state.read('ANTIBACKLASH_FINAL_MOVE_DIR_T')
        else:
            return self.posmodel.state.read('ANTIBACKLASH_FINAL_MOVE_DIR_P')

    @property
    def last_primary_hardstop_dir(self):
        if self.axisid == pc.T:
            return self.posmodel.state.read('LAST_PRIMARY_HARDSTOP_DIR_T')
        else:
            return self.posmodel.state.read('LAST_PRIMARY_HARDSTOP_DIR_P')

    @last_primary_hardstop_dir.setter
    def last_primary_hardstop_dir(self,value):
        if self.axisid == pc.T:
            self.posmodel.state.write('LAST_PRIMARY_HARDSTOP_DIR_T',value)
        else:
            self.posmodel.state.write('LAST_PRIMARY_HARDSTOP_DIR_P',value)

    @property
    def total_limit_seeks(self):
        if self.axisid == pc.T:
            return self.posmodel.state.read('TOTAL_LIMIT_SEEKS_T')
        else:
            return self.posmodel.state.read('TOTAL_LIMIT_SEEKS_P')

    @total_limit_seeks.setter
    def total_limit_seeks(self,value):
        if self.axisid == pc.T:
            self.posmodel.state.write('TOTAL_LIMIT_SEEKS_T',value)
        else:
            self.posmodel.state.write('TOTAL_LIMIT_SEEKS_P',value)

    @property
    def principle_hardstop_direction(self):
        """The "principle" hardstop is the one which is struck during homing.
        (The "secondary" hardstop is only struck when finding the total available travel range.)
        """
        if self.axisid == pc.T:
            return self.posmodel.state.read('PRINCIPLE_HARDSTOP_DIR_T')
        else:
            return self.posmodel.state.read('PRINCIPLE_HARDSTOP_DIR_P')

    @property
    def limit_seeking_search_distance(self):
        """A distance magnitude that guarantees hitting a hard limit in either direction.
        """
        return np.abs(np.diff(self.full_range)*self.posmodel.state.read('LIMIT_SEEK_EXCEED_RANGE_FACTOR'))

    def motor_to_shaft(self,distance):
        """Convert a distance in motor angle to shaft angle at the gearbox output.
        """
        p = self.motor_calib_properties
        return distance * prop['ccw_sign'] / (p['gear_ratio'] * p['gear_calib'])

    def shaft_to_motor(self,distance):
        """Convert a distance in shaft angle to motor angle at the gearbox output.
        """
        p = self.motor_calib_properties
        return distance * prop['ccw_sign'] * (p['gear_ratio'] * p['gear_calib'])

    def truncate_to_limits(self, distance, start_pos=None):
        """Return distance after truncating it (if necessary) to the software limits.
        An expected starting position can optionally be argued. If None, then the internally-
        tracked position is used as the starting point.
        """
        if start_pos == None:
            start_pos = self.pos
        target_pos = start_pos + distance
        if self.maxpos < self.minpos:
            distance = 0
        elif target_pos > self.maxpos:
            new_distance = self.maxpos - start_pos
            distance = new_distance
        elif target_pos < self.minpos:
            new_distance = self.minpos - start_pos
            distance = new_distance
        return distance

    def seek_and_set_limits_sequence(self):
        """Typical routine used in homing to find the max pos, min pos and
        primary hardstop. The sequence is returned in a move table.
        """
        direction = np.sign(self.principle_hardstop_direction())
        table = self.seek_one_limit_sequence(direction * self.limit_seeking_search_distance(), should_debounce_hardstops=True)
        if direction > 0:
            self.postmove_cleanup_cmds += 'self.pos = self.maxpos\n'
            self.postmove_cleanup_cmds += 'self.last_primary_hardstop_dir = +1.0\n'
        elif direction < 0:
            self.postmove_cleanup_cmds += 'self.pos = self.minpos\n'
            self.postmove_cleanup_cmds += 'self.last_primary_hardstop_dir = -1.0\n'
        else:
            print( 'bad direction ' + repr(direction))
        self.postmove_cleanup_cmds += 'self.total_limit_seeks += 1\n'
        return table

    def seek_one_limit_sequence(self, seek_distance, should_debounce_hardstops):
        """Use to go hit a hardstop. For the distance argument, direction matters.
        The sequence is returned in a move table.
        """
        table = posmovetable.PosMoveTable(self.posmodel)
        table.should_antibacklash = False
        table.should_final_creep  = False
        table.allow_exceed_limits = True
        table.allow_cruise        = not(self.posmodel.state.read('CREEP_TO_LIMITS'))
        both_debounce_vals = self.hardstop_debounce
        if should_debounce_hardstops:
            if seek_distance < 0:
                debounce_distance = both_debounce_vals[0]
            else:
                debounce_distance = both_debounce_vals[1]
        else:
            debounce_distance = 0
        for dist in [seek_distance,debounce_distance]:
            if self.axisid == self.posmodel.T:
                val1 = dist
                val2 = 0
            else:
                val1 = 0
                val2 = dist
            table.extend(self.posmodel.make_move_table('dtdp',val1,val2))
        return table

