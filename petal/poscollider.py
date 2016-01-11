import numpy as np

# Available geometry definitions (will select one version when initializing below)
DESI_0899_v4 = {'keepoutP' : [[3.967, 3.918, 3.269, 1.712, 1.313, 0.000, -1.324, -2.106, -2.106, -1.324,  0.000,  1.313,  1.712,  3.269,  3.918],
                              [0.000, 1.014, 1.583, 1.391, 1.959, 2.395,  1.959,  0.848, -0.848, -1.959, -2.395, -1.959, -1.391, -1.583, -1.014]],
                'keepoutT' : [[ 0.814,  2.083,  2.613,  4.194,  4.893, -1.902, -2.007, -1.139, -0.170],
                              [-3.236, -2.707, -2.665, -2.761, -1.168, -0.935, -2.665, -3.137, -3.332]],
                'keepoutP_point0_idx' : 12,
                'keepoutT_point0_idx' : 0
                }

class PosCollider(object):
    """PosCollider contains geometry definitions for mechanical components of the
    fiber positioner. It provides the methods to check for collisions between
    neighboring positioners.

    See DESI-0899 for geometry specifications, illustrations, and kinematics.
    """
    def __init__(self):
        geom = DESI_0899_v4
        self.keepoutP = PosPoly(geom['keepoutP'], geom['keepoutP_point0_idx'])
        self.keepoutT = PosPoly(geom['keepoutT'], geom['keepoutT_point0_idx'])


class PosPoly:
    """Represents geometry envelope definitions for mechanical components of the
    fiber positioner.
    """
    def __init__(self, points, point0_index=0):
        points = np.array(points)
        self.points = np.append(points[:,np.arange(point0_index,len(points[0]))], points[:,np.arange(0,point0_index+1)], axis=1)

    def rotated(self, angle):
        """Returns the polygon rotated by angle (unit degrees)."""
        return np.dot(rotmat2D_deg(angle), self.points)

    def translated(self, x, y):
        """Returns the polygon translaged by distance (x,y)."""
        return self.points + np.array([[x],[y]])

# 2D rotation matrix constructors
def rotmat2D_rad(angle):
    return np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
def rotmat2D_deg(angle):
    return rotmat2D_rad(np.deg2rad(angle))