import subprocess
import time
import json
from skopt import gp_minimize
from skopt.space import Categorical
from skopt.utils import use_named_args
from collections import OrderedDict
import resource


# ========== 参数空间 ==========
param_space = OrderedDict({
    'rsize': [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576],
    'wsize': [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576],
    'timeo': [10, 30, 70, 100, 200],
    'actimeo': [0, 1, 5, 25, 60, 120],
    'acregmin': [0, 3, 5],
    'acregmax': [30, 60, 120],
    'acdirmin': [0, 3, 5],
    'acdirmax': [30, 60, 120]
})

# ========== 挂载参数拼接 ==========
def generate_mount_opts(config):
    opts = [
        f"rsize={config['rsize']}",
        f"wsize={config['wsize']}",
        f"timeo={config['timeo']}",
        f"actimeo={config['actimeo']}",
        f"acregmin={config['acregmin']}",
        f"acregmax={config['acregmax']}",
        f"acdirmin={config['acdirmin']}",
        f"acdirmax={config['acdirmax']}",
        "hard", "sync", "rw", "fg"
    ]
    return ",".join(opts)
# 贝叶斯优化实现默认只会去最小化目标函数返回值
# 最大化score=最小化-score
def calculate_score(read_bw, read_lat, write_bw, write_lat,read_prop=0.5):
    if throughput == 0 or latency == float('inf'):
        return -1e6  # 极低分处理失败配置
    alpha = throughput / (latency * 10 + 1e-6)  # 自适应惩罚权重
    score = read_bw * read_prop + write_bw * (1 - read_prop)  - alpha*(read_lat * read_prop + write_lat * (1 - read_prop))
    return -score

# ========== fio 测试函数 ==========
def run_nfs_experiment(config):
    server_ip = "10.249.9.153"
    remote_dir = "/data/nfs4"
    local_mount = "/home/lll/nfs"
    # mount_opts = generate_mount_opts(config)

    # subprocess.run(["sudo", "umount", local_mount], stderr=subprocess.DEVNULL)
    # mount_cmd = ["sudo", "mount", "-t", "nfs", "-o", mount_opts, f"{server_ip}:{remote_dir}", local_mount]
    
    if config is None:
        # 默认挂载，无额外参数
        mount_cmd = ["sudo", "mount", "-t", "nfs", f"{server_ip}:{remote_dir}", local_mount]
    else:
        # 根据配置构建挂载命令
        mount_opts = generate_mount_opts(config)
        subprocess.run(["sudo", "umount", local_mount], stderr=subprocess.DEVNULL)
        mount_cmd = ["sudo", "mount", "-t", "nfs", "-o", mount_opts, f"{server_ip}:{remote_dir}", local_mount]
    
    try:
        subprocess.check_call(mount_cmd)
    except subprocess.CalledProcessError:
        print("挂载失败，跳过该配置")
        return 0.0, float("inf")

    fio_cmd = [
        "sudo", "fio", "--name=test", f"--directory=/home/lll/nfs",
        "--rw=readwrite", "--bs=64k", "--size=8M", "--numjobs=32", "--rwmixread=50",
        "--direct=1",  "--output-format=json"
    ] # fileserver


    try:
        result = subprocess.run(fio_cmd, capture_output=True, text=True, timeout=200)

        if result.stdout.strip():
            output = json.loads(result.stdout)
            print("FIO JSON 解析成功！")

            num = len(output['jobs'])

            total_read_bw = 0
            total_write_bw = 0
            total_read_lat_ns = 0
            total_write_lat_ns = 0

            for i in range(num):
                job = output['jobs'][i]
                read = job.get('read', {})
                write = job.get('write', {})

                read_bw = read.get('bw', 0)
                write_bw = write.get('bw', 0)
                read_lat = read.get('lat_ns', {}).get('mean', 0)
                write_lat = write.get('lat_ns', {}).get('mean', 0)

                total_read_bw += read_bw
                total_write_bw += write_bw
                total_read_lat_ns += read_lat
                total_write_lat_ns += write_lat

            # 平均值
            avg_read_bw = total_read_bw / num
            avg_write_bw = total_write_bw / num
            avg_read_lat_ms = total_read_lat_ns / num / 1e6  # ns → ms
            avg_write_lat_ms = total_write_lat_ns / num / 1e6
        else:
            print("FIO 输出为空，无法解析为 JSON。")
            bw_kb = 0
            lat_ms = float("inf")

    except json.JSONDecodeError as e:
        print("FIO 输出非 JSON 格式，解析失败：", e)
        bw_kb = 0
        lat_ms = float("inf")

    except subprocess.TimeoutExpired:
        print("FIO 执行超时。")
        bw_kb = 0
        lat_ms = float("inf")

    except Exception as e:
        print("FIO 运行失败:", e)
        bw_kb = 0
        lat_ms = float("inf")

    finally:
        subprocess.run(["sudo", "umount", local_mount], stderr=subprocess.DEVNULL)

    # 返回值
    # return round(bw_kb, 2), round(lat_ms, 2)
    return avg_read_bw, avg_read_lat_ms, avg_write_bw, avg_write_lat_ms

# ========== 优化器维度 ==========
dimensions = [Categorical(v, name=k) for k, v in param_space.items()]

# ========== 默认参数测试 ==========
def run_default_config():
    print("运行默认挂载配置下的基准测试...")
    read_bw, read_lat, write_bw, write_lat = run_nfs_experiment(config=None)
    # score = (read_bw + write_bw) / 2 - ALPHA_LATENCY * (read_lat + write_lat) / 2
    score = calculate_score(read_bw=read_bw, read_lat=read_lat, write_bw=write_bw, write_lat=write_lat)
    print(f"默认配置:  读吞吐量: {read_bw} KB/s, 写吞吐量: {write_bw} KB/s, 读延迟: {read_lat:.2f} ms, 写延时: {write_lat:.2f} ms, 综合得分: {score:.2f}")

# ========== 目标函数 ==========
@use_named_args(dimensions)
def objective(**params):
    # throughput, latency = run_nfs_experiment(params)
    read_bw, read_lat, write_bw, write_lat = run_nfs_experiment(params)
    score = calculate_score(read_bw=read_bw, read_lat=read_lat, write_bw=write_bw, write_lat=write_lat)
    print(f"配置: {params}, 读吞吐量: {read_bw} KB/s, 写吞吐量: {write_bw} KB/s, 读延迟: {read_lat:.2f} ms, 写延时: {write_lat:.2f} ms, 综合得分: {score:.2f}")
    return -score  # gp_minimize 是最小化器，我们希望 score 最大，因此取负

# ========== 主函数 ==========
def main():
    print(resource.getrlimit(resource.RLIMIT_NOFILE))
    run_default_config()
    print("开始自动优化参数...\n")
    res = gp_minimize(
        func=objective,
        dimensions=dimensions,
        acq_func="EI",
        n_calls=100,
        n_random_starts=10,
        random_state=42
    )

    print("\n最优配置:")
    for name, value in zip(param_space.keys(), res.x):
        print(f"  {name}: {value}")
    print(f"最优综合得分: {-res.fun:.2f}")

if __name__ == "__main__":
    main()
