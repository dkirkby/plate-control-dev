# imports here

class PosScheduler(object):
	"""Generates move schedules in local (th,ph) to get positioners from starts to finishes.
	   We should get a clear definition of the move table format in here early."""

	def __init__(self):
		#maybe not necessary?
		pass
		
	def schedule_moves(PQstart,PQtarg,anticollision_on):
         # generate initial move tables
         if anticollision_on:
             move_tables_ideal = _schedule_with_anticollision(PQstart,PQtarg)
         else:
             move_tables_ideal = _schedule_without_anticollision(PQstart,PQtarg)
         # use PosModel to get true moves (quantized into steps, and true timing estimate) and update the tables
         # re-run the anticollision check one more time
         return move_tables
         
     # internal methods    
     def _schedule_without_anticollision(PQstart,PQtarg):
         # convert all the (P,Q) into local (th,ph)
         # delta = finish - start
         # make move tables to do deltas
         # use PosModel to get true moves and update the tables
         move_tables = None # replace with lots of real code
         return move_tables

     def _schedule_with_anticollision(PQstart,PQtarg):
         # anticollision algorithm goes here
         move_tables = None # replace with lots of real code
         return move_tables
