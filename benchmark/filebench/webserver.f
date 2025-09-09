# webserver.f
# Filebench script simulating webserver workload (fio: rw=readwrite, bs=932k, size=8192k, numjobs=16, rwmixread=90)

define fileset name=webserver_files,path=/home/lll/nfs,size=8192k,entries=16

define process name=webserver_proc,instances=1
{
  thread name=webserver_thread,memsize=200m
  {
    flowop read_op name=read,filesetname=webserver_files,rdpct=90,rdsize=932k,rdpos=random
    flowop write_op name=write,filesetname=webserver_files,wrpct=10,wrsize=932k,wrpos=random
  }
}

echo "Starting webserver workload simulation"

run 60