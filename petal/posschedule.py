import posmovetable
import posconstants as pc
from poscollider import PosSweep
from bidirect_astar import inertial_bidirectional_astar_pathfinding

## External Dependencies
import numpy as np
from collections import Counter
import datetime
import os

## Temporary Debugging Dependencies
import matplotlib.pyplot as plt
import pdb
import copy as copymodule

class PosSchedule(object):
	"""Generates move table schedules in local (theta,phi) to get positioners
	from starts to finishes. The move tables are instances of the PosMoveTable
	class.

	Note that the schedule may contain multiple move tables for the same positioner,
	under the assumption that another module (i.e. Petal) will generally be
	the one which merges any such tables in sequence, before sending off to the hardware.
	
	Initialize with the petal object this schedule applies to.
	"""

	def __init__(self, petal,avoidance='tweak',verbose=False):
		self.petal = petal
		self.move_tables = []
		self.requests = {}
		self.posids = []
		# todo-anthony make compatible with various tp offsets and tp ranges
		self.anticol = Anticol(self.collider,self.petal,verbose)

	@property
	def collider(self):
		return self.petal.collider
		
	def request_target(self, posid, uv_type, u, v, log_note=''):
		"""Adds a request to the schedule for a given positioner to move to the
		target position (u,v) or by the target distance (du,dv) in the coordinate
		system indicated by uv_type.

			  posid ... string, unique id of positioner
			uv_type ... string, 'QS', 'dQdS', 'obsXY', 'posXY', 'dXdY', 'obsTP', 'posTP' or 'dTdP'
				  u ... float, value of q, dq, x, dx, t, or dt
				  v ... float, value of s, ds, y, dy, p, or dp
		   log_note ... optional string to store alongside the requested move in the log data

		A schedule can only contain one target request per positioner at a time.
		"""
		posmodel = self.petal.posmodel(posid)
		if self.already_requested(posid):
			print(str(posmodel.state.read('POS_ID')) + ': cannot request more than one target per positioner in a given schedule')
			return
		if self._deny_request_because_disabled(posmodel):
			return
		current_position = posmodel.expected_current_position
		start_posTP = [current_position['posT'],current_position['posP']]
		lims = 'targetable'
		if uv_type == 'QS':
			(targt_posTP,unreachable) = posmodel.trans.QS_to_posTP([u,v],lims)
		elif uv_type == 'obsXY':
			(targt_posTP,unreachable) = posmodel.trans.obsXY_to_posTP([u,v],lims)
		elif uv_type == 'posXY':
			(targt_posTP,unreachable) = posmodel.trans.posXY_to_posTP([u,v],lims)
		elif uv_type == 'obsTP':
			targt_posTP = posmodel.trans.obsTP_to_posTP([u,v])
		elif uv_type == 'posTP':
			targt_posTP = [u,v]
		elif uv_type == 'dQdS':
			start_uv = [current_position['Q'],current_position['S']]
			targt_uv = posmodel.trans.addto_QS(start_uv,[u,v])
			(targt_posTP,unreachable) = posmodel.trans.QS_to_posTP(targt_uv,lims)
		elif uv_type == 'dXdY':
			start_uv = [current_position['posX'],current_position['posY']]
			targt_uv = posmodel.trans.addto_posXY(start_uv,[u,v])
			(targt_posTP,unreachable) = posmodel.trans.posXY_to_posTP(targt_uv,lims)
		elif uv_type == 'dTdP':
			targt_posTP = posmodel.trans.addto_posTP(start_posTP,[u,v],lims)
		else:
			print('bad uv_type "' + str(uv_type) + '" for target request')
			return
		new_request = {'start_posTP' : start_posTP,
					   'targt_posTP' : targt_posTP,
						  'posmodel' : posmodel,
							 'posid' : posid,
						   'command' : uv_type,
						  'cmd_val1' : u,
						  'cmd_val2' : v,
						  'log_note' : log_note}
		self.requests[posid] = new_request

	def add_table(self, move_table):
		"""Adds an externally-constructed move table to the schedule. If there
		is ANY such table in a given schedule, then the anti-collision algorithm
		will NOT be used. Generally, this method should only be used for internal
		calls by an expert user.
		"""
		if self._deny_request_because_disabled(move_table.posmodel):
			return
		this_posid = move_table.posmodel.posid
		if this_posid in self.posids:
			index = self.posids.index(this_posid)
			self.move_tables[index].extend(move_table)
		else:
			self.posids.append(this_posid)
			self.move_tables.append(move_table)


	def schedule_moves(self, anticollision=True):
		"""Executes the scheduling algorithm upon the stored list of move requests.

		A single move table is generated for each positioner that has a request
		registered. The resulting tables are stored in the move_tables list. If the
		anticollision argument is true, then the anticollision algorithm is run when
		generating the move tables.

		If there were ANY pre-existing move tables in the list, then ALL the target
		requests are ignored, and the anticollision algorithm is NOT performed.
		"""
		if self.anticol.debug:
			reqs = self.requests.copy()

		if self.move_tables:
			return
		elif anticollision:
			## Note the use of non-functioning anticollision code! Only for testing purposes
			## Note the Positioners COULD collide using this function
			#self._schedule_without_anticollision_butwith_RRrE()
			self._schedule_with_anticollision()
		else:
			self._schedule_without_anticollision()
		pdb.set_trace()
		if self.anticol.debug:
			print("\n\n\nResulting Schedules:")
			print("\tIn scheduler:")
			for table in self.move_tables:
				schedule = table.full_table
				posid = table.posmodel.posid
		
				req = reqs[posid]
				posmodel = req['posmodel']
				if posmodel != table.posmodel:
					print('Posmodels didnt match for posid: {}'.format(posid))
				#start_obsTP = posmodel.trans.posTP_to_obsTP(req['start_posTP'])
				#final_obsTP = posmodel.trans.posTP_to_obsTP(req['targt_posTP'])
				#start_obsXY = posmodel.trans.posTP_to_obsXY(req['start_posTP'])
				#final_obsXY = posmodel.trans.posTP_to_obsXY(req['targt_posTP'])
				#
				#stats = schedule['stats']
				#beginning = posmodel.expected_current_position
				#begin_posTP = [beginning['posT'],beginning['posP']]
				#begin_obsTP = [beginning['obsT'],beginning['obsP']] #posmodel.trans.posTP_to_obsTP(begin_posTP)
				#begin_obsXY = posmodel.trans.posTP_to_obsXY(begin_posTP)
				#end_posTP = posmodel.trans.addto_posTP(begin_posTP,[stats['net_dT'][-1],stats['net_dP'][-1]],range_wrap_limits='targetable')
				#end_obsXY = posmodel.trans.posTP_to_obsXY(end_posTP)
				#end_obsTP = posmodel.trans.posTP_to_obsTP(end_posTP)
				#print('  posid: {}'.format(posid))
				#print('\tRequested start: obstp=({:0.04f},{:0.04f}) obsxy=({:0.04f},{:0.04f})'.format( start_obsTP[0],start_obsTP[1], \
				#                                                                    start_obsXY[0],start_obsXY[1]))
				#print('\tScheduled start: obstp=({:0.04f},{:0.04f}) obsxy=({:0.04f},{:0.04f})'.format( begin_obsTP[0],begin_obsTP[1], \
				#                                                                    begin_obsXY[0],begin_obsXY[1]))
				#print('\tRequested end  : obstp=({:0.04f},{:0.04f}) obsxy=({:0.04f},{:0.04f})'.format(final_obsTP[0],final_obsTP[1], \
				#                                                                   final_obsXY[0],final_obsXY[1]))
				#print('\tScheduled end  : obstp=({:0.04f},{:0.04f}) obsxy=({:0.04f},{:0.04f})'.format(end_obsTP[0],end_obsTP[1], \
				#                                                                   end_obsXY[0],end_obsXY[1]))
				
				print("\tPosid: {}".format(posid))
				print("\tCommands: {}  val1:{:.06f} val2:{:.06f}".format(schedule['command'][0],schedule['cmd_val1'][0],schedule['cmd_val2'][0]))
				print("\tTable Data:")
				for i in range(schedule['nrows']):
					angle_tup = (schedule[key][i] for key in ['dT', 'dP', 'Tdot', 'Pdot'])
					timing_tup = (schedule[key][i] for key in ['prepause','move_time','postpause'])
					print("\t\tRow {}: dT={:.04f}   dP={:.04f}   Tdot={:.02f}   Pdot={:.02f}".format(i,*angle_tup))
					print("\t\t       Prepause={:.04f}   movetime={:.04f}   Postpause={:.04f}".format(*timing_tup))
				#schedule = table.for_hardware
				#print("\t\tFor Hardware:")
				#for i in range(schedule['nrows']):
				#    motor_tup = (schedule[key][i] for key in ['motor_steps_T', 'motor_steps_P', 'speed_mode_T', 'speed_mode_P'])
				#    timing_tup = (schedule[key][i] for key in ['move_time','postpause'])
				#    print("\t\tRow {}: movetime={:.04f}   Postpause={:.04f}".format(i,*timing_tup))
				#    print("\t\t       Tmotsteps={}   Pmotsteps={}   Tspeedmode={}   Pspeedmode={}".format(*motor_tup))
		
			print("\n\n\n")

	def total_dtdp(self, posid):
		"""Return as-scheduled total move distance for positioner identified by posid.
		Returns [dt,dp].
		"""
		posmodel = self.petal.posmodel(posid)
		dtdp = [0,0]
		for tbl in self.move_tables:
			if tbl.posmodel == posmodel:
				postprocessed = tbl.full_table
				dtdp = [postprocessed['stats']['net_dT'][-1], postprocessed['stats']['net_dP'][-1]]
				break
		return dtdp

	def total_scheduled_time(self):
		"""Return as-scheduled total time for all moves and pauses to complete for
		all positioners.
		"""
		time = 0
		for tbl in self.move_tables:
			postprocessed = tbl.full_table
			tbl_time = postprocessed['stats']['net_time'][-1]
			if tbl_time > time:
				time = tbl_time

	def already_requested(self, posid):
		"""Returns boolean whether a request has already been registered in the
		schedule for the argued positioner.
		"""
		was_already_requested = posid in self.requests
		return was_already_requested


	def _deny_request_because_disabled(self, posmodel):
		"""This is a special function specifically because there is a bit of care we need to
		consistently take with regard to post-move cleanup, if a request is going to be denied.
		"""
		enabled = posmodel.state.read('CTRL_ENABLED')
		if enabled == False:  ## this is specifically NOT worded as "if not enabled:",
			## because here we actually do not want a value of None
			## to pass the test, in case the parameter field 'CTRL_ENABLED'
			## has not yet been implemented in the positioner's .conf file
			posmodel.clear_postmove_cleanup_cmds_without_executing()
			print(str(posmodel.state.read('POS_ID')) + \
				  ': move request denied because CTRL_ENABLED = ' + str(enabled))
			return True
		return False

	def _schedule_without_anticollision(self):
		posids = list(self.requests.keys())
		for posid in posids:
			req = self.requests.pop(posid)
			table = self._create_direct_movetable(req)
			table.store_orig_command(0, req['command'], req['cmd_val1'], req['cmd_val2'])
			table.log_note += (' ' if table.log_note else '') + req['log_note']
			self.move_tables.append(table)


	def _create_direct_movetable(self,request):
		posmodel = request['posmodel']
		table = posmovetable.PosMoveTable(posmodel)
		dtdp = posmodel.trans.delta_posTP(request['targt_posTP'], \
										  request['start_posTP'], range_wrap_limits='targetable')
		table.set_move(0, pc.T, dtdp[0])
		table.set_move(0, pc.P, dtdp[1])
		table.set_prepause(0, 0.0)
		table.set_postpause(0, 0.0)
		return table


	def _schedule_with_anticollision(self):
		'''
			Primary calling function. Once the PosAnticol is initiated, this is essentially all you need to call.
			This takes in requests with correctly ordered posunitids
			Since requests are dictionaries, they do not maintain an order, which is why the posunitids are
			critical to keeping things in a proper order.
			
			requests:  posschedule list of request objects
			posunitids:  a simple list or numpy array of the unitids. requests[i]['posmodel'].posid should have 
						a location
						  within posunitids. These will be matched and ordered below.
					  
		'''
		if self.anticol.verbose:
			print("You ARE doing anticollisions")
			print("Number of requests: "+str(len(self.requests)))

		self.anticol._update_positioner_properties()
		table_type = self._get_tabletype()
		move_tables = self._get_collisionless_movetables(table_type=table_type)

		## Write a comment in each movetable, pop the request out, and save to self.movetables
		for posid, movetable in move_tables.items():
			if posid != movetable.posmodel.posid and self.anticol.verbose:
				print("In anticollsion code the returned table didn't have the same posid as the key it had")
			req = self.requests.pop(posid)
			if movetable.posmodel != req['posmodel'] and self.anticol.verbose:
				print("In anticollsion code the tables posmodel didn't match the req posmodel")
			# Add the original commands and log notes to the move tables
			movetable.store_orig_command(0,req['command'],req['cmd_val1'],req['cmd_val2'])
			movetable.log_note += (' ' if movetable.log_note else '') + req['log_note']
			self.move_tables.append(movetable)

	def _get_collisionless_movetables(self,table_type='RRrE'):
		'''
			Code that generates move tables, finds the collisions,
			and updates move tables such that no collisions will occur.
			It returns the list of all movetables where none collide with
			one another or a fixed object.
		'''
		## Declare the dictionaries (and list of posids,
		## which ideally won't need to be used since it's analogous to *.keys())
		requested_posids = []

		## Name the steps involved in the avoidance (used for dictionary keys)
		if table_type == 'direct':
			stages = ['direct']
		elif table_type == 'RRrE' or table_type == 'RRE':
			stages = ['retract', 'rotate', 'extend']
		else:
			print("Not RRrE, RRE, or direct. Exiting")
			raise(TypeError)

		## Generate complete movetables under RRE method. Each stage gets it's own named dictionary
		info_for_all_stages = {}

		for oper in stages:
			info_for_all_stages[oper] = { 'movetables':{}, 'movetimes':{}, 'maxtime':{}, 'tpstarts':{}, 'tpfinals':{} }

		## Unpack the requests into seperate dictionaries (using the same keys!)
		## Each request must have retract, rotate, and extend moves
		## Which each have different start and end theta/phis
		for posid, req in self.requests.items():
			posmodel = req['posmodel']

			if posmodel.posid != posid and self.anticol.verbose:
				print("The posid of the request posmodel didn't match the posid key!")

			# Save these for later use
			requested_posids.append(posid)
			tps = posmodel.trans.posTP_to_obsTP(req['start_posTP'])
			tpf = posmodel.trans.posTP_to_obsTP(req['targt_posTP'])

			if table_type == 'direct':
				current_tables_dict = {}
				current_tables_dict['direct'] = self._create_direct_movetable(request=req)
				info_for_all_stages['direct']['tpstarts'][posid] = tps
				info_for_all_stages['direct']['tpfinals'][posid] = tpf
			elif table_type == 'RRE':
				current_tables_dict, tpsi, tpfi = self._create_RRE_movetables(tps, tpf, posmodel,reverse_extension=False)
				## retraction tps
				info_for_all_stages['retract']['tpstarts'][posid] = tps
				info_for_all_stages['retract']['tpfinals'][posid] = tpsi
				## rotation tps
				info_for_all_stages['rotate']['tpstarts'][posid] = tpsi
				info_for_all_stages['rotate']['tpfinals'][posid] = tpfi
				## extention tps
				info_for_all_stages['extend']['tpstarts'][posid] = tpfi
				info_for_all_stages['extend']['tpfinals'][posid] = tpf
			elif table_type == 'RRrE':
				current_tables_dict, tpsi, tpfi = self._create_RRE_movetables(tps, tpf, posmodel,reverse_extension=True)
				# retraction tps
				info_for_all_stages['retract']['tpstarts'][posid] = tps
				info_for_all_stages['retract']['tpfinals'][posid] = tpsi
				## rotation tps
				info_for_all_stages['rotate']['tpstarts'][posid] = tpsi
				info_for_all_stages['rotate']['tpfinals'][posid] = tpfi
				## **note extend is flipped (unflipped at end of anticol)** ##
				## extention tps
				info_for_all_stages['extend']['tpstarts'][posid] = tpf
				info_for_all_stages['extend']['tpfinals'][posid] = tpfi
				
			## Unwrap the three movetables and add each of r,r,and e to
			## a seperate list for that movetype
			## Also append the movetime for that move to a list
			for key in stages:
				movetime = current_tables_dict[key].for_schedule['stats']['net_time']
				info_for_all_stages[key]['movetables'][posid] = current_tables_dict[key]
				info_for_all_stages[key]['movetimes'][posid] = movetime[0] # should be -1? Kai & Joe


		## For each of r, r, and e, find the maximum time that
		## any positioner takes. The rest will be assigned to wait
		## until that slowest positioner is done moving before going to
		## the next move
		for stage in stages:
			stage_info = info_for_all_stages[stage]
			stage_info['maxtime'] = max(stage_info['movetimes'].values())
			for posid in requested_posids:
				table, movetime = stage_info['movetables'][posid],stage_info['movetimes'][posid]
				if movetime<stage_info['maxtime']:
					table.set_postpause(int(table.for_schedule['nrows'])-1,stage_info['maxtime']-movetime)

		if self.anticol.verbose:
			print_str = "Max times to start are: "
			for stage in stages:
				print_str += "{}={:.4f}, ".format(stage, info_for_all_stages[stage]['maxtime'])
			print(print_str)

		for stage in stages:
			stage_info = info_for_all_stages[stage]
			tpstarts = stage_info['tpstarts']
			tpfinals = stage_info['tpfinals']
			movetables = stage_info['movetables']
			maxtime = stage_info['maxtime']

			## animate
			if self.anticol.make_animations == True:
				self._animate_movetables(movetables, tpstarts)

			## Check for collisions   oper_info['
			collision_indices, collision_types = \
					self._check_for_collisions(tpstarts,movetables)
			print('Stage:',stage)
			print('Collision_indices',collision_indices)
			print('Collision_types',collision_types)
			## If no collisions, move directly to the next step
			if len(collision_indices) == 0:
				continue
			
			if self.anticol.verbose:
				print('\n\n\n\nStep: {}    Round: 1/1:\n'.format(stage))
				self._printindices('Collisions before iteration ',1,collision_indices)  

			ncols = len(collision_indices)
  
			## Avoid the collisions that were found
			movetables,moved_poss = self._avoid_collisions(movetables, \
									collision_indices, collision_types, tpstarts, \
									tpfinals, stage, maxtime, \
									algorithm=self.anticol.avoidance)
			info_for_all_stages[stage]['movetables']=movetables   #Kai: Update the info_for_all_stages
			for posid, req in self.requests.items():
				movetime = info_for_all_stages[stage]['movetables'][posid].for_schedule['stats']['net_time']
				info_for_all_stages[stage]['movetimes'][posid] = movetime[-1]
			# Synchronization
			stage_info = info_for_all_stages[stage]
			stage_info['maxtime'] = max(stage_info['movetimes'].values())
			for posid in requested_posids:
				table, movetime = stage_info['movetables'][posid],stage_info['movetimes'][posid]
				if movetime<stage_info['maxtime']:
					table.set_postpause(int(table.for_schedule['nrows'])-1,stage_info['maxtime']-movetime+table.for_schedule['postpause'][0])

			if self.anticol.verbose:
				## Check for collisions
				tps_check,tables_check={},{}
				tps_check['M00131']=tpstarts['M00131']
				tps_check['M00152']=tpstarts['M00152']
				tables_check['M00131']=movetables['M00131']
				tables_check['M00152']=movetables['M00152']
				a,b=self._check_for_collisions(tps_check,tables_check)
				print('131,152 check',a,b,tps_check)
				collision_indices, collision_types = \
						self._check_for_collisions(tpstarts,movetables)
				self._printindices('Collisions after Round 1, in Step ',stage,collision_indices)
				print("\nNumber corrected: {}\n\n\n\n".format(ncols-len(collision_indices)))

			if self.anticol.verbose:
				if movetables is not stage_info['movetables']:
					print('Movetables are not the same between movetables and the stage movetable')
				if stage_info['movetables'] is not info_for_all_stages[stage]['movetables']:
					print('Movetables are not the same between stage_info and info_for_all_stages')

		if table_type == 'direct':
			merged_tables = info_for_all_stages['direct']['movetables']
		elif table_type == 'RRrE':
			output_tables = {key: info_for_all_stages[key]['movetables'] for key in ['retract','rotate']}
			output_tables['extend'] = self._reverse_for_extension(info_for_all_stages['extend']['movetables'])
			merged_tables = self._combine_tables(output_tables)
		elif table_type == 'RRE':
			output_tables = {key: info_for_all_stages[key]['movetables'] for key in ['retract','rotate','extend']}
			merged_tables = self._combine_tables(output_tables)
		else:
			raise(TypeError)
		# Get the obsTP dictionary of starting positions for each positioner in the first move stage
		first_stage = stages[0]
		tp_starts = info_for_all_stages[first_stage]['tpstarts']

		## animate
		if self.anticol.make_animations == True:
			self._animate_movetables(merged_tables, tp_starts)
		tps_check,tables_check={},{}
		tps_check['M00131']=tp_starts['M00131']
		tps_check['M00152']=tp_starts['M00152']
		tables_check['M00131']=merged_tables['M00131']
		tables_check['M00152']=merged_tables['M00152']
		a,b=self._check_for_collisions(tps_check,tables_check)
		print('131,152 check after merge',a,b,tps_check)
		pdb.set_trace()
		collision_indices, collision_types = self._check_for_collisions(tp_starts, merged_tables)
		print('Collisions that need Zeroth order avoidance',collision_indices)
		## If no collisions, move directly to the next step
		if len(collision_indices) > 0:
			merged_tables, zeroed = self._avoid_collisions(merged_tables,collision_indices,tpss=tp_starts,algorithm='zeroth_order')
			## animate
			if self.anticol.make_animations == True:
				self._animate_movetables(merged_tables, tp_starts)
		else:
			zeroed = []

		if self.anticol.verbose:
			collision_indices, collision_types = self._check_for_collisions(tp_starts, merged_tables)
			self._printindices('Collisions after completion of anticollision ','',collision_indices)
			nzero =len(np.unique(zeroed))
			ntot = len(tp_starts)
			print("Number of zerod positioners: {}, total number of targets: {}, successes: {}%".format(nzero,ntot,100*(1-(float(nzero)/float(ntot)))))

		return merged_tables

	def _create_RRE_movetables(self,tp_start, tp_final, current_positioner_model, reverse_extension=True):
		'''
			Create the original movetable for the current positioner. This uses 
			the retract rotate extend framework and creates 3 seperate move tables.
			One for each of the r.r.e.
			Since all positioners should reach their final objectives in each portion before
			any can move to the next, each of the r.r.e. are independent (ie retract is independt of extend)
			Returns a dictionary of 3 move tables where the key is either retract rotate or extend.
		'''
		## Get a table class instantiation
		table = {}
		table['retract'] = posmovetable.PosMoveTable(current_positioner_model)
		table['rotate'] = posmovetable.PosMoveTable(current_positioner_model)
		table['extend'] = posmovetable.PosMoveTable(current_positioner_model)
		##redefine phi inner:
		phi_inner = max(self.anticol.phisafe,tp_start[pc.P])
		## Find the theta and phi movements for the retract move
		tpss = tp_start
		tpsi = self._assign_properly(tp_start[pc.T],phi_inner)
		dtdp = current_positioner_model.trans.delta_obsTP(tpsi,\
							tpss, range_wrap_limits='targetable')
		table['retract'].set_move(0, pc.T, dtdp[pc.T])
		table['retract'].set_move(0, pc.P, dtdp[pc.P])
		table['retract'].set_prepause(0, 0.0)
		table['retract'].set_postpause(0, 0.0)
		del dtdp
		## Find the theta and phi movements for the theta movement inside the safety envelope
		tpfi = self._assign_properly(tp_final[pc.T],phi_inner)
		dtdp = current_positioner_model.trans.delta_obsTP(tpfi,\
							tpsi, range_wrap_limits='targetable')
		table['rotate'].set_move(0, pc.T, dtdp[pc.T]) 
		table['rotate'].set_move(0, pc.P, dtdp[pc.P]) 
		table['rotate'].set_prepause(0, 0.0)
		table['rotate'].set_postpause(0, 0.0)
		del dtdp
		## Find the theta and phi movements for the phi extension movement
		## if reverse_extension, reverse it
		tpff = tp_final
		if reverse_extension:
			dtdp = current_positioner_model.trans.delta_obsTP(tpfi, tpff,range_wrap_limits='targetable')
		else:
			dtdp = current_positioner_model.trans.delta_obsTP(tpff, tpfi, range_wrap_limits='targetable')
		table['extend'].set_move(0, pc.T, dtdp[pc.T])
		table['extend'].set_move(0, pc.P, dtdp[pc.P])
		table['extend'].set_prepause(0, 0.0)
		table['extend'].set_postpause(0, 0.0)
		## return this positioners rre movetable
		return table, tpsi, tpfi



	def _avoid_collisions(self, tables, collision_indices, \
						  collision_types={}, tpss={}, tpfs={}, \
						  step='retract', maxtimes=np.inf, algorithm='tweak'):
		'''
			Function that is called with a list of collisions that need to be avoided. This uses 
			a 'force law' type approach to generate moves that avoid neighboring positioners 
			that it would otherwise collide with.
		'''
		print('Algorithm',algorithm)
		if algorithm.lower() in ['zeroth_order','zeroth order','zeroeth_order','zeroeth order']:
			return self._avoid_collisions_zerothorder(tables,collision_indices,tpss)
		# Larger phis are more tucked in, check if they are all tucked in enough
		# Ei is the more tucked in, extremem case
		phis = np.asarray([tp[pc.P] for tp in tpss.values()])
		# BUG ALERT #
		# phis is an array of None's
		# BUG AlERT
		if step.lower() == 'rotate' and np.all(phis>=self.collider.Eo_phi):
		   print("You want me to correct rotational collisions when all the phi motors are tucked in.")
		   print("Sorry I can't help")
		   return tables, []
		elif step.lower() == 'rotate':
		   print("It appears that some of your initial phis are not tucked in far enough, and you are trying to rotate.")
		   print("We currently don't have programming for rotation avoidance, as you should retract all positioners before this move")
		   print("Phi values that conflict: {}".format(phis[phis<self.collider.Eo_phi]))
		   return tables, []
		elif algorithm.lower() == 'astar':
			#if algorithm.lower() == 'astar':
			return self._avoid_collisions_astar(tables, collision_indices, \
						  collision_types, tpss, tpfs, \
						  step, maxtimes, algorithm)
		elif algorithm.lower() == 'tweak':
			return self._avoid_collisions_tweak(tables,collision_indices, collision_types,tpss,tpfs,step,maxtimes,algorithm)
		else:
			return self._avoid_collisions_zerothorder(tables, collision_indices,tpss)


	def _avoid_collisions_tweak(self,tables,collision_indices, collision_types,tpss,tpfs,step,maxtimes,algorithm):
		ptl=self.petal
		posids=[ptl.posmodels[i].posid for i in range(len(ptl.posmodels))]
		offsetX_arr=[ptl.posmodels[i].state._val['OFFSET_X'] for i in range(len(ptl.posmodels))]
		offsetY_arr=[ptl.posmodels[i].state._val['OFFSET_Y'] for i in range(len(ptl.posmodels))]
		altered_pos=[]
		for collision_indices_this,collision_type_this in zip(collision_indices,collision_types):
			posA,posB=collision_indices_this[0],collision_indices_this[1]
			print('Solving',posA,posB,collision_type_this)
			# Find neighbours first
			neighbours_this_pair=set()
			pos_neighbour_A,pos_neighbour_B=[],[]
			index_neighbour_A,index_neighbour_B=[],[]
			if posA != None:
				pos_neighbour_A,index_neighbour_A=self.find_neighbours(posA,posids,offsetX_arr,offsetY_arr)
			if posB != None:
				pos_neighbour_B,index_neighbour_B=self.find_neighbours(posB,posids,offsetX_arr,offsetY_arr)
			index_neighbour_this_pair=set(index_neighbour_A)|set(index_neighbour_B)
			neighbours_this_pair=set(pos_neighbour_A) | set(pos_neighbour_B)

			tps_check,tables_check={},{}
			if posA != None and posB != None:
				tables_backup=copymodule.deepcopy(tables)
				for j in neighbours_this_pair:
					tps_check[j]=tpss[j]
					tables_check[j]=tables[j]
				########################
				# Tweaks begin
				########################
				tables=self.tweak_add_prepause(tables,posA,1.)
				for j in neighbours_this_pair:
                                        tps_check[j]=tpss[j]
                                        tables_check[j]=tables[j]
				collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
				if len(collision_types_try)==0 :
					print('Solved by pause posA!')
					altered_pos.append(posA)
					continue
				else:
					tables=copymodule.deepcopy(tables_backup)


				tables=self.tweak_add_prepause(tables,posB,1.)
				for j in neighbours_this_pair:
                                        tps_check[j]=tpss[j]
                                        tables_check[j]=tables[j]
				collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
				if len(collision_types_try)==0 :
					print('Solved by pause posB!')
					altered_pos.append(posA)
					continue
				else:
					tables=copymodule.deepcopy(tables_backup)

				tables=self.tweak_move_theta(tables,posA,5.)
				for j in neighbours_this_pair:
                                        tps_check[j]=tpss[j]
                                        tables_check[j]=tables[j]
				collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
				if len(collision_types_try)==0 :
					print('Solved by moving posA theta 5 degree!')
					altered_pos.append(posA)
					continue
				else:
					tables=copymodule.deepcopy(tables_backup)

				tables=self.tweak_move_theta(tables,posB,5)
				for j in neighbours_this_pair:
                                        tps_check[j]=tpss[j]
                                        tables_check[j]=tables[j]
				collision_indices_try, collision_types_try = self._check_for_collisions(tps_check,tables_check)
				if len(collision_types_try)==0 :
					print('Solved by moving posB theta -5 degree!')
					altered_pos.append(posB)
					continue
				else:
					tables=copymodule.deepcopy(tables_backup)
				

		return tables, altered_pos

	def find_neighbours(self,posid,posids,offsetX_arr,offsetY_arr):
		ptl=self.petal
		index=posids.index(posid)
		offsetX=ptl.posmodels[int(index)].state._val['OFFSET_X']
		offsetY=ptl.posmodels[int(index)].state._val['OFFSET_Y']
		pos_dist=np.sqrt((np.array(offsetX_arr)-offsetX)**2+(np.array(offsetY_arr)-offsetY)**2)
		index1=np.where(pos_dist <= 11)
		index2=np.where(pos_dist > 0.2)
		index=set(index1[0].tolist()) & set(index2[0].tolist())
		index_neighbour=list(index)
		pos_neighbour=[posids[i] for i in index_neighbour]
		return pos_neighbour,index_neighbour

	def tweak_add_prepause(self,tables,posid,time):
		table = tables[posid]
		table.set_prepause(0, time)
		tables[posid] = table
		return tables

	def tweak_move_theta(self,tables,posid,dT):
		table = tables[posid]
		nrows=len(table.rows)
		table.insert_new_row(0)
		table.insert_new_row(nrows+1)
		nrows=len(table.rows)
		table.set_move(0, pc.T, dT)
		table.set_move(nrows-1,pc.T,-dT)
		tables[posid] = table
		return tables

	def tweak_move_phi(self,tables,posid,dP):
		table = tables[posid]
		nrows=len(table.rows)
		table.insert_new_row(0)
		table.insert_new_row(nrows+1)
		nrows=len(table.rows)
		table.set_move(0, pc.P, dP)
		table.set_move(nrows-1,pc.P,-dP)
		tables[posid] = table
		return tables

	def tweak_move_theta_phi(self,tables,posid,dT,dP):
		pass
	# todo-anthony split this into algorithm generic and specific, move generic to above function
	def _avoid_collisions_astar(self, tables, collision_indices, \
						  collision_types, tpss, tpfs, \
						  step, maxtimes, algorithm):
		## Create a set that contains all positioners involved in corrections. \
		## Only one alteration to a positioner neighborhood
		## per function call
		neighbor_ofaltered = set()

		## Unpack the starting and ending theta/phis for all collisions
		# tss = np.asarray(tpss[:,pc.T])
		# pss = np.asarray(tpss[:,pc.P])
		# tfs = np.asarray(tpfs[:,pc.T])
		# pfs = np.asarray(tpfs[:,pc.P])

		all_numeric_indices = []
		for ab in collision_indices:
			all_numeric_indices.extend(ab)
		### MS 180124: fixed the problem of multiple 'None' in list
		all_numeric_indices=[e for e in all_numeric_indices if e is not None]
		all_numeric_indices = np.unique(all_numeric_indices)    
		#if None in all_numeric_indices:
		#    all_numeric_indices.pop(all_numeric_indices.index(None))

		altered_pos = [-99]
		stallmovetimes = [0]
		
		### R1 and R2 parameters and their theta/phi and x/y offsets
		# self.collider.R1 
		# self.collider.R2     <- arrays for each positiner
		
		### Targetable theta_phi positions for all positioners
		# self.collider.tp_ranges 
		### safety phi values for each positioner
		# self.collider.Ei_polys, self.collider.Ee_polys
		
		# self.collider.keepout_PTL        
		# self.collider.place_phi_arm(idx, tp)
		# self.collider.place_central_body(idx, t)
		# self.collider.keepout_GFA
		# self.collider.ferrule_poly

		run_results = {'tpstart':[],'tpgoal':[],'idx_changing':[],'idx_unchanging':[],'case':[],'movetype':[],\
					   'heuristic':[],'weight':[],'pathlength_full':[np.nan],'pathlength_condensed':[],'found_path':[]}#'avoided_collision':[]

		## For each collision, check what type it is and try to resolve it
		for current_collision_indices,collision_type in zip(collision_indices,collision_types):
			A,B = current_collision_indices
			if A in altered_pos:
				continue
			elif B in altered_pos:
				continue
			## Determine which positioner to have avoid the other, which depends on
			## the type of collisions
			if collision_type == pc.case.I:
				if self.anticol.verbose:
					print("\n\nCollision was claimed, but case is non-collision Case I")
				continue
			elif collision_type in [pc.case.II,pc.case.IIIA,pc.case.IIIB]:
				if collision_type == pc.case.II:
					if self.anticol.verbose:
						print("\n\nSolving phi-phi collision!\n")
					## change larger phi since it has less distance to travel before safety
					if tpss[A] > tpss[B]:
						changings = [A,B]
						unchangings = [B,A]
					else:
						changings = [B,A]
						unchangings = [A,B]
				elif collision_type == pc.case.IIIA:
					if self.anticol.verbose:
						print("\n\nSolving phi-theta collision!\n")
					changings = [A]
					unchangings = [B] ## Theta Fiber
				elif collision_type == pc.case.IIIB:
					if self.anticol.verbose:
						print("\n\nSolving theta-phi collision!\n")
					changings = [B]
					unchangings = [A] ## Theta fiber
				# No need to loop over changing unchanging because its the same spatial collision between the two
				init_type = self.collider.spatial_collision_between_positioners(A, B, tpss[A], tpss[B])
				print('init_type:',A,tpss[A],B,tpss[B],init_type)
				if init_type != pc.case.I:
					if self.anticol.verbose:
						print("The current situation can't be resolved in this configuration, as the initial " + \
							  "location overlaps with a neighboring positioner.")
					continue
				for changing, unchanging in zip(changings, unchangings):
					fin_type = self.collider.spatial_collision_between_positioners(changing, unchanging, tpfs[changing], tpss[unchanging])
					if fin_type != pc.case.I:
						if self.anticol.verbose:
							print("The current situation can't be resolved in this configuration, as the final " + \
								  "goal overlaps with a neighboring positioner.")
						changings.remove(changing)
						unchangings.remove(unchanging)
				if len(changings) == 0:
					continue
			elif collision_type in [pc.case.GFA,pc.case.PTL]:
				## Test for problems in starting or finishing location
				init_type = self.collider.spatial_collision_with_fixed(A, tpss[A])
				fin_type = self.collider.spatial_collision_with_fixed(A, tpfs[A])
				if init_type != pc.case.I:
					if self.anticol.verbose:
						print("The current situation can't be resolved in this configuration, as the initial " + \
							  "location overlaps with a GFA or petal boundary")
					continue
				elif fin_type != pc.case.I:
					if self.anticol.verbose:
						print("The current situation can't be resolved in this configuration, as the final " + \
							  "goal overlaps with a GFA or petal boundary")
					continue
				## Verbosely tell what kind of collision we're about to resolve
				if collision_type == pc.case.GFA:
					if self.anticol.verbose:
						print("\n\nSolving GFA\n")
				elif collision_type == pc.case.PTL:
					if self.anticol.verbose:
						print("\n\nSolving Petal\n")
				## Assign lists of indices for use in upcoming for loop
				changings = [A]
				unchangings =[B] ## B is None

			## Loop over posibilities of which positioner moves and which is stationary
			for changing, unchanging in zip(changings,unchangings):
				if changing in neighbor_ofaltered:
					continue

				## Get the posmodel of the positioner we'll be working with
				## and info about it's neighbors
				changing_posmodel = self.collider.posmodels[changing]
				neighbor_ids = self.collider.pos_neighbors[changing]
				fixed_neighbors = self.collider.fixed_neighbor_cases[changing]

				if len(set(neighbor_ids).intersection(altered_pos))>0:
					continue
	
				## Set a boolean if the petal is something we need to avoid
				avoid_petal = (pc.case.PTL in fixed_neighbors)
				
				## if we collided with a positioner. Make sure the positioner is a neighbor
				## otherwise something strange has happened
				if unchanging != None and unchanging not in neighbor_ids:
					if self.anticol.verbose:
						print("Make sure the neighbors include the the positioner that it supposedly collided with. Adding posnum {}".format(unchanging))
					neighbor_ids = np.append(neighbor_ids,unchanging)
				if changing in neighbor_ids:
					if self.anticol.verbose:
						print('The positioner claims to have itself as a neighbor? posnum {}'.format(changing))
						if self.anticol.use_pdb:
							pdb.set_trace()
					else:
						continue

				start = tpss[changing]
				target = tpfs[changing]

				if self.anticol.verbose:
					print("Trying to correct positioners {},{} with {} avoidance".format(A,B,algorithm))
				## If the target is where we start, something weird is up
				if target[0] == start[0] and target[1]==start[1] and self.anticol.verbose and self.anticol.use_pdb:
					print("target and start are identical for id {}".format(A))
					pdb.set_trace()
					
				## Create a dictionary called neighbors with all useful information of the neighbors
				neighbors = {}
				xns = []
				yns = []
				nids = len(neighbor_ids)
				neighbors['theta_body_xns'] = np.ndarray(nids)
				neighbors['theta_body_yns'] = np.ndarray(nids)
				neighbors['xoffs'] = np.ndarray(nids)
				neighbors['yoffs'] = np.ndarray(nids)
				neighbors['ids'] = neighbor_ids

				neighbors['phins'] = np.ndarray(nids)
				neighbors['R1s'] = np.ndarray(nids)
				neighbors['R2s'] = np.ndarray(nids)
				neighbors['thetans'] = np.ndarray(nids)
				neighbors['thetants'] = np.ndarray(nids)
				neighbors['phints'] = np.ndarray(nids)
				neighbors['posmodels'] = np.ndarray(nids).astype(type(changing_posmodel))

				for i,posid in enumerate(neighbor_ids):
					neighbors['posmodels'][i] = self.collider.posmodels[posid]
					neighbors['xoffs'][i] = self.anticol.xoffs[posid]
					neighbors['yoffs'][i] = self.anticol.yoffs[posid]
					neighbors['R1s'][i] = self.anticol.r1s[posid]
					neighbors['R2s'][i] = self.anticol.r2s[posid]
					neighbors['phins'][i] = tpss[posid][pc.P]
					neighbors['thetans'][i] = tpss[posid][pc.T]
					neighbors['thetants'][i] = tpfs[posid][pc.T]
					neighbors['phints'][i] = tpfs[posid][pc.P]

				# todo-anthony make compatible with various tp offsets and tp ranges, and use proper transforms instead of saved values
				## Loop through the neighbors and calculate the x,y's for each
				for thit,pit,xoff,yoff,r1 in zip(neighbors['thetans'],neighbors['phins'],neighbors['xoffs'],neighbors['xoffs'],neighbors['R1s']):
					theta_bods = self.anticol.ultra_highres_posoutlines.central_body_outline([thit,pit],[xoff,yoff])
					phi_arms = self.anticol.ultra_highres_posoutlines.phi_arm_outline([thit,pit],r1, [xoff,yoff])
					xns.extend(theta_bods[0,:])
					xns.extend(phi_arms[0,:])
					yns.extend(theta_bods[1,:])
					yns.extend(phi_arms[1,:])
	
				## If we have to avoid the petal, do some work to find the x,y location
				## of the petal and place some 'avoidance' objects along it so that
				## our positioner is repulsed by them and thus the petal edge
				if avoid_petal:
					petalxys = self.anticol.ultra_highres_posoutlines.petal_outline(self.anticol.xoffs[changing],self.anticol.yoffs[changing],\
											self.anticol.neighborhood_radius)
					xns.extend(petalxys[0,:])
					yns.extend(petalxys[1,:])

				#xyns = changing_posmodel.trans.obsXY_to_flatXY([xns,yns])
			
				neighbors['xns'] = np.asarray(xns)
				neighbors['yns'] = np.asarray(yns)

				### check for the consistancy of the x and y values. Make sure they don't overlap
				if np.any( np.hypot(neighbors['xns']-self.anticol.xoffs[changing], neighbors['yns']-self.anticol.yoffs[changing] ) < 0.3):
					print('A neighbor is within 0.3 millimeters of the center of the changing positioner')
					if self.anticol.use_pdb:
						pdb.set_trace()
				
				## tbody_corner_locations has the xy coordinates of tracer points
				## around the central body of the positioner at ALL theta rotations
				## all we need to do is offset this by the positioner's offset
				central_body_matrix_locations = self.anticol.central_body_matrix.copy()
				central_body_matrix_locations[:,0,:] += self.anticol.xoffs[changing]
				central_body_matrix_locations[:,1,:] += self.anticol.yoffs[changing]
				phi_arm_matrix_locations = self.anticol.phi_arm_matrix.copy()
				phi_arm_matrix_locations[:,:,0,:] += self.anticol.xoffs[changing]
				phi_arm_matrix_locations[:,:,1,:] += self.anticol.yoffs[changing]

				## Assign the max and min angles for theta and phi, quantized to integers
				obs_tp_minmax = self.get_targetable_obstp(changing_posmodel).astype(int)
				theta_indices = (np.arange(obs_tp_minmax[0][0],obs_tp_minmax[0][1]+1) - self.anticol.min_default_theta)% 360
				phi_indices = (np.arange(obs_tp_minmax[1][0],obs_tp_minmax[1][1]+1) - self.anticol.min_default_phi)

				if np.any(theta_indices<0):
					if self.anticol.verbose:
						print("theta indices in avoid_collisions_astar include negatives")
						if self.anticol.use_pdb:
							pdb.set_trace()
				if np.any(phi_indices<0):
					if self.anticol.verbose:
						print("phi indices in avoid_collisions_astar include negatives")
						if self.anticol.use_pdb:
							pdb.set_trace()

				cut_cent_bod_matrix = np.ndarray((len(theta_indices),central_body_matrix_locations.shape[1],central_body_matrix_locations.shape[2]))
				cut_phi_arm_matrix = np.ndarray((len(theta_indices),len(phi_indices),phi_arm_matrix_locations.shape[2],phi_arm_matrix_locations.shape[3]))

				for i in range(theta_indices.size):
					rot_obs_t_index = theta_indices[i]
					#cut_cent_bod_matrix[i,:,:] = np.asarray(changing_posmodel.trans.obsXY_to_flatXY([central_body_matrix_locations[rot_obs_t_index,0,:],central_body_matrix_locations[rot_obs_t_index,1,:]]))
					cut_cent_bod_matrix[i,:,:] = np.asarray([central_body_matrix_locations[rot_obs_t_index,0,:],central_body_matrix_locations[rot_obs_t_index,1,:]])
					for j in range(phi_indices.size):
						rot_obs_p_index = phi_indices[j]
						#cut_phi_arm_matrix[i,j,:,:] = np.asarray(changing_posmodel.trans.obsXY_to_flatXY([phi_arm_matrix_locations[rot_obs_t_index,rot_obs_p_index,0,:],phi_arm_matrix_locations[rot_obs_t_index,rot_obs_p_index,1,:]]))
						cut_phi_arm_matrix[i,j,:,:] = np.asarray([phi_arm_matrix_locations[rot_obs_t_index,rot_obs_p_index,0,:],phi_arm_matrix_locations[rot_obs_t_index,rot_obs_p_index,1,:]])

				## With the positioner and neighbors setup, resolve the specific scenario and
				## return dt,dp,pausetime  lists that I can convert into a new movetable
				#pdb.set_trace()
				if algorithm == 'astar':
					dts,dps,times, test_outputs = inertial_bidirectional_astar_pathfinding(\
													 curmodel=changing_posmodel,start=start,\
													 target=target, neighbors=neighbors, \
													 thetaxys=cut_cent_bod_matrix, \
													 phixys=cut_phi_arm_matrix, \
													 anticol_params=self.anticol)

					nresult_rows = len(test_outputs['heuristic'])
					for key,val in test_outputs.items():
						if key in run_results.keys():
							run_results[key].extend(val)
						else:
							run_results[key] = list(val)
					run_results['tpstart'].extend([start]*nresult_rows)
					run_results['tpgoal'].extend([target]*nresult_rows)
					run_results['idx_changing'].extend([changing]*nresult_rows)
					run_results['idx_unchanging'].extend([unchanging]*nresult_rows)
					run_results['movetype'].extend([step]*nresult_rows)
					run_results['case'].extend([collision_type]*nresult_rows)
				else:
					continue
	
				## If length 0, don't create.
				if dts is None or len(dts)==0:
					if self.anticol.verbose:
						print("Number of rows in the new version of the table is: %d" % 0)
					continue
	
				## Convert steps into a new movetable
				new_changing_table = posmovetable.PosMoveTable(changing_posmodel)
				old_changing_table = tables[changing]

				## if length 1, create with one step.
				## else length > 1, add all steps
				if np.isscalar(dts):
					if self.anticol.verbose:
						print("Number of rows in the new version of the table is: %d" % 1)       
					new_changing_table.set_move(0, pc.T, dts)
					new_changing_table.set_move(0, pc.P, dps)
					new_changing_table.set_prepause(0, times)
					new_changing_table.set_postpause(0,0.0)
					itter = 1
				else:
					if self.anticol.verbose:
						print("Number of rows in the new version of the table is: %d" % dts.size)
					itter = 0
					for dt, dp, time in zip(dts,dps,times):
						new_changing_table.set_move(itter, pc.T, dt)
						new_changing_table.set_move(itter, pc.P, dp)
						new_changing_table.set_postpause(itter,0.0)
						new_changing_table.set_prepause(itter, time)
						itter += 1

				## Replace the old table with the newly created one
				newmovetime = new_changing_table.for_schedule['stats']['net_time'][dts.size-1]
				tables[changing] = new_changing_table

				prepauses = []
				for posid in neighbor_ids:
					table = tables[posid]
					prepauses.append(table.rows[0].data['prepause'])
					prepause = max(newmovetime, table.rows[0].data['prepause'])
					table.set_prepause(0, prepause)

				indices, coltype = self._check_single_positioner_for_collisions(tpss,tables,changing)
				print(coltype)
				print(indices)
				if len(set(coltype)) ==1 and coltype[0] == pc.case.I:
					stallmovetimes.append(newmovetime)
					altered_pos.append(changing)
					neighbor_ofaltered.union(set(neighbor_ids))
					for posid,table in tables.items():
						if posid == changing or posid in neighbor_ids:
							continue
						else:
							prepause = max(newmovetime,table.rows[0].data['prepause'])
							table.set_prepause(0, prepause)
					if self.anticol.verbose:
						print("Successfully found a schedule that avoids the collision!")
					break
				else:
					if self.anticol.verbose:
						print("Failed to find a valid avoidance movetable!")
					tables[changing] = old_changing_table
					for prep_itter, posid in enumerate(neighbor_ids):
						prepause = prepauses[prep_itter]
						table = tables[posid]
						table.set_prepause(0, prepause)
			## end of for loop over movable colliding positioners
			if self.anticol.verbose:
				if A not in altered_pos and B not in altered_pos:
					print("Failed to find a solution. Nothing has been changed for positioners {} and {}".format(A,B))
		## end of while loop over all collisions

		if self.anticol.debug:
			try:
				with open(os.path.join(self.anticol.anim_save_folder,'run_results__{0}.csv'.format(self.anticol.anim_save_number)), 'w') as runresultsfile:
					keys = np.sort(list(run_results.keys()))
					line = ''
					for key in keys:
						line += key + ','
					runresultsfile.write(line[:-1] + '\n')
					for itt in range(len(run_results['heuristic'])):
						line = ''
						for key in keys:
							line += str(run_results[key][itt]) + ','
						runresultsfile.write(line[:-1] + '\n')
				self.anticol.anim_save_number += 1
			except:
				pass

		if len(altered_pos) > 0:
			## Correct timing so everything is in sync again
			maxstalltime = np.max(stallmovetimes)
			movetimes = []
			## Update the movetimes for every positioner for this step
			for posid,table in tables.items():
				movetime = table.for_schedule['stats']['net_time'][-1]
				movetimes.append(movetime)
				if posid in altered_pos:
					tempmovetime = stallmovetimes[altered_pos==posid]
					table.set_postpause(len(table.rows)-1, maxstalltime-tempmovetime)
				else:
					prepause = max(table.rows[0].data['prepause'],maxstalltime-movetime)
					table.set_prepause(0, prepause)


			if self.anticol.verbose:
				## Just double check for good measure
				## Find the new max time for this step, and update the pospauses
				maxtime = np.max(movetimes)
				print("Max time after anticollisions is: {}".format(maxtime))

			## animate
			if self.anticol.plotting == True:
				self._animate_movetables(tables, tpss)

		## After all collision avoidances attempted. Return the new list of movetables
		return tables, altered_pos
	  
	# iidea - zero the top percent instead of 1 at a time (quicker for large positioner numbers)

	# fbug understand why a zeroed positioner is still occasionally selected
	def _avoid_collisions_zerothorder(self,tables,collision_indices,tpss):
		'''
			The original, and simplest method of avoiding collisions.
			This just prevents the positioners that would collide from moving, 
			therefore preventing collisions.
			This method requires an interative approach since preventing a positioner
			from moving may mean that it will be in the way of a different positioner
			which also needs to be stopped.
			This converges quickly without a huge impact on surrounding positioners.
			
			Input:
				tables     list or array of all movetables
				collision_indices   list or array containing all of the array indices
									for tables and posmodels that you wish to prevent from 
									moving
									
			Output:
				tables    list or array of all movetables, where the tables at indices specified 
							by collision_indices have been prevented from moving.
		'''
		## Get a unique list of all indices causing problems
		## Check for collisions in the total rre movetable
		unique_indices = self._unique_inds(collision_indices)
		max_time = self._get_max_time(tables)

		## Create list of indices we'll set to zero
		zerod= []
		## Remove "None" cases corresponding to fixed collisions
		if None in unique_indices.keys():
			## Remove None from possible positioners
			unique_indices.pop(None)
			## Set all positioners that collide with none to be zeroed
			for a,b in collision_indices:
				if b is None:
					zerod.append(a)
			if self.anticol.verbose:
				print("Zerod 'None' colliders: {}".format(zerod))
			for index in np.unique(zerod):
				table = posmovetable.PosMoveTable(tables[index].posmodel)
				table.set_move(0, pc.T, 0.)
				table.set_move(0, pc.P, 0.)
				table.set_prepause(0, max_time)
				table.set_postpause(0, 0.0)
				tables[index] = table

		## Iteratively zero the tables until no collisions remain
		## While there are still collisions, keep eliminating the positioners that collide
		## by setting them so that they don't move
		collision_indices, collision_types = self._check_for_collisions(tpss, tables)
		itter = 0
		ncols = len(collision_indices)
		while ncols > 0 and itter < 2 * len(tables):
			if self.anticol.verbose:
				self._printindices('Collisions before zeroth order run ', itter, collision_indices)
			tables, zeroed_poss = self._zerothorder_avoidance_iteration(tables, collision_indices, tpss, zerod)
			if np.isscalar(zeroed_poss):
				zerod.append(zeroed_poss)
				if self.anticol.verbose:
					print("\nNumber zeroed: {}\n\n\n\n".format(1))
			else:
				zerod.extend(list(zeroed_poss))
				if self.anticol.verbose:
					print("\nNumber zeroed: {}\n\n\n\n".format(len(zeroed_poss)))
			collision_indices, collision_types = self._check_for_collisions(tpss, tables)
			ncols = len(collision_indices)
			itter += 1
		## animate
		if self.anticol.make_animations == True:
			self._animate_movetables(tables, tpss)
		return tables, zerod

	def _zerothorder_avoidance_iteration(self,tables, collision_indices, tpss, zerod):
		unique_indices = self._unique_inds(collision_indices)
		raveled_inds = np.ravel(collision_indices)
		init_collisions = np.unique(raveled_inds[raveled_inds != None])
		ninit_collisions = len(init_collisions) - 1
		possits_to_zero = []
		max_time = self._get_max_time(tables)
		max_collisions = max(unique_indices.values())
		for posid,ncollisions in unique_indices.items():
			if ncollisions == max_collisions:
				possits_to_zero.append(posid)

		possits_to_zero = np.unique(possits_to_zero)
		print(max_collisions, possits_to_zero)

		nonzero = set(possits_to_zero).difference(set(zerod))
		if len(nonzero)==1:
			best_pos = nonzero.pop()
			table = posmovetable.PosMoveTable(tables[best_pos].posmodel)
			table.set_move(0, pc.T, 0.)
			table.set_move(0, pc.P, 0.)
			table.set_prepause(0, max_time)
			table.set_postpause(0, 0.0)
			tables[best_pos] = table
		elif len(possits_to_zero)==1:
			best_pos = possits_to_zero[0]
			table = posmovetable.PosMoveTable(tables[best_pos].posmodel)
			table.set_move(0, pc.T, 0.)
			table.set_move(0, pc.P, 0.)
			table.set_prepause (0, max_time)
			table.set_postpause(0, 0.0)
			tables[best_pos] = table
		else:
			## For the colliding indices, simply don't move them
			dn_colls = []
			for id in possits_to_zero:
				if id in zerod:
					dn_colls.append(-99)
					continue
				#ninit_collisions = unique_indices[index]
				old_table = tables[id]
				table = posmovetable.PosMoveTable(old_table.posmodel)
				table.set_move(0, pc.T, 0.)
				table.set_move(0, pc.P, 0.)
				table.set_prepause (0, max_time)
				table.set_postpause(0, 0.0)
				tables[id] = table
				itter_collinds, itter_colltypes = self._check_single_positioner_for_collisions(tpss,tables,id)
				raveled_inds = np.ravel(itter_collinds)
				if len(raveled_inds)>1:
					fin_collisions = np.unique(raveled_inds[raveled_inds != None])
				elif raveled_inds is None:
					fin_collisions = np.asarray([])
				else:
					fin_collisions = np.asarray(raveled_inds)
				nfin_collisions = len(fin_collisions)-1
				dn_colls.append(ninit_collisions-nfin_collisions)
				tables[id] = old_table
				del table
			best_choice = np.argmax(dn_colls)
			best_pos = possits_to_zero[best_choice]
			table = posmovetable.PosMoveTable(tables[best_pos].posmodel)
			table.set_move(0, pc.T, 0.)
			table.set_move(0, pc.P, 0.)
			table.set_prepause(0, max_time)
			table.set_postpause(0, 0.0)
			tables[best_pos] = table
		return tables, best_pos

	def _get_tabletype(self):
		## Now look at requests. if moves are small enough, move directly without RRE unless
		## explicitly told never to move direct
		dts_list,dps_list = [],[]
		for posid,req in self.requests.items():
			posmodel = req['posmodel']
			if posmodel.posid != posid and self.anticol.verbose:
				print("The posid of the request posmodel didn't match the posid key!")

			## Find the total extent of the move and save that to a list
			dtdp = posmodel.trans.delta_posTP(req['targt_posTP'], \
											  req['start_posTP'], range_wrap_limits='targetable')
			dts_list.append(dtdp[pc.T])
			dps_list.append(dtdp[pc.P])

		dts,dps = np.asarray(dts_list),np.asarray(dps_list)
		if np.all(dts < self.anticol.theta_direct_threshold) and np.all(dps < self.anticol.phi_direct_threshold) and not self.anticol.never_direct:
			if self.anticol.verbose:
				print("Scheduling a direct move, with AC")
			table_type='direct'
		else:
			## Make sure that the table type option is one of the allowed keywords
			for opt in self.anticol.table_type_options:
				if self.anticol.default_table_type.lower() == opt.lower() and self.anticol.default_table_type != opt:
					self.anticol.default_table_type = opt
			if self.anticol.default_table_type not in self.anticol.table_type_options:
				print_str = 'Table type was not one of: '
				for opt in self.anticol.table_type_options:
					print_str += '{}, '.format(opt)
				print(print_str+'. Exiting')
				raise(TypeError)
			if self.anticol.verbose:
				print("Scheduling move with {} and AC".format(self.anticol.default_table_type))
			table_type=self.anticol.default_table_type

		return table_type

	# todo-anthony is this still most efficient and accurate way?
	def _get_max_time(self,tabledicts):
		## Find out how long the longest move takes to execute
		movetimes = np.asarray([table.for_schedule['stats']['net_time'][-1] for table in tabledicts.values()])
		if self.anticol.verbose:
			print("std of movetimes was: ", np.std(movetimes))
		max_time = np.max(movetimes)
		return max_time

	# todo-anthony double check this code
	def _check_for_collisions(self,tps,tables):
		'''
			Find what positioners collide, and who they collide with
			Inputs:
				tps:  list or numpy array of theta,phi pairs that specify the location
						of every positioner
				tables:   dict of all the movetables with posid's as keys
				
			Outputs:
			   All 3 are numpy arrays giving information about every collision that occurs.
				collision_indices: list index which identifies the positioners that collide
									this has 2 indices in a pair [*,*] if 2 positioners collided
									or [*,None] if colliding with a wall of fiducial.
				collision_types:   Type of collision as specified in the pc class
		'''
		sweeps, collisions_ids, collision_type, earliest_collision = \
			self._get_sweeps_and_collision_info(tps, tables)

		collision_id_pairs = []
		collision_types = []
		posids_accounted_for = set()
		for posid,posid_collisions in collisions_ids.items():
			if collision_type[posid] != pc.case.I:
				if posid_collisions[0] not in posids_accounted_for:
					collision_id_pairs.append(posid_collisions)
					posids_accounted_for.add(posid_collisions[0])
					posids_accounted_for.add(posid_collisions[1])
					collision_types.append(collision_type[posid])
		
		## return the earliest collision time and collision indices
		return np.asarray(collision_id_pairs), np.asarray(collision_types)
	
	# todo-anthony double check this code
	def _check_single_positioner_for_collisions(self,tps,tablesdict,posid):
		'''
			Find what positioners collide, and who they collide with
			Inputs:
				tps:  list or numpy array of theta,phi pairs that specify the location
						of every positioner
				tablesdict:  dictionary of all tables
				posid:  posid of the single positioner we want to check neighbors of
				
			Outputs:
			   All 3 are numpy arrays giving information about every collision that occurs.
				collision_indices: list index which identifies the positioners that collide
									this has 2 indices in a pair [*,*] if 2 positioners collided
									or [*,None] if colliding with a wall of fiducial.
				collision_types:   Type of collision as specified in the pc class
		'''
		#colrelations = self.collider.collidable_relations
		pos_neighbors = self.collider.pos_neighbors
		local_radius_tables = {key:tablesdict[key] for key in pos_neighbors}
		local_radius_tables[posid] = tablesdict[posid]
		local_radius_tps = {key:tps[key] for key in pos_neighbors}
		local_radius_tps[posid] = tps[posid]
		return self._check_for_collisions(local_radius_tps,local_radius_tables)

	def _get_sweeps_and_collision_info(self, tps, tables):
		'''
			Find what positioners collide, and who they collide with
			Inputs:
				tps:  list or numpy array of theta,phi pairs that specify the location
						of every positioner
				cur_poscollider:  poscollider object used to find the actual collisions
				tables:   dict of all the movetables with posid's as keys

			Outputs:
			   All 3 are numpy arrays giving information about every collision that occurs.
				collision_indices: list index which identifies the positioners that collide
									this has 2 indices in a pair [*,*] if 2 positioners collided
									or [*,None] if colliding with a wall of fiducial.
				collision_types:   Type of collision as specified in the pc class
		'''
		all_posids = [key for key in tables]  # Changed by Kai to work for only a group of positioners
		sweeps = {posid: PosSweep(posid) for posid in all_posids}
		collision_ids = {posid: [] for posid in all_posids}
		collision_type = {posid: pc.case.I for posid in all_posids}
		earliest_collision = {posid: np.inf for posid in all_posids}
		nontriv = 0
		colrelations = self.collider.collidable_relations
		for Aid, Bid, B_is_fixed in zip(colrelations['A'], colrelations['B'], colrelations['B_is_fixed']):
			if Aid not in tables.keys():
				continue
			if (not B_is_fixed) and (Bid not in all_posids):
				continue
			tableA = tables[Aid].for_schedule
			obsTPA = tps[Aid]
			if B_is_fixed:
				these_sweeps = self.collider.spacetime_collision_with_fixed(Aid, obsTPA, tableA)
			else:
				tableB = tables[Bid].for_schedule
				obsTPB = tps[Bid]
				these_sweeps = self.collider.spacetime_collision_between_positioners(Aid, obsTPA, tableA, \
																					 Bid, obsTPB, tableB)
			if these_sweeps[0].collision_time <= earliest_collision[Aid]:
				nontriv += 1
				sweeps[Aid] = these_sweeps[0]
				collision_type[Aid] = these_sweeps[0].collision_case
				if B_is_fixed:
					collision_ids[Aid] = [Aid, None]
				else:
					collision_ids[Aid] = [Aid, Bid]
				if these_sweeps[0].collision_time < np.inf:
					earliest_collision[Aid] = these_sweeps[0].collision_time

			if len(these_sweeps) == 1 or B_is_fixed:
				continue

			for i in range(1, len(these_sweeps)):
				if these_sweeps[i].collision_time < earliest_collision[Bid]:
					nontriv += 1
					sweeps[Bid] = these_sweeps[i]
					earliest_collision[Bid] = these_sweeps[i].collision_time
					if B_is_fixed:
						collision_ids[Bid] = [Aid, None]
					else:
						collision_ids[Bid] = [Aid, Bid]
					collision_type[Bid] = these_sweeps[i].collision_case

		return sweeps, collision_ids, collision_type, earliest_collision

	def _animate_movetables(self,tables, tps):
		'''
			Find what positioners collide, and who they collide with
			Inputs:
				tps:  list or numpy array of theta,phi pairs that specify the location
						of every positioner
				tables:   movetable dict

			Outputs:
			   All 3 are numpy arrays giving information about every collision that occurs.
				collision_indices: list index which identifies the positioners that collide
									this has 2 indices in a pair [*,*] if 2 positioners collided
									or [*,None] if colliding with a wall of fiducial.
				collision_types:   Type of collision as specified in the pc class
		'''
		sweeps, collisions_ids, collision_type, earliest_collision = \
			self._get_sweeps_and_collision_info(tps, tables)

		## dict to list
		#sweeps_list = [sweep for sweep in list(sweeps.values()) if sweep != []]
		sweeps_list = list(sweeps.values())


		## animate
		self.collider.animate(sweeps=sweeps_list,savedir=self.anticol.anim_save_folder,\
						 vidname=self.anticol.anim_template.format(savenum=self.anticol.anim_save_number))

		if os.sys.platform == 'win32' or os.sys.platform == 'win64':
			delcom = 'del'
		else:
			delcom = 'rm'
		os.system('{delcommand} {savedir}*.png'.format(delcommand=delcom, savedir=os.path.join(self.anticol.anim_save_folder,'frame')))
		self.anticol.anim_save_number += 1

	def _combine_tables(self,tabledicts):
		## For each positioner, merge the three steps (r,r,e) into a single move table
		output_tables = {}
		for posid,retract_table in tabledicts['retract'].items():
			## start with copy of the retract step table
			## Note that we don't change final_creep or backlash for this final table
			newtab = posmovetable.PosMoveTable(retract_table.posmodel)

			for step in ['retract','rotate','extend']:
				table = tabledicts[step][posid]
				newtab.extend(table)

			output_tables[posid] = newtab
		return output_tables

	def _combine_single_table(self,tabledicts):
		## start with copy of the retract step table
		## Note that we don't change final_creep or backlash for this final table
		newtab = posmovetable.PosMoveTable(tabledicts['retract'].posmodel)
		for step in ['retract','rotate','extend']:
			table = tabledicts[step]
			newtab.extend(table)
		return newtab

	def _condense(self,dts,dps):
		'''
			Important routine. Goes through a newly created set of moves and 
			tries to eliminate redundant rows.
			If the same move is performed two timesteps in a row, they are combined
			into a single longer step
			This reduces the number of final steps in the movetable
			If both dt and dp for a step is 0, wait time is added after the previous move

			input:
				dts:    np.array  each value is the amount of change in theta
								  for that timestep
				dps:    np.array  each value is the amount of change in phi
								  for that timestep
			output:
				output_t: np.array   list of delta_theta moves after all merging is done
				output_p: np.array   list of delta_phi moves after all merging is done
				output_times: np.array   list of waittimes after each move after all merging is done
				
		'''
		## Intialize the arrays that will be output
		output_t = [dts[0]]
		output_p = [dps[0]]
		output_times = [0.]
		current_column = 0
		## Loop through the given array of dthetas,dphis
		for i in range(1,dts.size):
			## If we're not moving, we don't make a new move, we only add waittime
			## after the current move
			if dts[i]==0 and dps[i]==0:
				output_times[current_column] += self.anticol.dt
			## If the change in theta and phi is the same as before,
			## We don't need a new step, just increase the time we perform
			## the previous step
			elif dts[i]==dts[i-1] and dps[i]==dps[i-1]:
				output_t[current_column] += dts[i]
				output_p[current_column] += dps[i]
			## if none of the cases above, add a new move in the movetable
			## for the given dtheta, dphi, with no waittime
			else:
				output_t.append(dts[i])
				output_p.append(dps[i])
				# note the 0 here. wait times aren't considered
				output_times.append(0.)
				current_column += 1
		return np.asarray(output_t),np.asarray(output_p),np.asarray(output_times)

	def _reverse_for_extension(self,tables):

		## For each positioner, merge the three steps (r,r,e) into a single move table
		output_tables = {}
		for posid,table in tables.items():
			## start with copy of the retract step table
			newtab = posmovetable.PosMoveTable(table.posmodel)
			rows = table.rows.copy()
			rows = rows[::-1]
			#stats = {key:[table.rows[ind].data[key] for ind in range(len(table.rows))] for key in ['dT_ideal','dP_ideal','move_time' ]}
			#print("Before, Net time:{} t:{} p:{}".format(stats['move_time'], stats['dT_ideal'], stats['dP_ideal']))
			for i,row in enumerate(rows):
				dt, dp = row.data['dT_ideal'], row.data['dP_ideal']
				pre, post = row.data['prepause'], row.data['postpause']
				newtab.set_move(i, pc.T, -1*dt)
				newtab.set_move(i, pc.P, -1*dp)
				newtab.set_prepause(i, post)
				newtab.set_postpause(i, pre)
			#newstats = { key:[newtab.rows[ind].data[key] for ind in range(len(newtab.rows))] for key in ['dT_ideal','dP_ideal','move_time' ]}
			# print("After, Net time:{} t:{} p:{}\n".format(stats['move_time'], stats['dT_ideal'], stats['dP_ideal']))
			output_tables[posid] = newtab
		return output_tables        

		
	# todo-anthony what should we do with this?

	def _assign_properly(self,theta,phi):
		'''
		 Helper function that takes two variables theta and phi and returns a list pair of 
		 theta,phi in the order specified by pc.T and pc.P
		 Input:
			 Created for scalar theta, phi but there is nothing preventing other variable types
		 Output:
			 list pair that is correctly ordered by pc.T and pc.P
		'''
		tp = [None,None]
		tp[pc.T] = theta
		tp[pc.P] = phi
		return tp            

	def get_targetable_obstp(self,posmodel):
		post_minmax = posmodel.targetable_range_T
		posp_minmax = posmodel.targetable_range_P
		tmin, pmin = posmodel.trans.posTP_to_obsTP([post_minmax[0], posp_minmax[0]])
		tmax, pmax = posmodel.trans.posTP_to_obsTP([post_minmax[1], posp_minmax[1]])
		return np.asarray([[tmin,tmax],[pmin,pmax]])
		
	def _printindices(self,statement,step,indices):
		'''
			Helper function that prints information about the unique indices
			involved in collisions
		'''
		unique = self._unique_inds(indices)
		print('{} {}   at indices:    {}'.format(statement,step,unique))

	def _unique_inds(self,indices):
		'''
		  Counts the indices in the list and returns a Counter object
		  that holds information about the number of times each index appears
		'''         
		return Counter(np.ravel(indices))
	def _get_tabletype(self):
                ## Now look at requests. if moves are small enough, move directly without RRE unless
                ## explicitly told never to move direct
		dts_list,dps_list = [],[]
		for posid,req in self.requests.items():
			posmodel = req['posmodel']
			if posmodel.posid != posid and self.anticol.verbose:
				print("The posid of the request posmodel didn't match the posid key!")

                        ## Find the total extent of the move and save that to a list
			dtdp = posmodel.trans.delta_posTP(req['targt_posTP'],req['start_posTP'], range_wrap_limits='targetable')
			dts_list.append(dtdp[pc.T])
			dps_list.append(dtdp[pc.P])

		dts,dps = np.asarray(dts_list),np.asarray(dps_list)
		if np.all(dts < self.anticol.theta_direct_threshold) and np.all(dps < self.anticol.phi_direct_threshold) and not self.anticol.never_direct:
			if self.anticol.verbose:
				print("Scheduling a direct move, with AC")
			table_type='direct'
		else:
                        ## Make sure that the table type option is one of the allowed keywords
			for opt in self.anticol.table_type_options:
				if self.anticol.default_table_type.lower() == opt.lower() and self.anticol.default_table_type != opt:
					self.anticol.default_table_type = opt
			if self.anticol.default_table_type not in self.anticol.table_type_options:
				print_str = 'Table type was not one of: '
				for opt in self.anticol.table_type_options:
					print_str += '{}, '.format(opt)
				print(print_str+'. Exiting')
				raise(TypeError)
			if self.anticol.verbose:
				print("Scheduling move with {} and AC".format(self.anticol.default_table_type))
			table_type=self.anticol.default_table_type

		return table_type

class Anticol:
	def __init__(self,collider,petal,verbose, thetas=None,phis=None):
		##############################
		# User defineable parameters #
		##############################
		##** General PARAMS **##
		self.avoidance = 'tweak'#'astar' ## avoidance
		self.verbose = verbose
		self.plotting = True
		self.make_animations = False#True
		self.use_pdb = False#True
		self.debug = True
		self.collider = collider

		self.table_type_options = ['direct', 'RRE', 'RRrE']
		self.default_table_type = 'RRE'  # options in line above
		self.never_direct = False
		self.theta_direct_threshold = 3.
		self.phi_direct_threshold = 3.

		self._update_positioner_properties()

		## Define the phi position in degrees at which the positioner is safe
		self.phisafe = collider.Ei_phi

		# todo-anthony make compatible with various tp offsets and tp ranges
		## If thetas and phis aren't defined, define them to defaults
		if thetas is None:
			self.min_default_theta = -180
			self.max_default_theta = 180
			self.theta_inds = np.arange(self.min_default_theta,self.max_default_theta, 1)
		else:
			self.min_theta = np.min(thetas)
		if phis is None:
			self.min_default_phi = -20
			self.max_default_phi = 211
			self.phi_inds = np.arange(self.min_default_phi, self.max_default_phi, 1)

		## Some convenience definitions regarding the size of positioners
		motor_width = 1.58
		self.rtol = 2*motor_width
		self.max_thetabody = 3.967-motor_width ## mm

		##** EM PARAMS **##
		## Define how close to a target you must before moving to the exact final position
		## **note the "true" tolerance is max(tolerance,angstep)**
		self.tolerance = 2.
		
		## How far in theta or Phi do you move on each iterative step of the avoidance method
		self.angstep = 6#12.
		
		self.neighborhood_radius = 10

		## Determine how close we can actually need to get to the final target before calling it a success
		self.ang_threshold = max(self.tolerance, self.angstep)

		## to get accurate timestep information, we use a dummy posmodel
		self.dt = np.abs(self.angstep/petal.posmodels[0].axis[0].motor_to_shaft(petal.posmodels[0]._motor_speed_cruise))
		   
		## em potential computation coefficients
		self.coeffcr = 0.#10.0  ## central repulsive force, currently unused
		self.coeffca = 0.#100.0   ## central attractive force, currently unused
		self.coeffn =  6.0  ## repuslive force amplitude of neighbors and walls
		self.coeffa = 10.0  ## attractive force amplitude of the target location
		
		##** aSTAR PARAMS **##
		self.astar_tolerance_xy = 0.2 #3
		self.multitest = False
		self.astar_verbose = verbose
		self.astar_plotting = False
		self.astar_heuristic = 'euclidean'
		self.astar_weight = 1.2

		##** Animation Params **##
		self.anim_save_folder = os.path.join('..','figures',datetime.datetime.now().strftime('%Y%m%d%H%M'))
		if self.avoidance != 'astar':
			anim_save_prefix = 'anim_'
		else:
			anim_save_prefix = 'anim_hr-{}_tol-{}_wt-{}_'.format(self.astar_heuristic,self.astar_tolerance_xy,self.astar_weight)
		#anim_beginning = os.path.join(anim_save_folder,anim_save_prefix)
		self.anim_template = anim_save_prefix + '{savenum}.mp4'
		self.anim_save_number = 0
		if self.make_animations == True and not os.path.exists(self.anim_save_folder):
			os.makedirs(self.anim_save_folder)

		##############################################
		# Parameters defined by hardware or software #
		##############################################
		## Create an outlines class object with spacing comparable to the tolerance
		## of the search
		# iidea - higher res on non-rotating neighbors ?
		# todo-anthony make compatible with various tp offsets and tp ranges
		posoutlines = PosOutlines(collider, spacing=2.0*self.astar_tolerance_xy)
		self.ultra_highres_posoutlines = PosOutlines(collider, spacing=0.5*self.astar_tolerance_xy)
		##Note the approximation here
		## Todo - anthony make this work with new dictionary structure
		r1 = np.max(list(self.r1s.values()))
		self.central_body_matrix = posoutlines.central_body_outline_matrix(self.theta_inds)
		self.phi_arm_matrix = posoutlines.phi_arm_outline_matrix(theta_inds=self.theta_inds,phi_inds=self.phi_inds,xoff=r1,yoff=0)
		del posoutlines
		
	def _update_positioner_properties(self):
		self.xoffs = self.collider.x0
		self.yoffs = self.collider.y0
		self.toffs = self.collider.t0
		self.poffs = self.collider.p0
		self.r1s = self.collider.R1
		self.r2s = self.collider.R2

# iidea inherit from pospoly?
class PosOutlines:#(PosPoly):
	"""Represents a higher resolution version of the collidable polygonal 
	envelope definition for a mechanical component of the fiber positioner."""

	def __init__(self,collider,spacing=0.4):
		#self, points, point0_index=0, close_polygon=True):
		self.spacing = spacing
		self.thetapoints = self._highres(collider.keepout_T.points.copy())
		self.phipoints = self._highres(collider.keepout_P.points.copy())
		self.ferrulepoints = self._highres(collider.ferrule_poly.points.copy())
		possible_petal_pts = collider.keepout_PTL.points.copy()
		petaly = possible_petal_pts[1,:]
		actual_petal = np.where((petaly > np.min(petaly) + 1) & (petaly < np.max(petaly) - 1.))[0]
		true_petal_pts = possible_petal_pts[:,actual_petal]
		self.petalpoints = self._highres(true_petal_pts)
		self.petalpoints = collider.keepout_PTL.points.copy()
		self._rotmat2D_deg = collider.keepout_T._rotmat2D_deg
		#super(PosOutlines, self).__init__(self,collider,spacing=0.4)
   
	def phi_arm_outline(self, obsTP, R1, xyoff):
		"""Rotates and translates the phi arm to position defined by the positioner's
		xy0 and the argued obsTP (theta,phi) angles.
		"""
		polypts = self.phipoints.copy()
		polypts = self._rotate(polypts,obsTP[1])
		polypts = self._translate(polypts,R1, 0)
		polypts = self._rotate(polypts,obsTP[0])
		polypts = self._translate(polypts,xyoff[0], xyoff[1])
		return polypts
	
	def central_body_outline(self, obsTP, xyoff):
		"""Rotates and translates the central body of positioner identified by idx
		to it's xy0 and the argued obsT theta angle.
		"""
		polypts = self.thetapoints.copy()
		polypts = self._rotate(polypts,obsTP[0])
		polypts = self._translate(polypts,xyoff[0], xyoff[1])
		return polypts
	
	def ferrule_outline(self, obsTP, R1, R2, xyoff):
		"""Rotates and translates the ferrule to position defined by the positioner's
		xy0 and the argued obsTP (theta,phi) angles.
		"""
		polypts = self.ferrulepoints.copy()
		polypts = self._translate(polypts,R2, 0)
		polypts = self._rotate(polypts,obsTP[1])
		polypts = self._translate(polypts,R1,0)
		polypts = self._rotate(polypts,obsTP[0])
		polypts = self._translate(polypts,xyoff[0], xyoff[1])
		return polypts

	def petal_outline(self,positioner_x,positioner_y, radius):
		"""Returns the petal outline
		"""
		dx = self.petalpoints[0,:]-positioner_x
		dy = self.petalpoints[1,:]-positioner_y
		nearby = np.where(np.hypot(dx,dy) < radius)[0]
		return self.petalpoints[:,nearby]

	def central_body_outline_matrix(self,theta_inds):
		#all_theta_points = self.collider.keepout_T.points.copy()
		#theta_corner_locs = np.argsort(all_theta_points[0])[-4:]
		#theta_corner_locs = np.array([2,3,4])
		#theta_pts = all_theta_points[:,theta_corner_locs]
		all_angles = np.arange(360)
		thetas = all_angles[theta_inds]
		nthetas = len(thetas)
		theta_pts = np.asarray(self.thetapoints)
		rotation_matrices = self._rotmat2D_deg(thetas)
		#self.anticol.theta_corner_locations = np.asarray([np.dot(rotation_matrices[:,:,i], theta_corners) for i in range(thetas.size)])
		theta_corner_xyarray = np.zeros((nthetas,2,theta_pts.shape[1])) 

		for i in range(nthetas):
			theta_corner_xyarray[i,:,:] = np.dot(rotation_matrices[:,:,i], theta_pts)
		 
		return np.asarray(theta_corner_xyarray)

	def phi_arm_outline_matrix(self,theta_inds,phi_inds,xoff=0., yoff=0.):
		#all_phi_points = self.collider.keepout_P.points.copy()
		#phi_corner_locs = np.arange(7)
		#phi_pts = all_phi_points[:,phi_corner_locs]
		phi_pts = np.asarray(self.phipoints)

		all_angles = np.arange(360) # degrees around circle
		thetas = all_angles[theta_inds]
		phis = all_angles[phi_inds]
		phi_theta_offset = phis[0]-thetas[0]
		phi_inds_for_theta = (phis + phi_theta_offset) % 360
		nphis = len(phis)
		nthetas = len(thetas)
		## Assume mean arm length in order to perform these calculations only once
		rotation_matrices = self._rotmat2D_deg(all_angles)
		p_rotation_matrices = rotation_matrices.copy()[:,:,phi_inds]
		t_rotation_matrices = rotation_matrices[:,:,theta_inds]

		#phi_corners_rot1_transr1 = np.asarray([np.dot(rotation_matrices[:,:,i+phi_theta_offset], phi_pts)+[[r1],[0]] for i in range(nphis)])        
		phi_corner_xyarray = np.zeros((nthetas,nphis,2,phi_pts.shape[1])) 
		for j,phi in enumerate(phis):
			rot = np.dot(p_rotation_matrices[:,:,j], phi_pts)
			rot_trans = self._translate(points = rot, x=xoff, y=yoff)
			for i in range(nthetas):
				phi_corner_xyarray[i,j,:,:] = np.dot(t_rotation_matrices[:,:,i], rot_trans)
		 
		return np.asarray(phi_corner_xyarray)

	def _highres(self,endpts):
		closed_endpts = np.hstack([endpts,endpts[:,0].reshape(2,1)])
		diffs = np.diff(closed_endpts,axis=1)
		dists = np.hypot(diffs[0,:],diffs[1,:])
		#maxdiffs = diffs.max(axis=0)
		npts = np.ceil(dists/self.spacing).astype(np.int).clip(2,1e4)
		xs,ys = [],[]
		for i in np.arange(0,closed_endpts.shape[1]-1):
			xs.extend(np.linspace(closed_endpts[0,i],closed_endpts[0,i+1],npts[i]))
			ys.extend(np.linspace(closed_endpts[1,i],closed_endpts[1,i+1],npts[i]))
		return np.asarray([xs,ys])

	def _rotate(self, points, angle):
		"""Returns a copy of the polygon object, with points rotated by angle (unit degrees)."""
		return np.dot(self._rotmat2D_deg(angle), points)

	def _translate(self, points, x, y):
		"""Returns a copy of the polygon object, with points translated by distance (x,y)."""
		return points + np.array([[x],[y]])
		

