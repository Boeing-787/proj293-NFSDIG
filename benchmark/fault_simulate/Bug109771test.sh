#! /bin/sh

WAIT=4
OPTIONS="actimeo=3,vers=4.1"

clean () {
  sudo umount /tmp/nfs_mnt 
  sudo exportfs -u localhost:/tmp/nfs_test
  sudo rm /tmp/nfs_test/test.sh
  sudo rmdir /tmp/nfs_test
  rmdir /tmp/nfs_mnt
} 2>/dev/null

clean

sudo mkdir -p /tmp/nfs_test
sudo exportfs localhost:/tmp/nfs_test

mkdir -p /tmp/nfs_mnt
sudo mount -t nfs -o "$OPTIONS" localhost:/tmp/nfs_test /tmp/nfs_mnt

# sudo echo '#!/bin/sh' | sudo tee /tmp/nfs_test/test.sh
sudo echo 'echo OK' | sudo tee /tmp/nfs_test/test.sh

ls -l /tmp/nfs_mnt/test.sh 
mount | grep nfs


sudo chmod +x /tmp/nfs_test/test.sh



echo "sleeping $WAIT seconds before test....."
sleep $WAIT

ls -l /tmp/nfs_test/test.sh
/tmp/nfs_test/test.sh || strace /tmp/nfs_mnt/test.sh 

clean

