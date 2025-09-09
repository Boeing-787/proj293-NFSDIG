

# 网络测试
## 添加延迟
<!-- # 使用 tc 命令添加网络延迟

# qdisc: Queueing Discipline，队列规则
# add: 添加新的规则
# dev eth0: 指定网络设备 eth0
# root: 在根队列上添加规则
# netem: Network Emulator，网络模拟器
# delay 100ms: 设置 100 毫秒的固定延迟 -->
sudo tc qdisc add dev lo root netem delay 100ms
### 添加带波动的延迟（100ms ± 10ms）
sudo tc qdisc add dev lo root netem delay 100ms 10ms

### 限制带宽
tcset lo --rate 100Kbps

### 模拟丢包
tcset lo --loss 10%
### 恢复
sudo tcdel lo --all

## 使用namespace和cgroup隔离网络

## 防火墙
### 阻断特定端口（例如 2049 端口）
sudo iptables -A INPUT -p tcp --dport 2049 -j DROP
sudo iptables -A OUTPUT -p tcp --dport 2049 -j DROP
### 恢复
sudo iptables -D INPUT -p tcp --dport 2049 -j DROP
sudo iptables -D OUTPUT -p tcp --dport 2049 -j DROP
# 客户端
## CPU
1. 创建 cgroup
sudo mkdir -p /sys/fs/cgroup/nfslimit
2. 设置 CPU 限制（20% CPU）
sudo echo "+cpu" | sudo tee /sys/fs/cgroup/cgroup.subtree_control
sudo echo "20000 100000" | sudo tee /sys/fs/cgroup/nfslimit/cpu.max
3. 在限制下运行命令
sudo cgexec -g cpu:nfslimit command
4. 或直接将当前进程添加到cgroup中
echo $$ > /sys/fs/cgroup/nfslimit/cgroup.procs

# 内存
1. 创建内存 cgroup
sudo cgcreate -g memory:/nfslimit
2. 设置内存限制（如 512MB）
sudo cgset -r memory.limit_in_bytes=512M nfslimit
3. 在限制下运行
sudo cgexec -g memory:nfslimit command
# 模拟各种资源受限场景
ulimit -a

## 磁盘
#### 设置最低 I/O 优先级
ionice -c 3 -p $(pgrep nfs)
1. 创建 blkio cgroup
sudo cgcreate -g blkio:/nfslimit

2. 限制 I/O 带宽（bytes per second）
sudo cgset -r blkio.throttle.read_bps_device="8:0 1048576" nfslimit

## 使用stress-ng工具
### CPU压力测试
stress-ng --cpu 4 --timeout 60s
### 内存压力测试
stress-ng --vm 2 --vm-bytes 1G --timeout 60s
## 模拟文件系统限制：
### 启用 quota
sudo quotacheck -cugm /mount/point
sudo quotaon -v /mount/point
### 设置配额
sudo edquota -u username

### 创建小容量的文件系统镜像
dd if=/dev/zero of=smallfs.img bs=1M count=100
mkfs.ext4 smallfs.img
### 挂载
sudo mount smallfs.img /mnt/small

# 服务端特有故障：
## 文件系统故障

## IO故障损坏

## 配置故障
### 挂载点未创建
未编辑/etc/exports或未更新，即执行sudo exportfs
运行命令：sudo mount -t nfs 10.249.8.111:/data/fault_nfs /home/lll/nfs
报错信息：mount.nfs: access denied by server while mounting 10.249.8.111:/data/fault_nfs
## 权限故障
### 创建文件权限不够
运行命令：  sudo touch test.txt
报错信息：  touch: cannot touch 'test.txt': Permission denied
修改方式： 将/data/fault_nfs改为nobody:nogroup


# 一系列docker案例
1. feisky/word-pop： 动态文件读写