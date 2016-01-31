import numpy as np
import posconstants as pc
import postransforms
import posplot
import configobj


class PosCollider(object):
    """PosCollider contains geometry definitions for mechanical components of the
    fiber positioner. It provides the methods to check for collisions between
    neighboring positioners.

    See DESI-0899 for geometry specifications, illustrations, and kinematics.
    """
    def __init__(self, configfile=''):
        # load up a configobj from _collision_settings_DEFAULT.conf, in pc.settings_directory
        if not(configfile):
            configfile = '_collision_settings_DEFAULT.conf'
        filename = pc.settings_directory + configfile
        self.config = configobj.ConfigObj(filename,unrepr=True)
        self.posmodels = []
        self.pos_neighbor_idxs = [] # indexes of all the positioners surround a given positioner
        self.collidable_relations = {'A':[],'B':[],'B_is_fixed':[]} # every unique pair of geometry that can collide
        self.fixed_neighbor_cases = []
        self.plotting_on = True
        self.timestep = self.config['TIMESTEP']
        self.plotter = posplot.PosPlot(fignum=0, timestep=self.timestep)

    def add_positioners(self, posmodels):
        """Add a positioner or multiple positioners to the collider object.
        """
        (pm, was_not_list) = pc.listify(posmodels, keep_flat=True)
        self.posmodels.extend(pm)
        self.pos_neighbor_idxs.extend([[] for i in range(len(pm))])
        self.fixed_neighbor_cases.extend([[] for i in range(len(pm))])
        self.load_config_data()

    def load_config_data(self):
        """Reads latest versions of all configuration file offset, range, and
        polygon definitions, and updates stored values accordingly.
        """
        self.timestep = self.config['TIMESTEP']
        self._load_keepouts()
        self._load_positioner_params()
        self._load_circle_envelopes()
        for p in self.posmodels:
            self._identify_neighbors(p)
        self._update_collidable_relations()

    def animate(self, sweeps):
        """Makes an animation of positioners moving about the petal.
            sweeps ... list of PosSweep instances describing positioners' real-time moves
        """
        self.plotter.clear()
        all_times = [s.time for s in sweeps]
        global_start = np.min([np.min(t) for t in all_times])
        self.plotter.add_or_change_item('GFA', '', global_start, self.keepout_GFA.points)
        self.plotter.add_or_change_item('PTL', '', global_start, self.keepout_PTL.points)
        for i in range(len(self.posmodels)):
            self.plotter.add_or_change_item('Eo', i, global_start, self.Eo_polys[i].points)
            self.plotter.add_or_change_item('Ei', i, global_start, self.Ei_polys[i].points)
            self.plotter.add_or_change_item('Ee', i, global_start, self.Ee_polys[i].points)
            self.plotter.add_or_change_item('line at 180', i, global_start, self.line180_polys[i].points)
        for s in sweeps:
            for i in range(len(s.time)):
                self.plotter.add_or_change_item('central body', s.posidx, s.time[i], self.place_central_body(s.posidx, s.tp[0,i]).points, s.collision_case)
                self.plotter.add_or_change_item('phi arm',      s.posidx, s.time[i], self.place_phi_arm(s.posidx, s.tp[:,i]).points,      s.collision_case)
                self.plotter.add_or_change_item('ferrule',      s.posidx, s.time[i], self.place_ferrule(s.posidx, s.tp[:,i]).points,      s.collision_case)
                if s.collision_case == pc.case.GFA:
                    self.plotter.add_or_change_item('GFA', '', s.time[i], self.keepout_GFA.points, pc.case.GFA)
                elif s.collision_case == pc.case.PTL:
                    self.plotter.add_or_change_item('PTL', '', s.time[i], self.keepout_PTL.points, pc.case.PTL)
        self.plotter.animate()

    def spactime_collision_between_positioners(self, idxA, init_obsTP_A, tableA, idxB, init_obsTP_B, tableB):
        """Wrapper for spacetime_collision method, specifically for checking two positioners
        against each other."""
        return self.spacetime_collision(idxA, init_obsTP_A, tableA, idxB, init_obsTP_B, tableB)

    def spactime_collision_with_fixed(self, idx, init_obsTP, table):
        """Wrapper for spacetime_collision method, specifically for checking one positioner
        against the fixed keepouts.
        """
        return self.spacetime_collision(idx, init_obsTP, table)

    def spacetime_collision(self, idxA, init_obsTP_A, tableA, idxB=None, init_obsTP_B=None, tableB=None, return_on_collision=True):
        """Searches for collisions in time and space between two positioners
        which are rotating according to the argued tables.

            idxA, idxB                  ...  indices of the positioners in the list self.posmodels
            init_obsTP_A, init_obsTP_B  ...  starting (theta,phi) positions, in the obsTP coordinate systems
            tableA, tableB              ...  dictionaries defining rotation schedules as described below
            return_on_collision         ...  whether to return immediately as soon as any collision is identified

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
            'prepause'  : list of postpause (after the rotations end) values in seconds

        The return is a list of instances of PosSweep, containing the theta and phi rotations
        in real time, and when if any collision, and the collision type.
        """
        time_start = 0
        time_end = 0
        pospos = True if idxB else False # whether this is checking collisions between two positioners (or if false, between one positioner and fixed keepouts)
        if pospos:
            tables = [tableA,tableB]
            sweeps = [PosSweep(idxA), PosSweep(idxB)]
        else:
            tables = [tableA]
            sweeps = [PosSweep(idxA)]
        for table in tables:
            table['start_prepause'] = [time_start]
            table['start_move'] = []
            table['start_postpause'] = []
            for row in range(table['nrows']):
                table['start_move'].append(table['start_prepause'][row] + table['prepause'][row])
                table['start_postpause'].append(table['start_move'][row] + table['move_time'][row])
                time_end_temp = table['start_postpause'][row] + table['postpause'][row]
                if row < table['nrows'] - 1:
                   table['start_prepause'].append(time_end_temp)
            time_end = np.max([time_end, time_end_temp])
        time_domain = np.arange(time_start, time_end, self.timestep)
        if ((time_end - time_start) / self.timestep) % 1:
            time_domain = np.append(time_domain, time_end)
        rows = [0]*2 if pospos else [0]
        stage = ['prepause']*2 if pospos else ['prepause']
        stage_now = [0]*2 if pospos else [0]
        stage_start = [0]*2 if pospos else [0]
        for now in time_domain:
            for i in range(len(tables)):
                if stage[i] == 'prepause' and now >= tables[i]['start_move'][rows[i]]:
                    stage[i] = 'move'
                if stage[i] == 'move' and now >= tables[i]['start_postpause'][rows[i]]:
                    stage[i] = 'postpause'
                if stage[i] == 'postpause' and i < len(rows) - 1:
                    if now >= tables[i]['start_prepause'][rows[i]+1]:
                        stage[i] = 'prepause'
                        rows[i] += 1
                stage_start[i] = tables[i]['start_' + stage[i]][rows[i]]
                stage_now[i] = now - stage_start[i]
                if stage[i] == 'move':
                    moveT = np.min([stage_now[i] * tables[i]['Tdot'][rows[i]], tables[i]['dT'][rows[i]]])
                    moveP = np.min([stage_now[i] * tables[i]['Pdot'][rows[i]], tables[i]['dP'][rows[i]]])
                    sweeps[i].tp = np.append(sweeps[i].tp, [[moveT],[moveP]], axis=1)
                    sweeps[i].time = np.append(sweeps[i].time, now)
            if pospos:
                collision_case = self.spatial_collision_between_positioners(idxA, idxB, sweeps[0].tp[:,-1], sweeps[1].tp[:,-1])
            else:
                collision_case = self.spatial_collision_with_fixed(idxA, sweeps[0].tp[:,-1])
            if collision_case != pc.case.I:
                for s in sweeps:
                    s.collision_case = collision_case
                    s.collision_time = now
                if return_on_collision:
                    break
        return sweeps

    def spatial_collision_between_positioners(self, idxA, idxB, obsTP_A, obsTP_B):
        """Searches for collisions in space between two fiber positioners.

            idxA, idxB        ...  indices of the positioners in the list self.posmodels
            obsTP_A, obsTP_B  ...  (theta,phi) positions of the axes for positioners 1 and 2

        obsTP_A and obsTP_B are in the (obsT,obsP) coordinate system, as defined in
        PosTransforms.

        The return is an enumeration of type "case", indicating what kind of collision
        was first detected, if any.
        """
        if obsTP_A[1] >= self.Eo_phi and obsTP_B[1] >= self.Eo_phi:
            return pc.case.I
        elif obsTP_A[1] < self.Eo_phi and obsTP_B[1] >= self.Ei_phi: # check case IIIA
            if self._case_III_collision(idxA, idxB, obsTP_A, obsTP_B[0]):
                return pc.case.IIIA
            else:
                return pc.case.I
        elif obsTP_B[1] < self.Eo_phi and obsTP_A[1] >= self.Ei_phi: # check case IIIB
            if self._case_III_collision(idxB, idxA, obsTP_B, obsTP_A[0]):
                return pc.case.IIIB
            else:
                return pc.case.I
        else: # check cases II and III
            if self._case_III_collision(idxA, idxB, obsTP_A, obsTP_B[0]):
                return pc.case.IIIA
            elif self._case_III_collision(idxB, idxA, obsTP_B, obsTP_A[0]):
                return pc.case.IIIB
            elif self._case_II_collision(idxA, idxB, obsTP_A, obsTP_B):
                return pc.case.II
            else:
                return pc.case.I

    def spatial_collision_with_fixed(self, idx, obsTP):
        """Searches for collisions in space between a fiber positioner and all
        fixed keepout envelopes.

            idx         ...  index of the positioner in the list self.posmodels
            obsTP       ...  (theta,phi) position of the axes of the positioner

        obsTP is in the (obsT,obsP) coordinate system, as defined in
        PosTransforms.

        The return is an enumeration of type "case", indicating what kind of collision
        was first detected, if any.
        """
        if self.fixed_neighbor_cases[idx]:
            poly1 = self.place_phi_arm(idx,obsTP)
            for fixed_case in self.fixed_neighbor_cases[idx]:
                poly2 = self.fixed_neighbor_keepouts[fixed_case]
                if poly1.collides_with(poly2):
                    return fixed_case
        return pc.case.I

    def place_phi_arm(self, idx, obsTP):
        """Rotates and translates the phi arm to position defined by the positioner's
        xy0 and the argued obsTP (theta,phi) angles.
        """
        poly = self.keepout_P.rotated(obsTP[1])
        poly = poly.translated(self.R1[idx], 0)
        poly = poly.rotated(obsTP[0])
        poly = poly.translated(self.xy0[0,idx], self.xy0[1,idx])
        return poly

    def place_central_body(self, idx, obsT):
        """Rotates and translates the central body of positioner identified by idx
        to it's xy0 and the argued obsT theta angle.
        """
        poly = self.keepout_T.rotated(obsT)
        poly = poly.translated(self.xy0[0,idx], self.xy0[1,idx])
        return poly

    def place_ferrule(self, idx, obsTP):
        """Rotates and translates the ferrule to position defined by the positioner's
        xy0 and the argued obsTP (theta,phi) angles.
        """
        poly = self.ferrule_poly.translated(self.R2[idx], 0)
        poly = poly.rotated(obsTP[1])
        poly = poly.translated(self.R1[idx],0)
        poly = poly.rotated(obsTP[0])
        poly = poly.translated(self.xy0[0,idx], self.xy0[1,idx])
        return poly

    def _case_II_collision(self, idx1, idx2, tp1, tp2):
        """Search for case II collision, positioner 1 arm against positioner 2 arm."""
        poly1 = self.place_phi_arm(idx1, tp1)
        poly2 = self.place_phi_arm(idx2, tp2)
        return poly1.collides_with(poly2)

    def _case_III_collision(self, idx1, idx2, tp1, t2):
        """Search for case III collision, positioner 1 arm against positioner 2 central body."""
        poly1 = self.place_phi_arm(idx1, tp1)
        poly2 = self.place_central_body(idx2, t2)
        return poly1.collides_with(poly2)

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
        n = len(self.posmodels)
        self.R1 = np.zeros(n)
        self.R2 = np.zeros(n)
        self.xy0 = np.zeros((2,n))
        self.tp0 = np.zeros((2,n))
        self.tp_ranges = [[] for i in range(n)]
        for i in range(len(self.posmodels)):
            self.R1[i] = self.posmodels[i].state.read('LENGTH_R1')
            self.R2[i] = self.posmodels[i].state.read('LENGTH_R2')
            self.xy0[:,i] = np.array([self.posmodels[i].state.read('OFFSET_X'), self.posmodels[i].state.read('OFFSET_Y')])
            self.tp0[:,i] = np.array([self.posmodels[i].state.read('OFFSET_T'), self.posmodels[i].state.read('OFFSET_P')])
            self.tp_ranges[i] = np.array(self.posmodels[i].trans.shaft_ranges('targetable'))

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
        self.Eo_poly = PosPoly(self._circle_poly_points(self.Eo, self.config['RESOLUTION_EO']))
        self.Ei_poly = PosPoly(self._circle_poly_points(self.Ei, self.config['RESOLUTION_EI']))
        self.Ee_poly = PosPoly(self._circle_poly_points(self.Ee, self.config['RESOLUTION_EE']))
        self.line180_poly = PosPoly([[0,0],[-self.Eo/2,0]],close_polygon=False)
        self.Eo_polys = []
        self.Ei_polys = []
        self.Ee_polys = []
        self.line180_polys = []
        for i in range(len(self.posmodels)):
            x = self.xy0[0,i]
            y = self.xy0[1,i]
            self.Eo_polys.append(self.Eo_poly.translated(x,y))
            self.Ei_polys.append(self.Ei_poly.translated(x,y))
            self.Ee_polys.append(self.Ee_poly.translated(x,y))
            self.line180_polys.append(self.line180_poly.rotated(self.tp0[0,i]).translated(x,y))
        self.ferrule_diam = self.config['FERRULE_DIAM']
        self.ferrule_poly = PosPoly(self._circle_poly_points(self.ferrule_diam, self.config['FERRULE_RESLN']))

    def _identify_neighbors(self, posmodel):
        """Find all neighbors which can possibly collide with a given posmodel."""
        p1 = self.posmodels.index(posmodel)
        Ee1 = self.Ee_poly.translated(self.xy0[0,p1], self.xy0[1,p1])
        for p2 in range(len(self.posmodels)):
            Ee2 = self.Ee_poly.translated(self.xy0[0,p2], self.xy0[1,p2])
            if not(p1 == p2) and Ee1.collides_with(Ee2):
                self.pos_neighbor_idxs[p1].append(p2)
        for p2 in self.fixed_neighbor_keepouts.keys():
            if Ee1.collides_with(self.fixed_neighbor_keepouts[p2]):
                self.fixed_neighbor_cases[p1].append(p2)

    def _update_collidable_relations(self):
        """Update the list of all possible collisions."""
        A = []
        B = []
        B_is_fixed = []
        for i in range(len(self.pos_neighbor_idxs)):
            for j in self.pos_neighbor_idxs[i]:
                if i in A and j in B and A.index(i) == B.index(j):
                    pass
                elif j in A and i in B and A.index(j) == B.index(i):
                    pass
                else:
                    A.append(i)
                    B.append(j)
                    B_is_fixed.append(False)
        i = 0
        for cases in self.fixed_neighbor_cases:
            for case in cases:
                A.append(i)
                B.append(case)
                B_is_fixed.append(True)
            i += 1
        self.collidable_relations['A'] = A
        self.collidable_relations['B'] = B
        self.collidable_relations['B_is_fixed'] = B_is_fixed

    def _max_extent(self):
        """Calculation of max radius of keepout for a positioner with fully-extended phi arm."""
        extended_phi = self.keepout_P.translated(np.max(self.R1),0) # assumption here that phi arm polygon defined at 0 deg angle
        return max(np.sqrt(np.sum(extended_phi.points**2, axis=0)))

    @staticmethod
    def _circle_poly_points(diameter, npts, outside=True):
        """Constuct a polygon approximating a circle of a given diameter, with a
        given number of points. The polygon's segments are tangent to the circle if
        the optional argument 'outside' is true. If 'outside' is false, then the
        segment points lie on the circle.
        """
        alpha = np.linspace(0, 2 * np.pi, npts + 1)[0:-1]
        if outside:
            half_angle = alpha[0]/2
            points_radius = diameter/2 / np.cos(half_angle)
        else:
            points_radius = diameter/2
        x = points_radius * np.cos(alpha)
        y = points_radius * np.sin(alpha)
        return np.array([x,y])


class PosSweep(object):
    """Contains a real-time description of the sweep of positioner mechanical
    geometries through space.
    """
    def __init__(self, posidx=None):
        self.posidx = posidx              # index identifying the positioner
        self.time = np.array([])          # real time at which each TP position value occurs
        self.tp   = np.array([[],[]])     # theta,phi angles corresponding to time
        self.collision_case = pc.case.I   # enumeration of type "case", indicating what kind of collision first detected, if any
        self.collision_time = np.inf      # time at which collision occurs. if no collision, the time is inf


class PosPoly(object):
    """Represents a collidable polygonal envelope definition for a mechanical component
    of the fiber positioner.
    """
    def __init__(self, points, point0_index=0, close_polygon=True):
        points = np.array(points)
        head = points[:,np.arange(point0_index,len(points[0]))]
        tail = points[:,np.arange(0,point0_index+1*close_polygon)]
        self.points = np.append(head, tail, axis=1)

    def rotated(self, angle, getobject=False):
        """Returns a copy of the polygon object, with points rotated by angle (unit degrees)."""
        return PosPoly(np.dot(PosPoly._rotmat2D_deg(angle), self.points), point0_index=0, close_polygon=False)

    def translated(self, x, y):
        """Returns a copy of the polygon object, with points translated by distance (x,y)."""
        return PosPoly(self.points + np.array([[x],[y]]), point0_index=0, close_polygon=False)

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
        if   np.max(pts1[0]) < np.min(pts2[0]):
            return False
        elif np.max(pts1[1]) < np.min(pts2[1]):
            return False
        elif np.max(pts2[0]) < np.min(pts1[0]):
            return False
        elif np.max(pts2[1]) < np.min(pts1[1]):
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
        for i in range(len(pts1[0][:-1])):
            A1 = np.array([pts1[0,i],   pts1[1,i]])
            A2 = np.array([pts1[0,i+1], pts1[1,i+1]])
            for j in range(len(pts2[0][:-1])):
                B1 = np.array([pts2[0,j],   pts2[1,j]])
                B2 = np.array([pts2[0,j+1], pts2[1,j+1]])
                if PosPoly._segments_intersect(A1,A2,B1,B2):
                    return True
        return False

    @staticmethod
    def _segments_intersect(A1,A2,B1,B2):
        """Checks whether two 2d line segments intersect. The endpoints for segments
        A and B are each a pair of (x,y) coordinates.
        """
        dx_A = A2[0] - A1[0]
        dy_A = A2[1] - A1[1]
        dx_B = B2[0] - B1[0]
        dy_B = B2[1] - B1[1]
        delta = dx_B * dy_A - dy_B * dx_A
        if delta == 0:
            return False  # parallel segments
        s = (dx_A * (B1[1] - A1[1]) + dy_A * (A1[0] - B1[0])) / delta
        t = (dx_B * (A1[1] - B1[1]) + dy_B * (B1[0] - A1[0])) / (-delta)
        return (0 <= s <= 1) and (0 <= t <= 1)

    @staticmethod
    def _rotmat2D_rad(angle):
        """Return the 2d rotation matrix for an angle given in radians."""
        return np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])

    @staticmethod
    def _rotmat2D_deg(angle):
        """Return the 2d rotation matrix for an angle given in degrees."""
        return PosPoly._rotmat2D_rad(np.deg2rad(angle))
