import posarraymaster
import fidarraymaster

class Petal(object):
    """Controls a petal. Communicates with the PetalBox hardware via PetalComm.

    The general sequence to make postioners move is:
        1. request all the desired moves from all the desired positioners
        2. schedule the moves (anti-collision and anti-backlash are automatically calculated here)
        3. send the scheduled move tables out to the positioners
        4. execute the move tables (synchronized start on all the positioners at once.

    Convenience wrapper functions are provided to combine these steps when desirable.
    """
    def __init__(self, petal_id, pos_ids, fid_ids):
        self.comm = petalcomm.PetalComm(petal_id)
        # later, implement auto-lookup of pos_ids and fid_ids from database etc
        self.pos = posarraymaster.PosArrayMaster(pos_ids, self.comm)
        self.fid = fidarraymaster.FidArrayMaster(fid_ids, self.comm)

    def request_targets(self, pos, commands, vals1, vals2):
        """Input a list of positioners and corresponding move targets to the schedule.
        This method is for requests to perform complete repositioning sequence to get
        to the targets.

            - Anticollision is enabled.
            - Only one requested target per positioner.
            - Theta angles are wrapped across +/-180 deg
            - Contact of hard limits is prevented.

        INPUTS:
            pos      ... list of positioner ids
            commands ... corresponding list of move command strings, each element is 'QS', 'dQdS', 'obsXY', 'posXY', 'dXdY', 'obsTP', 'posTP' or 'dTdP'
            vals1    ... corresponding list of first move arguments, each element is the value for q, dq, x, dx, t, or dt
            vals2    ... corresponding list of second move arguments, each element is the value for s, ds, y, dy, p, or dp
        """
        self.pos.request_targets(pos, commands, vals1, vals2)

    def request_direct_dtdp(self, pos, dt, dp, cmd_prefix=''):
        """Input a list of positioners and corresponding move targets to the schedule.
        This method is for direct requests of rotations by the theta and phi shafts.
        This method is generally recommended only for expert usage.

            - Anticollision is disabled.
            - Multiple moves allowed per positioner.
            - Theta angles are not wrapped across +/-180 deg
            - Contact of hard limits is allowed.

        INPUTS:
            pos ... list of positioner ids
            dt  ... corresponding list of delta theta values
            dp  ... corresponding list of delta phi values

        The optional argument cmd_prefix allows adding a descriptive string to the log.
        """
        self.pos.request_direct_dtdp(pos, dt, dp, cmd_prefix)

    def request_limit_seek(self, pos, axisid, direction, anticollision=True, cmd_prefix=''):
        """Request hardstop seeking sequence for positioners in list pos.
        The optional argument cmd_prefix allows adding a descriptive string to the log.
        """
        self.pos.request_limit_seek(pos, axisid, direction, anticollision, cmd_prefix)

    def request_homing(self, pos):
        """Request homing sequence for positioners in list pos to find the primary hardstop
        and set values for the max position and min position.
        """
        self.pos.request_homing(pos)

    def schedule_moves(self,anticollision=None):
        """Generate the schedule of moves and submoves that get positioners
        from start to target. Call this after having input all desired moves
        using the move request methods. Note the available boolean to turn the
        anticollision algorithm on or off for the scheduling. If that flag is
        None, then the default anticollision parameter is used.
        """
        self.pos.schedule_moves(anticollision)

    def send_move_tables(self):
        """Send move tables that have been scheduled out to the positioners.
        """
        self.pos.send_move_tables()

    def execute_moves(self):
        """Command the positioners to do the move tables that were sent out to them.
        Then do clean-up and logging routines to keep track of the moves that were done.
        """
        self.pos.execute_moves()

    def quick_move(self, pos, commands, vals1, vals2):
        """Convenience wrapper to request, schedule, send, and execute a list of moves
        to a list of positioners, all in one shot.
        """
        self.request_targets(pos, commands, vals1, vals2)
        self.schedule_send_execute()

    def quick_dtdp(self, pos, dt, dp, cmd_prefix=''):
        """Convenience wrapper to request, schedule, send, and execute a list of direct
        delta theta, delta phi moves. There is NO anti-collision calculation. This
        method is intended for expert usage only.
        """
        self.request_direct_dtdp(pos, dt, dp, cmd_prefix)
        self.schedule_send_execute()

    def schedule_send_and_execute_moves(self):
        """Convenience wrapper to schedule, send, and execute the pending requested
        moves, all in one shot.
        """
        self.schedule_moves()
        self.send_and_execute_moves()

    def send_and_execute_moves(self):
        """Convenience wrapper to send and execute the pending moves (that have already
        been scheduled).
        """
        self.send_move_tables()
        self.execute_moves()

    def fiducials_on(self):
        """Turn all the fiducials on.
        """
        self.fid.all_on()

    def fiducials_off(self):
        """Turn all the fiducials off.
        """
        self.fid.all_off()