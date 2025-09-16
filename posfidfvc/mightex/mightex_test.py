#    Title:       test_mightex.py
#    Date:        03/30/2017
#    Author:      cad
#    Sysnopsis:   Test mightex Python code
#
#    Revisions:
#    mm/dd/yyyy who        description
#    ---------- --------   -----------
#
# ****************************************************************************

import mightex
import random
import time
import sys

thelogfilename=""
g_verbosity=5

serial_nos=["04-120502-002","04-170117-047","04-160119-002"]

#NOTE size of limits must be the same as m
# Limit for actual LED (first serial_no, channel 1) is 100
limits=[100,999,500,400,800,700,600,500]
led_off=[1,0,0,0,0,0,0,0]

try:
    m=[mightex.Mightex_LED_Controller(1,serial_nos[0]),
       mightex.Mightex_LED_Controller(2,serial_nos[0]),
       mightex.Mightex_LED_Controller(1,serial_nos[1]),
       mightex.Mightex_LED_Controller(2,serial_nos[1]),
       mightex.Mightex_LED_Controller(1,serial_nos[2]),
       mightex.Mightex_LED_Controller(2,serial_nos[2]),
       mightex.Mightex_LED_Controller(3,serial_nos[2]),
       mightex.Mightex_LED_Controller(4,serial_nos[2])]

    for i in range(len(limits)):
        if(0==m[i].setCurrentLimit(limits[i])):
            print("Bad current limit:",limits[i])

except IOError:
    print("Error, device doesn't exist")

def mydelay( delay_millisec=1000 ):
    if(delay_millisec > 0):
        time.sleep(delay_millisec/1000.0)

def newlogfilename(basename):
    global thelogfilename
    thelogfilename=time.strftime( basename+"%Y%m%d_%H%M%S.txt")

# log message with date and time
def logit(themessage,level=0):
    global thelogfilename
    global g_verbosity
    if(level <= g_verbosity):
        if(""==thelogfilename):
            newlogfilename("mightex_test_")
        try_counter=0
        while(30 > try_counter):
            try:
                logfile= open( thelogfilename, 'a' )
                logfile.write( time.strftime( "%x %X, " ) + themessage + "\n" )
                logfile.close()			# This will flush out the log after every line
                return
            except IOError:
                print("Error writing to log, waiting half second for retry")
                mydelay(500)
                try_counter=try_counter+1
    return

def logprint( themessage ):
    logit(themessage)
    print(time.strftime( "%x %X," ),themessage)

def mightex_test(verbose=0,tolerance=8):
    global m
    global limits

    # initialize random number generator
    done=0
    random.seed()

    failcount=[0 for j in range(len(m))]
    if(0!=verbose):
        for i in range(len(m)):
            m[i].mlc_Debug=1

    set_mA=[]
    read_mA=[]
    autopilot_used=[]
    for j in range(len(m)):
        set_mA.append(0)
        read_mA.append(0)
        autopilot_used.append(0)

    max_i=1000000
    for i in range(max_i):
        if(done):
            break;
        this_loop_success=1
        for j in reversed(range(len(m))):
            if(done):
                break;
            led_val=random.randint(0,limits[j])
            set_mA[j]=led_val
            if(failcount[j]<10):
                try:
                    success=m[j].setLevel(int(led_val),1)
                    autopilot_used[j]=m[j].mlc_autopilot_iterations
                    read_mA[j]=m[j].mlc_device_mA_Setting
                    # [max_val,val]=m[j].getLevels()
                    # read_mA[j]=val
                except IOError:
                    print("Check if ",m[j].mlc_serialno,"was removed")
                    failcount+=1
            else:
                done=1
                break;
        # leave leds on for 1/4 sec, then off 1/4 sec before next loop
        # time.sleep(0.25)
        for j in range(len(m)):
            if(led_off[j]):
                m[j].setMode(0)
        # time.sleep(0.25)

        # save results
        out_data=""
        for j in range(len(m)):
            out_data+=str(set_mA[j])+","+str(read_mA[j])+","+str(autopilot_used[j])+","
        logprint(out_data)

        # end of loop
    print("Done")


