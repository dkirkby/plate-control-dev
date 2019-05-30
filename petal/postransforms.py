import numpy as np
import posconstants as pc
import posmodel
import math
import sys


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
        QS     ... (q,s) global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis. this is for observer perspective only and there is no positioner local counterpart
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
    
    The option "curved" sets whether we are looking at a flat focal plane (such as a laboratory
    test stand), or a true petal, with its asphere. When curved == False, PosTransforms will
    treat S as exactly equal to the radius R.
    """

    def __init__(self, this_posmodel=None, curved=True):
        if this_posmodel is None:
            this_posmodel = posmodel.PosModel()
        self.posmodel = this_posmodel
        self.curved = curved
        self.alt_override = False  # alternate calibration values one can set, so one can temporarily override whatever the positioner's stored vals are
        self.alt = {'LENGTH_R1' : 3.0,
                    'LENGTH_R2' : 3.0,
                    'OFFSET_X'  : 0.0,
                    'OFFSET_Y'  : 0.0,
                    'OFFSET_T'  : 0.0,
                    'OFFSET_P'  : 0.0}
        self.getval = lambda varname: (  # varname is a string
            self.alt[varname] if self.alt_override
            else self.posmodel.state.read(varname))

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
            return [[-179.999999999,180.0],[0.0,180.0]]
        else:
            print('bad range_limits argument "' + str(range_limits) + '"')
            return None

    # FUNDAMENTAL TRANSFORMATIONS
    def obsTP_to_posTP(self, tp):
        """
        input:  tp ... [obsT,obsP] expected position of fiber tip, including offsets and calibrations
        output: TP ... [posT,posP] internally-tracked expected position of gearmotor shafts at output of gear heads
        """
        T = tp[0] - self.getval('OFFSET_T')
        P = tp[1] - self.getval('OFFSET_P')
        return [T, P]

    def posTP_to_obsTP(self, tp):
        """
        input:  tp ... [posT,posP] internally-tracked expected position of gearmotor shafts at output of gear heads
        output: TP ... [obsT,obsP] expected position of fiber tip, including offsets and calibrations
        """
        T = tp[0] + self.getval('OFFSET_T')
        P = tp[1] + self.getval('OFFSET_P')
        return [T, P]

    def posTP_to_posXY(self, tp):
        """
        input:  tp ... [posT,posP] internally-tracked expected position of gearmotor shafts at output of gear heads
        output: xy ... [posX,posY] global to focal plate, centered on optical axis, looking at fiber tips
        """
        r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
        TP = self.posTP_to_obsTP(tp)  # adjust shaft angles into observer space (since observer sees the physical phi = 0)
        xy = self.tp2xy(TP, r)         # calculate xy in posXY space
        return xy

    def posXY_to_posTP(self, xy, range_limits='full'):
        """
        input:  xy ... [posX,posY] global to focal plate, centered on optical axis, looking at fiber tips
        output: TP ... [posT,posP) internally-tracked expected position of gearmotor shafts at output of gear heads
        
        input:  range_limits ... (optional) string, see shaft_ranges method
        output: unreachable  ... boolean, True if no posTP exists that can achieve the requested posXY
        """
        r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
        shaft_ranges = self.shaft_ranges(range_limits)
        obs_range_tptp = [self.posTP_to_obsTP([shaft_ranges[0][0],shaft_ranges[1][0]]), self.posTP_to_obsTP([shaft_ranges[0][1],shaft_ranges[1][1]])] # want range used in next line to be according to observer (since observer sees the physical phi = 0)
        obs_range=[[obs_range_tptp[0][0],obs_range_tptp[1][0]],[obs_range_tptp[0][1],obs_range_tptp[1][1]]]
        (tp, unreachable) = self.xy2tp(xy,r,obs_range)
        TP = self.obsTP_to_posTP(tp) # adjust angles back into shaft space
        return TP, unreachable

    def posXY_to_obsXY(self, xy):
        """
        input:  xy ... [posX,posY] local to fiber positioner, centered on theta axis, looking at fiber tip
        output: XY ... [obsX,obsY] global to focal plate, centered on optical axis, looking at fiber tips
        """        
        X = xy[0] + self.getval('OFFSET_X')
        Y = xy[1] + self.getval('OFFSET_Y')
        return [X, Y]

    def obsXY_to_posXY(self, xy):
        """
        input:  xy ... [obsX,obsY] global to focal plate, centered on optical axis, looking at fiber tips
        output: XY ... [posX,posY] local to fiber positioner, centered on theta axis, looking at fiber tip
        """
        X = xy[0] - self.getval('OFFSET_X')
        Y = xy[1] - self.getval('OFFSET_Y')
        return [X, Y]

    def obsXY_to_QS(self, xy):
        """
        input:  xy ... [obsX,obsY] global to focal plate, centered on optical axis, looking at fiber tips
        output: QS ... [Q,S] global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        """
        Q = math.degrees(math.atan2(xy[1],xy[0]))
        R = (xy[0]**2.0 + xy[1]**2.0)**0.5
        S = self.R2S(R) if self.curved else R
        return [Q,S]

    def QS_to_obsXY(self, qs):
        """
        input:  qs ... [Q,S] global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        output: XY ... [obsX,obsY] global to focal plate, centered on optical axis, looking at fiber tips
        """
        Q_rad = math.radians(qs[0])
        R = self.S2R(qs[1]) if self.curved else qs[1]
        X = R * math.cos(Q_rad)
        Y = R * math.sin(Q_rad)
        return [X,Y]

    @staticmethod
    def QS_to_flatXY(qs):
        """
        input:  qs ... [Q,S] global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        output: XY ... [flatX,flatY] global to focal plate, with focal plate slightly stretched out and flattened (used for anti-collision)
        """
        Q_rad = math.radians(qs[0])
        X = qs[1] * math.cos(Q_rad)
        Y = qs[1] * math.sin(Q_rad)
        return [X,Y]

    @staticmethod
    def flatXY_to_QS(xy):
        """
        input:  xy ... [flatX,flatY] global to focal plate, with focal plate slightly stretched out and flattened (used for anti-collision)
        output: QS ... [Q,S] global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        """
        Q = math.degrees(math.atan2(xy[1],xy[0]))
        S = (xy[0]**2.0 + xy[1]**2.0)**0.5
        return [Q,S]

    # COMPOSITE TRANSFORMATIONS
    def posTP_to_obsXY(self, tp):
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
    def delta_posXY(xy1, xy0):
        """Returns dxdy corresponding to xy1 - xy0."""
        return PosTransforms.vector_delta(xy1,xy0)

    def delta_obsXY(xy1, xy0):
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
            dtdp = self._wrap_theta(tp0,dtdp,range_wrap_limits)
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

    def delta_QS(qs1, qs0):
        """Returns dqds corresponding to qs1 - qs0."""
        return PosTransforms.vector_delta(qs1,qs0)

    def delta_flatXY(xy0, xy1):
        """Returns dxdy corresponding to xy1 - xy0."""
        return PosTransforms.vector_delta(xy1,xy0)

    # ADDITION METHODS
    def addto_posXY(xy0, dxdy):
        """Returns xy corresponding to xy0 + dxdy."""
        return PosTransforms.vector_add(xy0,dxdy)

    def addto_obsXY(xy0, dxdy):
        """Returns xy corresponding to xy0 + dxdy."""
        return PosTransforms.vector_add(xy0,dxdy)

    def addto_posTP(self, tp0, dtdp, range_wrap_limits='full'):
        """Returns tp corresponding to tp0 + dtdp.
        The range_wrap_limits option can be any of the values for the shaft_ranges
        method, or 'none'. If 'none', then the returned point is a simple vector addition
        with no special checks for angle-wrapping across positioner's theta = +/-180 deg.
        """
        if range_wrap_limits != 'none':
            dtdp = self._wrap_theta(tp0,dtdp,range_wrap_limits)
        return PosTransforms.vector_add(tp0,dtdp)

    def addto_obsTP(self, tp0, dtdp, range_wrap_limits='full'):
        """Returns tp corresponding to tp0 + dtdp.
        The range_wrap_limits option can be any of the values for the shaft_ranges
        method, or 'none'. If 'none', then the returned point is a simple vector addition
        with no special checks for angle-wrapping across positioner's theta = +/-180 deg.
        """
        TP0 = self.obsTP_to_posTP(tp0)
        return self.addto_posTP(TP0,dtdp,range_wrap_limits)

    def addto_QS(qs0, dqds):
        """Returns qs corresponding to qs0 + dqds."""
        return PosTransforms.vector_add(qs0,dqds)

    def addto_flatXY(xy0, dxdy):
        """Returns xy corresponding to xy0 + dxdy."""
        return PosTransforms.vector_add(xy0,dxdy)

    # INTERNAL METHODS
    def _wrap_theta(self,tp0,dtdp,range_wrap_limits='full'):
        """Returns a modified dtdp after appropriately wrapping the delta theta
        to not cross a physical hardstop. The range_wrap_limits option can be any
        of the values for the shaft_ranges method.
        """
        dt = dtdp[0]
        t = tp0[0] + dt
        wrapped_dt = dt - 360*pc.sign(dt)
        wrapped_t = tp0[0] + wrapped_dt
        t_range = self.shaft_ranges(range_wrap_limits)[pc.T]
        if min(t_range) <= wrapped_t <= max(t_range):
            if (min(t_range) > t or max(t_range) < t) or abs(wrapped_dt) < abs(dt):
                dtdp[0] = wrapped_dt
        return dtdp

    # STATIC INTERNAL METHODS
    @staticmethod
    def R2S(r):
        """Uses focal surface definition of DESI-0530 to convert R coordinate to S.
        """
        return pc.R2S_lookup(r)

    @staticmethod
    def S2R(s):
        """Uses focal surface definition of DESI-0530 to convert S coordinate to R.
        """
        return pc.S2R_lookup(s)

    @staticmethod
    def tp2xy(tp, r):
        """Converts TP angles into XY cartesian coordinates, where arm lengths
        associated with angles theta and phi are respectively r[1] and r[2].

        INPUTS:  tp ... [theta,phi], unit degrees
                  r ... [central arm length, eccentric arm length]

        OUTPUT:  xy ... [x,y]
        """
        t = math.radians(tp[0])
        t_plus_p = t + math.radians(tp[1])
        x = r[0] * math.cos(t) + r[1] * math.cos(t_plus_p)
        y = r[0] * math.sin(t) + r[1] * math.sin(t_plus_p)
        return [x,y]

    @staticmethod
    def xy2tp(xy, r, ranges):
        """Converts XY cartesian coordinates into TP angles, where arm lengths
         associated with angles theta and phi are respectively r[1] and r[2].

        INPUTS:   xy ... [x,y]
                   r ... [central arm length, eccentric arm length]
              ranges ... [[min(theta), max(theta)], [min(phi), max(phi)]]
              
        OUTPUTS:  tp ... [theta,phi], unit degrees
         unreachable ... boolean, True if the requested xy cannot be reached by any tp
        
        In cases where unreachable == True, the returned tp value will be a closest
        possible approach to the unreachable point requested at xy.
        """
        theta_centralizing_err_tol = 1e-4 # within this much xy error allowance, adjust theta toward center of its range
        n_theta_centralizing_iters = 3    # number of points to try when attempting to centralize theta
        numeric_contraction = sys.float_info.epsilon*10 # slight contraction to avoid numeric divide-by-zero type of errors
        x = xy[0]
        y = xy[1]
        unreachable = False
        # adjust targets within reachable annulus
        hypot = (x**2.0 + y**2.0)**0.5
        angle = math.atan2(y,x)
        outer = r[0] + r[1]
        inner = abs(r[0] - r[1])
        if hypot > outer or hypot < inner:
            unreachable = True
            # print('Target is outside of reachable regions')
        inner += numeric_contraction
        outer -= numeric_contraction
        HYPOT = hypot
        if hypot >= outer:
            HYPOT = outer
        elif hypot <= inner:
            HYPOT = inner
        X = HYPOT*math.cos(angle)
        Y = HYPOT*math.sin(angle)

        # transfrom from cartesian XY to angles TP
        arccos_arg = (X**2.0 + Y**2.0 - (r[0]**2.0 + r[1]**2.0)) / (2.0 * r[0] * r[1])
        arccos_arg = max(arccos_arg, -1.0) # deal with slight numeric errors where arccos_arg comes back like -1.0000000000000002
        arccos_arg = min(arccos_arg, +1.0) # deal with slight numeric errors where arccos_arg comes back like +1.0000000000000002
        P = math.acos(arccos_arg)

        T = angle - math.atan2(r[1]*math.sin(P),r[0]+r[1]*math.cos(P)) 
        TP = [math.degrees(T), math.degrees(P)]

        # wrap angles into travel ranges
        for i in [0,1]:
            range_min = min(ranges[i])
            range_max = max(ranges[i])
            if TP[i] < range_min:
                TP[i] += math.floor((range_max - TP[i])/360.0)*360.0  # try +360 phase wrap
                if TP[i] < range_min:
                    # print('TP',i,TP[i],' < range_min:',range_min,' thus unreachable')
                    # print('ranges[i]',ranges[i])
                    TP[i] = range_min
                    unreachable = True
            elif TP[i] > range_max:
                TP[i] -= np.floor((TP[i] - range_min)/360.0)*360.0  # try -360 phase wrap
                if TP[i] > range_max:
                    # print('TP ',i,TP[i],'> range_max:',range_max,' thus unreachable')
                    # print('ranges[i]',ranges[i])
                    TP[i] = range_max
                    unreachable = True
        # centralize theta
        T_ctr = (ranges[0][0] + ranges[0][1])/2.0
        T_options = pc.linspace(TP[0], T_ctr, n_theta_centralizing_iters)
        for T_try in T_options:
            xy_try = PosTransforms.tp2xy([T_try,TP[1]], r)
            x_err = xy_try[0] - X
            y_err = xy_try[1] - Y
            vector_err = (x_err**2.0 + y_err**2.0)**0.5
            if vector_err <= theta_centralizing_err_tol:
                TP[0] = T_try
                break
            
        return TP, unreachable

    @staticmethod
    def vector_delta(uv1,uv0):
        """Generic vector difference uv1 - uv0."""
        return [uv1[0] - uv0[0], uv1[1] - uv0[1]]

    @staticmethod
    def vector_add(uv0,uv1):
        """Generic vector addition uv0 + uv1."""
        return [uv0[0] + uv1[0], uv0[1] + uv1[1]]
