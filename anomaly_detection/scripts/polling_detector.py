import os
import sys
import json
import argparse
import pandas as pd
import time
import signal
import threading
from collections import defaultdict

# # Add project root to path to allow imports
# sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from model.detect import detect
from model import EWMAControlThreeSigmaDetector
from detector.detect import detect as JumpStarterDetect

# Global flag for graceful shutdown
shutdown_event = threading.Event()

def get_file_line_count(filepath):
    """Counts the number of lines in a file."""
    if not os.path.exists(filepath):
        return 0
    with open(filepath, 'r') as f:
        return sum(1 for line in f)

def create_model_for_algorithm(algorithm_name):
    """Create a model instance for the specified algorithm."""
    if algorithm_name == "adaptive-3-sigma":
        return EWMAControlThreeSigmaDetector(sigma_multiplier=3.0, window_size=50, alpha=0.1, auto_optimize=True)
    elif algorithm_name == "jumpstarter":
        return None  # JumpStarterDetect is a function, not a model object
    else:
        return None

def process_files(mapping_data, output_file, processed_lines, models):
    """Process all files for anomaly detection."""
    total_anomalies = 0
    
    for data_file, algorithm_name in mapping_data.items():
        # Check for shutdown signal
        if shutdown_event.is_set():
            print("Shutdown signal received, stopping processing...")
            break
            
        if not os.path.exists(data_file):
            print(f"Warning: Data file not found, skipping: {data_file}")
            continue

        print(f"\nProcessing '{data_file}' with '{algorithm_name}'...")
        
        anomalies_before = get_file_line_count(output_file)
        last_line = processed_lines.get(data_file, 0)

        if algorithm_name == "EWMAControlThreeSigmaDetector":
            model = models.get(data_file)
            if model:
                # The 'detect' from scripts.detect takes a model object
                detect(model, data_file, output_file, data_file, last_line=last_line)
            else:
                print(f"Warning: Model for '{algorithm_name}' not found. Skipping.")
                continue
        elif algorithm_name == "jumpstarter":
            jumpstarter_detect_func = JumpStarterDetect
            if jumpstarter_detect_func:
                # This is a direct call to the detection function
                jumpstarter_detect_func(data_path=data_file, output_path=output_file, metric_name=data_file, last_line=last_line)
            else:
                print(f"Warning: Function for '{algorithm_name}' not found. Skipping.")
                continue
        else:
            print(f"Warning: Unknown algorithm '{algorithm_name}' for file '{data_file}'. Skipping.")
            continue
        
        # Update processed lines count
        try:
            df = pd.read_csv(data_file)
            processed_lines[data_file] = len(df)
        except Exception as e:
            print(f"Warning: Could not update processed lines for {data_file}: {e}")
        
        anomalies_after = get_file_line_count(output_file)

        newly_detected = anomalies_after - anomalies_before
        if newly_detected > 0:
            print(f"  -> Found and wrote {newly_detected} anomalies.")
            total_anomalies += newly_detected
        else:
            print("  -> No anomalies found.")
    
    return total_anomalies

def process_file_worker(data_file, algorithm_name, output_file, model, polling_interval, processed_lines):
    """Worker function for processing a single file in a separate thread."""
    print(f"Started monitoring thread for {data_file}")
    
    while not shutdown_event.is_set():
        try:
            print(f"\n[{data_file}] Processing iteration...")
            
            if not os.path.exists(data_file):
                print(f"[{data_file}] Warning: Data file not found, skipping...")
                # Sleep with frequent checks for shutdown
                for _ in range(polling_interval):
                    if shutdown_event.is_set():
                        return
                    time.sleep(0.5)
                continue

            anomalies_before = get_file_line_count(output_file)
            last_line = processed_lines.get(data_file, 0)

            if algorithm_name == "EWMAControlThreeSigmaDetector":
                if model:
                    detect(model, data_file, output_file, data_file, last_line=last_line)
                else:
                    print(f"[{data_file}] Warning: Model not found. Skipping.")
                    for _ in range(polling_interval):
                        if shutdown_event.is_set():
                            return
                        time.sleep(0.5)
                    continue
            elif algorithm_name == "jumpstarter":
                jumpstarter_detect_func = JumpStarterDetect
                if jumpstarter_detect_func:
                    jumpstarter_detect_func(data_path=data_file, output_path=output_file, metric_name=data_file, last_line=last_line)
                else:
                    print(f"[{data_file}] Warning: Function not found. Skipping.")
                    for _ in range(polling_interval):
                        if shutdown_event.is_set():
                            return
                        time.sleep(0.5)
                    continue
            
            # Update processed lines count
            try:
                df = pd.read_csv(data_file)
                processed_lines[data_file] = len(df)
            except Exception as e:
                print(f"[{data_file}] Warning: Could not update processed lines: {e}")
            
            anomalies_after = get_file_line_count(output_file)
            newly_detected = anomalies_after - anomalies_before
            
            if newly_detected > 0:
                print(f"[{data_file}] Found and wrote {newly_detected} anomalies.")
            else:
                print(f"[{data_file}] No new anomalies found.")
            
            # Sleep with frequent checks for shutdown signal (every 0.5 seconds)
            for _ in range(polling_interval * 2):
                if shutdown_event.is_set():
                    return
                time.sleep(0.5)
                
        except Exception as e:
            print(f"[{data_file}] Error in processing: {e}")
            for _ in range(polling_interval):
                if shutdown_event.is_set():
                    return
                time.sleep(0.5)
    
    print(f"[{data_file}] Monitoring thread stopped.")

def signal_handler(signum, frame):
    """Handle interrupt signals."""
    print(f"\nReceived signal {signum}. Initiating graceful shutdown...")
    shutdown_event.set()
    # Force exit after 3 seconds if threads don't stop
    def force_exit():
        time.sleep(3)
        print("Force exiting...")
        os._exit(1)
    
    force_thread = threading.Thread(target=force_exit, daemon=True)
    force_thread.start()

def main():
    parser = argparse.ArgumentParser(description="Run anomaly detection on a set of files with polling.")
    parser.add_argument("--mapping_file", type=str, 
                        default="anomaly_detection/scripts/algorithm_mapping.json",
                        help="Path to the algorithm mapping JSON file.")
    parser.add_argument("--anomaly_file", type=str, default="anomalies.csv",
                        help="Path to the file to save all anomalies.")
    parser.add_argument("--polling_interval", type=int, default=30,
                        help="Polling interval in seconds (default: 30).")
    parser.add_argument("--run_once", action="store_true",
                        help="Run detection once and exit (no polling).")
    parser.add_argument("--log-dir", default="traceOutput/op",
                        help="Directory to read trace logs from.")
    parser.add_argument("--output-dir", default="nfs_output/op_latency/",
                        help="Directory to write latency CSVs to.")
    parser.add_argument("--state-file", default="anomaly_detection/op_latency_analyzer_state.json",
                        help="Path to the state file for the analyzer.")
    parser.add_argument("--mapping-file", default="anomaly_detection/nfs_op_algorithm_mapping.json",
                        help="Path to the algorithm mapping file to update.")
    args = parser.parse_args()

    # Load the algorithm mapping
    try:
        with open(args.mapping_file, 'r') as f:
            mapping_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading mapping file '{args.mapping_file}': {e}")
        sys.exit(1)
        
    # Clear previous anomaly file if it exists
    if os.path.exists(args.anomaly_file):
        os.remove(args.anomaly_file)
    
    # Clear all files in output directory if it exists
    output_dir = os.path.dirname(args.output_file)
    if os.path.exists(output_dir):
        print(f"Clearing all files in output directory: {output_dir}")
        for file in os.listdir(output_dir):
            file_path = os.path.join(output_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"Removed: {file_path}")

    print(f"Starting anomaly detection for {len(mapping_data)} files...")
    print(f"Anomalies will be saved to '{args.anomaly_file}'.")
    if not args.run_once:
        print(f"Polling interval: {args.polling_interval} seconds")
    else:
        print("Running once (no polling)")

    # Create model instances for each file
    models = {}
    for data_file, algorithm_name in mapping_data.items():
        if algorithm_name == "EWMAControlThreeSigmaDetector":
            models[data_file] = create_model_for_algorithm(algorithm_name)
            print(f"Created {algorithm_name} model for {data_file}")
        elif algorithm_name == "jumpstarter":
            models[data_file] = None  # JumpStarterDetect is a function
            print(f"Using {algorithm_name} function for {data_file}")

    # Track processed lines for each file
    processed_lines = defaultdict(int)
    
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}. Force exiting immediately...")
        os._exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.run_once:
        # 单次运行模式
        total_anomalies = process_files(mapping_data, args.output_file, processed_lines, models)
        print(f"\nAnomaly detection complete. Total anomalies found: {total_anomalies}.")
    else:
        # 持续监控模式
        threads = []
        
        try:
            # 创建工作线程
            for data_file, algorithm_name in mapping_data.items():
                model = models.get(data_file)
                thread = threading.Thread(
                    target=process_file_worker,
                    args=(data_file, algorithm_name, args.anomaly_file, model, args.polling_interval, processed_lines),
                    daemon=True  # 设置为守护线程
                )
                threads.append(thread)
                thread.start()
            
            print(f"Started {len(threads)} monitoring threads (daemon mode).")
            print("Press Ctrl+C to exit immediately.")
            
            # 主线程永久等待（直到被信号中断）
            while True:
                time.sleep(3600)  # 长时间休眠等待中断
                
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            os._exit(1)

if __name__ == '__main__':
    main() 