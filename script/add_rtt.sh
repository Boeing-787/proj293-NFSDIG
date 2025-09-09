#!/bin/bash

# 定义颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 网络接口（默认为 lo）
INTERFACE="lo"

# 帮助信息
show_help() {
    cat <<EOF
NFS 故障模拟工具
用法: $0 [选项] [参数]

网络故障模拟:
  --delay <ms>        添加网络延迟（毫秒）
  --delay-var <ms>    添加带波动的延迟（例如：100 10 表示 100ms ± 10ms）
  --bandwidth <Kbps>  限制带宽
  --loss <percent>    模拟丢包率（百分比）
  --clear-tc          清除所有流量控制规则
  --set-mtu <size>    设置网络接口的 MTU 值

防火墙规则:
  --block-nfs         阻断 NFS 端口（2049）
  --unblock-nfs       解除 NFS 端口阻断

压力测试:
  --stress-cpu <num>       CPU 压力测试（指定核心数）
  --stress-memory <size>   内存压力测试（例如：1G）
  --stress-time <seconds>  压力测试持续时间

清理:
  --clean                  清除所有故障模拟设置

示例:
  $0 --delay 100              # 添加 100ms 延迟
  $0 --set-mtu 1500           # 设置 MTU 为 1500
  $0 --cpu-limit 20           # 限制 CPU 使用率为 20%
  $0 --stress-cpu 4 --stress-time 60  # 4核心CPU压力测试60秒
EOF
}

# 网络故障模拟函数
add_delay() {
    sudo tc qdisc add dev $INTERFACE root netem delay $1ms
    echo -e "${GREEN}已添加 $1ms 网络延迟${NC}"
}

add_delay_variation() {
    sudo tc qdisc add dev $INTERFACE root netem delay $1ms $2ms
    echo -e "${GREEN}已添加 $1ms ± $2ms 网络延迟${NC}"
}

# 删除网络延迟配置
del_delay() {
    sudo tc qdisc del dev $INTERFACE root
    echo -e "${RED}已删除网络延迟配置${NC}"
}

limit_bandwidth() {
    tcset $INTERFACE --rate $1Kbps
    echo -e "${GREEN}已限制带宽为 $1 Kbps${NC}"
}

add_packet_loss() {
    sudo tcset $INTERFACE --loss $1%
    echo -e "${GREEN}已设置丢包率为 $1%${NC}"
}

clear_tc() {
    sudo tcdel $INTERFACE --all
    echo -e "${GREEN}已清除所有流量控制规则${NC}"
}

set_mtu() {
    sudo ip link set dev $INTERFACE mtu $1
    echo -e "${GREEN}已将 $INTERFACE 的 MTU 设置为 $1${NC}"
}

# 防火墙规则函数
block_nfs() {
    sudo iptables -A INPUT -p tcp --dport 2049 -j DROP
    sudo iptables -A OUTPUT -p tcp --dport 2049 -j DROP
    echo -e "${GREEN}已阻断 NFS 端口${NC}"
}

unblock_nfs() {
    sudo iptables -D INPUT -p tcp --dport 2049 -j DROP
    sudo iptables -D OUTPUT -p tcp --dport 2049 -j DROP
    echo -e "${GREEN}已解除 NFS 端口阻断${NC}"
}



# 压力测试函数
stress_test() {
    local cpu=$1
    local mem=$2
    local time=$3
    
    if [ ! -z "$cpu" ]; then
        stress-ng --cpu $cpu --timeout ${time}s &
    fi
    if [ ! -z "$mem" ]; then
        stress-ng --vm 2 --vm-bytes $mem --timeout ${time}s &
    fi
}

# 清理函数
cleanup() {
    # clear_tc
    unblock_nfs
    del_delay
    # 将进程移出 cgroup
    echo $$ | sudo tee /sys/fs/cgroup/cgroup.procs > /dev/null 2>&1
    # 删除 cgroup
    sudo cgdelete cpu,memory,blkio:/nfslimit 2>/dev/null
    echo -e "${GREEN}已清除所有故障模拟设置${NC}"
}

# 另外添加一个新函数用于检查 cgroup 状态
check_cgroup_status() {
    echo -e "${YELLOW}当前 CPU 限制状态：${NC}"
    cat /sys/fs/cgroup/nfslimit/cpu.max 2>/dev/null || echo "未设置 CPU 限制"
    
    echo -e "${YELLOW}当前内存限制状态：${NC}"
    cat /sys/fs/cgroup/nfslimit/memory.max 2>/dev/null || echo "未设置内存限制"
    
    echo -e "${YELLOW}当前 IO 限制状态：${NC}"
    cat /sys/fs/cgroup/nfslimit/io.max 2>/dev/null || echo "未设置 IO 限制"
    
    echo -e "${YELLOW}当前进程所属 cgroup：${NC}"
    cat /proc/$$/cgroup
}

# 主程序
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

while [ $# -gt 0 ]; do
    case "$1" in
        --help)
            show_help
            exit 0
            ;;
        --delay)
            add_delay $2
            shift 2
            ;;
        --delay-var)
            add_delay_variation $2 $3
            shift 3
            ;;
        --bandwidth)
            limit_bandwidth $2
            shift 2
            ;;
        --loss)
            add_packet_loss $2
            shift 2
            ;;
        --clear-tc)
            clear_tc
            shift
            ;;
        --block-nfs)
            block_nfs
            shift
            ;;
        --unblock-nfs)
            unblock_nfs
            shift
            ;;
        --stress-cpu)
            STRESS_CPU=$2
            shift 2
            ;;
        --stress-memory)
            STRESS_MEM=$2
            shift 2
            ;;
        --stress-time)
            STRESS_TIME=$2
            shift 2
            ;;
        --clean)
            cleanup
            shift
            ;;
        --status)
            check_cgroup_status
            shift
            ;;
        --set-mtu)
            set_mtu $2
            shift 2
            ;;
        *)
            echo -e "${RED}未知选项: $1${NC}"
            show_help
            exit 1
            ;;
    esac
done

# 如果设置了压力测试参数，在最后执行
if [ ! -z "$STRESS_CPU" ] || [ ! -z "$STRESS_MEM" ]; then
    stress_test "$STRESS_CPU" "$STRESS_MEM" "${STRESS_TIME:-60}"
fi