import numpy as np
cimport numpy as np

# Type definitions for cython
FLOAT = np.float # defined at Python run time
ctypedef np.float_t FLOAT_t # defined at C compile time (note numpy.float_t is built-in to Numpy's cython headers)
ctypedef np.ndarray[FLOAT_t,ndim=2] FLOAT2D_t # buffer syntax for efficient indexing

# Available geometry definitions (will select one version when initializing below)
cdef struct DESI_0899_v4:
    cdef FLOAT2D_t keepoutP = np.array([[3.967, 3.918, 3.269, 1.712, 1.313, 0.000, -1.324, -2.106, -2.106, -1.324,  0.000,  1.313,  1.712,  3.269,  3.918],
                                        [0.000, 1.014, 1.583, 1.391, 1.959, 2.395,  1.959,  0.848, -0.848, -1.959, -2.395, -1.959, -1.391, -1.583, -1.014]],
                                       dtype=FLOAT)
    cdef FLOAT2D_t keepoutT = np.array([[ 0.814,  2.083,  2.613,  4.194,  4.893, -1.902, -2.007, -1.139, -0.170],
                                        [-3.236, -2.707, -2.665, -2.761, -1.168, -0.935, -2.665, -3.137, -3.332]],
                                       dtype=FLOAT)
    cdef int keepoutP_point0_idx = 12
    cdef int keepoutT_point0_idx = 0

# 2D rotation matrix constructors
cdef inline FLOAT2D_t rotmat2D_rad(FLOAT_t angle) = np.array([np.cos(angle), -np.sin(angle), np.sin(angle), np.cos(angle)], dtype=FLOAT)
cdef inline FLOAT2D_t rotmat2D_deg(FLOAT_t angle) = rotmat2D_rad(np.deg2rad(angle))

def class PosCollider:
    """PosCollider contains geometry definitions for mechanical components of the
    fiber positioner. It provides the methods to check for collisions between
    neighboring positioners.

    See DESI-0899 for geometry specifications, illustrations, and kinematics.
    """
    cdef FLOAT2D_t keepoutP, keepoutT

    def __init__(self):
        cdef struct geom = DESI_0899_v4
        self.keepoutP = PosPoly(geom.keepoutP, geom.keepoutP_point0_idx)
        self.keepoutT = PosPoly(geom.keepoutT, geom.keepoutT_point0_idx)


cdef class PosPoly:
    """Represents geometry envelope definitions for mechanical components of the
    fiber positioner.
    """
    cdef FLOAT2D_t points, original_points
    cdef unsigned int point0_index

    def __cinit__(self, FLOAT2D_t points not None, unsigned int point0_index=0 not None):
        self.original_points = points
        self.point0_index = point0_index

    property point0_index:
        def __get__(self):
            return self.point0_index

        def __set__(self, value):
            self.point0_index = value
            self.points = np.append(self.original_points[:,np.arange(self.point0_index,len(keepoutP[0]))],
                                    self.original_points[:,np.arange(0,self.point0_index+1)],
                                    axis=1)

        def __del__(self):
            del self.point0_index = 0

    cdef FLOAT2D_t rotated(PosPoly self, FLOAT_t angle):
        """Returns the polygon rotated by angle (unit degrees)."""
        if angle is None:
            print('argument was None')
            return np.zeros_like(self.points)
        return np.dot(rotmat2D_deg(angle), self.points)

    cdef FLOAT2D_t translated(PosPoly self, FLOAT_t x, FLOAT_t y):
        """Returns the polygon translaged by distance (x,y)."""
        if x is None or y is None:
            print('argument was None')
            return np.zeros_like(self.points)
        return self.points + np.array([[x],[y]],dtype=FLOAT)

