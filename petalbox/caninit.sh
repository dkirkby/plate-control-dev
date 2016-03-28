#!/bin/bash
# simple script to initialize CAN
for i in `seq 0 2`;
do
	echo $i
	check="$(ip link show can$i | grep brd)"
	echo "check:"$check
	if ! [[ -z "${check// }" ]];
	then
		echo "detected SYSTEC on can$i"
		ip link set can$i type can bitrate 500000
  		ip link set can$i up 
	fi
done
