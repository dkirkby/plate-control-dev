# watcher.py
# Michael Schubnell, University of Michigan
# March 29, 2017

import sys
import os
import time
import sendalarm

NOTIFY=['schubnel@umich.edu','7343951248@txt.att.net'] 
""" Alltel: phonenumber@message.alltel.com.
    AT&T: phonenumber@txt.att.net.
    T-Mobile: phonenumber@tmomail.net.
    Virgin Mobile: phonenumber@vmobl.com.
    Sprint: phonenumber@messaging.sprintpcs.com.
    Verizon: phonenumber@vtext.com.
    Nextel: phonenumber@messaging.nextel.com.
"""
INTERVAL=60.
PROCNAME='xytest.py'
SUBJECT='Test stand UM1 alarm'

def getpids(procname='xytest.py'):
	aux=os.popen("ps aux").read()
	pids=[]	
	for line in aux.split('\n'):
		    if procname in line:
		            pids.append(line.split()[1])
	return pids

if __name__=="__main__":
	alarm=sendalarm.SendAlarm(NOTIFY)
	pids=getpids(PROCNAME)
	if len(pids) > 1:
		print("More than one process with name "+PROCNAME+" running!!")
		sys.exit()

	run=True
	while run:		 		
		if (len(pids) !=1) or ( not os.path.exists("/proc/"+pids[0])):
			alarm.send (SUBJECT,'xytest no longer running')
			sys.exit()
		time.sleep(INTERVAL)
