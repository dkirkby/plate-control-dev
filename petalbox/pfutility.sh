#!/bin/bash
# simple script to run pf_utility
cd $PETALBOX_HOME
for i in `seq 0 2`;
do
	sudo ip link set can$i down
	check="$(ip link show can$i | grep brd)"

	if ! [[ -z "${check// }" ]];
	then
#		echo "detected SYSTEC on can$i ..."
		break
	fi
done
python3 pf_utility.py can$i

