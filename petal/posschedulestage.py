class PosScheduleStage(object):
    """This class encapsulates the concept of a 'stage' of the RRE plan of fiber
    positioner motion. The stage can be of several types, describing retraction,
    rotation, or extension steps.
    
        start_tp    ... dict of starting [theta,phi] positions, keys are posids
        final_tp    ... dict of final [theta,phi] positions, keys are posids
        collider    ... instanct of poscollider for this petal
        stage_type  ... 'direct', 'retract', 'rotate', 'extend'
        anneal_time ... Time in seconds over which to spread out moves in this stage
                        to reduce overall power density consumed by the array. You
                        can also argue None if no annealing should be done.
    """
    def __init__(self, start_tp, finish_tp, collider, anneal_time=3, stage_type='direct', verbose=False):
        self.collider = collider # poscollider instance
        self.move_tables = {} # keys: posids, values: posmovetable instances
        self.stage_type = stage_type
        if stage_type == 'direct':
            self.anticol_method = 'none'
        else:
            self.anticol_method = 'zeroth' # valid types: 'astar', 'zeroth', 'tweak'
        self.anneal_time = anneal_time
        
    @property
    def posids(self):
        """List of posid strings for all the positioners."""
        return self.collider.posids
    
    @property
    def posmodels(self):
        """Returns dict with key: posid string, value: posmodel instances."""
        return self.collider.posmodels
    
    def initialize_move_tables(self):
        """Generates basic move tables for each positioner, going straight from
        the start_tp to the final_tp.
        """

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
        
    def adjust_paths(self):
        """Alters move tables to avoid collisions.
        """
        
    def freeze(self, posids_that_should_not_be_moved):
        """Freezes positioners in their start_tp position, so that they won't
        move at all.
        """
        
