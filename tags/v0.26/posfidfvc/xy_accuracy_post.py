# xy_accuracy_post.py
# M. Schubnell, Univ. of Michiagn
# 
# Creates vector plot visualizing distance between target and position after move
# 
# Requires 'quiver' to be installed: pip3 install quiver
# Call with <filename> and <submove> as argument
# Example:
# python3 xy_accuracy_post.py UM00022_2016-05-12_T184730 0
# 

from matplotlib.pyplot import cm
import matplotlib.pyplot as plt
import numpy as np
import csv
from sys import argv, exit

try:
	#filename='UM00022_2016-05-12_T184730' #_movedata.csv'
	filename = argv[1]
	submove= argv[2]
except:
	print(" please specify filename and submove")
	exit()

if submove not in ['0','1','2','3','4']:
	print(" invalid submove ")
	exit()
	

movefile=csv.DictReader(open(filename+'_movedata.csv'))
movelist={}
for row in movefile:
    for column, value in row.items():
        movelist.setdefault(column,[]).append(value)
#print (movelist.keys())

X=np.array([float(i) for i in movelist['target_x']])
Y=np.array([float(i) for i in movelist['target_y']])

U=np.array([float(i) for i in movelist['meas_x'+submove]])
V=np.array([float(i) for i in movelist['meas_y'+submove]])

DX=U-X #np.subtract(U,X)
DY=V-Y #snp.subtract(V,Y)

distance = np.sqrt(DX**2 + DY**2)

# normalizes so that all arrows have same length
#DX = DX/distance
#DY = DY/distance
scale=1./(.15/np.max(distance))

plot1 = plt.figure()
plt.quiver(X,Y, DX, DY, distance*1000., cmap=cm.cool, headlength=7,scale=scale)
plt.colorbar()                  # adds the colour bar
plt.xlabel('x (mm)')
plt.ylabel('y (mm)')
plt.title(filename+' Submove '+submove)
plot1.savefig(filename+'_qvplot_submove'+submove+'.png')  