import numpy as np
import posconstants as pc
import posanimator
import configobj
import os
import copy as copymodule
import math
from numba import jit

class PosCollider(object):
    """PosCollider contains geometry definitions for mechanical components of the
    fiber positioner, GFA camera, and petal. It provides the methods to check for
    collisions between neighboring positioners, and to check for crossing the
    boundaries of the GFA or petal envelope. It maintains a list of all the particular
    positioners in its petal.

    See DESI-0899 for geometry specifications, illustrations, and kinematics.
    """
    def __init__(self, configfile=''):
        if not configfile:
            defaultconfigfile = '_collision_settings_DEFAULT.conf'
            filename = os.path.join(pc.dirs['collision_settings'],defaultconfigfile)
        else:
            filename = os.path.join(pc.dirs['collision_settings'],configfile)
        self.config = configobj.ConfigObj(filename,unrepr=True)
        self.posids = set() # posid strings for all the positioners
        self.posindexes = {} # key: posid string, value: index number for positioners in animations
        self.posmodels = {} # key: posid string, value: posmodel instance
        self.pos_neighbors = {} # all the positioners that surround a given positioner. key is a posid, value is a set of neighbor posids
        self.fixed_neighbor_cases = {} # all the fixed neighbors that apply to a given positioner. key is a posid, value is a set of the fixed neighbor cases
        self.R1, self.R2, self.x0, self.y0, self.t0, self.p0 = {}, {}, {}, {}, {}, {}
        self.plotting_on = True
        self.timestep = self.config['TIMESTEP']
        self.animator = posanimator.PosAnimator(fignum=0, timestep=self.timestep)

    def add_positioners(self, posmodels):
        """Add a collection of positioners to the collider object.
        """
        for posmodel in posmodels:
            posid = posmodel.posid
            if posid not in self.posids:
                self.posids.add(posid)
                self.posindexes[posid] = len(self.posindexes) + 1
                self.posmodels[posid] = posmodel
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
            self.animator.add_or_change_item('Ei', self.posindexes[posid], start_time, self.Ei_polys[posid].points)
            self.animator.add_or_change_item('Ee', self.posindexes[posid], start_time, self.Ee_polys[posid].points)
            self.animator.add_or_change_item('line at 180', self.posindexes[posid], start_time, self.line180_polys[posid].points)
        
    def add_mobile_to_animator(self, start_time, sweeps):
        """Add a collection of PosSweeps to the animator, describing positioners'
        real-time motions.

            start_time ... seconds, global time when the move begins        
            sweeps     ... dict with keys = posids, values = PosSweep instances
        """            
        for posid,s in sweeps:
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
        else:
            init_obsTPs = [init_obsTP_A]
            tables = [tableA]
            sweeps = [PosSweep(posid_A)]
            steps_remaining = [0]
            step = [0]
        for i in range(len(tables)):
            sweeps[i].fill_exact(init_obsTPs[i], tables[i])
            sweeps[i].quantize(self.timestep)
            steps_remaining[i] = len(sweeps[i].time)
        while any(steps_remaining):
            check_collision_this_loop = False
            for i in range(len(sweeps)):
                if any(sweeps[i].tp_dot[:,step[i]]) or step[i] == 0:
                    check_collision_this_loop = True
            if check_collision_this_loop:
                if pospos:
                    collision_case = self.spatial_collision_between_positioners(posid_A, posid_B, sweeps[0].tp[:,step[0]], sweeps[1].tp[:,step[1]])
                else:
                    collision_case = self.spatial_collision_with_fixed(posid_A, sweeps[0].tp[:,step[0]])
                if collision_case != pc.case.I:
                    for i,j in zip(range(len(sweeps)), reversed(range(len(sweeps)))):
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
            for i in range(len(sweeps)):
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
        elif obsTP_A[1] < self.Eo_phi and obsTP_B[1] >= self.Ei_phi: # check case IIIA
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
        poly = self.keepout_P.rotated(obsTP[1])
        poly = poly.translated(self.R1[posid], 0)
        poly = poly.rotated(obsTP[0])
        poly = poly.translated(self.x0[posid], self.y0[posid])
        return poly

    def place_central_body(self, posid, obsT):
        """Rotates and translates the central body of positioner
        to its (x0,y0) and the argued obsT theta angle.
        """
        poly = self.keepout_T.rotated(obsT)
        poly = poly.translated(self.x0[posid], self.y0[posid])
        return poly

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
        self._load_keepouts()
        self._load_positioner_params()
        self._load_circle_envelopes()

    def _load_keepouts(self):
        """Read latest versions of all keepout geometries."""
        self.keepout_P = PosPoly(self.config['KEEPOUT_PHI'], self.config['KEEPOUT_PHI_PT0'])
        self.keepout_T = PosPoly(self.config['KEEPOUT_THETA'], self.config['KEEPOUT_THETA_PT0'])
        self.keepout_PTL = PosPoly(self.config['KEEPOUT_PTL'], self.config['KEEPOUT_PTL_PT0'])
        self.keepout_GFA = PosPoly(self.config['KEEPOUT_GFA'], self.config['KEEPOUT_GFA_PT0'])
        self.keepout_GFA = self.keepout_GFA.rotated(self.config['KEEPOUT_GFA_ROT'])
        self.keepout_GFA = self.keepout_GFA.translated(self.config['KEEPOUT_GFA_X0'],self.config['KEEPOUT_GFA_Y0'])
        self.fixed_neighbor_keepouts = {pc.case.PTL : self.keepout_PTL, pc.case.GFA : self.keepout_GFA}

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
        self.Ee = self._max_extent() * 2        # extended-phi clear rotation envelope
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

    def _identify_neighbors(self, posid):
        """Find all neighbors which can possibly collide with a given positioner."""
        Ee = self.Ee_poly.translated(self.x0[posid], self.y0[posid])
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
        extended_phi = self.keepout_P.translated(max(self.R1.values()),0) # assumption here that phi arm polygon defined at 0 deg angle
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

    def register_as_frozen(self):
        """Sets an indicator that the sweep has been frozen at the end."""
        self.frozen_time = self.time[-1]

    @property
    def is_frozen(self):
        """Returns boolean value whether the sweep has a "freezing" event."""
        return self.frozen_time < math.inf
    
    def theta(self, step):
        """Returns theta position of the sweep at the specified timestep index."""
        return self.tp[0,step]
    
    def phi(self, step):
        """Returns phi position of the sweep at the specified timestep index."""
        return self.tp[1,step]
    
class PosPoly(object):
    """Represents a collidable polygonal envelope definition for a mechanical component
    of the fiber positioner.
    
        points        ... [[x1,x2,...], [y1,y2,...]] list of vertices of the polygon
        point0_index  ... first point in the list
        close_polygon ... whether to make an identical last point matching the first
    """
    def __init__(self, points, point0_index=0, close_polygon=True):
        self.points = points
        if point0_index:
            shift = point0_index + 1
            self.points[0] = self.points[0][shift:] + self.points[0][:shift]
            self.points[1] = self.points[1][shift:] + self.points[1][:shift]
        if close_polygon:
            self.points[0].append(points[0][0])
            self.points[1].append(points[1][0])

    def rotated(self, angle):
        """Returns a copy of the polygon object, with points rotated by angle (unit degrees)."""
        R = self._rotmat2D_deg(angle)
        p = self.points
        rng = range(len(p[0]))
        X = [R[0][0]*p[0][i] + R[0][1]*p[1][i] for i in rng]
        Y = [R[1][0]*p[0][i] + R[1][1]*p[1][i] for i in rng]
        return PosPoly([X,Y], point0_index=0, close_polygon=False)

    def translated(self, x, y):
        """Returns a copy of the polygon object, with points translated by distance (x,y)."""
        X = [x + val for val in self.points[0]]
        Y = [y + val for val in self.points[1]]
        return PosPoly([X,Y], point0_index=0, close_polygon=False)

    def collides_with(self, other):
        """Searches for collisions in space between this polygon and
        another PosPoly object. Returns a bool, where true indicates a
        collision.
        """
        if PosPoly._bounding_boxes_collide(self.points,other.points):
            return PosPoly._polygons_collide(self.points,other.points)
        else:
            return False

    @staticmethod
    def _bounding_boxes_collide(pts1,pts2):
        """Check whether the rectangular bounding boxes of two polygons collide.
        pts1 and pts2 are 2xN numpy arrays of the polygon (x,y) vertices (closed polygon).
        Returns True if the bounding boxes collide, False if they do not. Intended as
        a fast check, to enhance speed of other collision detection functions.
        """
        if   max(pts1[0]) < min(pts2[0]):
            return False
        elif max(pts1[1]) < min(pts2[1]):
            return False
        elif max(pts2[0]) < min(pts1[0]):
            return False
        elif max(pts2[1]) < min(pts1[1]):
            return False
        else:
            return True
    
    @staticmethod
    def _polygons_collide(pts1,pts2):
        """Check whether two closed polygons collide.
        pts1 and pts2 are 2xN numpy arrays of the polygon (x,y) vertices (closed polygon).
        Returns true if the polygons intersect, False if they do not.
        The algorithm is by detecting intersection of line segments, therefore the case of
        a small polygon completely enclosed by a larger polygon will return False. Not checking
        for this condition admittedly breaks some conceptual logic, but this case is not
        anticipated to occur given the DESI petal geometry, and speed is at a premium.
        """
        pts1 = np.array(pts1,dtype='float64')
        pts2 = np.array(pts2,dtype='float64')
        A1 = pts1[:,0:-1]
        A2 = pts1[:,1:]
        B1 = pts2[:,0:-1]
        B2 = pts2[:,1:]
        for i in range(np.shape(A1)[1]):
            out = PosPoly._segments_intersect(A1[:,i],A2[:,i],B1,B2) # note this is vectorized, to avoid having an internal for loop
            if any(out):
                return True
        return False

    @staticmethod
    @jit # This is about the only place I've found the @jit decorator helpful in here. Everywhere else actually costs overhead.
    def _segments_intersect(A1,A2,B1,B2):
        """Checks whether two 2d line segments intersect. The endpoints for segments
        A and B are each a pair of (x,y) coordinates. This function is vectorized,
        so either A or B can actually be an arbitrary number of segments. But the
        other one needs to be just one segment. They all need to be numpy arrays.
        For example, you could have A1,A2 both be 2x1 and B1,B2 both be 2xN or vice versa.
        """
        dx_A = A2[0] - A1[0]
        dy_A = A2[1] - A1[1]
        dx_B = B2[0] - B1[0]
        dy_B = B2[1] - B1[1]
        delta = dx_B * dy_A - dy_B * dx_A
        zero_delta = np.where(delta == 0) # parallel segments
        delta += 1e-16 # avoid divide-by-zero error in next line
        s = (dx_A * (B1[1] - A1[1]) + dy_A * (A1[0] - B1[0])) / delta
        t = (dx_B * (A1[1] - B1[1]) + dy_B * (B1[0] - A1[0])) / (-delta)
        test_intersect = (0 <= s) * (s <= 1) * (0 <= t) * (t <= 1)
        test_intersect[zero_delta] = False
        return test_intersect

    @staticmethod
    def _rotmat2D_rad(angle):
        """Return the 2d rotation matrix for an angle given in radians."""
        return [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]

    @staticmethod
    def _rotmat2D_deg(angle):
        """Return the 2d rotation matrix for an angle given in degrees."""
        return PosPoly._rotmat2D_rad(angle*math.pi/180.)

if __name__=="__main__":
    P1 = PosPoly([[0,1,1],[0,0,1]])
    P2 = P1.translated(0.5,0)
    P3 = P1.translated(10,0)
    P4 = P2.rotated(30)
    print(PosPoly._polygons_collide(P1.points,P1.points))
    print(PosPoly._polygons_collide(P1.points,P2.points))
    print(PosPoly._polygons_collide(P1.points,P3.points))
    print(PosPoly._polygons_collide(P1.points,P4.points))