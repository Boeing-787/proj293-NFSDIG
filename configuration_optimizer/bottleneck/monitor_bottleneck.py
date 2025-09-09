import os
import time
import shutil
import psutil

CPU_THRESHOLD = 90                   # CPU负载阈值
MEM_THRESHOLD = 90                   # 内存使用率阈值（%）
DISK_FREE_THRESHOLD = 10             # 磁盘剩余空间小于10%视为瓶颈
NET_UTIL_THRESHOLD = 0.9             # 网络使用率超过95%
NET_BANDWIDTH_MBPS = 125             # 带宽上限为125MB/s (1Gbps)

# def check_cpu():
#     try:
#         load1, _, _ = os.getloadavg()
#         core_count = os.cpu_count()
#         load_percent = (load1 / core_count) * 100
#         if load_percent > CPU_THRESHOLD:
#             return f"[CPU瓶颈]: 1分钟平均负载为 {load1:.2f}，约等于 {load_percent:.1f}% 使用率"
#     except:
#         return None
def check_cpu():
    usage = psutil.cpu_percent(interval=1)
    if usage > CPU_THRESHOLD:
        return f"[CPU瓶颈]: 当前CPU使用率为 {usage:.1f}%"
    return None

def check_memory():
    try:
        with open('/proc/meminfo') as f:
            info = {line.split(':')[0]: int(line.split()[1]) for line in f if ':' in line}
        total = info.get('MemTotal', 0)
        available = info.get('MemAvailable', 0)
        used_percent = (1 - available / total) * 100
        if used_percent > MEM_THRESHOLD:
            return f"[内存瓶颈]：当前使用率约为 {used_percent:.1f}%"
    except:
        return None

def check_disk():
    bottlenecks = []
    target_device = "/dev/nvme0n1p2"
    target_mount = None

    # 查找该设备的挂载点
    with open("/proc/mounts") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == target_device:
                target_mount = parts[1]
                break

    if target_mount:
        try:
            total, used, free = shutil.disk_usage(target_mount)
            free_percent = (free / total) * 100
            if free_percent < DISK_FREE_THRESHOLD:
                bottlenecks.append(
                    f"[磁盘瓶颈]：挂载点 {target_mount}（{target_device}）剩余空间为 {free_percent:.1f}%"
                )
        except Exception as e:
            bottlenecks.append(f"磁盘检查错误：无法访问 {target_mount} - {e}")
    else:
        bottlenecks.append(f"未找到设备 {target_device} 的挂载点")

    return bottlenecks

def read_net_bytes():
    stats = {}
    with open("/proc/net/dev") as f:
        for line in f:
            if ":" in line:
                iface, data = line.split(":", 1)
                iface = iface.strip()
                fields = data.strip().split()
                recv = int(fields[0])
                sent = int(fields[8])
                stats[iface] = (recv, sent)
    return stats

# def check_network():
#     stats1 = read_net_bytes()
#     time.sleep(1)
#     stats2 = read_net_bytes()

#     bottlenecks = []
#     for iface in stats1:
#         if iface == 'lo':
#             continue
#         recv_diff = stats2[iface][0] - stats1[iface][0]
#         sent_diff = stats2[iface][1] - stats1[iface][1]
#         recv_mbps = recv_diff / 1024 / 1024  # B -> MB
#         sent_mbps = sent_diff / 1024 / 1024
#         if recv_mbps > NET_BANDWIDTH_MBPS * NET_UTIL_THRESHOLD or \
#            sent_mbps > NET_BANDWIDTH_MBPS * NET_UTIL_THRESHOLD:
#             bottlenecks.append(
#                 f"[网络瓶颈]：接口 {iface} 当前吞吐 Rx: {recv_mbps:.2f} MB/s, Tx: {sent_mbps:.2f} MB/s"
#             )
#     return bottlenecks

def read_net_bytes():
    stats = {}
    with open('/proc/net/dev') as f:
        for line in f.readlines()[2:]:
            parts = line.strip().split()
            iface = parts[0].strip(':')
            recv_bytes = int(parts[1])
            sent_bytes = int(parts[9])
            stats[iface] = (recv_bytes, sent_bytes)
    return stats

def check_network():
    stats1 = read_net_bytes()
    time.sleep(1)
    stats2 = read_net_bytes()

    bottlenecks = []
    for iface in stats1:
        if iface == 'lo' or iface not in stats2:
            continue  # 排除本地回环或消失的接口

        recv_diff = stats2[iface][0] - stats1[iface][0]
        sent_diff = stats2[iface][1] - stats1[iface][1]

        recv_mbps = recv_diff / (1024 * 1024)  # B/s -> MB/s
        sent_mbps = sent_diff / (1024 * 1024)

        threshold = NET_BANDWIDTH_MBPS * NET_UTIL_THRESHOLD

        if recv_mbps > threshold or sent_mbps > threshold:
            bottlenecks.append(
                f"[网络瓶颈]：接口 {iface} 当前吞吐 Rx: {recv_mbps:.2f} MB/s, Tx: {sent_mbps:.2f} MB/s，超过阈值 {threshold:.2f} MB/s"
            )

    return bottlenecks

def check_bottlenecks():
    bottlenecks = []

    cpu_bottle = check_cpu()
    if cpu_bottle:
        bottlenecks.append(cpu_bottle)

    mem_bottle = check_memory()
    if mem_bottle:
        bottlenecks.append(mem_bottle)

    disk_bottles = check_disk()
    bottlenecks.extend(disk_bottles)

    net_bottles = check_network()
    bottlenecks.extend(net_bottles)

    if bottlenecks:
        print("=== 系统瓶颈检测报告 ===")
        for b in bottlenecks:
            print(b)
        print("========================\n")
    else:
        print("系统状态正常，无明显瓶颈")
        print("========================\n")

if __name__ == "__main__":
    while True:
        check_bottlenecks()
        time.sleep(5)
