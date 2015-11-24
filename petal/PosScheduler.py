import numpy as np
import PosMoveTable

class PosScheduler(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.
    """
    
    def __init__(self):
        self.move_tables = []
        self._start = []
        self._targt = []
        self._is_forced_dtdp = []
        
    def overall_move_request(posmodel, P, Q):
        """Adds a request to the scheduler for a given positioner to move to
        the target position (P,Q).
        """
        self.move_tables.append(PosMoveTable.PosMoveTable(posmodels))
        self._targt.append([P,Q])
        self._is_forced_dtdp.append(False)
    
    def overall_move_request_with_forced_dtdp(posmodel, dt, dp):
        """Adds a request to the scheduler for a given positioner to move by
        a relative amount (dtheta, dphi). Inherently such moves will NOT be
        analyzed by the anticollision algorithm. Therefore calling this function
        should generally be used only by an expert user.
        """
        self.move_tables.append(PosMoveTable.PosMoveTable(posmodel))
        self._targt.append([dt,dp])
        self._is_forced_dtdp.append(True)
            
    def schedule_moves(self, anticollision=True):
        """Executes the scheduling algorithm upon the stored list of move requests.
        Note that if there are any forced relative (dtheta,dphi) moves in the requests
        list, then this forces that the whole schedule be done with no anticollision.
        """
        self._start = [[0,0]] * len(self._start)
        for i in range(len(self.move_tables)):
            if not(self._is_forced_dtdp[i]):
                current_position = self.move_tables[i].posmodel.position_PQ
                self._start[i] = current_position.transpose().tolist()
        if not(anticollision) or any(self._is_forced_dtdp):
            self.move_tables = self._schedule_without_anticollision()
        else:
            self.move_tables = self._schedule_with_anticollision()
         
    # internal methods    
    def _schedule_without_anticollision(self):
        start = np.transpose(np.array(self._start))
        targt = np.transpose(np.array(self._targt))

        # check forced dtdp
        for i in range(len(self._is_forced_dtdp)):
            if self._is_forced_dtdp[i]:
                start[:,i] = 0
            else:
                start = self.move_tables[i].posmodel.trans.QP_to_obsTP(start) # check format after PosTransforms updated
                targt = self.move_tables[i].posmodel.trans.QP_to_obsTP(targt) # check format after PosTransforms updated

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