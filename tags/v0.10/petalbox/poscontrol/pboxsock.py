'''
    socket server for communicating with petalcomm.py
'''
from __future__ import print_function 
import socket
import sys
from thread import start_new_thread
 
verbose=True
HOST = ''
PORT = 8888 # pick a port
 
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
if verbose: print('Socket created')
 
# now bind socket to local host and port
try:
    s.bind((HOST, PORT)) 
except socket.error as msg:
    if verbose: print('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
    sys.exit()
     
if verbose: print('Socket bind success')
 
# start listening on socket; maximum number of queued connetions = 10
maxqueue=10
s.listen(maxqueue)
if verbose: print('Socket now listening')
 
# this function handles the connections. It will be used to create threads
def clientthread(conn):
# if we want to send a message first to the client we would do this here
#   conn.send('Welcome to the server. Type something and hit enter\n') #send only takes string
    # infinite loop so that function does not terminate and thread does not end.
    while True:
        print( ">>>> in loop") 
        #Receiving from client
        data = conn.recv(16)
        print( "received ..."+str(data))
        reply = 'OK...' + data
        if not data:
#            print "no data  :("
            break
     
        conn.sendall(reply)

    # we came out of the loop - closing the connection
    conn.close()
 
# keep talking with the client
while 1:
    #wait to accept a connection - blocking call
    conn, addr = s.accept()
    if verbose: print('Connected with client at' + addr[0] + ':' + str(addr[1]))
     
    # start new thread takes 1st argument as a function name to be run,
    # second is the tuple of arguments to the function.
    start_new_thread(clientthread ,(conn,))
 
s.close()
