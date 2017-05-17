import numpy as np
import posconstants as pc
import posmodel

class PetalTransforms(object):
    """This class provides transformations between individual petal metrology data and
	the global focal plane coordinate system. The key document defining the metrology
	data meaning and formatting is DESI-2850, which one should definitely read.

    The coordinate systems are:

        meas_proj_xyz  ... 
		
		ptlXYZ ... (x,y,z) measured device locations on the aspheric focal surface,
		                   local to an individual petal, with some arbitrary origin
						   
		petal_trans_xyz ... (x0,y0,z0) translational offsets and (rot1,rot2,rot3)  
		
        obsXY  ... (x,y) global to focal plate, centered on optical axis, looking at fiber tips
        posTP  ... (theta,phi) internally-tracked expected position of gearmotor shafts at output of gear heads
        obsTP  ... (theta,phi) expected position of fiber tip including offsets
        QS     ... (q,s) global to focal plate, q is angle about the optical axis, s is path distance from optical axis, along the curved focal surface, within a plane that intersects the optical axis
        flatXY ... (x,y) global to focal plate, with focal plate slightly stretched out and flattened (used for anti-collision)

    The fundamental transformations provided are:

        obsTP <--> posTP
        posTP <--> posXY
        posXY <--> obsXY
        obsXY <--> QS
        QS    <--> flatXY

    Additionally, some composite transformations are provided for convenience of syntax:

        posTP <--> obsXY
        posTP <--> QS
        posTP <--> flatXY
        obsXY <--> flatXY
        obsTP <--> flatXY

    These can be chained together in any order to convert among the various coordinate systems.

    The theta axis has a physical travel range wider than +/-180 degrees. Simple vector addition
    and subtraction is not sufficient when delta values cross the theta hardstop near +/-180.
    Therefore special methods are provided for performing addition and subtraction operations
    between two points, with angle-wrapping logic included.

        delta_posTP  ... is like dtdp = tp1 - tp0
        delta_obsTP
        addto_posTP  ... is like tp1 = tp0 + dtdtp
        addto_obsTP

    To round out the syntax, similar delta_ and addto_ methods are provided for the other
    coordinate systems. These are convenicence methods to do the vector subtraction or addition.

    Note in practice that the coordinate S is similar, but not identical, to the radial distance
    R from the optical axis. This similarity is because the DESI focal plate curvature is gentle.
    See DESI-0530 for detail on the (Q,S) coordinate system.
    """

    def __init__(self, this_posmodel=None):