#!/bin/bash
# simple script to initialize CAN
echo "checking for SYSTEC CAN on can0, can1, can2 ..."
for i in `seq 0 2`;
do
#	echo $i
	sudo ip link set can$i down
	check="$(ip link show can$i | grep brd)"

	if ! [[ -z "${check// }" ]];
	then
		echo "detected SYSTEC on can$i ..."
		sudo ip link set can$i type can bitrate 500000
  		sudo ip link set can$i up
		break
	fi
done
echo "creating a local copy of petalcontroller.conf ..."
cd $PETALBOX_HOME
cp petalcontroller.conf.default petalcontroller.conf
echo "updating petalcontroller.ini file ..."
python3 caninit.py can$i
echo "...done"
