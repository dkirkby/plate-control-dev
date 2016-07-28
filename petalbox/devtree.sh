#!/bin/bash
sudo sh -c "echo 'cape-universaln' > /sys/devices/platform/bone_capemgr/slots"
sudo sh -c "echo 'BB-W1-P8.07' > /sys/devices/platform/bone_capemgr/slots"
sudo sh -c "echo 'am33xx_pwm' > /sys/devices/platform/bone_capemgr/slots"

sudo chmod -R +rwx /sys/devices/platform/ocp/
sudo chmod -R +rwx /sys/class/gpio

