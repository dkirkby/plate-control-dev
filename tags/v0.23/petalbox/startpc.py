from configobj import ConfigObj
from sys import exit
from os import chmod

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
	text='python3 petalcontroller.py --role '+role+' --service PetalControl'
	with open("startpc.sh", "w") as text_file:
    		print(text, file=text_file)
	chmod("startpc.sh", 0o755)
except:
	print ("Error writing startpc.sh")
	exit()
