import os
import sys
sys.path.append(os.path.abspath('./SBIG/'))
import sbig_grab_cen
import numpy as np
import time

class FVCHandler(object):
    """Provides a generic interface to the Fiber View Camera. Can support different
    particular FVC implementations, providing a common set of functions to call
    from positioner control scripts.
    
    The order of operations for transforming from CCD coordinates to output is:
        1. rotation
        2. scale
        3. translation
    """
    def __init__(self, fvc_type='SBIG'):
        self.fvc_type = fvc_type # 'SBIG' or 'FLI'
        if self.fvc_type == 'SBIG':
            self.sbig = sbig_grab_cen.SBIG_Grab_Cen()
        self.exposure_time = 90  # ms, camera exposure time
        self.rotation = 0        # [deg] rotation angle from image plane to object plane
        self.scale = 1.0         # scale factor from image plane to object plane
        self.translation = [0,0] # translation of origin within the image plane

    def measure_and_identify(self, expected_pos_xy=[], expected_ref_xy=[]):
        """Calls for an FVC measurement, and returns a list of measured centroids.
        The centroids are in order according to their closeness to the list of
        expected xy values.

        If the expected xy are unknown, then use the measure method instead.

        INPUT:  expected_pos_xy ... list of expected positioner fiber locations
                expected_ref_xy ... list of expected fiducial positions

        OUTPUT: measured_pos_xy ... list of measured positioner fiber locations
                measured_ref_xy ... list of measured fiducial positions

        Lists of xy coordinates are of the form [[x1,y1],[x2,y2],...]
        """
        expected_xy = expected_pos_xy + expected_ref_xy
        num_objects = len(expected_xy)
        unsorted_xy = self.measure(num_objects)
        measured_xy = self.sort_by_closeness(unsorted_xy, expected_xy)
        measured_pos_xy = measured_xy[:len(expected_pos_xy)]
        measured_ref_xy = measured_xy[len(expected_pos_xy):]
        if len(measured_ref_xy) > 0:
            xy_diff = np.array(measured_ref_xy) - np.array(expected_ref_xy)
            xy_shift = np.median(xy_diff,axis=0)
            measured_pos_xy -= xy_shift
            measured_pos_xy = measured_pos_xy.tolist()
        return measured_pos_xy, measured_ref_xy

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
        return xy

    def measure(self, num_objects=1):
        """Calls for an FVC image capture, applies transformations to get the
        centroids into the units and orientation of the object plane,  and returns
        the centroids.
            xy ... list of the form [[x1,y1],[x2,y2],...]
        """
        if self.fvc_type == 'SBIG':
            xy,brightness,t = self.sbig.grab(num_objects)
        elif self.fvc_type == 'FLI':
            xy = [] # to be implemented
        else:
            xy = []
        xy_np = np.array(xy).transpose()
        rot = FVCHandler.rotmat2D_deg(self.rotation)
        xy_np = np.dot(rot, xy_np)
        xy_np *= self.scale
        translation_x = self.translation[0] * np.ones(np.shape(xy_np)[1])
        translation_y = self.translation[1] * np.ones(np.shape(xy_np)[1])
        xy_np += [translation_x,translation_y]
        xy = xy_np.transpose().tolist()
        return xy

    @staticmethod
    def rotmat2D_deg(angle):
        """Return the 2d rotation matrix for an angle given in degrees."""
        radians = np.deg2rad(angle)
        return np.array([[np.cos(radians), -np.sin(radians)], [np.sin(radians), np.cos(radians)]])

if __name__ == '__main__':
    f = FVCHandler()
    n_objects = 3
    n_repeats = 5
    xy = []
    print('start taking ' + str(n_repeats) + ' images')
    start_time = time.time()
    for i in range(n_repeats):
        xy.append(f.measure(n_objects))
        print(xy[i])
    total_time = time.time() - start_time
    print('total time = ' + str(total_time) + ' (' + str(total_time/n_repeats) + ' per image)')
