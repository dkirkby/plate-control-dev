# imports here

class PosScheduler(object):
	"""Generates move schedules in local (t,p) to get positioners from starts to finishes.
	   We should get a clear definition of the move table format in here early."""

	def __init__(self):
		#maybe not necessary?
		pass
		
	def schedule_moves(Qstart,Pstart,Qtarg,Ptarg,anticollision_on):
         # generate initial move tables
         if anticollision_on:
             move_tables_ideal = _schedule_with_anticollision(Qstart,Pstart,Qtarg,Ptarg)
         else:
             move_tables_ideal = _schedule_without_anticollision(Qstart,Pstart,Qtarg,Ptarg)
         # use PosModel to get true moves (quantized into steps, and true timing estimate) and update the tables
         # re-run the anticollision check one more time
         return move_tables
         
     # internal methods    
     def _schedule_without_anticollision(Qstart,Pstart,Qtarg,Ptarg):
         # convert all the Qs and Ps into local theta,phi
         # delta = finish - start
         # make move tables to do deltas
         # use PosModel to get true moves and update the tables
         move_tables = None # replace with lots of real code
         return move_tables

     def _schedule_with_anticollision(Qstart,Pstart,Qtarg,Ptarg):
         # anticollision algorithm goes here
         move_tables = None # replace with lots of real code
         return move_tables
