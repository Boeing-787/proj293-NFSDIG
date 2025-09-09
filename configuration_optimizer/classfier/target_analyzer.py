import time
import pandas as pd
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess
import threading
from pathlib import Path
from collections import defaultdict

csv_path = "/home/lll/nfsdig/output/nfs/nfs_2025-06-10-10-29-11.csv"
baseline_window = 10
after_window = 30
top_k = 10

# 定义 9 种 FIO 测试配置
fio_scenarios = [
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=1M", "--size=128M", "--numjobs=32", "--direct=1", "--time_based", "--runtime=40", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=1M", "--size=128M", "--numjobs=16", "--direct=1", "--time_based", "--runtime=40", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=1M", "--size=128M", "--numjobs=4", "--direct=1", "--time_based", "--runtime=40", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=64k", "--size=8M", "--numjobs=32", "--direct=1", "--time_based", "--runtime=40", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=64k", "--size=8M", "--numjobs=16", "--direct=1", "--time_based", "--runtime=40", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=64k", "--size=8M", "--numjobs=4", "--direct=1", "--time_based", "--runtime=40", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=4k",  "--size=512k", "--numjobs=32", "--direct=1", "--time_based", "--runtime=60", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=4k",  "--size=512k", "--numjobs=16", "--direct=1", "--time_based", "--runtime=60", "--group_reporting", "--output-format=json"],
    ["fio", "--name=test", "--directory=/home/lll/nfs", "--rw=readwrite", "--bs=4k",  "--size=512k", "--numjobs=4",  "--direct=1", "--time_based", "--runtime=60", "--group_reporting", "--output-format=json"]
]


class DriftAnalyzer:
    def __init__(self):
        self.baseline_data = []
        self.after_data = []
        self.results = []   # 保存所有测试的指标变化率
        self.lock = threading.Lock()    # 线程安全
        self.triggered = threading.Event()
        self.current_index = 0  # 当前测试次数
        self.max_runs = 6 * 5   # 最大允许运行次数（防溢出）
        # 配置NFS挂载路径
        self.server_ip = "10.249.9.153"
        self.remote_dir = "/data/nfs4"
        self.local_mount = "/home/lll/nfs"

    def mount_nfs(self):
        subprocess.run(["sudo", "umount", self.local_mount], stderr=subprocess.DEVNULL)
        mount_cmd = ["sudo", "mount", "-t", "nfs", f"{self.server_ip}:{self.remote_dir}", self.local_mount]
        try:
            subprocess.check_call(mount_cmd)
            return True
        except subprocess.CalledProcessError:
            print("挂载失败，跳过该测试！！！")
            return False

    def umount_nfs(self):
        subprocess.run(["sudo", "umount", self.local_mount], stderr=subprocess.DEVNULL)

    def run_fio(self, cmd):
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        except Exception:
            print("FIO 测试失败")

    def process_csv(self):
        df = pd.read_csv(csv_path)
        if df.empty or len(df) < (baseline_window + after_window + 1):
            return None, None

        baseline = df.iloc[-(baseline_window + after_window):-after_window]
        after = df.iloc[-after_window:]

        df_base = baseline.drop(columns=["timestamp"], errors='ignore')
        df_after = after.drop(columns=["timestamp"], errors='ignore')

        mean_base = df_base.mean()
        mean_after = df_after.mean()

        delta = ((mean_after - mean_base).abs()) / (mean_base.abs() + 1e-6)
        return delta

    def run_test_once(self, scenario_index):
        if self.current_index >= self.max_runs:
            return

        print(f"[第 {self.current_index + 1} 次测试] 运行场景 {scenario_index + 1} 的 FIO...")

        time.sleep(1)  # 收集 baseline 前静置
        baseline = pd.read_csv(csv_path).iloc[-baseline_window:].to_dict(orient="records")

        self.run_fio(fio_scenarios[scenario_index])
        time.sleep(after_window + 1)  # 等待采样

        delta = self.process_csv()
        if delta is not None:
            with self.lock:
                self.results.append(delta)

        self.current_index += 1

    def run_all(self):
        print("挂载 NFS...")
        if not self.mount_nfs():
            print("NFS 挂载失败，无法执行测试!!!")
            return
        for i in range(9):
            for j in range(3):
                self.run_test_once(i)
            time.sleep(20)  # 避免相邻干扰    

        self.umount_nfs()
        print("卸载 NFS 挂载点")

        # 汇总所有 drift
        self.aggregate_results()

    def aggregate_results(self):
        print("\n=== 综合分析测试中最具变化的指标 ===")
        if not self.results:
            print("无有效结果")
            return

        all_df = pd.concat(self.results, axis=1).fillna(0)
        mean_delta = all_df.mean(axis=1)
        top_metrics = mean_delta.sort_values(ascending=False).head(top_k)

        for i, (metric, val) in enumerate(top_metrics.items(), 1):
            print(f"{i:>2}. {metric:<30} 变动率: {val*100:.4f}")

if __name__ == "__main__":
    print("开始执行 9 种场景、共 27 次 FIO 测试...")
    analyzer = DriftAnalyzer()
    analyzer.run_all()
