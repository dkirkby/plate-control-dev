import time
import warnings
import multicens
import numpy as np
import gc
import sbigcam

# 160326: 	MS-created based on the script SBIGgrabCen.py which used an c++ compiled executable to control
#			the SBIG camera (by calling SBIGGrabImage.py)
#			This was replaced with the new class in sbigcam.py 


def sbig_grab_cen(exposure_time=90, nWin=1, min_brightness=5000, max_brightness=60000, verbose=False, writefits=False):
	"""
    Calls function to grab light and dark images from SBIG camera, then centroids spots.
	 
    INPUTS

    exposure_time:	integer, exposure time, ms (90ms min)
    nWin: 			integer, number of centroid windows. For the measure_camera_scale script, nwin should be equal 1

    RETURNS
		xywin: list of centroid coordinates and fwhms for each spot in window ('list of lists')
				brightness is value of brightest pixel (dark subtracted)
				time is elapsed time in seconds 
	Sample call:
    	xywin, brightness, time = sbig_grab_cen(90,1)

    """
	# for now hardcode the following parameters but we will read those eventually
	# through config parser
#	
#	config=ConfigObj('camera_scale.conf')
#	min_brightness=config.get('Settings').as_int('min_brightness')
#	max_brightness=config.get('Settings').as_int('max_brightness')
#	verbose=config.get('Preferences').as_bool('verbose')
#	writefits=config.get('Preferences').as_bool('writefits')
#	pwd=os.getcwd()
#	
	#min_brightness=5000
	#max_brightness=60000
    
	# end configuration
	
	tic = time.time()
	
	cam=sbigcam.SBIGCam()
	cam.select_camera('ST8300')	
	cam.open_camera()
	
	cam.set_exposure_time(int(exposure_time))

	if verbose:
		print("verbose: ",verbose)			

	if verbose: print("dark Image")

	cam.set_dark(True)
	D = cam.start_exposure()

	if verbose: print("light image")

	cam.set_dark(False)
	L = cam.start_exposure() 
	if writefits: cam.write_fits(L,'LightImage.FITS')

	cam.close_camera()

	LD = np.array(L,dtype = np.int32) - np.array(D,dtype = np.int32)
	if writefits: cam.write_fits(LD,'DiffImage.FITS')

	del L
	del D
	gc.collect()

	brightness = np.amax(LD)
	if verbose: print("Brightness: "+str(brightness))
	if brightness < min_brightness:
		warnings.warn('Spot seems dark (brightness = {})'.format(brightness))
	if brightness > max_brightness:
		warnings.warn('Spot may be over saturated (brightness = {}'.format(brightness))

	# call routine to determine multiple gaussian-fitted centroids
	xcen, ycen, fwhm = multicens.multiCens(LD, nWin, verbose) 
	xy = [[xcen[i],ycen[i]] for i in range(len(xcen))]

	toc = time.time()
	if verbose:
		print("Time used: "+str(toc-tic)+"\n")
	return xy,brightness,tic-toc


