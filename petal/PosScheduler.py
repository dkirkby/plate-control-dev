# imports here

class PosScheduler(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.
    """

	def __init__(self):
		#maybe not necessary?
		pass
		
	def schedule_moves(Pstart,Qstart,Ptarg,Qtarg,anticollision_mode_on):
         if anticollision_mode_on:
             move_tables = _schedule_with_anticollision(Pstart,Qstart,Ptarg,Qtarg)
         else:
             move_tables = _schedule_without_anticollision(Pstart,Qstart,Ptarg,Qtarg)
         return move_tables
         
     # internal methods    
     def _schedule_without_anticollision(Pstart,Qstart,Ptarg,Qtarg):
         # convert all the (P,Q) into local (th,ph)
         # delta = finish - start
         # use PosMoveTable to make move tables that do the deltas
         move_tables = None # replace with lots of real code
         return move_tables

     def _schedule_with_anticollision(Pstart,Qstart,Ptarg,Qtarg):
         # anticollision algorithm goes here
         move_tables = None # replace with lots of real code
         return move_tables
