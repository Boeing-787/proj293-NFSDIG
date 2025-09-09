import subprocess
import re

def test_disk_read_speed(device="/dev/nvme0n1"):
    print(f"正在测试磁盘读取速度(设备: {device})...")
    try:
        result = subprocess.run(
            ["sudo", "hdparm", "-t", device],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout
        match = re.search(r"=\s+([\d.]+)\s+MB/sec", output)
        if match:
            speed = float(match.group(1))
            print(f"磁盘读取速度: {speed:.2f} MB/s")
            return speed
        else:
            print("未能解析磁盘读取速度")
    except subprocess.CalledProcessError as e:
        print(f"磁盘测试失败: {e}")
    return None


def test_network_throughput(server_ip="10.249.9.153", duration=30):
    print(f"\n正在测试网络吞吐量(服务器: {server_ip}，持续时间: {duration}s)...")
    try:
        result = subprocess.run(
            ["iperf3", "-c", server_ip, "-t", str(duration)],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout
        match = re.search(r"receiver.*?([\d.]+)\s+([KMG]bits/sec)", output, re.IGNORECASE)
        if match:
            throughput = float(match.group(1))
            unit = match.group(2)
            print(f"网络吞吐量: {throughput:.2f} {unit}")
            return throughput, unit
        else:
            print("未能解析网络吞吐量")
    except subprocess.CalledProcessError as e:
        print(f"网络测试失败: {e}")
    return None, None


def main():
    print("===== 系统最大吞吐量测试报告 =====\n")

    disk_speed = test_disk_read_speed("/dev/nvme0n1")
    net_speed, net_unit = test_network_throughput("192.168.1.100", duration=5)

    print("\n===== 测试汇总 =====")
    if disk_speed is not None:
        print(f"磁盘读取速度: {disk_speed:.2f} MB/s")
    if net_speed is not None:
        print(f"网络吞吐量: {net_speed:.2f} {net_unit}")
    print("=================================")


if __name__ == "__main__":
    main()