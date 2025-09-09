import os
import sys
import json
import argparse
import pandas as pd
import subprocess
import time

# Add project root to allow imports from other directories
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from model.detect import detect
from model import EWMAControlThreeSigmaDetector

STATE_FILE = "anomaly_detection/scripts/nfs_op_polling_state.json"

def get_file_line_count(filepath):
    """Counts the number of lines in a file."""
    if not os.path.exists(filepath):
        return 0
    # Efficiently count lines
    with open(filepath, 'rb') as f:
        return sum(1 for _ in f)

def load_state():
    """Loads the last processed line number for each file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} # Handle empty or corrupt state file
    return {}

def save_state(state):
    """Saves the last processed line number for each file."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def main():
    parser = argparse.ArgumentParser(description="Run NFS-OP anomaly detection in a continuous polling loop.")
    parser.add_argument("--mapping_file", type=str, 
                        default="anomaly_detection/scripts/nfs_op_algorithm_mapping.json",
                        help="Path to the NFS-OP algorithm mapping JSON file.")
    parser.add_argument("--log-dir", default="traceOutput/op",
                        help="Directory to read trace logs from. Can be set to mock directory for testing.")
    parser.add_argument("--anomaly_file", type=str, default="nfs_op_anomalies.csv",
                        help="Path to the file to save NFS-OP anomalies.")
    parser.add_argument("--nfs_output_dir", default="nfs_output/op_latency/",
                        help="Directory to read latency CSVs from.")
    parser.add_argument("--poll_interval", type=int, default=10,
                        help="Interval in seconds between polling for new data.")
    args = parser.parse_args()

    # --- Initial Cleanup ---
    # Clear previous anomaly file if starting fresh
    if os.path.exists(args.anomaly_file):
        print(f"Clearing previous anomaly file: {args.anomaly_file}")
        os.remove(args.anomaly_file)
    # Clear state file to ensure a fresh start
    if os.path.exists(STATE_FILE):
        print(f"Clearing previous state file: {STATE_FILE}")
        os.remove(STATE_FILE)
    # Clear mapping file to ensure a fresh start
    if os.path.exists(args.mapping_file):
        print(f"Clearing previous mapping file: {args.mapping_file}")
        os.remove(args.mapping_file)
    
    # Clear all files in output directory if it exists
    nfs_output_dir = os.path.dirname(args.nfs_output_dir)
    if os.path.exists(nfs_output_dir):
        print(f"Clearing all files in output directory: {nfs_output_dir}")
        for file in os.listdir(nfs_output_dir):
            file_path = os.path.join(nfs_output_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"Removed: {file_path}")

    print(f"Starting NFS-OP anomaly detection polling loop every {args.poll_interval} seconds...")
    print(f"Anomalies will be saved to '{args.anomaly_file}'. Press Ctrl+C to stop.")

    # 存储每个文件的模型实例
    models = {}
    # 存储每个文件的状态（最后处理的行数）
    processing_state = {}

    while True:
        # --- 1. Run the log analyzer to process new op data ---
        try:
            command = ['python3', 'anomaly_detection/op_latency_analyzer.py']
            subprocess.run(command, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error running op_latency_analyzer.py: {e}. Skipping this cycle.")
            time.sleep(args.poll_interval)
            continue

        # --- 2. Load the (potentially updated) algorithm mapping ---
        try:
            if not os.path.exists(args.mapping_file) or os.path.getsize(args.mapping_file) == 0:
                time.sleep(args.poll_interval)
                continue
            with open(args.mapping_file, 'r') as f:
                mapping_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error loading mapping file '{args.mapping_file}': {e}. Skipping this cycle.")
            time.sleep(args.poll_interval)
            continue
        
        # --- 3. 清理不再存在的文件模型 ---
        current_files = set(mapping_data.keys())
        # 从models字典中移除不再存在于mapping_data中的文件
        for file_path in list(models.keys()):
            if file_path not in current_files:
                # print(f"Removing model for discontinued file: {file_path}")
                del models[file_path]
                if file_path in processing_state:
                    del processing_state[file_path]
        
        # --- 4. 处理每个文件 ---
        total_anomalies_in_cycle = 0
        files_processed = 0

        for data_file, algorithm_name in mapping_data.items():
            if not os.path.exists(data_file):
                print(f"File not found, skipping: {data_file}")
                continue
                
            # 获取或创建模型实例
            if data_file not in models:
                # print(f"Creating new model for: {data_file}")
                if algorithm_name == "EWMAControlThreeSigmaDetector":
                    models[data_file] = EWMAControlThreeSigmaDetector(
                        sigma_multiplier=3.0, 
                        window_size=50, 
                        alpha=0.1, 
                        data_pre_required=200,
                        auto_optimize=True
                    )
                else:
                    print(f"Unsupported algorithm '{algorithm_name}' for file '{data_file}'. Skipping.")
                    continue
            
            # 获取最后处理的行数
            last_line = processing_state.get(data_file, 0)
            current_line_count = get_file_line_count(data_file)
            
            # 如果没有新数据，跳过处理
            if current_line_count <= last_line:
                # print(f"No new data for {data_file}, skipping.")
                continue
                
            # 使用特定文件的模型进行处理
            model = models[data_file]
            
            if algorithm_name == "EWMAControlThreeSigmaDetector":
                # 调用检测函数
                detect(model, data_file, args.anomaly_file, data_file, has_pid=1, last_line=last_line)
                
                # 更新状态
                processing_state[data_file] = current_line_count
                files_processed += 1
                
                # 检查是否有新异常（可选）
                # 这里可以根据需要添加异常检测的逻辑
            else:
                print(f"Warning: Unknown algorithm '{algorithm_name}' for file '{data_file}'.")
        
        # --- 5. 保存状态并等待下一个周期 ---
        save_state(processing_state)
        
        if files_processed > 0:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Processed {files_processed} files. {len(mapping_data)} total files monitored.")
        time.sleep(args.poll_interval)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nPolling stopped by user.")
        sys.exit(0)