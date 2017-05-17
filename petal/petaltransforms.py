import numpy as np
import postransforms

class PetalTransforms(object):
    """This class provides transformations between petal metrology data and the
    global focal plane coordinate system. The key document defining the metrology
    data meaning and formatting is DESI-2850.
    
    There is a 6 DOF rigid-body transformation that takes any given petal's metXYZ into
    the global system. It is defined by six parameters, which are reported per petal
    also according to DESI-2850. The method provided in this class contains the
    canonical order of operations to do this transform.
    
    In use, you maek one instance of PetalTransforms per petal. A given instance of
    needs to either be initialized with these 6 transform values, or else be provided
    a specific file location where to look these up.

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

    
    This class also provides methods for reading in the CSV metrology report files
    and writing out the transformed results, so that they can be easily checked / tested.
    """

    def __init__(self, focal_plane_metrology_file='', transform={}):
        self.trans_keys = ['petal_offset_x','petal_offset_y','petal_offset_z','petal_rot1','petal_rot_2','petal_rot_3']
        self.petal_offset_x = petal_offset_x
        self.petal_offset_y = petal_offset_y
        self.petal_offset_z = petal_offset_y
        pass
    
    def metXYZ_to_QS(xyz,transforms):
        """Transforms list of metXYZ coordinates into QS.
        INPUTS:
            metXYZ     ... [N][3] array of [[metX0,metY0,metZ0],[metX1,metY1,metZ1],...]
            transforms ... [offset_x,offset_y,offset_z,rot_1,rot_,rot_3]
        
        OUTPUT:
            [N][2] list of corresponding [[q0,s0],[q1,s1],...]
        """
        pass
    
    def QS_to_metXYZ(qs,transforms)