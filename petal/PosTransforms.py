import numpy as np
import PosConstants as pc
import PosState
from numpy.lib.scimath import sqrt as csqrt

class PosTransforms(object):
    """This class includes the following transformations:
    (1) posXY <---> obsXY. XY_pos are the positioner aligned XY values
    (2) shaftTP <---> obsTP. Theta,Phi shaft values and those observed at FVC
    (3) shaftTP <---> obsXY. Thata/phi shaft values and XY at the FVC
    (4) QS <---> obsXY. This is XY as observed at the FVC
    (5) QS <---> flatXY. This is XY used for anticollision
    (6) QS <---> shaftTP. This is XY used for anticollision

    Use of Polyval function : the input arg must be a array who looks like [[c2], [c1], [c0]], where cn are the coefficient
    of the Polynomial function, the other ouput arg is the variables: array or float
    All input and output variables are basic objects from Python ( no Numpy objects )
    """

    def __init__(self, state=None):
        if state is None:
            self.state = PosState.PosState()
        else:
            self.state = state

    def poly(self,var):
        """Reads in polynomial functions from state. Called with var argument 'X','Y','T','P'
        """
        if var == 'X':
            return [self.state.read('POLYN_X1'), self.state.read('POLYN_X0')]
        elif var == 'Y':
            return [self.state.read('POLYN_Y1'), self.state.read('POLYN_Y0')]
        elif var == 'T':
            return [self.state.read('POLYN_T2'), self.state.read('POLYN_T1'), self.state.read('POLYN_T0')]
        elif var == 'P':
            return [self.state.read('POLYN_P2'), self.state.read('POLYN_P1'), self.state.read('POLYN_P0')]
        else:
            print('bad var ' + str(var))

    def posXY_to_obsXY(self, xy):
        """
        INPUT:  [2][N] array of positioner-aligned values XY values 
        RETURN: [2][N] array of XY values as seen by observer at FVC
        """
        X = np.polyval(self.poly('X'), xy[0])
        Y = np.polyval(self.poly('Y'), xy[1])
        XY = np.array([X,Y]).tolist()
        return XY

    def obsXY_to_posXY(self, xy):
        """
        INPUT:  [2][N] array of observer values xy values returns
        RETURN: [2][N] array of XY values of the positioner_aligned
        """
        x = np.array(xy[0])
        y = np.array(xy[1])
        Xguess = x - self.poly('X')[-1]
        Yguess = y - self.poly('Y')[-1]
        XY = [self.inverse_quadratic(self.poly('X'), x, Xguess), self.inverse_quadratic(self.poly('Y'), y, Yguess)]
        return XY

    def shaftTP_to_obsTP(self, tp):
        """
        INPUT:  [2][N] array of theta phi shaft angle values
        RETURN: [2][N] array of tp values as seen by observer
        """
        T = np.polyval(self.poly('T'), tp[0])
        P = np.polyval(self.poly('P'), tp[1])
        TP = np.array([T,P]).tolist()
        return TP

    def obsTP_to_shaftTP(self, tp):
        """
        INPUT:  [2][N] array of theta phi as seen by observer angle values
        RETURN: [2][N] array of theta phi as seen at the output of the gearmotors
        """
        t = np.array(tp[0])
        p = np.array(tp[1])
        Tguess = t - self.poly('T')[-1]
        Pguess = p - self.poly('P')[-1]
        TP = [self.inverse_quadratic(self.poly('T'), t, Tguess), self.inverse_quadratic(self.poly('P'), p, Pguess)]
        return TP

    def obsXY_to_shaftTP(self, xy, r, shaft_range):
        """ Wrapper function for xy2tp, which includes handling of offsets for the
        (x,y) and (t,p) axes. The output "reachable" is a list of all the
        indexes of the points that were able to be reached
        INPUT:  [2][N] array of XY values as seen at the FVC
                [2] array of arm lengths
                [2][2] array of [[min(theta),max(theta)],[min(phi),max(phi)]]
        RETURN: [2][N] array of TP values and whether or not they are reachable
        """
        XY = self.obsXY_to_posXY(xy)        # adjust observer xy into the positioner system XY
        obs_range = self.shaftTP_to_obsTP(shaft_range) # want range used in next line to be according to observer (since observer sees the physical phi = 0)
        [tp, reachable] = self.xy2tp(XY, r, obs_range)
        TP = self.obsTP_to_shaftTP(tp)  # adjust angles back into shaft space
        return TP, reachable

    def shaftTP_to_obsXY(self, tp, r):
        """Wrapper function for tp2xy, which includes handling of offsets
        INPUT:  [2][N] array of shaft tp values
                [2] array of arm lengths
        RETURN: [2][N] array of XY values as seen at the FVC
        """
        TP = self.shaftTP_to_obsTP(tp)  # adjust shaft angles into observer space (since observer sees the physical phi = 0)
        xy = self.tp2xy(TP, r)  # calculate xy in posXY space
        XY = self.posXY_to_obsXY(xy)  # adjust positionner XY into observer space
        return XY

    def QS_to_flatXY(self,qs):
        """
        INPUT:  [2][N] array of QS values
        RETURN: [2][N] array of XY values in a flat system (used for anti-collision) where S is treated as an uncurved radius value
        """
        Q = np.array(qs[0])
        S = np.array(qs[1])
        X = S * np.cos(np.deg2rad(Q))
        Y = S * np.sin(np.deg2rad(Q))
        XY = [X.tolist(),Y.tolist()]
        return XY

    def flatXY_to_QS(self,xy):
        """
        INPUT:  [2][N] array of XY values in a flat system (used for anti-collision) where S is treated as an uncurved radius value
        RETURN: [2][N] array of QS values
        """
        X = np.array(xy[0])
        Y = np.array(xy[1])
        Q = np.degrees(np.arctan2(Y,X))
        S = np.sqrt(X**2 + Y**2)
        QS = [Q.tolist(),S.tolist()]
        return QS

    def QS_to_obsXY(self,qs):
        """
        INPUT:  [2][N] array of QS values
        RETURN: [2][N] array of XY values, as observed at FVC
        """
        Q = np.array(qs[0])
        R = self.S2R(qs[1])
        X = R * np.cos(np.deg2rad(Q))
        Y = R * np.sin(np.deg2rad(Q))
        XY = [X.tolist(),Y.tolist()]
        return XY
     
    def obsXY_to_QS(self,xy):
        """
        INPUT:  [2][N] array of XY values, as observed at FVC
        RETURN: [2][N] array of QS values
        """
        X = np.array(xy[0])
        Y = np.array(xy[1])
        Q = np.degrees(np.arctan2(Y,X))
        R = np.sqrt(X**2 + Y**2)
        S = self.R2S(R.tolist())
        QS = [Q.tolist(),S]
        return QS
       
    def QS_to_shaftTP(self, qs, r, shaft_range):
        """
        INPUT:  [2][N] array of QS
                [2] array of arm lengths
                [2][2] array of [[min(theta),max(theta)],[min(phi),max(phi)]]
        RETURN: [2][N] array of TP values and whether or not they are reachable
        """
        obsXY = self.QS_to_obsXY(qs)
        [shaftTP, reachable] = self.obsXY_to_shaftTP(obsXY,r,shaft_range)
        return shaftTP, reachable

    def shaftTP_to_QS(self,tp,r):
        """
        INPUT:  [2][N] array of shaft tp values
                [2] array of arm lengths
        RETURN: [2][N] array of QS values
        """
        obsXY = self.shaftTP_to_obsXY(tp,r)
        QS = self.obsXY_to_QS(obsXY)
        return QS
        
    @staticmethod
    def R2S(r):
        """Uses focal surface polynomials from DESI-0530 to convert from R to S.
        (Lookup-table may be faster + simpler.)
        INPUT:  R = sqrt(x^2+y^2)
        OUTPUT: S
        """
        p = np.array(pc.R2Spoly)
        p = p[::-1] #reverses list
        S = np.polyval(p,r)
        return S.tolist()
    
    @staticmethod
    def S2R(s):
        """Uses focal surface polynomials from DESI-0530 and poly1d.roots to convert from S to R.
        (Lookup-table may be faster + simpler.)
        INPUT:  S
        OUTPUT: R = sqrt(x^2+y^2)
        """
        p = np.array(pc.R2Spoly)
        p = p[::-1] #reverses list
        p = np.poly1d(p)
        r = (p-np.array(s)).roots
        R = r[-1]
        return R        

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
    def xy2tp(xy, r, ranges, *args):
        """Converts XY coordinates into TP angles, where arm lengths
         associated with angles theta and phi are respectively r(1) and r(2).

        INPUTS:   xy = 2xN array of (x,y) angles
                   r = 1x2 array of arm lengths. r(1) = central arm, r(2) = eccentric arm
              ranges = ranges max and min of theta and phi arms
                args = int : new error limit
        OUTPUTS:  tp = 2xN array of (theta,phi) coordinates
           reachable = List of point reachable
        """
        rounds = 14
        xy = np.array(xy, dtype=float)
        r = np.array(r, dtype=float)
        if len(xy) == 0:
            tp =[]
            reachable = []
            return tp, reachable

        x = xy[0]
        y = xy[1]
        a1_acos_arg = (x**2 + y**2 - (r[0]**2 +r[1]**2)) / (2 * r[0] *r[1])
        prescision = np.where(np.absolute(a1_acos_arg) >= 1 - 1.11 * 10**(-14))
        prescisionbis = np.where(a1_acos_arg-1 >= 10**(-6))
        prescisiontris = np.where(a1_acos_arg+1 <= -10**(-6))
        a1_acos_arg[prescision] = np.around(a1_acos_arg[prescision]/10**(-rounds))*10**(-rounds)#Round a1_acos_arg if it's close to 1 and above or close to -1 and below
        a1_acos_arg[prescisionbis] = 1 #Round to 1 a1_acos_arg if it's close to 1 and below
        a1_acos_arg[prescisiontris] = -1 #Round to -1 a1_acos_arg if it's close to -1 and above
        A = np.zeros(np.shape(xy))
        unreachable = np.zeros(np.shape(xy)[1])
        temporeach = np.where(np.absolute(a1_acos_arg) < 1)
        tempounreach = np.where(np.absolute(a1_acos_arg) > 1)
        A[1,tempounreach] = np.arccos( a1_acos_arg[tempounreach] + 0j).real
        unreachable[ tempounreach] = True
        A[1, temporeach] = np.arccos(a1_acos_arg[temporeach])
        hypot_temp = np.sqrt(x**2+y**2)
        hypot_temp[np.where( hypot_temp < 10**(-rounds))] = 10**(-rounds)
        a0_asin_arg = (r[1] / hypot_temp) * np.sin(A[1])
        prescision = np.where(np.absolute(a0_asin_arg) >= 1 - 1.11 * 10**(-14))#
        prescisionbis = np.where(a0_asin_arg-1 >= 10**(-6))
        prescisiontris = np.where(a0_asin_arg+1 <= -10**(-6))
        a0_asin_arg[prescision] = np.around(a0_asin_arg[prescision]/10**(-rounds))*10**(-rounds)#Round a0_asin_arg if it's close to 1 and above or close to -1 and below
        a0_asin_arg[prescisionbis] = 1 #Round to 1 a0_asin_arg if it's close to 1 and below
        a0_asin_arg[prescisiontris] = -1#Round to -1 a0_asin_arg if it's close to -1 and above
        temporeach = np.where(np.absolute(a0_asin_arg) <= 1)
        tempounreach = np.where(np.absolute(a0_asin_arg) > 1)
        A[0,tempounreach] = np.arctan2(y[tempounreach], x[tempounreach]) - np.arcsin(a0_asin_arg[tempounreach] + 0j).real
        unreachable[tempounreach] = True
        reachable = 1 - unreachable
        A[0, temporeach] = np.arctan2(y[temporeach], x[temporeach]) - np.arcsin(a0_asin_arg[temporeach])

        if len(args) == 0:
            tol = 10**(-rounds)
        else:
            tol = args[0]

        A = np.degrees(A)

        xy_test = PosTransforms.tp2xy(A, r)
        xy_test_err = np.sqrt(np.sum((xy_test-xy)**2, 0))
        badtp = np.where(xy_test_err > tol)
        if badtp[0].tolist() != []:
            a = PosTransforms.xy2tp([(x[badtp]).tolist(), (y[badtp]).tolist()], r, ranges, tol*2)[0]
            a  = np.array(a)
            A[:,badtp] = a[:,np.newaxis]
        below = np.zeros(np.shape(xy))
        above = np.zeros(np.shape(xy))
        still_below = np.zeros(np.shape(xy))
        still_above = np.zeros(np.shape(xy))

        # wrap angles into travel ranges
        for i in [1, 0]:
            if i == 1 and np.any(np.where(unreachable != 0)):
                # mitigate unreachable error distance by adjusting central axis
                unreach = np.where(unreachable == True )
                x_unreachable = r[0] * np.cos(np.deg2rad(A[0,unreach])) + r[1] * np.cos(np.deg2rad(A[0, unreach]+ A[1,unreach]))
                y_unreachable = r[0] * np.sin(np.deg2rad(A[0,unreach])) + r[1] * np.sin(np.deg2rad(A[0, unreach]+ A[1,unreach]))
                erra1r = np.array(PosTransforms.cart2pol(x_unreachable[0], y_unreachable[0])) - np.array(PosTransforms.cart2pol(x[unreach], y[unreach]))
                A[:,unreach] = A[:, unreach] - erra1r[:,np.newaxis]

            below[i] = A[i] < np.min(ranges[i])
            wbelow = np.where(below[i] == True)
            A[i,wbelow] += 360 * np.floor((np.max(ranges[i])-A[i,wbelow]) / 360)
            still_below[i] = A[i] < np.min(ranges[i])
            wsbelow = np.where (still_below[i] == True)
            A[i,wsbelow] = np.min(ranges[i])
            above[i] = A[i] > np.max(ranges[i])
            wabove = np.where (above[i] == True)
            A[i,wabove] -= 360 * np.floor((A[i,wabove]-np.min(ranges[i])) / 360)
            still_above[i] = A[i] > np.max(ranges[i])
            wsabove = np.where (still_above[i] == True)
            A[i,wsabove] = np.max(ranges[i])

        tp = A
        return A.tolist(), reachable.tolist()

    @staticmethod
    def inverse_quadratic(p, y, xguess):
        """inverter function for quadratic polynomial such that y = polyval(p,x)
         INPUTS:
         y       =  1xN array
         xguess  =  1xN array
         p       =  polynomial function to invert
         """
        p = np.array(p, dtype=float)
        y = np.array(y, dtype=float)
        if len(p) == 0:
            x = xguess
        else:
            if p.size > 3:
                p1 = p[-1]
                p2 = p[-2]
                p3 = p[-3]
                p = np.array([p3,p2,p1])  # just throw away errant higher order terms
            elif p.size < 3:
                p = np.concatenate((np.array([np.zeros((3-p.size))]), p), axis=0)  # fill in any missing zeros
            a = p[0][0]
            b = p[1][0]
            c = (p[2][0] - y)
            discriminant = csqrt(b**2 - 4*a*c)
            if b >= 0:
                x1 = (-b-discriminant)/(2*a)
                x2 = (2*c)/(-b-discriminant)
            else:
                x1 =(2*c)/(-b-discriminant)
                x2 =(-b-discriminant)/(2*a)
            xtest = np.array([x1,x2])
            xdist = (xtest - xguess)**2
            xselect = np.argmin(xdist, axis=0)
            x = np.zeros(np.shape(y))
            a = np.where(xselect == 0)
            x[np.where(xselect == 0)] = xtest[0, np.where(xselect == 0)]
            x[np.where(xselect == 1)] = xtest[1, np.where(xselect == 1)]
            # also handle any non-real results from the sqrt
            nonreal = np.where(np.imag(discriminant))[0]
            if not(len(nonreal) == 0):
                x[nonreal] = PosTransforms.inverse_quadratic(p[1:], y[nonreal], xguess[nonreal]) #just throw away the fending quadratic term
            return x.tolist()
    
    @staticmethod
    def cart2pol(x,y):
        """transform cartesian coordinates to polar coordinates"""
        r = np.sqrt(x**2+y**2)
        theta = np.degrees(np.arctan2(y, x))
        return r, theta