#!/bin/bash
remote_ip=$1
remote_path=$2
local_path=$3
local_ip=$(hostname -I | awk '{print $1}')
# 检查rpcbind服务状态
rpcbind_status=$(systemctl is-active rpcbind)
if [[ -z "$1" || -z "$2" || -z "$3" ]]; then
    echo "请提供远程NFS服务器IP、远程路径和本地挂载路径。e.g. ./client.sh 192.168.1.1 /home/nfs /mnt/nfs"
    exit 1
fi

if [ "$rpcbind_status" != "active" ]; then
    echo "rpcbind服务未启动，请启动rpcbind服务后再运行此脚本。"
    exit 1
else
    echo "rpcbind服务已启动。"
fi

# 检查nfs-client.target服务状态
nfs_client_status=$(systemctl is-active nfs-client.target)
if [ "$nfs_client_status" != "active" ]; then
    echo "nfs-client服务未启动，请启动nfs-client服务后再运行此脚本。"
    exit 1
else
    echo "nfs-client服务已启动。"
fi

# 检查挂载点
echo "打印NFS客户端是否导出路径："
showmount -e $remote_ip | grep $remote_path | grep $local_ip
if [ $? -ne 0 ]; then
    echo "NFS服务端未导出路径，请检查NFS服务器配置。"
    exit 1
else
    echo "NFS服务端已导出路径。"
fi



echo "NFS客户端检测完成，未发现配置错误。"

sudo mount -t nfs $1:$2 $3

echo "自动挂载成功, 打印NFS挂载点信息如下："
mount | grep nfs