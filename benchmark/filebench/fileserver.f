# fileserver.f
# Filebench script simulating fileserver workload (fio: rw=readwrite, bs=352k, size=2048k, numjobs=16, rwmixread=33)

define fileset name=fileserver_files,path=/mnt/nfs_test/testbench,size=2048k,entries=16

define process name=fileserver_proc,instances=1
{
  thread name=fileserver_thread,memsize=100m
  {
    flowop read_op name=read,filesetname=fileserver_files,rdpct=33,rdsize=352k,rdpos=random
    flowop write_op name=write,filesetname=fileserver_files,wrpct=67,wrsize=352k,wrpos=random
  }
}

echo "Starting fileserver workload simulation"

run 60