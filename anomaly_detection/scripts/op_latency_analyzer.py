import os
import pandas as pd
from collections import Counter
import glob
import json
import time
import argparse

BATCH_SIZE = 3
BUSY_THRESHOLD_SECONDS = 5.0

def load_state(state_file, default_log_dir):
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass # Fallback to default if file is corrupt
    # Initialize with a dummy file that is older than any real log file
    return {'last_processed_file': os.path.join(default_log_dir, '0'), 'last_processed_line': 0}

def save_state(state, state_file):
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=4)

def update_mapping_file(new_filepath, mapping_file):
    """Adds a new file path to the mapping JSON if it's not already there."""
    try:
        if os.path.exists(mapping_file) and os.path.getsize(mapping_file) > 0:
            with open(mapping_file, 'r') as f:
                mapping = json.load(f)
        else:
            mapping = {}
    except json.JSONDecodeError:
        mapping = {}

    if new_filepath not in mapping:
        mapping[new_filepath] = "EWMAControlThreeSigmaDetector"
        with open(mapping_file, 'w') as f:
            json.dump(mapping, f, indent=4)
        # print(f"Registered new operation for analysis: {new_filepath}")

def process_log_file(filepath, start_line, output_dir, mapping_file):
    try:
        # A more robust way to read the CSV: read the whole file with its header,
        # then slice the dataframe to get only the new rows.
        # This is simpler and avoids errors with header/data type mismatches.
        df = pd.read_csv(filepath, header=0)
        new_rows_df = df.iloc[start_line:]

        if new_rows_df.empty:
            return start_line
            
    except Exception as e:
        # Catch potential errors during file read, like file being empty or locked
        # print(f"DEBUG: Could not read {filepath}: {e}")
        return start_line

    new_lines_processed = 0
    # Process the new rows in batches
    for i in range(0, len(new_rows_df), BATCH_SIZE):
        batch = new_rows_df.iloc[i:i+BATCH_SIZE]
        if len(batch) < BATCH_SIZE:
            continue
        
        first_timestamp_ns = batch.iloc[0]['Timestamp']
        last_timestamp_ns = batch.iloc[-1]['Timestamp']
        time_delta_seconds = (last_timestamp_ns - first_timestamp_ns) / 1e9

        if time_delta_seconds < BUSY_THRESHOLD_SECONDS:
            op_counts = Counter(batch['OP_TYPE'])
            top_3_ops = op_counts.most_common(BATCH_SIZE)

            for op_name, _ in top_3_ops:
                # Select Timestamp, Latency, and Pid columns for context
                op_data = batch[batch['OP_TYPE'] == op_name][['Timestamp', 'Pid', 'Latency(us)']]
                
                # Rename 'Latency(us)' to 'latency' for consistency and compatibility
                op_data = op_data.rename(columns={'Latency(us)': 'latency'})
                
                os.makedirs(output_dir, exist_ok=True)
                output_filepath = os.path.join(output_dir, f"{op_name}.csv")

                is_new_file = not os.path.exists(output_filepath)
                # Write the three-column dataframe (Timestamp, latency, Pid)
                op_data.to_csv(output_filepath, mode='a', header=is_new_file, index=False)
                
                update_mapping_file(output_filepath, mapping_file)

        new_lines_processed += len(batch)

    return start_line + new_lines_processed

def main():
    parser = argparse.ArgumentParser(description="Analyze NFS OP logs for latency anomalies during busy periods.")
    parser.add_argument("--log-dir", default="traceOutput/op",
                        help="Directory to read trace logs from.")
    parser.add_argument("--output-dir", default="nfs_output/op_latency/",
                        help="Directory to write latency CSVs to.")
    parser.add_argument("--state-file", default="anomaly_detection/scripts/op_latency_analyzer_state.json",
                        help="Path to the state file for the analyzer.")
    parser.add_argument("--mapping-file", default="anomaly_detection/scripts/nfs_op_algorithm_mapping.json",
                        help="Path to the algorithm mapping file to update.")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    
    state = load_state(args.state_file, args.log_dir)
    
    log_files = sorted(glob.glob(os.path.join(args.log_dir, '*.log')))
    if not log_files:
        return

    # More robust logic for finding where to start processing.
    # If the last processed file no longer exists, start from the beginning.
    start_index = 0
    if state['last_processed_file'] in log_files:
        try:
            start_index = log_files.index(state['last_processed_file'])
        except ValueError:
            # This case handles if the file disappears between glob and index call
            pass
    
    for i in range(start_index, len(log_files)):
        log_file = log_files[i]
        
        # Determine the line to start from
        line_to_process = 0
        if log_file == state['last_processed_file']:
            # If it's the same file we processed last, continue from where we left off
            line_to_process = state['last_processed_line']
        
        # Process the file
        lines_processed = process_log_file(log_file, line_to_process, args.output_dir, args.mapping_file)
        
        # Update state
        state['last_processed_file'] = log_file
        state['last_processed_line'] = lines_processed
    
    save_state(state, args.state_file)

if __name__ == "__main__":
    main() 