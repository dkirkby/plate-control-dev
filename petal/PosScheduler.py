import numpy as np
import PosMoveTable

class PosScheduler(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.
    """
    
    def __init__(self):
        self.move_tables = []
        self._PQ_start = []
        self._PQ_targt = []
        
    def overall_move_request(posmodel, P, Q):
        """Adds a request to the scheduler for a given positioner to move to
        the target position (P,Q).
        """
        self.move_tables.append(PosMoveTable.PosMoveTable(posmodels[i]))
        self._PQ_targt = self._PQ_targt.append([P,Q])
        
    def schedule_moves(self, anticollision=True):
        self._PQ_start = [[0,0]] * len(self._PQ_start)
        for i in range(len(self.move_tables)):
            current_position = self.move_tables[i].posmodel.position_PQ
            self._PQ_start[i] = current_position
        if anticollision:
            self.move_tables = self._schedule_with_anticollision()
        else:
            self.move_tables = self._schedule_without_anticollision()
         
     # internal methods    
     def _schedule_without_anticollision(self):
        # convert all the (P,Q) into local (th,ph)
        PQ_start = np.transpose(np.array(self._PQ_start))
        PQ_targt = np.transpose(np.array(self._PQ_targt))
        tp_start = pos.trans.QP_to_obsTP(PQ_start)
        tp_targt = pos.trans.QP_to_obsTP(PQ_targt)

        # delta = finish - start
        dtdp = tp_targ - tp_start
        
        # set deltas and pauses into move tables
        for i in range(len(self.move_tables)):
            tbl = self.move_tables[i]
            row = 0
            tbl.set_move(row, tbl.posmodel.T, dtdp[0,i])
            tbl.set_move(row, tbl.posmodel.P, dtdp[1,i])
            tbl.set_prepause (row, 0.0)
            tbl.set_postpause(row, 0,0)
            
        return move_tables
        
    def _schedule_with_anticollision(self):
        # anticollision algorithm goes here
        # see the "without" anticollision method for bare skeleton of what needs to happen
        move_tables = self._schedule_without_anticollision() # placeholder to be replaced with real code
        return move_tables