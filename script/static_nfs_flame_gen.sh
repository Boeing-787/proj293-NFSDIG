# 查看相关事件
 sudo ls /sys/kernel/debug/tracing/events/nfs 
# 指定记录NFS相关事件（更精确）
sudo perf record -e 'nfs:*' -e 'sunrpc:*' -e 'nfsd:*' -e 'nfs4:*' -a -g -- sleep 30
# 生成原始数据
sudo perf script > perf.nfs.trace
# 折叠堆栈
~/FlameGraph/stackcollapse-perf.pl perf.nfs.trace > nfs.folded
# 生成SVG火焰图
~/FlameGraph/flamegraph.pl nfs.folded > nfs_flame.svg
# 删除中间文件
rm perf.nfs.trace nfs.folded perf.data