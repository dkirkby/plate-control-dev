import sbig_grab_cen
import numpy as np

class FVCHandler(object):
    """Provides function interface to the Fiber View Camera. Can support different
    particular FVC implementations, providing a common set of functions to call
    from positioner control scripts. Provides distinction of reference fiducials.
    """
    def __init__(self, fvc_type='SBIG'):
        self.fvc_type = fvc_type   # 'SBIG' or 'FLI'
        self.exposure_time = 90 # ms, camera exposure time
        self.translation = [0,0] # translation of origin within the image plane
        self.scale = 0.015       # scale factor from image plane to object plane
        self.rotation = 0        # [deg] rotation angle from image plane to object plane

    def measure_and_identify(self, expected_xy=[]):
        """Calls for an FVC measurement, and returns a list of measured centroids.
        The centroids are in order according to their closeness to the list of
        expected xy values.
        """
        num_objects = len(expected_xy)
        measured_xy = self.measure(num_objects)
        sorted_xy = self.sort_by_closeness(measured_xy, expected_and_ref)
        return sorted_xy

    def sort_by_closeness(self, unknown_xy, expected_xy):
        """Sorts the list unknown_xy so that each point is at the same index
        as its closest-distance match in the list expected_xy.
        """
        xy = []
        u = np.array(unknown_xy)
        for e in expected_xy:
            delta = u - e
            dist = np.sqrt(np.sum(delta**2,axis=1))
            closest = u[np.argmin(dist),:]
            xy.append(closest.tolist())

    def measure(self, num_objects=1):
        """Calls for an FVC image capture, applies transformations to get the
        centroids into the units and orientation of the object plane,  and returns
        the centroids.
            xy ... list of the form [[x1,y1],[x2,y2],...]
        """
        if self.fvc_type == 'SBIG':
            xywin,brightness,t = sbig_grab_cen.sbig_grab_cen(self.exposure_time, num_objects)
            xy = [[row[0],row[1]] for row in xywin]
        elif self.fvc_type == 'FLI':
            xy = [] # to be implemented
        else:
            xy = []
        xy_np = np.array(xy).transpose()
        xy_np += self.translation
        xy_np *= self.scale
        xy_np = np.dot(FVCHandler._rotmat2D_deg(self.rotation), xy)
        xy = xy_np.tolist()
        return xy

    @staticmethod
    def _rotmat2D_rad(angle):
        """Return the 2d rotation matrix for an angle given in radians."""
        return np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])

    @staticmethod
    def _rotmat2D_deg(angle):
        """Return the 2d rotation matrix for an angle given in degrees."""
        return PosPoly._rotmat2D_rad(np.deg2rad(angle))