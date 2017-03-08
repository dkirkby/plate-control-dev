#!/bin/bash

cd $PETALBOX_HOME


#sudo ip link set can0 type can bitrate 500000
#sudo ip link set can0 up

echo "checking for SYSTEC CAN on can0, can1, can2 ..."
for i in `seq 0 2`;
do
#       echo $i
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

kill $(ps aux | grep '/usr/bin/python3 /home/msdos/dos_home/dos_products/petalbox/petalcontroller.py --role PC'$1' --service PetalControl' | awk '{print $2}')

/usr/bin/python3 $PETALBOX_HOME/petalcontroller.py --role PC$1 --service PetalControl &

/usr/bin/python3 $PETALBOX_HOME/poscontrol.py $1
