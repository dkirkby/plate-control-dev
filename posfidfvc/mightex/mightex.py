#    Title:       mightex.py
#    Date:        03/23/2017
#    Author:      cad
#    Sysnopsis:   Class for Mightex LED Controllers
#
#    Revisions:
#    mm/dd/yyyy who        description
#    ---------- --------   -----------
#    03/29/2017 cad        Use instance variables, not Class variables
# ****************************************************************************

import subprocess

class Mightex_LED_Controller:
    """Class for Mightex LED Controllers"""

    # Not for external use, sends commands to the Controller via mightex_cmd
    # The initial version of this code takes about 35 seconds to execute 100
    # setLevel commands where the mode is specified, and 25 seconds where the
    # mode is not specified.
    def __mightexCmd__(self,command,no_channel=0,no_serialno=0):
        mycommand=['mightex_cmd']
        # if user specified a Serial number, use it
        if(0==no_serialno and 1==self.mlc_initialized and ""!=self.mlc_serialno):
            mycommand.append('-N')
            mycommand.append(str(self.mlc_serialno))
        # if user specified a channel, use it
        if(0==no_channel and 1==self.mlc_initialized and 1!=int(self.mlc_currentChannel)):
            mycommand.append('-H')
            mycommand.append(str(self.mlc_currentChannel))
        mycommand+=command
        if(self.mlc_Debug):
            print("Command: ",mycommand)
        p=subprocess.Popen(mycommand,stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
        ans=p.communicate()
        self.mlc_last_stdout=ans[0]
        self.mlc_last_stderr=ans[1]
        # print("stdout: " + ans[0] + "\n")
        # print("stderr: " + ans[1] + "\n")
        return ans[0]

    # Open a specific channel (default 1) on the Mightex LED Controller with the specified
    # serial number, or if no serial number is specified, on the last LED controller in the list
    # (i.e., essentially chosen at random since the order on the list is determined by the
    # order of connection/discovery)
    def __init__(self,channel=1,serialno=""):
        self.mlc_initialized=0     # is the Mightex LED Controller initialized
        self.mlc_maxChannel=0      # number of channels for the device
        self.mlc_currentChannel=1  # default Chanel is 1
        self.mlc_serialno=""       # by default, talk to the first found device
        self.mlc_serialno_list=[]
        self.mlc_error_msg=""
        self.mlc_last_stdout=[]
        self.mlc_last_stderr=[]
        self.mlc_Debug=0

        self.mlc_serialno=str(serialno)  # If the user specified one, talk to it

        # query for serial numbers of attached Mightex LED Controllers
        self.mlc_serialno_list=self.__mightexCmd__(['-n']).split(",")
        num_serialno=len(self.mlc_serialno_list)
        for i in range(num_serialno):
            self.mlc_serialno_list[i]=self.mlc_serialno_list[i].strip()
        # check for no controlleres
        if(1==num_serialno and ""==self.mlc_serialno_list[0]):
            num_serialno=0
        if(self.mlc_Debug):
            print("num=",num_serialno," list=",self.mlc_serialno_list," serialno=",str(serialno))
        # If user specified a serial number, check if it's in the list
        if(num_serialno>0):
            if(str(serialno)!=""):
                for i in range(num_serialno):
                    if(self.mlc_Debug):
                        print("i=",i)
                    if(str(serialno)==str(self.mlc_serialno_list[i])):
                        self.mlc_initialized=1
                        self.mlc_serialno=str(serialno)
                        if(0!=channel):
                            self.mlc_currentChannel=channel
                        break;
            else:
                self.mlc_serialno=str(self.mlc_serialno_list[num_serialno-1])
                self.mlc_initialized=1
                if(0!=int(channel)):
                    self.mlc_currentChannel=int(channel)
            if(0==self.mlc_initialized):
                if(""!=str(serialno)):
                    self.mlc_error_msg="SerialNo " + str(serialno) + " not found"
                else:
                    self.mlc_error_msg="No Mightex LED Controllers found"
            else:
                if(self.mlc_Debug and self.mlc_initialized):
                    print("Initialized SerialNo: ",self.mlc_serialno)
        else:
            self.mlc_error_msg="No Mightex LED Controllers found"
        if(0!=self.mlc_initialized):
            # Get maximum channels for this controller
            ans_maxChannel=self.__mightexCmd__(['-e'],1).split("=")
            if(len(ans_maxChannel)>1):
                self.mlc_maxChannel=int(ans_maxChannel[1].strip())
                # print("answer=",ans_maxChannel)
                if(self.mlc_Debug):
                    print("maxChannel=",self.mlc_maxChannel)
                if(self.mlc_maxChannel < self.mlc_currentChannel):
                    self.mlc_initialized=0
                    self.mlc_error_msg="Specified channel, " +str(self.mlc_currentChannel) + " is > Max channel, " + str(self.mlc_maxChannel)
                    if(self.mlc_Debug):
                        print(self.mlc_error_msg)

            else:
                self.mlc_error_msg="maxChannel error"
                self.mlc_initialized=0
                if(self.mlc_Debug):
                    print(self.mlc_error_msg)
        if(0==self.mlc_initialized):
            raise IOError(self.mlc_error_msg)
        return

    # returns the maximum number of channels for the current Mightex LED Controller
    def getMaxChannels(self):
        if(0!=self.mlc_initialized):
            return int(self.mlc_maxChannel)
        else:
            return

    # returns a list of the serial numbers for currently attached Mightex LED Controllers
    def getSerialNos(self):
        if(0!=self.mlc_initialized):
            ans_sn=self.__mightexCmd__(['-n'],1,1).strip()
            ans_sn=ans_sn.strip('(')
            ans_sn=ans_sn.strip(')')
            ans_list=ans_sn.split(',')
            if(0!=len(ans_list)):
                return ans_list
            return []   # return an empty list
        else:
            return

    # returns the present mode of the current Channel
    def getMode(self):
        if(0!=self.mlc_initialized):
            ans_Mode=self.__mightexCmd__(['-m']).strip()
            try:
                int(ans_Mode)
                return int(ans_Mode)
            except:
                raise IOError("getMode returned '"+str(ans_Mode)+"'")
            return
        else:
            return

    def setMode(self,mode=0):
        if(0!=self.mlc_initialized):
            ans_Mode=self.__mightexCmd__(['-M',str(int(mode))]).strip()
            if(self.mlc_Debug):
                print(ans_Mode)
            if("##"==str(ans_Mode)):
                return 1
            else:
                raise IOError("setMode returned '"+str(ans_Mode)+"'")
            return 0
        else:
            return

    # returns a list of the Maximum and Current milliAmp levels for the current Channel        
    def getLevels(self):
        if(0!=self.mlc_initialized):
            ans_MaxSet=self.__mightexCmd__(['-c']).strip()
            ans_list=ans_MaxSet.split()
            if(2==len(ans_list)):
                ans_list[0]=ans_list[0].strip(',')
                return ans_list
            else:
                raise IOError("SN='"+str(self.mlc_serialno)+"' Channel="+str(self.mlc_currentChannel))
            return
        else:
            return

    # Set the value of the LED current in milliAmps
    # Optionally, specify the Mode and the Maximum LED current
    # If the Mode is not specified, none will be set (NOTE: no changes to the
    # LED intensity are made until you set Mode 1, even if already in Mode 1)
    # If the Maximum is not specified, it is set to 10 more than what you specified
    # (up to a maximum of 1000)
    def setLevel(self,led_milliamps=0,mode=-1,max_led_milliamps=-1):
        if(0!=self.mlc_initialized):
            if(-1==max_led_milliamps):
                max_led_milliamps=10+int(led_milliamps)
                if(max_led_milliamps>1000):
                    max_led_milliamps=1000
            if(1000<int(led_milliamps)):
                led_milliamps=1000
            cvals=str(max_led_milliamps)+" "+str(led_milliamps)
            ans_setLevel=self.__mightexCmd__(['-C',cvals]).strip()
            if(self.mlc_Debug):
                print(ans_setLevel)
            if("##"==str(ans_setLevel)):
                if(-1!=mode):
                    return self.setMode(int(mode))
                else:
                    return 1
            else:
                raise IOError("setLevel returned '"+str(ans_setLevel)+"'")
            return 0
        else:
            return

    # Load the Factory Defaults for all settings
    # NOTE: the new settings do not take effect until you set the Mode
    # and they are NOT saved in the NVRAM
    def setFactoryDefaults(self):
        if(0!=self.mlc_initialized):
            ans_FR=self.__mightexCmd__(['-F'],1).strip()
            if(self.mlc_Debug):
                print(ans_FR)
            return
        else:
            return

    # Reset the Mightex LED Controller
    # CAUTION: Executing this command may require a Linux restart to recover!
    def setReset(self):
        if(0!=self.mlc_initialized):
            ans_RS=self.__mightexCmd__(['-R'],1).strip()
            if(self.mlc_Debug):
                print(ans_RS)
            return
        else:
            return

    # Save settings to NVRAM, the current settings, including MODE
    # will be restored at power-on reset
    def setSaveDefaults(self):
        if(0!=self.mlc_initialized):
            ans_SD=self.__mightexCmd__(['-S'],1).strip()
            if(self.mlc_Debug):
                print(ans_SD)
            return
        else:
            return


