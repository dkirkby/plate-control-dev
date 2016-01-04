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

        # List of particular PosState parameters that modify internal details of how a move
        # gets divided into cruise / creep, antibacklash moves added, etc. What distinguishes
        # these parameters is that they specify particular *modes* of motion. They are not
        # calibration parameters or id #s or the like.
        self.default_move_options = {'BACKLASH_REMOVAL_ON'  : True,
                                     'FINAL_CREEP_ON'       : True,
                                     'ALLOW_EXCEED_LIMITS'  : False,
                                     'ONLY_CREEP'           : False}

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
            'x'      ... float, mm,  dependent variable, expected global x position
            'y'      ... float, mm,  dependent variable, expected global y position
            'obsT'   ... float, deg, dependent variable, expected position of theta axis, as seen by an external observer (includes offsets, calibrations)
            'obsP'   ... float, deg, dependent variable, expected position of phi axis, as seen by an external observer (includes offsets, calibrations)
            'shaftT' ... float, deg, independent variable, the internally-tracked expected position of the theta shaft at the output of the gearbox
            'shaftP' ... float, deg, independent variable, the internally-tracked expected position of the phi shaft at the output of the gearbox
            'motorT' ... float, deg, dependent variable, expected position of theta motor
            'motorP' ... float, deg, dependent variable, expected position of phi motor
        """
        shaftTP = [self.axis[pc.T].pos, self.axis[pc.P].pos]
        d = {}
        d['shaftT'] = shaftTP[0]
        d['shaftP'] = shaftTP[1]
        d['motorT'] = d['shaftT'] * self.axis[pc.T].gear_ratio
        d['motorP'] = d['shaftP'] * self.axis[pc.P].gear_ratio
        obsTP = self.trans.shaftTP_to_obsTP(shaftTP)
        d['obsT'] = obsTP[0]
        d['obsP'] = obsTP[1]
        obsXY = self.trans.shaftTP_to_obsXY(shaftTP)
        d['x'] = obsXY[0]
        d['y'] = obsXY[1]
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
        s = 'Q:{:7.3f}{}, S:{:7.3f}{} | x:{:7.3f}{}, y:{:7.3f}{} | obsT:{:8.3f}{}, obsP:{:8.3f}{} | motorT:{:8.1f}{}, motorP:{:8.1f}{}'. \
            format(pos['Q'],mm, pos['S'],deg,
                   pos['x'],mm, pos['y'],mm,
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

    def true_move(self, axisid, distance, options=[], expected_prior_dTdP=[0,0]):
        """Input move distance on either the theta or phi axis, as seen by the
        observer, in degrees.

        The optional argument 'options' is a dictionary that can be used to specify
        several flags that control particular modes of motor operation. See comments
        on the parameter 'default_move_options' for more detail on this.

        Outputs are quantized distance [deg], speed [deg/sec], integer number of
        motor steps, speed mode ['cruise' or 'creep'], and move time [sec]

        The return values are formatted as a dictionary of lists. (This handles the
        case where if it's a "final" move, it really consists of multiple submoves.)

        The optional argument 'expected_prior_dTdP' is used to account for expected
        future shaft position changes. This is necessary for correct checking of
        software travel limits, when a sequence of multiple moves is being planned out.
        """
        if not(options):
            options = self.default_move_options
        options = options.copy() # don't disturb the input
        pos = self.expected_current_position
        shaft_start = [pos['shaftT'] + expected_prior_dTdP[0], pos['shaftP'] + expected_prior_dTdP[1]]
        obs_start = self.trans.shaftTP_to_obsTP(shaft_start)
        obs_finish = obs_start.copy()
        obs_finish[axisid] += distance
        shaft_finish = self.trans.obsTP_to_shaftTP(obs_finish)
        dist = shaft_finish[axisid] - shaft_start[axisid]
        if not(options['ALLOW_EXCEED_LIMITS']):
            dist = self.axis[axisid].truncate_to_limits(dist,shaft_start[axisid])
        gear_ratio = self.axis[axisid].gear_ratio
        ccw_sign = self.axis[axisid].ccw_sign
        dist *= gear_ratio
        dist *= ccw_sign
        antibacklash_final_move_dir = ccw_sign * self.axis[axisid].antibacklash_final_move_dir
        backlash_magnitude = gear_ratio * self.state.read('BACKLASH') * options['BACKLASH_REMOVAL_ON']
        if np.sign(dist) == antibacklash_final_move_dir:
            final_move  = np.sign(dist) * backlash_magnitude
            undershoot  = -final_move * self.state.read('BACKLASH_REMOVAL_BACKUP_FRACTION')
            backup_move = -(final_move + undershoot)
            overshoot   = 0;
        else:
            final_move  = -np.sign(dist) * backlash_magnitude
            undershoot  = 0
            backup_move = 0
            overshoot   = -final_move
        primary_move = dist + overshoot + undershoot

        opt = {}
        move_data = {}
        options['CRUISE_SHY_OF_TARGET'] = False # usually false, except in the special case below
        opt['primary'] = options.copy()
        opt['backup']  = options.copy()
        opt['final']   = options.copy()
        if final_move: # in this special case, don't need a creep move after the primary, since we will later do another final move anyway. however, still want to stay shy of the final target
            opt['primary']['FINAL_CREEP_ON']       = False
            opt['primary']['CRUISE_SHY_OF_TARGET'] = True
        opt['backup']['ONLY_CREEP'] = True
        opt['final'] ['ONLY_CREEP'] = True
        i = 0
        for m in [[primary_move,opt['primary']], [backup_move,opt['backup']], [final_move,opt['final']]]:
            true_move = None
            if i == 0:
                true_move = self.motor_true_move(axisid, m[0], m[1])
                dist_correction = m[0] - sum(true_move['obs_distance']) # note, it is intentional that this will only be used when there was already a plan to do a non-zero final_move
            if i == 1 and m[0]:
                true_move = self.motor_true_move(axisid, m[0], m[1])
            if i == 2 and m[0]:
                true_move = self.motor_true_move(axisid, m[0] + dist_correction, m[1])
            if true_move:
                for key in true_move.keys():
                    if not(key in move_data.keys()):
                        move_data[key] = []
                    move_data[key].extend(true_move[key])
            i += 1
        n_submoves = len(move_data['obs_distance'])
        for i in range(n_submoves):
            move_data['obs_distance'][i] *= ccw_sign / gear_ratio
            move_data['obs_speed'][i]    *= ccw_sign / gear_ratio
        return move_data

    def motor_true_move(self, axisid, distance, options):
        """Calculation of cruise, creep, spinup, and spindown details for a move of
        an argued distance on the axis identified by axisid.
        """
        move_data = {'obs_distance' : [],
                     'obs_speed'    : [],
                     'motor_step'   : [],
                     'speed_mode'   : [],
                     'move_time'    : []}
        dist_spinup = 2 * np.sign(distance) * self._spinupdown_distance
        if options['ONLY_CREEP'] or (abs(distance) <= (abs(dist_spinup) + self.state.read('NOM_FINAL_CREEP_DIST'))):
            dist_spinup     = 0
            dist_cruise     = 0
            steps_cruise    = 0
            dist_cruisespin = 0
            net_dist_creep  = distance
        else:
            dist_creep      = np.sign(distance) * self.state.read('NOM_FINAL_CREEP_DIST') * options['FINAL_CREEP_ON']      # initial guess at how far to creep
            dist_shy        = np.sign(distance) * self.state.read('NOM_FINAL_CREEP_DIST') * options['CRUISE_SHY_OF_TARGET']  # when ya ain't creepin' this time but ya know you will real soon
            dist_cruise     = distance - dist_spinup - dist_creep - dist_shy      # initial guess at how far to cruise
            steps_cruise    = round(dist_cruise / self._stepsize_cruise)          # quantize cruise steps
            dist_cruisespin = steps_cruise * self._stepsize_cruise + dist_spinup  # actual distance covered while cruising
            net_dist_creep  = (distance - dist_cruisespin) * options['FINAL_CREEP_ON']
        steps_creep = round(net_dist_creep / self._stepsize_creep)
        dist_creep = steps_creep * self._stepsize_creep
        if steps_cruise:
            move_data['obs_distance'].append(dist_cruisespin)
            move_data['obs_speed'].append(self._motor_speed_cruise)
            move_data['motor_step'].append(round(float(steps_cruise))) # round() rather than int() to prevent flooring the value
            move_data['speed_mode'].append('cruise')
            move_data['move_time'].append((abs(steps_cruise)*self._stepsize_cruise + 4*self._spinupdown_distance) / self._motor_speed_cruise)
        if steps_creep:
            move_data['obs_distance'].append(dist_creep)
            move_data['obs_speed'].append(self._motor_speed_creep)
            move_data['motor_step'].append(round(float(steps_creep))) # round() rather than int() to prevent flooring the value
            move_data['speed_mode'].append('creep')
            move_data['move_time'].append(abs(steps_creep)*self._stepsize_creep / self._motor_speed_creep)
        return move_data

    def postmove_cleanup(self, cleanup_table, lognote=''):
        """Always perform this after positioner physical moves have been completed,
        to update the internal tracking of shaft positions and variables.
        """
        self.axis[pc.T].pos += sum(cleanup_table['dT'])
        self.axis[pc.P].pos += sum(cleanup_table['dP'])
        for axis in self.axis:
            exec(axis.postmove_cleanup_cmds)
            axis.postmove_cleanup_cmds = ''
        separator = '; '
        self.state.write('LAST_MOVE_CMD',  separator.join(cleanup_table['cmd']))
        self.state.write('LAST_MOVE_VAL1', separator.join(['{0:.6g}'.format(x) for x in cleanup_table['cmd_val1']]))
        self.state.write('LAST_MOVE_VAL2', separator.join(['{0:.6g}'.format(x) for x in cleanup_table['cmd_val2']]))
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
        start_tp = [pos['shaftT'] + expected_prior_dTdP[0], pos['shaftP'] + expected_prior_dTdP[1]]
        if   movecmd == 'qs':
            targt_xy = self.trans.QS_to_obsXY(vals)
            (targt_tp,unreachable) = self.trans.obsXY_to_shaftTP(targt_xy)
        elif movecmd == 'dqds':
            start_xy = self.trans.shaftTP_to_obsXY(start_tp)
            start_qs = self.trans.obsXY_to_QS(start_xy)
            targt_qs = (np.array(start_PQ) + np.array(vals)).tolist()
            targt_xy = self.trans.QS_to_obsXY(targt_qs)
            (targt_tp,unreachable) = self.trans.obsXY_to_shaftTP(targt_xy)
        elif movecmd == 'xy':
            (targt_tp,unreachable) = self.trans.obsXY_to_shaftTP(vals)
        elif movecmd == 'dxdy':
            start_xy = self.trans.shaftTP_to_obsXY(start_tp)
            targt_xy = (np.array(start_xy) + np.array(vals)).tolist()
            (targt_tp,unreachable) = self.trans.obsXY_to_shaftTP(targt_xy)
        elif movecmd == 'tp':
            targt_tp = vals
        elif movecmd == 'dtdp':
            targt_tp = (np.array(start_tp) + np.array(vals)).tolist()
        elif movecmd == 'home':
            for a in self.axis:
                table.extend(a.seek_and_set_limits_sequence())
            return table
        elif movecmd == 'seeklimit':
            search_dist = []
            search_dist[pc.T] = np.sign(val1)*self.axis[pc.T].limit_seeking_search_distance()
            search_dist[pc.P] = np.sign(val2)*self.axis[pc.P].limit_seeking_search_distance()
            old_SHOULD_DEBOUNCE_HARDSTOPS = self.state.read('SHOULD_DEBOUNCE_HARDSTOPS')
            self.state.write('SHOULD_DEBOUNCE_HARDSTOPS',0)
            for i in [pc.T,pc.P]:
                table.extend(self.axis[i].seek_one_limit_sequence(search_dist[i]))
            self.state.write('SHOULD_DEBOUNCE_HARDSTOPS',old_SHOULD_DEBOUNCE_HARDSTOPS)
            return table
        else:
            print( 'move command ' + repr(movecmd) + ' not recognized')
            return []

        delta_t = targt_tp[0] - start_tp[0]
        delta_p = targt_tp[1] - start_tp[1]
        table.set_move(0, pc.T, delta_t)
        table.set_move(0, pc.P, delta_p)
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
        """Internally-tracked angular position of the axis. By definition pos = (motor shaft position) / (gear ratio).
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
            targetable_range = abs(self.posmodel.state.read('PHYSICAL_RANGE_T'))
            return [-0.50*targetable_range, 0.50*targetable_range]  # split theta range such that 0 is essentially in the middle
        else:
            targetable_range = abs(self.posmodel.state.read('PHYSICAL_RANGE_P'))
            return [-0.01*targetable_range, 0.99*targetable_range]  # split phi range such that 0 is essentially at the minimum

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
    def gear_ratio(self):
        if self.axisid == pc.T:
            return self.posmodel.state.read('GEAR_T')
        else:
            return self.posmodel.state.read('GEAR_P')

    @property
    def ccw_sign(self):
        if self.axisid == pc.T:
            return self.posmodel.state.read('MOTOR_CCW_DIR_T')
        else:
            return self.posmodel.state.read('MOTOR_CCW_DIR_P')

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

    def truncate_to_limits(self, distance, expected_pos=None):
        """Return distance after first truncating it (if necessary) according to software limits.
        An expected starting position can optionally be argued. If None, then the internally-
        tracked position is used as the starting point.
        """
        if not(self.posmodel.state.read('ALLOW_EXCEED_LIMITS')):
            if expected_pos == None:
                expected_pos = self.pos
            target_pos = expected_pos + distance
            if self.maxpos < self.minpos:
                distance = 0
            elif target_pos > self.maxpos:
                new_distance = self.maxpos - expected_pos
                distance = new_distance
            elif target_pos < self.minpos:
                new_distance = self.minpos - expected_pos
                distance = new_distance
        return distance

    def seek_and_set_limits_sequence(self):
        """Typical routine used in homing to find the max pos, min pos and
        primary hardstop. The sequence is returned in a move table.
        """
        direction = np.sign(self.principle_hardstop_direction())
        table = self.seek_one_limit_sequence(direction * self.limit_seeking_search_distance())
        if direction > 0:
            self.postmove_cleanup_cmds += 'self.pos = self.maxpos\n'
            self.postmove_cleanup_cmds += 'self.last_primary_hardstop_dir = +1.0\n'
        elif direction < 0:
            self.postmove_cleanup_cmds += 'self.pos = self.minpos\n'
            self.postmove_cleanup_cmds += 'self.last_primary_hardstop_dir = -1.0\n'
        else:
            print( 'bad direction ' + repr(direction))
        return table

    def seek_one_limit_sequence(self, seek_distance):
        """Use to go hit a hardstop. For the distance argument, direction matters.
        The sequence is returned in a move table.
        """
        table = posmovetable.PosMoveTable(self.posmodel)
        old_allow_exceed_limits = self.posmodel.state.read('ALLOW_EXCEED_LIMITS')
        self.posmodel.state.write('ALLOW_EXCEED_LIMITS',True)
        old_only_creep = self.posmodel.state.read('ONLY_CREEP')
        if self.posmodel.state.read('CREEP_TO_LIMITS'):
            self.posmodel.state.write('ONLY_CREEP',True)
        both_debounce_vals = self.hardstop_debounce
        if self.posmodel.state.read('SHOULD_DEBOUNCE_HARDSTOPS'):
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
        self.posmodel.state.write('ALLOW_EXCEED_LIMITS',old_allow_exceed_limits)
        self.posmodel.state.write('ONLY_CREEP',old_only_creep)
        return table

