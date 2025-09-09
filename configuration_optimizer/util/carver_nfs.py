# 我们先用**拉丁超立方（LHS）在高维离散参数空间中做覆盖性采样并执行真实/仿真实验收集性能（吞吐量、延迟），
# 然后用方差分解/组内相对标准差（RSD）作为性能可解释性度量，通过贪心的条件重要性评分（variance-reduction）**
# 逐步选出能最大程度解释性能差异的参数集合，直到“按这些参数分组后，组内性能不再显著波动（RSD 小于阈值）”，即认为找到了核心参数集。
from pyDOE import lhs   # 拉丁超立方采样，用于从高维参数空间中均匀采样。
import numpy as np
import random
import time
from collections import defaultdict
import subprocess
import json

# ========== Step 1: 定义 NFS 参数空间 + LHS 采样 ==========
# 定义了 10 个 NFS 可调参数，每个参数对应一个有限的离散值列表
nfs_params = {
    'rsize': [4096, 8192, 16384, 32768, 65536],
    'wsize': [4096, 8192, 16384, 32768, 65536],
    'timeo': [7, 10, 30, 70],
    'retrans': [2, 3, 5],
    'proto': ['tcp', 'udp'],
    'hard': ['hard', 'soft'],
    'actimeo': [0, 1, 5, 30],
    'vers': ['3', '4', '4.1'],
    'async': ['sync', 'async'],
    'threads': [8, 16, 32],

    # 新增
    'mount_mode': ['rw', 'ro'],
    # 'sec': ['sys', 'krb5', 'krb5i', 'krb5p'],
    'noacl': [True, False],
    'acregmin': [0, 3, 5],
    'acregmax': [30, 60, 120],
    'acdirmin': [0, 3, 5],
    'acdirmax': [30, 60, 120],
    'noresvport': [True, False],
    'nolock': [True, False],
    'lock': [True, False],
    'bg_mode': ['bg', 'fg']
}

param_names = list(nfs_params.keys())
# 二维列表，每一行是一个参数的所有可能取值
param_choices = [nfs_params[p] for p in param_names]
# 参数的总数（即参数空间的维度）
dim = len(param_names)

def generate_lhs_samples(num_samples=50):
    lhs_matrix = lhs(dim, samples=num_samples)
    configurations = []

    for i in range(num_samples):
        config = {}
        for j in range(dim):
            values = param_choices[j]
            idx = int(lhs_matrix[i][j] * len(values))
            idx = min(idx, len(values) - 1)
            config[param_names[j]] = values[idx]
        configurations.append(config)
    return configurations

# ========== Step 2: 部署实验并模拟测量性能 ==========
def run_nfs_experiment(config):
    # 配置参数拼接为挂载选项字符串
    # 将输入参数拼接成 mount 命令需要的格式
    mount_opts = f"nolock,nfsvers=3,vers=3,"
    mount_opts = f"rsize={config['rsize']},wsize={config['wsize']},timeo={config['timeo']},"
    mount_opts += f"retrans={config['retrans']},proto={config['proto']},hard={config['hard']},"
    mount_opts += f"actimeo={config['actimeo']},vers={config['vers']}"
    mount_opts += f",async={config['async']},threads={config['threads']}"
    # mount_opts += f",mount_mode={config['mount_mode']},sec={config['sec']}"
    mount_opts += f",mount_mode={config['mount_mode']}"
    mount_opts += f",noacl={config['noacl']},acregmin={config['acregmin']}"
    mount_opts += f",acregmax={config['acregmax']},acdirmin={config['acdirmin']}"
    mount_opts += f",acdirmax={config['acdirmax']},noresvport={config['noresvport']}"
    mount_opts += f",nolock={config['nolock']},lock={config['lock']}"
    mount_opts += f",bg_mode={config['bg_mode']}"

    # 挂载 NFS
    server_ip = "10.249.8.111"
    remote_dir = "/data/nfs"
    local_mount = "/mnt/nfs_test"

    # sudo mount -t nfs 10.249.8.111:/data/nfs /mnt/nfs_test
    # sudo umount /mnt/nfs_test
    # sudo mount -t nfs  -o rw,bg,timeo=50,retrans=2 10.249.8.111:/data/nfs /mnt/nfs_test
    # subprocess.run(["sudo", "umount", local_mount], stderr=subprocess.DEVNULL)
    # # 调用 subprocess.check_call(...) 执行真实的 NFS 挂载
    # # sudo mount -t nfs -o <mount_opts> 127.0.0.1:/nfs /mnt/nfs_test
    # mount_cmd = ["sudo", "mount", "-t", "nfs", "-o", mount_opts,
    #              f"{server_ip}:{remote_dir}", local_mount]
    mount_cmd = ["sudo", "mount", "-t", "nfs", f"{server_ip}:{remote_dir}", local_mount,
                 "-o", mount_opts]
    try:
        subprocess.check_call(mount_cmd)
    except subprocess.CalledProcessError:
        print("挂载失败，跳过该配置")
        return 0.0, float("inf")  # 性能极差，跳过

    # 使用 fio 执行 I/O 测试
    fio_cmd = [
        # "fio", "--name=test", "--directory=/mnt/nfs_test",
        "fio", "--name=test", "--directory=/home/lll/nfs",
        "--rw=readwrite", "--bs=64k", "--size=100M", "--numjobs=1",
        "--time_based", "--runtime=10", "--group_reporting", "--output-format=json"
    ]
    try:
        result = subprocess.run(fio_cmd, capture_output=True, text=True, timeout=20)
        print(result.stdout)  # debug
        import json
        output = json.loads(result.stdout)
        bw_kb = output['jobs'][0]['read']['bw']  # bandwidth in KB/s
        iops = output['jobs'][0]['read']['iops']
        lat_ms = output['jobs'][0]['read']['clat']['mean'] / 1000.0  # convert us to ms
    except Exception as e:
        print("fio 运行失败:", e)
        return 0.0, float("inf")

    # subprocess.run(["sudo", "umount", local_mount])
    bw_kb, lat_ms = run_fio(fio_cmd)
    return round(bw_kb, 2), round(lat_ms, 2)

def run_fio(fio_cmd):
    try:
        result = subprocess.run(fio_cmd, capture_output=True, text=True, timeout=20)
        # print(result.stdout)  # debug

        output = json.loads(result.stdout)
        job = output['jobs'][0]
        rw_mode = job["job options"]["rw"]

        # 根据读写模式选择对应字段
        if rw_mode in ["read", "randread"]:
            section = job.get("read", {})
        elif rw_mode in ["write", "randwrite"]:
            section = job.get("write", {})
        elif rw_mode in ["readwrite", "rw"]:
            # 直接合并 read 和 write 的均值
            read = job.get("read", {})
            write = job.get("write", {})
            bw_kb = (read.get("bw", 0) + write.get("bw", 0)) // 2
            iops = (read.get("iops", 0) + write.get("iops", 0)) // 2
            lat_ns = (
                read.get("clat_ns", {}).get("mean", 0) +
                write.get("clat_ns", {}).get("mean", 0)
            ) // 2
            lat_ms = lat_ns / 1e6  # ns -> ms
            return bw_kb, lat_ms
        else:
            print("不支持的rw模式:", rw_mode)
            return 0.0, float("inf")

        # 如果是单纯的 read 或 write
        bw_kb = section.get("bw", 0)
        iops = section.get("iops", 0)
        lat_ns = section.get("clat_ns", {}).get("mean", 0)
        lat_ms = lat_ns / 1e6  # ns -> ms

        return bw_kb, lat_ms

    except Exception as e:
        print("fio 运行失败:", e)
        return 0.0, float("inf")

def run_all_experiments(configurations):
    results = []
    for config in configurations:
        throughput, latency = run_nfs_experiment(config)
        results.append({
            'config': config,
            'throughput': throughput,
            'latency': latency
        })
    return results

# ========== Step 3: 参数重要性评估 + 贪心选择核心参数 ==========

def compute_variance(samples):
    values = [s['throughput'] for s in samples]
    return np.var(values)

# RSD = 标准差 / 均值 × 100%
# RSD 越小，说明性能越稳定，说明解释能力越强
def compute_rsd(samples):
    values = [s['throughput'] for s in samples]
    mean = np.mean(values)
    std = np.std(values)
    return (std / mean) * 100 if mean != 0 else 0
def compute_grouped_rsd(samples, selected_params):
    if not selected_params:
        return compute_rsd(samples)

    grouped = defaultdict(list)
    for s in samples:
        key = tuple((k, s['config'][k]) for k in selected_params)
        grouped[key].append(s)

    total_rsd = 0
    total_weight = 0
    for group in grouped.values():
        if len(group) < 2:
            continue
        rsd = compute_rsd(group)
        total_rsd += rsd * len(group)
        total_weight += len(group)

    return total_rsd / total_weight if total_weight > 0 else 0

def parameter_importance(param, samples):
    full_var = compute_variance(samples)
    subgroups = defaultdict(list)
    for s in samples:
        key = s['config'][param]
        subgroups[key].append(s)
    weighted_subvar = sum((len(v)/len(samples)) * compute_variance(v) for v in subgroups.values())
    return full_var - weighted_subvar

# 这相当于在控制（固定）已选参数的情况下，测量新参数对组内剩余方差的解释能力。这样做可以捕捉交互效应：
# 如果参数 p 与已选参数 S 强相关或作用被 S 覆盖，则 p 的条件重要性会下降；反之，能补充解释组内差异的参数则得分高。
def conditional_parameter_importance(param, selected_params, samples):
    if not selected_params:
        return parameter_importance(param, samples)

    grouped = defaultdict(list)
    for s in samples:
        key = tuple((k, s['config'][k]) for k in selected_params)
        grouped[key].append(s)

    total_cpi = 0
    total_weight = 0
    for group in grouped.values():
        if len(group) > 1:
            cpi = parameter_importance(param, group)
            total_cpi += len(group) * cpi
            total_weight += len(group)

    return total_cpi / total_weight if total_weight > 0 else 0

# 一个贪心的向前选择流程，目标是用尽可能少的参数把样本按这些参数划分得“组内稳定”（即组内吞吐波动很小）。
# 当组内 RSD 足够低时，说明剩余的性能差异与未选参数关系微弱，可以停止。
def carver_select_core_parameters(samples, all_params, rsd_threshold=2):
    selected = []
    remaining = list(all_params)

    while remaining:
        importance_scores = {
            p: conditional_parameter_importance(p, selected, samples)
            for p in remaining
        }
        best_param = max(importance_scores, key=importance_scores.get)
        selected.append(best_param)
        remaining.remove(best_param)

        # current_rsd = compute_rsd(samples)
        current_rsd = compute_grouped_rsd(samples, selected)
        # for sample in samples:
        #     print(sample['config'], sample['throughput'], sample['latency'])
        print(f"Selected: {best_param:<10} | RSD: {current_rsd:.2f}%")

        # 只要 RSD 小于阈值(2%)就停止
        if current_rsd < rsd_threshold:
            break

    return selected


# ========== Main 执行流程 ==========

if __name__ == "__main__":
    print("采样参数配置...")
    configs = generate_lhs_samples(num_samples=80)

    print("执行模拟实验...")
    results = run_all_experiments(configs)

    print("计算参数重要性并贪心选择核心参数集...")
    core_params = carver_select_core_parameters(results, param_names, rsd_threshold=2.0)

    print("\n最终核心参数列表(重要性降序):")
    for i, p in enumerate(core_params):
        print(f"  {i+1}. {p}")
