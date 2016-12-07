#!/bin/bash
sudo sh -c "echo 'cape-universaln' > /sys/devices/platform/bone_capemgr/slots"
sudo sh -c "echo 'BB-W1-P8.07' > /sys/devices/platform/bone_capemgr/slots"
sudo sh -c "echo 'am33xx_pwm' > /sys/devices/platform/bone_capemgr/slots"

sudo chmod -R +rwx /sys/devices/platform/ocp/
sudo chmod -R +rwx /sys/class/gpio

sudo config-pin "P8_12" 1
sudo config-pin "P8_14" 1
sudo config-pin "P8_13" out
sudo config-pin "P8_13" 1
sudo config-pin "P8_19" out
sudo config-pin "P8_19" 1

