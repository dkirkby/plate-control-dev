import numpy as np
import posconstants as pc
import postransforms
import configobj

class PosCollider(object):
    """PosCollider contains geometry definitions for mechanical components of the
    fiber positioner. It provides the methods to check for collisions between
    neighboring positioners.

    See DESI-0899 for geometry specifications, illustrations, and kinematics.
    """
    def __init__(self, configfile=''):
        # load up a configobj from _collision_settings_DEFAULT.conf, in pc.settings_directory
        if not(configfile):
            configfile = '_collision_settings_DEFAULT.conf'
        filename = pc.settings_directory + configfile
        self.config = configobj.ConfigObj(filename,unrepr=True)
        self.posmodels = []
        self.load_config_data()

    def add_positioners(self, posmodels):
        """Add a positioner to the collider.
        """
        self.posmodels.append(posmodels)
        self.load_config_data()

    def load_config_data(self):
        """Reads latest versions of all configuration file offset, range, and
        polygon definitions, and updates stored values accordingly.
        """
        self.timestep = self.config['TIMESTEP']
        self.Eo = self.config['ENVELOPE_EO']
        self.Ei = self.config['ENVELOPE_EI']
        self.Ee = self.config['ENVELOPE_EE']
        self._load_keepouts()
        self._load_posparams()
        for p in self.posmodels:
            self._identify_neighbors(p)

    def collision_between(self):
        """Searches for collisions in time and space between two polygon geometries
        which are rotating according to argued move tables.
        """
        pass

    def _load_keepouts(self):
        self.keepout_P = PosPoly(self.config['KEEPOUT_PHI'], self.config['KEEPOUT_PHI_PT0'])
        self.keepout_T = PosPoly(self.config['KEEPOUT_THETA'], self.config['KEEPOUT_THETA_PT0'])
        self.keepout_PTL = PosPoly(self.config['KEEPOUT_PTL'], self.config['KEEPOUT_PTL_PT0'])
        GFA_temp = PosPoly(self.config['KEEPOUT_GFA'], self.config['KEEPOUT_GFA_PT0'])
        GFA_temp = GFA_temp.rotated(self.config['KEEPOUT_GFA_ROT'])
        GFA_temp = GFA_temp.translated(self.config['KEEPOUT_GFA_X0'],self.config['KEEPOUT_GFA_X0'])
        self.keepout_GFA = PosPoly(GFA_temp)

    def _load_posparams(self):
        n = len(self.posmodels)
        self.R1 = np.zeros(n)
        self.R2 = np.zeros(n)
        self.xy0 = np.zeros((2,n))
        self.tp0 = np.zeros((2,n))
        self.tp_ranges = [[]]*n
        for i in range(len(self.posmodels)):
            self.R1[i] = self.posmodels[i].state.read('LENGTH_R1')
            self.R2[i] = self.posmodels[i].state.read('LENGTH_R2')
            self.xy0[:,i] = np.array([self.posmodels[i].state.read('OFFSET_X'), self.posmodels[i].state.read('OFFSET_Y')])
            self.tp0[:,i] = np.array([self.posmodels[i].state.read('OFFSET_T'), self.posmodels[i].state.read('OFFSET_P')])
            self.tp_ranges[i] = np.array(self.posmodels[i].trans.shaft_ranges('targetable'))

    def _identify_neighbors(self, posmodel):
        self.pos_neighbors = []
        self.fixed_neighbors = []

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