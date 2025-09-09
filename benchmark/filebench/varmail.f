# varmail.f
# Filebench script simulating varmail workload (fio: rw=readwrite, bs=1032k, size=8192k, numjobs=16, rwmixread=50)

define fileset name=varmail_files,path=/home/lll/nfs,size=8192k,entries=16

define process name=varmail_proc,instances=1
{
  thread name=varmail_thread,memsize=200m
  {
    flowop read_op name=read,filesetname=varmail_files,rdpct=50,rdsize=1032k,rdpos=random
    flowop write_op name=write,filesetname=varmail_files,wrpct=50,wrsize=1032k,wrpos=random
  }
}

echo "Starting varmail workload simulation"

run 60