class PetalComm(object):
    """Handles communication between petal software running on floor control computers
    and petalbox software running on the petal.
    """

def __init(self):
    pass

def send_tables(self, move_tables):
    """Sends move tables for positioners over ethernet to the petal controller,
    where they are then sent over CAN to the positioners. See method
    "hardware_ready_move_tables" in class PosArrayMaster for definition of the
    move_tables format.
    """
    pass

def execute_moves_hard_sync(self):
    """Send the command to synchronously begin move sequences to all positioners
    on the petal simultaneously. Uses the hardware sync pin as the start signal.
    """
    pass

def execute_moves_soft_sync(self):
    """Send the command to synchronously begin move sequences to all positioners,
    using CAN command as the start signal.
    """
    pass

def set_pos_constants(self, posids, settings):
    """Send settings over ethernet to the petal controller, where they are
    sent over CAN to the positioners identified the list 'posids', with the setting
    values in the corresponding (dictionary? list of dicts?) 'settings'.
    """
    pass

def set_fiducials(self, ids, percent_duty, duty_period):
    """Send settings over ethernet to the petal controller, where they are
    sent over CAN to the fiducials. Sets the fiducials identified by the list ids
    to the corresponding duty values.
        ids          ... list of fiducial ids
        percent_duty ... list of values, 0-100, 0 means off
        duty_period  ... list of values, ms, time between duty cycles
    """
    pass

def set_device(self, id, key, value):
    """Set a value on a device other than positioners or fiducials. This includes
    fans, power supplies, and sensors.
    """
    pass

def get_pos_status(self):
    """Returns a (dictionary?) containing status of all positioners on the petal.
    """
    # (to-do)
    return status

def get_fid_status(self):
    """Returns a (dictionary?) containing status of all fiducials on the petal.
    """
    # (to-do)
    return status

def get_device_status(self):
    """Returns a (dictionary?) containing status of all devices other than positioners
    and fiducials on the petal. This includes fans, power supplies, and sensors.
    """
    # (to-do)
    return status