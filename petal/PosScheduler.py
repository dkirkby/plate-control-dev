# imports here

class PosScheduler(object):
	"""Generates move schedules in local (t,p) to get positioners from starts to finishes.
	   We should get a clear definition of the move table format in here early."""

	def __init__(self):
		#maybe not necessary?
		pass
		
	def schedule_moves(Qstart,Pstart,Qtarg,Ptarg,anticollision_on):
		if anticollision_on:
			# run the algorithm for anticollision
		else
			# convert all the Qs and Ps into local theta,phi
			# delta = finish - start
			# make move tables to do deltas
			# use PosModel to get true moves and update the tables
			
		return move_tables