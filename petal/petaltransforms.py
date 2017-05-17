import numpy as np
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
        
        QS     ... (q,s) global to focal plate, q is the angle about the optical axis, s is
                   the path distance from optical axis, along the curved focal surface, within
                   a plane that intersects the optical axis, per DESI-0742.
                   
    Once you have coordinates in the QS system, one uses methods from PosTransforms
    to convert into any other positioner-specific coordinate systems.
    """
    
    trans_keys = ['petal_offset_x','petal_offset_y','petal_offset_z','petal_rot1','petal_rot_2','petal_rot_3']

    def __init__(self, transforms={}):
        self.transforms = {0 for key in self.trans_keys}
        self.transforms.update(transforms)
        self.postrans = postransforms.PosTransforms()
    
    def metXYZ_to_QS(self,xyz):
        """Transforms list of metXYZ coordinates into QS system.
        
        INPUT:  metXYZ ... [N][3] array of [[metX0,metY0,metZ0],[metX1,metY1,metZ1],...]
        OUTPUT: [N][2] array of corresponding [[q0,s0],[q1,s1],...]
        """
        if np.ndim(xyz) == 1:
            xyz = [xyz] # for convenience if user accidentally only puts in a list of 3 vals
        xyz_trans = np.transpose(xyz) + self.trans_matrix
        xyz_rot = self.rot_matrix * xyz_trans
        xy = xyz_rot[[0,1],:]
        qs = self.postrans.obsXY_to_QS(xy.tolist())
        return np.transpose(qs).tolist()
    
    def QS_to_metXY(self,qs):
        """Transforms list of QS coordinates into metXYZ system.
        
        Note that because QS is only 2 dimensional, the Z coordinate is a nominal value
        that is looked up from the Echo22 asphere definition.
        
        INPUT:  qs ... [N][2] array of [[q0,s0],[q1,s1],...]
        OUTPUT: [N][3] array of corresponding [[metX0,metY0,metZ0],[metX1,metY1,metZ1],...]
        """
        if np.ndim(qs) == 1:
            qs = [qs] # for convenience if user accidentally only puts in a list of 3 vals
        qs = np.transpose(qs)
        xy = self.postrans.QS_to_obsXY(qs.tolist())
        r = np.sqrt(np.sum(np.power(xy,2),axis=0))
        z = pc.R2Z_lookup(r)
        xyz = np.array([xy[0],xy[1],z])
        xyz_rot = self.inverse_rot_matrix * xyz
        xyz_trans = xyz_rot + self.inverse_tran_matrix
        return np.transpose(xyz_trans).tolist()
    
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
        a = {field:np.deg2rad(angle_deg[field]) for field in angle_deg.keys()}
        c = {field:np.cos(a[field]) for field in a.keys()}
        s = {field:np.sin(a[field]) for field in a.keys()}
        
        # precession, nutation, spin interpretation of rot1, rot2, rot3
        prec = 1
        nuta = 2
        spin = 3
        rot = np.zeros([3,3])
        rot[0,0] = c[spin]*c[prec] - s[spin]*c[nuta]*s[prec]
        rot[0,1] = c[spin]*s[prec] + s[spin]*c[nuta]*c[prec]
        rot[0,2] = s[spin]*s[nuta]
        rot[1,0] = -s[spin]*c[prec] - c[spin]*c[nuta]*s[prec]
        rot[1,1] = -s[spin]*s[prec] + c[spin]*c[nuta]*c[prec]
        rot[1,2] = c[spin]*s[nuta]
        rot[2,0] = s[nuta]*s[prec]
        rot[2,1] = -s[nuta]*c[prec]
        rot[2,2] = c[nuta]
        
        return np.array(rot)
        
    @property
    def inverse_rot_matrix(self):
        """Rotations matrix as 3x3 numpy array, for going from QS --> metXYZ."""
        return np.transpose(self.rot_matrix)
    
        
if __name__ == '__main__':
    """The code below allows you to test out the transforms on a real-world set of
    report files formatted per DESI-2850.
    """
    import os
    import csv
    import tkinter
    import tkinter.filedialog
    
    gui_root = tkinter.Tk()
    initialdir = os.getenv('HOME')
    filetypes = (("CSV file","*.csv"),("All Files","*")),
    files = {key:'' for key in ['petal_metrology','focal_plane_metrology']}
    for key in files.keys():
        message = 'Select ' + key + ' file.'
        files[key] = tkinter.filedialog.askopenfilename(initialdir=initialdir, filetypes=filetypes, title=message)
        data = {}
        if files[key]:
            with open(files[key],'r',newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                data[key] = {field:[] for field in reader.fieldnames}
                for row in reader:
                    for field in reader.fieldnames:
                        data[key][field].append(float(row[field]))
    if all([key in data.keys() for key in files.keys()]):
        petal_id = data['petal_metrology']['petal_id'][0]
        n = len(data['petal_metrology']['x_meas_proj'])
        metXYZ = []
        for i in range(n):
            metXYZ.append([data['petal_metrology'][field][i] for field in ['x_meas_proj','y_meas_proj','z_meas_proj']])
        trans_row = data['focal_plane_metrology']['petal_id'].index(petal_id)
        transforms = [data['focal_plane_metrology'][field][trans_row] for field in PetalTransforms().trans_keys]
        petal_trans = PetalTransforms(transforms)
        QS = petal_trans.metXYZ_to_QS(metXYZ)
        checkXYZ = petal_trans.QS_to_metXYZ(QS)
        initialdir = os.path.split(files['petal_metrology'])[0]
        initialfile = 'results_petal_' + str(petal_id) + '.csv'
        message = 'Save results as'
        savefile = tkinter.filedialog.asksaveasfilename(initialdir=initialdir, filetypes=filetypes, title=message)
        if savefile:
            with open(savefile,'w',newline='') as csvfile:
                writer = csv.DictWriter(fieldnames=['metX','metY','metZ','Q','S','checkX','checkY', 'checkZ'])
                for i in range(n):
                    row['metX'] = metXYZ[i][0]
                    row['metY'] = metXYZ[i][1]
                    row['metZ'] = metXYZ[i][2]
                    row['Q'] = QS[i][0]
                    row['S'] = QS[i][1]
                    row['checkX'] = checkXYZ[i][0]
                    row['checkY'] = checkXYZ[i][1]
                    row['checkZ'] = checkXYZ[i][2]
    gui_root.withdraw()
    