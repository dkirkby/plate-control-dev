import sbig_grab_cen
import numpy as np

class FVCHandler(object):
    """Provides a generic interface to the Fiber View Camera. Can support different
    particular FVC implementations, providing a common set of functions to call
    from positioner control scripts.
    """
    def __init__(self, fvc_type='SBIG'):
        self.fvc_type = fvc_type   # 'SBIG' or 'FLI'
        self.exposure_time = 90 # ms, camera exposure time
        self.translation = [0,0] # translation of origin within the image plane
        self.scale = 0.015       # scale factor from image plane to object plane
        self.rotation = 0        # [deg] rotation angle from image plane to object plane

    def measure_and_identify(self, expected_xy):
        """Calls for an FVC measurement, and returns a list of measured centroids.
        The centroids are in order according to their closeness to the list of
        expected xy values. If expected_xy are unknown, then argue just the number
        of centroids expected instead (not a list).

        input:  expected_xy ... list of the form [[x1,y1],[x2,y2],...] OR
                                one integer, the total number expected centroids
        """
        if isinstance(expected_xy, list):
            num_objects = len(expected_xy)
            measured_xy = self.measure(num_objects)
            xy = self.sort_by_closeness(measured_xy, expected_xy)
        else:
            num_objects = expected_xy
            xy = self.measure(num_objects)
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
        rot = FVCHandler.rotmat2D_deg(self.rotation)
        xy_np = np.dot(rot, xy)
        xy = xy_np.tolist()
        return xy

    @staticmethod
    def rotmat2D_deg(angle):
        """Return the 2d rotation matrix for an angle given in degrees."""
        radians = np.deg2rad(angle)
        return np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])
