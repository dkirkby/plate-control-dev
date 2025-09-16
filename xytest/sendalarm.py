# SendAlarm
#
# 	by Michael Schubnell, University of Michigan
#	schubnel@umich.edu
#
#	History:
#	March 2017: created
#
#	To Do:
#
import smtplib
from email.mime.text import MIMEText
class SendAlarm(object):
	def __init__(self,toaddrs  = 'schubnel@gmail.com'):
		""" toaddrs must be a list if there is more than a single address: ['user@xyz.com','someone@abc.com']"""
		self.username = 'desipositionerproduction'
		self.password = 'Mayall4m'
		self.toaddrs=toaddrs
	def send(self,subject='Positioner test alarm',inmsg='Unknown error'):
		fromaddr = 'desipositionerproduction@gmail.com'
		to = self.toaddrs
		msg=MIMEText(inmsg)
		msg['Subject'] = subject
		msg['From'] = fromaddr
		msg['To'] = ', '.join(to)
# Now send the mail
		server = smtplib.SMTP('smtp.gmail.com:587')
		server.starttls()
		server.login(self.username,self.password)
		server.sendmail(fromaddr, to, msg.as_string())
		server.quit()
if __name__ == "__main__":
	sendalarm=SendAlarm(['schubnel@umich.edu','7343951248@txt.att.net','kfanning@umich.edu','2488187909@messaging.sprintpcs.com'])
	sendalarm.send ('test stand UM1 alarm','test no longer running')
