# watcher.py
# Michael Schubnell, University of Michigan
# March 29, 2017

import sys
import os
import time
import sendalarm
import psutil

NOTIFY=['schubnel@umich.edu','7343951248@txt.att.net','kfanning@umich.edu','2488187909@messaging.sprintpcs.com'] 
""" Alltel: phonenumber@message.alltel.com.
    AT&T: phonenumber@txt.att.net.
    T-Mobile: phonenumber@tmomail.net.
    Virgin Mobile: phonenumber@vmobl.com.
    Sprint: phonenumber@messaging.sprintpcs.com.
    Verizon: phonenumber@vtext.com.
    Nextel: phonenumber@messaging.nextel.com.
"""
INTERVAL=180.					# this determines the time interval (in seconds) between checks 
PROCNAME='xytest.py'			# watcher.py looks for this process in the process table.
								# an error condition PROC_ERR is generated if a) this process does not exist or b) multiple instances of this process are running 	
SUBJECT='Test stand UM1 alarm'	# subject line of email/text message sent out if error condition is triggered

LOW_MEM_THRESH=50				# Low memory mark (in MB). If available memory falls below this threshold the error condition LOW_MEM is triggered					
LOW_SPACE_THRESH=100			# Low disk space mark (in MB). If free disk space falls below this threshold the error condition LOW_SPACE is triggered	

def getpids(procname='xytest.py'):
	aux=os.popen("ps aux").read()
	pids=[]	
	for line in aux.split('\n'):
		    if procname in line:
		            pids.append(line.split()[1])
	return pids

def sys_status()
	status={}
	status['mem_free'] =int( psutil.virtual_memory()[1] / 1000000 )
	status['disk_free']=int( psutil.disk_usage('/')[2] / 1000000 )
	return status

if __name__=="__main__":
	print("main")
	errcon={'LOW_MEM':False,'LOW_SPACE'=False,'PROC_ERR'=False}

	alarm=sendalarm.SendAlarm(NOTIFY)
	pids=getpids(PROCNAME)
	if len(pids) > 1:
		print("More than one process with name "+PROCNAME+" running!!")
		sys.exit()

	run=True
	while run:
		print"here")		 		
		if (len(pids) !=1) or ( not os.path.exists("/proc/"+pids[0])):
			errcon['PROC_ERR']='True'
			alarm.send (SUBJECT,'xytest no longer running')
			sys.exit()
		status=sys_status()
		if status['mem_free'] < LOW_MEM_THRESH:
			errcon['LOW_MEM']=True
			alarm.send (SUBJECT,'Warning: Low Memory')
		if status['disk_free'] < LOW_MEM_THRESH:
			errcon['LOW_SPACE']=True
			alarm.send (SUBJECT,'Warning: Low Disk Space')
		time.sleep(INTERVAL)
