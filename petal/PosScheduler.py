import numpy as np
import PosMoveTable

class PosScheduler(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.
    
    Note that the schedule may contain multiple move tables for the same positioner,
    under the assumption that another module (i.e. PosArrayMaster) will generally be
    the one which merges any such tables in sequence, before sending off to the hardware. 
    """
    
    def __init__(self):
        self.move_tables = []
        self._start = []
        self._targt = []
        self._is_forced = []
        
    def move_request(self, posmodel, P, Q):
        """Adds a request to the scheduler for a given positioner to move to
        the target position (P,Q).
        """
        self.move_tables.append(PosMoveTable.PosMoveTable(posmodel))
        self._targt.append([P,Q])
        self._is_forced_dtdp.append(False)
    
    def expert_move_request(self, move_table):
        """Adds an externally-constructed move table to the schedule. The move
        table will be skipped by the scheduling algorithm. Also, if there
        is ANY such table in a given schedule, then the anti-collision algorithm
        will NOT be used. Generally, this method should only be used for internal
        calls by an expert user.
        """
        self.move_tables.append(move_table)
        self._targt.append([float('nan'),float('nan')])
        self._is_forced.append(True)
            
    def schedule_moves(self, anticollision=True):
        """Executes the scheduling algorithm upon the stored list of move requests.
        Note that if there are any forced relative (dtheta,dphi) moves in the requests
        list, then this forces that the whole schedule be done with no anticollision.
        """
        self._start = [[0,0]] * len(self._start)
        for i in range(len(self.move_tables)):
            if self._is_forced[i]:
                self._start[i] = [float('nan'),float('nan')]
            else:
                current_P = self.move_tables[i].posmodel.state.kv['P_obs']
                current_Q = self.move_tables[i].posmodel.state.kv['Q_obs']
                self._start[i] = [current_P, current_Q]
        if not(anticollision) or any(self._is_forced):
            self.move_tables = self._schedule_without_anticollision()
        else:
            self.move_tables = self._schedule_with_anticollision()
         
    # internal methods
    def _schedule_without_anticollision(self):
        i = 0        
        for tbl in self.move_tables:      
            # convert global P,Q into local theta,phi
            start = np.transpose(np.array(self._start[i]))
            targt = np.transpose(np.array(self._targt[i]))
            start = self.tbl.posmodel.trans.obsPQ_to_obsTP(start) # check format after PosTransforms updated
            targt = self.tbl.posmodel.trans.obsPQ_to_obsTP(targt) # check format after PosTransforms updated

            # delta = finish - start
            dtdp_obs = targt - start

            # set deltas and pauses into move table
            if not(self._is_forced[i]):
                row = 0 # for the anti-collision, this would vary
                self.tbl.set_move     (row, tbl.posmodel.T, dtdp_obs[0,i])
                self.tbl.set_move     (row, tbl.posmodel.P, dtdp_obs[1,i])
                self.tbl.set_prepause (row, 0.0)
                self.tbl.set_postpause(row, 0,0)
            
            i += 1
                
        return move_tables
        
    def _schedule_with_anticollision(self):
        # anticollision algorithm goes here
        # see the "without" anticollision method for bare skeleton of what needs to happen
        move_tables = self._schedule_without_anticollision() # placeholder to be replaced with real code
        return move_tables