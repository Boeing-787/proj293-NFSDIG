# 查看挂载的nfs
mount | grep nfs 
cat /proc/mounts | grep nfs # 可视化效果一般
# 查看防火墙规则
sudo iptables -L | grep 2049
# 查看selinux状态
getenforce
# 查看系统日志
sudo tail -f /var/log/syslog | grep -i nfs
# 查看rpc服务状态
rpcinfo -p 
# 查看rpc服务日志
sudo tail -f /var/log/syslog | grep -i rpc
# 查看rpc服务配置
sudo cat /etc/idmapd.conf
# 查看挂载信息
showmount -e <hostname>
# 查看性能信息
sudo cat /proc/self/mountstats
# 操作记数
/proc/net/rpc/nfsd
# 查看nfsd日志
# 设置nfs调试级别
sudo sysctl -w sunrpc.nfs_debug=1023
# 关闭nfs调试级别
sudo sysctl -w sunrpc.nfs_debug=0