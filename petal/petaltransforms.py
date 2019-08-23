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

        metXYZ:     (x,y,z) measured device center locations on the aspheric
                    focal surface, local to an individual petal,
                    with some arbitrary origin for each petal, such that
                    metrology data are overall closest to nomial specs in CAD.
                    These are the projected fibre tip or FIF pinhole centre
                    coordinates reported from the metrology
                    (x_meas_proj, y_meas_proj, z_meas_proj), assuming
                    perfectly built positioners.
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

    def metXYZ_to_obsXYZ(self, metXYZ):
        """
        INPUT:  3 x N array, each column vector is metXYZ
        OUTPUT: 3 x N array, each column vector is obsXYZ
        """
        return self.R @ metXYZ + self.T  # forward transformation

    def obsXYZ_to_metXYZ(self, obsXYZ):
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
        ret = np.zeros((2, obsXYZ.shape[1]))
        for i in range(obsXYZ.shape[1]):  # loop over all column vectors
            ret[:, i] = self.postrans.obsXY_to_QS([obsXYZ[0, i], obsXYZ[1, i]])
        return ret

    def QS_to_obsXYZ(self, QS):
        """Transforms list of obsXYZ coordinates into QS system.
        INPUT:  2 x N array, each column vector is QS
        OUTPUT: 3 x N array, each column vector is obsXYZ

        Note that because QS is only 2 dimensional,
        the Z coordinate is a nominal value looked up from the Echo22 asphere.
        """
        ret = np.zeros((3, QS.shape[1]))
        for i in range(QS.shape[1]):  # loop over all column vectors
            ret[:2, i] = self.postrans.QS_to_obsXY([QS[0, i], QS[1, i]])
            r = np.sqrt(np.sum(np.square(ret[:2, i])))
            ret[2, i] = pc.R2Z_lookup(r)
        return ret

    def metXYZ_to_QS(self, metXYZ):
        """
        INPUT:  3 x N array, each column vector is metXYZ
        OUTPUT: 2 x N array of corresponding [[q0,s0],[q1,s1],...]
        """
        obsXYZ = self.metXYZ_to_obsXYZ(metXYZ)
        return self.obsXYZ_to_QS(obsXYZ)

    def QS_to_metXYZ(self, QS):
        """Transforms list of QS coordinates into metXYZ system.
        INPUT:  [N][2] array of [[q0,s0],[q1,s1],...]
        OUTPUT: 3 x N array, each column vector is metXYZ
        """
        obsXYZ = self.QS_to_obsXYZ(QS)
        return self.obsXYZ_to_metXYZ(obsXYZ)


if __name__ == '__main__':
    """The code below allows you to test out the transforms on a real-world
    set of report files formatted per DESI-2850.
    Probably not working after the changes.
    """
    import os
    import csv
    import tkinter
    import tkinter.filedialog

    gui_root = tkinter.Tk()
    initialdir = os.getcwd()
    filetypes = (("CSV file", "*.csv"), ("All Files", "*")),
    files = {key: '' for key in ['petal_metrology', 'focal_plane_metrology']}
    data = {}
    for key in files:
        message = 'Select ' + key + ' file.'
        files[key] = tkinter.filedialog.askopenfilename(
            initialdir=initialdir, filetypes=filetypes, title=message)
        if files[key]:
            with open(files[key], 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                data[key] = {field: [] for field in reader.fieldnames}
                for row in reader:
                    for field in reader.fieldnames:
                        data[key][field].append(float(row[field]))
        initialdir = os.path.split(files[key])[0]
    if all([key in data for key in files]):
        petal_id = data['petal_metrology']['petal_id'][0]
        n = len(data['petal_metrology']['x_meas_proj'])
        metXYZ = []
        for i in range(n):
            this_xyz = [data['petal_metrology'][field][i] for field in
                        ['x_meas_proj', 'y_meas_proj', 'z_meas_proj']]
            metXYZ.append(this_xyz)
        trans_row = data['focal_plane_metrology']['petal_id'].index(petal_id)
        transforms = {field: data['focal_plane_metrology'][field][trans_row]
                      for field in PetalTransforms().trans_keys}
        petal_trans = PetalTransforms(transforms)
        QS = petal_trans.metXYZ_to_QS(metXYZ)
        checkXYZ = petal_trans.QS_to_metXYZ(QS)
        initialdir = os.path.split(files['petal_metrology'])[0]
        initialfile = 'results_petal_' + str(int(petal_id)) + '.csv'
        message = 'Save results as'
        savefile = tkinter.filedialog.asksaveasfilename(
            initialdir=initialdir, initialfile=initialfile,
            filetypes=filetypes, title=message)
        if savefile:
            with open(savefile, 'w', newline='') as csvfile:
                writer = csv.DictWriter(
                    csvfile,
                    fieldnames=['device_loc', 'metX', 'metY', 'metZ',
                                'Q', 'S', 'ballX', 'ballY', 'ballZ',
                                'checkX', 'checkY', 'checkZ',
                                'errX', 'errY', 'errZ'])
                writer.writeheader()
                for i in range(n):
                    row = {}
                    row['device_loc'] = int(
                        data['petal_metrology']['device_loc'][i])
                    row['metX'] = metXYZ[i][0]
                    row['metY'] = metXYZ[i][1]
                    row['metZ'] = metXYZ[i][2]
                    is_ball = (
                        row['device_loc'] in PetalTransforms().dtb_device_ids)
                    if not is_ball:
                        row['Q'] = QS[i][0]
                        row['S'] = QS[i][1]
                        row['checkX'] = checkXYZ[i][0]
                        row['checkY'] = checkXYZ[i][1]
                        row['checkZ'] = checkXYZ[i][2]
                        for letter in ['X', 'Y', 'Z']:
                            row['err'+letter] = \
                                row['check'+letter] - row['met'+letter]
                    else:
                        ballXYZ = petal_trans.metXYZ_to_obsXYZ(metXYZ[i])[0]
                        row['ballX'] = ballXYZ[0]
                        row['ballY'] = ballXYZ[1]
                        row['ballZ'] = ballXYZ[2]
                        for letter in ['X', 'Y', 'Z']:
                            field = [field for field in
                                     data['focal_plane_metrology']
                                     if str(row['device_loc']) in field
                                     and letter.lower() in field][0]
                            row['check'+letter] = \
                                data['focal_plane_metrology'][field][trans_row]
                            row['err'+letter] = \
                                row['ball'+letter] - row['check'+letter]
                    writer.writerow(row)
    gui_root.withdraw()
