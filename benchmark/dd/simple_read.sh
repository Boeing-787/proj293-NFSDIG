#!/bin/bash
echo "Simple write test"
time dd if=/dev/zero of=/mnt/nfs_test/testfile bs=8K count=1024

echo "Simple read test"
time dd if=/mnt/nfs_test/testfile of=/dev/null bs=8K count=1024