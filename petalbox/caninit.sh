#!/bin/bash
# simple script to initialize CAN
echo "checking for SYSTEC CAN on can0, can1, can2 ..."
for i in `seq 0 2`;
do
#	echo $i
	check="$(ip link show can$i | grep brd)"
	if ! [[ -z "${check// }" ]];
	then
		echo "detected SYSTEC on can$i ..."
		ip link set can$i type can bitrate 500000
  		ip link set can$i up
	fi
done
echo "updating petalcontroller.ini file ..."
python3 caninit.py can$i
echo "...done"
