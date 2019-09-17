import sys
import math
import posconstants as pc
import posmodel
import petaltransforms


class PosTransforms(petaltransforms.PetalTransforms):
    """
    This class provides transformations between positioner coordinate systems.
    Requires an input instance of PetalTransforms() to provide support for
    legacy method calls.
    All coordinate transforms must be done via the methods provided here.
    This ensures consistent and invertible definitions.

    An instance of PosTransforms is associated with a particular instance of
    PosModel, so that the transforms will automatically draw on the correct
    calibration parameters for that particular positioner.

    The coordinate systems are:

        posintTP:   internally-tracked expected (theta, phi) of gearmotor
                    shafts at output of gear heads, pos origin
                    theta offset depends on the individual rotation of
                    positioner when installed formerly posTP

        poslocTP:   (theta, phi) in the petal local CS with pos origin
                    (centred on theta axis) renamed, does not exist before

        poslocXY:   (x, y) in the petal local CS with pos origin
                    (centered on theta axis), directly corresponds to posTP

        ptlXY:      (x, y) position in petal local CS as defined in petal CAD
                    petal origin

        obsXY:      2D projection of obsXYZ in CS5 defined in PetalTransforms
                    CS5 origin

        posobsXY:   (x, y) in global CS5 with pos origin (centred on theta)
                    formerly posXY

        posobsTP:   (T, P) in global CS5 with pos origin (centred on theta)
                    formerly obsTP

    The fundamental transformations provided are:

        posintTP        <--> poslocTP
        poslocTP        <--> ptlXY
        ptlXY           <--> obsXY    (from PetalTransforms)
        obsXY           <--> QS       (from PetalTransforms)
        flatXY          <--> QS       (from PetalTransforms)
        obsXY           <--> posobsXY

    Composite transformations are provided for convenience:

        degree 1:
            posintTP    <--> poslocXY
        degree 2:
            poslocXY    <--> obsXY
            obsXY       <--> flatXY
            QS           --> ptlXY
        degree 3:
            posintTP    <--> obsXY
        degree 4:
            intTP       <--> QS
        degree 5:
            intTP       <--> flatXY

    These can be chained together in any order to convert among the various
    coordinate systems.

    The theta axis has a physical travel range wider than +/-180 degrees.
    Simple vector addition and subtraction is not sufficient when delta values
    cross the theta hardstop near +/-180. Therefore special methods are
    provided for performing addition and subtraction operations between two
    points, with angle-wrapping logic included.

        delta_posTP  ... is like dtdp = tp1 - tp0
        delta_obsTP
        addto_posTP  ... is like tp1 = tp0 + dtdtp
        addto_obsTP

    To round out the syntax, similar delta_ and addto_ methods are provided for
    the other coordinate systems. These are convenicence methods to do the
    vector subtraction or addition.

    Note in practice that the coordinate S is similar, but not identical, to
    the radial distance R from the optical axis. This similarity is because the
    DESI focal plate curvature is gentle. See DESI-0530 for detail on the (Q,S)
    coordinate system.


    """

    def __init__(self, this_posmodel=None, petal_alignment=None):
        if petal_alignment is None:
            petal_alignment = {'Tx': 0, 'Ty': 0, 'Tz': 0,
                               'alpha': 0, 'beta': 0, 'gamma': 0}
        super().__init__(Tx=petal_alignment['Tx'],
                         Ty=petal_alignment['Ty'],
                         Tz=petal_alignment['Tz'],
                         alpha=petal_alignment['alpha'],
                         beta=petal_alignment['beta'],
                         gamma=petal_alignment['gamma'], curved=True)
        if this_posmodel is None:
            this_posmodel = posmodel.PosModel()
        self.posmodel = this_posmodel
        # allow alternate calibration values to temporarily override DB
        self.alt_override = False
        self.alt = {'LENGTH_R1': 3.0,
                    'LENGTH_R2': 3.0,
                    'OFFSET_X': 0.0,
                    'OFFSET_Y': 0.0,
                    'OFFSET_T': 0.0,
                    'OFFSET_P': 0.0}
        self.getval = lambda varname: (  # varname is a string
            self.alt[varname] if self.alt_override
            else self.posmodel.state._val[varname])

    # SHAFT RANGES
    def shaft_ranges(self, range_limits):
        """
        Returns a set of range limits for the theta and phi axes. The argument
        range_limits is a string:
            'full':         means from hardstop-to-hardstop
            'targetable':   restricts range by excluding the debounce and
                            backlash clearance zones near the hardstops
            'exact':        means theta range of [-179.999999999,180] and phi
                            range of [0,180]
        """
        if range_limits == 'full':
            return [self.posmodel.full_range_T, self.posmodel.full_range_P]
        elif range_limits == 'targetable':
            return [self.posmodel.targetable_range_T,
                    self.posmodel.targetable_range_P]
        elif range_limits == 'exact':
            return [[-179.999999999, 180.0], [0.0, 180.0]]
        else:
            print(f'bad range_limits argument: {range_limits}')
            return None

    # %% FUNDAMENTAL TRANSFORMATIONS between different CS
    def posintTP_to_poslocTP(self, posintTP):
        """
        input:  list or tuple of internally-tracked expected position of
                gearmotor shafts at output of gear heads
        output: (posT, posP) expected position of fiber tip including offsets
                and calibrations in petal local CS
        """
        poslocT = posintTP[0] + self.getval('OFFSET_T')
        poslocP = posintTP[1] + self.getval('OFFSET_P')
        return poslocT, poslocP

    def poslocTP_to_posintTP(self, poslocTP):
        """
        input:  list or tuple of expected position of fiber tip including
                offsets and calibrations in petal local CS
        output: (intT, intP) internally-tracked expected position of
                gearmotor shafts at output of gear heads
        """
        posintT = poslocTP[0] - self.getval('OFFSET_T')
        posintP = poslocTP[1] - self.getval('OFFSET_P')
        return posintT, posintP

    def poslocXY_to_ptlXY(self, poslocXY):
        ''' input is list or tuple or 1D array '''
        ptlX = poslocXY[0] + self.getval('OFFSET_X')
        ptlY = poslocXY[1] + self.getval('OFFSET_Y')
        return ptlX, ptlY

    def ptlXY_to_poslocXY(self, ptlXY):
        ''' input is list or tuple or 1D array '''
        poslocX = ptlXY[0] - self.getval('OFFSET_X')
        poslocY = ptlXY[1] - self.getval('OFFSET_Y')
        return poslocX, poslocY

    def obsXY_to_posobsXY(self, obsXY):
        ''' input is list or tuple or 1D array '''
        centre_ptlXY = [self.getval('OFFSET_X'), self.getval('OFFSET_Y')]
        centre_obsXY = self.ptlXY_to_obsXY(centre_ptlXY, cast=True).flatten()
        return self.delta_XY(obsXY, centre_obsXY)

    def posobsXY_to_obsXY(self, posobsXY):
        ''' input is list or tuple or 1D array '''
        centre_ptlXY = [self.getval('OFFSET_X'), self.getval('OFFSET_Y')]
        centre_obsXY = self.ptlXY_to_obsXY(centre_ptlXY, cast=True)
        return self.addto_XY(posobsXY, centre_obsXY)

    # %% fundamental XY and TP conversion in the same positioner-centred CS
    def poslocTP_to_poslocXY(self, poslocTP):
        ''' input is list or tuple or 1D array '''
        r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
        return PosTransforms.tp2xy(poslocTP, r)  # return (poslocX, poslocY)

    def poslocXY_to_poslocTP(self, poslocXY, range_limits='full'):
        ''' input is list or tuple or 1D array '''
        posintT_range, posintP_range = self.shaft_ranges(range_limits)
        poslocTP_min = self.posintTP_to_poslocTP(
            [posintT_range[0], posintT_range[0]])
        poslocTP_max = self.posintTP_to_poslocTP(
            [posintP_range[1], posintP_range[1]])
        posloc_ranges = [[poslocTP_min[0], poslocTP_max[0]],  # T min, T max
                         [poslocTP_min[1], poslocTP_max[1]]]  # P min, P max
        r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
        return PosTransforms.xy2tp(poslocXY, r, posloc_ranges)

    def posobsTP_to_posobsXY(self, posobsTP):
        ''' input is list or tuple or 1D array '''
        r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
        return PosTransforms.tp2xy(posobsTP, r)  # return (posobsX, posobsY)

    def posobsXY_to_posobsTP(self, posobsXY, range_limits='full'):
        ''' input is list or tuple or 1D array '''
        r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
        posobs_ranges = [[0, 359.99999999], [0, 220]]
        return PosTransforms.xy2tp(posobsXY, r, posobs_ranges)[0]

    # %% composite transformations for convenience (degree 1)
    def posintTP_to_poslocXY(self, posintTP):
        ''' input is list or tuple '''
        poslocTP = self.posintTP_to_poslocTP(posintTP)
        return self.poslocTP_to_poslocXY(poslocTP)  # tuple

    def poslocXY_to_posintTP(self, poslocXY, range_limits='full'):
        ''' input is list or tuple '''
        poslocTP, unreachable = self.poslocXY_to_poslocTP(
            poslocXY, range_limits=range_limits)
        return self.poslocTP_to_posintTP(poslocTP), unreachable  # tuple

    # %% composite transformations for convenience (degree 2)
    def poslocXY_to_obsXY(self, poslocXY):
        ''' input is list or tuple '''
        ptlXY = self.poslocXY_to_ptlXY(poslocXY)  # tuple
        obsXY = self.ptlXY_to_obsXY(ptlXY, cast=True).flatten()  # 1D arr
        return tuple(obsXY)

    def obsXY_to_poslocXY(self, obsXY):
        ''' input is list or tuple '''
        ptlXY = self.obsXY_to_ptlXY(obsXY, cast=True).flatten()  # 1D arr
        return self.ptlXY_to_poslocXY(ptlXY)  # return (posX, posY)

    def ptlXY_to_posintTP(self, ptlXY):
        ''' input is list or tuple '''
        poslocXY = self.ptlXY_to_poslocXY(ptlXY)
        return self.poslocXY_to_posintTP(poslocXY)

    def posintTP_to_ptlXY(self, posintTP):
        ''' input is list or tuple '''
        poslocXY = self.posintTP_to_poslocXY(posintTP)
        return self.poslocXY_to_ptlXY(poslocXY)

    def QS_to_ptlXY(self, QS):
        ''' input is list or tuple '''
        obsXY = self.QS_to_obsXY(QS)
        return self.obsXY_to_ptlXY(obsXY)

    # %% composite transformations for convenience (degree 3)
    def posintTP_to_obsXY(self, posintTP):
        poslocXY = self.posintTP_to_poslocXY(posintTP)  # tuple
        return self.poslocXY_to_obsXY(poslocXY)  # return (obsX, obsY)

    def obsXY_to_posintTP(self, obsXY, range_limits='full'):
        """Composite transformation, performs obsXY --> posXY --> intTP"""
        poslocXY = self.obsXY_to_poslocXY(obsXY)  # tuple
        return self.poslocXY_to_posintTP(poslocXY, range_limits=range_limits)

    # %% composite transformations for convenience (degree 4)
    def posintTP_to_QS(self, posintTP):
        """Composite transformation, performs intTP --> obsXY --> QS"""
        obsXY = self.posintTP_to_obsXY(posintTP)  # tuple (obsX, obsY)
        QS = self.obsXY_to_QS(obsXY, cast=True).flatten()  # 1D array
        return tuple(QS)

    def QS_to_posintTP(self, QS, range_limits='full'):
        """Composite transformation, performs QS --> obsXY --> intTP"""
        obsXY = self.QS_to_obsXY(QS, cast=True)  # 1D array
        return self.obsXY_to_posintTP(obsXY, range_limits)  # tp, unreachable

    def posintTP_to_posobsXY(self, posintTP):
        obsXY = self.posintTP_to_obsXY(posintTP)
        return tuple(self.obsXY_to_posobsXY(obsXY))  # tuple

    # %% composite transformations for convenience (degree 5)
    def posintTP_to_flatXY(self, posintTP):
        """Composite transformation, performs intTP --> QS --> flatXY"""
        QS = self.posintTP_to_QS(posintTP)
        flatXY = self.QS_to_flatXY(QS, cast=True).flatten()  # 1D array
        return tuple(flatXY)

    def flatXY_to_posintTP(self, flatXY, range_limits='full'):
        """Composite transformation, performs flatXY --> QS --> intTP"""
        QS = self.flatXY_to_QS(flatXY, cast=True)
        return self.QS_to_posintTP(QS, range_limits)  # (tp, unreachable)

    # %% angle additions and subtractions

    def addto_posintTP(self, posintTP0, dtdp, range_wrap_limits='full'):
        """Returns tp corresponding to tp0 + dtdp.
        The range_wrap_limits option can be any of the values for the
        shaft_ranges method, or 'none'. If 'none', then the returned point is
        a simple vector addition with no special checks for angle-wrapping
        across positioner's theta = +/-180 deg.
        """
        if range_wrap_limits != 'none':
            posintT_range = self.shaft_ranges(range_wrap_limits)[pc.T]
            dtdp = PosTransforms._wrap_theta(posintTP0, dtdp, posintT_range)
        return PosTransforms.vector_add(posintTP0, dtdp)

    def delta_posintTP(self, posintTP0, posintTP1, range_wrap_limits='full'):
        """Returns dtdp corresponding to tp0 - tp1, or final - initial
        The range_wrap_limits option can be any of the values for the
        shaft_ranges method, or 'none'. If 'none', then the returned delta is
        a simple vector subtraction with no special checks for angle-wrapping
        across positioner's theta = +/-180 deg.
        """
        dtdp = PosTransforms.vector_delta(posintTP0, posintTP1)
        if range_wrap_limits != 'none':
            posintT_range = self.shaft_ranges(range_wrap_limits)[pc.T]
            dtdp = PosTransforms._wrap_theta(posintTP1, dtdp, posintT_range)
        return dtdp

    def addto_poslocTP(self, poslocTP0, dtdp, range_wrap_limits='full'):
        """Returns tp corresponding to tp0 + dtdp.
        The range_wrap_limits option can be any of the values for the
        shaft_ranges method, or 'none'. If 'none', then the returned point is
        a simple vector addition with no special checks for angle-wrapping
        across positioner's theta = +/-180 deg.
        """
        posintTP0 = self.poslocTP_to_posintTP(poslocTP0)
        posintTP1 = self.addto_posintTP(posintTP0, dtdp, range_wrap_limits)
        return self.posintTP_to_poslocTP(posintTP1)  # return tuple coords

    def delta_poslocTP(self, poslocTP0, poslocTP1, range_wrap_limits='full'):
        """Returns dtdp corresponding to tp0 - tp1.
        The range_wrap_limits option can be any of the values for the
        shaft_ranges method, or 'none'. If 'none', then the returned delta is
        a simple vector subtraction with no special checks for angle-wrapping
        across positioner's theta = +/-180 deg.
        """
        posintTP0 = self.poslocTP_to_posintTP(poslocTP0)
        posintTP1 = self.poslocTP_to_posintTP(poslocTP1)
        return self.delta_posintTP(posintTP0, posintTP1, range_wrap_limits)

    # %% STATIC INTERNAL METHODS
    @staticmethod
    def vector_delta(uv0, uv1):
        """Generic vector difference uv0 - uv1."""
        return [uv0[0] - uv1[0], uv0[1] - uv1[1]]

    @staticmethod
    def vector_add(uv0, uv1):
        """Generic vector addition uv0 + uv1."""
        return [uv0[0] + uv1[0], uv0[1] + uv1[1]]

    @staticmethod
    def addto_XY(xy0, dxdy):
        """Returns xy corresponding to xy0 + dxdy."""
        return PosTransforms.vector_add(xy0, dxdy)

    @staticmethod
    def addto_QS(qs0, dqds):
        """Returns qs corresponding to qs0 + dqds."""
        return PosTransforms.vector_add(qs0, dqds)

    @staticmethod
    def delta_XY(xy0, xy1):
        """Returns dxdy corresponding to xy0 - xy1."""
        return PosTransforms.vector_delta(xy0, xy1)

    @staticmethod
    def delta_QS(qs0, qs1):
        """Returns dqds corresponding to qs0 - qs1."""
        return PosTransforms.vector_delta(qs0, qs1)

    @staticmethod
    def _wrap_theta(tp0, dtdp, posintT_range):
        """
        tp0             : initial TP positions
        dtdp            : delta TP movement
        posintT_range   : allowed range of internal theta, tuple or list

        Returns a modified dtdp after appropriately wrapping the delta theta
        to not cross a physical hardstop. Phi angle is untouched.
        """
        ti, dt, dp = tp0[0], dtdp[0], dtdp[1]  # t initial, dt, dp
        wrapped_dt = dt - 360*pc.sign(dt)
        tf = ti + dt
        wrapped_tf = ti + wrapped_dt
        if min(posintT_range) <= wrapped_tf <= max(posintT_range):
            if ((min(posintT_range) > tf or max(posintT_range) < tf)
                    or abs(wrapped_dt) < abs(dt)):
                dt = wrapped_dt
        return dt, dp

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
        return x, y

    @staticmethod
    def xy2tp(xy, r, ranges):
        """Converts XY cartesian coordinates into TP angles, where arm lengths
         associated with angles theta and phi are respectively r[1] and r[2].

        INPUTS:   xy ... [x,y]
                   r ... [central arm length, eccentric arm length]
              ranges ... [[min(theta), max(theta)], [min(phi), max(phi)]]

        OUTPUTS:  tp ... [theta,phi], unit degrees
         unreachable ... boolean, True if the requested xy cannot be reached
                         by any tp

        In cases where unreachable == True, the returned tp value will be a
        closest possible approach to the unreachable point requested at xy.
        """
        # within this much xy error allowance, adjust theta toward center
        # of its range
        theta_centralizing_err_tol = 1e-4
        # number of points to try when attempting to centralize theta
        n_theta_centralizing_iters = 3
        # slight contraction to avoid numeric divide-by-zero type of errors
        numeric_contraction = sys.float_info.epsilon*10
        x, y, r1, r2 = xy[0], xy[1], r[0], r[1]
        unreachable = False
        # adjust targets within reachable annulus
        hypot = (x**2.0 + y**2.0)**0.5
        angle = math.atan2(y, x)
        outer = r[0] + r[1]
        inner = abs(r[0] - r[1])
        if hypot > outer or hypot < inner:
            unreachable = True
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
        arccos_arg = (X**2.0 + Y**2.0 - (r1**2.0 + r2**2.0)) / (2.0 * r1 * r2)
        # deal with slight numeric errors where arccos_arg comes back
        # like -1.0000000000000002
        arccos_arg = max(arccos_arg, -1.0)
        # deal with slight numeric errors where arccos_arg comes back
        # like +1.0000000000000002
        arccos_arg = min(arccos_arg, +1.0)
        P = math.acos(arccos_arg)
        T = angle - math.atan2(r2*math.sin(P), r1 + r2*math.cos(P))
        TP = [math.degrees(T), math.degrees(P)]
        # wrap angles into travel ranges
        for i in [0, 1]:
            range_min, range_max = min(ranges[i]), max(ranges[i])
            if TP[i] < range_min:
                # try +360 phase wrap
                TP[i] += math.floor((range_max - TP[i])/360.0)*360.0
                if TP[i] < range_min:
                    # print(f'TP {i}, {TP[i]} < range_min: {range_min}'
                    #       f'thus unreachable\n{ranges[i]}')
                    TP[i] = range_min
                    unreachable = True
            elif TP[i] > range_max:
                # try -360 phase wrap
                TP[i] -= math.floor((TP[i] - range_min)/360.0)*360.0
                if TP[i] > range_max:
                    # print(f'TP {i}, {TP[i]} > range_max: {range_max}'
                    #       f'thus unreachable\n{ranges[i]}')
                    TP[i] = range_max
                    unreachable = True
        # centralize theta
        T_ctr = (ranges[0][0] + ranges[0][1])/2.0
        T_options = pc.linspace(TP[0], T_ctr, n_theta_centralizing_iters)
        for T_try in T_options:
            xy_try = PosTransforms.tp2xy([T_try, TP[1]], r)
            x_err = xy_try[0] - X
            y_err = xy_try[1] - Y
            vector_err = (x_err**2.0 + y_err**2.0)**0.5
            if vector_err <= theta_centralizing_err_tol:
                TP[0] = T_try
                break
        return tuple(TP), unreachable


if __name__ == '__main__':
    '''
    try several gamma rotaion values here, e.g. 0, 36 deg, 180 deg
    '''
    petal_alignment = {'Tx': 0, 'Ty': 0, 'Tz': 0,
                       'alpha': 0, 'beta': 0, 'gamma': 36/180*math.pi}
    trans = PosTransforms(petal_alignment=petal_alignment)
    state = trans.posmodel.state
    state._val['OFFSET_X'], state._val['OFFSET_Y'] = 28.134375, 5.201437
    print(f'posstate values:\n{state._val}')
    poslocTP1 = trans.posintTP_to_poslocTP([0, 120])
    print(f'poslocTP1 = {poslocTP1}')
    posintTP1 = trans.poslocTP_to_posintTP(poslocTP1)
    print(f'posintTP1 = {posintTP1}')
    ptlXY = trans.poslocXY_to_ptlXY([1.5, 1.5*math.sqrt(3)])
    print(f'ptlXY = {ptlXY}')
    poslocXY1 = trans.ptlXY_to_poslocXY(ptlXY)
    print(f'poslocXY1 = {poslocXY1}')
    poslocXY2 = trans.poslocTP_to_poslocXY(poslocTP1)
    print(f'poslocXY2 = {poslocXY2}')
    poslocTP2, unreachable = trans.poslocXY_to_poslocTP(poslocXY2)
    print(f'poslocTP2 = {poslocTP2}, unreachable: {unreachable}')
    poslocXY3 = trans.posintTP_to_poslocXY(posintTP1)
    print(f'poslocXY3 = {poslocXY3}')
    posintTP2, unreachable = trans.poslocXY_to_posintTP(poslocXY3)
    print(f'posintTP2 = {posintTP2}, unreachable: {unreachable}')
    obsXY1 = trans.poslocXY_to_obsXY(poslocXY3)
    print(f'obsXY1 = {obsXY1}')
    poslocXY4 = trans.obsXY_to_poslocXY(obsXY1)
    print(f'poslocXY4 = {poslocXY4}')
    obsXY2 = trans.posintTP_to_obsXY(posintTP2)
    print(f'obsXY2 = {obsXY2}')
    posintTP3, unreachable = trans.obsXY_to_posintTP(obsXY2)
    print(f'posintTP3 = {posintTP3}, unreachable: {unreachable}')
    QS = trans.posintTP_to_QS(posintTP2)
    print(f'QS = {QS}')
    posintTP4, unreachable = trans.QS_to_posintTP(QS)
    print(f'posintTP4 = {posintTP4}, unreachable: {unreachable}')
    flatXY1 = trans.posintTP_to_flatXY(posintTP3)
    print(f'flatXY1 = {flatXY1}')
    posintTP4, unreachable = trans.flatXY_to_posintTP(flatXY1)
    print(f'posintTP4 = {posintTP4}, unreachable: {unreachable}')
    poslocTP3 = trans.addto_poslocTP(poslocTP2, (200, 100))
    print(f'poslocTP3 = {poslocTP3}, unreachable: {unreachable}')
