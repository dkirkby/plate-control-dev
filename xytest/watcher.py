# watcher.py
# Michael Schubnell, University of Michigan
# March 29, 2017
import os
import sys
from time import sleep
import sendalarm
import configobj

sys.path.append(os.path.abspath('../petal/'))
import posconstants as pc
hwdir = pc.dirs['hwsetups']

poslogsdir = pc.dirs['xytest_logs']
alltestlogs = [os.path.join(poslogsdir, logname) for logname in os.listdir(poslogsdir)]
newestfile = max(alltestlogs, key = os.path.getctime)

i_conf = configobj.ConfigObj(hwdir+'local_identity.conf',unrepr=True,encoding='utf-8')
this_site=i_conf['site']
hw_conf=configobj.ConfigObj(hwdir+'hwsetup_'+this_site+'.conf',unrepr=True,encoding='utf-8')

NOTIFY=hw_conf['watcher']['notify']
#NOTIFY=['schubnel@umich.edu','7343951248@txt.att.net','kfanning@umich.edu','2488187909@messaging.sprintpcs.com']
""" Alltel: phonenumber@message.alltel.com.
    AT&T: phonenumber@txt.att.net.
    T-Mobile: phonenumber@tmomail.net.
    Virgin Mobile: phonenumber@vmobl.com.
    Sprint: phonenumber@messaging.sprintpcs.com.
    Verizon: phonenumber@vtext.com.
    Nextel: phonenumber@messaging.nextel.com.
"""
INTERVAL=hw_conf['watcher']['interval']
PROCNAME=hw_conf['watcher']['procname']
SUBJECT='Test stand '+str(this_site)+' alarm'

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
	if PROCNAME == 'xytest.py':
		while run:
			if (len(pids) !=1) or ( not os.path.exists("/proc/"+pids[0])):
				finishcheck = list(open(newestfile, 'r'))[-2]
				if finishcheck[-15:-1] == "Test complete.":
					alarm.send (SUBJECT,'xytest is complete')
				else:
					alarm.send (SUBJECT,'xytest has crashed')
				sys.exit()
			sleep(INTERVAL)
	else:
		while run:
			if (len(pids) !=1) or ( not os.path.exists("/proc/"+pids[0])):
				alarm.send (SUBJECT,'xytest no longer running')
				sys.exit()
			sleep(INTERVAL)


