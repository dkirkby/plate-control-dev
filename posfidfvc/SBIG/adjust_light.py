import multicens
import pyfits
import time
import sys
import numpy as np
import matplotlib as plt
import led_illuminator as led
import serial, struct
import time
import warnings
import sbigcam
import os

# -----------------------------------------------------------------------
def stf():
	# stf function
	def flip_horizontal(img):
		img = np.fliplr(img)
		return img
	def flip_vertical(img):
		img = np.flipud(img)
		return img
	print("This will take a moment ...")
	VERBOSE=False
	cam=sbigcam.SBIGCam()
	cam.select_camera('ST8300')
	cam.set_fast_mode(fast_mode=True)
	#cam.set_window_mode(top=400, left=450)
	#cam.set_image_size(2200,1400)
	try:
		cam.close_camera() # in case driver was previously left in "open" state
	except:
		pass
	cam.verbose=VERBOSE
	cam.open_camera()
	cam.set_exposure_time(200)
	cam.set_dark(False)
	start = time.time()
	#L=cam.start_exposure()
	L = flip_horizontal(cam.start_exposure())
	print('Time for readout:', time.time()-start, 'seconds.')
	filename = 'sbig_image.fits'
	try:
		os.remove(filename)
	except:
		print('couldn''t remove file: ' + filename)
	cam.write_fits(L,filename)
	print("... All done. Wrote file 'sbig_image.fits'")

# -----------------------------------------------------------------------
def spotfit(nspots):
	# the numbers below are from fvchandler
	max_counts = 2**16 - 1 # SBIC camera ADU max
	min_energy = 0.3 * 1.0 # this is the minimum allowed value for the product peak*fwhm for any given dot

	fname='sbig_image.fits'
	fboxsize=7
	print("nspots : ", nspots)

	img=pyfits.getdata(fname) 
	#t0=time.time()
	xCenSub, yCenSub, peaks, FWHMSub, filename =multicens.multiCens(img, n_centroids_to_keep=nspots, verbose=False, write_fits=False,size_fitbox=fboxsize)
	# we are calculating the quantity 'FWHM*peak' with peak normalized to the maximum peak level. This is
	# esentially a linear light density. We will call this quantity 'energy' to match Joe's naming in fvchandler.
	# We verified that the linear light density is insensitive to spot position whereas the measured peak is not.
	energy=[FWHMSub[l]*(peaks[l]/max_counts) for l in range(len(peaks))]
	print(" File: "+str(fname))
	print(" Number of centroids requested: "+str(nspots))
	print(" Fitboxsize: "+str(fboxsize))
	print(" Centroid list:")  
	print(" Spot  x         y          FWHM    Peak     LD  ")

	# sort by peak value
	sindex=sorted(range(len(peaks)), key=lambda k: peaks[k])

	peaks_sorted=[peaks[l] for l in sindex]
	x_sorted=[xCenSub[l] for l in sindex]
	y_sorted=[yCenSub[l] for l in sindex]
	fwhm_sorted=[FWHMSub[l] for l in sindex]
	energy_sorted=[energy[l] for l in sindex]

	for l, x in enumerate(x_sorted):
		line=("{:5d} {:9.3f} {:9.3f} {:6.2f}  {:7.0f} {:7.2f} ".format(l, x, y_sorted[l], fwhm_sorted[l], peaks_sorted[l], energy_sorted[l]))
		if energy[l] < min_energy:
			line=line+'*'
		print(line)

	return (x_sorted, y_sorted, peaks_sorted)



# Read inputs ------------------------------------------------------------
arguments = sys.argv[1:]
nargs = len(arguments)
try:
	if nargs <1:
		print("Proper use: python3 adjust_light.py <quantity_positioners>")
		sys.exit()
	if nargs==1:
		quantity_positioners=int(arguments[0])
	if nargs >=2:
		print("What are you doing ? stop tapping !")
		sys.exit()
except:
	print("Proper use: python3 adjust_light.py <quantity_positioners>")
	sys.exit()


# -----------------------------------------------------------------------
class Fiber:
	position_x = [None] * quantity_positioners
	position_y = [None] * quantity_positioners
	peak_intensity = [None] * quantity_positioners
	led_bright = [None] * quantity_positioners
	state = [False] * quantity_positioners


# Initialisation----------------------------------------------------------
default_bright = 255
error_spotfit = 2
min_peak = 35000
max_peak = 45000
min_LED_value = 1
max_LED_value = 255

mean_peak=(max_peak+min_peak)/2

a = quantity_positioners//2
b = quantity_positioners-a
batch_size = [a//2, a-a//2, b//2, b-b//2]
batch = [0, batch_size[0], batch_size[0]+batch_size[1], batch_size[0]+batch_size[1]+batch_size[2], quantity_positioners]

position_x_temp = []
position_y_temp = []
peak_intensity_temp = []

led=led.LedIlluminator()
led.set_array(255)
fiber=Fiber()


print("Size of the batchs : {} - {} - {} - {}".format(batch_size[0], batch_size[1], batch_size[2], batch_size[3]))

led.set_array(0)
#take 4 pictures of the 4 batchs ----------------------------------------
for i in range(4):
	led.set_array(0)
	for j in range(batch[i], batch[i+1]):
		led._set_fiber(j,default_bright)

	stf()
	x_sorted, y_sorted, peaks_sorted = spotfit(batch[i+1]-batch[i])

	position_x_temp.append(x_sorted)
	position_y_temp.append(y_sorted)
	peak_intensity_temp.append(peaks_sorted)

for i in range(4): # if a batch is smaller, add some 0 to prevent out of index
	if batch_size[i]<max(batch_size):
		position_x_temp[i].append(0)
		position_y_temp[i].append(0)
		peak_intensity_temp[i].append(0)


#take pictures for 1 fiber per batchs and find correspondance between LED and X,Y----------
for i in range(max(batch_size)): # define a LED value for each fiber
	led.set_array(0)
	for j in range(4):
		if i==(max(batch_size)-1):
			if batch_size[j]==max(batch_size):
				led._set_fiber(batch[j]+i, default_bright)
		else:
			led._set_fiber(batch[j]+i, default_bright)

	stf()
	x_sorted, y_sorted, peaks_sorted = spotfit(4)
	
	for j in range(4): # find the X,Y value for each LED and save in Fiber class with intensity
		for k in range(max(batch_size)):
			for l in range(len(x_sorted)):
				if x_sorted[l]>(position_x_temp[j][k]-error_spotfit) and x_sorted[l]<(position_x_temp[j][k]+error_spotfit) and y_sorted[l]>(position_y_temp[j][k]-error_spotfit) and y_sorted[l]<(position_y_temp[j][k]+error_spotfit):
					fiber.position_x[batch[j]+i]=x_sorted[l]
					fiber.position_y[batch[j]+i]=y_sorted[l]
					fiber.peak_intensity[batch[j]+i]=peaks_sorted[l]

for i in range(quantity_positioners):
	fiber.led_bright[i]=default_bright


# Correction of peak_intensity
counter=0
while not all(fiber.state):
	led.set_array(0)
	for i in range(quantity_positioners):
		if fiber.peak_intensity[i]<min_peak or fiber.peak_intensity[i]>max_peak:
			fiber.led_bright[i]=mean_peak*fiber.led_bright[i]/fiber.peak_intensity[i]
		else:
			fiber.state[i]=True
		if fiber.led_bright[i]<min_LED_value:
			fiber.led_bright[i]=min_LED_value
		if fiber.led_bright[i]>max_LED_value:
			fiber.led_bright[i]=max_LED_value
		led._set_fiber(i,fiber.led_bright[i])

	del x_sorted[:]
	del y_sorted[:]
	del peaks_sorted[:]

	stf()
	x_sorted, y_sorted, peaks_sorted = spotfit(quantity_positioners)

	k=0
	for i in range(quantity_positioners):
		for j in range(quantity_positioners):
			if x_sorted[i]>(fiber.position_x[j]-error_spotfit) and x_sorted[i]<(fiber.position_x[j]+error_spotfit) and y_sorted[i]>(fiber.position_y[j]-error_spotfit) and y_sorted[i]<(fiber.position_y[j]+error_spotfit):
				fiber.peak_intensity[j]=peaks_sorted[i]
	print("Iteration : ", counter)		
	print("LED_position   State         X        Y    Peak_Intensity    LED_value")
	for i in range(quantity_positioners):
		print("{:12d} {:7} {:9.1f} {:8.1f} {:17.1f} {:13.1f} ".format(i, fiber.state[i], fiber.position_x[i], fiber.position_y[i], fiber.peak_intensity[i], fiber.led_bright[i]))
	counter=counter+1
	if counter>15:
		print("Dots can't be achieve at the range !!!")
		sys.exit()

#print("intensity",peak_intensity)

