from __future__ import print_function
import socket   #for sockets
import sys  #for exit

class PetSockComm(object):
    """socket client class
    """
    def __init__(self,host='',port=8888,verbose=False):
        self.host=host
        self.port=port
        self.verbose=verbose
        #create an INET, STREAMing socket
        try:
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error:
            if verbose: print('Failed to create socket')
            sys.exit()

        if self.verbose: print('Socket Created')

        #host = '131.243.51.243'
        #port = 8888

        try:
           remote_ip = socket.gethostbyname( host )

        except socket.gaierror:
            #could not resolve
            if self.verbose: print('Hostname could not be resolved. Exiting')
            sys.exit()

        #Connect to remote server
        self.s.connect((remote_ip , port))

        if self.verbose: print('Socket Connected to ' + host + ' on ip ' + remote_ip)


    def send_data(self,data):
        #Send some data to remote server
        message = str(data)

        try :
            #Set the whole string
            self.s.sendall(message)
        except socket.error:
            #Send failed
            if self.verbose: print('Send failed')
            sys.exit()

        if self.verbose: print('Message send successfully')


    def get_data(self,dlen):
        #Now receive data
        reply = self.s.recv(dlen)
        if self.verbose: print("Data received: "+str(reply))
        return reply

if __name__ == '__main__':
    sc=PetSockComm('131.243.51.243',8888,True)
    sc.send_data("Hello from Michael's MacBook")
    reply=sc.get_data(24)
