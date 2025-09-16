/*******************************************
 H+

  Title:	mightex_cmd.c
  Author:	Carl Dobson
  Date:		03/02/2017
  Synopsis:	Send commands to MIGHTEX Universal LED Controller (SLC-MA series) and gets replies
  Usage:	mightex_cmd [-acdehimnrvVFRS] [-C "Max Set"] [-D device_path] [-H channel_num] [-M mode_num] [-N serial_no]
  Options:
		-a		Show information for all Mightex devices (note, no settings will be read,
				and no commands will be sent to the controller)
		-c		Show Maximum and Set Current (milliAmp)
		-C "Max Set"	Set Maximum and Set Current (milliAmp) values
		-d		Show automatically found device_path
		-D device_path	Use the specified device path rather than auto-finding it
		-e		Show maximum channels for active controller
		-F		Reset the Mightex controller to factory defaults
		-h		Print a help message
		-H channel_num	Use the specified channel (default is channel 1)
		-i		Send DEVICEINFO command
		-m		Show current mode
		-M mode_num	Set current mode_num
		-n		Show comma-separated list of Serial No(s) of attached Mightex devices
		-N serial_no	Use the device with the specified serial number
		-r		Show revision number of mightex_cmd
		-R		Reset the Mightex controller
		-S		Save the active settings to NVRAM (after power cycle,
				the controller will turn on with the active settings loaded)
		-v		Verbose (output written to stderr)
		-V		Even more Verbose (output written to stderr)

  Revisions:
  mm/dd/yyyy who       description
  ---------- --------  ------------------------------------------
  05/10/2017 cad       Cleared out all incoming data before first real query

 H-
*******************************************/

#include <libudev.h>
#include <locale.h>

/* Linux */
#include <linux/types.h>
#include <linux/input.h>
#include <linux/hidraw.h>

/*
 * Ugly hack to work around failing compilation on systems that don't
 * yet populate new version of hidraw.h to userspace.
 */
#ifndef HIDIOCSFEATURE
#warning Please have your distro update the userspace kernel headers
#define HIDIOCSFEATURE(len)    _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x06, len)
#define HIDIOCGFEATURE(len)    _IOC(_IOC_WRITE|_IOC_READ, 'H', 0x07, len)
#endif

/* Unix */
#include <sys/ioctl.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

/* C */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include <ctype.h>

static char *mightex_cmd_version="1.00";

#define MAX_STR 1024
#define MAX_CMD_QUEUE 128
#define MAX_MIGHTEX_DEVICES 10
static char idVendor[MAX_STR];
static char idProduct[MAX_STR];
static char Manufacturer[MAX_STR];
static char Product[MAX_STR];
static char useSerialNo[MAX_STR];
static char SerialNo[MAX_STR];
static char Device_Node_Path[MAX_STR];
static char Command_Queue[MAX_CMD_QUEUE][MAX_STR];
static int  Max_Channels;

static int nMightexDevices=0;
static char m_SerialNo[MAX_MIGHTEX_DEVICES][MAX_STR];
static char m_idVendor[MAX_MIGHTEX_DEVICES][MAX_STR];
static char m_idProduct[MAX_MIGHTEX_DEVICES][MAX_STR];
static char m_Product[MAX_MIGHTEX_DEVICES][MAX_STR];
static char m_Device_Node_Path[MAX_MIGHTEX_DEVICES][MAX_STR];
static int m_Max_Channels[MAX_MIGHTEX_DEVICES];

static int Command_Count;
static char MaxSet[MAX_STR];
static int iMaxmilliA,iSetmilliA;
static int channel_num=1;
static int mode_num;
static int verbose=0;
static int prev_stdout=0;
static int prev_stderr=0;

static int aflag,cflag,dflag,eflag,hflag,iflag,mflag,nflag,rflag;
static int CapCflag, CapDflag, CapFflag, CapHflag, CapMflag, CapNflag, CapRflag, CapSflag;

/* Function prototypes */
int hidmain(char *use_device);
int add_to_command_queue(char *command);
void mystrncpy(char *dest, const char *src, size_t max_dest);
void mystrncat(char *dest, const char *src, size_t max_dest);
int my_snprintf(char *buffer, size_t buffer_size, const char *fmt, ...);
const char *bus_str(int bus);

// BEWARE of SIDE EFFECTS when using mystrSZcpy and mystrSZcat!  (a is perhaps evaluated TWICE!)
#define mystrSZcpy(a,b)	mystrncpy((a),(b),sizeof(a))
#define mystrSZcat(a,b)	mystrncat((a),(b),sizeof(a))

static int print_debug_output=0;

/* print usage string to stderr */
void print_usage(FILE *fp)
{
	fprintf(fp,
	  "Usage: mightex_cmd [-acdehimnrvFRSV] [-C \042Max Set\042] [-D device_path] [-H channel_num] [-M mode_num] [-N serial_no]\n");
}

void usage(void)
{
	print_usage(stderr);
	prev_stderr=1;
}

void help(void)
{
	print_usage(stdout);
	fprintf(stdout,"Options:\n");
	fprintf(stdout,"	-a		Show information for all Mightex devices\n");
	fprintf(stdout,"                        (note, no settings will be read,\n");
	fprintf(stdout,"			and no commands will be sent to the controller)\n");
	fprintf(stdout,"	-c		Show Maximum and Set Current (milliAmp) \n");
	fprintf(stdout,"	-C \042Max Set\042	Set Maximum and Set Current (milliAmp) values\n");
	fprintf(stdout,"			(note: current settings over 999 will be limited to 999\n");
	fprintf(stdout,"	-d		Show device_path to be used\n");
	fprintf(stdout,"	-D device_path	Use the specified device path rather than auto-finding it\n");
	fprintf(stdout,"	-e		Show maximum channels for active controller\n");
	fprintf(stdout,"	-F		Reset the Mightex controller to factory defaults\n");
	fprintf(stdout,"			(note: requires -M to activate Factory settings and -S to save them)\n");
	fprintf(stdout,"	-h		Print this help message\n");
	fprintf(stdout,"	-H channel_num	Use the specified channel (default is channel 1)\n");
	fprintf(stdout,"	-i		Send DEVICEINFO command\n");
	fprintf(stdout,"	-m		Show active mode (0==Off, 1=Normal)\n");
	fprintf(stdout,"	-M mode_num	Set mode to mode_num\n");
	fprintf(stdout,"	-n		Show comma-separated list of serial number(s) of \n");
	fprintf(stdout,"                        attached Mightex device(s)\n");
	fprintf(stdout,"	-N serial_no	Use the device with the specified serial number (if it exists)\n");
	fprintf(stdout,"	-r		Show revision number of mightex_cmd\n");
	fprintf(stdout,"	-R		Reset the Mightex controller\n");
	fprintf(stdout,"	-S		Save the active settings to NVRAM (after power cycle,\n");
	fprintf(stdout,"			the controller will turn on with the active settings loaded)\n");
	fprintf(stdout,"	-v		Verbose (output written to stderr)\n");
	fprintf(stdout,"	-V		Even more Verbose (output written to stderr)\n");
	prev_stdout=1;
}

int main (int argc, char **argv)
{
	int c;
	int badargs=0;
	struct udev *udev;
	struct udev_enumerate *enumerate;
	struct udev_list_entry *devices, *dev_list_entry;
	struct udev_device *dev;

//   	struct udev_monitor *mon;
//	int fd;
	char use_device[MAX_STR];
	char command_string[MAX_STR];

	mystrSZcpy(use_device,"");

	/* read command line options and set up appropriate actions */
	while((c = getopt(argc, argv, "acdehimnrvVFRSC:D:H:M:N:")) != -1)
	{
		switch(c)
		{
			case 'v':
				verbose=1;
				break;
			case 'V':
				print_debug_output=1;
				verbose=1;
				break;
			case 'a':
				aflag=1;
				break;
			case 'd':
				dflag=1;
				break;
			case 'e':
				eflag=1;
				break;
			case 'D':
				if(optarg && *optarg)
				{
					CapDflag=1;
					mystrSZcpy(Device_Node_Path,optarg);
					mystrSZcpy(use_device,optarg);
				}
				else
				{
					fprintf(stderr,"Must spcecify a device path with -D\n");
					badargs=1;
				}
				break;
			case 'c':
				cflag=1;
				(void)my_snprintf(command_string, sizeof(command_string), "?CURRENT %d ", channel_num);
				add_to_command_queue(command_string);
				break;
			case 'C':
				if((2==sscanf(optarg,"%d  %d",&iMaxmilliA,&iSetmilliA) ||
				    2==sscanf(optarg,"%d, %d",&iMaxmilliA,&iSetmilliA)) &&
				   iMaxmilliA>=iSetmilliA)
				{
					CapCflag=1;
					mystrSZcpy(MaxSet,optarg);
					// It turns out that you can set the Max to 1000, but if you do
					// you're only allowed two digits for the current setting because
					// the whole command string can only be 16 chars long.
					// Setting iMaxmilliA to a Maximum of 999 avoids that issue
					if(iMaxmilliA>1000)
						iMaxmilliA=999;
					if(iSetmilliA>1000)
						iSetmilliA=999;
					(void)my_snprintf(command_string, sizeof(command_string), "NORMAL %d %d %d ", channel_num, iMaxmilliA, iSetmilliA);
					add_to_command_queue(command_string);
				}
				else
				{
					fprintf(stderr,"Must spcecify a Maximum and a Set value with -C\n");
					badargs=1;
				}
				break;
			case 'F':
				CapFflag=1;
				(void)my_snprintf(command_string, sizeof(command_string), "RESTOREDEF" );
				add_to_command_queue(command_string);
				break;
			case 'h':
				hflag=1;
				help();
				break;
			case 'H':
				if(1==sscanf(optarg,"%d",&channel_num))
				{
					CapHflag=1;
				}
				else
				{
					fprintf(stderr,"Must spcecify a cHannel value with -H\n");
					badargs=1;
				}
				break;
			case 'i':
				iflag=1;
				(void)my_snprintf(command_string, sizeof(command_string), "DEVICEINFO" );
				add_to_command_queue(command_string);
				break;
			case 'm':
				mflag=1;
				(void)my_snprintf(command_string, sizeof(command_string), "?MODE %d ", channel_num);
				add_to_command_queue(command_string);
				break;
			case 'M':
				if(1==sscanf(optarg,"%d",&mode_num) && (0==mode_num || 1==mode_num))
				{
					CapMflag=1;
					(void)my_snprintf(command_string, sizeof(command_string), "MODE %d %d ", channel_num, mode_num);
					add_to_command_queue(command_string);
				}
				else
				{
					fprintf(stderr,"Must spcecify a Mode value with -M\n");
					badargs=1;
				}
				break;
			case 'n':
				nflag=1;
				break;
			case 'N':
				if(optarg && *optarg)
				{
					CapNflag=1;
					mystrSZcpy(useSerialNo,optarg);
				}
				else
				{
					fprintf(stderr,"Must spcecify a serial number string with -N\n");
					badargs=1;
				}
				break;
			case 'r':
				rflag=1;
				if(1==prev_stdout)
					fprintf(stdout,"; \n");
				prev_stdout=1;
				fprintf(stdout,"mightex_cmd version %s\n",mightex_cmd_version);
				break;
			case 'R':
				CapRflag=1;
				(void)my_snprintf(command_string, sizeof(command_string), "RESET" );
				add_to_command_queue(command_string);
				break;
			case 'S':
				CapSflag=1;
				(void)my_snprintf(command_string, sizeof(command_string), "STORE" );
				add_to_command_queue(command_string);
				break;
			case '?':
				if('M'==optopt)
				{
					fprintf(stderr,"Must spcecify a Mode value with -M\n");
				}
				else if('H'==optopt)
				{
					fprintf(stderr,"Must spcecify a cHannel value with -H\n");
				}
				else if('C'==optopt)
				{
					fprintf(stderr,"Must spcecify a Maximum and a Set value with -C\n");
				}
				else if('D'==optopt)
				{
					fprintf(stderr,"Must spcecify a device path with -D\n");
				}
				else if('N'==optopt)
				{
					fprintf(stderr,"Must spcecify a serial number string with -N\n");
				}
				else if(isprint(optopt))
				{
					fprintf(stderr,"Unknown option -%c\n",optopt);
				}
				else
				{
					fprintf(stderr,"Unknown option character: 0x%02x\n",optopt);
				}
				// fall through
			default:
				badargs=1;
				break;
		}
	}
	if(badargs)
	{
		usage();
		return 1;
	}

	/* Create the udev object */
	udev = udev_new();
	if (!udev) {
		printf("Can't create udev\n");
		exit(1);
	}

	/* Create a list of the devices in the 'hidraw' subsystem. */
	enumerate = udev_enumerate_new(udev);
	udev_enumerate_add_match_subsystem(enumerate, "hidraw");
	udev_enumerate_scan_devices(enumerate);
	devices = udev_enumerate_get_list_entry(enumerate);
	/* For each item enumerated, print out its information.
	   udev_list_entry_foreach is a macro which expands to
	   a loop. The loop will be executed for each member in
	   devices, setting dev_list_entry to a list entry
	   which contains the device's path in /sys. */
	udev_list_entry_foreach(dev_list_entry, devices) {
		const char *path;

		/* Get the filename of the /sys entry for the device
		   and create a udev_device object (dev) representing it */
		path = udev_list_entry_get_name(dev_list_entry);
		dev = udev_device_new_from_syspath(udev, path);

		/* usb_device_get_devnode() returns the path to the device node
		   itself in /dev. */
		mystrSZcpy(Device_Node_Path,udev_device_get_devnode(dev));
		if(verbose)
		{
			if(1==prev_stdout)
				fprintf(stdout,"; \n");
			prev_stdout=1;
			fprintf(stdout,"; Device: %s\n", Device_Node_Path);
		}

		/* The device pointed to by dev contains information about
		   the hidraw device. In order to get information about the
		   USB device, get the parent device with the
		   subsystem/devtype pair of "usb"/"usb_device". This will
		   be several levels up the tree, but the function will find
		   it.*/
		dev = udev_device_get_parent_with_subsystem_devtype( dev, "usb", "usb_device");
		if (!dev) {
			if(1==prev_stderr)
				fprintf(stderr,"; \n");
			fprintf(stderr,"; Unable to find parent usb device for %s", Device_Node_Path);
			break;
		}

		/* From here, we can call get_sysattr_value() for each file
		   in the device's /sys entry. The strings passed into these
		   functions (idProduct, idVendor, serial, etc.) correspond
		   directly to the files in the /sys directory which
		   represents the USB device. Note that USB strings are
		   Unicode, UCS2 encoded, but the strings returned from
		   udev_device_get_sysattr_value() are UTF-8 encoded. */
		mystrSZcpy(idVendor,udev_device_get_sysattr_value(dev,"idVendor"));
		mystrSZcpy(idProduct,udev_device_get_sysattr_value(dev, "idProduct"));
		mystrSZcpy(Manufacturer,udev_device_get_sysattr_value(dev,"manufacturer"));
		mystrSZcpy(Product,udev_device_get_sysattr_value(dev,"product"));
		mystrSZcpy(SerialNo,udev_device_get_sysattr_value(dev, "serial"));
		udev_device_unref(dev);

		if(verbose)
		{
		  if(1==prev_stdout)
			fprintf(stdout,"; \n");
		  prev_stdout=1;
		  fprintf(stdout,"; VendorID: %s\n",idVendor);
		  fprintf(stdout,"; ProductID: %s\n",idProduct);
		  fprintf(stdout,"; Manufacturer: %s\n",Manufacturer);
		  fprintf(stdout,"; Product: %s\n",Product);
		  fprintf(stdout,"; SerialNo: %s\n",SerialNo);
		}

		if(strstr(Product,"SLC-") && strstr(Manufacturer,"Mightex"))	// Mightex?
		{
			char *p;

			mystrSZcpy(m_SerialNo[nMightexDevices],SerialNo);
			mystrSZcpy(m_Product[nMightexDevices],Product);
			mystrSZcpy(m_idProduct[nMightexDevices],idProduct);
			mystrSZcpy(m_idVendor[nMightexDevices],idVendor);
			mystrSZcpy(m_Device_Node_Path[nMightexDevices],Device_Node_Path);
			p=strstr(Product,"SLC-");
			if(p && strlen(p)>6)
			{
				int max_channels=0;
				char a;
				p+=4;
				while((a=*p++) && a!='-')
					if(a>='0' && a<='9')
						max_channels=(a-'0')+(max_channels*10);
				m_Max_Channels[nMightexDevices]=max_channels;
			}

			if(aflag)
			{
			    if(prev_stdout)
				fprintf(stdout,"\n");
			    prev_stdout=1;
			    fprintf(stdout,"; Device: %s\n", Device_Node_Path);
			    fprintf(stdout,"; VendorID: %s\n",idVendor);
			    fprintf(stdout,"; ProductID: %s\n",idProduct);
			    fprintf(stdout,"; Manufacturer: %s\n",Manufacturer);
			    fprintf(stdout,"; Product: %s\n",Product);
			    fprintf(stdout,"; Max_Channels: %d\n",m_Max_Channels[nMightexDevices]);
			    fprintf(stdout,"; SerialNo: %s\n",SerialNo);
			}

			nMightexDevices++;

			if(0==CapDflag)
			{	// no Device specified
				if(CapNflag)
				{	// SerialNo was specified
					if(0==strcmp(SerialNo,useSerialNo) && '\0'!=*Device_Node_Path)
					{	// a match!
						mystrSZcpy(use_device,Device_Node_Path);
						Max_Channels=m_Max_Channels[nMightexDevices-1];
					}
				}
				else
				{	// No SerialNo and no Device was specified, use this device
					if('\0'!=*Device_Node_Path)
					{
						mystrSZcpy(use_device,Device_Node_Path);
						Max_Channels=m_Max_Channels[nMightexDevices-1];
					}
				}
			}
			else
			{
				if(CapNflag)
				{	// A Device and a SerialNo were specified
					if(0!=strcmp(SerialNo,useSerialNo) && 0==strcmp(use_device,Device_Node_Path))
					{	// but, they don't match
					    if(prev_stderr)
						fprintf(stderr,"\n");
					    prev_stderr=1;
					    fprintf(stderr,"; Specified Device does not match the specified SerialNo!\n");
					    exit(2);
					}
				}
				else
				{
					if(0==strcmp(use_device,Device_Node_Path))
					{
						Max_Channels=m_Max_Channels[nMightexDevices-1];
					}

				}
			}
		}
	}
	/* Free the enumerator object */
	udev_enumerate_unref(enumerate);
	udev_unref(udev);

	if(verbose)
	{
		if(prev_stderr)
			fprintf(stderr,"; \n");
		// "acdehimnrvFRSC:D:H:M:N:"
		fprintf(stderr,"; aflag=%d cflag=%d dflag=%d eflag=%d hflag=%d iflag=%d mflag=%d nflag=%d rflag=%d vflag=%d Cflag=%d Dflag=%d Fflag=%d Hflag=%d Mflag=%d Nflag=%d Rflag=%d Sflag=%d\n",
			aflag,cflag,dflag,eflag,hflag,iflag,mflag,nflag,rflag,verbose, CapCflag, CapDflag, CapFflag, CapHflag, CapMflag, CapNflag, CapRflag, CapSflag);
	}

	if('\0'==*use_device)
	{
		if((hflag || rflag) && 0==aflag && 0==dflag && 0==eflag && 0==nflag)
		{
			// no need for message about no devices
		}
		else if(aflag)
		{
			if(prev_stdout)
				fprintf(stdout,"; \n");
			fprintf(stdout,"; No matching Mightex devices found\n");
		}
		else
		{
			if(prev_stderr)
				fprintf(stderr,"; \n");
			fprintf(stderr,"; No matching Mightex devices found\n");
			exit(3);
		}
	}

	if(dflag)
	{
		if(prev_stdout)
			fprintf(stdout,"; \n");
		fprintf(stdout,"; Device=%s\n",use_device);
	}

	if(eflag)
	{
		if(prev_stdout)
			fprintf(stdout,"; \n");
		fprintf(stdout,"; Max_Channels=%d\n",Max_Channels);
	}

	if(nflag)
	{
		int i;
		if(prev_stdout && nMightexDevices)
			fprintf(stdout,"; \n");
		for(i=0;i<nMightexDevices;i++)
		{
			fprintf(stdout,"%s%s",(0==i)?"":",",m_SerialNo[i]);
		}
		if(nMightexDevices)
			fprintf(stdout,"\n");
	}

	if(0==aflag && 0!=Command_Count && '\0'!=*use_device)
		return hidmain(use_device);

	return 0;
}

/* Add a command to the command queue */
int add_to_command_queue(char *command)
{
	int retval=0;	// no problems, return 1 for failure
	if(Command_Count<MAX_CMD_QUEUE)
	{
		mystrSZcpy(Command_Queue[Command_Count],command);
		Command_Count++;	// NOTE: beware side effects if you put the ++ in the line above
	}
	else
	{
		retval=1;
	}
	return retval;
}

void print_hexascii(FILE *fp,char *buf, int bufsz)
{
	int i;
	char asc[10];
	memset(asc,0,10);

	for (i = 0; i < bufsz; i++)
	{
		fprintf(fp,"%02hhx ", buf[i]);
		if(isprint(buf[i]))
			asc[i%8]=buf[i];
		else
			asc[i%8]='.';
		asc[1+(i%8)]='\0';
		if(7==(i%8))
		{
			fprintf(fp," ; %s\n",asc);
			asc[0]='\0';
		}
	}
	// Finish out the last partial line
	if(0 != (i%8))
	{
		for( ; 0 != (i%8) ; i++)
			fprintf(fp,"   ");
		fprintf(fp," ; %s\n",asc);
	}
	fprintf(fp,"\n");
	return;
}

void set_buf_cmd(char *buf,int irpt_num,char *command)
{
	int i=0;

	buf[i++] = irpt_num;
	buf[i++] = strlen(command)+2;
	strcpy(&buf[i],command);
	strcat(&buf[i],"\n\r");

	if(verbose)
		fprintf(stderr,"; sent: %s\n", command);
	return;
}

int my_getFeature(int fd, int ireport, char *buf, int bufsz, int feature_size)
{
	int res,i;

	if(feature_size>bufsz)
		feature_size=bufsz;

	for(i=0;i<bufsz;i++) buf[i]='\0';
	buf[0] = ireport; /* Report Number */
	res = ioctl(fd, HIDIOCGFEATURE(feature_size), buf);
	if (res < 0)
	{
		perror("HIDIOCGFEATURE");
	}
	else
	{
		if(print_debug_output)
		{
		  fprintf(stderr,"ioctl HIDIOCGFEATURE returned: %d\n", res);
		  fprintf(stderr,"Report data (not containing the report number):\n");
		  print_hexascii(stderr,(char *)buf,res);
		}
	}
	return res;
}

#define MAX_MIGHTEX_REPLY_RETRIES	1

// Do NOT make MAX_RESPONSE_TRIES less than 6, or the DEVICEINFO command will not complete
#define MAX_RESPONSE_TRIES 10
#define RESPONSE_SIZE 256
char *get_mightex_response(int fd, int ireport,int *response_size)
{
	char buf[RESPONSE_SIZE];
	static char answer[RESPONSE_SIZE];
	int res;
	int need_more=1;
	int tries=0;
	int a_ndx=0;
	int fsize=18;

	answer[a_ndx]='\0';
	*response_size=RESPONSE_SIZE;

	while(need_more && tries<MAX_RESPONSE_TRIES)
	{
		tries++;

		/* Get Feature */
		res = my_getFeature(fd, ireport, buf, sizeof(buf), fsize);
		if (res >= 0)
		{
			if(res && buf[0]==0x01 && buf[1]==0x00)
				usleep(10000L);	// sleep 0.01 sec waiting for more
			if(res && buf[0]==0x01 && buf[1]<=(fsize-2))
			{
				int i;
				for(i=0;i<buf[1];i++)
				{
					answer[a_ndx++]=buf[2+i];
				}
				answer[a_ndx]='\0';
				if(a_ndx>1)
				{	// handle <cr><lf> and <lf><cr>
					if(answer[a_ndx-1]==0x0d && answer[a_ndx-2]==0x0a)
						need_more=0;
					if(need_more && answer[a_ndx-1]==0x0a && answer[a_ndx-2]==0x0d)
						need_more=0;
				}
			}
		}
	}
	if(verbose)
		printf("; answer=%s\n",answer);
	return (char *)answer;
}

int hidmain(char *use_device)
{
	int fd;
	int j;
	int res;
	char ibuf[256];
	char buf[256];
	int ireport=1;
	int fsize=18;
#if 0
	int desc_size = 0;
	struct hidraw_report_descriptor rpt_desc;
	struct hidraw_devinfo info;
#endif // 0
	char *device = "/dev/hidraw0";
#if 0
	char *queries[]={
		"?CURRENT 1 ",
		"?CURRENT 2 ",
		"?MODE 1 ",
		"?MODE 2 ",
		"NORMAL 1 200 2 ",
		"?CURRENT 1 ",
		"CURRENT 1 3 ",
		"?CURRENT 1 ",
		"MODE 1 1 ",
		"?CURRENT 1 ",
		"MODE 1 0 ",
		"NORMAL 1 200 2 ",
		"MODE 1 1 ",
		"?MODE 1 ",
		"?CURRENT 1 ",
		"STORE",
		"DEVICEINFO",
		""};
#endif // 0

	if(use_device)
	  device = use_device;

	/* Open the Device with non-blocking reads. In real life,
	   don't use a hard coded path; use libudev instead. */
	fd = open(device, O_RDWR|O_NONBLOCK);

	if (fd < 0) {
		perror("Unable to open device");
		return 1;
	}

#if 0
	memset(&rpt_desc, 0x0, sizeof(rpt_desc));
	memset(&info, 0x0, sizeof(info));
	memset(buf, 0x0, sizeof(buf));

	/* Get Report Descriptor Size */
	res = ioctl(fd, HIDIOCGRDESCSIZE, &desc_size);
	if (res < 0)
		perror("HIDIOCGRDESCSIZE");
	else
		printf("Report Descriptor Size: %d\n", desc_size);

	/* Get Report Descriptor */
	rpt_desc.size = desc_size;
	res = ioctl(fd, HIDIOCGRDESC, &rpt_desc);
	if (res < 0)
	{
		perror("HIDIOCGRDESC");
	}
	else
	{
		fprintf(stderr,"Report Descriptor:\n");
		print_hexascii(stderr,(char *)&rpt_desc.value[0],rpt_desc.size);
	}

	/* Get Raw Name */
	res = ioctl(fd, HIDIOCGRAWNAME(256), buf);
	if (res < 0)
		perror("HIDIOCGRAWNAME");
	else
		fprintf(stderr,"Raw Name: %s\n", buf);

	/* Get Physical Location */
	res = ioctl(fd, HIDIOCGRAWPHYS(256), buf);
	if (res < 0)
		perror("HIDIOCGRAWPHYS");
	else
		fprintf(stderr,"Raw Phys: %s\n", buf);

	/* Get Raw Info */
	res = ioctl(fd, HIDIOCGRAWINFO, &info);
	if (res < 0) {
		perror("HIDIOCGRAWINFO");
	} else {
		fprintf(stderr,"Raw Info:\n");
		fprintf(stderr,"\tbustype: %d (%s)\n",
			info.bustype, bus_str(info.bustype));
		fprintf(stderr,"\tvendor: 0x%04hx\n", info.vendor);
		fprintf(stderr,"\tproduct: 0x%04hx\n", info.product);
	}
#endif // 0

	/* This first loop gets us in sync with the device */
	for(j=1;j<20;j++)
	{
		/* Get Feature */
		res=my_getFeature(fd,ireport,buf,sizeof(buf),fsize);
		if(buf[0]==ireport && buf[1]==0x00 )
			break;	// now the input queue is clear
	}

	/* Make sure we can ask for the mode on channel 1 and get a good answer */
	for(j=1;j<20;j++)
	{
		char *mode_cmd="?MODE 1 ";

		memset(ibuf,'\0',sizeof(ibuf));
		set_buf_cmd(ibuf,ireport,mode_cmd);
		if(print_debug_output)
			fprintf(stderr,"ioctl HIDIOCSFEATURE #: %d, %s\n", ireport,mode_cmd);

		/* Set Feature */
		res = ioctl(fd, HIDIOCSFEATURE(fsize), ibuf);
		if (res < 0)
			perror("HIDIOCSFEATURE");
		else
			if(print_debug_output)
			  fprintf(stderr,"ioctl HIDIOCSFEATURE returned: %d\n", res);

		usleep(10000L);	// sleep 0.01 sec before checking for response
		/* Get Feature */
		res=my_getFeature(fd,ireport,buf,sizeof(buf),fsize);
		if(buf[0]==0x01 && buf[1]==0x05 && buf[2]=='#' && buf[3]>='0' && buf[3]<='3')
			break;	// got the expected answer
	}

	/* Clear out all input again */
	for(j=1;j<20;j++)
	{
		/* Get Feature */
		res=my_getFeature(fd,ireport,buf,sizeof(buf),fsize);
		if(buf[0]==ireport && buf[1]==0x00 )
			break;	// now the input queue is clear
	}

	for(j=0;j<MAX_CMD_QUEUE && *Command_Queue[j]!='\0';j++)
	{
		char *response;
		int response_size=0;
		int resp_retries=0;

//		sleep(1);
		memset(ibuf,0,sizeof(ibuf));
		set_buf_cmd(ibuf,ireport,Command_Queue[j]);
		if(verbose)
			fprintf(stderr,"; sent: %s\n", Command_Queue[j]);

		res = ioctl(fd, HIDIOCSFEATURE(fsize), ibuf);
		if (res < 0)
			perror("HIDIOCSFEATURE");
		else
		{
			if(print_debug_output)
				fprintf(stderr,"ioctl HIDIOCSFEATURE returned: %d\n", res);
		}

		usleep(10000L);	// sleep 0.01 sec before checking for response
		resp_retries=0;
		response=get_mightex_response(fd,ireport,&response_size);
		while( (0==strlen(response)) && (MAX_MIGHTEX_REPLY_RETRIES>(++resp_retries)) )
			response=get_mightex_response(fd,ireport,&response_size);
		if(MAX_MIGHTEX_REPLY_RETRIES==resp_retries && 0==strlen(response) && '?'!=*Command_Queue[j])
		{
			// no answer from command, so send a query
			memset(ibuf,'\0',sizeof(ibuf));
			set_buf_cmd(ibuf,ireport,"?MODE 1 ");
			if(verbose)
				fprintf(stderr,"sent: %s\n", "?MODE 1 ");

			res = ioctl(fd, HIDIOCSFEATURE(fsize), ibuf);
			if (res < 0)
				perror("HIDIOCSFEATURE");
			else
			{
				if(print_debug_output)
					fprintf(stderr,"ioctl HIDIOCSFEATURE returned: %d\n", res);
			}

			usleep(10000L);	// sleep 0.01 sec before checking for response
			resp_retries=0;
			response=get_mightex_response(fd,ireport,&response_size);
			while( (0==strlen(response)) && (MAX_MIGHTEX_REPLY_RETRIES>(++resp_retries)) )
				response=get_mightex_response(fd,ireport,&response_size);
		}
		if(strstr(Command_Queue[j],"?MODE "))
		{	// only the number should be reported
			int imode;
			if(1==sscanf(response,"#%d",&imode))
				my_snprintf(response, response_size, "%d",imode);
		}
		else if(strstr(Command_Queue[j],"?CURRENT "))
		{	// only the last two numbers should be reported
			// The SLC-MA series reports 6 junk numbers, the SLC-SA series reports 8.
			#define MAX_JUNK_COUNT 12
			#if(4*(MAX_JUNK_COUNT+2)>256)
				#define FMT_SZ	(10+(MAX_JUNK_COUNT*4))
			#else
				#define FMT_SZ	256
			#endif
			int ijunk[MAX_JUNK_COUNT],imax,icurrent,icount,i;
			char format[FMT_SZ];

			mystrSZcpy(format,"#");
			for(i=0;i<MAX_JUNK_COUNT;i++)
			  mystrSZcat(format,"%d ");

			#if(12!=MAX_JUNK_COUNT)
				"The Following Line must be fixed"
			#endif
			icount=sscanf(response,format,&ijunk[0],&ijunk[1],&ijunk[2],&ijunk[3],&ijunk[4],&ijunk[5],&ijunk[6],&ijunk[7],&ijunk[8],&ijunk[9],&ijunk[10],&ijunk[11]);
			if(icount>2)
			{
				mystrSZcpy(format,"#");
				for(i=0;i<(icount-2);i++)
				  mystrSZcat(format,"%*d ");	// skip icount-2 integers
				mystrSZcat(format,"%d %d");	// store only the last two
				if(2==sscanf(response,format,&imax,&icurrent))
					my_snprintf(response, response_size, "%d, %d",imax,icurrent);
			}
		}
		else
		{	// remove trailing "<cr><lf>" or "<lf><cr>"
			int len=strlen(response);
			if(len && ('\r'==response[len-1] || '\n'==response[len-1]))
				response[len-1]='\0';
			len=strlen(response);
			if(len && ('\r'==response[len-1] || '\n'==response[len-1]))
				response[len-1]='\0';
		}
		fprintf(stdout,"%s\n",response);
	}

	close(fd);
	return 0;
}

const char *
bus_str(int bus)
{
	switch (bus) {
	case BUS_USB:
		return "USB";
		break;
	case BUS_HIL:
		return "HIL";
		break;
	case BUS_BLUETOOTH:
		return "Bluetooth";
		break;
	case BUS_VIRTUAL:
		return "Virtual";
		break;
	default:
		return "Other";
		break;
	}
}

void mystrncpy(char *p1,const char *p2,size_t max_p1)
{
	if(p1==(char *)0 || p2==(char *)0 || max_p1<1)
	{
//		assert(0);
		return;
	}
	strncpy(p1,p2,max_p1-1);
	p1[max_p1-1]=0x00;
}

void mystrncat(char *p1,const char *p2,size_t max_p1)
{
	int curlen;
	int avail;

	if(p1==(char *)0 || p2==(char *)0 || max_p1<1)
	{
//		assert(0);
		return;
	}

	curlen=strlen(p1);
	if(curlen<max_p1)
	{
		avail=max_p1-curlen-1;
		if(avail>0)
			strncat(p1,p2,avail);
	}
}

int my_snprintf(char *buffer, size_t count, const char *fmt, ...)
{
    va_list ap;
    int ret;

    va_start(ap, fmt);

    if((char *)0==buffer || 1>count)
        ret=0;
    else
    {
        ret = vsnprintf(buffer, count-1, fmt, ap);
        if (ret < 0)
            buffer[count-1] = '\0';
    }
    va_end(ap);
    return ret;
}

