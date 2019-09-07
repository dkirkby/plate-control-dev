# cython: profile=False
# cython: language_level=3
cimport cython
import numpy as np
import posconstants as pc
import posstate
import posanimator
import configobj
import os
import copy as copymodule
import math
import collision_lookup_generator_subset as lookup
import pickle

class PosCollider(object):
    """PosCollider contains geometry definitions for mechanical components of the
    fiber positioner, GFA camera, and petal. It provides the methods to check for
    collisions between neighboring positioners, and to check for crossing the
    boundaries of the GFA or petal envelope. It maintains a list of all the particular
    positioners in its petal.

    See DESI-0899 for geometry specifications, illustrations, and kinematics.
    """
    def __init__(self, configfile='', 
                 collision_hashpp_exists=False, 
                 collision_hashpf_exists=False, 
                 hole_angle_file=None, 
                 use_neighbor_loc_dict=False,
                 config=None):
        if not config:
            if not configfile:
                filename = '_collision_settings_DEFAULT.conf'
            else:
                filename = configfile
            filepath = os.path.join(pc.dirs['collision_settings'],filename)
            self.config = configobj.ConfigObj(filepath,unrepr=True)
        else:
            self.config = config
        self.posids = set() # posid strings for all the positioners
        self.posindexes = {} # key: posid string, value: index number for positioners in animations
        self.posmodels = {} # key: posid string, value: posmodel instance
        self.devicelocs = {} # key: device loc, value: posid string
        self.pos_neighbors = {} # all the positioners that surround a given positioner. key is a posid, value is a set of neighbor posids
        self.fixed_neighbor_cases = {} # all the fixed neighbors that apply to a given positioner. key is a posid, value is a set of the fixed neighbor cases
        self.R1, self.R2, self.x0, self.y0, self.t0, self.p0 = {}, {}, {}, {}, {}, {}
        self.set_petal_offsets() # default values are used here. one should call this function with actual values after initializing collider
        self.plotting_on = True
        self.timestep = self.config['TIMESTEP']
        self.animator = posanimator.PosAnimator(fignum=0, timestep=self.timestep)
        self.use_neighbor_loc_dict = use_neighbor_loc_dict
        self.keepouts_T = {} # key: posid, value: central body keepout of type PosPoly
        self.keepouts_P = {} # key: posid, value: phi arm keepout of type PosPoly
        
        # hash table initializations (if being used)
        self.collision_hashpp_exists = collision_hashpp_exists
        self.collision_hashpf_exists = collision_hashpf_exists
        if self.collision_hashpp_exists:
            f = open(os.path.join(os.environ.get('collision_table'), 'table_pp_50_5_5_5_5.out'), 'rb')
            self.table_pp = pickle.load(f)
            f.close()
            f = open(os.path.join(os.environ.get('collision_table'), hole_angle_file), 'rb')
            self.hole_angle = pickle.load(f)
            f.close()
            
        if self.collision_hashpf_exists:
            f = open(os.path.join(os.environ.get('collision_table'), 'table_pf_50_50_5_5.out'), 'rb')
            self.table_pf = pickle.load(f)
            f.close()
        
        # load fixed dictionary containing locations of neighbors for each positioner DEVICE_LOC (if this option has been selected)
        if self.use_neighbor_loc_dict:
            with open(pc.dirs['positioner_neighbors_file'], 'rb') as f:
                self.neighbor_locs = pickle.load(f)
            
    def set_petal_offsets(self, x0=0.0, y0=0.0, rot=0.0):
        """Sets information about a particular petal's overall location. This
        information is necessary for handling the fixed collision boundaries of
        petal exterior and GFA.
            x0 and y0 units are mm
            rot units are deg
        """
        self._petal_x0 = x0
        self._petal_y0 = y0
        self._petal_rot = rot
        self._load_keepouts()
		
    def update_positioner_offsets_and_arm_lengths(self):
        """Loads positioner parameters.  This method is called when new calibration data is available
        for positioner arm lengths and offsets.
        """
        self._load_positioner_params()
        self._adjust_keepouts()

    def add_positioners(self, posmodels):
        """Add a collection of positioners to the collider object.
        """
        for posmodel in posmodels:
            posid = posmodel.posid
            if posid not in self.posids:
                self.posids.add(posid)
                self.posindexes[posid] = len(self.posindexes) + 1
                self.posmodels[posid] = posmodel
                self.devicelocs[posmodel.deviceloc] = posid
                self.pos_neighbors[posid] = set()
                self.fixed_neighbor_cases[posid] = set()
        self._load_config_data()
        for p in self.posids:
            self._identify_neighbors(p)

    def add_fixed_to_animator(self, start_time=0):
        """Add unmoving polygon shapes to the animator.
        
            start_time ... seconds, global time when the move begins
        """
        self.animator.add_or_change_item('GFA', '', start_time, self.keepout_GFA.points)
        self.animator.add_or_change_item('PTL', '', start_time, self.keepout_PTL.points)
        for posid in self.posindexes:
            self.animator.add_or_change_item('Eo', self.posindexes[posid], start_time, self.Eo_polys[posid].points)
            # self.animator.add_or_change_item('Ei', self.posindexes[posid], start_time, self.Ei_polys[posid].points)
            # self.animator.add_or_change_item('Ee', self.posindexes[posid], start_time, self.Ee_polys[posid].points)
            self.animator.add_or_change_item('line at 180', self.posindexes[posid], start_time, self.line180_polys[posid].points)
            self.animator.add_label(format(self.posmodels[posid].deviceloc,'03d'), self.x0[posid], self.y0[posid])
        
    def add_mobile_to_animator(self, start_time, sweeps):
        """Add a collection of PosSweeps to the animator, describing positioners'
        real-time motions.

            start_time ... seconds, global time when the move begins        
            sweeps     ... dict with keys = posids, values = PosSweep instances
        """            
        for posid,s in sweeps.items():
            posidx = self.posindexes[posid]
            for i in range(len(s.time)):
                style_override = ''
                collision_has_occurred = s.time[i] >= s.collision_time
                freezing_has_occurred = s.time[i] >= s.frozen_time
                if freezing_has_occurred:
                    style_override = 'frozen'
                if collision_has_occurred:
                    style_override = 'collision'
                time = start_time + s.time[i]
                self.animator.add_or_change_item('central body', posidx, time, self.place_central_body(posid, s.tp[0,i]).points, style_override)
                self.animator.add_or_change_item('phi arm',      posidx, time, self.place_phi_arm(     posid, s.tp[:,i]).points, style_override)
                self.animator.add_or_change_item('ferrule',      posidx, time, self.place_ferrule(     posid, s.tp[:,i]).points, style_override)
                if collision_has_occurred and s.collision_case == pc.case.GFA:
                    self.animator.add_or_change_item('GFA', '', time, self.keepout_GFA.points, style_override)
                elif collision_has_occurred and s.collision_case == pc.case.PTL:
                    self.animator.add_or_change_item('PTL', '', time, self.keepout_PTL.points, style_override)

    def spacetime_collision_between_positioners(self, posid_A, init_obsTP_A, tableA, posid_B, init_obsTP_B, tableB):
        """Wrapper for spacetime_collision method, specifically for checking two positioners
        against each other."""
        return self.spacetime_collision(posid_A, init_obsTP_A, tableA, posid_B, init_obsTP_B, tableB)

    def spacetime_collision_with_fixed(self, posid, init_obsTP, table):
        """Wrapper for spacetime_collision method, specifically for checking one positioner
        against the fixed keepouts.
        """
        return self.spacetime_collision(posid, init_obsTP, table)

    def spacetime_collision(self, posid_A, init_obsTP_A, tableA, posid_B=None, init_obsTP_B=None, tableB=None):
        """Searches for collisions in time and space between two positioners
        which are rotating according to the argued tables.

            posid_A, posid_B            ...  posid strings of the two positioners to check against each other
            init_obsTP_A, init_obsTP_B  ...  starting (theta,phi) positions, in the obsTP coordinate systems
            tableA, tableB              ...  dictionaries defining rotation schedules as described below

        If no arguments are provided for the "B" positioner (i.e. no args for idxB, init_obsTP_B, tableB)
        then the method checks the "A" positioner against the fixed keepout envelopes.

        The input table dictionaries must contain the following fields:

            'nrows'     : number of rows in the lists below (all must be the same length)
            'dT'        : list of theta rotation distances in degrees
            'dP'        : list of phi rotation distances in degrees
            'Tdot'      : list of theta rotation speeds in deg/sec
            'Pdot'      : list of phi rotation speeds in deg/sec
            'prepause'  : list of prepause (before the rotations begin) values in seconds
            'move_time' : list of durations of rotations in seconds, approximately equals max(dT/Tdot,dP/Pdot), but calculated more exactly for the physical hardware
            'postpause' : list of postpause (after the rotations end) values in seconds

        The return is a list of instances of PosSweep. (These contain the theta and phi rotations
        in real time, when if any collision, and the collision type and neighbor.)
        """
        pospos = posid_B is not None # whether this is checking collisions between two positioners (or if false, between one positioner and fixed keepouts)
        if pospos:
            init_obsTPs = [init_obsTP_A,init_obsTP_B]
            tables = [tableA,tableB]
            sweeps = [PosSweep(posid_A),PosSweep(posid_B)]
            steps_remaining = [0,0]
            step = [0,0]
            pos_range = [0,1]
        else:
            init_obsTPs = [init_obsTP_A]
            tables = [tableA]
            sweeps = [PosSweep(posid_A)]
            steps_remaining = [0]
            step = [0]
            pos_range = [0]
        rev_pos_range = pos_range[::-1]
        for i in pos_range:
            sweeps[i].fill_exact(init_obsTPs[i], tables[i])
            sweeps[i].quantize(self.timestep)
            steps_remaining[i] = len(sweeps[i].time)
        while any(steps_remaining):
            check_collision_this_loop = False
            for i in pos_range:
                if any(sweeps[i].tp_dot[:,step[i]]) or step[i] == 0:
                    check_collision_this_loop = True
            if check_collision_this_loop:
                if pospos:
                    collision_case = self.spatial_collision_between_positioners(posid_A, posid_B, sweeps[0].tp[:,step[0]], sweeps[1].tp[:,step[1]])
                else:
                    collision_case = self.spatial_collision_with_fixed(posid_A, sweeps[0].tp[:,step[0]])
                if collision_case != pc.case.I:
                    for i,j in zip(pos_range, rev_pos_range):
                        sweeps[i].collision_case = collision_case
                        if pospos:
                            sweeps[i].collision_neighbor = sweeps[j].posid
                            possible_collision_times = {sweeps[i].time[step[i]]:step[i], sweeps[j].time[step[j]]:step[j]} # key: time value, value: step index
                            sweeps[i].collision_time = max(possible_collision_times)
                            sweeps[i].collision_idx = possible_collision_times[sweeps[i].collision_time]
                        else:
                            sweeps[i].collision_neighbor = 'PTL' if collision_case == pc.case.PTL else 'GFA'
                            sweeps[i].collision_time = sweeps[i].time[step[i]]
                            sweeps[i].collision_idx = step[i]
                        steps_remaining[i] = 0 # halt the sweep here
            steps_remaining = np.clip(np.asarray(steps_remaining)-1,0,np.inf)
            for i in pos_range:
                if steps_remaining[i]:
                    step[i] += 1
                else:
                    pass
        return sweeps

    def spatial_collision_between_positioners(self, posid_A, posid_B, obsTP_A, obsTP_B):
        """Searches for collisions in space between two fiber positioners.

            posid_A, posid_B  ...  posid strings of the two positioners to check against each other
            obsTP_A, obsTP_B  ...  (theta,phi) positions of the axes for the two positioners

        obsTP_A and obsTP_B are in the (obsT,obsP) coordinate system, as defined in
        PosTransforms.

        The return is an enumeration of type "case", indicating what kind of collision
        was first detected, if any.
        """
        if obsTP_A[1] >= self.Eo_phi and obsTP_B[1] >= self.Eo_phi:
            return pc.case.I
        
        if self.collision_hashpp_exists:
            
            dr = self.hole_angle[posid_A][posid_B][0]
            angle = self.hole_angle[posid_A][posid_B][1]
            
            # to make theta angle ranges from 0-360, rather than -180 to 180
            # to be consistent with angle convention used in table
            if obsTP_A[0] < 0: 
                t1 = 360 + obsTP_A[0]
            else:
                t1 = obsTP_A[0]
                
            if obsTP_B[0] < 0: 
                t2 = 360 + obsTP_B[0]
            else:
                t2 = obsTP_B[0]
            
            # binning to the resolution of the lookup table
            dr = lookup.nearest(dr, 50, 0, 950)
            t1 = lookup.nearest(t1, 5, 0, 360)
            t2 = lookup.nearest(t2, 5, 0, 360)
            phi1 = lookup.nearest(obsTP_A[1], 5, -20, 205)
            phi2 = lookup.nearest(obsTP_B[1], 5, -20, 205)
            
            if t1 == 360: t1 = 0
            if t2 == 360: t2 = 0
            code = lookup.make_code_pp(dr, t1-angle, phi1, t2-angle, phi2)
            
            if code in self.table_pp:
                return self.table_pp[code] # <= 0.1 us
            else:
                return pc.case.I
            
        else:
            if obsTP_A[1] < self.Eo_phi and obsTP_B[1] >= self.Ei_phi: # check case IIIA
                if self._case_III_collision(posid_A, posid_B, obsTP_A, obsTP_B[0]):
                    return pc.case.IIIA
                else:
                    return pc.case.I
            elif obsTP_B[1] < self.Eo_phi and obsTP_A[1] >= self.Ei_phi: # check case IIIB
                if self._case_III_collision(posid_B, posid_A, obsTP_B, obsTP_A[0]):
                    return pc.case.IIIB
                else:
                    return pc.case.I
            else: # check cases II and III
                if self._case_III_collision(posid_A, posid_B, obsTP_A, obsTP_B[0]):
                    return pc.case.IIIA
                elif self._case_III_collision(posid_B, posid_A, obsTP_B, obsTP_A[0]):
                    return pc.case.IIIB
                elif self._case_II_collision(posid_A, posid_B, obsTP_A, obsTP_B):
                    return pc.case.II
                else:
                    return pc.case.I

    def spatial_collision_with_fixed(self, posid, obsTP):
        """Searches for collisions in space between a fiber positioner and all
        fixed keepout envelopes.

            posid    ...  positioner to check
            obsTP    ...  (theta,phi) position of the axes of the positioner

        obsTP is in the (obsT,obsP) coordinate system, as defined in
        PosTransforms.

        The return is an enumeration of type "case", indicating what kind of collision
        was first detected, if any.
        """
        if self.fixed_neighbor_cases[posid]:
            if self.collision_hashpf_exists:
                loc_id = self.posmodels[posid].deviceloc
                dx = abs(self.x0[posid] - self.posmodels[posid].expected_current_position['obsX'])
                dy = abs(self.y0[posid] - self.posmodels[posid].expected_current_position['obsY'])
                code = lookup.make_code_pf(loc_id, dx, dy, obsTP[0], obsTP[1])
                if code in self.table_pf:
                    return self.table_pf[code]
                
            else:
                poly1 = self.place_phi_arm(posid,obsTP)
                for fixed_case in self.fixed_neighbor_cases[posid]:
                    poly2 = self.fixed_neighbor_keepouts[fixed_case]
                    if poly1.collides_with(poly2):
                        return fixed_case
                    
        return pc.case.I

    def place_phi_arm(self, posid, obsTP):
        """Rotates and translates the phi arm to position defined by the positioner's
        (x0,y0) and the argued obsTP (theta,phi) angles.
        """
        return self.keepouts_P[posid].place_as_phi_arm(obsTP[0],obsTP[1],self.x0[posid],self.y0[posid],self.R1[posid])

    def place_central_body(self, posid, obsT):
        """Rotates and translates the central body of positioner
        to its (x0,y0) and the argued obsT theta angle.
        """
        return self.keepouts_T[posid].place_as_central_body(obsT,self.x0[posid],self.y0[posid])

    def place_ferrule(self, posid, obsTP):
        """Rotates and translates the ferrule to position defined by the positioner's
        (x0,y0) and the argued obsTP (theta,phi) angles.
        """
        poly = self.ferrule_poly.translated(self.R2[posid], 0)
        poly = poly.rotated(obsTP[1])
        poly = poly.translated(self.R1[posid],0)
        poly = poly.rotated(obsTP[0])
        poly = poly.translated(self.x0[posid], self.y0[posid])
        return poly

    def _case_II_collision(self, posid1, posid2, tp1, tp2):
        """Search for case II collision, positioner 1 arm against positioner 2 arm."""
        poly1 = self.place_phi_arm(posid1, tp1)
        poly2 = self.place_phi_arm(posid2, tp2)
        return poly1.collides_with(poly2)

    def _case_III_collision(self, posid1, posid2, tp1, t2):
        """Search for case III collision, positioner 1 arm against positioner 2 central body."""
        poly1 = self.place_phi_arm(posid1, tp1)
        poly2 = self.place_central_body(posid2, t2)
        return poly1.collides_with(poly2)

    def _load_config_data(self):
        """Reads latest versions of all configuration file offset, range, and
        polygon definitions, and updates stored values accordingly.
        """
        self.timestep = self.config['TIMESTEP']
        self._load_positioner_params()
        self._load_keepouts()
        self._adjust_keepouts()
        self._load_circle_envelopes()

    def _load_positioner_params(self):
        """Read latest versions of all positioner parameters."""
        for posid, posmodel in self.posmodels.items():
            self.R1[posid] = posmodel.state.read('LENGTH_R1')
            self.R2[posid] = posmodel.state.read('LENGTH_R2')
            self.x0[posid] = posmodel.state.read('OFFSET_X')
            self.y0[posid] = posmodel.state.read('OFFSET_Y')
            self.t0[posid] = posmodel.state.read('OFFSET_T')
            self.p0[posid] = posmodel.state.read('OFFSET_P')

    def _load_circle_envelopes(self):
        """Read latest versions of all circular envelopes, including outer clear rotation
        envelope (Eo), inner clear rotation envelope (Ei) and extended-phi clear rotation
        envelope (Ee).
        """
        self.Eo_phi = self.config['PHI_EO']   # angle above which phi is guaranteed to be within envelope Eo
        self.Ei_phi = self.config['PHI_EI']   # angle above which phi is guaranteed to be within envelope Ei
        self.Eo = self.config['ENVELOPE_EO']  # outer clear rotation envelope
        self.Ei = self.config['ENVELOPE_EI']  # inner clear rotation envelope
        self.Ee = self._max_extent() * 2      # extended-phi clear rotation envelope
        self.Eo_poly = PosPoly(self._circle_poly_points(self.Eo, self.config['RESOLUTION_EO']).tolist())
        self.Ei_poly = PosPoly(self._circle_poly_points(self.Ei, self.config['RESOLUTION_EI']).tolist())
        self.Ee_poly = PosPoly(self._circle_poly_points(self.Ee, self.config['RESOLUTION_EE']).tolist())
        self.line180_poly = PosPoly([[0,0],[-self.Eo/2,0]],close_polygon=False)
        self.Eo_polys = {}
        self.Ei_polys = {}
        self.Ee_polys = {}
        self.line180_polys = {}
        for posid in self.posids:
            x = self.x0[posid]
            y = self.y0[posid]
            self.Eo_polys[posid] = self.Eo_poly.translated(x,y)
            self.Ei_polys[posid] = self.Ei_poly.translated(x,y)
            self.Ee_polys[posid] = self.Ee_poly.translated(x,y)
            self.line180_polys[posid] = self.line180_poly.rotated(self.t0[posid]).translated(x,y)
        self.ferrule_diam = self.config['FERRULE_DIAM']
        self.ferrule_poly = PosPoly(self._circle_poly_points(self.ferrule_diam, self.config['FERRULE_RESLN']).tolist())
        
    def _load_keepouts(self):
        """Read latest versions of all keepout geometries."""
        self.general_keepout_P_unexpanded = PosPoly(self.config['KEEPOUT_PHI'])
        self.general_keepout_T_unexpanded = PosPoly(self.config['KEEPOUT_THETA'])
        self.keepout_PTL = PosPoly(self.config['KEEPOUT_PTL'])
        self.keepout_GFA = PosPoly(self.config['KEEPOUT_GFA'])
        self.keepout_PTL = self.keepout_PTL.rotated(self._petal_rot)
        self.keepout_PTL = self.keepout_PTL.translated(self._petal_x0, self._petal_y0)
        self.keepout_GFA = self.keepout_GFA.rotated(self._petal_rot)
        self.keepout_GFA = self.keepout_GFA.translated(self._petal_x0, self._petal_y0)
        self.fixed_neighbor_keepouts = {pc.case.PTL : self.keepout_PTL, pc.case.GFA : self.keepout_GFA}
    
    def _adjust_keepouts(self):
        """Expand/contract, and pre-shift the theta and phi keepouts for each positioner."""
        self.general_keepout_P = self.general_keepout_P_unexpanded.expanded_radially(self.config['KEEPOUT_EXPANSION_PHI_RADIAL'])
        self.general_keepout_P = self.general_keepout_P_unexpanded.expanded_angularly(self.config['KEEPOUT_EXPANSION_PHI_ANGULAR'])
        self.general_keepout_T = self.general_keepout_T_unexpanded.expanded_radially(self.config['KEEPOUT_EXPANSION_THETA_RADIAL'])
        self.general_keepout_T = self.general_keepout_T_unexpanded.expanded_angularly(self.config['KEEPOUT_EXPANSION_THETA_ANGULAR'])
        for posid in self.posids:
            R1_error = self.R1[posid] - pc.nominals['LENGTH_R1']['value']
            R2_error = self.R2[posid] - pc.nominals['LENGTH_R2']['value']
            self.keepouts_P[posid] = self.general_keepout_P.translated(R1_error,0)
            self.keepouts_P[posid] = self.keepouts_P[posid].expanded_x(left_shift=R1_error, right_shift=R2_error)
            self.keepouts_T[posid] = self.general_keepout_T.translated(0,0) # effectively just a copy operation

    def _identify_neighbors(self, posid):
        """Find all neighbors which can possibly collide with a given positioner."""
        Ee = self.Ee_poly.translated(self.x0[posid], self.y0[posid])
        if self.use_neighbor_loc_dict:
            deviceloc = self.posmodels[posid].deviceloc
            neighbors = self.neighbor_locs[deviceloc].intersection(self.devicelocs.keys())
            self.pos_neighbors[posid] = {self.devicelocs[loc] for loc in neighbors}
        else:
            for possible_neighbor in self.posids:
                Ee_neighbor = self.Ee_poly.translated(self.x0[possible_neighbor], self.y0[possible_neighbor])
                if not(posid == possible_neighbor) and Ee.collides_with(Ee_neighbor):
                    self.pos_neighbors[posid].add(possible_neighbor)
        for possible_neighbor in self.fixed_neighbor_keepouts:
            EE_neighbor = self.fixed_neighbor_keepouts[possible_neighbor]
            if Ee.collides_with(EE_neighbor):
                self.fixed_neighbor_cases[posid].add(possible_neighbor)

    def _max_extent(self):
        """Calculation of max radius of keepout for a positioner with fully-extended phi arm."""
        extended_phi = self.general_keepout_P.translated(max(self.R1.values()),0) # assumption here that phi arm polygon defined at 0 deg angle
        return max(np.sqrt(np.sum(np.array(extended_phi.points)**2, axis=0)))

    @staticmethod
    def _circle_poly_points(diameter, npts, outside=True):
        """Constuct a polygon approximating a circle of a given diameter, with a
        given number of points. The polygon's segments are tangent to the circle if
        the optional argument 'outside' is true. If 'outside' is false, then the
        segment points lie on the circle.
        """
        alpha = np.linspace(0, 2 * math.pi, npts + 1)[0:-1]
        if outside:
            half_angle = alpha[0]/2
            points_radius = diameter/2 / math.cos(half_angle)
        else:
            points_radius = diameter/2
        x = points_radius * np.cos(alpha)
        y = points_radius * np.sin(alpha)
        return np.array([x,y])


class PosSweep(object):
    """Contains a real-time description of the sweep of positioner mechanical
    geometries through space.
    """
    def __init__(self, posid=None):
        self.posid     = posid              # unique posid string of the positioner
        self.time      = np.array([])       # time at which each TP position value occurs
        self.tp        = np.array([[],[]])  # theta,phi angles as function of time (sign indicates direction)
        self.tp_dot    = np.array([[],[]])  # theta,phi rotation speeds as function of time (sign indicates direction)
        self.collision_case = pc.case.I     # enumeration of type "case", indicating what kind of collision first detected, if any
        self.collision_time = math.inf      # time at which collision occurs. if no collision, the time is inf
        self.collision_idx = None           # index in time and theta,phi lists at which collision occurs
        self.collision_neighbor = ''        # id string (posid, 'PTL', or 'GFA') of neighbor it collides with, if any
        self.frozen_time = math.inf         # time at which positioner is frozen in place. if no freezing, the time is inf

    def copy(self):
        return copymodule.deepcopy(self)

    def fill_exact(self, init_obsTP, table, start_time=0):
        """Fills in a sweep object based on the input table. Time and position
        are handled continuously and exactly (i.e. not yet quantized).
        """
        time = [start_time]
        tp = [[init_obsTP[0]],[init_obsTP[1]]]
        tp_dot = [[0],[0]]
        for i in range(0,table['nrows']):
            if table['prepause'][i]:
                time.append(table['prepause'][i] + time[-1])
                tp[0].append(tp[0][-1])
                tp[1].append(tp[1][-1])
                tp_dot[0].append(0)
                tp_dot[1].append(0)
            if table['move_time'][i]:
                time.append(table['move_time'][i] + time[-1])
                tp[0].append(table['dT'][i] + tp[0][-1])
                tp[1].append(table['dP'][i] + tp[1][-1])
                tp_dot[0].append(pc.sign(table['dT'][i]) * abs(table['Tdot'][i]))
                tp_dot[1].append(pc.sign(table['dP'][i]) * abs(table['Pdot'][i]))
            if table['postpause'][i]:
                time.append(table['postpause'][i] + time[-1])
                tp[0].append(tp[0][-1])
                tp[1].append(tp[1][-1])
                tp_dot[0].append(0)
                tp_dot[1].append(0)
        self.time = np.array(time)
        self.tp = np.array(tp)
        self.tp_dot = np.array(tp_dot)

    def quantize(self, timestep):
        """Converts itself from exact, continuous time to quantized, discrete time.
        The result has approximate intermediate (theta,phi) positions and speeds,
        all as a function of discrete time. The quantization is according to the
        parameter 'timestep'.
        """
        discrete_time = [self.time[0]]
        discrete_position = np.array([[self.tp[pc.T,0]],[self.tp[pc.P,0]]])
        speed = np.array([[self.tp_dot[pc.T,0]],[self.tp_dot[pc.P,0]]])
        for i in range(1,len(self.time)):
            this_discrete_time = np.arange(discrete_time[-1], self.time[i], timestep) + timestep # additional timestep shifts times such that they correspond to when steps are finished, rather than when they're started
            this_discrete_position = [[],[]]
            this_speed = [[],[]]
            for ax in [pc.T,pc.P]:
                discrete_step = self.tp_dot[ax,i] * timestep
                this_discrete_position[ax] = discrete_position[ax,-1] + np.arange(1,len(this_discrete_time)+1)*discrete_step
                if len(this_discrete_position[ax]>0):
                     this_discrete_position[ax][-1] = self.tp[ax,i] # force the final step to end at the right place (thus slightly changing the effective speed of the final step)
                this_speed[ax] = self.tp_dot[ax,i]*np.ones_like(this_discrete_time) # for book keeping
            discrete_position = np.append(discrete_position, this_discrete_position, axis=1)
            discrete_time = np.append(discrete_time, this_discrete_time)
            speed = np.append(speed, this_speed, axis=1)
        self.time = discrete_time
        self.tp = discrete_position
        self.tp_dot = speed
        
    def extend(self, timestep, max_time):
        """Extends a sweep object to max_time to reflect the postpauses inserted into the move table 
        in equalize_table_times() in posschedulestage.py, ensuring that the sweep object
        is in sync with the move table so that the animator is reflecting true moves. """
        
        starttime_extension = self.time[-1] + timestep
        time_extension = np.arange(starttime_extension, max_time + timestep, timestep)
        extended_time = np.append(self.time, time_extension)
        
        #starttime_extension = self.time[-1] + timestep
        #endtime_extension = self.time[-1] + equalizing_pause
        #time_extension = np.arange(starttime_extension, endtime_extension + timestep, timestep)
        #extended_time = np.append(self.time, time_extension)
        
        # tp extension are just the last tp entry repeated throughout the extended time
        theta_extension = self.tp[0,-1]*np.ones(len(time_extension))
        phi_extension = self.tp[1,-1]*np.ones(len(time_extension))
        extended_theta = list(np.append(self.tp[0], theta_extension))
        extended_phi = list(np.append(self.tp[1], phi_extension))
        extended_tp = np.array([extended_theta, extended_phi])
        
        # tp_dot extension are just zeros repeated throughout the extended time
        tdot_extension = np.zeros(len(time_extension))
        pdot_extension = np.zeros(len(time_extension))
        extended_tdot = list(np.append(self.tp_dot[0], tdot_extension))
        extended_pdot= list(np.append(self.tp_dot[1], pdot_extension))
        extended_tp_dot = np.array([extended_tdot, extended_pdot])
        
        self.time = extended_time
        self.tp = extended_tp
        self.tp_dot = extended_tp_dot

    def register_as_frozen(self):
        """Sets an indicator that the sweep has been frozen at the end."""
        self.frozen_time = self.time[-1]

    @property
    def is_frozen(self):
        """Returns boolean value whether the sweep has a "freezing" event."""
        return self.frozen_time < math.inf
    
    def is_moving(self,step):
        """Returns boolean value whether the sweep is moving at the argued timestep."""
        if self.tp[0,step]*self.tp_dot[0,step] or self.tp[1,step]*self.tp_dot[1,step]:
            return True
        return False
    
    def theta(self, step):
        """Returns theta position of the sweep at the specified timestep index."""
        return self.tp[0,step]
    
    def phi(self, step):
        """Returns phi position of the sweep at the specified timestep index."""
        return self.tp[1,step]

from cpython.mem cimport PyMem_Malloc, PyMem_Free
from libc.math cimport sin as c_sin
from libc.math cimport cos as c_cos
from libc.math cimport pi as c_pi
from libc.math cimport fmax as c_fmax
from libc.math cimport fmin as c_fmin
from libc.math cimport atan2 as c_atan2
cdef double rad_per_deg = c_pi / 180.0
cdef double deg_per_rad = 180.0 / c_pi

cdef class PosPoly:
    """Represents a collidable polygonal envelope definition for a mechanical component
    of the fiber positioner.
    
        points ... normal usage: 2 x N list of x and y coordinates of polygon vertices
               ... expert usage: ignored
               
        close_polygon ... normal usage: whether to make an identical last point matching the first
                      ... expert usage: ignored
        
        allocation ... normal usage: leave False, and it is ignored
                   ... expert usage: positive integer, stating just a size of arrays to allocate.
                                     (overrides both points and close_polygon)
    """
    cdef double* x
    cdef double* y
    cdef unsigned int n_pts
    
    def __cinit__(self, points, close_polygon=True, allocation=False):
        cdef size_t xlen
        cdef size_t ylen
        cdef size_t extra = 0
        cdef size_t xlen_plus
        cdef unsigned int fill_zeros = False
        cdef unsigned int i
        cdef unsigned int allocation_qty = allocation

        if allocation_qty > 0:
                xlen = allocation_qty
                fill_zeros = True
        else:
            xlen = len(points[0])
            ylen = len(points[1])
            if close_polygon:
                extra = 1
            if xlen != ylen:
                print('Error: different lengths x (' + str(xlen) + ') and y (' + str(ylen) + ')')
                return
        xlen_plus = xlen + extra
        self.x = <double*> PyMem_Malloc((xlen_plus) * sizeof(double))
        self.y = <double*> PyMem_Malloc((xlen_plus) * sizeof(double))
        if fill_zeros:
            for i in range(xlen_plus):
                self.x[i] = 0.0
                self.y[i] = 0.0
        else:
            for i in range(xlen):
                self.x[i] = points[0][i]
                self.y[i] = points[1][i]
            if extra:
                self.x[xlen] = self.x[0]
                self.y[xlen] = self.y[0]
        self.n_pts = xlen_plus
        if not self.x or not self.y:
            raise MemoryError()

    def __dealloc__(self):
        PyMem_Free(self.x)
        PyMem_Free(self.y)

    def __repr__(self):
        points = self.points
        output = 'PosPoly ['
        for i in range(len(points)):
            output += '['
            output += ', '.join([format(x,'.3f') for x in points[i]])
            output += '],'
        output = output[:-1]
        output += ']'
        return output

    @property
    def points(self):
        xy = [[],[]]
        for i in range(self.n_pts):
            xy[0].append(self.x[i])
            xy[1].append(self.y[i])
        return xy

    cpdef PosPoly copy(self):
        cdef PosPoly new = PosPoly(points=0, close_polygon=False, allocation=self.n_pts)
        cdef unsigned int i
        for i in range(new.n_pts):
            new.x[i] = self.x[i]
            new.y[i] = self.y[i]
        return new

    cpdef PosPoly rotated(self, angle):
        """Returns a copy of the polygon object, with points rotated by angle (unit degrees)."""
        cdef PosPoly new = self.copy()
        cdef double a = angle
        a *= rad_per_deg
        cdef double c = c_cos(a)
        cdef double s = c_sin(a)
        cdef double this_x
        cdef unsigned int i
        for i in range(new.n_pts):
            this_x = new.x[i]
            new.x[i] = c*this_x + -s*new.y[i]
            new.y[i] = s*this_x +  c*new.y[i]
        return new

    cpdef PosPoly translated(self, dx, dy):
        """Returns a copy of the polygon object, with points translated by distance (dx,dy)."""
        cdef PosPoly new = self.copy()
        cdef unsigned int i
        cdef double delta_x = dx
        cdef double delta_y = dy
        for i in range(new.n_pts):
            new.x[i] += delta_x
            new.y[i] += delta_y
        return new

    cpdef PosPoly expanded_radially(self, dR):
        """Returns a copy of the polygon object, with points expanded radially by distance dR.
        The linear expansion is made along lines from the polygon's [0,0] center.
        A value dR < 0 is allowed, causing contraction of the polygon."""
        cdef PosPoly new = self.copy()
        cdef unsigned int i
        cdef double delta_r = dR
        cdef double angle
        for i in range(new.n_pts):
            angle = c_atan2(new.y[i], new.x[i])
            new.x[i] += delta_r * c_cos(angle)
            new.y[i] += delta_r * c_sin(angle)
        return new
    
    cpdef PosPoly expanded_x(self, left_shift, right_shift):
        """Returns a copy of the polygon object, with points expanded along the x direction only.
        Points leftward of the line x=0 are shifted further left by an amount left_shift > 0.
        Points rightward of the line x=0 are shifted further right by an amount right_shift > 0.
        Points upon the line x=0 are not shifted.
        Negative values for left_dx and right_dx are allowed. They contract the polygon rightward and leftward, respectively."""
        cdef PosPoly new = self.copy()
        cdef unsigned int i
        cdef double L = left_shift
        cdef double R = right_shift
        for i in range(new.n_pts):
            if new.x[i] > 0:
                new.x[i] += R
            elif new.x[i] < 0:
                new.x[i] -= L
        return new
        
    cpdef PosPoly expanded_angularly(self, dA):
        """Returns a copy of the polygon object, with points expanded rotationally by angle dA (in degrees).
        The rotational expansion is made about the polygon's [0,0] center.
        Expansion is made in both the clockwise and counter-clockwise directions from the line y=0. 
        A value dA < 0 is allowed, causing contraction of the polygon."""
        cdef PosPoly new = self.copy()
        cdef unsigned int i
        cdef double delta_angle = dA
        cdef double this_angle
        cdef double radius
        delta_angle *= rad_per_deg
        for i in range(new.n_pts):
            this_angle = c_atan2(new.y[i], new.x[i])
            if this_angle > 0:
                this_angle += delta_angle
            elif this_angle < 0:
                this_angle -= delta_angle
            radius = (new.x[i]**2 + new.y[i]**2)**0.5
            new.x[i] = radius * c_cos(this_angle)
            new.y[i] = radius * c_sin(this_angle)
        return new

    cpdef PosPoly place_as_phi_arm(self, theta, phi, x0, y0, r1):
        """Treating polygon as a phi arm, rotates and translates it to position defined
        by angles theta and phi (deg) and calibration values x0, y0, r1.
        """
        cdef PosPoly new = self.rotated(theta + phi) # units deg
        cdef double X0 = x0
        cdef double Y0 = y0
        cdef double R1 = r1
        cdef double T = theta
        cdef unsigned int i
        T *= rad_per_deg
        cdef double delta_x = X0 + R1 * c_cos(T) # now radians
        cdef double delta_y = Y0 + R1 * c_sin(T)
        for i in range(new.n_pts):
            new.x[i] += delta_x
            new.y[i] += delta_y
        return new

    cpdef PosPoly place_as_central_body(self, theta, x0, y0):
        """Treating polygon as a central body, rotates and translates it to postion
        defined by angle theta (deg) and calibration values x0, y0.
        """
        cdef PosPoly new = self.rotated(theta)
        cdef double delta_x = x0
        cdef double delta_y = y0
        cdef unsigned int i
        for i in range(new.n_pts):
            new.x[i] += delta_x
            new.y[i] += delta_y
        return new

    cpdef unsigned int collides_with(self, PosPoly other):
        """Searches for collisions in space between this polygon and
        another PosPoly object. Returns a bool, where true indicates a
        collision.
        """
        if _bounding_boxes_collide(self.x, self.y, self.n_pts, other.x, other.y, other.n_pts):
            return _polygons_collide(self.x, self.y, self.n_pts, other.x, other.y, other.n_pts)
        else:
            return False

cdef unsigned int _bounding_boxes_collide(double x1[], double y1[], unsigned int len1, double x2[], double y2[], unsigned int len2):
    """Check whether the rectangular bounding boxes of two polygons collide.
        
       x1,y1 ... 1xN c-arrays of the 1st polygon's vertices
       len1  ... length of x1 and y1
       x2,y2,len ... similarly for polygon 2
    
    Returns True if the bounding boxes collide, False if they do not. Intended as
    a fast check, to enhance speed of other collision detection functions.
    """
    if   _c_max(x1,len1) < _c_min(x2,len2):
        return False
    elif _c_max(y1,len1) < _c_min(y2,len2):
        return False
    elif _c_max(x2,len2) < _c_min(x1,len1):
        return False
    elif _c_max(y2,len2) < _c_min(y1,len1):
        return False
    else:
        return True

cdef unsigned int _polygons_collide(double x1[], double y1[], unsigned int len1, double x2[], double y2[], unsigned int len2):
    """Check whether two closed polygons collide.
    
       x1,y1 ... 1xN c-arrays of the 1st polygon's vertices
       len1  ... length of x1 and y1
       x2,y2,len ... similarly for polygon 2

    Returns True if the polygons intersect, False if they do not.
    
    The algorithm is by detecting intersection of line segments, therefore the case of
    a small polygon completely enclosed by a larger polygon will return False. Not checking
    for this condition admittedly breaks some conceptual logic, but this case is not
    anticipated to occur given the DESI petal geometry, and speed is at a premium.
    """
    cdef double[2] A1,A2,B1,B2
    cdef unsigned int i,j
    for i in range(len1 - 1):
        A1 = [x1[i],   y1[i]]
        A2 = [x1[i+1], y1[i+1]]
        for j in range(len2 - 1):
            B1 = [x2[j],   y2[j]]
            B2 = [x2[j+1], y2[j+1]]
            if _segments_intersect(A1,A2,B1,B2):
                return True
    return False

@cython.cdivision(True)
cdef unsigned int _segments_intersect(double A1[2], double A2[2], double B1[2], double B2[2]):
    """Checks whether two 2d line segments intersect. The endpoints for segments
    A and B are each a pair of (x,y) coordinates.
    """
    dx_A = A2[0] - A1[0]
    dy_A = A2[1] - A1[1]
    dx_B = B2[0] - B1[0]
    dy_B = B2[1] - B1[1]
    delta = dx_B * dy_A - dy_B * dx_A
    if delta == 0.0:
        return False  # parallel segments
    s = (dx_A * (B1[1] - A1[1]) + dy_A * (A1[0] - B1[0])) / delta
    t = (dx_B * (A1[1] - B1[1]) + dy_B * (B1[0] - A1[0])) / (-delta)
    return (0 <= s <= 1) and (0 <= t <= 1)
    
cdef double _c_max(double x[], unsigned int length):
    """Get the max of a c-array of doubles."""
    cdef unsigned int i
    cdef double max_val
    if length >= 1:
        max_val = x[0]
        for i in range(1,length):
            max_val = c_fmax(x[i],max_val)
        return max_val
    else:
        return 0.0
    
cdef double _c_min(double x[], unsigned int length):
    """Get the min of a c-array of doubles."""
    cdef unsigned int i
    cdef double min_val
    if length >= 1:
        min_val = x[0]
        for i in range(1,length):
            min_val = c_fmin(x[i],min_val)
        return min_val
    else:
        return 0.0

cpdef test():
    polys = []
    polys += [PosPoly([[0,1,1],[0,0,1]])]
    polys += [polys[0].translated(0.5,0)]
    polys += [polys[0].translated(10,0)]
    polys += [polys[1].rotated(30)]
    polys += [PosPoly([[0,1,2,3,4,5,6,7,8,9],[10,11,12,13,14,15,16,17,18,19]])]
    polys += [polys[4].rotated(45)]
    polys += [PosPoly([[20,10,43.2,-74],[1,2,3,4]])]
    bools = []
    bools += [polys[0].collides_with(polys[0])]
    bools += [polys[0].collides_with(polys[1])]
    bools += [polys[0].collides_with(polys[2])]
    bools += [polys[0].collides_with(polys[3])]
    bools += [polys[0].collides_with(polys[4])]
    bools += [polys[4].collides_with(polys[5])]
    bools += [polys[6].collides_with(polys[0])]
    t = 20
    p = -100
    x = 10
    y = -4
    r1 = 3
    a = polys[0].rotated(p)
    a = a.translated(r1,0)
    a = a.rotated(t)
    a = a.translated(x,y)
    b = polys[0].place_as_phi_arm(t,p,x,y,r1)
    return polys,bools, a, b