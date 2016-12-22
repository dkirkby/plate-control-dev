# xypost_plots.py
# creates post xy_accuracy_test plots
# December 2016, M. Schubnell
import matplotlib.pyplot as plt
import matplotlib.mlab as mlab
import matplotlib.patches as patches
from scipy.stats import norm
import numpy as np
import csv
import sys


class PostPlots(object):
	def __init__(self,filename):
		self.filename=filename


	def read_movedata(self):
		"""
		Reads movedata from filename and returns dictionary 'movedata'
		INPUT
			filename: filename (including path) of movedata file
		RETURNS
			movedata=dictionary of lists with following elements
				'npoints', (int) number of submoves
				'nentries', (int) number of points
				'timestamp', (list of strings) format 2016-12-04 15:40:02.907794
				'cycle', (list of integres)
				'target_x', (list of floats)
				'target_y', (list of floats) 
				'meas_x<i>', (list of floats) with i=0,npoints-1
				'meas_y<i>',
				'err_x<i>',
				'err_y<i>',
				'err_xy<i>',
				'pos_t<i>',
				'pos_p<i>'

		"""	

		movefile=csv.DictReader(open(self.filename))
		movedata={}
		for row in movefile:
			for column, value in row.items():
				movedata.setdefault(column,[]).append(value)
		k=len(movedata.keys())
		movedata['npoints']=int((k-4)/7)
		movedata['nentries']=len(movedata['cycle'])
		return movedata


	def pieplot(self,movelist):
		fig4 = plt.figure(figsize=(10.5,8))

		ax = fig4.add_subplot(111, aspect='equal')
		X=np.array([float(i) for i in movelist['target_x']])
		Y=np.array([float(i) for i in movelist['target_y']])

		E0=np.array([float(i) for i in movelist['err_xy0']])
		E1=np.array([float(i) for i in movelist['err_xy1']])
		E2=np.array([float(i) for i in movelist['err_xy2']])
		E3=np.array([float(i) for i in movelist['err_xy3']])

		plt.plot(X,Y,'+',markersize=40,color='red')
		scale=50.
		for i,x in enumerate(zip(X,Y)):

			ax.add_patch(patches.Wedge(x, 0.1*scale/10., 0, 90 ,color='black',alpha=0.4,fill=False))
			ax.add_patch(patches.Wedge(x, 0.05*scale/10., 90, 360 ,color='black',alpha=0.4,fill=False))
			ax.add_patch(patches.Wedge(x, E0[i]*scale/10., 0, 90 ,color='blue',alpha=0.4))
			ax.add_patch(patches.Wedge(x, E1[i]*scale, 90, 180 ,color='lightsalmon',alpha=0.6))
			ax.add_patch(patches.Wedge(x, E2[i]*scale, 180, 270 ,color='tomato',alpha=0.8))
			ax.add_patch(patches.Wedge(x, E3[i]*scale, 270, 360 ,color='r',alpha=0.8))	

		y=ax.get_ylim()
		ax.set_ylim(y[0]-2,y[1]+2)
		x=ax.get_xlim()
		ax.set_xlim(x[0]-2,x[1]+2)
		pie_colors=['blue','lightsalmon','tomato','red']
		for i,col in enumerate(pie_colors):
			text='Submove '+str(i)
			ax.text(0.05,0.93-0.03*i,text,transform=ax.transAxes,fontsize=12,color=col)

		x=x[1]+1
		y=y[1]+1
		ax.add_patch(patches.Wedge((x,y), 0.1*scale/10., 0, 90 ,color='black',alpha=0.4,fill=False))
		ax.add_patch(patches.Wedge((x,y), 0.05*scale/10., 90, 360 ,color='black',alpha=0.4,fill=False))
		ax.text(x+0.2,y+0.5,'100',fontsize=8,color='black')
		ax.text(x-.5,y-0.06,'5',fontsize=8,color='black')
		ax.text(x-1.4,y-0.6,'Scale in microns',fontsize=8,color='black')

		plt.xlabel("x [mm]")
		plt.ylabel("y [mm]")

		return(fig4)	

	def quiverplot(self,movelist):

		fig6 = plt.figure(figsize=(10.5,8))

		ax=fig6.add_subplot(111)
		TX=np.array([float(i) for i in movelist['target_x']])
		TY=np.array([float(i) for i in movelist['target_y']])

		X0=np.array([float(i) for i in movelist['meas_x0']])
		Y0=np.array([float(i) for i in movelist['meas_y0']])

		DX=X0-TX
		DY=Y0-TY
		distance = np.sqrt(DX**2 + DY**2)
		scale=(1./np.max(distance))*.2
		ax.plot(TX,TY,'r+',markersize=20)

		ax.quiver(TX,TY, DX,DY, color='dodgerblue', headlength=6,scale=1.)  # 1 for blind move; 0.05 for submoves
		y=ax.get_ylim()
		ax.set_ylim(y[0]-2,y[1]+2)
		x=ax.get_xlim()
		ax.set_xlim(x[0]-2,x[1]+2)
		
		ax.quiver(x[0]-1.,y[1]+1.,0.1,0., color='dodgerblue', headlength=6,scale=1.)
		text='Submove 0'
		ax.text(0.7,0.9,text,transform=ax.transAxes,fontsize=14)
		text='100 microns'
		ax.text(0.05,0.89,text,transform=ax.transAxes)
		plt.xlabel("x [mm]")
		plt.ylabel("y [mm]")
		return(fig6)


	def histoplot(self,movelist):

		nmoves=movelist['npoints']
		pgrid={1:110,2:210,3:220,4:220,5:320,6:320,7:330,8:330,9:330}
		wins=pgrid[nmoves]
		fig6 = plt.figure(figsize=(10.5,8))
		TX=np.array([float(i) for i in movelist['target_x']])
		TY=np.array([float(i) for i in movelist['target_y']])

		for ii in range (0,nmoves):
			ax=fig6.add_subplot(wins+ii+1)
			DX=np.array([float(i) for i in movelist['meas_x'+str(ii)]]) - TX
			DY=np.array([float(i) for i in movelist['meas_y'+str(ii)]]) - TY
			distance = np.sqrt(DX**2 + DY**2) * 1000.

			if i==0:
				col='cornflowerblue'
				alp=0.75
			else:
				col='lightsalmon'
				alp=0.7
			n, bins, patches = ax.hist(distance, 30, normed=1, facecolor=col, alpha=alp)
			plt.ylabel("dN/dD (normalized)")
			plt.xlabel("distance error D (micron)")

			(mu,sigma) = norm.fit(distance)
			avg=np.mean(distance)
			rms = np.sqrt(np.mean(distance*distance))
			maxval = np.max(distance)
			text='Submove '+str(ii)
			ax.text(0.4,0.9,text,transform=ax.transAxes)

			lvals=('Max: ','Mean: ','Sigma: ','Avg: ','RMS: ')
			legend={'Max: ':maxval,'Mean: ':mu,'Sigma: ':sigma,'Avg: ':avg,'RMS: ':rms}
			ylegend=0.9
			for l in lvals:
				text=l+'{:5.1f}'.format(legend[l])
				ylegend=ylegend-0.05
				ax.text(0.7,ylegend,text,transform=ax.transAxes,fontsize=10)

			y = mlab.normpdf(bins,mu,sigma)
			ax.plot(bins,y,'b--',linewidth=2)

			y=ax.get_ylim()
			req=5.
			if ii==0: req=100.
			ax.plot((req,req),y,'k--',linewidth=2)
		return(fig6)



	def gridplot(self,movelist, submove): #path_no_ext, pos_id, data, center, theta_range, r1, r2, title_txt):
   
		plt.ioff() # interactive plotting off

		n_targets = movelist['npoints']
		targ_x = np.array([float(i) for i in movelist['target_x']])
		targ_y = np.array([float(i) for i in movelist['target_y']])


#    radius = r1 + r2
#    min_line_x = [center[0], radius * np.cos(theta_range[0]*np.pi/180) + center[0]]
#    min_line_y = [center[1], radius * np.sin(theta_range[0]*np.pi/180) + center[1]]
#    max_line_x = [center[0], radius * np.cos(theta_range[1]*np.pi/180) + center[0]]
#    max_line_y = [center[1], radius * np.sin(theta_range[1]*np.pi/180) + center[1]]
#    annulus_angles = np.arange(0,360,5)*np.pi/180
#    annulus_angles = np.append(annulus_angles,annulus_angles[0])
#    annulus_inner_x = center[0] + np.abs(r1-r2) * np.cos(annulus_angles)
#    annulus_inner_y = center[1] + np.abs(r1-r2) * np.sin(annulus_angles)
#    annulus_outer_x = center[0] + np.abs(r1+r2) * np.cos(annulus_angles)
#    annulus_outer_y = center[1] + np.abs(r1+r2) * np.sin(annulus_angles)
		s=submove

		fig = plt.figure(figsize=(10.5,8))
		#meas_x = [data['meas_obsXY'][s][i][0] for i in range(n_targets)]
		#meas_y = [data['meas_obsXY'][s][i][1] for i in range(n_targets)]


		meas_x=np.array([float(i) for i in movelist['meas_x'+str(s)]])
		meas_y=np.array([float(i) for i in movelist['meas_y'+str(s)]])
		E=np.array([float(i) for i in movelist['err_xy'+str(s)]])

		summary_txt  = '\n'
		summary_txt += 'SUBMOVE: ' + str(s) + '\n'
		summary_txt += '--------------------\n'
		summary_txt += 'error max: ' + format(np.max(E*1000),'6.1f') + ' um\n'
		summary_txt += '      rms: ' + format(np.sqrt(np.mean(E)**2)*1000,'6.1f') + ' um\n'
		summary_txt += '      avg: ' + format(np.mean(E)*1000,'6.1f') + ' um\n'
		summary_txt += '      min: ' + format(np.min(E)*1000,'6.1f') + ' um\n'
		plt.plot(targ_x,targ_y,'ro',label='target points',markersize=4,markeredgecolor='r',markerfacecolor='None')        
		plt.plot(meas_x,meas_y,'k+',label='measured data',markersize=6,markeredgewidth='1')
		#plt.plot(annulus_outer_x,annulus_outer_y,'b-',linewidth='0.5',label='patrol envelope')    
		#plt.plot(annulus_inner_x,annulus_inner_y,'b-',linewidth='0.5')
		#plt.plot(min_line_x,min_line_y,'g-',linewidth='0.5',label='theta min')
		#plt.plot(max_line_x,max_line_y,'g--',linewidth='0.8',label='theta max')
		txt_x = np.min(plt.xlim()) + np.diff(plt.xlim()) * 0
		txt_y = np.max(plt.ylim()) - np.diff(plt.ylim()) * 0
		plt.text(txt_x,txt_y,summary_txt,horizontalalignment='left',verticalalignment='top',family='monospace',fontsize=10)
		plt.xlabel('x (mm)')
		plt.ylabel('y (mm)')
		#plt.title(str(title_txt) + '\n' + str(pos_id) + ', ' + str(n_targets) + ' targets\n ')
		plt.grid(True)
		plt.margins(0.0, 0.03)
		plt.axis('equal')
		plt.legend(loc='upper right',fontsize=8)
		#plt.savefig(path_no_ext + '_submove' + str(s) + '.png',dpi=150)
		#plt.close(fig)
		return(fig)





if __name__=="__main__":

	filepath=os.environ['POSITIONER_LOGS']+'/test_logs'
	filename='M00175_2016-12-05_T172230_slamtest20'

	post=PostPlots(filepath+filename+'_movedata.csv')

	movelist=post.read_movedata()
	ngridpoints=movelist['nentries']
	print("... creating histoplot")
	fig=post.histoplot(movelist)
	fig.suptitle(filename+'\n'+str(ngridpoints)+' Points', fontsize=14)
	fig.savefig(filename+'_histoplot.png', dpi=150)
	print("... creating quiverplot")
	fig=post.quiverplot(movelist)
	fig.suptitle(filename+'\n'+str(ngridpoints)+' Points', fontsize=14)
	fig.savefig(filename+'_quiverplot.png', dpi=150)
	print("... creating pieplot")
	fig=post.pieplot(movelist)
	fig.suptitle(filename+'\n'+str(ngridpoints)+' Points', fontsize=14)
	fig.savefig(filename+'_pieplot.png', dpi=150)
	print("... DONE")
	sys.exit()

