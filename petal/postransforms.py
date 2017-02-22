import numpy as np
import posconstants as pc
import posmodel

class PosTransforms(object):
    """This class provides transformations between positioner coordinate systems. All
    coordinate transforms must be done via the methods provided here. This ensures
    consistent and invertible definitions.

    An instance of PosTransforms is associated with a particular instance of PosModel,
    so that the transforms will automatically draw on the correct calibration parameters
    for that particular positioner.

    The coordinate systems are:

        posXY  ... (x,y) local to fiber positioner, centered on theta axis, looking at fiber tip
        obsXY  ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        posTP  ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        obsTP  ... (theta,phi) expected position of fiber tip including offsets
        QS     ... (q,s) global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        flatXY ... (x,y) global to focal plate, with focal plate slightly stretched out and flattened (used for anti-collision)

    The fundamental transformations provided are:

        obsTP <--> posTP
        posTP <--> posXY
        posXY <--> obsXY
        obsXY <--> QS
        QS    <--> flatXY

    Additionally, some composite transformations are provided for convenience of syntax:

        posTP <--> obsXY
        posTP <--> QS
        posTP <--> flatXY
        obsXY <--> flatXY
        obsTP <--> flatXY

    These can be chained together in any order to convert among the various coordinate systems.

    The theta axis has a physical travel range wider than +/-180 degrees. Simple vector addition
    and subtraction is not sufficient when delta values cross the theta hardstop near +/-180.
    Therefore special methods are provided for performing addition and subtraction operations
    between two points, with angle-wrapping logic included.

        delta_posTP  ... is like dtdp = tp1 - tp0
        delta_obsTP
        addto_posTP  ... is like tp1 = tp0 + dtdtp
        addto_obsTP

    To round out the syntax, similar delta_ and addto_ methods are provided for the other
    coordinate systems. These are convenicence methods to do the vector subtraction or addition.

    Note in practice that the coordinate S is similar, but not identical, to the radial distance
    R from the optical axis. This similarity is because the DESI focal plate curvature is gentle.
    See DESI-0530 for detail on the (Q,S) coordinate system.
    """

    def __init__(self, this_posmodel=None):
        if this_posmodel == None:
            this_posmodel = posmodel.PosModel()
        self.posmodel = this_posmodel
        self.alt_override = False  # alternate calibration values one can set, so one can temporarily override whatever the positioner's stored vals are
        self.alt = {'LENGTH_R1' : 3.0,
                    'LENGTH_R2' : 3.0,
                    'OFFSET_X'  : 0.0,
                    'OFFSET_Y'  : 0.0,
                    'OFFSET_T'  : 0.0,
                    'OFFSET_P'  : 0.0}

    # SHAFT RANGES
    def shaft_ranges(self, range_limits):
        """Returns a set of range limits for the theta and phi axes. The argument
        range_limits is a string:
            ... 'full' means from hardstop-to-hardstop
            ... 'targetable' restricts range by excluding the debounce and backlash clearance zones near the hardstops
            ... 'exact' means theta range of [-179.999999999,180] and phi range of [0,180]
        """
        if range_limits == 'full':
            return [self.posmodel.full_range_T, self.posmodel.full_range_P]
        elif range_limits == 'targetable':
            return [self.posmodel.targetable_range_T, self.posmodel.targetable_range_P]
        elif range_limits == 'exact':
            return [[-179.999999999,180],[0,180]]
        else:
            print('bad range_limits argument "' + str(range_limits) + '"')
            return None

    # FUNDAMENTAL TRANSFORMATIONS
    def obsTP_to_posTP(self, tp):
        """
        obsTP          ... (theta,phi) expected position of fiber tip, including offsets and calibrations
        posTP          ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        INPUT:  [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        RETURN: [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        """
        (tp, was_not_list) = pc.listify(tp)
        T = np.array(tp[0]) - (self.posmodel.state.read('OFFSET_T') if not self.alt_override else self.alt['OFFSET_T'])
        P = np.array(tp[1]) - (self.posmodel.state.read('OFFSET_P') if not self.alt_override else self.alt['OFFSET_P'])
        TP = np.array([T,P]).tolist()
        if was_not_list:
            TP = pc.delistify(TP)
        return TP

    def posTP_to_obsTP(self, tp):
        """
        posTP          ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        obsTP          ... (theta,phi) expected position of fiber tip, including offsets and calibrations
        INPUT:  [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        RETURN: [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        """
        (tp, was_not_list) = pc.listify(tp)
        T = np.array(tp[0]) + (self.posmodel.state.read('OFFSET_T') if not self.alt_override else self.alt['OFFSET_T'])
        P = np.array(tp[1]) + (self.posmodel.state.read('OFFSET_P') if not self.alt_override else self.alt['OFFSET_P'])
        TP = np.array([T,P]).tolist()
        if was_not_list:
            TP = pc.delistify(TP)
        return TP

    def posTP_to_posXY(self, tp):
        """
        posTP ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        obsXY ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        INPUT:  [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        RETURN: [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        """
        (tp, was_not_list) = pc.listify(tp)
        r = [self.posmodel.state.read('LENGTH_R1') if not self.alt_override else self.alt['LENGTH_R1'],
             self.posmodel.state.read('LENGTH_R2') if not self.alt_override else self.alt['LENGTH_R2']]
        TP = self.posTP_to_obsTP(tp)  # adjust shaft angles into observer space (since observer sees the physical phi = 0)
        xy = self.tp2xy(TP, r)        # calculate xy in posXY space
        xy = xy.tolist()
        if was_not_list:
            xy = pc.delistify(xy)
        return xy

    def posXY_to_posTP(self, xy, range_limits='full'):
        """
        obsXY ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        posTP ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        INPUT:  [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
                range_limits (optional) string, see shaft_ranges method
        RETURN: [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
                [N]    array of [index_values]
        The output "unreachable" is a list of all the indexes of the points that could not be physically reached.
        """
        (xy, was_not_list) = pc.listify(xy)
        r = [self.posmodel.state.read('LENGTH_R1') if not self.alt_override else self.alt['LENGTH_R1'],
             self.posmodel.state.read('LENGTH_R2') if not self.alt_override else self.alt['LENGTH_R2']]
        shaft_ranges = self.shaft_ranges(range_limits)
        obs_range = self.posTP_to_obsTP(shaft_ranges)  # want range used in next line to be according to observer (since observer sees the physical phi = 0)
        (tp, unreachable) = self.xy2tp(xy, r, obs_range)
        TP = self.obsTP_to_posTP(tp)                  # adjust angles back into shaft space
        if was_not_list:
            TP = pc.delistify(TP)
        return TP, unreachable

    def posXY_to_obsXY(self, xy):
        """
        posXY          ... (x,y) local to fiber positioner, centered on theta axis, looking at fiber tip
        obsXY          ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        INPUT:  [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        RETURN: [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        """
        (xy, was_not_list) = pc.listify(xy)
        
        X = np.array(xy[0]) + (self.posmodel.state.read('OFFSET_X') if not self.alt_override else self.alt['OFFSET_X'])
        Y = np.array(xy[1]) + (self.posmodel.state.read('OFFSET_Y') if not self.alt_override else self.alt['OFFSET_Y'])
        XY = np.array([X,Y]).tolist()
        if was_not_list:
            XY = pc.delistify(XY)
        return XY

    def obsXY_to_posXY(self, xy):
        """
        obsXY          ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        posXY          ... (x,y) local to fiber positioner, centered on theta axis, looking at fiber tip
        INPUT:  [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        RETURN: [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        """
        (xy, was_not_list) = pc.listify(xy)
        X = np.array(xy[0]) - (self.posmodel.state.read('OFFSET_X') if not self.alt_override else self.alt['OFFSET_X'])
        Y = np.array(xy[1]) - (self.posmodel.state.read('OFFSET_Y') if not self.alt_override else self.alt['OFFSET_Y'])
        XY = np.array([X,Y]).tolist()
        if was_not_list:
            XY = pc.delistify(XY)
        return XY

    def obsXY_to_QS(self,xy):
        """
        obsXY   ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        QS      ... (q,s) global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        INPUT:  [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        RETURN: [2][N] array of [[q_values],[s_values]] or [2] array of [q_value,s_value]
        """
        (xy, was_not_list) = pc.listify(xy)
        X = np.array(xy[0])
        Y = np.array(xy[1])
        Q = np.degrees(np.arctan2(Y,X))
        R = np.sqrt(X**2 + Y**2)
        S = self.R2S(R.tolist())
        QS = [Q.tolist(),S]
        if was_not_list:
            QS = pc.delistify(QS)
        return QS

    def QS_to_obsXY(self,qs):
        """
        QS      ... (q,s) global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        obsXY   ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        INPUT:  [2][N] array of [[q_values],[s_values]] or [2] array of [q_value,s_value]
        RETURN: [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        """
        (qs, was_not_list) = pc.listify(qs)
        Q = qs[0]
        R = self.S2R(qs[1])
        X = R * np.cos(np.deg2rad(Q))
        Y = R * np.sin(np.deg2rad(Q))
        XY = [X.tolist(),Y.tolist()]
        if was_not_list:
            XY = pc.delistify(XY)
        return XY

    def QS_to_flatXY(self,qs):
        """
        QS      ... (q,s) global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        flatXY  ... (x,y) global to focal plate, with focal plate slightly stretched out and flattened (used for anti-collision)
        INPUT:  [2][N] array of [[q_values],[s_values]] or [2] array of [q_value,s_value]
        RETURN: [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        """
        (qs, was_not_list) = pc.listify(qs)
        Q = np.array(qs[0])
        S = np.array(qs[1])
        X = S * np.cos(np.deg2rad(Q))
        Y = S * np.sin(np.deg2rad(Q))
        XY = [X.tolist(),Y.tolist()]
        if was_not_list:
            XY = pc.delistify(XY)
        return XY

    def flatXY_to_QS(self,xy):
        """
        flatXY  ... (x,y) global to focal plate, with focal plate slightly stretched out and flattened (used for anti-collision)
        QS      ... (q,s) global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        INPUT:  [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        RETURN: [2][N] array of [[q_values],[s_values]] or [2] array of [q_value,s_value]
        """
        (xy, was_not_list) = pc.listify(xy)
        X = np.array(xy[0])
        Y = np.array(xy[1])
        Q = np.degrees(np.arctan2(Y,X))
        S = np.sqrt(X**2 + Y**2)
        QS = [Q.tolist(),S.tolist()]
        if was_not_list:
            QS = pc.delistify(QS)
        return QS

    # COMPOSITE TRANSFORMATIONS
    def posTP_to_obsXY(self,tp):
        """Composite transformation, performs posTP --> posXY --> obsXY."""
        posXY = self.posTP_to_posXY(tp)
        obsXY = self.posXY_to_obsXY(posXY)
        return obsXY

    def obsXY_to_posTP(self,xy,range_limits='full'):
        """Composite transformation, performs obsXY --> posXY --> posTP."""
        posXY = self.obsXY_to_posXY(xy)
        (tp,unreachable) = self.posXY_to_posTP(posXY,range_limits)
        return tp, unreachable

    def posTP_to_QS(self,tp):
        """Composite transformation, performs posTP --> posXY --> obsXY --> QS."""
        xy = self.posTP_to_obsXY(tp)
        qs = self.obsXY_to_QS(xy)
        return qs

    def QS_to_posTP(self,qs,range_limits='full'):
        """Composite transformation, performs QS --> obsXY --> posXY --> posTP."""
        xy = self.QS_to_obsXY(qs)
        (tp,unreachable) = self.obsXY_to_posTP(xy,range_limits)
        return tp, unreachable

    def posTP_to_flatXY(self,tp):
        """Composite transformation, performs posTP --> posXY --> obsXY --> QS --> flatXY."""
        qs = self.posTP_to_QS(tp)
        xy = self.QS_to_flatXY(qs)
        return xy

    def flatXY_to_posTP(self,xy,range_limits='full'):
        """Composite transformation, performs flatXY --> QS --> obsXY --> posXY --> posTP."""
        qs = self.flatXY_to_QS(xy)
        (tp,unreachable) = self.QS_to_posTP(qs,range_limits)
        return tp, unreachable

    def obsXY_to_flatXY(self,xy):
        """Composite transformation, performs obsXY --> QS --> flatXY."""
        qs = self.obsXY_to_QS(xy)
        flatXY = self.QS_to_flatXY(qs)
        return flatXY

    def flatXY_to_obsXY(self,xy):
        """Composite transformation, performs flatXY --> QS --> obsXY."""
        qs = self.flatXY_to_QS(xy)
        obsXY = self.QS_to_obsXY(qs)
        return obsXY

    def obsTP_to_flatXY(self,tp):
        """Composite transformation, performs obsTP --> posTP --> posXY --> obsXY --> QS --> flatXY."""
        posTP = self.obsTP_to_posTP(tp)
        xy = self.posTP_to_flatXY(posTP)
        return xy

    def flatXY_to_obsTP(self,xy,range_limits='full'):
        """Composite transformation, performs flatXY --> QS --> obsXY --> posXY --> posTP --> obsTP"""
        (posTP,unreachable) = self.flatXY_to_posTP(xy,range_limits)
        obsTP = self.posTP_to_obsTP(posTP)
        return obsTP, unreachable

    # DIFFERENCE METHODS
    def delta_posXY(self, xy1, xy0):
        """Returns dxdy corresponding to xy1 - xy0."""
        return PosTransforms.vector_delta(xy1,xy0)

    def delta_obsXY(self, xy1, xy0):
        """Returns dxdy corresponding to xy1 - xy0."""
        return PosTransforms.vector_delta(xy1,xy0)

    def delta_posTP(self, tp1, tp0, range_wrap_limits='full'):
        """Returns dtdp corresponding to tp1 - tp0.
        The range_wrap_limits option can be any of the values for the shaft_ranges
        method, or 'none'. If 'none', then the returned delta is a simple vector subtraction
        with no special checks for angle-wrapping across positioner's theta = +/-180 deg.
        """
        dtdp = PosTransforms.vector_delta(tp1,tp0)
        if range_wrap_limits != 'none':
            dtdp = self.wrap_theta(tp0,dtdp,range_wrap_limits)
        return dtdp

    def delta_obsTP(self, tp1, tp0, range_wrap_limits='full'):
        """Returns dtdp corresponding to tp1 - tp0.
        The range_wrap_limits option can be any of the values for the shaft_ranges
        method, or 'none'. If 'none', then the returned delta is a simple vector subtraction
        with no special checks for angle-wrapping across positioner's theta = +/-180 deg.
        """
        TP0 = self.obsTP_to_posTP(tp0)
        TP1 = self.obsTP_to_posTP(tp1)
        return self.delta_posTP(TP1,TP0,range_wrap_limits)

    def delta_QS(self, qs1, qs0):
        """Returns dqds corresponding to qs1 - qs0."""
        return PosTransforms.vector_delta(qs1,qs0)

    def delta_flatXY(self, xy0, xy1):
        """Returns dxdy corresponding to xy1 - xy0."""
        return PosTransforms.vector_delta(xy1,xy0)

    # ADDITION METHODS
    def addto_posXY(self, xy0, dxdy):
        """Returns xy corresponding to xy0 + dxdy."""
        return PosTransforms.vector_add(xy0,dxdy)

    def addto_obsXY(self, xy0, dxdy):
        """Returns xy corresponding to xy0 + dxdy."""
        return PosTransforms.vector_add(xy0,dxdy)

    def addto_posTP(self, tp0, dtdp, range_wrap_limits='full'):
        """Returns tp corresponding to tp0 + dtdp.
        The range_wrap_limits option can be any of the values for the shaft_ranges
        method, or 'none'. If 'none', then the returned point is a simple vector addition
        with no special checks for angle-wrapping across positioner's theta = +/-180 deg.
        """
        if range_wrap_limits != 'none':
            dtdp = self.wrap_theta(tp0,dtdp,range_wrap_limits)
        return PosTransforms.vector_add(tp0,dtdp)

    def addto_obsTP(self, tp0, dtdp, range_wrap_limits='full'):
        """Returns tp corresponding to tp0 + dtdp.
        The range_wrap_limits option can be any of the values for the shaft_ranges
        method, or 'none'. If 'none', then the returned point is a simple vector addition
        with no special checks for angle-wrapping across positioner's theta = +/-180 deg.
        """
        TP0 = self.obsTP_to_posTP(tp0)
        return self.addto_posTP(TP0,dtdp,range_wrap_limits)

    def addto_QS(self, qs0, dqds):
        """Returns qs corresponding to qs0 + dqds."""
        return PosTransforms.vector_add(qs0,dqds)

    def addto_flatXY(self, xy0, dxdy):
        """Returns xy corresponding to xy0 + dxdy."""
        return PosTransforms.vector_add(xy0,dxdy)

    # INTERNAL METHODS
    def wrap_theta(self,tp0,dtdp,range_wrap_limits='full'):
        """Returns a modified dtdp after appropriately wrapping the delta theta
        to not cross a physical hardstop. The range_wrap_limits option can be any
        of the values for the shaft_ranges method.
        """
        (dtdp, was_not_list) = pc.listify(dtdp)
        dt = np.array(dtdp[0])
        t = tp0[0] + dt
        wrapped_dt = dt - 360*np.sign(dt)
        wrapped_t = np.array(tp0[0]) + wrapped_dt
        t_range = self.shaft_ranges(range_wrap_limits)[pc.T]
        if np.min(t_range) <= wrapped_t and wrapped_t <= np.max(t_range):
            if (np.min(t_range) > t or np.max(t_range) < t) or np.abs(wrapped_dt) < np.abs(dt):
                dtdp[0] = wrapped_dt.tolist()
        if was_not_list:
            dtdp = pc.delistify(dtdp)
        return dtdp

    # STATIC INTERNAL METHODS
    @staticmethod
    def R2S(r):
        """Uses focal surface definition of DESI-0530 to convert R coordinate to S.
        INPUT:  R, single value or list of values
        OUTPUT: S, single value or list of values
        """
        return np.array(pc.R2S_lookup(r)).tolist()

    @staticmethod
    def S2R(s):
        """Uses focal surface definition of DESI-0530 to convert S coordinate to R.
        INPUT:  R, single value or list of values
        OUTPUT: S, single value or list of values
        """
        return np.array(pc.S2R_lookup(s)).tolist()

    @staticmethod
    def tp2xy(tp, r):
        """Converts TP angles into XY coordinates, where arm lengths
        associated with angles theta and phi are respectively r(1) and r(2).

        INPUTS:   tp  = 2xN array of (theta,phi) angles
                   r  = 1x2 array of arm lengths. r(1) = central arm, r(2) = eccentric arm

        OUTPUTS:  xy  = 2xN array of (x,y) coordinates
        """
        tp = np.array(tp)
        x = r[0] * np.cos(np.deg2rad(tp[0])) + r[1] * np.cos(np.deg2rad(tp[0] + tp[1]))
        y = r[0] * np.sin(np.deg2rad(tp[0])) + r[1] * np.sin(np.deg2rad(tp[0] + tp[1]))
        xy = np.array([x.tolist(), y.tolist()])
        return xy

    @staticmethod
    def xy2tp(xy, r, ranges):
        """Converts XY coordinates into TP angles, where arm lengths
         associated with angles theta and phi are respectively r(1) and r(2).

        INPUTS:   xy ... 2xN array of (x,y) coordinates
                   r ... 1x2 array of arm lengths. r(1) = central arm, r(2) = eccentric arm
              ranges ... 2x2 array of [[min(theta),max(theta)],[min(phi),max(phi)]
        OUTPUTS:  tp ... 2xN array of (theta,phi) angles, unit degrees
         unreachable ... list of indexes of all the points that could not be reached.
                         (the corresponding tp value returned will be a closest approach to the unreachable point)
        """
        theta_centralizing_err_tol = 1e-4 # within this much xy error allowance, adjust theta toward center of its range
        n_theta_centralizing_iters = 3    # number of points to try when attempting to centralize theta
        x = np.array(xy[0])
        y = np.array(xy[1])
        T = np.zeros(len(x))
        P = np.zeros(len(x))
        unreachable = np.array([False]*len(x))

        # adjust targets within reachable annulus
        hypot = (x**2 + y**2)**0.5
        angle = np.arctan2(y,x)
        outer = r[0] + r[1]
        inner = abs(r[0] - r[1])
        unreachable[hypot > outer] = True
        unreachable[hypot < inner] = True
        inner += np.finfo(float).eps*10 # slight contraction to avoid numeric divide-by-zero type of errors
        outer -= np.finfo(float).eps*10 # slight contraction to avoid numeric divide-by-zero type of errors
        HYPOT = hypot
        HYPOT[hypot >= outer] = outer
        HYPOT[hypot <= inner] = inner
        X = HYPOT*np.cos(angle)
        Y = HYPOT*np.sin(angle)
        ANGLE = np.arctan2(Y,X)

        # transfrom from cartesian XY to angles TP
        arccos_arg = (X**2 + Y**2 - (r[0]**2 + r[1]**2)) / (2 * r[0] * r[1])
        P = np.arccos(arccos_arg)
        arcsin_arg = r[1] / HYPOT * np.sin(P)
        outofrange = np.abs(arcsin_arg) > 1 # will round arcsin arguments to 1 or -1
        arcsin_arg[outofrange] = np.sign(arcsin_arg[outofrange])
        #T = ANGLE - np.arcsin(arcsin_arg) # older method of calculating theta, had some degeneracies for points near center, if LENGTH_R1 << LENGTH_R2
        T = ANGLE - np.arctan2(r[1]*np.sin(P),r[0]+r[1]*np.cos(P)) 
        T *= 180/np.pi
        P *= 180/np.pi

        # wrap angles into travel ranges
        TP = np.array([T,P])
        for i in range(len(TP)):
            range_min = min(ranges[i])
            range_max = max(ranges[i])
            below = np.where(TP[i] < range_min)
            TP[i,below] += np.floor((range_max - TP[i,below])/360)*360  # try +360 phase wrap
            still_below = np.where(TP[i] < range_min)
            TP[i,still_below] = range_min
            unreachable[still_below] = True
            above = np.where(TP[i] > range_max)
            TP[i,above] -= np.floor((TP[i,above] - range_min)/360)*360  # try -360 phase wrap
            still_above = np.where(TP[i] > range_max)
            TP[i,still_above] = range_max
            unreachable[still_above] = True

        # centralize theta
        T_ctr = np.mean(ranges[0])
        T_best = TP[0].copy()
        for i in range(len(TP[0])):
            T_try = np.linspace(TP[0][i],T_ctr,n_theta_centralizing_iters,True).tolist()
            P_try = [TP[1][i]]*len(T_try)
            xy_try = PosTransforms.tp2xy([T_try,P_try],r)
            x_err = np.array(xy_try[0]) - X[i]
            y_err = np.array(xy_try[1]) - Y[i]
            xy_err = (x_err**2 + y_err**2)**0.5
            sort = np.argsort(xy_err)
            xy_err = xy_err[sort]
            for j in range(len(xy_err)-1,0,-1):
                if xy_err[j] <= theta_centralizing_err_tol:
                    T_best[i] = T_try[sort[j]]
                    break
        TP[0] = T_best

        # return
        tp = TP.tolist()
        unreachable = np.where(unreachable)[0].tolist()
        return tp, unreachable

    @staticmethod
    def vector_delta(uv1,uv0):
        """Generic vector difference uv1 - uv0."""
        (uv0, was_not_list0) = pc.listify(uv0)
        (uv1, was_not_list1) = pc.listify(uv1)
        uv2 = (np.array(uv1) - np.array(uv0)).tolist()
        if was_not_list0 or was_not_list1:
            uv2 = pc.delistify(uv2)
        return uv2

    @staticmethod
    def vector_add(uv0,uv1):
        """Generic vector addition uv0 + uv1."""
        (uv0, was_not_list0) = pc.listify(uv0)
        (uv1, was_not_list1) = pc.listify(uv1)
        uv2 = (np.array(uv0) + np.array(uv1)).tolist()
        if was_not_list0 or was_not_list1:
            uv2 = pc.delistify(uv2)
        return uv2