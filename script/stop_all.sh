for pidfile in /tmp/nfstrace.pid /tmp/syscount.pid /tmp/vfsstat.pid /tmp/biosnoop.pid; do
    if [ -f "$pidfile" ]; then
        pid=$(cat "$pidfile")
        sudo kill "$pid"
        rm -f "$pidfile"
    fi
done