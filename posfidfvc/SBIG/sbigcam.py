'''
sbigcam.py 
March 2016

Author: Kevin Fanning (kfanning@umich.edu) referencing sbigudrv.h

Requires: ctypes*, platform*, numpy, pyfits, time*
*Refers to packages in Python's Standard Library

1.  you need to install the SBIG driver (libsbigudrv.so) to /usr/local/lib. 
    Drivers for ARM, 32-bit and 64 bit Intel processors are in the 
    svn (focalplane/test_stand_control/trunk/camera_code/SBIG_dev).
2.  copy 51-sbig-debian.rules into /etc/udev/rules.d 
    (the rules file is also in the SBIG_Dev directory)
3.  point LD_LIBRARY_PATH to /usr/local/lib

Function:   When run as main, takes image from SBIG camera and 
            saves it as FITS file.

As module:  imports a class with many memeber functions allowing for 
            the control of an SBIG camera.
            First, import this by typing import SBIG, then create
            a camera object using object = SBIG.CAMERA().
            From here you have several member functions that are called
            using object.function(args), where object is your object's name,
            funtion is the funtion namem and args are any arguments
            the function might take.

There are several changable settings for an object:
 
The image resolution is set to 3352x2532 pixels by default as that is
the resolution STF-8300M. This can be changed by calling
set_resolution(width, height), where width and height are integer arguments.

The image is an exposure by default but can be set to a dark image by
calling object.SetDark(x) where ideally x is 0 (exposure) or 1 (dark image), 
but the function casts x as a bool to be safe.

The exposure time is 90ms by default, the shortest time that can be used. 
This can be changed by calling set_exposure(time) command where time is 
the exposure time in milliseconds. The longest exposure time avalible
is 3600000ms (1 hour). 

NOTE: Please use the setter functions rather than manually changing 
the object's elements, since the  setter functions cast the values 
into ctype values that are required for many of the camera commands.

The typical sequence for taking an exposure is as follows:
    import sbigcam
    cam = sbigcam.SBIGCam()
    cam.open_camera()
    cam.select_camera('ST8300')
    cam.set_exposure_time(100)
    cam.set_dark(False)
    image=cam.start_exposure()
    cam.write_fits(image,'Image.FITS')
    cam.close_camera()

Changelog:

160317-MS:  converted to python3 (print statements, raw_input)

160325-MS   renamed to sbigcam.py
            renamed methods to comply with Python convention
            added error checking, added method to write FITS file 
            
160424-MS   fixed exposure time error. The exposureTime item is in
            1/100 seconds (and not in msec)
            implemented fast readout mode (set_fast_mode)
            implemented window mode (set_window_mode)

160506-MS   added 'verbose=False' to constructor
            allowed exposure times of less than 90 ms (needed for bias frames)
            set default exposure time to 0
            Note: this will still be overwritten by the camera's FW for
            non-dark frames.

160721-dyt  added EndReadoutParams for reducing readout noice by freezing TEC.
            fixed bug when open_camera and close_camera are called repeatedly
            and return false.
            adding temperature regulation and query.
            it's best to enable auto_freeze, regulation mode 5.

160722-dyt  added self.CameraName to differentiate STF-8300M and ST-i cameras
            for customising features.
            added self.keepShutterOpen boolean flag for tests that require
            open shutter.
            going to add force shutter open and close methods.

'''

from ctypes import CDLL, byref, Structure, c_bool, c_ushort, c_ulong, c_double, c_int
from platform import system
import numpy as np
from astropy.io import fits
import time
import sys

class SBIGCam(object):

    # Structures defined in sbigudrv.h
    class OpenDeviceParams(Structure):
        _fields_ = [('deviceType',                      c_ushort),
                    ('lptBaseAddress',                  c_ushort),
                    ('ipAddress',                       c_ulong)]
                    
    class EstablishLinkResults(Structure):
        _fields_ = [('cameraType',                      c_ushort)]
        
    class EstablishLinkParams(Structure):
        _fields_ = [('sbigUseOnly',                     c_ushort)]
                    
    class StartExposureParams2(Structure):
        _fields_ = [('ccd',                             c_ushort),
                    ('exposureTime',                    c_ulong),
                    ('abgState',                        c_ushort),
                    ('openShutter',                     c_ushort),
                    ('readoutMode',                     c_ushort),
                    ('top',                             c_ushort),
                    ('left',                            c_ushort),
                    ('height',                          c_ushort),
                    ('width',                           c_ushort)]
                    
    class EndExposureParams(Structure):
        _fields_ = [('ccd',                             c_ushort)]
        
    class StartReadoutParams(Structure):
        _fields_ = [('ccd',                             c_ushort),
                    ('readoutMode',                     c_ushort),
                    ('top',                             c_ushort),
                    ('left',                            c_ushort),
                    ('height',                          c_ushort),
                    ('width',                           c_ushort)]
                    
    class ReadoutLinesParams(Structure):
        _fields_ = [('ccd',                             c_ushort),
                    ('readoutMode',                     c_ushort),
                    ('pixelStart',                      c_ushort),
                    ('pixelLength',                     c_ushort)]

    class EndReadoutParams(Structure):
        _fields_ = [('ccd',                             c_ushort)]
    
    class QueryCommandStatusParams(Structure):
        _fields_ = [('command',                         c_ushort)]
    
    class QueryCommandStatusResults(Structure):
        _fields_ = [('status',                          c_ushort)]
  
<<<<<<< .mine
    class SetTemperatureRegulationParams2(Structure):
        _fields_ = [('regulation',                      c_int),
                    ('ccdSetpoint',                     c_double)]
||||||| .r5271
	class SetTemperatureRegulationParams2(Structure):
		_fields_ = [('regulation', c_int),
					('ccdSetpoint', c_double)]
	
	#Enumerated values taken from sbigudrv.h
	CC_OPEN_DRIVER = 17
	CE_NO_ERROR = 0
	CC_CLOSE_DRIVER = 18
	CC_OPEN_DEVICE = 27
	CC_CLOSE_DEVICE = 28
	CC_ESTABLISH_LINK = 9
	CC_START_EXPOSURE2 = 50
	CC_END_EXPOSURE = 2
	CC_START_READOUT = 35
	CC_READOUT_LINE = 3
	CC_QUERY_COMMAND_STATUS = 12
	CC_SET_TEMPERATURE_REGULATION2 = 51
	CCD_IMAGING = 0
	SC_CLOSE_SHUTTER = 2
	SC_OPEN_SHUTTER = 1
	RM_1X1 = 0
	ABG_LOW7 = 1
	EXP_FAST_READOUT = 0x08000000	
	
	def __init__(self,verbose=False):
		self.DARK = 0 #Defaults to 0
		self.exposure = 0 # units 1/100 second (minimum exposure is 0.09 seconds)
		self.TOP = c_ushort(0)
		self.LEFT = c_ushort(0)
		self.FAST = 0
		#self.cam_model=cam_model
		self.WIDTH = 0
		self.HEIGHT = 0
		#Include sbigudrv.so
		if system() == 'Linux':
			self.SBIG = CDLL("/usr/local/lib/libsbigudrv.so")
		elif system() == 'Windows': #Note: Requires 32bit python to access 32bit DLL
			self.SBIG = CDLL('C:\\Windows\system\sbigudrv.dll')
		else: #Assume Linux
			self.SBIG = CDLL("/usr/local/lib/libsbigudrv.so")
		self.verbose = verbose
=======
	class SetTemperatureRegulationParams2(Structure):
		_fields_ = [('regulation', c_int),
					('ccdSetpoint', c_double)]
    class MiscellaneousControlParams(Structure):
        _fields_ = [('fanEnable', c_ushort),
                    ('shutterCommand', c_ushort),
					('ledState', c_ushort)]
	
	#Enumerated values taken from sbigudrv.h
	CC_OPEN_DRIVER = 17
	CE_NO_ERROR = 0
	CC_CLOSE_DRIVER = 18
	CC_OPEN_DEVICE = 27
	CC_CLOSE_DEVICE = 28
	CC_ESTABLISH_LINK = 9
	CC_START_EXPOSURE2 = 50
	CC_END_EXPOSURE = 2
	CC_START_READOUT = 35
	CC_READOUT_LINE = 3
	CC_QUERY_COMMAND_STATUS = 12
	CC_SET_TEMPERATURE_REGULATION2 = 51
	CCD_IMAGING = 0
	SC_CLOSE_SHUTTER = 2
	SC_OPEN_SHUTTER = 1
	RM_1X1 = 0
	ABG_LOW7 = 1
	EXP_FAST_READOUT = 0x08000000
    CC_MISCELLANEOUS_CONTROL = 13
    LED_OFF = 0	
	
	def __init__(self,verbose=False):
		self.DARK = 0 #Defaults to 0
		self.exposure = 0 # units 1/100 second (minimum exposure is 0.09 seconds)
		self.TOP = c_ushort(0)
		self.LEFT = c_ushort(0)
		self.FAST = 0
		#self.cam_model=cam_model
		self.WIDTH = 0
		self.HEIGHT = 0
		#Include sbigudrv.so
		if system() == 'Linux':
			self.SBIG = CDLL("/usr/local/lib/libsbigudrv.so")
		elif system() == 'Windows': #Note: Requires 32bit python to access 32bit DLL
			self.SBIG = CDLL('C:\\Windows\system\sbigudrv.dll')
		else: #Assume Linux
			self.SBIG = CDLL("/usr/local/lib/libsbigudrv.so")
		self.verbose = verbose
>>>>>>> .r5289
        self.shutter = False

    class QueryTemperatureStatusParams(Structure):
        _fields_ = [('request',                         c_int)]

    class QueryTemperatureStatusResults2(Structure):
        _fields_ = [('coolingEnabled',                  c_bool),
                    ('fanEnabled',                      c_ushort),
                    ('ccdSetpoint',                     c_double),
                    ('imagingCCDTemperature',           c_double),
                    ('trackingCCDTemperature',          c_double),
                    ('externalTrackingCCDTemperature',  c_double),
                    ('ambientTemperature',              c_double),
                    ('imagingCCDPower',                 c_double),
                    ('trackingCCDPower',                c_double),
                    ('externalTrackingCCDPower',        c_double),
                    ('heatsinkTemperature',             c_double),
                    ('fanPower',                        c_double),
                    ('fanSpeed',                        c_double),
                    ('trackingCCDSetpoint',             c_double)]
    class MiscellaneousControlParams(Structure):
        _fields_ = [('fanEnable',                       c_bool),
                    ('shutterCommand',                  c_ushort),
					('ledState',                        c_ushort)]

    # Enumerated codes taken from sbigudrv.h
    # general use camera commands
    CC_END_EXPOSURE                 = 2
    CC_READOUT_LINE                 = 3
    CC_QUERY_TEMPERATURE_STATUS     = 6
    CC_ESTABLISH_LINK               = 9
    CC_QUERY_COMMAND_STATUS         = 12
    CC_MISCELLANEOUS_CONTROL        = 13
    CC_OPEN_DRIVER                  = 17
    CC_CLOSE_DRIVER                 = 18
    CC_END_READOUT                  = 25
    CC_OPEN_DEVICE                  = 27
    CC_CLOSE_DEVICE                 = 28
    CC_START_READOUT                = 35
    CC_START_EXPOSURE2              = 50
    CC_SET_TEMPERATURE_REGULATION2  = 51
    # camera error base
    CE_NO_ERROR                     = 0
    # CCD request
    CCD_IMAGING                     = 0
    # shutter command
    SC_LEAVE_SHUTTER                = 0
    SC_OPEN_SHUTTER                 = 1
    SC_CLOSE_SHUTTER                = 2
    SC_INITIALIZE_SHUTTER           = 3
    # readout binning mode
    RM_1X1                          = 0
    # ABG_STATE7 - Passed to Start Exposure Command
    ABG_LOW7                        = 1
    # activate the fast readout mode of the STF-8300, etc.
    EXP_FAST_READOUT                = 0x08000000
    # LED State
    LED_OFF                         = 0
    LED_ON                          = 1
    LED_BLINK_LOW                   = 2
    LED_BLINK_HIGH                  = 3
    # temperature regulation codes
    """
    Requires camera to be open (open_camera())
    Command values:
    0 - 'off' - regulation off
    1 - 'on' - regulation on
    2 - 'override' - regulation override
    3 - 'freeze_on' - freeze TE cooler (ST-8/7 cameras)
    4 - 'freeze_off' - unfreeze TE cooler
    5 - 'autofreeze_on' - enable auto-freeze
    6 - 'autofreeze_off' - disable auto-freeze
    temp is the CCD temperature in celsius to activate regulation
    """
    # prebuild dictionaries to avoid rebuilding upon each command call
    tempRegulationDict = {'REGULATION_OFF'                  : 0, 
                          'REGULATION_ON'                   : 1,
                          'REGULATION_OVERRIDE'             : 2,
                          'REGULATION_FREEZE'               : 3,
                          'REGULATION_UNFREEZE'             : 4,
                          'REGULATION_ENABLE_AUTOFREEZE'    : 5,
                          'REGULATION_DISABLE_AUTOFREEZE'   : 6}
    # inverse mapping for displaying messages
    # regulationDictInv = {regulationDict[k]: k for k in regulationDict.keys()}
    
    def __init__(self, verbose=True):
        self.cameraName = 'No Camera Selected'
        self.DARK = 0 # Defaults to 0
        self.exposure = 0 # units 1/100 second (minimum exposure is 0.09 seconds)
        self.TOP = c_ushort(0)
        self.LEFT = c_ushort(0)
        self.FAST = 0
        # self.cam_model=cam_model
        self.WIDTH = 0
        self.HEIGHT = 0
        # Include sbigudrv.so
        if system() == 'Linux':
            self.SBIG = CDLL("/usr/local/lib/libsbigudrv.so")
        elif system() == 'Windows': # Note: Requires 32bit python to access 32bit DLL
            self.SBIG = CDLL('C:\\Windows\system\sbigudrv.dll')
        else: # Assume Linux
            self.SBIG = CDLL("/usr/local/lib/libsbigudrv.so")
        self.verbose = verbose
        self.keepShutterOpen = False

<<<<<<< .mine
    def set_image_size(self, width, height):
        """
        sets the CCD chip size in pixels
        Input
            width: Integer, width of CCD
            height: Integer, height of CCD
        Returns:
            True if success
            False if failed
        """
        try:
            self.WIDTH = c_ushort(width)
            self.HEIGHT = c_ushort(height)
            
            
            return True
        except:
            return False
||||||| .r5271
		if name in ['ST8300','STi']:
			try:
				if name == 'ST8300': self.set_image_size(3352,2532)
				if name == 'STi':self.set_image_size(648,484)
				return True
			except:
				print('could not select camera: ' + name)
				return False	
		else:
			print('Not a valid camera name (use "ST8300" or "STi") ')
			return False
=======
		if name in ['ST8300','STi']:
			try:
				if name == 'ST8300':
                    self.set_image_size(3352,2532)
                    self.shutter = False
				if name == 'STi':
                    self.set_image_size(648,484)
                    self.shutter=True
                
				return True
			except:
				print('could not select camera: ' + name)
				return False	
		else:
			print('Not a valid camera name (use "ST8300" or "STi") ')
			return False
>>>>>>> .r5289


    def set_window_mode(self, top=0, left=0):
        try:
            self.TOP=c_ushort(top)
            self.LEFT=c_ushort(left)
            return True
        except:
            return False
            
    def select_camera(self, name='STF-8300M'):
        """
        sets the CCD chip size in pixels according to
        the camera model selected
        Input
            name: string, camera model (must be 'STF 8300M' or 'ST-i')
        Returns:
            True if success
            False if failed
        Default CCD size is for the SBIG STF-8300M
        """

        if name in ['ST8300', 'STi']:
            try:
                if name == 'ST8300': 
                    self.cameraName = 'ST8300'
                    self.set_image_size(3352,2532)
                if name == 'STi':
                    self.cameraName = 'STi'
                    self.set_image_size(648,484)
                return True
            except:
                print('could not select camera: ' + name)
                return False    
        else:
            print('Not a valid camera name (use "ST8300" or "STi") ')
            return False

    def set_resolution(self, width,height):
        """
        wrapper for legacy method
        """
        self.set_image_size(width,height)
        return

    def set_fast_mode(self, fast_mode=False):
        if fast_mode:
            self.FAST=self.EXP_FAST_READOUT
        return

    def set_exposure_time(self, exp_time=90):
        """
        sets the exposure time in ms
        Input
            time: Integer, exposure time in ms (min: 90, max: 3600)
        Returns:
            True if success
            False if failed
        """
#       if exp_time < 90: exp_time = 90  removed to allow 0s bias frames
        if exp_time > 3600000: exp_time=3600000
        try:
            self.exposure = int(exp_time/10)
            return True
        except:
            return False
        return

    def set_dark(self, x=False):
        """
        Dark Frame:
        if x == True then shutter stays closed during exposure

        """
        self.DARK = bool(x)
        return
  
<<<<<<< .mine
    def set_temperature_regulation2(self, regulationInput, CCDSetpoint):
||||||| .r5271
	def temperature_control(self, command, temp):
		"""
  		Requires camera to be open (open_camera())
  		
  		Command values:
		0 - 'off' - regulation off
		1 - 'on' - regulation on
		2 - 'override' - regulation override
		3 - 'freeze_on' - freeze TE cooler (ST-8/7 cameras)
		4 - 'freeze_off' - unfreeze TE cooler
		5 - 'autofreeze_on' - enable auto-freeze
		6 - 'autofreeze_off' - disable auto-freeze
		
  		temp is the CCD temperature in celsius to activate regulation
    		"""
		commands = {'off':0, 'on':1, 'override':2,'freeze_on':3,'freeze_off':4,'autofreeze_on':5, 'autofreeze_off':6}
		if command not in commands.keys() and commands not in range(0,7):
			print('Invalid Command')
			return False
		elif command in commands.keys():
			command = commands[command]
		trp2 = self.SetTemperatureRegulationParams2(regulation = c_int(command), ccdSetpoint = c_double(temp))
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_SET_TEMPERATURE_REGULATION2, byref(trp2), None)
		if Error != self.CE_NO_ERROR:
			print('Attempt to adjust temperature control returned error:', Error)
			return False
		elif self.verbose:
			print('Temperature command:', command, 'set. Temperature:', temp, 'C')
		return True
  
	def open_camera(self):
		"""
		initializes driver and camera
		"""
		 #Open Driver
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_OPEN_DRIVER, None, None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to open driver returned error:', Error)
			return False
		elif self.verbose:
			print ('Driver successfully opened.')
	 
	   
		#Open Device
		odp = self.OpenDeviceParams(deviceType = 0x7F00)
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_OPEN_DEVICE, byref(odp), None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to open device returned error:', Error)
			return False
		elif self.verbose:
			print ('Device successfully opened.')
		
		
		#Establish Link
		elr = self.EstablishLinkResults()
		elp = self.EstablishLinkParams(sbigUseOnly = 0)
		self.SBIG.SBIGUnivDrvCommand(self.CC_ESTABLISH_LINK, byref(elp), byref(elr))
		if elr.cameraType == 0xFFFF:
			print ('No camera found.')
			return False
		return True
		
	def start_exposure(self): 
		"""
		starts the exposure
		Input
			None
		Returns
			Image if success, False otherwise
		"""    
		#Take Image  
		exposure=c_ulong(self.exposure + self.FAST)
		sep2 = self.StartExposureParams2(ccd = self.CCD_IMAGING, exposureTime = exposure,
									abgState = self.ABG_LOW7, readoutMode = self.RM_1X1,
									top = self.TOP, left = self.LEFT, 
									height = self.HEIGHT, width = self.WIDTH)
		if self.DARK:
			sep2.openShutter = self.SC_CLOSE_SHUTTER
		else:
			sep2.openShutter = self.SC_OPEN_SHUTTER
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_START_EXPOSURE2, byref(sep2), None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to start exposure returned error:', Error)
			return False
		elif self.verbose:
			print ('Exposure successfully initiated.')		 
		#Wait for exposure to end
		qcspar = self.QueryCommandStatusParams(command = self.CC_START_EXPOSURE2)
		qcsres = self.QueryCommandStatusResults(status = 6)
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_QUERY_COMMAND_STATUS, byref(qcspar), byref(qcsres))
		while qcsres.status == 2:
			Error = self.SBIG.SBIGUnivDrvCommand(self.CC_QUERY_COMMAND_STATUS, byref(qcspar), byref(qcsres))
		#End Exposure
		eep = self.EndExposureParams(ccd = self.CCD_IMAGING)
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_END_EXPOSURE, byref(eep), None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to end exposure returned error:', Error)
			return False
		elif self.verbose:
			print ('Exposure successfully ended.')
		 
		#Start Readout
		srp = self.StartReadoutParams(ccd = self.CCD_IMAGING, readoutMode = self.RM_1X1,
								 top = self.TOP, left = self.LEFT, height = self.HEIGHT,
								 width = self.WIDTH)
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_START_READOUT, byref(srp), None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to initialize readout returned error:', Error)
			return False
		elif self.verbose:
			print ('Readout successfully initialized.')
		  
		  
		#Readout
		rlp = self.ReadoutLinesParams(ccd = self.CCD_IMAGING, readoutMode = self.RM_1X1,
								 pixelStart = 0, pixelLength = self.WIDTH)
		cameraData = ((c_ushort*(self.WIDTH.value))*self.HEIGHT.value)()
		for i in range(self.HEIGHT.value):
			Error = self.SBIG.SBIGUnivDrvCommand(self.CC_READOUT_LINE,byref(rlp), byref(cameraData, i*self.WIDTH.value*2)) #the 2 is essential
			if Error != self.CE_NO_ERROR:
				print ('Readout failed. Writing readout then closing device and driver.')
				break
		image = np.ctypeslib.as_array(cameraData)
		#hdu = fits.PrimaryHDU(image)
		#name = time.strftime("%Y-%m-%d-%H%M%S") + '.fits' #Saves file with timestamp
		#hdu.writeto(name)
		if Error == self.CE_NO_ERROR and self.verbose:
			print ('Readout successfully completed.')
		return image
	
	
	def write_fits(self, image, name):
		"""
		Writes out image to a FITS file with name 'name'
		Input:
			image: numpy array
			name: string, filename 
		"""
		#image = np.ctypeslib.as_array(cameraData)
		try:
			hdu = fits.PrimaryHDU(image)
		#name = time.strftime("%Y-%m-%d-%H%M%S") + '.fits' #Saves file with timestamp
			hdu.writeto(name)
			return True
		except:
			return False
=======
	def temperature_control(self, command, temp):
		"""
  		Requires camera to be open (open_camera())
  		
  		Command values:
		0 - 'off' - regulation off
		1 - 'on' - regulation on
		2 - 'override' - regulation override
		3 - 'freeze_on' - freeze TE cooler (ST-8/7 cameras)
		4 - 'freeze_off' - unfreeze TE cooler
		5 - 'autofreeze_on' - enable auto-freeze
		6 - 'autofreeze_off' - disable auto-freeze
		
  		temp is the CCD temperature in celsius to activate regulation
    		"""
		commands = {'off':0, 'on':1, 'override':2,'freeze_on':3,'freeze_off':4,'autofreeze_on':5, 'autofreeze_off':6}
		if command not in commands.keys() and commands not in range(0,7):
			print('Invalid Command')
			return False
		elif command in commands.keys():
			command = commands[command]
		trp2 = self.SetTemperatureRegulationParams2(regulation = c_int(command), ccdSetpoint = c_double(temp))
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_SET_TEMPERATURE_REGULATION2, byref(trp2), None)
		if Error != self.CE_NO_ERROR:
			print('Attempt to adjust temperature control returned error:', Error)
			return False
		elif self.verbose:
			print('Temperature command:', command, 'set. Temperature:', temp, 'C')
		return True
  
	def open_camera(self):
		"""
		initializes driver and camera
		"""
		 #Open Driver
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_OPEN_DRIVER, None, None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to open driver returned error:', Error)
			return False
		elif self.verbose:
			print ('Driver successfully opened.')
	 
	   
		#Open Device
		odp = self.OpenDeviceParams(deviceType = 0x7F00)
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_OPEN_DEVICE, byref(odp), None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to open device returned error:', Error)
			return False
		elif self.verbose:
			print ('Device successfully opened.')
		
		
		#Establish Link
		elr = self.EstablishLinkResults()
		elp = self.EstablishLinkParams(sbigUseOnly = 0)
		self.SBIG.SBIGUnivDrvCommand(self.CC_ESTABLISH_LINK, byref(elp), byref(elr))
		if elr.cameraType == 0xFFFF:
			print ('No camera found.')
			return False
		return True
		
	def start_exposure(self): 
		"""
		starts the exposure
		Input
			None
		Returns
			Image if success, False otherwise
		"""    
		#Take Image  
		exposure=c_ulong(self.exposure + self.FAST)
		sep2 = self.StartExposureParams2(ccd = self.CCD_IMAGING, exposureTime = exposure,
									abgState = self.ABG_LOW7, readoutMode = self.RM_1X1,
									top = self.TOP, left = self.LEFT, 
									height = self.HEIGHT, width = self.WIDTH)
		if self.DARK:
			sep2.openShutter = self.SC_CLOSE_SHUTTER
		else:
			sep2.openShutter = self.SC_OPEN_SHUTTER
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_START_EXPOSURE2, byref(sep2), None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to start exposure returned error:', Error)
			return False
		elif self.verbose:
			print ('Exposure successfully initiated.')		 
		#Wait for exposure to end
		qcspar = self.QueryCommandStatusParams(command = self.CC_START_EXPOSURE2)
		qcsres = self.QueryCommandStatusResults(status = 6)
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_QUERY_COMMAND_STATUS, byref(qcspar), byref(qcsres))
		while qcsres.status == 2:
			Error = self.SBIG.SBIGUnivDrvCommand(self.CC_QUERY_COMMAND_STATUS, byref(qcspar), byref(qcsres))
		#End Exposure
		eep = self.EndExposureParams(ccd = self.CCD_IMAGING)
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_END_EXPOSURE, byref(eep), None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to end exposure returned error:', Error)
			return False
		elif self.verbose:
			print ('Exposure successfully ended.')

        #Close shutter for STi cameras
        if self.shutter:
            shutt = self.MiscellaneousControlParams(fanEnable=0,shutterCommand=self.SC_CLOSE_SHUTTER,ledState=self.LED_OFF)
			Error = self.SBIG.SBIGUnivDrvCommand(self.CC_MISCELLANEOUS_CONTROL, byref(shutt), None)
			#print(Error)
			if Error!=self.CE_NO_ERROR:
				print("wasn't able to close shutter: ",Error)
			elif self.verbose:
				print("Shutter closed")
		else:
			pass
		 
		#Start Readout
		srp = self.StartReadoutParams(ccd = self.CCD_IMAGING, readoutMode = self.RM_1X1,
								 top = self.TOP, left = self.LEFT, height = self.HEIGHT,
								 width = self.WIDTH)
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_START_READOUT, byref(srp), None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to initialize readout returned error:', Error)
			return False
		elif self.verbose:
			print ('Readout successfully initialized.')
		  
		  
		#Readout
		rlp = self.ReadoutLinesParams(ccd = self.CCD_IMAGING, readoutMode = self.RM_1X1,
								 pixelStart = 0, pixelLength = self.WIDTH)
		cameraData = ((c_ushort*(self.WIDTH.value))*self.HEIGHT.value)()
		for i in range(self.HEIGHT.value):
			Error = self.SBIG.SBIGUnivDrvCommand(self.CC_READOUT_LINE,byref(rlp), byref(cameraData, i*self.WIDTH.value*2)) #the 2 is essential
			if Error != self.CE_NO_ERROR:
				print ('Readout failed. Writing readout then closing device and driver.')
				break
		image = np.ctypeslib.as_array(cameraData)
		#hdu = fits.PrimaryHDU(image)
		#name = time.strftime("%Y-%m-%d-%H%M%S") + '.fits' #Saves file with timestamp
		#hdu.writeto(name)
		if Error == self.CE_NO_ERROR and self.verbose:
			print ('Readout successfully completed.')
		return image
	
	
	def write_fits(self, image, name):
		"""
		Writes out image to a FITS file with name 'name'
		Input:
			image: numpy array
			name: string, filename 
		"""
		#image = np.ctypeslib.as_array(cameraData)
		try:
			hdu = fits.PrimaryHDU(image)
		#name = time.strftime("%Y-%m-%d-%H%M%S") + '.fits' #Saves file with timestamp
			hdu.writeto(name)
			return True
		except:
			return False
>>>>>>> .r5289


        # check input
        if regulationInput in self.tempRegulationDict.keys():
            regulation = self.regulationDict[regulationInput]
        elif regulationInput in self.tempRegulationDict.values():
            regulation = regulationInput
        else:
            print('Invalid Command')
            return False
            
        # send driver command
        trp2 = self.SetTemperatureRegulationParams2(
                    regulation  = c_int(regulation),
                    ccdSetpoint = c_double(CCDSetpoint))
        Error = self.SBIG.SBIGUnivDrvCommand(
                    self.CC_SET_TEMPERATURE_REGULATION2, byref(trp2), None)
        if Error != self.CE_NO_ERROR:
            print('Temperature regulation returned error: ', Error)
            return False
        elif self.verbose:
            print('Temperature regulation set: ', regulation, 
                      '. CCD Setpoint: ', CCDSetpoint, 'degree C.')
        return True
        
    def query_temperature_status(self):
        
        '''
        standard request returns temperature status in A/D units
        advanced request returns degree celsius, recommended
        '''

        tsp = self.QueryTemperatureStatusParams(request = c_int(2))
        qtsr2 = self.QueryTemperatureStatusResults2()
        Error = self.SBIG.SBIGUnivDrvCommand(
            self.CC_QUERY_TEMPERATURE_STATUS, byref(tsp), byref(qtsr2))
            
        if Error != self.CE_NO_ERROR:
            print ('Temperature status query returned error:', Error)
            return False
        elif self.verbose:
            results_text = ('Temperature status query results: '     +'\n'
                +'Cooling Enabled: ' 
                    + repr(qtsr2.coolingEnabled)                     +'\n'
                +'Fan Enabled: ' 
                    + repr(qtsr2.fanEnabled)                         +'\n'
                +'CCD Setpoint: ' 
                    + repr(qtsr2.ccdSetpoint)                        +'\n'
                +'Imaging CCD Temperature: '
                    +repr(qtsr2.imagingCCDTemperature)               +'\n'
                +'Tracking CCD Temperature: '
                    +repr(qtsr2.trackingCCDTemperature)              +'\n'
                +'External Tracking CCD Temperature: '
                    +repr(qtsr2.externalTrackingCCDTemperature)      +'\n'
                +'Ambient Temperature: '
                    +repr(qtsr2.ambientTemperature)                  +'\n'
                +'Imaging CCD Power: '
                    +repr(qtsr2.imagingCCDPower)                     +'\n'
                +'Tracking CCD Power: '
                    +repr(qtsr2.trackingCCDPower)                    +'\n'
                +'External Tracking CCD Power: '
                    +repr(qtsr2.externalTrackingCCDPower)            +'\n'
                +'Heatsink Temperature: '
                    +repr(qtsr2.heatsinkTemperature)                 +'\n'
                +'Fan Power: '
                    +repr(qtsr2.fanPower)                            +'\n'
                +'Fan Speed: '
                    +repr(qtsr2.fanSpeed))

            print (results_text)
            
    def open_camera(self):
        """
        initializes driver and camera
        """
        # Open Driver
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_OPEN_DRIVER, None, None)
        if Error == 21:
            print ('Code 21: driver already opened.')
        elif Error != self.CE_NO_ERROR:
            print ('Attempt to open driver returned error:', Error)
            return False
        elif self.verbose:
            print ('Driver successfully opened.')
     
        # Open Device
        odp = self.OpenDeviceParams(deviceType = 0x7F00)
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_OPEN_DEVICE, byref(odp), None)
        if Error == 29:
            print ('Code 29: device already opened.')
        elif Error != self.CE_NO_ERROR:
            print ('Attempt to open device returned error:', Error)
            return False
        elif self.verbose:
            print ('Device successfully opened.')
        
        # Establish Link
        elp = self.EstablishLinkParams(sbigUseOnly = 0)
        elr = self.EstablishLinkResults()
        self.SBIG.SBIGUnivDrvCommand(self.CC_ESTABLISH_LINK, byref(elp), byref(elr))
        if elr.cameraType == 0xFFFF:
            print ('No camera found.')
            return False
        elif self.verbose:
            print ('Link successfully established.')
        return True
        
    def start_exposure(self): 
        """
        starts the exposure
        Input
            None
        Returns
            Image if success, False otherwise
        """    
        # Take Image  
        exposure = c_ulong(self.exposure + self.FAST)
        sep2 = self.StartExposureParams2(
                    ccd = self.CCD_IMAGING, 
                    exposureTime = exposure, 
                    abgState = self.ABG_LOW7, 
                    readoutMode = self.RM_1X1,
                    top = self.TOP, 
                    left = self.LEFT, 
                    height = self.HEIGHT,
                    width = self.WIDTH)
        if self.DARK:
            sep2.openShutter = self.SC_CLOSE_SHUTTER
        else:
            sep2.openShutter = self.SC_OPEN_SHUTTER
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_START_EXPOSURE2, byref(sep2), None)
        if Error != self.CE_NO_ERROR:
            print ('Attempt to start exposure returned error:', Error)
            return False
        elif self.verbose:
            print ('Exposure successfully initiated.')       
        # Wait for exposure to end
        qcspar = self.QueryCommandStatusParams(command = self.CC_START_EXPOSURE2)
        qcsres = self.QueryCommandStatusResults(status = 6)
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_QUERY_COMMAND_STATUS, byref(qcspar), byref(qcsres))
        while qcsres.status == 2:
            Error = self.SBIG.SBIGUnivDrvCommand(self.CC_QUERY_COMMAND_STATUS, byref(qcspar), byref(qcsres))
        # End Exposure
        eep = self.EndExposureParams(ccd = self.CCD_IMAGING)
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_END_EXPOSURE, byref(eep), None)
        if Error != self.CE_NO_ERROR:
            print ('Attempt to end exposure returned error:', Error)
            return False
        elif self.verbose:
            print ('Exposure successfully ended.')
            
        # close shutter for ST-i camera
        # This section is skipped for 8300 camera and keepShutterOpen=True
        if self.cameraName == 'STi' and self.keepShutterOpen == False:
            mcp = self.MiscellaneousControlParams(
                    fanEnable = c_bool(True),
                    shutterCommand = self.SC_CLOSE_SHUTTER,
                    ledState = self.LED_ON)
            Error = self.SBIG.SBIGUnivDrvCommand(
                       self.CC_MISCELLANEOUS_CONTROL, byref(mcp), None)
			#print(Error)
                       
        if Error != self.CE_NO_ERROR:
            print("Closing ST-i shutter returned error:", Error)
        elif self.verbose:
            print("ST-i shutter successfully closed.")
         
        # Start Readout
        srp = self.StartReadoutParams(ccd = self.CCD_IMAGING, readoutMode = self.RM_1X1,
                                 top = self.TOP, left = self.LEFT, height = self.HEIGHT,
                                 width = self.WIDTH)
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_START_READOUT, byref(srp), None)
        if Error != self.CE_NO_ERROR:
            print ('Attempt to initialise readout returned error:', Error)
            return False
        elif self.verbose:
            print ('Readout successfully initiated.')
          
          
        # Readout
        rlp = self.ReadoutLinesParams(ccd = self.CCD_IMAGING, readoutMode = self.RM_1X1,
                                 pixelStart = 0, pixelLength = self.WIDTH)
        cameraData = ((c_ushort*(self.WIDTH.value))*self.HEIGHT.value)()
        for i in range(self.HEIGHT.value):
            Error = self.SBIG.SBIGUnivDrvCommand(self.CC_READOUT_LINE, byref(rlp), byref(cameraData, i*self.WIDTH.value*2)) # the 2 is essential
            if Error != self.CE_NO_ERROR:
                print ('Readout failed. Writing readout then closing device and driver.')
                break
        image = np.ctypeslib.as_array(cameraData)
        if Error == self.CE_NO_ERROR and self.verbose:
            print ('Readout successful.')

        # End readout in any case for autofreeze to function proper
        '''
        The End Readout command should be called at least once per readout
        after calls to the Readout Line, Read Subtract Line or Dump Lines 
        command are complete. Several End Readout commands can be issued 
        without generating an error.
        '''
        erp = self.EndReadoutParams(cd = self.CCD_IMAGING)
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_END_READOUT, byref(erp), None)
        if Error != self.CE_NO_ERROR:
            print ('End readout failed with error code: ', Error)
        elif self.verbose:
            print ('Readout sucessfully ended.')
        # hdu = fits.PrimaryHDU(image)
        # name = time.strftime("%Y-%m-%d-%H%M%S") + '.fits' # Saves file with timestamp
        # hdu.writeto(name)
        return image
    
    
    def write_fits(self, image, name):
        """
        Writes out image to a FITS file with name 'name'
        Input:
            image: numpy array
            name: string, filename 
        """
        # image = np.ctypeslib.as_array(cameraData)
        # retrieve current CCD temperature

        try:
            hdu = fits.PrimaryHDU(image)
        # name = time.strftime("%Y-%m-%d-%H%M%S") + '.fits' # Saves file with timestamp
            hdu.writeto(name)
            return True
        except:
            return False

    
    def close_camera(self):
         # Close Device
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_CLOSE_DEVICE, None, None)
        if Error == 20:
            print ('Code 20: device already closed.')
        elif Error != self.CE_NO_ERROR:
            if self.verbose: print ('Attempt to close device returned error:', Error)
            return False
        elif self.verbose:
            print ('Device successfully closed.')
        
        # Close Driver
        Error = self.SBIG.SBIGUnivDrvCommand(self.CC_CLOSE_DRIVER, None, None)
        if Error == 20:
            print ('Code 20: driver already closed.')
        elif Error != self.CE_NO_ERROR:
            print ('Attempt to close driver returned error:', Error)
            return False
        elif self.verbose:
            print ('Driver successfully closed.')
            
        return True

if __name__ == '__main__':

    model={'1':     'ST8300',
           '2':     'STi'}
    camtype=input("Select camera type.  (1) for ST8300 or (2) for STi: ")
    if camtype.lower() not in ['1','2']:
        print("Not a valid camera type")
        sys.exit()
    camera = SBIGCam()
    camera.select_camera(model[camtype.lower()])    
    # Time of exposure in between 90ms and 3600000ms
    if not camera.open_camera():
        print ("Can't establish connection to camera")
        sys.exit()
    extime = input("Exposure time in milliseconds (between 0 and 3600000): ")
    while (type(extime) is str):
        try:
            extime = int(extime)
        except ValueError:
            print("Looks like that's not a valid exposure time ")
            camera.close_camera()
            sys.exit()
    camera.set_exposure_time(extime)        
    response= input("Will this be a dark image? (Y/N) ") 
    # 1 for dark, 0 for exposure
    try:
        if response[0].lower() not in ['y','n']:
            print("Input Error")
        else:
            camera.set_dark(False)
            if response[0].lower() == 'y':
                camera.set_dark(True)
    except:
        print("Input Error")            
    image=camera.start_exposure()
    filename = 'sbig'+time.strftime("%y%m%d-%H%M%S") + '.fits' 
    camera.write_fits(image,filename)
    camera.close_camera()
