import sys
import math
import posconstants as pc
import posmodel
import petaltransforms


class PosTransforms(petaltransforms.PetalTransforms):
    """
    see diagram in the following google doc
    https://docs.google.com/document/d/1KBLyRw8DyeUMA9c8i_vdzjJlU2PSyV-cyPTdKV86HlA/

    This class provides transformations between positioner coordinate systems.
    Requires an input instance of PetalTransforms() to provide support for
    legacy method calls.
    All coordinate transforms must be done via the methods provided here.
    This ensures consistent and invertible definitions.

    An instance of PosTransforms is associated with a particular instance of
    PosModel, so that the transforms will automatically draw on the correct
    calibration parameters for that particular positioner.

    The coordinate systems are (except those inherited from PetalTransforms)

        posintTP:   internally-tracked expected (theta, phi) of gearmotor
                    shafts at output of gear heads, pos origin
                    theta offset depends on the individual rotation of
                    positioner when installed formerly posTP

        poslocTP:   (theta, phi) in the positioner local CS, aligned with
                    petal flatXY, centred on theta axis

        poslocXY:   (x, y) in the positioner local CS, aligned with
                    petal flatXY, centred on theta axis

        flatXY:     (x, y) in the petal local flat CS on the focal surface

    The fundamental transformations provided are:

        posintTP        <--> poslocTP
        poslocXY        <--> flatXY   (within petal local CS)

    Composite transformations are provided for convenience:

        degree 1:
            posintTP    <--> poslocXY
        degree 3:
            posintTP    <--> flatXY
        degree 4:
            posintTP    <--> QS

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

    # %% FUNDAMENTAL TRANSFORMATIONS between different CS (offsets definitions)
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

    def poslocXY_to_flatXY(self, poslocXY):
        ''' input is list or tuple or 1D array '''
        flatX = poslocXY[0] + self.getval('OFFSET_X')
        flatY = poslocXY[1] + self.getval('OFFSET_Y')
        return flatX, flatY

    def flatXY_to_poslocXY(self, flatXY):
        ''' input is list or tuple or 1D array '''
        poslocX = flatXY[0] - self.getval('OFFSET_X')
        poslocY = flatXY[1] - self.getval('OFFSET_Y')
        return poslocX, poslocY

    # def obsXY_to_posobsXY(self, obsXY):
    #     ''' input is list or tuple or 1D array '''
    #     centre_ptlXY = [self.getval('OFFSET_X'), self.getval('OFFSET_Y')]
    #     centre_obsXY = self.ptlXY_to_obsXY(centre_ptlXY, cast=True).flatten()
    #     return self.delta_XY(obsXY, centre_obsXY)

    # def posobsXY_to_obsXY(self, posobsXY):
    #     ''' input is list or tuple or 1D array '''
    #     centre_ptlXY = [self.getval('OFFSET_X'), self.getval('OFFSET_Y')]
    #     centre_obsXY = self.ptlXY_to_obsXY(centre_ptlXY, cast=True)
    #     return self.addto_XY(posobsXY, centre_obsXY)

    # %% fundamental XY and TP conversion in the same positioner-centred CS
    def poslocTP_to_poslocXY(self, poslocTP):
        ''' input is list or tuple or 1D array '''
        r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
        return PosTransforms.tp2xy(poslocTP, r)  # return (poslocX, poslocY)

    def poslocXY_to_poslocTP(self, poslocXY, range_limits='full'):
        ''' input is list or tuple or 1D array '''
        posintT_range, posintP_range = self.shaft_ranges(range_limits)
        poslocTP_min = self.posintTP_to_poslocTP(
            [posintT_range[0], posintP_range[0]])
        poslocTP_max = self.posintTP_to_poslocTP(
            [posintT_range[1], posintP_range[1]])
        posloc_ranges = [[poslocTP_min[0], poslocTP_max[0]],  # T min, T max
                         [poslocTP_min[1], poslocTP_max[1]]]  # P min, P max
        r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
        return PosTransforms.xy2tp(poslocXY, r, posloc_ranges)

    # def posobsTP_to_posobsXY(self, posobsTP):
    #     ''' input is list or tuple or 1D array '''
    #     r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
    #     return PosTransforms.tp2xy(posobsTP, r)  # return (posobsX, posobsY)

    # def posobsXY_to_posobsTP(self, posobsXY, range_limits='full'):
    #     ''' input is list or tuple or 1D array '''
    #     r = [self.getval('LENGTH_R1'), self.getval('LENGTH_R2')]
    #     posobs_ranges = [[0, 359.99999999], [0, 220]]
    #     return PosTransforms.xy2tp(posobsXY, r, posobs_ranges)[0]

    # %% composite transformations for convenience (degree 1)
    def posintTP_to_poslocXY(self, posintTP):
        ''' input is list or tuple '''
        poslocTP = self.posintTP_to_poslocTP(posintTP)
        return self.poslocTP_to_poslocXY(poslocTP)  # (poslocX, poslocY)

    def poslocXY_to_posintTP(self, poslocXY, range_limits='full'):
        ''' input is list or tuple '''
        poslocTP, unreachable = self.poslocXY_to_poslocTP(
            poslocXY, range_limits=range_limits)
        return self.poslocTP_to_posintTP(poslocTP), unreachable  # (t, p), unr

    # %% composite transformations for convenience (degree 2)
    # def poslocXY_to_obsXY(self, poslocXY):
    #     ''' input is list or tuple '''
    #     ptlXY = self.poslocXY_to_ptlXY(poslocXY)  # tuple
    #     obsXY = self.ptlXY_to_obsXY(ptlXY, cast=True).flatten()  # 1D arr
    #     return tuple(obsXY)  # (x, y)

    # def obsXY_to_poslocXY(self, obsXY):
    #     ''' input is list or tuple '''
    #     ptlXY = self.obsXY_to_ptlXY(obsXY, cast=True).flatten()  # 1D arr
    #     return self.ptlXY_to_poslocXY(ptlXY)  # return (poslocX, poslocY)

    def QS_to_poslocXY(self, QS):
        ''' input is list or tuple '''
        flatXY = self.QS_to_flatXY(QS, cast=True).flatten()
        return self.flatXY_to_poslocXY(flatXY)  # (poslocX, poslocY)

    def poslocXY_to_QS(self, poslocXY):
        ''' input is list or tuple '''
        flatXY = self.poslocXY_to_flatXY(poslocXY)  # (flatX, flatY)
        QS = self.flatXY_to_QS(flatXY, cast=True).flatten()  # 1 x 2 array
        return tuple(QS)  # (Q, S)

    # %% composite transformations for convenience (degree 3)
    def posintTP_to_flatXY(self, posintTP):
        poslocXY = self.posintTP_to_poslocXY(posintTP)  # (poslocX, poslocY)
        return self.poslocXY_to_flatXY(poslocXY)  # return (flatX, flatY)

    def flatXY_to_posintTP(self, flatXY, range_limits='full'):
        """Composite transformation, performs obsXY --> posXY --> posintTP"""
        poslocXY = self.flatXY_to_poslocXY(flatXY)  # (poslocX, poslocY)
        return self.poslocXY_to_posintTP(poslocXY, range_limits=range_limits)

    # %% composite transformations for convenience (degree 4)
    def ptlXY_to_posintTP(self, ptlXY):
        ''' input is list or tuple '''
        ptlXYZ = self.QS_to_obsXYZ(self.obsXY_to_QS(ptlXY, cast=True))  # add Z
        flatXY = self.ptlXYZ_to_flatXY(ptlXYZ).flatten()
        return self.flatXY_to_posintTP(flatXY)

    def posintTP_to_ptlXY(self, posintTP):
        ''' input is list or tuple '''
        flatXY = self.posintTP_to_flatXY(posintTP)
        ptlXYZ = self.flatXY_to_ptlXYZ(flatXY, cast=True).flatten()
        return tuple(ptlXYZ)[:2]  # (ptlX, ptlY), petal-local

    # %% composite transformations for convenience (degree 6)
    def posintTP_to_QS(self, posintTP):
        """Composite transformation, performs posintTP --> obsXY --> QS"""
        flatXY = self.posintTP_to_flatXY(posintTP)  # ptl local (flatX, flatY)
        QS = self.flatXY_to_QS(flatXY, cast=True).flatten()  # 1D array
        return tuple(QS)

    def QS_to_posintTP(self, QS, range_limits='full'):
        """Composite transformation, performs QS --> obsXY --> posintTP"""
        flatXY = self.QS_to_flatXY(QS, cast=True).flatten()  # 1D array
        return self.flatXY_to_posintTP(flatXY, range_limits)  # tp, unreachable

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
    def _wrap_consecutive_angles(self, angles, expected_direction):
        """
        input angles is a list of [120, 150, 180, 220, 300...]
        Wrap angles in one expected direction. It is expected that the
        physical deltas we are trying to wrap all increase or all decrease
        sequentially. In other words, that the sequence of angles is only
        going one way around the circle.
        """
        wrapped = [angles[0]]
        for i in range(1, len(angles)):
            delta = angles[i] - wrapped[i-1]
            while pc.sign(delta) != expected_direction and pc.sign(delta) != 0:
                delta += expected_direction * 360
            wrapped.append(wrapped[-1] + delta)
        return wrapped

    @staticmethod
    def _centralized_angular_offset_value(self, offset_angle):
        """
        A special unwrapping check for OFFSET_T and OFFSET_P angles,
        for which we are always going to want to default to the option closer
        to 0 deg. Hence if our calibration routine calculates a best fit
        value for example of OFFSET_T or OFFSET_P = 351 deg, then the real
        setting we want to apply should clearly instead be -9.
        """
        try_plus = offset_angle % 360
        try_minus = offset_angle % -360
        if abs(try_plus) <= abs(try_minus):
            return try_plus
        else:
            return try_minus

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
                       'alpha': 0, 'beta': 0, 'gamma': 0/180*math.pi}
    trans = PosTransforms(petal_alignment=petal_alignment)
    state = trans.posmodel.state
    # device location 0 on petal
    state._val['OFFSET_X'], state._val['OFFSET_Y'] = 28.134375, 5.201437
    print(f'posstate values:\n{state._val}')
    posintTP = (0, 120)
    poslocTP = trans.posintTP_to_poslocTP(posintTP)
    print(f'poslocTP = {poslocTP}')
    posintTP = trans.poslocTP_to_posintTP(poslocTP)
    print(f'posintTP = {posintTP}')
    poslocXY = trans.poslocTP_to_poslocXY(poslocTP)
    print(f'poslocXY = {poslocXY}')
    print(f'poslocTP, unreachable = {trans.poslocXY_to_poslocTP(poslocXY)}')
    flatXY = trans.poslocXY_to_flatXY(poslocXY)
    print(f'flatXY = {flatXY}')
    print(f'poslocXY = {trans.flatXY_to_poslocXY(flatXY)}')
    print(f'poslocXY = {trans.posintTP_to_poslocXY(posintTP)}')
    print(f'posintTP, unreachable = {trans.poslocXY_to_posintTP(poslocXY)}')
    QS = trans.poslocXY_to_QS(poslocXY)
    print(f'QS = {QS}')
    print(f'poslocXY = {trans.QS_to_poslocXY(QS)}')
    print(f'flatXY = {trans.posintTP_to_flatXY(posintTP)}')
    print(f'posintTP, unreachable = {trans.flatXY_to_posintTP(flatXY)}')
    ptlXY = trans.posintTP_to_ptlXY(posintTP)
    print(f'ptlXY = {ptlXY}')
    print(f'posintTP = {trans.ptlXY_to_posintTP(ptlXY)}')
    QS = trans.posintTP_to_QS(posintTP)
    print(f'QS = {QS}')
    print(f'posintTP, unreachable = {trans.QS_to_posintTP(QS)}')
