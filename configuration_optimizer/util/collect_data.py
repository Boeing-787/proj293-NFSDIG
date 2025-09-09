import subprocess
import time
import csv
import os
import re
from pathlib import Path

nfs_mount = "/mnt/nfs_test"
server_ip = "10.249.8.111"
remote_dir = "/data/nfs"
output_csv = "../data/train_dataset/nfs_metrics_dataset6.csv"
samples_per_label = 60  # 每种场景采集样本数
sampling_interval = 1   # 每次采样间隔（秒）
fio_runtime = 180        # 每轮 FIO 执行时间（秒）

# 关键指标
target_keys = [
    "nfs_close", "nfs_statfs", "read_avg_queue", "write_avg_queue",
    "read_avg_exe", "read_kb_per_op", "nfs_read"
]

fio_scenarios = [ 
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=1M", "--size=128M", "--numjobs=32", "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=1M", "--size=128M", "--numjobs=16", "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=1M", "--size=128M", "--numjobs=4",  "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=64k", "--size=8M", "--numjobs=32", "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=64k", "--size=8M", "--numjobs=16", "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=64k", "--size=8M", "--numjobs=4",  "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=4k", "--size=512k", "--numjobs=32", "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=4k", "--size=512k", "--numjobs=16", "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/mnt/nfs_test", "--rw=readwrite", "--bs=4k", "--size=512k", "--numjobs=4",  "--rwmixread=50", "--direct=1", "--time_based", "--runtime=180", "--group_reporting", "--output-format=json"]
]

def run_cmd(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return result.stdout

def extract_first_float(s):
    match = re.search(r"[\d.]+", s)
    return float(match.group()) if match else 0.0

def parse_nfsstat(output):
    result = {k: 0.0 for k in target_keys}

    lines = output.splitlines()
    # 先解析 rpc stats 区域
    rpc_section_start = False
    for i, line in enumerate(lines):
        if line.strip().startswith("Client rpc stats:"):
            rpc_section_start = True
            continue
        if rpc_section_start and line.strip():
            # rpc stats header line 和数值行，我们跳过标题行，解析下一行
            parts = line.strip().split()
            break

    # 解析 Client nfs v4 区域
    nfs_section_start = False
    # 用一个字典映射 key 到 target_keys
    key_map = {
        "close": "nfs_close",
        "statfs": "nfs_statfs",
        "read": "nfs_read"
    }

    # 找到 Client nfs v4: 的行数
    for i, line in enumerate(lines):
        if line.strip().startswith("Client nfs v4:"):
            nfs_section_start = True
            # 从下一行开始解析
            idx = i + 1
            break

    if nfs_section_start:
        # 从 idx 开始，逐行读取，直到空行或者文件末尾
        while idx < len(lines):
            line1 = lines[idx].strip()
            idx += 1
            if idx >= len(lines):
                break
            line2 = lines[idx].strip()
            idx += 1

            if not line1 or not line2:
                break

            # line1 和 line2 是操作名列表 和对应数据列表
            ops = line1.split()
            vals = line2.split()

            # 每个操作对应两列数据，分别是数字和百分比
            # 对于 nfs 计数我们只取数字列，数字列在偶数索引，百分比在奇数索引
            for i_op in range(0, len(ops)):
                op = ops[i_op].lower()
                if op in key_map:
                    # 获取数字列索引，注意每操作占两列，数字在偶数列，即 i_op * 2
                    val_idx = i_op * 2
                    if val_idx < len(vals):
                        try:
                            val = float(vals[val_idx])
                            result[key_map[op]] = val
                        except:
                            pass
    return result

def parse_nfsiostat(output):
    result = {}
    lines = output.strip().splitlines()
    for i, line in enumerate(lines):
        if "read:" in line and i + 1 < len(lines):
            values = lines[i+1].split()
            if len(values) >= 7:
                result["read_avg_queue"] = extract_first_float(values[6])
                result["read_avg_exe"] = extract_first_float(values[5])
                result["read_kb_per_op"] = extract_first_float(values[2])
        elif "write:" in line and i + 1 < len(lines):
            values = lines[i+1].split()
            if len(values) >= 7:
                result["write_avg_queue"] = extract_first_float(values[6])
    return result

def mount_nfs():
    subprocess.run(["sudo", "umount", nfs_mount], stderr=subprocess.DEVNULL)
    cmd = ["sudo", "mount", "-t", "nfs", f"{server_ip}:{remote_dir}", nfs_mount]
    subprocess.run(cmd, check=True)

def umount_nfs():
    subprocess.run(["sudo", "umount", nfs_mount], stderr=subprocess.DEVNULL)

def write_header(path):
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=target_keys + ["label"])
        writer.writeheader()

def append_row(path, row):
    with open(path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=target_keys + ["label"])
        writer.writerow(row)

def collect_metrics(label):
    for i in range(samples_per_label):
        print(f"  [采样] label={label}, sample={i+1}/{samples_per_label}")
        nfsstat_out = run_cmd("nfsstat -c")
        nfsiostat_out = run_cmd(f"nfsiostat {nfs_mount} 1 1")

        metrics = {**parse_nfsstat(nfsstat_out), **parse_nfsiostat(nfsiostat_out)}
        metrics["label"] = label
        append_row(output_csv, metrics)
        time.sleep(sampling_interval)

if __name__ == "__main__":
    if not os.path.exists(output_csv):
        write_header(output_csv)

    for label in range(1, 10):
        print(f"\n=== 场景 {label} 开始 ===")
        mount_nfs()
        fio_proc = subprocess.Popen(fio_scenarios[label - 1])
        collect_metrics(label)
        fio_proc.wait()
        umount_nfs()
        print(f"=== 场景 {label} 结束 ===\n")
        time.sleep(10)  # 避免过快切换
