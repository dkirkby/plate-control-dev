'''
sbigcam.py 
March 2016

Author: Kevin Fanning (kfanning@umich.edu) referencing sbigudrv.h

Requires: ctypes*, platform*, numpy, pyfits, time*
*Refers to packages in Python's Standard Library

1.) you need to install the SBIG driver (libsbigudrv.so) to /usr/local/lib. 
	Drivers for ARM, 32-bit and 64 bit Intel processors are in the 
	svn (focalplane/test_stand_control/trunk/camera_code/SBIG_dev).
2.) copy 51-sbig-debian.rules into /etc/udev/rules.d  (the rules file is also in the SBIG_Dev directory)
3.) point LD_LIBRARY_PATH to /usr/local/lib

Function: When run as main, takes image from SBIG camera and saves it as FITS file.

As a Module: imports a class with many memeber functions allowing for the control of an SBIG camera.
First, import this by typing import SBIG, then create a camera object using object = SBIG.CAMERA().
From here you have several member functions that are called using object.function(args), where object
is your object's name, funtion is the funtion name and args are any arguments the function might take.

There are several changable settings for an object:
 
The image resolution is set to 3352x2532 pixels by default as that is the resolution STF-8300M. 
This can be changed by calling set_resolution(width, height), whyere width
and height are integer arguments.

The image is an exposure by default but can be set to a dark image by calling object.SetDark(x)
where ideally x is 0 (exposure) or 1 (dark image), but the function casts x as a bool to be safe.

The exposure time is 90ms by default, the shortest time that can be used. This can be changed by 
calling set_exposure(time) command where time is the exposure time in milliseconds. The
longest exposure time avalible is 3600000ms (1 hour). 

NOTE: Please use the setter functions rather than manually changing the object's elements, since the 
setter functions cast the values into ctype values that are required for many of the camera commands.

The typical sequence for taking an exposure is as follows:
	cam=SBIGCam()
	cam.open_camera()
	cam.select_camera('ST8300')
	cam.set_exposure_time(100)
	cam.set_dark(False)

	image=cam.start_exposure()
	cam.write_fits(image,'Image.FITS')

	cam.close_camera()



Modification history:

160317-MS:  replaced astropy.io import with pyfits

			converted to python3 (print statements, raw_input)
160325-MS	renamed to sbigcam.py, renamed methods to comply with Python convention
			added error checking, added method to write FITS file 
			

'''



from ctypes import CDLL, byref, Structure, c_ushort, c_ulong, c_void_p
from platform import system
import numpy as np
#from astropy.io import fits
import pyfits as fits
import time
import sys


class SBIGCam(object):

	#Structures defined in sbigudrv.h
	class OpenDeviceParams(Structure):
		_fields_ = [('deviceType', c_ushort),
					('lptBaseAddress', c_ushort),
					( 'ipAddress', c_ulong)]
					
	class EstablishLinkResults(Structure):
		_fields_ = [('cameraType', c_ushort)]
		
	class EstablishLinkParams(Structure):
		_fields_ = [('sbigUseOnly', c_ushort)]
					
	class StartExposureParams2(Structure):
		_fields_ = [('ccd', c_ushort),
					('exposureTime', c_ulong),
					('abgState', c_ushort),
					('openShutter', c_ushort),
					('readoutMode', c_ushort),
					('top', c_ushort),
					('left', c_ushort),
					('height', c_ushort),
					('width', c_ushort)]
					
	class EndExposureParams(Structure):
		_fields_ = [('ccd', c_ushort)]
		
	class StartReadoutParams(Structure):
		_fields_ = [('ccd', c_ushort),
					('readoutMode', c_ushort),
					('top', c_ushort),
					('left', c_ushort),
					('height', c_ushort),
					('width', c_ushort)]
					
	class ReadoutLinesParams(Structure):
		_fields_ = [('ccd', c_ushort),
					('readoutMode', c_ushort),
					('pixelStart', c_ushort),
					('pixelLength', c_ushort)]
	
	class QueryCommandStatusParams(Structure):
		_fields_ = [('command', c_ushort)]
	
	class QueryCommandStatusResults(Structure):
		_fields_ = [('status', c_ushort)]
	
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
	CCD_IMAGING = 0
	SC_CLOSE_SHUTTER = 2
	SC_OPEN_SHUTTER = 1
	RM_1X1 = 0
	ABG_LOW7 = 1
	
	def __init__(self):
		self.DARK = 0 #Defaults to 0
		self.exposure = c_ulong(90) #defaults to 90ms
		self.TOP = c_ushort(0)
		self.LEFT = c_ushort(0)
		#self.cam_model=cam_model
		self.WIDTH = c_ushort(3352) 
		self.HEIGHT = c_ushort(2532)
		#Include sbigudrv.so
		if system() == 'Linux':
			self.SBIG = CDLL("/usr/local/lib/libsbigudrv.so")
		elif system() == 'Windows': #Note: Requires 32bit python to access 32bit DLL
			self.SBIG = CDLL('C:\\Windows\system\sbigudrv.dll')
		#elif system() == 'OSX':
		#    self.SBIG = '???'
		else: #Assume Linux
			self.SBIG = CDLL("/usr/local/lib/libsbigudrv.so")
		self.verbose = False

	def set_image_size(self, width=3352, height=2532):
		"""
		sets the CCD chip size in pixels
		Input
			width: Integer, width of CCD
			height: Integer, height of CCD
		Returns:
			True if success
			False if failed
		Default CCD size is for the SBIG STF-8300
		"""
		try:
			self.WIDTH = c_ushort(width)
			self.HEIGHT = c_ushort(height)
			return True
		except:
			return False

	def select_camera(self,name='ST8300'):
		"""
		sets the CCD chip size in pixels according to
		the camera model selected
		Input
			name: string, camera model (must be 'ST8300' or 'STi')
		Returns:
			True if success
			False if failed
		Default CCD size is for the SBIG STF-8300
		"""

		if name in ['ST8300','STi']:
			try:
				if name == 'ST800': self.set_image_size()
				if name == 'STi':self.set_image_size(648,484)
				return True
			except:
				return False	
		else:
			return False



	def set_resolution(self, width,height):
		"""
		wrapper for legacy method
		"""
		self.set_image_size(width,height)
		return


	def set_exposure_time(self, time=90):
		"""
		sets the exposure time in ms
		Input
			time: Integer, exposure time in ms (min: 90, max: 3600)
		Returns:
			True if success
			False if failed
		"""
		if time < 90: time = 90
		if time > 3600000: time=3600000
		try:
			
			self.exposure = c_ulong(time)
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
		sep2 = self.StartExposureParams2(ccd = self.CCD_IMAGING, exposureTime = self.exposure,
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
			Error = self.SBIG.SBIGUnivDrvCommand(self.CC_READOUT_LINE,
												 byref(rlp), byref(cameraData, i*self.WIDTH.value*2)) #the 2 is essential
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

	
	def close_camera(self):
		 #Close Device
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_CLOSE_DEVICE, None, None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to close device returned error:', Error)
			return False
		elif self.verbose:
			print ('Device successfully closed.')
		
		
		#Close Driver
		Error = self.SBIG.SBIGUnivDrvCommand(self.CC_CLOSE_DRIVER, None, None)
		if Error != self.CE_NO_ERROR:
			print ('Attempt to close driver returned error:', Error)
			return False
		elif self.verbose:
			print ('Driver successfully closed.')
			
		return True

if __name__ == '__main__':
	camera = SBIGCam()
	#Settings
	#Time of exposure in between 90ms and 3600000ms
	if not camera.open_camera():
		print ("Can't establish connection to camera")
		sys.exit()
	extime = input("Exposure time in milliseconds (between 90 and 3600000): ")
	while (type(extime) is str):
		try:
			extime = int(extime)
		except ValueError:
			print("Looks like that's not a valid exposure time ")
			camera.close_camera()
			sys.exit()
	camera.set_exposure_time(extime)		
	response= input("Will this be a dark image? (Y/N) ") 
	#1 for dark, 0 for exposure
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
