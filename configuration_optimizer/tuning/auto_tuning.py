import time
import pandas as pd
import torch
import torch.nn as nn
import subprocess
from pathlib import Path
import joblib
import os
import re
import pexpect

# ========== 配置路径 ==========
metrics_cpu = "/home/lll/nfsdig/output/cpu/cpu.csv"
metrics_disk = "/home/lll/nfsdig/output/disk/disk.csv"
metrics_memory = "/home/lll/nfsdig/output/memory/memory.csv"
metrics_network = "/home/lll/nfsdig/output/network/network.csv"
metrics_csv = "/home/lll/nfsdig/output/nfs/nfs.csv"     # 指标数据文件
scene_params_csv = "/home/lll/nfsdig/configuration_optimizer/tuning/optimized_parameter.csv"      # 场景参数表
model_path = "/home/lll/nfsdig/configuration_optimizer/classfier/nfs_classfication_model.pt"   # 分类器模型权重
scaler_path = "/home/lll/nfsdig/configuration_optimizer/classfier/scaler.pkl"                   # 训练时保存的标准化器
check_interval = 20                                        # 检查间隔（秒）
nfs_mount_point = "/home/lll/nfs"                         # NFS挂载点
samples_per_label = 12  # 总采样次数（包括前2个 warm-up）

# ========== 目标特征指标 ==========
target_features = [
    "read_ops", "read_kb_s", "read_kb_op", "read_retrans", "read_rtt", "read_exe", "read_queue",
    "write_ops", "write_kb_s", "write_kb_op", "write_retrans", "write_rtt", "write_exe", "write_queue"
]

# ========== 定义网络结构 ==========
class NFSNet(nn.Module):
    def __init__(self, input_dim):
        super(NFSNet, self).__init__()
        self.model = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(0.3),

            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.3),

            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(0.2),

            nn.Linear(32, 21)  # 标签范围 0-19
        )

    def forward(self, x):
        return self.model(x)

# ========== 初始化模型与 scaler ==========
input_dim = len(target_features)
clf = NFSNet(input_dim)
clf.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
clf.eval()

scaler = joblib.load(scaler_path)
scene_params_df = pd.read_csv(scene_params_csv)
last_line_count = 0  # 记录处理的行数

# ========== 利用autofs应用NFS参数 ==========
# server_ip = "10.249.8.111"
server_ip = "10.249.9.153"
remote_dir = "/data/nfs4"
local_mount = "/home/lll/nfs"
def apply_nfs_params(label, param ,server_ip="10.249.9.153",
                     remote_dir="/data/nfs4",
                     nfs_mount_point="/home/lll/nfs",
                     autofs_base="/mnt/nfs"):

    assert 0 <= label <= 19, f"label 超出范围: {label}"
    autofs_profile_path = f"{autofs_base}/profile{label}"

    # 强制访问 autofs 路径触发自动挂载
    print(f"[INFO] 激活 autofs 挂载点: {autofs_profile_path}")
    subprocess.run(["ls", autofs_profile_path], check=True)

    # 卸载原绑定挂载点
    print(f"[INFO] 卸载旧的绑定挂载点: {nfs_mount_point}")
    subprocess.run(f"sudo umount -l {nfs_mount_point}", shell=True, check=True)

    # 绑定新的 profile 到目标挂载点
    print(f"[INFO] 使用 bind 挂载 profile{label} 到 {nfs_mount_point}")
    subprocess.run(f"sudo mount --bind {autofs_profile_path} {nfs_mount_point}", shell=True, check=True)

    print(f"[INFO] NFS 参数已切换到 profile{label}，对应目录: {autofs_profile_path}")

# ========== 解析nfsiostat输出 ==========
def extract_first_float(s):
    match = re.search(r"[\d.]+", s)
    return float(match.group()) if match else 0.0
def parse(output):
    result = {
        "read_ops": 0.0, "read_kb_s": 0.0, "read_kb_op": 0.0, "read_retrans": 0.0,
        "read_rtt": 0.0, "read_exe": 0.0, "read_queue": 0.0,
        "write_ops": 0.0, "write_kb_s": 0.0, "write_kb_op": 0.0, "write_retrans": 0.0,
        "write_rtt": 0.0, "write_exe": 0.0, "write_queue": 0.0,
    }
    lines = output.strip().splitlines()
    for i, line in enumerate(lines):
        if "read:" in line and i + 1 < len(lines):
            read_values = lines[i + 1].split()
            if len(read_values) >= 7:
                result["read_ops"] = extract_first_float(read_values[0])
                result["read_kb_s"] = extract_first_float(read_values[1])
                result["read_kb_op"] = extract_first_float(read_values[2])
                result["read_retrans"] = extract_first_float(read_values[3])
                result["read_rtt"] = extract_first_float(read_values[4])
                result["read_exe"] = extract_first_float(read_values[5])
                result["read_queue"] = extract_first_float(read_values[6])
        elif "write:" in line and i + 1 < len(lines):
            write_values = lines[i + 1].split()
            if len(write_values) >= 7:
                result["write_ops"] = extract_first_float(write_values[0])
                result["write_kb_s"] = extract_first_float(write_values[1])
                result["write_kb_op"] = extract_first_float(write_values[2])
                result["write_retrans"] = extract_first_float(write_values[3])
                result["write_rtt"] = extract_first_float(write_values[4])
                result["write_exe"] = extract_first_float(write_values[5])
                result["write_queue"] = extract_first_float(write_values[6])
    return result

def parse_nfsstat(output):
    result = {
        "calls": 0,
        "retrans": 0,
        "authrefrsh": 0,
        "nfs_v4_total_ops": 0,
        "read_ops": 0,
        "write_ops": 0,
        "commit_ops": 0,
        "getattr_ops": 0,
        "lookup_ops": 0,
        "fsinfo_ops": 0,
        "access_ops": 0,
    }

    lines = output.strip().splitlines()
    parsing_rpc = False
    parsing_nfs_v4 = False

    for line in lines:
        if "Client rpc stats" in line:
            parsing_rpc = True
            continue
        if "Client nfs v4" in line:
            parsing_nfs_v4 = True
            continue

        if parsing_rpc:
            if re.match(r"^\s*calls", line):
                parts = line.strip().split()
                if len(parts) >= 3:
                    result["calls"] = int(parts[0])
                    result["retrans"] = int(parts[1])
                    result["authrefrsh"] = int(parts[2])
                parsing_rpc = False  # Done parsing this section

        elif parsing_nfs_v4:
            tokens = line.strip().split()
            for i in range(0, len(tokens), 2):
                if i + 1 >= len(tokens):
                    break
                op = tokens[i]
                count = int(tokens[i + 1])
                result["nfs_v4_total_ops"] += count

                if op == "read":
                    result["read_ops"] = count
                elif op == "write":
                    result["write_ops"] = count
                elif op == "commit":
                    result["commit_ops"] = count
                elif op == "getattr":
                    result["getattr_ops"] = count
                elif op == "lookup":
                    result["lookup_ops"] = count
                elif op == "fsinfo":
                    result["fsinfo_ops"] = count
                elif op == "access":
                    result["access_ops"] = count

    return result

# ========== 解析nfsdig输出 ==========
def parse_cpu_monitor(output):
    lines = output.strip().splitlines()
    if len(lines) < 2:
        return {}  # 无数据可解析

    header = lines[0].strip().split(",")
    latest = lines[-1].strip().split(",")

    if len(header) != len(latest):
        return {}  # 格式异常

    result = {}
    for key, value in zip(header, latest):
        key = key.strip()
        value = value.strip()
        if key == "timestamp":
            try:
                result[key] = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                result[key] = value  # 或者设为 None
        elif key == "users":
            result[key] = int(value)
        else:
            result[key] = extract_first_float(value)
    
    return result

def parse_disk(output):
    result = {
        "used_gb": 0.0,
        "avail_gb": 0.0,
        "use_percent": 0.0,
        "size_gb": 0.0,
        "mounted_on": "",
        "filesystem": "",
        "timestamp": ""
    }
    
    lines = output.strip().splitlines()
    if len(lines) < 2:
        return result  # 没有数据行

    header = lines[0].strip().split(",")
    latest_line = lines[-1].strip().split(",")

    if len(header) != len(latest_line):
        return result  # 格式异常

    for i, key in enumerate(header):
        key = key.strip()
        val = latest_line[i].strip()
        if key in ["used_gb", "avail_gb", "use_percent", "size_gb"]:
            result[key] = extract_first_float(val)
        elif key == "timestamp":
            try:
                result[key] = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                result[key] = val  # 如果解析失败，保留原字符串
        else:
            result[key] = val

    return result

def parse_memory(output):
    result = {
        "mem_total": 0.0,
        "mem_used": 0.0,
        "mem_free": 0.0,
        "mem_available": 0.0,
        "mem_usage_pct": 0.0,
        "swap_total": 0.0,
        "swap_used": 0.0,
        "swap_free": 0.0,
        "swap_usage_pct": 0.0,
        "timestamp": ""
    }

    lines = output.strip().splitlines()
    if len(lines) < 2:
        return result  # 无数据

    header = lines[0].strip().split(",")
    latest_line = lines[-1].strip().split(",")

    if len(header) != len(latest_line):
        return result  # 格式不一致

    for i, key in enumerate(header):
        key = key.strip()
        val = latest_line[i].strip()

        if key == "timestamp":
            try:
                result[key] = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                result[key] = val
        else:
            result[key] = extract_first_float(val)

    return result

def parse_network(output):
    result = {
        "iface_read_pk": 0.0,
        "iface_write_pk": 0.0,
        "iface_read_kb": 0.0,
        "iface_write_kb": 0.0,
        "iface_util": 0.0,
        "timestamp": ""
    }

    lines = output.strip().splitlines()
    if len(lines) < 2:
        return result  # 无有效数据

    header = lines[0].strip().split(",")
    latest_line = lines[-1].strip().split(",")

    if len(header) != len(latest_line):
        return result  # 列数不一致

    for i, key in enumerate(header):
        key = key.strip()
        val = latest_line[i].strip()

        if key == "timestamp":
            try:
                result[key] = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                result[key] = val
        else:
            result[key] = extract_first_float(val)
    return result

def parse_all_metrics(
    nfsiostat_output: str,
    nfsstat_output: str,
    cpu_output: str,
    memory_output: str,
    disk_output: str,
    network_output: str
):
 
    _ = parse_nfsstat(nfsstat_output)
    _ = parse_cpu_monitor(cpu_output)
    _ = parse_memory(memory_output)
    _ = parse_disk(disk_output)
    _ = parse_network(network_output)
    
    return parse(nfsiostat_output)

# ========== 主监控循环 ==========
def monitor_loop():
    print("[INFO] 开始监控...")
    last_label = None
# sudo fio --name=test --directory=/mnt/nfs_test --bs=1M --size=128M --numjobs=32 --time_based --runtime=150 --rw=readwrite --rwmixread=50 
    while True:
        try:
            print("--------------------------------------------")
            print(f"[INFO] 开始采集数据")
            cmd1 = ["nfsiostat", nfs_mount_point, "1", str(samples_per_label)]
            cmd2 = ["nfsstat", "-c"]
            result = subprocess.run(cmd1, capture_output=True, text=True)
            lines = result.stdout.strip().splitlines()
            # print(f"{lines}")
            # 分块提取数据
            blocks = []
            block = []
            for line in lines:
                if line.strip().startswith(f"{server_ip}:{remote_dir} mounted on {nfs_mount_point}"):
                    if block:
                        blocks.append(block)
                        block = []
                block.append(line)
            if block:
                blocks.append(block)
            valid_blocks = blocks[2:]  # 跳过前两个 warm-up
            print(f"[INFO] 共采集 {len(valid_blocks)} 条有效数据，开始分析")

            # 对每个 block 提取 metrics，然后平均
            metrics_list = [parse_all_metrics("\n".join(b)) for b in valid_blocks]
            avg_metrics = {k: sum(m[k] for m in metrics_list) / len(metrics_list) for k in target_features}
            # print(f"{avg_metrics}")
            # 特征标准化并预测
            ####
            feature_values = [avg_metrics[k] for k in target_features]
            X_std = scaler.transform([feature_values])
            X_tensor = torch.tensor(X_std, dtype=torch.float32)
            start_time = time.time()
            with torch.no_grad():
                output = clf(X_tensor)
                label = torch.argmax(output, dim=1).item()
            print(f"[INFO] 识别场景为：{label}")
            if label == last_label:
                print(f"[INFO] 场景未变化（仍为 {label}），无需重新挂载。")
            else:
                matched_row = scene_params_df[scene_params_df["label"] == label]
                if not matched_row.empty:
                    params = matched_row.iloc[0].to_dict()
                    apply_nfs_params(label, params)
                    last_label = label
                else:
                    print(f"[ERROR] 未找到匹配参数，场景label={label}")
            elapsed = time.time() - start_time
            # print(f"[SUCCESS] 调优完成，总耗时: {elapsed:.3f} 秒")
            print(f"[SUCCESS] 调优完成")
            print("--------------------------------------------")
        except Exception as e:
            print(f"[ERROR] 出现异常：{e}")

        time.sleep(check_interval)


if __name__ == "__main__":
    monitor_loop()