import numpy as np
import PosConstants
#import functionsnew as fun
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

    def polyss(self):
        """Reads in polynomial functions from state. Called with 'X','Y','T','P'
        """
        polyss = {}
        polyss['X'] = np.array([[self.state.read('POLYN_X1')], [self.state.read('POLYN_X0')]])
        polyss['Y'] = np.array([[self.state.read('POLYN_Y1')], [self.state.read('POLYN_Y0')]])
        polyss['T'] = np.array([[self.state.read('POLYN_T2')], [self.state.read('POLYN_T1')],[self.state.read('POLYN_T0')]])
        polyss['P'] = np.array([[self.state.read('POLYN_P2')], [self.state.read('POLYN_P1')], [self.state.read('POLYN_P0')]])
        return polyss

    def posXY_to_obsXY(self, xy):
        """
        RETURN: 2N array of XY values as seen by observer at FVC
        INPUT: 2N array of positioner-aligned values XY values 
        """
        xy_polys = self.polyss()
        XY = np.array([np.polyval(xy_polys['X'], xy[:,0]), np.polyval(xy_polys['Y'], xy[:,1])]).tolist()
        return XY

    def obsXY_to_posXY(self, xy):
        """
        RETURN: 2N array of XY values of the positioner_aligned
        INPUT: 2N array of observer values xy values returns
        """
        xy_polys = self.polyss()
        x = np.array(xy[:,0])
        y = np.array(xy[:,1])
        XYguess0 = x-xy_polys['X'][-1]
        XYguess1 = y-xy_polys['Y'][-1]
        if xy.shape == (2,):
            XY = [self.inverse_quadratic(xy_polys['X'], [x], XYguess0[0]), self.inverse_quadratic(xy_polys['Y'], [y], XYguess1[0])][0]
        else :
            XY = [self.inverse_quadratic(xy_polys['X'], x, XYguess0[0]), self.inverse_quadratic(xy_polys['Y'], y, XYguess1[0])]
        return XY

    def shaftTP_to_obsTP(self, tp):
        """
        RETURN: 2N array of tp values as seen by observer
        INPUT: 2N array of theta phi shaft angle values

        PosConstants.T,P give index for theta, phi
        """
        tp_polys = self.polyss()
        evalfunc_T = lambda x: np.polyval(tp_polys['T'], x)
        evalfunc_P = lambda x: np.polyval(tp_polys['P'], x)
        TP = np.array([evalfunc_T(tp[:,PosConstants.T]).tolist(),evalfunc_P(tp[:,PosConstants.P]).tolist()]).tolist()
        return TP

    def obsTP_to_shaftTP(self, tp, *args, T=False, P=False):
        """
        RETURN: 2N array of tp values 
        INPUT: 2N array of theta phi as seen by observer angle values
        args: True --> force use of quadratic poly
        """
        note = '' #not sure that we need this. Took it out for time being.

        tp = np.array(tp)
        tp_polys = self.polyss()
        TP = np.zeros(tp.shape)
        TPguess = np.zeros(tp.shape)

        if tp.shape[0] == 1:
            if T == True:
                TPguess = tp - tp_polys['T'][-1]
                inversefunc_T = lambda x: self.inverse_quadratic(tp_polys['T'], x, TPguess)[0]
                TP = inversefunc_T(tp)

            elif P == True:
                TPguess = tp - tp_polys['P'][-1]
                inversefunc_P = lambda x: self.inverse_quadratic(tp_polys['P'], x, TPguess)[0]
                TP = inversefunc_P(tp)
                
            else:
                print('You must identify whether this is theta or phi axis data')

        elif tp.shape[0] == 2:
            TPguess[PosConstants.T] = tp[PosConstants.T] - tp_polys['T'][-1]
            TPguess[PosConstants.P] = tp[PosConstants.P] - tp_polys['P'][-1]
            inversefunc_T = lambda x: self.inverse_quadratic(tp_polys['T'], x, TPguess[PosConstants.T])[0]
            inversefunc_P = lambda x: self.inverse_quadratic(tp_polys['P'], x, TPguess[PosConstants.P])[0]
            TP[PosConstants.T] = inversefunc_T(tp[PosConstants.T])
            TP[PosConstants.P] = inversefunc_P(tp[PosConstants.P])

        #I don't fully understand this part
        use_pp = [False, False]
        unchanged = TP == tp
        for i in range(0, tp.shape[0]):
            if unchanged[i].any and use_pp[i]:
                TP_backup = self.obsTP_to_shaftTP(tp[:, unchanged[i]], True)
                TP[i, unchanged[i]] = TP_backup[i]
                print('obsTP_to_shaftTP: piecewise polynom inversion error. reverting to quadpoly')

        return TP


    def obsXY_to_shaftTP(self, xy, r, shaft_range):
        """ Wrapper function for xy2tp, which includes handling of offsets for the
        (x,y) and (t,p) axes. The output "reachable" is a list of all the
        indexes of the points that were able to be reached
        RETURN: 2N array of TP values and whether or not they are reachable
        INPUT: 2N array of XY values as seen at the FVC, r = (r[1],r[2]), and shaft_range
        """
        xy = np.array(xy)
        XY = self.obsXY_to_posXY(xy)        # adjust observer xy into the position system XY
        obs_range = self.shaftTP_to_obsTP(shaft_range) # want range used in next line to be according to observer (since observer sees the physical phi = 0)
        if xy.shape == (2,):
            [tp, reachable] = self.xy2tp([[XY[0]],[XY[1]]], r, obs_range) # calculate theta phi angles in observer space
            tp = [tp[0][0], tp[1][0]]
        else:
            [tp, reachable] = self.xy2tp(XY, r, obs_range)
        TP = self.obsTP_to_shaftTP(tp)  # adjust angles back into shaft space
        return TP, reachable

    def shaftTP_to_obsXY(self, tp, r):
        """Wrapper function for tp2xy, which includes handling of offsets
        RETURN: 2N array of XY values as seen at the FVC
        INPUT: 2N array of shaft tp values and r = (r[1],r[2])
        """
        TP = self.shaftTP_to_obsTP(tp)  # adjust shaft angles into observer space (since observer sees the physical phi = 0)
        xy = self.tp2xy(TP, r)  # calculate xy in posXY space
        XY = self.posXY_to_obsXY(xy)  # adjust positionner XY into observer space
        return XY

    def QS_to_flatXY(self,qs):
        """
        RETURN: XY flattened as 2N array
        INPUT: QS values as 2N array
        """
        QS = np.array(qs)
        aQ = np.arctan(QS[:,0])
        S = QS[:,1]
        
        x = (np.sqrt((S**2*aQ**2)/(1+aQ**2)))
        y = (np.sqrt((S**2-aQ**2)/2))
        XY = np.array([x,y]).tolist()
        return XY

    def flatXY_to_QS(self,xy):
        """
        RETURN:QS values as 2N array
        INPUT: XY flattened as 2N array
        """
        XY = np.array(xy)
        q = np.tan(XY[:,0]/XY[:,1])
        s = np.sqrt(XY[:,0]**2+XY[:,1]**2)

        QS = np.array([q,s]).tolist()
        return QS

    def QS_to_obsXY(self,qs):
        """Uses S2R function to convert between S and R.
        RETURN: XY as observed at FVC as 2N array
        INPUT: QS values as 2N array
        """
        QS = np.array(qs)
        aQ = np.arctan(QS[:,0])
        S = QS[:,1]
        R = self.S2R(S)

        x = (np.sqrt((R**2*aQ**2)/(1+aQ**2)))
        y = (np.sqrt((R**2-aQ**2)/2))
        XY = np.array([x,y]).tolist()
        return XY
     
    def obsXY_to_QS(self,xy):
        """Uses R2S to convert between R and S
        RETURN:QS values as 2N array
        INPUT: XY flattened as 2N array
        """
        XY = np.array(xy)
        q = np.tan(XY[:,0]/XY[:,1])
        r = np.sqrt(XY[:,0]**2+XY[:,1]**2)
        s = self.R2S(r)

        QS = np.array([q,s]).tolist()
        return QS
       
    def QS_to_shaftXY(self,qs, r, shaft_range):
        """
        RETURN: XY flattened as 2N array
        INPUT: QS values as 2N array
               r = arm lengths ([r[1],r[2]])
               shaft_range = max range of ([theta,phi])
        """
        QS = np.array(qs)
        obsXY = self.QS_to_obsXY(QS)
        [shaft_tp, reachable] = self.obsXY_to_shaftTP(obsXY,r,shaft_range)
        
        return [shaft_tp, reachable]

    def shaftTP_to_QS(self,tp,r):
        """
        RETURN:QS values as 2N array
        INPUT: XY flattened as 2N array
               r = arm lengths ([r[1],r[2]])
        """
        TP = np.array(tp)
        obsXY = self.shaftTP_to_obsXY(TP,r)
        qs = self.obsXY_to_QS(obsXY)
        QS = np.array(qs).tolist()
        return QS
        
    @staticmethod
    def R2S(r):
        """Takes polynomials from DESIdoc530 to convert from R to S.
        INPUT: R = sqrt(x^2+y^2)
        OUTPUT: S
        """
        p = np.array([5.00010E-01,9.99997E-01,1.91532E-07,1.72104E-09,7.31761E-11,-5.78982E-13,3.30271E-15,-1.11245E-17,1.90376E-20,-1.26341E-23])
        p = [::-1] #reverses list
        Q = np.polyval(p,r)
        return Q
    
    @staticmethod
    def S2R(s):
        """Takes polynomials from DESIdoc530 and poly1d.roots to convert from S to R.
        INPUT: S
        OUTPUT: R = sqrt(x^2+y^2)
        """
        p = np.array([5.00010E-01,9.99997E-01,1.91532E-07,1.72104E-09,7.31761E-11,-5.78982E-13,3.30271E-15,-1.11245E-17,1.90376E-20,-1.26341E-23])
        p = [::-1] #reverses list
        p = np.poly1d(p)

        r = (p-s).roots
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
                erra1r = np.array(fun.cart2pol(x_unreachable[0], y_unreachable[0])) - np.array(fun.cart2pol(x[unreach], y[unreach]))
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
                x[nonreal] = inverse_quadratic(p[1:], y[nonreal], xguess[nonreal]) #just throw away the fending quadratic term
            return x.tolist()

