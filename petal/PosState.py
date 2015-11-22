# imports here

class PosState(object):
    """State variables for the positioner are generally stored, accessed,
    and queried through this class. The approach has been to put any
    parameters which may vary from positioner to positioner in this
    single object. Data structure is kept to a straightforward single
    key / single value scheme.
    """
    
    def __init__(self):
        pass