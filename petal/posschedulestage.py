import posconstants as pc
import posmovetable

class PosScheduleStage(object):
    """This class encapsulates the concept of a 'stage' of the fiber
    positioner motion. The typical usage would be either a direct stage from
    start to finish, or an intermediate stage, used for retraction, rotation,
    or extension.

        collider     ... instance of poscollider for this petal
        anneal_time  ... Time in seconds over which to spread out moves in this stage
                         to reduce overall power density consumed by the array. You
                         can also argue None if no annealing should be done.
    """
    def __init__(self, collider, anneal_time=3, verbose=False):
        self.collider = collider # poscollider instance
        self.anneal_time = anneal_time
        self.move_tables = {} # keys: posids, values: posmovetable instances
        self.sweeps = {} # keys: posids, values: possweep instances
        
    @property
    def posids(self):
        """List of posid strings for all the positioners."""
        return self.collider.posids
    
    @property
    def posmodels(self):
        """Returns dict with key: posid string, value: posmodel instances."""
        return self.collider.posmodels
    
    def initialize_move_tables(self, start_tp, final_tp):
        """Generates basic move tables for each positioner, going straight from
        the start_tp to the final_tp.
        
            start_tp    ... dict of starting [theta,phi] positions, keys are posids
            final_tp    ... dict of final [theta,phi] positions, keys are posids
            posmodels   ... dict of posmodel instances, keys are posids
        """
        self._start_tp = start_tp
        self._final_tp = final_tp
        for posid in self._start_tp.keys():
            posmodel = self.posmodels[posid]
            dtdp = posmodel.trans.delta_posTP(final_tp[posid], start_tp[posid], range_wrap_limits='targetable')
            table = posmovetable.PosMoveTable(posmodel)
            table.set_move(0, pc.T, dtdp[0])
            table.set_move(0, pc.P, dtdp[1])
            table.set_prepause(0, 0.0)
            table.set_postpause(0, 0.0)
            self.move_tables[posid] = table

    def anneal_power_density(self):
        """Adjusts move tables internal timing, to reduce peak power consumption
        of the overall array.
        """
        if self.anneal_time == None:
            pass
        else:
            pass
        
    def find_collisions(self):
        """Identifies collisions in the current move tables.
        """
        
    def adjust_paths(self, avoidance_method='zeroth'):
        """Alters move tables to avoid collisions.
        
            avoidance_method ... Valid collision avoidance methods: 'zeroth', 'tweak', 'astar'
        """
        
    def freeze(self, posids_that_should_not_be_moved):
        """Freezes positioners in their start_tp position, so that they won't
        move at all.
        """
 
        
