#import multicens_v17 as multicens
import multicens
import pyfits
import time
import sys
import numpy as np

def magnitude(p,b):

	m=25.0 - 2.5*np.log10(p-b)
	return m

arguments = sys.argv[1:]
nargs = len(arguments)
try:
	if nargs <1:
		nspots=1
	else:
		nspots=int(arguments[0])
	if nargs <2:
		fname='sbig_image.fits'
	else:
		fname = arguments[1]
	if nargs >=3:
		fboxsize=int(arguments[2])
	else:
		fboxsize=7
except:
	print("Proper use: python3 spotfit.py <n_centroids_expected> <fits_filename> <fitbox_size>")
	sys.exit()		
#fname='peak_12548.4_fwhm_-0.338_sizefitbox_7.FITS'
img=pyfits.getdata(fname) 

#t0=time.time()
xCenSub, yCenSub, peaks, FWHMSub, filename =multicens.multiCens(img, n_centroids_to_keep=nspots, verbose=False, write_fits=False,size_fitbox=fboxsize)
#t=time.time()-t0
print(" File: "+str(fname))
print(" Number of centroids requested: "+str(nspots))
print(" Fitboxsize: "+str(fboxsize))
print(" Centroid list:")  
print(" Spot  x         y          FWHM    Peak      ")
for i, x in enumerate(xCenSub):
	print("{:5d} {:9.3f} {:9.3f} {:7.3f}   {:9.3f} ".format(i, x, yCenSub[i], FWHMSub[i], peaks[i]))

#print(" Spot  x         y          FWHM    Peak       Bias        Mag")
#for i, x in enumerate(xCenSub):
#	print("{:5d} {:9.3f} {:9.3f} {:7.3f}   {:9.3f} {:9.3f}   {:7.3f} ".format(i, x, yCenSub[i], FWHMSub[i], peaks[i], bias[i],magnitude(peaks[i],bias[i])))

# write region file
with open('region.reg','w') as fp:
	for i, x in enumerate(xCenSub):
		#print("{:5d} {:9.3f} {:9.3f} {:7.3f}   {:9.3f} {:9.3f}   {:7.3f} ".format(i, x, yCenSub[i], FWHMSub[i], peaks[i], bias[i],magnitude(peaks[i],bias[i])))
		fp.write('circle '+ "{:9.3f} {:9.3f} {:7.3f} \n".format(x+1, yCenSub[i]+1, FWHMSub[i]/2.))
		text='"'+str(i)+'"'
		fp.write('text '+ "{:9.3f} {:9.3f} {:s} \n".format(x+1+5, yCenSub[i]+1+5, text))
#print("time: "+str(t))
