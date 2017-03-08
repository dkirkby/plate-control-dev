  (c) SYSTEC electronic GmbH, D-08468 Heinsdorfergrund, Am Windrad 2
        www.systec-electronic.com

                                                       2015-03-10

        SocketCAN Driver for USB-CANmodul series
        =========================================

Requirements
-------------

* USB-CANmodul series generation 3 and 4

* Linux Kernel version >= 2.6.32

* Following kernel options have to be set:

CONFIG_CAN=m
CONFIG_CAN_RAW=m
CONFIG_CAN_BCM=m
CONFIG_CAN_DEV=m
CONFIG_CAN_CALC_BITTIMING=y


***************************************
This is how you check for the above:

cat /boot/config-2.6.32-220.el6.x86_64 | grep CONFIG_CAN
 (replace config-2.6.32.xxx.xxx.... with the actual kernel version number
****************************************



* CAN utilities from the SocketCAN repository for first tests

$ git clone git://github.com/linux-can/can-utils/ # works on 104
$ cd can-utils
$ make # works on 104

***********************************************************
IG, MS June 16, 2015
NOTE: the above did not work for us. This did:
git clone git://github.com/linux-can/can-utils
cd can-utils
./autogen.sh
./configure
make
make install

NOTE: yum install libtool if ./autogen.sh has problems
************************************************************

From the svn, get systec drivers (systec_can-V0.9.0.tar.bz2) and unzip.


Beaglebone:
Installing kernel header files - see: http://dumb-looks-free.blogspot.com/2014/06/beaglebone-black-bbb-kernal-headers.html


Changes
--------
v0.9:
* Added support of bootloader update
  * required for newer firmware versions
  * bootloader files from /lib/firmware/ are used
  * only update is done, no downgrade
* Loosen the driver <-> firmware coupling
  * firmware on modules is updated/downgraded to the firmware files located
    in /lib/firmware/
  * firmware file names have changed: version number removed from name
* Added support for kernels up to 3.18
* Fix a kernel warning upon interface startup

Supported features
-------------------

* CAN frame reception and transmission:
  + standard frame format (11 bit identifier)
  + extended frame format (29 bit identifier)
  + remote transmit request frames (RTR)

* Supported CAN controller states:
  + CAN_STATE_ERROR_ACTIVE  (CAN bus runs error-free)
  + CAN_STATE_ERROR_WARNING (error counters reached warning limit)
  + CAN_STATE_ERROR_PASSIVE (node sends passive error frames)
  + CAN_STATE_BUS_OFF       (node does not send any frames,
                             i.e. it is virtually disconnected from bus)

* Supported SocketCAN error frame flags
  (not to mix up with CAN error frames according to CAN specification)
    struct can_frame frame;
    ....
    if (frame.can_id & CAN_ERR_FLAG) {
      if (frame.can_id & CAN_ERR_BUSOFF) {
        /* BUS OFF */ }
      if (frame.can_id & CAN_ERR_RESTARTED) {
        /* recover from BUS OFF */ }
      if (frame.can_id & CAN_ERR_CRTL) {
        if (frame.data[1] & (CAN_ERR_CRTL_RX_WARNING |
            CAN_ERR_CRTL_TX_WARNING)) {
          /* warning limit reached */ }
        if (frame.data[1] & (CAN_ERR_CRTL_RX_PASSIVE |
            CAN_ERR_CRTL_TX_PASSIVE)) {
          /* error passive state entered */ }
        if (frame.can_id & CAN_ERR_PROT) {
          if (frame.data[2] & CAN_ERR_PROT_ACTIVE) {
            /* error active state entered */ }
        }
      }
    }

* Supported CAN controller modes
  + CAN_CTRLMODE_3_SAMPLES  (Triple sampling mode)
  + CAN_CTRLMODE_LISTENONLY (Listen-only mode)

* Tx echo is implemented in driver and there is optional support for
  hw based Tx echo.


Limitations
------------

* Firmware version >=4.06 must be installed on USB-CANmodul.
  In case of an older firmware version, please connect the USB-CANmodul to a
  Windows PC with a recent driver version. The Windows driver will update the
  firmware. Afterwards also this driver is capable of updating the firmware.
* There is currently no way to read out or set the digital I/Os of the
  user port or the CAN port (signals EN, /STB, /ERR, /TRM).
* No support for the obsolete modules GW-002 and GW-001.
  This is not planned at all.
* Planned CAN controller modes
  + CAN_CTRLMODE_LOOPBACK   (Loopback mode)


Build the driver
-----------------

Run make within the source directory

$ cd systec_can
$ make


Load the driver from the local source directory
------------------------------------------------

1. Load basic CAN drivers

$ sudo modprobe can_raw
$ sudo modprobe can_dev

2. Install firmware

$ sudo make firmware_install

3. Load USB-CANmodul driver

$ sudo insmod systec_can.ko

- OR -

Install the driver and firmware system-wide
--------------------------------------------

$ sudo make modules_install
$ sudo make firmware_install

The kernel module should now be loaded automatically by udev
when the device is connected.


Module parameters
------------------

The driver has the following module parameters:

* debug (type int)

  This is a bitmask enabling/disabling different parts of debug messages at
  module load time or during runtime.
  It can be set during a manual insmod: e.g. insmod systec_can.ko debug=0x1
  Or use /etc/modprobe.d/ (actual path may depend on used version and/or
  distribution) for usage with modprobe and/or automatically load with udev.
  All messages are still send with debug level, so a system logger may need to be
  configured accordingly.

  Available Bits:
  Bit 1: Generic driver debug message for module load/unload and interface up/down
  Bit 2: USB command message dump
  Bit 3: USB status message dump
  Bit 4: USB data message dump
  Bit 5: Tx related events (start and finish of USB transfer)
  Bit 6: Bittiming related output (e.g. settings like bitrate and sample point)
  Bit 7: USB command message events
  Bit 8: Error handling events
  Bit 9: Disconnect related events

* hw_txecho (type boolean)

  If set the CAN frame will be echoed when actually sent by the hardware. Any change
  to this flags will become effective when the interface is (re-)started.

Known Issues
-------------

* When updating the bootloader from version 1.01 r2 it might happen that the
  device will not reconnect properly. LEDs are not indicating this.
  Workaround: Disconnect the device physically and reconnect it afterwards.

Run basic tests
----------------

1. Connect the USB-CANmodul to the PC

Note: Some of the following commands require the capability CAP_NET_ADMIN.
      So those commands should be executed as root (e.g. via sudo).

2. Set bitrate to 125kBit/s

$ ip link set can0 type can bitrate 125000
- OR if CONFIG_CAN_CALC_BITTIMING is undefined -
$ ip link set can0 type can tq 500 prop-seg 6 phase-seg1 7 phase-seg2 2

3. Start up the CAN interface

$ ip link set can0 up

4. Dump the traffic on the CAN bus

$ cd can-utils
$ ./candump can0

to display error frames (option -e is supported in newer candump versions only):

$ ./candump -e can0,0:0,#FFFFFFFF

5. Transmit one CAN frame

$ cd can-utils
$ ./cangen -n 1 -I 640 -L 8 -D 4000100000000000 can0

6. Print out some statistics

$ ip -details -statistics link show can0

7. Restart CAN channel manually in case of bus-off (i.e. short circuit)

$ ip link set can0 type can restart

Automatically restart the CAN channel 1000 ms after bus-off occurs

$ ip link set can0 type can restart-ms 1000

8. Increase the transmit queue length from default value 10 to 1000.
   10 is the size of one CAN message.

$ ip link set can0 txqueuelen 1000


Hardware address
-----------------

The hardware address (like the MAC address of Ethernet controllers)
of each CAN channel as shown with
`ip link show can0` or `ifconfig can0` is formed the following way:

S0:S1:S2:S3:DN:CN

Sx - Serial Number in Hex with S0 contains the most significant byte
DN - Device Number
CN - Channel Number (00 - CAN1, 01 - CAN2)

The unique hardware address can be used by a special udev rule to
assign stable interface names and numbers.

sysfs attributes
----------------

devicenr
--------
The Device Number can be changed via the sysfs attribute 'devicenr' under
/sys/class/net/*/device/devicenr (where * corresponds to the interface name like
can0) or /sys/bus/usb/devices/*/devicenr (where * corresponds to the USB device
path like '3-1:1.0'). Please note the hardware address will change after device
reset.

dual_channel
------------
This USB interface attribute shows 0 for a single-channel device and 1 for a dual-channel device.

reset
-----
Writes to this USB interface reset the device.

channel
-------
This CAN interface attribute shows the channel number on the device.

tx_timeout_ms
-------------
This CAN interface attribute on a dual-channel device configures a timeout when
a message shall be dropped, if it cannot be sent due to
e.g. low CAN-ID priority, not connected bus, ...
In this case the other channel is blocked for firmware restrictions.
Using this timeout the other, correctly connected, channel can still be used.

status_timeout
--------------
This USB device attribute can read/write the status timeout in ms. When a
CAN interface is active the status request URB must be send within this
limit after the last one or the device will disconnect and reconnect itself.
A timeout of 0 means the check is disabled.
Any change will only take effect after power-on the USB-CAN-Module!

udev rules examples
-------------------
Example for udev rule (file /etc/udev/rules.d/20-systec-can.rules):

# USB device 0x0878:0x1101 (systec_can)
# device number 01, first CAN channel -> can10
SUBSYSTEM=="net", ACTION=="add", DRIVERS=="systec_can", \
ATTR{address}=="??:??:??:??:01:00", KERNEL=="can*", NAME="can10"

# USB device 0x0878:0x1101 (systec_can)
# device number 01, second CAN channel -> can11
SUBSYSTEM=="net", ACTION=="add", DRIVERS=="systec_can", \
ATTR{address}=="??:??:??:??:01:01", KERNEL=="can*", NAME="can11"

# USB device 0x0878:0x1101 (systec_can)
# device connected at USB port 3-1:1.0, first CAN channel -> can20
SUBSYSTEM=="net", ACTION=="add", DRIVERS=="systec_can", KERNELS=="3-1:1.0", \
ATTR{address}=="??:??:??:??:??:00", KERNEL=="can*", NAME="can20"

# USB device 0x0878:0x1101 (systec_can)
# device connected at USB port 3-1:1.0, second CAN channel -> can21
SUBSYSTEM=="net", ACTION=="add", DRIVERS=="systec_can", KERNELS=="3-1:1.0", \
ATTR{address}=="??:??:??:??:??:01", KERNEL=="can*", NAME="can21"

# USB device 0x0878:0x1101 (systec_can)
# only set the timeout on dual channel devices
ACTION=="add", SUBSYSTEM=="net", DRIVERS=="systec_can", \
ATTRS{dual_channel}=="1", ATTR{tx_timeout_ms}="1000"

Further information
--------------------

[1] CAN utilities
    http://github.com/linux-can/can-utils/

[2] Linux Kernel Source Code Documentation/networking/can.txt
    http://git.kernel.org/?p=linux/kernel/git/torvalds/linux.git;a=blob;f=Documentation/networking/can.txt;hb=HEAD

[3] Talk about SocketCAN - CAN Driver Interface under Linux
    (German, but slides in English)
    http://chemnitzer.linux-tage.de/2012/vortraege/1044

[4] libsocketcan V0.0.9
    Helper library for CAN interface configuration (e.g. bitrate)
    over netlink API.
    http://www.pengutronix.de/software/libsocketcan/download/

