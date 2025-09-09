sudo ./exe/syscount &
echo $! > /tmp/syscount.pid
sudo ./exe/bcc-tools/biosnoop.py &
echo $! > /tmp/biosnoop.pid
sudo ./exe/vfsstat &
echo $! > /tmp/vfsstat.pid
sudo ./exe/nfstrace -r -o -d -t -x --xdp-interface "lo" &
echo $! > /tmp/nfstrace.pid
wait