import numpy as np
import posconstants as pc


# %% rotation matrices
def Rx(angle):  # all in radians
    Rx = np.array([
                   [1.0,           0.0,            0.0],
                   [0.0,           np.cos(angle),  -np.sin(angle)],
                   [0.0,           np.sin(angle),  np.cos(angle)]
                  ])
    return Rx


def Ry(angle):  # all in radians
    Ry = np.array([
                   [np.cos(angle),  0.0,            np.sin(angle)],
                   [0.0,            1.0,            0.0],
                   [-np.sin(angle), 0.0,            np.cos(angle)]
                  ])
    return Ry


def Rz(angle):  # all in radians
    Rz = np.array([
                   [np.cos(angle), -np.sin(angle), 0.0],
                   [np.sin(angle), np.cos(angle),  0.0],
                   [0.0,           0.0,            1.0]
                  ])
    return Rz


def Rxyz(alpha, beta, gamma):  # yaw-pitch-roll system, all in radians
    return Rz(gamma) @ Ry(beta) @ Rx(alpha)  # @ is matrix multiplication


def typecast(x):
    if type(x) in [list, tuple]:  # 2 or 3 coordinates, reshape into column vec
        return np.array(x).reshape(len(x), 1)
    elif type(x) is np.ndarray:
        if x.ndim == 1:  # a 1D array of 2 or 3 coordinates
            return x.reshape(x.size, 1)  # reshape into column vector
        elif x.ndim == 2:  # 2D array, assume each column is a column vec
            return x
        else:
            raise ValueError(f'Wrong numpy array dimension: {x.ndim}')
    else:
        raise TypeError(f'Wrong data type: {type(x)}')


# %% class definition
class PetalTransforms:
    """
    This class provides transformations between the petal local nominal
    coordinate system (CAD model) and the focal plane CS5.
    The transformation parameters are found in focal palte alignment as
    6 DOF rigid-body transformation parameters, defined in trans_keys below,
    and reported per petal according to DESI-2850.

    trans_keys = ['petal_offset_x', 'petal_offset_y', 'petal_offset_z',
                  'petal_rot_x', 'petal_rot_y', 'petal_rot_z']
    which are the input variables, Tx, Ty, Tz in mm, alpha, beta, gamma in rad

    For forward transformation,
    the transformation defined by these 6 parameters can act on
    (1) nominal values in the petal local CS as defined in the CAD model, or
    (2) metrology data in the petal local CS (best-fit to the CAD, "ZBF")
    and result in coordinates in CS5, assuming the alignment achieved on
    mountain is the same as done in the metrology lab.

    In use, you make one instance of PetalTransforms per petal.
    A given instance can be initialised with either 6 dof or just 3 dof as
    viewed by the FVC, assuming the other three are zero.

    Note the rotation angles reported from metrology and used for
    focal plate alingment are NOT the classic Euler 3-2-3 or Z-Y-Z angles.
    They are the rotation angles w.r.t. x, y, and z-axes.
    The Euler method provided in this class contains the
    canonical order of operations to do this transform in 3-2-3.

    The coordinate systems are:

        ptlXYZ:     position of a point in the petal's local coordinate system
                    according to the CAD design (overlaps with location 3)

        obsXYZ:     (x, y, z) global cartesian coordinates on the focal plate
                    cenetered on optical axis looking at fiber tips (don't use)

        QS:         (q,s) global coordinates on the focal plate, per DESI-0742
                    q is the angle about the optical axis
                    s is the path distance from optical axis,
                    along the curved focal surface,
                    within a plane that intersects the optical axis

        flatXY:     reserved for petal local CS, with focal plate slightly
                    stretched out and flattened (used for anti-collision)

                    for global flatXY coordinates, use obsXY methods with
                    curved = False

    With QS coordinates, PosTransforms converts into any other
    positioner-specific CS. The wrappers here convert a list of positioner
    coordinates, but that is not acturally supported in PosTransforms.
    We may want to get rid them and unify our transformation methods.

    All methods take list or np.ndarray input as handled in typecast() above.
    Set optional arg cast=True when feeding a non-column-vector-based array.

    The option "curved" sets whether we are looking at a flat focal plane
    (such as a laboratory test stand), or a true petal, with its asphere.
    When curved == False, PosTransforms will treat S as exactly equal to the
    radius R.
    """

    dtb_device_ids = [543, 544, 545]  # three datum tooling balls on a petal

    def __init__(self, Tx=0, Ty=0, Tz=0, alpha=0, beta=0, gamma=0,
                 curved=True):  # input in mm and radians
        # self.postrans = PosTransforms(curved=True)
        # tanslation matrix from petal nominal CS to CS5, column vector
        self.T = np.array([Tx, Ty, Tz]).reshape(3, 1)
        # orthogonal rotation matrix
        self.R = Rxyz(alpha, beta, gamma)
        self.curved = curved

    # %% fundamental transformations
    def ptlXYZ_to_obsXYZ(self, ptlXYZ, cast=False):
        """
        INPUT:  3 x N array, each column vector is ptlXYZ
        OUTPUT: 3 x N array, each column vector is obsXYZ
        """
        if cast:
            ptlXYZ = typecast(ptlXYZ)
        return self.R @ ptlXYZ + self.T  # forward transformation

    def obsXYZ_to_ptlXYZ(self, obsXYZ, cast=False):
        """
        INPUT:  3 x N array, each column vector is obsXYZ
        OUTPUT: 3 x N array, each column vector is ptlXYZ
        """
        if cast:
            obsXYZ = typecast(obsXYZ)
        return self.R.T @ (obsXYZ - self.T)  # backward transform

    # %% QS transforms (only need 2D)
    def obsXY_to_QS(self, obsXY, curved=None, cast=False):
        """
        input:  2 x N array
        output: 2 x N array, each column vector is QS
        """
        if cast:
            obsXY = typecast(obsXY)
        if curved is None:  # allow forcing flatXY despite curved instance
            curved = self.curved
        X, Y = obsXY[0, :], obsXY[1, :]
        Q = np.degrees(np.arctan2(Y, X))  # Y over X
        R = np.sqrt(np.square(X) + np.square(Y))
        S = pc.R2S_lookup(R) if curved else R
        return np.array([Q, S])

    def QS_to_obsXY(self, QS, curved=None, cast=False):
        """
        input:  2 x N array, each column vector is QS
        output: 2 x N array, if curved=False, returns flatXY on focal surface
        """
        if cast:
            QS = typecast(QS)
        if curved is None:  # allow forcing flatXY despite curved instance
            curved = self.curved
        Q_rad, S = np.radians(QS[0, :]), QS[1, :]
        R = pc.S2R_lookup(S) if curved else S
        X = R * np.cos(Q_rad)
        Y = R * np.sin(Q_rad)
        return np.array([X, Y])

    def obsXYZ_to_QS(self, obsXYZ, curved=None, cast=False):
        """Transform obsXYZ coordinates into QS system.
        Z data (in 3rd row) aren't used at all, as X and Y are sufficient.
        INPUT:  3 x N array, each column vector is obsXYZ
        OUTPUT: 2 x N array of corresponding [[q0,s0],[q1,s1],...]
        """
        if cast:
            obsXYZ = typecast(obsXYZ)
        if curved is None:  # allow forcing flatXY despite curved instance
            curved = self.curved
        return self.obsXY_to_QS(obsXYZ[:2, :], curved=curved)  # use only XY

    def QS_to_obsXYZ(self, QS, curved=None, cast=False):
        """Transforms list of QS coordinates into obsXYZ system.
        On-shell condition is enforced
        INPUT:  2 x N array, each column vector is QS
        OUTPUT: 3 x N array, each column vector is obsXYZ
        """
        if cast:
            QS = typecast(QS)
        if curved is None:  # allow forcing flatXY despite curved instance
            curved = self.curved
        obsXY = self.QS_to_obsXY(QS, curved=curved)  # convert XY
        R = np.sqrt(np.square(obsXY[0, :]) + np.square(obsXY[1, :]))  # get Z
        Z = pc.R2Z_lookup(R)
        return np.vstack([obsXY, Z])  # add z data to the 3rd row

    # %% flatXY transforms within petal local coordinates
    def ptlXYZ_to_flatXY(self, ptlXYZ, cast=False):
        """
        INPUT:  3 x N array, each column vector is ptlXYZ, petal-local
        OUTPUT: 2 x N array, each column vector is flatXY, petal-local
        useful for seeding xy offsets on flattened focal surface
        """
        if cast:
            ptlXYZ = typecast(ptlXYZ)
        # assume this petal is mounted nomically in location 3
        # i.e. let the petal local CS align with CS5 and QS coordinates
        QS = self.obsXYZ_to_QS(ptlXYZ)
        return self.QS_to_obsXY(QS, curved=False)  # effectively QS to flatXY

    def flatXY_to_ptlXYZ(self, flatXY, cast=False):
        """
        INPUT:  2 x N array, each column vector is flatXY, petal-local
        OUTPUT: 3 x N array, each column vector is ptlXYZ, petal-local
        """
        if cast:
            flatXY = typecast(flatXY)
        # assume this petal is mounted nomically in location 3
        # i.e. let the petal local CS align with CS5 and QS coordinates
        QS = self.obsXY_to_QS(flatXY, curved=False)  # this is QS in CS5
        return self.QS_to_obsXYZ(QS)

    # %% composite transformations for convenience
    def ptlXYZ_to_QS(self, ptlXYZ, cast=False):
        """
        INPUT:  3 x N array, each column vector is ptlXYZ, petal-local
        OUTPUT: 2 x N array of corresponding [[q0,s0],[q1,s1],...], global
        """
        if cast:
            ptlXYZ = typecast(ptlXYZ)
        obsXYZ = self.ptlXYZ_to_obsXYZ(ptlXYZ)
        return self.obsXYZ_to_QS(obsXYZ)

    def QS_to_ptlXYZ(self, QS, cast=False):
        """
        INPUT:  2 x N array of corresponding [[q0,s0],[q1,s1],...], global
        OUTPUT: 3 x N array, each column vector is ptlXYZ, petal-local
        """
        if cast:
            QS = typecast(QS)
        obsXYZ = self.QS_to_obsXYZ(QS)
        return self.obsXYZ_to_ptlXYZ(obsXYZ)

    def flatXY_to_QS(self, flatXY, cast=False):
        """
        INPUT:  2 x N array, each column vector is flatXY, petal-local
        OUTPUT: 2 x N array of corresponding [[q0,s0],[q1,s1],...], global
        """
        if cast:
            flatXY = typecast(flatXY)
        ptlXYZ = self.flatXY_to_ptlXYZ(flatXY)  # petal local
        return self.ptlXYZ_to_QS(ptlXYZ)  # to global

    def QS_to_flatXY(self, QS, cast=False):
        """
        INPUT:  2 x N array of corresponding [[q0,s0],[q1,s1],...], global
        OUTPUT: 2 x N array, each column vector is flatXY, petal-local
        """
        if cast:
            QS = typecast(QS)
        ptlXYZ = self.QS_to_ptlXYZ(QS)  # global to petal local
        return self.ptlXYZ_to_flatXY(ptlXYZ)  # petal local

# %% written but discouraged transformations

    # def ptlXY_to_obsXY(self, ptlXY, cast=False):
    #     """
    #     INPUT:  2 x N array, each column vector is ptlXY
    #     OUTPUT: 2 x N array, each column vector is obsXY
    #     On-shell condition is enforced because Z coordinates necessrily mix
    #     with XY when doing a (more accurate in principle) 3D transformation
    #     """
    #     if cast:
    #         ptlXY = typecast(ptlXY)
    #     R = np.sqrt(np.square(ptlXY[0, :]) + np.square(ptlXY[1, :]))
    #     ptlXYZ = np.vstack([ptlXY, pc.R2Z_lookup(R)])
    #     return self.ptlXYZ_to_obsXYZ(ptlXYZ)[:2, :]  # only take first 2 rows

    # def obsXY_to_ptlXY(self, obsXY, cast=False):
    #     """
    #     INPUT:  2 x N array, each column vector is obsXY
    #     OUTPUT: 2 x N array, each column vector is ptlXY
    #     On-shell condition is enforced
    #     """
    #     if cast:
    #         obsXY = typecast(obsXY)
    #     R = np.sqrt(np.square(obsXY[0, :]) + np.square(obsXY[1, :]))
    #     obsXYZ = np.vstack([obsXY, pc.R2Z_lookup(R)])
    #     return self.obsXYZ_to_ptlXYZ(obsXYZ)[:2, :]  # only take first 2 rows

    # def ptlXY_to_QS(self, ptlXY, cast=False):
    #     if cast:
    #         ptlXY = typecast(ptlXY)
    #     obsXY = self.ptlXY_to_obsXY(ptlXY)
    #     return self.obsXY_to_QS(obsXY)

    # def QS_to_ptlXY(self, QS, cast=False):
    #     if cast:
    #         QS = typecast(QS)
    #     obsXY = self.QS_to_obsXY(QS)
    #     return self.obsXY_to_ptlXY(obsXY)

    # def obsXY_to_flatXY(self, obsXY, cast=False):
    #     """Composite transformation, performs obsXY --> QS --> flatXY"""
    #     if cast:
    #         obsXY = typecast(obsXY)
    #     QS = self.obsXY_to_QS(obsXY)
    #     return self.QS_to_flatXY(QS)

    # def flatXY_to_obsXY(self, flatXY, cast=False):
    #     """Composite transformation, performs flatXY --> QS --> obsXY"""
    #     if cast:
    #         flatXY = typecast(flatXY)
    #     QS = self.flatXY_to_QS(flatXY)
    #     return self.QS_to_obsXY(QS)


# %% main
if __name__ == '__main__':
    """
    Unit test, choose location 4, which is 36 degrees of rotation ccw
    Taken from petal alignment data， PTL04
    T = [0.01261281, 0.068910657, 0.017850711]
    angles = [0.001382631,	-0.002945219,	35.9887675]
    dtb0_543 = [11.671,	23.542,	-81.893] in CS5
    [23.233778, 12.1450584, -81.9095268] in petal CS

    """
    trans = PetalTransforms(Tx=0.01261281, Ty=0.068910657, Tz=0.017850711,
                            alpha=0.001382631,
                            beta=-0.002945219,
                            gamma=0/180*np.pi)
    trans = PetalTransforms(gamma=-180/180*np.pi)
    # location 408
    ptlXYZ = np.array([319.951289, 131.457285, -13.262356]).reshape(3, 1)
    # obsXYZ_actual = np.array([11.671,	23.542,	-81.893]).reshape(3, 1)
    # ptlXYZ_actual = np.array([23.2337, 12.1450, -81.9095]).reshape(3, 1)
    # print(f'obsXYZ, actual: {obsXYZ_actual.T}\ntransformed: {obsXYZ.T}\n'
    #       f'ptlXYZ, actual: {ptlXYZ_actual.T}\ntransformed: {ptlXYZ.T}')
    # device location 526
    obsXYZ = trans.ptlXYZ_to_obsXYZ(ptlXYZ)
    ptlXYZ = trans.obsXYZ_to_ptlXYZ(obsXYZ)
    QS = trans.obsXY_to_QS(obsXYZ[:2, :])
    print(f'QS = {QS.T}')
    obsXY = trans.QS_to_obsXY(QS)
    print(f'obsXY = {obsXY.T}')
    print(f'obsXYZ = {obsXYZ.T}')
    print(f'ptlXYZ = {ptlXYZ.T}')
    QS = trans.obsXYZ_to_QS(obsXYZ)
    print(f'QS = {QS.T}')
    print(f'obsXYZ = {trans.QS_to_obsXYZ(QS).T}')
    obsXY = trans.QS_to_obsXY(QS)
    print(f'obsXY = {obsXY.T}')
    print(f'QS = {trans.obsXY_to_QS(obsXY).T}')
    flatXY = trans.ptlXYZ_to_flatXY(ptlXYZ)
    print(f'flatXY = {flatXY.T}')
    print(f'ptlXYZ = {trans.flatXY_to_ptlXYZ(flatXY).T}')
    print(f'QS = {trans.ptlXYZ_to_QS(ptlXYZ).T}')
    print(f'ptlXYZ = {trans.QS_to_ptlXYZ(QS).T}')
    print(f'QS = {trans.flatXY_to_QS(flatXY).T}')
    print(f'flatXY = {trans.QS_to_flatXY(QS).T}')
