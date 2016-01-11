import numpy as np
import postransforms

class PosCollider(object):
    """PosCollider contains geometry definitions for mechanical components of the
    fiber positioner. It provides the methods to check for collisions between
    neighboring positioners.

    See DESI-0899 for geometry specifications, illustrations, and kinematics.
    """
    def __init__(self):
        self.timestep = 0.1 # [sec] time increment for collision checking (put in config file?)
        self.posmodels = []
        self.R1 = []
        self.R2 = []
        self.xy0 = []
        self.tp0 = []
        self.tp_ranges = []
        self.Eo = 9.xxx
        self.Ei = 6.xxx
        self.keepoutP = PosPoly([])
        self.keepoutT = PosPoly([])
        self.fixed_keepouts = [] # for GFA, petal edge, and any other fixed keepout locations

    def add_positioner(self, posmodel):
        """Add a positioner to the collider.
        """
        #xxx self.posgeoms.append(PosGeom(posmodel))

    def refresh_geometry_configs(self):
        """Reads latest versions of all configuration file offset, range, and
        polygon definitions, and updates the positioner geometries accordingly.
        """
        for p in posgeoms:
            # loopify
            keepoutP_points = [self.posmodel.state.read('KEEPOUT_PHI_X'),   self.posmodel.state.read('KEEPOUT_PHI_Y')]
            keepoutT_points = [self.posmodel.state.read('KEEPOUT_THETA_X'), self.posmodel.state.read('KEEPOUT_THETA_Y')]
            keepoutP_start_idx = self.posmodel.state.read('KEEPOUT_PHI_PT0')
            keepoutT_start_idx = self.posmodel.state.read('KEEPOUT_THETA_PT0')
            self.keepoutP = PosPoly(keepoutP_points, keepoutP_start_idx)
            self.keepoutT = PosPoly(keepoutT_points, keepoutT_start_idx)
            self.R1 = self.posmodel.state.read('LENGTH_R1')
            self.R2 = self.posmodel.state.read('LENGTH_R2')
            self.xy0 = np.array([self.posmodel.state.read('OFFSET_X'), self.posmodel.state.read('OFFSET_Y')])
            self.tp0 = np.array([self.posmodel.state.read('OFFSET_T'), self.posmodel.state.read('OFFSET_P')])
            self.tp_ranges = np.array(posmodel.trans.shaft_ranges('targetable'))

    def collision_between(self):
        """Searches for collisions in time and space between two polygon geometries
        which are rotating according to argued move tables.
        """
        pass

class PosPoly(object):
    """Represents a polygonal envelope definition for a mechanical component of
    the fiber positioner.
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