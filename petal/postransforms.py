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

        posXY   ... (x,y) local to fiber positioner, centered on theta axis, looking at fiber tip
        obsXY   ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        shaftTP ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        obsTP   ... (theta,phi) expected position of fiber tip, including offsets and calibrations
        QS      ... (q,s) global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        flatXY  ... (x,y) global to focal plate, with focal plate slightly stretched out and flattened (used for anti-collision)

    The fundamental transformations provided are:

        posXY   <--> obsXY
        obsXY   <--> shaftTP
        shaftTP <--> obsTP
        obsXY   <--> QS
        QS      <--> flatXY

    These can be chained together in any order to convert among the various coordinate systems.

    Note in practice that the coordinate S is similar, but not identical, to the radial distance
    R from the optical axis. This similarity is because the DESI focal plate curvature is gentle.
    See DESI-0530 for detail on the (Q,S) coordinate system.
    """

    def __init__(self, posmodel=None):
        if not(posmodel):
            posmodel = posmodel.PosModel()
        self.posmodel = posmodel

    # FUNDAMENTAL TRANSFORMATIONS
    def posXY_to_obsXY(self, xy):
        """
        posXY   ... (x,y) local to fiber positioner, centered on theta axis, looking at fiber tip
        obsXY   ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        INPUT:  [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        RETURN: [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        """
        (xy, was_not_list) = pc.listify(xy)
        X = np.polyval(self.poly('X'), xy[0])
        Y = np.polyval(self.poly('Y'), xy[1])
        XY = np.array([X,Y]).tolist()
        if was_not_list:
            XY = pc.delistify(XY)
        return XY

    def obsXY_to_posXY(self, xy):
        """
        obsXY   ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        posXY   ... (x,y) local to fiber positioner, centered on theta axis, looking at fiber tip
        INPUT:  [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        RETURN: [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        """
        (xy, was_not_list) = pc.listify(xy)
        x = np.array(xy[0])
        y = np.array(xy[1])
        Xguess = x - self.poly('X')[-1]
        Yguess = y - self.poly('Y')[-1]
        X = [0]*x.size
        Y = [0]*y.size
        for i in range(x.size):
            X[i] = self.inverse_poly(self.poly('X'), x[i], Xguess[i])
            Y[i] = self.inverse_poly(self.poly('Y'), y[i], Yguess[i])
        XY = [X,Y]
        if was_not_list:
            XY = pc.delistify(XY)
        return XY

    def obsXY_to_shaftTP(self, xy):
        """
        obsXY   ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        shaftTP ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        INPUT:  [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        RETURN: [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
                [N]    array of [index_values]
        The output "unreachable" is a list of all the indexes of the points that could not be physically reached.
        """
        (xy, was_not_list) = pc.listify(xy)
        r = [self.posmodel.state.read('LENGTH_R1'),self.posmodel.state.read('LENGTH_R2')]
        shaft_range = [self.posmodel.full_range_T, self.posmodel.full_range_P]
        XY = self.obsXY_to_posXY(xy)                    # adjust observer xy into the positioner system XY
        obs_range = self.shaftTP_to_obsTP(shaft_range)  # want range used in next line to be according to observer (since observer sees the physical phi = 0)
        (tp, unreachable) = self.xy2tp(XY, r, obs_range)
        TP = self.obsTP_to_shaftTP(tp)                  # adjust angles back into shaft space
        if was_not_list:
            TP = pc.delistify(TP)
        return TP, unreachable

    def shaftTP_to_obsXY(self, tp):
        """
        shaftTP ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        obsXY   ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        INPUT:  [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        RETURN: [2][N] array of [[x_values],[y_values]] or [2] array of [x_value,y_value]
        """
        (tp, was_not_list) = pc.listify(tp)
        r = [self.posmodel.state.read('LENGTH_R1'),self.posmodel.state.read('LENGTH_R2')]
        TP = self.shaftTP_to_obsTP(tp)  # adjust shaft angles into observer space (since observer sees the physical phi = 0)
        xy = self.tp2xy(TP, r)          # calculate xy in posXY space
        xy = xy.tolist()
        XY = self.posXY_to_obsXY(xy)  # adjust positionner XY into observer space
        if was_not_list:
            XY = pc.delistify(XY)
        return XY

    def shaftTP_to_obsTP(self, tp):
        """
        shaftTP ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        obsTP   ... (theta,phi) expected position of fiber tip, including offsets and calibrations
        INPUT:  [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        RETURN: [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        """
        (tp, was_not_list) = pc.listify(tp)
        T = np.polyval(self.poly('T'), tp[0])
        P = np.polyval(self.poly('P'), tp[1])
        TP = np.array([T,P]).tolist()
        if was_not_list:
            TP = pc.delistify(TP)
        return TP

    def obsTP_to_shaftTP(self, tp):
        """
        obsTP   ... (theta,phi) expected position of fiber tip, including offsets and calibrations
        shaftTP ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        INPUT:  [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        RETURN: [2][N] array of [[t_values],[p_values]] or [2] array of [t_value,p_value]
        """
        (tp, was_not_list) = pc.listify(tp)
        t = np.array(tp[0])
        p = np.array(tp[1])
        Tguess = t - self.poly('T')[-1]
        Pguess = p - self.poly('P')[-1]
        T = [0]*t.size
        P = [0]*p.size
        for i in range(t.size):
            T[i] = self.inverse_poly(self.poly('T'), t[i], Tguess[i])
            P[i] = self.inverse_poly(self.poly('P'), p[i], Pguess[i])
        TP = [T,P]
        if was_not_list:
            TP = pc.delistify(TP)
        return TP

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

    # CALIBRATION POLYNOMIAL GETTER
    def poly(self,var):
        """Get polynomial calibraton coefficients.
        INPUT:  'X','Y','T','P' indicates which dimension to get the polynomial of
        OUTPUT: list of polynomial coefficients
        """
        if var == 'X':
            return [1, self.posmodel.state.read('POLYN_X0')]
        elif var == 'Y':
            return [1, self.posmodel.state.read('POLYN_Y0')]
        elif var == 'T':
            return [self.posmodel.state.read('POLYN_T2'), self.posmodel.state.read('POLYN_T1'), self.posmodel.state.read('POLYN_T0')]
        elif var == 'P':
            return [self.posmodel.state.read('POLYN_P2'), self.posmodel.state.read('POLYN_P1'), self.posmodel.state.read('POLYN_P0')]
        else:
            print('bad var ' + str(var))

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
        HYPOT[hypot > outer] = outer
        HYPOT[hypot < inner] = inner
        X = HYPOT*np.cos(angle)
        Y = HYPOT*np.sin(angle)

        # transfrom from cartesian XY to angles TP
        arccos_arg = (X**2 + Y**2 - (r[0]**2 + r[1]**2)) / (2 * r[0] * r[1])
        P = np.arccos(arccos_arg)
        arcsin_arg = r[1] / HYPOT * np.sin(P)
        outofrange = np.abs(arcsin_arg) > 1 # will round arcsin arguments to 1 or -1
        arcsin_arg[outofrange] = np.sign(arcsin_arg[outofrange])
        T = np.arctan2(Y,X) - np.arcsin(arcsin_arg)
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
    def inverse_poly(p, y, xguess):
        """inverter function for quadratic polynomial such that y = polyval(p,x)
        single value calculated at a time only
        """
        if len(p) == 1:
            return (y - p[0])
        elif len(p) == 2:
            return (y - p[1])/p[0]
        else:
            P = p.copy()
            P[-1] -= y
            roots = np.roots(P)
            xdist = (roots - xguess)**2
            x = roots[np.argmin(xdist)]
            return x
