#!/bin/bash
echo "Simple write test"
time dd if=/dev/zero of=/mnt/local_test/testfile bs=8K count=1024

echo "Simple read test"
# echo 3 | sudo tee /proc/sys/vm/drop_caches
time dd if=/mnt/local_test/testfile of=/dev/null bs=8K count=1024