class FidArrayMaster(object):
    """Maintains a list of fiducials and provides the functions to control them.

    initialize with:
        fid_ids ... list of fiducials ids -- as of April 2016, these are just CAN ids
        comm    ... petalcomm communication object

    As of April 2016, the implementation is kept as simple as possible, for the
    purpose of running test stands only. Later implementations should track
    physical hardware by unique id number, log expected and measured positions,
    log cycles and total on time, etc.
    """
    def __init__(self, fid_ids, comm):
        self.comm = comm
        self.can_ids = fid_ids
        self.duty_percent = 50 # 0-100
        self.duty_period  = 55 # milliseconds
        self.obsXY = [] # list of locations of the dots in the obsXY coordinate system

    def all_on(self):
        """Turn all fiducials on at their default settings.
        """
        duty_percents = [self.duty_percent]*len(self.can_ids)
        duty_periods = [self.duty_period]*len(self.can_ids)
        self.comm.set_fiducials(self.can_ids, duty_percents, duty_periods)

    def all_off(self):
        """Turn all fiducials off.
        """
        duty_percents = [0]*len(self.can_ids)
        duty_periods = [self.duty_period]*len(self.can_ids)
        self.comm.set_fiducials(self.can_ids, duty_percents, duty_periods)
