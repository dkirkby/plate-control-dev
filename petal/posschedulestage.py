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
        self.frozen = set() # positioners that are required to stay exactly in place (no motion)
        self._start_posTP = {} # keys: posids, values: [theta,phi]
        self._final_posTP = {} # keys: posids, values: [theta,phi]
        self._true_dtdp = {} # keys: posids, values: [delta theta, delta phi]
    
    def initialize_move_tables(self, start_posTP, dtdp):
        """Generates basic move tables for each positioner, going straight from
        the start_tp to the final_tp.
        
            start_posTP  ... dict of starting [theta,phi] positions, keys are posids
            dtdp         ... dict of [delta theta, delta phi] from the starting position. keys are posids
                             The user should take care that these dtdp have been generated properly using PosTransforms, with range_wrap_limits='targetable'
        """
        self._start_posTP = start_posTP
        for posid in self._start_posTP:
            posmodel = self.collider.posmodels[posid]
            self._final_posTP[posid] = posmodel.trans.addto_posTP(self._start_posTP[posid], dtdp[posid], range_wrap_limits='targetable')
            self._true_dtdp[posid] = posmodel.trans.delta_posTP(self._final_posTP[posid], self.start_posTP[posid], range_wrap_limits='targetable')
            table = posmovetable.PosMoveTable(posmodel, self._start_posTP[posid])
            table.set_move(0, pc.T, dtdp[posid][0])
            table.set_move(0, pc.P, dtdp[posid][1])
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
        
    def find_collisions(self, posids=set()):
        """Identifies collisions in the current move tables.
        
            posids  ... Set of positioners to be checked. They will each be checked
                        for collisions against all their neighbors, and against any
                        applicable fixed boundaries, such as the GFA or Petal envelopes
                        Arguing an empty list causes the complete list of positioners to
                        be checked.
        
        Returns a dict with keys = posids, values = enumerated collision types
        (see the 'case' class in PosConstants). The dict only contains positioners
        that collide, and will be empty if there are no collisions
        """
        if not posids:
            posids = self.collider.posids
        pairs = {}
        for posid in posids:
            for neighbor in self.collider.pos_neighbors[posid]:
                # this if statement below is wrong -- still need to check disabled positioners. it's just that we don't adjust their paths later
                if neighbor not in pairs and posid in self.move_tables and neighbor in self.move_tables:
                    pairs[posid] = neighbor
                    this_table = self.move_tables[posid]
                    neighbor_table self.move_tables[neighbor]
                    this_init_obsTP = 
                    # make init_obsTPs
                    # make tables
                    pospos_sweeps = self.collider.spacetime_collision_between_positioners(posid, init_obsTP_A, tableA, neighbor, init_obsTP_B, tableB)
        # also do fixed boundary checks
        # for any positioner that has 2 collisions, return the first collision only

        
    def adjust_paths(self, avoidance_method='zeroth'):
        """Alters move tables to avoid collisions.
        
            avoidance_method ... Valid collision avoidance methods: 'zeroth', 'tweak', 'astar'
        """
        # be sure to not adjust paths on any positioners that aren't specifcially included in the start_tp, final_tp dicts

        
        
    def freeze(self, posids_that_should_not_be_moved):
        """Freezes positioners in their start_tp position, so that they won't
        move at all.
        """
 
        
