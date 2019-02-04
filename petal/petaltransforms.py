import numpy as np
import math
import postransforms
import posconstants as pc

class PetalTransforms(object):
    """This class provides transformations between petal metrology data and the
    global focal plane coordinate system. The key document defining the metrology
    data meaning and formatting is DESI-2850.
    
    There is a 6 DOF rigid-body transformation that takes any given petal's metXYZ into
    the global system. It is defined by six parameters, which are reported per petal
    also according to DESI-2850. The method provided in this class contains the
    canonical order of operations to do this transform.
    
    In use, you make one instance of PetalTransforms per petal. A given instance of
    needs to be initialized with these 6 transform values, provided in a dictionary
    with the following keys:
        
        'petal_offset_x','petal_offset_y','petal_offset_z','petal_rot1','petal_rot_2','petal_rot_3'

    The coordinate systems are:
        
        metXYZ ... (x,y,z) measured device center locations on the aspheric focal surface,
                   local to an individual petal, with some arbitrary origin for each petal.
                   These are the reported values from the metrology, called x_meas_proj,
                   y_meas_proj, and z_meas_proj in the report file, per DESI-2850.
                   
        obsXYZ ... (x,y,z) global cartesian coordinates on the focal plate
                   cenetered on optical axis, looking at fiber tips
        
        QS     ... (q,s) global coordinates on the focal plate, per DESI-0742
                   q is the angle about the optical axis
                   s is the path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
                   
    Once you have coordinates in the QS system, one uses methods from PosTransforms
    to convert into any other positioner-specific coordinate systems.
    """
    
    trans_keys = ['petal_offset_x','petal_offset_y','petal_offset_z','petal_rot_1','petal_rot_2','petal_rot_3']
    tooling_ball_locs = [543,544,545]

    def __init__(self, transforms={}):
        self.transforms = {key:0 for key in self.trans_keys}
        self.transforms.update(transforms)
        self.postrans = postransforms.PosTransforms(this_posmodel=None, curved=True)
    
    def metXYZ_to_QS(self,xyz):
        """Transforms list of metXYZ coordinates into QS system.
        INPUT:  [N][3] array of [[metX0,metY0,metZ0],[metX1,metY1,metZ1],...]
        OUTPUT: [N][2] array of corresponding [[q0,s0],[q1,s1],...]
        """
        obsXYZ = self.metXYZ_to_obsXYZ(xyz)
        qs = self.obsXYZ_to_QS(obsXYZ)
        return qs

    def QS_to_metXYZ(self,qs):
        """Transforms list of QS coordinates into metXYZ system.
        INPUT:  [N][2] array of [[q0,s0],[q1,s1],...]
        OUTPUT: [N][3] array of corresponding [[metX0,metY0,metZ0],[metX1,metY1,metZ1],...]

        Note that because QS is only 2 dimensional, the Z coordinate is a nominal value
        that is looked up from the Echo22 asphere definition.
        """
        obsXYZ = self.QS_to_obsXYZ(qs)
        metXYZ = self.obsXYZ_to_metXYZ(obsXYZ)
        return metXYZ

    def metXYZ_to_obsXYZ(self,xyz):
        """Transforms list of metXYZ coordinates into obsXYZ system.
        INPUT:  [N][3] array of [[metX0,metY0,metZ0],[metX1,metY1,metZ1],...]
        OUTPUT: [N][3] array of corresponding [[obsX0,obsY0,obsZ0],[obsX1,obsY1,obsZ1],...]
        """
        xyz = self.listify(xyz)
        xyz_trans = np.transpose(xyz) + self.trans_matrix
        xyz_rot = np.dot(self.rot_matrix,xyz_trans)
        return np.transpose(xyz_rot).tolist()

    def obsXYZ_to_metXYZ(self,xyz):
        """Transforms list of obsXYZ coordinates into metXYZ system.
        INPUT:  [N][3] array of [[obsX0,obsY0,obsZ0],[obsX1,obsY1,obsZ1],...]
        OUTPUT: [N][3] array of corresponding [[metX0,metY0,metZ0],[metX1,metY1,metZ1],...]
        """
        xyz = np.transpose(self.listify(xyz))
        xyz_rot = np.dot(self.inverse_rot_matrix,xyz)
        xyz_trans = xyz_rot + self.inverse_tran_matrix
        return np.transpose(xyz_trans).tolist()

    def obsXYZ_to_QS(self,xyz):
        """Transforms list of obsXYZ coordinates into QS system.
        INPUT:  [N][3] array of [[obsX0,obsY0,obsZ0],[obsX1,obsY1,obsZ1],...]
        OUTPUT: [N][2] array of corresponding [[q0,s0],[q1,s1],...]
        """
        xyz = self.listify(xyz)
        x = [xyz[i][0] for i in range(len(xyz))]
        y = [xyz[i][1] for i in range(len(xyz))]
        qs = self.postrans.obsXY_to_QS([x,y])
        return np.transpose(qs).tolist()
        
    def QS_to_obsXYZ(self,qs):
        """Transforms list of obsXYZ coordinates into QS system.
        INPUT:  [N][2] array of [[q0,s0],[q1,s1],...]
        OUTPUT: [N][3] array of corresponding [[obsX0,obsY0,obsZ0],[obsX1,obsY1,obsZ1],...]

        Note that because QS is only 2 dimensional, the Z coordinate is a nominal value
        that is looked up from the Echo22 asphere definition.
        """
        qs = self.listify(qs)
        xy = [self.postrans.QS_to_obsXY(this_qs) for this_qs in qs]
        r = np.sqrt(np.sum(np.power(xy,2),axis=1))
        z = pc.R2Z_lookup(r)
        xyz = [[xy[i][0], xy[i][1], z[i]] for i in range(len(xy))]
        return xyz
        
    @property
    def trans_matrix(self):
        """Translations matrix as 3x1 numpy array, for going from metXYZ --> QS."""
        offsets = [[self.transforms['petal_offset_' + c]] for c in ['x','y','z']]
        return np.array(offsets)
    
    @property
    def inverse_tran_matrix(self):
        """Translations matrix as 3x1 numpy array, for going from QS --> metXYZ."""
        return -self.trans_matrix
        
    @property
    def rot_matrix(self):
        """Rotations matrix as 3x3 numpy array, for going from metXYZ --> QS."""
        angle_deg = {field:self.transforms['petal_rot_' + str(field)] for field in [1,2,3]}
        a = {field:angle_deg[field]*pc.rad_per_deg for field in angle_deg}
        c = {field:math.cos(a[field]) for field in a}
        s = {field:math.sin(a[field]) for field in a}
        prec = [[c[1],-s[1],0],[s[1],c[1],0],[0,0,1]]
        nuta = [[c[2],0,s[2]],[0,1,0],[-s[2],0,c[2]]]
        spin = [[c[3],-s[3],0],[s[3],c[3],0],[0,0,1]]
        rot = np.dot(prec,np.dot(nuta,spin)) # ordered as extrinsic rots
        return np.array(rot)
        
    @property
    def inverse_rot_matrix(self):
        """Rotations matrix as 3x3 numpy array, for going from QS --> metXYZ."""
        return np.transpose(self.rot_matrix)
    
    @staticmethod
    def listify(x):
        """For convenience if user accidentally only puts in a list of 3 vals."""
        if np.ndim(x) == 1:
            x = [x]        
        return x
    
if __name__ == '__main__':
    """The code below allows you to test out the transforms on a real-world set of
    report files formatted per DESI-2850.
    """
    import os
    import csv
    import tkinter
    import tkinter.filedialog
    
    gui_root = tkinter.Tk()
    initialdir = os.getcwd()
    filetypes = (("CSV file","*.csv"),("All Files","*")),
    files = {key:'' for key in ['petal_metrology','focal_plane_metrology']}
    data = {}
    for key in files:
        message = 'Select ' + key + ' file.'
        files[key] = tkinter.filedialog.askopenfilename(initialdir=initialdir, filetypes=filetypes, title=message)
        if files[key]:
            with open(files[key],'r',newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                data[key] = {field:[] for field in reader.fieldnames}
                for row in reader:
                    for field in reader.fieldnames:
                        data[key][field].append(float(row[field]))
        initialdir = os.path.split(files[key])[0]
    if all([key in data for key in files]):
        petal_id = data['petal_metrology']['petal_id'][0]
        n = len(data['petal_metrology']['x_meas_proj'])
        metXYZ = []
        for i in range(n):
            this_xyz = [data['petal_metrology'][field][i] for field in ['x_meas_proj','y_meas_proj','z_meas_proj']]
            metXYZ.append(this_xyz)
        trans_row = data['focal_plane_metrology']['petal_id'].index(petal_id)
        transforms = {field:data['focal_plane_metrology'][field][trans_row] for field in PetalTransforms().trans_keys}
        petal_trans = PetalTransforms(transforms)
        QS = petal_trans.metXYZ_to_QS(metXYZ)
        checkXYZ = petal_trans.QS_to_metXYZ(QS)
        initialdir = os.path.split(files['petal_metrology'])[0]
        initialfile = 'results_petal_' + str(int(petal_id)) + '.csv'
        message = 'Save results as'
        savefile = tkinter.filedialog.asksaveasfilename(initialdir=initialdir, initialfile=initialfile, filetypes=filetypes, title=message)
        if savefile:
            with open(savefile,'w',newline='') as csvfile:
                writer = csv.DictWriter(csvfile,fieldnames=['device_loc','metX','metY','metZ','Q','S','ballX','ballY','ballZ','checkX','checkY', 'checkZ','errX','errY','errZ'])
                writer.writeheader()
                for i in range(n):
                    row = {}
                    row['device_loc'] = int(data['petal_metrology']['device_loc'][i])
                    row['metX'] = metXYZ[i][0]
                    row['metY'] = metXYZ[i][1]
                    row['metZ'] = metXYZ[i][2]
                    is_ball = row['device_loc'] in PetalTransforms().tooling_ball_locs
                    if not is_ball:
                        row['Q'] = QS[i][0]
                        row['S'] = QS[i][1]
                        row['checkX'] = checkXYZ[i][0]
                        row['checkY'] = checkXYZ[i][1]
                        row['checkZ'] = checkXYZ[i][2]
                        for letter in ['X','Y','Z']:
                            row['err'+letter] = row['check'+letter] - row['met'+letter]
                    else:
                        ballXYZ = petal_trans.metXYZ_to_obsXYZ(metXYZ[i])[0]
                        row['ballX'] = ballXYZ[0]
                        row['ballY'] = ballXYZ[1]
                        row['ballZ'] = ballXYZ[2]
                        for letter in ['X','Y','Z']:
                            field = [field for field in data['focal_plane_metrology'] if str(row['device_loc']) in field and letter.lower() in field][0]
                            row['check'+letter] = data['focal_plane_metrology'][field][trans_row]
                            row['err'+letter] = row['ball'+letter] - row['check'+letter]
                    writer.writerow(row)
    gui_root.withdraw()
    
