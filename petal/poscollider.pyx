import numpy as np
cimport numpy as np

# Type definitions for cython
FLOAT = np.float # run time
ctypedef np.float_t FLOAT_t # compile time

# Polygon geometry definitions (will select one version below)
cdef struct geometry_v4:
    cdef np.ndarray keepoutP = np.array([[3.967, 3.918, 3.269, 1.712, 1.313, 0.000, -1.324, -2.106, -2.106, -1.324,  0.000,  1.313,  1.712,  3.269,  3.918],
                                         [0.000, 1.014, 1.583, 1.391, 1.959, 2.395,  1.959,  0.848, -0.848, -1.959, -2.395, -1.959, -1.391, -1.583, -1.014]],
                                        dtype=FLOAT)
    cdef np.ndarray keepoutT = np.array([[ 0.814,  2.083,  2.613,  4.194,  4.893, -1.902, -2.007, -1.139, -0.170],
                                         [-3.236, -2.707, -2.665, -2.761, -1.168, -0.935, -2.665, -3.137, -3.332]],
                                        dtype=FLOAT)
    cdef int keepoutP_first_idx = 12
    cdef int keepoutT_first_idx = 0

# Compiled-in selection of which geometry definitions to use.
cdef struct gsel = geometry_v4

# Copy over the desired geometry data. Keepout polygons are shifted to the desired
# first index (may slightly speed up gap-checking algorithm) and closed.
cdef struct g:
    cdef np.ndarray keepoutP = np.append(gsel.keepoutP[:,np.arange(gsel.keepoutP_first_idx,len(keepoutP[0]))], gsel.keepoutP[:,np.arange(0,gsel.keepoutP_first_idx+1)], axis=1)
    cdef np.ndarray keepoutT = np.append(gsel.keepoutT[:,np.arange(gsel.keepoutT_first_idx,len(keepoutT[0]))], gsel.keepoutT[:,np.arange(0,gsel.keepoutT_first_idx+1)], axis=1)

def class PosCollider:
    """PosCollider contains geometry definitions for mechanical components of the
    fiber positioner. It provides the methods to check for collisions between
    neighboring positioners.

    See DESI-0899 for geometry specifications, illustrations, and kinematics.
    """






