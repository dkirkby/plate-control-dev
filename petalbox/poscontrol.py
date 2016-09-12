# poscontrol.py
# 
# Michael Schubnell, University of Michigan
#
# 
# History:
# 	Aug. 2016: created
from Tkinter import *
import Pmw
import time,os
import pickle
#from pscemail import PSCemail
import pylab as pl
from configobj import ConfigObj


class PositionerControl(object):
	def __init__(self, root,verbose=False,log=False):		
		self.verbose=verbose
		self.root = root
		self.log = log
		self.root.title('Positioner Control')

# lock the update
		self.lockupdate=False

# read the config file
		#cconfigfile=os.environ.get('PSC_HWCONFPATH')+'control.conf'
		#cconfig = ConfigObj(cconfigfile)
		self.t_update=2000 # int(cconfig['topgui']['t_update'])*1000	# update time in msec
		#configfile=os.environ.get('PSC_HWCONFPATH')+'gui.conf'
		#config = ConfigObj(configfile)
		#self.t_alarm=int(cconfig['topgui']['t_alarm'])

		self.tstart=time.time()	# the start time of the GUI
		self.tstartemail=time.time()
#		self.pmail=PSCemail('schubnel@umich.edu')	# list of email recipients for email alerts.
		self.notify=None
		#if cconfig['topgui']['notify'] == 'yes':
		#	self.email=PSCemail(cconfig['topgui']['notify_list'])
#			self.notify='yes'

#		if cconfig['topgui']['notify_phone'] == 'yes':
#			self.pmail=PSCemail('schubnel@gmail.com')#cconfig['topgui']['notify_phone_list'])	
		
# read limits from the param configuration file
	
		#self.read_config()
		
# pyro stuff

		

# get last used scs run id number
		#homedir=os.environ.get('PSC_HOME')
		#indexfile = homedir+'log/scsindex.dat'
				
		#if self.verbose: print '*** index file:', indexfile
		
		#if os.path.exists(indexfile):
		#	info='index file does exist'
		#	if self.verbose: print '*** '+info+' ***'
		#	fd=open(indexfile,'r')
		self.scsrunid=1 #pickle.load(fd) +1
		#	fd.close()
		#else:
		#	info='index file does not exist'
		#	if self.verbose: print '*** '+info+' ***'
		#	self.scsrunid=0
		#fd=open(indexfile,'w')
		#pickle.dump(self.scsrunid, fd)
		#fd.close()

# Start a new log file
# get time and date and create file name
#

# open logbook file
# 
#log bfile Format /log/yymm/scsryymmdd%%%.log
		#srunid= '%6.6i' % self.scsrunid
		#logfile_path='/data/scs/log/gui/'+scsdate[0:4]+'/'
		#logfile_name=logfile_path+'scs'+scsdate+'r'+srunid+'.log'
		#if os.path.exists(logfile_name):
		#	if self.verbose: print 'log file does exist'
		#	self.logfile=open(logfile_name,'a')
		#else:
		#	if verbose: print '*** log file does not exist'
		#	if not os.path.exists(logfile_path):
		#		info='directory does not exist... creating'
		#		if verbose: print '*** .... creating '+logfile_path
		#		os.makedirs(logfile_path)
		#	self.logfile=open(logfile_name,'w')
#
		#self.logfile.write('*** Starting new SCS logfile *** UT date:'+scsdate+' UT time: '+scstime+' ***\n' )     




# the GUI components
		width=20
		self.defcol=root.cget("bg")
		masterframe = Frame(root)
		masterframe.pack()

		topframe=Frame(masterframe,bg='white')
		topframe.pack(side=TOP,fill=BOTH,expand=1)
		logoframe = Frame(topframe,bg='white')
		logoframe.pack(side=TOP,fill=BOTH,expand=1)	

		bodyframe = Frame(masterframe)
		bodyframe.pack(side=TOP,fill=BOTH,expand=1)	
	
		left_frame= Frame(bodyframe)
		left_frame.pack(side=LEFT, fill=Y, expand=1, padx=10, pady=5)

		right_frame= Frame(bodyframe)
		right_frame.pack(side=LEFT, fill=Y, expand=1, padx=10, pady=5)
#		
######## left frame #######################################################################
#
# ======================== Time group =================================
#
		g_time = Pmw.Group(left_frame, tag_text = ' Time and Date')
		
		messagebar_rid = Pmw.MessageBar(g_time.interior(),
			entry_width=width,
			entry_relief=GROOVE,
			labelpos=W,
			label_text='Log Nr.:')                            

		messagebar_rid.pack(side=BOTTOM, fill=X, expand=1, padx=10, pady=5)
		
		messagebar_rt = Pmw.MessageBar(g_time.interior(),
			entry_width=width,
			entry_relief=GROOVE,
			labelpos=W,
			label_text='Uptime:')

		messagebar_rt.pack(side=BOTTOM, fill=X, expand=1, padx=10, pady=5)

		messagebar = Pmw.MessageBar(g_time.interior(),
			entry_width=width,
			entry_relief=GROOVE,
			labelpos=W,
			label_text='Local Time:')

		messagebar.pack(side=BOTTOM, fill=X, expand=1, padx=10, pady=5)

			messagebar_ut = Pmw.MessageBar(g_time.interior(),
			entry_width=width,
			entry_relief=GROOVE,
			labelpos=W,
			label_text='        UT:')

		messagebar_ut.pack(side=BOTTOM, fill=X, expand=1, padx=10, pady=5)
		
		
		g_time.pack(side=TOP, fill=X, expand=1, padx=5, pady=5)		
		
######## center frame #######################################################		


# ======================== Relay group =================================
#
		ctrlgroup = Pmw.Group(left_frame, tag_text = 'Control')
		ctrlgroup.pack(side=TOP, fill=X, expand=1, padx=1, pady=5)
		
		self._posid = Pmw.EntryField(ctrlgroup.interior(),
                labelpos = 'w',
                label_text = '       Positioner ID:',
                validate = None,
                command = self.read_posid)
		self._posid.pack(side=TOP,  expand=1, padx=10, pady=5)


		self._dtheta = Pmw.EntryField(ctrlgroup.interior(),
                labelpos = 'w',
                label_text = 'Delta Theta (deg):',
                validate = None,
                command = self.read_theta)
		self._dtheta.pack(side=TOP,  expand=1, padx=10, pady=5)


		self._dphi = Pmw.EntryField(ctrlgroup.interior(),
                labelpos = 'w',
                label_text = '    Delta Phi (deg):',
                validate = None,
                command = self.read_phi)
		self._dphi.pack(side=TOP,  expand=1, padx=10, pady=5)


		move_button = Button(ctrlgroup.interior(),
			bg='gainsboro',
			text = 'Move', 
			command = self.move_pos,height=0)
		move_button.pack(side=RIGHT)

# ======================== Operator group =================================
#
		g_shifter = Pmw.Group(right_frame, tag_text = 'Operator')
		g_shifter.pack(side=TOP, fill=X, expand=1, padx=5, pady=5)
		self._shifter = Pmw.EntryField(g_shifter.interior(),
                labelpos = 'w',
                label_text = 'Name:',
                validate = None,
                command = self.readshiftername)
		self._shifter.pack(side=TOP,  expand=1, padx=10, pady=5)
		
		fixedFont = Pmw.logicalfont('Fixed')
 		self.commentbox = Pmw.ScrolledText(g_shifter.interior(),
				# borderframe = 1,
				labelpos = 'n',
				label_text='Comment',
#                columnheader = 1,
#                rowheader = 1,
#                rowcolumnheader = 1,
               usehullsize = 1,
               hull_width = 280,
               hull_height =80
#-				text_wrap='none',
#-				text_font = fixedFont,
#				Header_font = fixedFont,
#                Header_foreground = 'blue',
#                rowheader_width = 3,
#                rowcolumnheader_width = 3,
#-				text_padx = 4,
#-				text_pady = 4)
#				Header_padx = 4,
#				rowheader_pady = 4,
				)

		self.commentbox.pack(side=TOP,padx = 5, pady = 5, fill = 'both', expand = 1)
		buttonbox=Frame(g_shifter.interior())
		
		comment_clearButton = Button(buttonbox, bg='gainsboro',text = 'Clear', command = self.clear_comment,height=0)
		comment_clearButton.pack(side=RIGHT)
		comment_acceptButton = Button(buttonbox, bg='gainsboro',text = 'Enter', command = self.accept_comment,height=1)
		comment_acceptButton.pack(side=RIGHT)
		buttonbox.pack(side=BOTTOM)
		
# ======================== SCS Status group =================================
#	
		g_logging = Pmw.Group(right_frame, tag_text = 'Log')
		g_logging.pack(side=TOP, fill=BOTH, expand=1, padx=5, pady=5)
		fixedFont = Pmw.logicalfont('Fixed')
 		self.statusbox = Pmw.ScrolledText(g_logging.interior(),
				# borderframe = 1,
#				labelpos = 'n',
#				label_text='SCS Status',
#                columnheader = 1,
#                rowheader = 1,
#                rowcolumnheader = 1,
               usehullsize = 1,
               hull_width = 200,
               hull_height = 100,
#-				text_wrap='none',
#-				text_font = fixedFont,
#				Header_font = fixedFont,
#                Header_foreground = 'blue',
#                rowheader_width = 3,
#                rowcolumnheader_width = 3,
#				rowheader_pady = 4,
				)

		self.statusbox.pack(side=TOP,padx = 5, pady = 5, fill = 'both', expand = 1)

#------------------------------------------------------

		f_image=Frame(logoframe,bg='white')
		f_image.pack(side=TOP,expand=1)
		img=PhotoImage(file='poscontrol2.gif')
		# get the image size
		w = img.width()
		h = img.height()
 
# position coordinates of root 'upper left corner'
		x = 0
		y = 0
 
# make the root window the size of the image
#		f_image.geometry("%dx%d+%d+%d" % (w, h, x, y))
		logo=Label(logoframe,image=img,height=h,bg='white')   # [-TBD-] make it red for alarms!
		logo.image=img
		logo.pack(side=TOP,fill=X,expand=1)
# --------------------------
		self.time_display(messagebar,messagebar_ut,messagebar_rt,messagebar_rid)
		
		stime=time.strftime("%H:%M:%S", time.localtime())
	
		self.statusbox.insert('end',stime+' ***SCS start ***\n')
		self.statusbox.insert('end',stime+' Run ID: '+str(self.scsrunid)+'\n')
		

	def write_stext(self, stext):
		stime=time.strftime("%H:%M:%S", time.localtime())
		stext=stime+stext
		self.statusbox.insert('end',stext)
		if self.log: self.logfile.write(stext)  

	def clear_comment(self):
		self.commentbox.delete(1.0, END)

	def accept_comment(self):
		comment_text=self.commentbox.get(1.0, END)
		stime=time.strftime("%H:%M:%S", time.localtime())
		stext=stime+' Comment written to log'+'\n'
		self.statusbox.insert('end',stext)
		if self.log: 
			self.logfile.write(stext)
			self.logfile.write(comment_text)  
		pass

	def readshiftername(self):
		#stime=time.strftime("%H:%M:%S", time.localtime())
		shiftername=self._shifter.getvalue()
		stext=' New Op: '+shiftername+'\n'
		#self.statusbox.insert('end',stext)
		#self.logfile.write(stext)  
		self.write_stext(stext)

	def read_posid(self):
		posid=self._posid.getvalue()
		stext=' PosID selected: '+posid+'\n' 
		self.write_stext(stext)

	def read_theta(self):
		theta=self._dtheta.getvalue()
		stext=' Theta selected: '+theta+'\n'
		self.write_stext(stext)

	def read_phi(self):
		phi=self._dphi.getvalue()
		stext=' Phi selected: '+phi+'\n'
		self.write_stext(stext)

	def move_pos(self):
		posid=self._posid.getvalue()
		theta=self._dtheta.getvalue()
		phi=self._dphi.getvalue()
		stext=' Move req.: ID'+posid+' T'+theta+' P'+phi+'\n'

		# here we ask for the move

		self.write_stext(stext)


	def sec2HMS(self,seconds):
		seconds=int(seconds)
		hours = seconds / 3600
		seconds -= 3600*hours
		minutes = seconds / 60
		seconds -= 60*minutes
		if hours == 0:
			return "%02d:%02d" % (minutes, seconds)
		return "%02d:%02d:%02d" % (hours, minutes, seconds)

	def time_display(self,label,label_ut,label_rt,label_id):	
		def update_func():
			lowcolor='lightblue1'
			highcolor='pink1'
			normcolor='palegreen1'		
			t=time.time()
			label.after(self.t_update, update_func) # after 2000 ms update
			label.message('state',time.ctime(t))
			label_ut.message('state',time.asctime(time.gmtime()))
			runtime= self.sec2HMS(time.time()-self.tstart)
			label_rt.message('state',runtime)
			label_id.message('state',str(self.scsrunid))
		update_func()



	
if __name__ == '__main__':
	verbose=True
	if len(sys.argv) >=1:
		if len(sys.argv) == 2:
			if sys.argv[1].lower() == 'false':
				verbose=False
	
	
	root =Tk()
	
	rs=PositionerControl(root,verbose,log=False)

	bottom_menu=Frame(root)
	exitButton = Button(bottom_menu, bg='gainsboro',text = 'Exit', command = root.destroy)
	exitButton.pack(side=LEFT)

	bottom_menu.pack(side=BOTTOM, fill=X, expand=1, padx=5, pady=5)
	root.mainloop()


