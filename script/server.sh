#!/bin/bash
# remote_ip=$(hostname -I | awk '{print $1}')
# client_ip=$1
# client_path=$2
# local_path=$3

# 检查rpcbind服务状态
rpcbind_status=$(systemctl is-active rpcbind)
if [ "$rpcbind_status" != "active" ]; then
    echo "rpcbind服务未启动，请启动rpcbind服务后再运行此脚本。"
    exit 1
else
    echo "rpcbind服务已启动。"
fi

# 检查nfs-server服务状态
nfs_server_status=$(systemctl is-active nfs-server)
if [ "$nfs_server_status" != "active" ]; then
    echo "nfs-server服务未启动，请启动nfs-server服务后再运行此脚本。"
    exit 1
else
    echo "nfs-server服务已启动。"
fi

# 检查 /etc/exports 文件是否存在且不为空
if [ ! -s /etc/exports ]; then
    echo "/etc/exports 文件未配置或为空，请配置该文件后再运行此脚本。"
    exit 1
else
    echo "/etc/exports 文件已配置。"
fi

# 检查导出配置是否已生效
exportfs_output=$(sudo exportfs -v)
if [ -z "$exportfs_output" ]; then
    echo "导出配置未生效，请重新导出NFS共享目录。"
    exit 1
else
    echo "导出配置已生效，当前NFS共享目录："
    echo "$exportfs_output"
fi


# 端口检查
# sudo cat /etc/nfs.conf
echo "检查rpc端口信息"
rpcinfo -p | grep nfs

echo "检查哪些客户端正在使用nfs挂载"
sudo cat /proc/fs/nfs/exports 


echo "NFS服务端检测完成，未发现配置错误。"
