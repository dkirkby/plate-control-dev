import numpy as np
from postransforms import PosTransforms
import posconstants as pc


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


class PetalTransforms(object):
    """
    This class provides transformations between the petal local nominal
    coordinate system (CAD model) and the focal plane CS5.
    The transformation parameters are found in focal palte alignment as
    6 DOF rigid-body transformation parameters, defined in trans_keys below,
    and reported per petal according to DESI-2850.

    trans_keys = ['petal_offset_x', 'petal_offset_y', 'petal_offset_z',
                  'petal_rot_x', 'petal_rot_y', 'petal_rot_z']
    which are the input variables, Tx, Ty, Tz in mm, alpha, beta, gamma in deg

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
        obsXYZ:     (x,y,z) global cartesian coordinates on the focal plate
                    cenetered on optical axis, looking at fiber tips
        QS:         (q,s) global coordinates on the focal plate, per DESI-0742
                    q is the angle about the optical axis
                    s is the path distance from optical axis,
                    along the curved focal surface,
                    within a plane that intersects the optical axis

    With QS coordinates, PosTransforms converts into any other
    positioner-specific CS. The wrappers here convert a list of positioner
    coordinates, but that is not acturally supported in PosTransforms.
    We may want to get rid them and unify our transformation methods.
    """

    dtb_device_ids = [543, 544, 545]  # three datum tooling balls on a petal

    def __init__(self, Tx=0, Ty=0, Tz=0, alpha=0, beta=0, gamma=0):
        self.postrans = PosTransforms(curved=True)
        # tanslation matrix from petal nominal CS to CS5, column vector
        self.T = np.array([Tx, Ty, Tz]).reshape(3, 1)
        # orthogonal rotation matrix
        self.R = Rxyz(np.radians(alpha), np.radians(beta), np.radians(gamma))

    def ptlXYZ_to_obsXYZ(self, ptlXYZ):
        """
        INPUT:  3 x N array, each column vector is metXYZ
        OUTPUT: 3 x N array, each column vector is obsXYZ
        """
        return self.R @ ptlXYZ + self.T  # forward transformation

    def obsXYZ_to_ptlXYZ(self, obsXYZ):
        """
        INPUT:  3 x N array, each column vector is obsXYZ
        OUTPUT: 3 x N array, each column vector is metXYZ
        """
        return self.R.T @ (obsXYZ - self.T)  # backward transformation

    def obsXYZ_to_QS(self, obsXYZ):
        """Transforms list of obsXYZ coordinates into QS system.
        INPUT:  3 x N array, each column vector is obsXYZ
        OUTPUT: 2 x N array of corresponding [[q0,s0],[q1,s1],...]
        """
        X, Y = obsXYZ[0, :], obsXYZ[1, :]
        Q = np.degrees(np.arctan2(Y, X))  # Y over X
        R = np.sqrt(np.square(X) + np.square(Y))
        S = pc.R2S_lookup(R)
        return np.array([Q, S])

    def QS_to_obsXYZ(self, QS):
        """Transforms list of QS coordinates into obsXYZ system.
        INPUT:  2 x N array, each column vector is QS
        OUTPUT: 3 x N array, each column vector is obsXYZ
        """
        Q_rad, S = np.radians(QS[0, :]), QS[1, :]
        R = self.S2R(S)
        X = R * np.cos(Q_rad)
        Y = R * np.sin(Q_rad)
        Z = pc.R2Z_lookup(R)
        return np.array([X, Y, Z])

    def ptlXYZ_to_QS(self, ptlXYZ):
        """
        INPUT:  3 x N array, each column vector is ptlXYZ
        OUTPUT: 2 x N array of corresponding [[q0,s0],[q1,s1],...]
        """
        obsXYZ = self.ptlXYZ_to_obsXYZ(ptlXYZ)
        return self.obsXYZ_to_QS(obsXYZ)

    def QS_to_ptlXYZ(self, QS):
        """
        INPUT:  2 x N array of corresponding [[q0,s0],[q1,s1],...]
        OUTPUT: 3 x N array, each column vector is ptlXYZ
        """
        obsXYZ = self.QS_to_obsXYZ(QS)
        return self.obsXYZ_to_ptlXYZ(obsXYZ)


if __name__ == '__main__':
    """
    Unit test, choose location 4, which is 36 degrees of rotation ccw
    Taken from petal alignment data， PTL04
    T = [0.01261281, 0.068910657, 0.017850711]
    angles = [0.001382631,	-0.002945219,	35.9887675]
    dtb0_543 = [11.671,	23.542,	-81.893] in CS5
    [23.233778, 12.1450584, -81.9095268] in petal CS

    """
    ptltrans = PetalTransforms(Tx=0.01261281, Ty=0.068910657, Tz=0.017850711,
                               alpha=0.001382631,
                               beta=-0.002945219,
                               gamma=35.9887675)
    obsXYZ_actual = np.array([11.671,	23.542,	-81.893])
    ptlXYZ_actual = np.array([23.233778, 12.1450584, -81.9095268])
    obsXYZ = ptltrans.ptlXYZ_to_obsXYZ(ptlXYZ_actual)
    ptlXYZ = ptltrans.obsXYZ_to_ptlXYZ(obsXYZ_actual)
    print(f'obsXYZ, actual: {obsXYZ_actual}, transformed: {obsXYZ}\n'
          f'ptlXYZ, actual: {ptlXYZ_actual}, transformed: {ptlXYZ}')
