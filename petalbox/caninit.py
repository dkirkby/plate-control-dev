from configobj import ConfigObj
from sys import argv,exit
canlist=argv[1]
canlist.replace(" ","")
canlist=canlist.lower()
ncan=canlist.count('can')
if ncan < 1:
	print("Error in canlist")
	exit() 
if ncan == 1: canlist=canlist+","
try:
	config=ConfigObj('petalcontroller.ini')
	role=config['role']
except:
	print ("Error reading petalcontroller.ini file")
	exit()
if role not in ['PC1','PC2','PC3','PC4','PC5','PC6','PC7','PC8','PC9','PC0']:
	print ("Role must be PC<n>")
	exit()
try:
	config=ConfigObj('petalcontroller.conf')
	config['CAN'][role]['canlist']=canlist
	config.write()
except:
	print ("Error modifying petalcontroller.conf file")
	exit()
