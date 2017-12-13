import posmovetable
import posconstants as pc

# External Dependencies
import numpy as np
from collections import Counter

# Temporary Debugging Dependencies
import matplotlib.pyplot as plt
import pdb
import copy as copymodule
from bidirect_astar import bidirectional_astar_pathfinding

class PosSchedule(object):
    """Generates move table schedules in local (theta,phi) to get positioners
    from starts to finishes. The move tables are instances of the PosMoveTable
    class.

    Note that the schedule may contain multiple move tables for the same positioner,
    under the assumption that another module (i.e. Petal) will generally be
    the one which merges any such tables in sequence, before sending off to the hardware.
    
    Initialize with the petal object this schedule applies to.
    """

    def __init__(self, petal,avoidance='EM',verbose=False):
        self.petal = petal
        self.move_tables = []
        self.requests = []
        
        thetas = np.arange(-200,200,1)
        phis = np.arange(0,200,1)
        self.anticol = Anticol(self.collider,self.petal,verbose, thetas,phis)       

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
        self.requests.append(new_request)

    def add_table(self, move_table):
        """Adds an externally-constructed move table to the schedule. If there
        is ANY such table in a given schedule, then the anti-collision algorithm
        will NOT be used. Generally, this method should only be used for internal
        calls by an expert user.
        """
        if self._deny_request_because_disabled(move_table.posmodel):
            return
        self.move_tables.append(move_table)
        self._merge_tables_for_each_pos()

    def schedule_moves(self, anticollision=True):
        """Executes the scheduling algorithm upon the stored list of move requests.

        A single move table is generated for each positioner that has a request
        registered. The resulting tables are stored in the move_tables list. If the
        anticollision argument is true, then the anticollision algorithm is run when
        generating the move tables.

        If there were ANY pre-existing move tables in the list, then ALL the target
        requests are ignored, and the anticollision algorithm is NOT performed.
        """
        if self.move_tables:
            return
        elif anticollision:
            self._schedule_with_anticollision()
        else:
            self._schedule_without_anticollision()

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
        already_requested_list = [p['posid'] for p in self.requests]
        was_already_requested = posid in already_requested_list
        return was_already_requested

    # internal methods
    def _merge_tables_for_each_pos(self):
        """In each case where one positioner has multiple tables, they are merged in sequence
        into a single table.
        """
        i = 0
        while i < len(self.move_tables):
            j = i + 1
            extend_list = []
            while j < len(self.move_tables):
                if self.move_tables[i].posmodel.posid == self.move_tables[j].posmodel.posid:
                    extend_list.append(self.move_tables.pop(j))
                else:
                    j += 1
            for e in extend_list:
                self.move_tables[i].extend(e)
            i += 1

    def _schedule_without_anticollision(self):
        while(self.requests):
            req = self.requests.pop(0)
            posmodel = req['posmodel']
            table = posmovetable.PosMoveTable(posmodel)
            dtdp = posmodel.trans.delta_posTP(req['targt_posTP'], \
                        req['start_posTP'], range_wrap_limits='targetable')
            table.set_move(0, pc.T, dtdp[0])
            table.set_move(0, pc.P, dtdp[1])
            table.set_prepause (0, 0.0)
            table.set_postpause(0, 0.0)
            table.store_orig_command(0, req['command'], req['cmd_val1'], req['cmd_val2'])
            table.log_note += (' ' if table.log_note else '') + req['log_note']
            self.move_tables.append(table)

    def _deny_request_because_disabled(self, posmodel):
        """This is a special function specifically because there is a bit of care we need to
        consistently take with regard to post-move cleanup, if a request is going to be denied.
        """
        enabled = posmodel.state.read('CTRL_ENABLED')
        if enabled == False: # this is specifically NOT worded as "if not enabled:", 
                             # because here we actually do not want a value of None 
                             # to pass the test, in case the parameter field 'CTRL_ENABLED'
                             # has not yet been implemented in the positioner's .conf file
            posmodel.clear_postmove_cleanup_cmds_without_executing()
            print(str(posmodel.state.read('POS_ID')) + \
                    ': move request denied because CTRL_ENABLED = ' + str(enabled))
            return True
        return False

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

        log_notes = []; commands = []            
        posmodels = []; tpstart = []; tptarg = []
        xoffs = []
        yoffs = []
        # Loop through the posunitids and the requests, and correctly order the request
        # information into the order set by posunitids
        for posunitid in self.petal.posids:
            for req in self.requests:
                if req['posmodel'].posid == posunitid:
                    posmodel = req['posmodel']
                    posmodels.append(posmodel)
                    xoffs.append(posmodel.state.read('OFFSET_X'))
                    yoffs.append(posmodel.state.read('OFFSET_Y'))
                    tpstart.append(posmodel.trans.posTP_to_obsTP(req['start_posTP']))
                    tptarg.append(posmodel.trans.posTP_to_obsTP(req['targt_posTP']))
                    log_notes.append(req['log_note'])
                    commands.append((0,req['command'],req['cmd_val1'],req['cmd_val2']))
                    break
        self.anticol.xoffs = np.asarray(xoffs)
        self.anticol.yoffs = np.asarray(yoffs)
        
        # Now that we have the requests curated and sorted. Lets do anticollision
        # using the PosAnticol.avoidance method specified 
        move_tables = self._run_RRE_anticol(tpstart,tptarg,posmodels)

        # Write a comment in each movetable
        for movetable,log,coms,pmod in zip(move_tables,log_notes,commands,posmodels):
            # Make sure that the ordering of everything is still correct by asserting
            # that the positioner id of the movetable matches the one defined originally
            # this throws an error if the two are not the same
            assert pmod.posid == movetable.posmodel.posid, "Ensure the movetable and posmodel match"
            movetable.store_orig_command(*coms)
            movetable.log_note += (' ' if movetable.log_note else '') + log
            
        # return the movetables as a list of movetables
        self.move_tables = move_tables
                                                    
    def _run_RRE_anticol(self,tps_list,tpf_list,posmodels):
        '''
            Code that generates move tables, finds the collisions,
            and updates move tables such that no collisions will occur.
            It returns the list of all movetables where none collide with
            one another or a fixed object.
        '''   
        # Name the three steps in rre (used for dictionary keys)
        order_of_operations = ['retract','rotate','extend']
    
        # Generate complete movetables under RRE method
        tabledicts = {item:[] for item in order_of_operations}   
        movetimes = {item:[] for item in order_of_operations}
        maxtimes = {item:0. for item in order_of_operations}
        tpstart = {item:[] for item in order_of_operations} 
        tpfinal = {item:[] for item in order_of_operations}
        
        # Loops through the requests
        # Each request must have retract, rotate, and extend moves
        # Which each have different start and end theta/phis
        for tps, tpf, cur_posmodel in zip(tps_list, tpf_list, posmodels):
            current_tables_dict = self._create_table_RRrEdict(tps, tpf,cur_posmodel)
            phi_inner = max(self.anticol.phisafe,tps[pc.P])
            tpstart['retract'].append(tps)
            tpfinal['retract'].append([tps[0],phi_inner])
            tpstart['rotate'].append([tps[0],phi_inner])
            tpfinal['rotate'].append([tpf[0],phi_inner])
            # **note extend is flipped (unflipped at end of anticol)** #
            tpstart['extend'].append(tpf)
            tpfinal['extend'].append([tpf[0],phi_inner])
            # Unwrap the three movetables and add each of r,r,and e to
            # a seperate list for that movetype
            # Also append the movetime for that move to a list
            for key in order_of_operations:
                movetime = current_tables_dict[key].for_schedule['move_time']
                tabledicts[key].append(current_tables_dict[key])
                movetimes[key].append(movetime[0])
                
        # For each of r, r, and e, find the maximum time that 
        # any positioner takes. The rest will be assigned to wait
        # until that slowest positioner is done moving before going to
        # the next move
        for key in order_of_operations:
            maxtimes[key] = max(movetimes[key])
            for table,movetime in zip(tabledicts[key],movetimes[key]): 
                if movetime<maxtimes[key]:
                    table.set_postpause(0,maxtimes[key]-movetime)
        if self.anticol.verbose:
            print("Max times to start are: ",maxtimes)
        
        # Define whether phi increases, decreases, or stays static
        #dp_directions = {'rotate':0,'retract':-1,'extend':1}
        
        # Redefine list as numpy arrays
        posmodels = np.asarray(posmodels)
        for step in order_of_operations:
            tabledicts[step] = np.asarray(tabledicts[step])
            tpstart[step] = np.asarray(tpstart[step])
            tpfinal[step] = np.asarray(tpfinal[step])
            movetimes[step] = np.asarray(movetimes[step])
        
        
        for step in order_of_operations:
            # Check for collisions
            collision_indices, collision_types = \
                    self._check_for_collisions(tpstart[step],tabledicts[step])
            
 
            # If no collisions, move directly to the next step
            if len(collision_indices) == 0:
                continue
            
            if self.anticol.verbose:
                print('\n\n\n\nStep: ',step,'    Round: 1/1:\n')
                self._printindices('Collisions before iteration ',1,collision_indices)  

            ncols = len(collision_indices)
  
            # Avoid the collisions that were found
            tabledicts[step],moved_poss = self._avoid_collisions(tabledicts[step],posmodels, \
                                    collision_indices, collision_types, tpstart[step], \
                                    tpfinal[step], step, maxtimes[step], \
                                    algorithm=self.anticol.avoidance)
                              
            if self.anticol.verbose:
                # Check for collisions
                collision_indices, collision_types = \
                        self._check_for_collisions(tpstart[step],tabledicts[step])
                self._printindices('Collisions after Round 1, in Step ',step,collision_indices)        
                print("\nNumber corrected: ",ncols-len(collision_indices),'\n\n\n\n')      

        #if not self.anticol.verbose:
        #    # Check for collisions
        #    collision_indices, collision_types = \
        #            self._check_for_collisions(tpstart['extend'],tabledicts['extend'])
            
        # The step is extend. If collisions still exist after avoidance,
        # Set that positioner to not move
        #tabledicts['extend'],moved_poss = self._avoid_collisions(tabledicts['extend'], posmodels, \
        #                                collision_indices, algorithm='zeroth_order')      

        tabledicts['extend'] = self._reverse_for_extension(tabledicts['extend'])
        output_tables = self._combine_tables(tabledicts)
    
        # Check for collisions in the total rre movetable
        collision_indices, collision_types = self._check_for_collisions(tps_list,output_tables)   
        
        # While there are still collisions, keep eliminating the positioners that collide
        # by setting them so that they don't move
        itter = 0
        ncols = len(collision_indices)
        while len(collision_indices)>0:
            if self.anticol.verbose:
                self._printindices('Collisions before zeroth order run ',itter,collision_indices)
            output_tables, moved_poss = self._avoid_collisions(output_tables,posmodels,collision_indices,algorithm='zeroth_order')
            collision_indices, collision_types = self._check_for_collisions(tps_list,output_tables)
            if self.anticol.verbose:
                print("\nNumber corrected: ",ncols-len(collision_indices),'\n\n\n\n') 
            ncols = len(collision_indices)
            itter += 1
                   
        if self.anticol.verbose:
            self._printindices('Collisions after completion of anticollision ','',collision_indices)           
        return output_tables
                                                
                                                    
    def _create_table_RREdict(self,tp_start, tp_final, current_positioner_model):
        '''
            Create the original movetable for the current positioner. This uses 
            the retract rotate extend framework and creates 3 seperate move tables.
            One for each of the r.r.e.
            Since all positioners should reach their final objectives in each portion before
            any can move to the next, each of the r.r.e. are independent (ie retract is independt of extend)
            Returns a dictionary of 3 move tables where the key is either retract rotate or extend.
        '''
        # Get a table class instantiation
        table = {}
        table['retract'] = posmovetable.PosMoveTable(current_positioner_model)
        table['rotate'] = posmovetable.PosMoveTable(current_positioner_model)
        table['extend'] = posmovetable.PosMoveTable(current_positioner_model)
        #redefine phi inner:
        phi_inner = max(self.anticol.phisafe,tp_start[pc.P])
        # Find the theta and phi movements for the retract move
        tpss = tp_start
        tpsi = self._assign_properly(tp_start[pc.T],phi_inner)
        dtdp = current_positioner_model.trans.delta_obsTP(tpsi,\
                            tpss, range_wrap_limits='targetable')
        table['retract'].set_move(0, pc.T, dtdp[pc.T])
        table['retract'].set_move(0, pc.P, dtdp[pc.P])
        table['retract'].set_prepause(0, 0.0)
        table['retract'].set_postpause(0, 0.0)
        del dtdp
        # Find the theta and phi movements for the theta movement inside the safety envelope
        tpfi = self._assign_properly(tp_final[pc.T],phi_inner)
        dtdp = current_positioner_model.trans.delta_obsTP(tpfi,\
                            tpsi, range_wrap_limits='targetable')
        table['rotate'].set_move(0, pc.T, dtdp[pc.T]) 
        table['rotate'].set_move(0, pc.P, dtdp[pc.P]) 
        table['rotate'].set_prepause(0, 0.0)
        table['rotate'].set_postpause(0, 0.0)
        del dtdp
        # Find the theta and phi movements for the phi extension movement
        tpff = tp_final
        dtdp = current_positioner_model.trans.delta_obsTP(tpff,\
                            tpfi, range_wrap_limits='targetable')
        table['extend'].set_move(0, pc.T, dtdp[pc.T])
        table['extend'].set_move(0, pc.P, dtdp[pc.P])
        table['extend'].set_prepause(0, 0.0)
        table['extend'].set_postpause(0, 0.0)
        # return this positioners rre movetable
        return table
        
    def _create_table_RRrEdict(self,tp_start, tp_final, current_positioner_model):
        '''
            Create the original movetable for the current positioner. This uses 
            the retract rotate extend framework and creates 3 seperate move tables.
            One for each of the r.r.e
            
            **with reversed extend method**
            
            Since all positioners should reach their final objectives in each portion before
            any can move to the next, each of the r.r.e. are independent (ie retract is independt of extend)
            Returns a dictionary of 3 move tables where the key is either retract rotate or extend.
        '''
        # Get a table class instantiation
        table = {}
        table['retract'] = posmovetable.PosMoveTable(current_positioner_model)
        table['rotate'] = posmovetable.PosMoveTable(current_positioner_model)
        table['extend'] = posmovetable.PosMoveTable(current_positioner_model)
        #redefine phi inner:
        phi_inner = max(self.anticol.phisafe,tp_start[pc.P])
        # Find the theta and phi movements for the retract move
        tpss = tp_start
        tpsi = self._assign_properly(tp_start[pc.T],phi_inner)
        dtdp = current_positioner_model.trans.delta_obsTP(tpsi,\
                            tpss, range_wrap_limits='targetable')
        table['retract'].set_move(0, pc.T, dtdp[pc.T])
        table['retract'].set_move(0, pc.P, dtdp[pc.P])
        table['retract'].set_prepause(0, 0.0)
        table['retract'].set_postpause(0, 0.0)
        del dtdp
        # Find the theta and phi movements for the theta movement inside the safety envelope
        tpfi = self._assign_properly(tp_final[pc.T],phi_inner)
        dtdp = current_positioner_model.trans.delta_obsTP(tpfi,\
                            tpsi, range_wrap_limits='targetable')
        table['rotate'].set_move(0, pc.T, dtdp[pc.T]) 
        table['rotate'].set_move(0, pc.P, dtdp[pc.P]) 
        table['rotate'].set_prepause(0, 0.0)
        table['rotate'].set_postpause(0, 0.0)
        del dtdp
        # Find the theta and phi movements for the phi extension movement
        tpff = tp_final
        dtdp = current_positioner_model.trans.delta_obsTP(tpfi,\
                            tpff, range_wrap_limits='targetable')
        table['extend'].set_move(0, pc.T, dtdp[pc.T])
        table['extend'].set_move(0, pc.P, dtdp[pc.P])
        table['extend'].set_prepause(0, 0.0)
        table['extend'].set_postpause(0, 0.0)
        # return this positioners rre movetable
        return table
       
    
    def _avoid_collisions(self, tables, posmodels, collision_indices, \
                          collision_types=[], tpss=[], tpfs=[], \
                          step='retract', maxtimes=np.inf, algorithm='astar'):
        '''
            Function that is called with a list of collisions that need to be avoided. This uses 
            a 'force law' type approach to generate moves that avoid neighboring positioners 
            that it would otherwise collide with.
        '''
        if algorithm.lower() == 'zeroth_order':
            return self._avoid_collisions_zerothorder(tables,posmodels,collision_indices)

        if step == 'rotate' and np.all(tpss<self.collider.Ei_phi):
            print("You want me to correct rotational collisions when all the phi motors are tucked in.")
            print("Sorry I can't help")
            return tables, []
        elif step == 'rotate':
            print("We currently don't have programming for rotation avoidance, as it shouldn't be physically possible")
            return tables, []
        # Create a set that contains all positioners involved in corrections. \
        # Only one alteration to a positioner neighborhood
        # per function call
        neighbor_ofaltered = set()

        # Unpack the starting and ending theta/phis for all collisions
        tss = np.asarray(tpss[:,pc.T])
        pss = np.asarray(tpss[:,pc.P])
        tfs = np.asarray(tpfs[:,pc.T])
        pfs = np.asarray(tpfs[:,pc.P])

        all_numeric_indices = []
        for a,b in collision_indices:
            if a is not None:
                all_numeric_indices.append(a)
            if b is not None:
                all_numeric_indices.append(b)

        col_ind_array = np.sort(np.unique(all_numeric_indices))
        #pdb.set_trace()
        starting_anticol_theta = tfs.copy()
        starting_anticol_phi = pfs.copy()
        goal_anticol_theta = tfs.copy()
        goal_anticol_phi = pfs.copy()
        for ind in col_ind_array:
            starting_anticol_theta[ind] = tss[ind]
            starting_anticol_phi[ind] = pss[ind]
            goal_anticol_theta[ind] = tfs[ind]
            goal_anticol_phi[ind] = pfs[ind]  
        #max_stall_time = 0
        altered_pos = [-99]
        stallmovetimes = [0]
        
        # R1 and R2 parameters and their theta/phi and x/y offsets
        # self.collider.R1 
        # self.collider.R2     <- arrays for each positiner
        # self.collider.xy0
        # self.collider.tp0 
        
        # Targetable theta_phi positions for all positioners
        # self.collider.tp_ranges 
        # safety phi values for each positioner
        # self.collider.Ei_polys, self.collider.Ee_polys
        
        # self.collider.keepout_PTL        
        # self.collider.place_phi_arm(idx, tp)
        # self.collider.place_central_body(idx, t)
        # self.collider.keepout_GFA
        # self.collider.ferrule_poly


        run_results = {'tpstart':[],'tpgoal':[],'idx_changing':[],'idx_unchanging':[],'case':[],'movetype':[],'heuristic':[],'weight':[],'pathlength_full':[np.nan],'pathlength_condensed':[],'found_path':[]}#'avoided_collision':[]                 

        # For each collision, check what type it is and try to resolve it          
        for current_collision_indices,collision_type in zip(collision_indices,collision_types):
            A,B = current_collision_indices
            if A in altered_pos:
                continue
            elif B in altered_pos:
                continue
            # Determine which positioner to have avoid the other, which depends on
            # the type of collisions
            if collision_type == pc.case.I:
                if self.anticol.verbose:
                    print("\n\nCollision was claimed, but case is non-collision Case I")
                continue
            elif collision_type == pc.case.II:
                if self.anticol.verbose:
                    print("\n\nSolving phi-phi collision!\n")
                # change larger phi since it has less distance to travel before safety
                if starting_anticol_phi[A] > starting_anticol_phi[B]:
                    changings = [A,B]
                    unchangings = [B,A]
                else:
                    changings = [B,A]
                    unchangings = [A,B]              
            elif collision_type == pc.case.IIIA:
                if self.anticol.verbose:
                    print("\n\nSolving phi-theta collision!\n")
                changings = [A]
                unchangings = [B]
            elif collision_type == pc.case.IIIB:
                if self.anticol.verbose:
                    print("\n\nSolving theta-phi collision!\n")
                changings = [B]
                unchangings = [A]
            elif collision_type == pc.case.GFA:
                print("\n\nSolving GFA\n")
                changings = [A]
                unchangings = [B]
            elif collision_type == pc.case.PTL:
                print("\n\nSolving Petal\n")
                changings = [A]
                unchangings =[None]
                
            for changing, unchanging in zip(changings,unchangings):
                if len(tpfs[changing])< 2:
                    print(tpfs[changing])
                elif len(tpss[unchanging])<2:
                    print(tpss[unchanging])
                if self.collider.spatial_collision_between_positioners(changing, unchanging, \
                        tpfs[changing], tpss[unchanging]) != pc.case.I:
                    if self.anticol.verbose:
                        print("The current situation can't be resolved in this configuration, as the final goal overlaps with the colliding positioners current place")
                    continue
                if changing in neighbor_ofaltered:
                    continue
                # Get the posmodel of the positioner we'll be working with
                # and info about it's neighbors
                changing_posmodel = posmodels[changing]
                neighbor_idxs = self.collider.pos_neighbor_idxs[changing]
                fixed_neighbors = self.collider.fixed_neighbor_cases[changing]

                skip_this_loop = False
                for pos_neighb in neighbor_idxs:
                    if pos_neighb in altered_pos:
                        skip_this_loop = True
                        break
                if skip_this_loop:
                    continue
    
                # Set a boolean if the petal is something we need to avoid
                avoid_petal = (pc.case.PTL in fixed_neighbors)
                
                # if we collided with a positioner. Make sure the positioner is a neighbor
                # otherwise something strange has happened
                if unchanging != None and unchanging not in neighbor_idxs:
                    print("Make sure the neighbor includes the position that it supposedly collided with")
                    neighbor_idxs = np.append(neighbor_idxs,unchanging)
                if changing in neighbor_idxs:
                    print('The positioner claims to have itself as a neighbor?')
                    pdb.set_trace()
                #nidxs = neighbor_idxs
                #for i,idx in enumerate(neighbor_idxs[:-1]):
                #    for j,idx2 in enumerate(neighbor_idxs[i+1:]):
                #        if idx==idx2:
                #            print('Two indices have the same value')
                #            nidxs.pop(i+1+j)
                #neighbor_idxs = np.array(nidxs)
                # define the beginning and ending locations for the positioner we're moving
                # If we are         
                start = [starting_anticol_theta[changing],starting_anticol_phi[changing]]
                target = [goal_anticol_theta[changing],goal_anticol_phi[changing]]

                if self.anticol.verbose:
                    print("Trying to correct indices ",A,B," with ",algorithm," avoidance")
                # If the target is where we start, something weird is up
                if target[0] == start[0] and target[1]==start[1] and self.anticol.verbose:
                    pdb.set_trace() 
                    
                # Create a dictionary called neighbors with all useful information of the neighbors
                neighbors = {}
                neighbors['posmodels'] = np.asarray(posmodels[neighbor_idxs])
                xns = []
                yns = [] 
                neighbors['theta_body_xns'] = np.zeros(len(neighbor_idxs))
                neighbors['theta_body_yns'] = np.zeros(len(neighbor_idxs))
                neighbors['xoffs'] = self.anticol.xoffs[neighbor_idxs]
                neighbors['yoffs'] = self.anticol.yoffs[neighbor_idxs]
                neighbors['idxs'] = neighbor_idxs
                
                neighbors['phins'] = starting_anticol_phi[neighbor_idxs]
                neighbors['thetans'] = starting_anticol_theta[neighbor_idxs]
                neighbors['thetants'] = goal_anticol_theta[neighbor_idxs]
                neighbors['phints'] = goal_anticol_theta[neighbor_idxs]
                
                # Loop through the neighbors and calculate the x,y's for each
                for thit,pit,idxit in zip(neighbors['thetans'],neighbors['phins'],neighbors['idxs']):
                    theta_bods = self.anticol.posoutlines.central_body_outline([thit,pit],[self.anticol.xoffs[idxit],self.anticol.yoffs[idxit]])
                    phi_arms = self.anticol.posoutlines.phi_arm_outline([thit,pit],self.collider.R1[idxit], [self.anticol.xoffs[idxit],self.anticol.yoffs[idxit]])
                    xns.extend(theta_bods[0,:])
                    xns.extend(phi_arms[0,:])
                    yns.extend(theta_bods[1,:])
                    yns.extend(phi_arms[1,:])
    
                # If we have to avoid the petal, do some work to find the x,y location
                # of the petal and place some 'avoidance' objects along it so that
                # our positioner is repulsed by them and thus the petal edge
                if avoid_petal:
                    petalxys = self.anticol.posoutlines.petal_outline(self.anticol.xoffs[changing],self.anticol.yoffs[changing],\
                                            self.anticol.neighborhood_radius)
                    xns.extend(petalxys[0,:])
                    yns.extend(petalxys[1,:])

                xyns = changing_posmodel.trans.obsXY_to_flatXY([xns,yns])
            
                neighbors['xns'] = np.asarray(xyns[0])
                neighbors['yns'] = np.asarray(xyns[1])

                # check for the consistancy of the x and y values. Make sure they don't overlap
                #testxns = np.asarray(xns).reshape((len(xns),1))
                #testyns = np.asarray(yns).reshape((len(yns),1))
                #dxs = testxns-testxns.T
                #dys = testyns-testyns.T
                #dists = np.hypot(dxs,dys)
                #dists[np.diag_indices(dists.shape[0])] = 99
               
                if np.any( np.hypot(neighbors['xns']-self.anticol.xoffs[changing],neighbors['yns']-self.anticol.yoffs[changing] ) < 0.3):
                    print('A neighbor is within 0.3 millimeters of the center of the changing positioner')
                    pdb.set_trace()

                #plt.plot(testxns,testyns,'b.'); plt.show()
                #pdb.set_trace() 
                
                ## tbody_corner_locations has the xy coordinates of tracer points
                ## around the central body of the positioner at ALL theta rotations
                ## all we need to do is offset this by the positioner's offset
                central_body_matrix_locations = self.anticol.central_body_matrix.copy()
                central_body_matrix_locations[:,0,:] += self.anticol.xoffs[changing]
                central_body_matrix_locations[:,1,:] += self.anticol.yoffs[changing]
                phi_arm_matrix_locations = self.anticol.phi_arm_matrix.copy()
                phi_arm_matrix_locations[:,:,0,:] += self.anticol.xoffs[changing]
                phi_arm_matrix_locations[:,:,1,:] += self.anticol.yoffs[changing]

                # Assign the max and min angles for theta and phi, quantized to integers
                postmin,postmax = changing_posmodel.targetable_range_T
                pospmin,pospmax = changing_posmodel.targetable_range_P
                tpmin = changing_posmodel.trans.posTP_to_obsTP([postmin,pospmin])
                tpmax = changing_posmodel.trans.posTP_to_obsTP([postmax,pospmax])
                obs_tmin,obs_tmax = int(tpmin[0]),int(tpmax[0])
                obs_pmin,obs_pmax = int(tpmin[1]),int(tpmax[1])

                # Find the locations where we can actually target with this positioner                
                good_thetas = np.where( ( (self.anticol.thetas >= obs_tmin) & (self.anticol.thetas <= obs_tmax) ) )[0]
                good_phis = np.where( ( (self.anticol.phis >= obs_pmin) & (self.anticol.phis <= obs_pmax) ) )[0]

                # Make bad xy values of the theta body in same grid coordinates
                # thetaxys have shape theta_ind, x/y as 0/1 ind, point_ind
                cut_cent_bod_matrix = central_body_matrix_locations[good_thetas,:,:]
            
                # phixys has shape theta_ind, phi_ind, x/y as 0/1 ind, point_ind
                cut_phi_arm_matrix = phi_arm_matrix_locations[good_thetas,:,:,:]
                cut_phi_arm_matrix = cut_phi_arm_matrix[:,good_phis,:,:]
                
                assert cut_cent_bod_matrix.shape[0] == cut_phi_arm_matrix.shape[0],\
                "The theta dimensions of the xyrot_matrices are not the same for theta and phi"
                #pdb.set_trace()
                for i in range(cut_cent_bod_matrix.shape[0]):
                    cut_cent_bod_matrix[i,:,:] = np.asarray(changing_posmodel.trans.obsXY_to_flatXY([cut_cent_bod_matrix[i,0,:],cut_cent_bod_matrix[i,1,:]]))
                    for j in range(cut_phi_arm_matrix.shape[1]):
                        cut_phi_arm_matrix[i,j,:,:] = np.asarray(changing_posmodel.trans.obsXY_to_flatXY([cut_phi_arm_matrix[i,j,0,:],cut_phi_arm_matrix[i,j,1,:]]))

                # With the positioner and neighbors setup, resolve the specific scenario and
                # return dt,dp,pausetime  lists that I can convert into a new movetable
                #pdb.set_trace()
                if algorithm == 'astar':
                    if self.anticol.multitest:
                        heuristics = ['euclidean','theta','phi','manhattan']
                        weights = [1,1.2,1.4,1.6,1.8,2]
                    else:
                        heuristics = []
                        weights = []    

                    dts,dps,times, test_outputs = bidirectional_astar_pathfinding(\
                                                     changing_posmodel,start,\
                                                     target, neighbors, \
                                                     cut_cent_bod_matrix, \
                                                     cut_phi_arm_matrix, \
                                                     self.anticol,heuristics,weights
                                                     )
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
                    dts,dps,times = self._em_resolution(changing_posmodel,start,target,neighbors,step)
    
                # If length 0, don't create.
                if dts is None:
                    if self.anticol.verbose:
                        print("Number of rows in the new version of the table is: %d" % 0)
                    continue
    
                # Convert steps into a new movetable
                new_changing_table = posmovetable.PosMoveTable(changing_posmodel)
                new_unchange_table = posmovetable.PosMoveTable(posmodels[unchanging])
                old_changing_table = tables[changing]
                old_unchange_table = tables[unchanging]
                #new_table.set_move(0, pc.T, 0)
                #new_table.set_move(0, pc.P, 0)
                #new_table.set_prepause(0, maxtimes)
                #new_table.set_postpause(0,0)               
                #new_unchange_table.set_move(0,pc.T,0)
                #new_unchange_table.set_prepause(0, maxtimes)
                #new_unchange_table.extend(old_unchange_table)
                new_unchange_table.rows = old_unchange_table.rows.copy()
                new_unchange_table.set_prepause(0,new_unchange_table.rows[0].data['prepause']+maxtimes)
                # if length 1, create with one step.
                # else length > 1, add all steps
                if np.isscalar(dts):
                    if self.anticol.verbose:
                        print("Number of rows in the new version of the table is: %d" % 1)       
                    new_changing_table.set_move(0, pc.T, dts)
                    new_changing_table.set_move(0, pc.P, dps)
                    new_changing_table.set_prepause(0, 0)
                    new_changing_table.set_postpause(0,times)
                else:
                    if self.anticol.verbose:
                        print("Number of rows in the new version of the table is: %d" % dts.size)
                    itter = 0
                    for dt, dp, time in zip(dts,dps,times):
                        new_changing_table.set_move(itter, pc.T, dt)
                        new_changing_table.set_move(itter, pc.P, dp)
                        new_changing_table.set_postpause(itter,time)
                        new_changing_table.set_prepause(itter, 0.0)
                        itter += 1
                new_changing_table.set_prepause(0, maxtimes)        
                # Replace the old table with the newly created one
                newmovetime = new_changing_table.for_schedule['move_time'][dts.size-1]
                tables[changing] = new_changing_table
                tables[unchanging] = new_unchange_table
                
                indices, coltype = self._check_single_positioner_for_collisions(tpss,tables,changing)
                if coltype == pc.case.I:
                    stallmovetimes.append(newmovetime)
                    altered_pos.append(changing)
                    neighbor_ofaltered.union(set(neighbor_idxs))
                    if self.anticol.verbose:
                        print("Successfully found a schedule that avoids the collision!")
                    break
                else:
                    tables[changing] = old_changing_table
                    tables[unchanging] = old_unchange_table
            # end of for loop over moveable colliding positioners
        # end of while loop over all collisions
            
        # Correct timing so everything is in sync again
        maxstalltime = np.max(stallmovetimes)
        movetimes = np.zeros(len(tables))
        # Update the movetimes for every positioner for this step
        for i,table in enumerate(tables):
            if i in altered_pos:
                tempmovetime = stallmovetimes[altered_pos==i]
                try:
                    table.set_postpause(len(table.rows)-1, maxstalltime-tempmovetime)
                except:
                    pdb.set_trace()
            else:
                table.set_postpause(len(table.rows)-1, maxstalltime-table.for_schedule['move_time'][-1])
            movetimes[i] = table.for_schedule['move_time'][-1]
        # Just double check for good measure
        # Find the new max time for this step, and update the pospauses
        maxtime = np.max(movetimes)
        #for table,movetime in zip(tables,movetimes): 
        #    if movetime<maxtime:
        #        table.set_postpause(len(table.rows)-1,maxtime-movetime)
        if self.anticol.verbose:
            print("Max times to start are: ",maxtime)
                # After all collision avoidances attempted. Return the new list of movetables
        import time
        with open('../outputs/run_results__{0}.csv'.format(str(time.time()).split('.')[0]),'w') as runresultsfile:
            keys = np.sort(list(run_results.keys()))
            line = ''
            for key in keys:
                line += key+','
            runresultsfile.write(line[:-1]+'\n')
            for itt in range(len(run_results['heuristic'])):
                line = ''
                for key in keys:
                    line += str(run_results[key][itt])+','
                runresultsfile.write(line[:-1]+'\n')    
        return tables, altered_pos
        
 
       
    def _em_resolution(self,posmodel,start,target,neighbors=None,dp_direction = 0):
        '''
            Avoids the neightbors for the currenct posmodel and gets the positioner from the 
            start t,p to the target t,p without hitting the neighbors using a 'force law' repulsion/attraction
            type of avoidance.
        '''
        # Define a few constants
        nsteps = 10000
        
        # Intialize values
        theta,phi = start[pc.T],start[pc.P]    
        dTs,dPs = [],[]

        # Find the xy of the starting position and get the theta and phi ranges
        # we are allowed to move to
        xstart,ystart = posmodel.trans.obsTP_to_flatXY(start)
        postmin,postmax = posmodel.targetable_range_T
        pospmin,pospmax = posmodel.targetable_range_P
        tmin,pmin = posmodel.trans.posTP_to_obsTP([postmin,pospmin])
        tmax,pmax = posmodel.trans.posTP_to_obsTP([postmax,pospmax])
        phi_safe = posmodel.trans.posTP_to_obsTP([theta,self.anticol.phisafe])[1]

        ## Create huge list of neighboring positioner locations
        # Figure out if we're extending or retracting, and move the theta/phis of neighbors
        # If rotation, the neighbors aren't moving. Say so and continue.
        print("I'm making neighbors static until we move the problematic positioners.")
        xns = np.concatenate((neighbors['xns'],neighbors['theta_body_xns']))
        yns = np.concatenate((neighbors['yns'],neighbors['theta_body_yns']))
        # Move without waiting unless specific criteria in the loop are met
        for i in range(nsteps):       
            # Calculate the potential surrounding the current point and 
            # return the direction that minimizes the potential
            theta_new,phi_new = self._take_step(posmodel,[theta,phi],target,xns,\
                                                yns,tmin,tmax,pmin,pmax,phi_safe)
            # Save the change in theta and phi and redefine things for the next loop
            dTs.append(theta_new-theta)
            dPs.append(phi_new-phi)
            theta,phi = theta_new,phi_new
            # If we are within tolerance of the final target
            if ( (np.abs(phi - target[pc.P]) < self.anticol.ang_threshold) and \
                 (np.abs(theta - target[pc.T]) < self.anticol.ang_threshold) ):
                xo,yo = posmodel.trans.obsTP_to_flatXY([target[pc.T],target[pc.P]])
                rhons = np.hypot(xns-xo,yns-yo)
                # If all of the collideable objects are far enough away, we're done
                # Move to the final location and exit
                if np.all(rhons>self.anticol.rtol):
                    dTs.append(target[pc.T]-theta)
                    dPs.append(target[pc.P]-phi)
                    theta,phi = target[pc.T],target[pc.P]
                    if self.anticol.verbose:
                        print("Final Loop reached!   Theta =  %f   and phi = %f    nitters = %d" %(theta,phi,i+1))
                    # If desired we can plot the movement and the potential field seen
                    # by the positioner
                    if self.anticol.plotting:
                        self._plot_potential(posmodel,target,neighbors)
                        plt.title("Start ts=%d ps=%d tf=%d pf=%d" %    (start[pc.T],start[pc.P],target[pc.T],target[pc.P]))
                        xls,yls = posmodel.trans.obsTP_to_flatXY([start[pc.T]+np.cumsum(dTs),start[pc.P]+np.cumsum(dPs)])
                        plt.plot(xls,yls,'g.',markersize=8)
                        plt.plot(xstart,ystart,'k^',markersize=10)
                        plt.show()
                        plt.close()
                    return self._condense(np.asarray(dTs),np.asarray(dPs))
                # If neighbors won't move out of the way, give up as we can't get there
                else:
                    break
                
                    
        # If loop is completed or broken and no solution found,
        # we can plot the movements performed and the potential the positioner saw
        if self.anticol.plotting:
            self._plot_potential(posmodel,target,neighbors)
            plt.title("Start ts=%d ps=%d tf=%d pf=%d" % (start[pc.T],start[pc.P],target[pc.T],target[pc.P]))
            xls,yls = posmodel.trans.obsTP_to_flatXY([start[pc.T]+np.cumsum(dTs),start[pc.P]+np.cumsum(dPs)])
            plt.plot(xls,yls,'g.',markersize=8)        
            plt.plot(xstart,ystart,'k^',markersize=10)
            plt.show()
            plt.close()
            
        # If the loop didn't converge or we broke, return None's since we didn't have success
        return None,None,None
    
    
    
    
    def _take_step(self,posmodel,current,target,xns,yns,tmin,tmax,pmin,pmax,phi_safe):
        '''
        A single step within the em_resolution function. This attempts to move a distance
        self.angstep in both the positive and negative theta and phi directions
        and calculates the potential at all 9 possibilities (no movement is an option)
        It selects the option that minimizes the potential and returns the final location
        of that minimizing movement in local theta,phi 
        '''
        # Get the xy location of the target
        xa,ya = posmodel.trans.obsTP_to_flatXY(target)
        
        # Define the current and desired locations, and the angular steps to use
        theta, phi = current[pc.T],current[pc.P]
        thetaa,phia = target[pc.T],target[pc.P]
        angstep = self.anticol.angstep#1. #0.01
        stepper_array = np.array([-1,0,1])*angstep

        # If within safety envelope, proceed directly to desired location
        if phi > phi_safe and phia > phi_safe:
            return thetaa,phia
    
        # Initialize the next phi value to old value
        phi_next = phi
        theta_next = theta
        
        # Loop through possible steps and calculate the potential at each.
        # If the angle is outside acceptable limits, we move on to the next without
        # calculating the potential
        psteps = np.clip(phi + stepper_array, pmin, pmax)
        tsteps = np.clip(theta + stepper_array, tmin, tmax)
        ts,ps = np.meshgrid(tsteps,psteps)
        ts = ts.ravel()
        ps = ps.ravel()
        # Calculate the term in the potential for the motor location
        xos,yos = posmodel.trans.obsTP_to_flatXY([ts.tolist(),ps.tolist()])

        # Calculate the derivative of the potentials
        Vs = self._findpotential(np.asarray(xos),np.asarray(yos),xa,ya,xns,yns)

        #if V < V_prev:
        if len(Vs)>0:
            min_ind = np.argmin(Vs)
            phi_next = ps[min_ind]
            theta_next = ts[min_ind]

            
        # If the best move is to do nothing, random walk by 2*stepsize
        # so long as the random walk is within allowable angle constraints
        if phi_next == phi and theta_next == theta:
            if theta >= (tmin + 5):
                if theta <= (tmax - 5):
                    theta_next += np.random.randint(-1,2)*2*angstep
                else:
                    theta_next += np.random.randint(-1,1)*2*angstep   
            else:
                theta_next += np.random.randint(0,2)*2*angstep
            if phi >= (pmin+5):
                if phi <= (pmin-5):
                    phi_next += np.random.randint(-1,2)*2*angstep
                else:
                    phi_next += np.random.randint(-1,1)*2*angstep
            else:
                phi_next += np.random.randint(0,2)*2*angstep           
                
        return theta_next,phi_next
        


    def _findpotential(self,xos,yos,xa,ya,xns,yns):
        '''
            Calculates the distances from the positioner to all 
            the relevant locations and then returns the potential
            that the positioner 'feels' given all those distances.
        '''
        # Calculate the term in the potential for the motor location
        rhocs = np.hypot(xos,yos)
        # Calculate the potential pieces for the neighbors
        xosT = xos.reshape((1,xos.size))
        yosT = yos.reshape((1,yos.size))
        xns = xns.reshape((xns.size),1)
        yns = yns.reshape((yns.size),1)
        rhonss = np.hypot(xns-xosT,yns-yosT)    
        # Calculate the potential pieces for the target
        rhoas = np.hypot(xa-xos,ya-yos)
        # Calculate the derivative of the potentials
        Vs = self._potential(rhocs,rhonss,rhoas)  
        return Vs       
      
      
      
    def _avoid_collisions_zerothorder(self,tables,posmodels,collision_indices):
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
                posmodels   list or array of all posmodels
                collision_indices   list or array containing all of the array indices
                                    for tables and posmodels that you wish to prevent from 
                                    moving
                                    
            Output:
                tables    list or array of all movetables, where the tables at indices specified 
                            by collision_indices have been prevented from moving.
        '''
        # Get a unique list of all indices causing problems
        unique_indices = self._unique_inds(collision_indices)
        # Remove "None" cases corresponding to fixed collisions
        if None in unique_indices.keys():
            unique_indices.pop(None)

        # Find out how long the longest move takes to execute
        movetimes = np.asarray([table.for_schedule['move_time'][-1] for table in tables])
        if self.anticol.verbose:
            try:
                print("std of movetimes was: ",np.std(movetimes))
            except:
                pass
        max_time = np.max(movetimes)
                    
        # For the colliding indices, simply don't move them
        for index in unique_indices.keys():
            table = posmovetable.PosMoveTable(posmodels[index])
            table.set_move(0, pc.T, 0.)
            table.set_move(0, pc.P, 0.)
            table.set_prepause (0, max_time)
            table.set_postpause(0, 0.0)
            tables[index] = table
        #pdb.set_trace()
        return tables,collision_indices.tolist()
        
        
        
    
    
    def _check_for_collisions(self,tps,list_tables):
        '''
            Find what positioners collide, and who they collide with
            Inputs:
                tps:  list or numpy array of theta,phi pairs that specify the location
                        of every positioner
                cur_poscollider:  poscollider object used to find the actual collisions
                list_tables:   list of all the movetables
                
            Outputs:
               All 3 are numpy arrays giving information about every collision that occurs.
                collision_indices: list index which identifies the positioners that collide
                                    this has 2 indices in a pair [*,*] if 2 positioners collided
                                    or [*,None] if colliding with a wall of fiducial.
                collision_types:   Type of collision as specified in the pc class
        '''
        posmodel_index_iterable = range(len(self.collider.posmodels))
        sweeps = [[] for i in posmodel_index_iterable]
        collision_index = [[] for i in posmodel_index_iterable]
        collision_type = [pc.case.I for i in posmodel_index_iterable]
        earliest_collision = [np.inf for i in posmodel_index_iterable]
        nontriv = 0
        colrelations = self.collider.collidable_relations
        for A, B, B_is_fixed in zip(colrelations['A'],colrelations['B'],colrelations['B_is_fixed']):
            tableA = list_tables[A].for_schedule
            obsTPA = tps[A]
            if B_is_fixed and A in range(len(list_tables)): # might want to replace 2nd test here with one where we look in tables for a specific positioner index
                these_sweeps = self.collider.spacetime_collision_with_fixed(A, obsTPA, tableA)
            elif A in range(len(list_tables)) and B in range(len(list_tables)): # again, might want to look for specific indexes identifying which tables go with which positioners
                tableB = list_tables[B].for_schedule
                obsTPB = tps[B]    
                these_sweeps = self.collider.spacetime_collision_between_positioners(A, obsTPA, tableA, B, obsTPB, tableB)
    
            if these_sweeps[0].collision_time <= earliest_collision[A]:
                nontriv += 1
                sweeps[A] = these_sweeps[0]
                earliest_collision[A] = these_sweeps[0].collision_time
                if B_is_fixed:
                    collision_index[A] = [A,None]
                else:
                    collision_index[A] = [A,B]
                collision_type[A] = these_sweeps[0].collision_case
                if these_sweeps[0].collision_time < np.inf:
                    earliest_collision[A] = these_sweeps[0].collision_time
            for i in range(1,len(these_sweeps)):
                if these_sweeps[i].collision_time < earliest_collision[B]:
                    nontriv += 1
                    sweeps[B] = these_sweeps[i]
                    earliest_collision[B] = these_sweeps[i].collision_time
                    if B_is_fixed:
                        collision_index[B] = [A,None]
                    else:
                        collision_index[B] = [A,B]
                    collision_type[B] = these_sweeps[i].collision_case

        collision_indices = np.asarray(collision_index)
        collision_types = np.asarray(collision_type)
        collision_indices = collision_indices[collision_types != pc.case.I]
        collision_types = collision_types[collision_types != pc.case.I]
        
        collision_mask = np.ones(len(collision_indices)).astype(bool)
        for i in range(len(collision_indices)):
            for j in np.arange(i+1,len(collision_indices)):
                if collision_mask[i]:
                    if np.all(collision_indices[i] == collision_indices[j]):
                        collision_mask[j]=False
                    elif np.all(collision_indices[i] == list(reversed(collision_indices[j]))):
                        collision_mask[j]=False
    
        collision_indices = collision_indices[collision_mask]
        collision_types = collision_types[collision_mask]
        
        # return the earliest collision time and collision indices
        return collision_indices, collision_types
    

    def _check_single_positioner_for_collisions(self,tps,list_tables,index):
        '''
            Find what positioners collide, and who they collide with
            Inputs:
                tps:  list or numpy array of theta,phi pairs that specify the location
                        of every positioner
                cur_poscollider:  poscollider object used to find the actual collisions
                list_tables:   list of all the movetables
                
            Outputs:
               All 3 are numpy arrays giving information about every collision that occurs.
                collision_indices: list index which identifies the positioners that collide
                                    this has 2 indices in a pair [*,*] if 2 positioners collided
                                    or [*,None] if colliding with a wall of fiducial.
                collision_types:   Type of collision as specified in the pc class
        '''
        collision_index,collision_type,earliest_collision = [],pc.case.I,np.inf
        nontriv = 0
        colrelations = self.collider.collidable_relations
        colrelA = np.asarray(colrelations['A'])
        colrelB = np.asarray(colrelations['B'])
        colrelBfixd = np.asarray(colrelations['B_is_fixed'])
        iteration_relation = np.where(colrelA==index)[0]
        for A, B, B_is_fixed in zip(colrelA[iteration_relation],colrelB[iteration_relation],\
                                colrelBfixd[iteration_relation]):
            tableA = list_tables[A].for_schedule
            obsTPA = tps[A]
            if B_is_fixed and A in range(len(list_tables)): # might want to replace 2nd test here with one where we look in tables for a specific positioner index
                these_sweeps = self.collider.spacetime_collision_with_fixed(A, obsTPA, tableA)
            elif A in range(len(list_tables)) and B in range(len(list_tables)): # again, might want to look for specific indexes identifying which tables go with which positioners
                tableB = list_tables[B].for_schedule
                obsTPB = tps[B]    
                these_sweeps = self.collider.spacetime_collision_between_positioners(A, obsTPA, tableA, B, obsTPB, tableB)
    
            if these_sweeps[0].collision_time <= earliest_collision:
                nontriv += 1
                earliest_collision = these_sweeps[0].collision_time
                if B_is_fixed:
                    collision_index = [A,None]
                else:
                    collision_index = [A,B]
                collision_type = these_sweeps[0].collision_case
                if these_sweeps[0].collision_time < np.inf:
                    earliest_collision = these_sweeps[0].collision_time
            for i in range(1,len(these_sweeps)):
                if these_sweeps[i].collision_time < earliest_collision:
                    nontriv += 1
                    earliest_collision = these_sweeps[i].collision_time
                    if B_is_fixed:
                        collision_index = [A,None]
                    else:
                        collision_index = [A,B]
                    collision_type = these_sweeps[i].collision_case


        
        # return the earliest collision time and collision indices
        return np.asarray(collision_index), np.asarray(collision_type)
    
        
    
    def _potential(self,rhocs,rhonss,rhoas):
        '''
            Where the 'forces' the positioner feels are defined. The potential
            acts to attract the positioner to the target, and repel it from the neighbors
            and walls.
            It can also give long range attraction to the center of the posioner range
            and short range repulsion to preferentially 
        '''
        # Avoid divide-by-zero errors by setting 0 valued distances to a very small number
        np.clip(rhocs,1e-12,np.inf,out=rhocs)
        np.clip(rhonss,1e-12,np.inf,out=rhonss)
        np.clip(rhoas,1e-12,np.inf,out=rhoas)  

        # Return the potential given the distances and the class-defined coefficients
        return ( (self.anticol.coeffn*np.sum((1./(rhonss*rhonss)),axis=0)) - (self.anticol.coeffa/(rhoas**0.5))) 
                 # (self.anticol.coeffcr/(rhoc**4)) +  - (self.anticol.coeffca/(rhoc**0.25))  #7,3 
        
    def _combine_tables(self,tabledicts):
        # For each positioner, merge the three steps (r,r,e) into a single move table
        output_tables = []
        for tablenum in range(len(tabledicts['retract'])):
            # start with copy of the retract step table
            newtab = posmovetable.PosMoveTable(tabledicts['retract'][tablenum].posmodel)
            newtab.rows = tabledicts['retract'][tablenum].rows.copy()
            #newtab = copymodule.deepcopy(tabledicts['retract'][tablenum])
            # append the rotate and extend moves onto the end of the retract table
            for step in ['rotate','extend']:
                newtab.extend(tabledicts[step][tablenum])
            output_tables.append(newtab)
        return output_tables
        
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
        # Intialize the arrays that will be output
        output_t = [dts[0]]
        output_p = [dps[0]]
        output_times = [0.]
        current_column = 0
        # Loop through the given array of dthetas,dphis
        for i in range(1,dts.size):
            # If the change in theta and phi is the same as before,
            # We don't need a new step, just increase the time we perform
            # the previous step
            if dts[i]==dts[i-1] and dps[i]==dps[i-1]:
                output_t[current_column] += dts[i]
                output_p[current_column] += dps[i]
            # If we're not moving, we don't make a new move, we only add waittime
            # after the current move
            elif dts[i]==0 and dps[i]==0:
                output_times[current_column] += self.anticol.dt
            # if none of the cases above, add a new move in the movetable
            # for the given dtheta, dphi, with no waittime 
            else:
                output_t.append(dts[i])
                output_p.append(dps[i])
                output_times.append(0.)
                current_column += 1
        return np.asarray(output_t),np.asarray(output_p),np.asarray(output_times)

    def _reverse_for_extension(self,tables):
        # For each positioner, merge the three steps (r,r,e) into a single move table
        output_tables = []
        for table in tables:
            # start with copy of the retract step table
            newtab = posmovetable.PosMoveTable(table.posmodel)
            rows = table.rows.copy()
            rows = rows[::-1]
            for i,row in enumerate(rows):
                dt, dp = row.data['dT_ideal'], row.data['dP_ideal'],
                pre, post = row.data['prepause'], row.data['postpause']
                newtab.set_move(i, pc.T, -1*dt)
                newtab.set_move(i, pc.P, -1*dp)
                newtab.set_prepause(i, post)
                newtab.set_postpause(i, pre)    
            output_tables.append(newtab)
        return output_tables        

        
        
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
        
        
    def _printindices(self,statement,step,indices):
        '''
            Helper function that prints information about the unique indices
            involved in collisions
        '''
        unique = self._unique_inds(indices)
        print(statement,step,'   at indices:    ',unique)

        
        
    def _unique_inds(self,indices):
        '''
          Counts the indices in the list and returns a Counter object
          that holds information about the number of times each index appears
        '''         
        return Counter(np.ravel(indices))
        
        
    def _plot_potential(self,posmodel,target,neighbors):
        '''
            Loops through all possible positions of the posmodel
            and calculates the observed potential the positioner
            would see give the target location and neighbors
            
            Inputs:
                posmodel:  the posmodel of the positioner of interest
                target:  [theta,phi]  where you want the positioner to go
                neighbors:   dictionary of lists containing information on the 
                            positioner's neighbor
        '''
        # Define the range of angles we want to look at
        thetas = np.arange(*posmodel.targetable_range_T,1)
        phis = np.arange(*posmodel.targetable_range_P,1)
        thetagrid, phigrid = np.meshgrid(thetas,phis)
        
        # The target x,y coordinates
        xa,ya = posmodel.trans.obsTP_to_flatXY(target)
        # Pull the neighbor x's and y's from the neighbors dictionary
        xns = np.concatenate((neighbors['xns'],neighbors['theta_body_xns']))
        yns = np.concatenate((neighbors['yns'],neighbors['theta_body_yns']))
        
        # For every angle we're interested in, calculate the x,y locations and then
        # the potential at that location
        xs,ys = posmodel.trans.obsTP_to_flatXY([thetagrid.ravel(), phigrid.ravel()])
        xs, ys = np.asarray(xs),np.asarray(ys)
        Vlocs = self._findpotential(xs,ys,xa,ya,xns,yns).reshape(thetagrid.shape)  
        xs = xs.reshape(thetagrid.shape)
        ys = ys.reshape(thetagrid.shape)
        # Find the theta=360 boundary  (relevant because pts on one side are not
        # readily connected to the otherside of the boundary)
        crossover_x = []
        crossover_y = []
        for i in range(0,181,6):
            x_tax, y_tax = posmodel.trans.obsTP_to_flatXY([360,i])
            crossover_x.append(x_tax)
            crossover_y.append(y_tax)

        # plot the potential
        plt.figure()
        plt.title('Potential')
        plt.plot(xa,ya,'b*',markersize=12)
        plt.plot(crossover_x,crossover_y,'w-',linewidth=1)
        Vlocs[Vlocs>1000]=1000
        plt.pcolormesh(xs,ys,np.sign(Vlocs)*np.log(np.abs(Vlocs)))
        plt.colorbar()
        plt.show()
        pdb.set_trace()

        
class Anticol:
    def __init__(self,collider,petal,verbose, thetas=None,phis=None):
        if thetas is None:
            thetas = np.arange(-200,200,1)
        if phis is None:
            phis = np.arange(0,200,1)
            
        self.thetas = thetas
        self.phis = phis
        ##############################
        # User defineable parameters #
        ##############################
        ##** General PARAMS **##
        self.avoidance = 'astar'#avoidance
        self.verbose = verbose
        self.plotting = True           

        # Define the phi position in degrees at which the positioner is safe
        self.phisafe = 144.
        
        # Some convenience definitions regarding the size of positioners
        motor_width = 1.58
        self.rtol = 2*motor_width
        self.max_thetabody = 3.967-motor_width # mm

        ##** EM PARAMS **##
        # Define how close to a target you must before moving to the exact final position
        # **note the "true" tolerance is max(tolerance,angstep)**
        self.tolerance = 2.
        
        # How far in theta or Phi do you move on each iterative step of the avoidance method
        self.angstep = 6#12.
        
        self.neighborhood_radius = 10

        # Determine how close we can actually need to get to the final target before calling it a success
        self.ang_threshold = max(self.tolerance, self.angstep)

        # to get accurate timestep information, we use a dummy posmodel
        self.dt = self.angstep/petal.posmodels[0].axis[0].motor_to_shaft(petal.posmodels[0]._motor_speed_cruise)
           
        # em potential computation coefficients
        self.coeffcr = 0.#10.0  # central repulsive force, currently unused
        self.coeffca = 0.#100.0   # central attractive force, currently unused
        self.coeffn =  6.0  # repuslive force amplitude of neighbors and walls
        self.coeffa = 10.0  # attractive force amplitude of the target location 
        
        ##** aSTAR PARAMS **##
        self.astar_tolerance_xy = 0.4 #3
        self.multitest = False
        self.astar_verbose = False
        self.astar_plotting = True
        self.astar_heuristic = 'euclidean'
        self.astar_weight = 1.2
        
        #############################################
        # Parameters defined by harware or software #
        #############################################
        # Create an outlines class object with spacing comparable to the tolerance
        # of the search 
        self.posoutlines = PosOutlines(collider, spacing=self.astar_tolerance_xy)
        ##Note the approximation here
        r1 = np.mean(collider.R1)         
        self.central_body_matrix = self.posoutlines.central_body_outline_matrix(thetas)
        self.phi_arm_matrix = self.posoutlines.phi_arm_outline_matrix(thetas=thetas,phis=phis,xoff=r1,yoff=0)

        

        
     
        
#from poscollider import PosPoly
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
        actual_petal = np.where((petaly > -1.) & (petaly < 249.))[0]
        true_petal_pts = possible_petal_pts[:,actual_petal]
        self.petalpoints = self._highres(true_petal_pts)
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

    def central_body_outline_matrix(self,thetas):
        #all_theta_points = self.collider.keepout_T.points.copy()
        #theta_corner_locs = np.argsort(all_theta_points[0])[-4:]
        #theta_corner_locs = np.array([2,3,4])
        #theta_pts = all_theta_points[:,theta_corner_locs]
        nthetas = len(thetas)
        theta_pts = np.asarray(self.thetapoints)
        rotation_matrices = self._rotmat2D_deg(thetas)
        #self.anticol.theta_corner_locations = np.asarray([np.dot(rotation_matrices[:,:,i], theta_corners) for i in range(thetas.size)])
        theta_corner_xyarray = np.zeros((nthetas,2,theta_pts.shape[1])) 

        for i in range(nthetas):
            theta_corner_xyarray[i,:,:] = np.dot(rotation_matrices[:,:,i], theta_pts)
         
        return np.asarray(theta_corner_xyarray)

        
    def phi_arm_outline_matrix(self,thetas,phis,xoff=0., yoff=0.):
        #all_phi_points = self.collider.keepout_P.points.copy()
        #phi_corner_locs = np.arange(7)
        #phi_pts = all_phi_points[:,phi_corner_locs]
        phi_pts = np.asarray(self.phipoints)
        phi_theta_offset = phis[0]-thetas[0]
        nphis = len(phis)
        nthetas = len(thetas)
        # Assume mean arm length in order to perform these calculations only once
        t_rotation_matrices = self._rotmat2D_deg(thetas)
        p_rotation_matrices = t_rotation_matrices[:,:,phi_theta_offset:]
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
        

