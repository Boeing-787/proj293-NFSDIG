import pandas as pd
import numpy as np
import json
import os

def determine_algorithm(data_file_path):
    """
    Determines the appropriate algorithm for a given data file based on its structure.

    Args:
        data_file_path (str): The path to the CSV data file.

    Returns:
        str: The name of the selected algorithm.
    """
    try:
        df = pd.read_csv(data_file_path)

        # Drop the timestamp column if it exists
        if 'timestamp' in df.columns:
            df = df.drop(columns=['timestamp'])

        # Identify and select only numeric columns
        numeric_cols = df.select_dtypes(include=np.number).columns.tolist()
        
        if len(numeric_cols) > 1:
            # Multi-variable case
            return "jumpstarter"
        elif len(numeric_cols) == 1:
            # Single-variable case
            column_name = numeric_cols[0]
            mean = df[column_name].mean()
            std_dev = df[column_name].std()
            
            if mean != 0:
                cv = std_dev / mean
                if cv > 0.1:
                    return "jumpstarter"
            # If mean is 0 or cv <= 0.1, fall through to default
        
        # Default for single variable with low CV or no numeric columns
        return "EWMAControlThreeSigmaDetector"

    except Exception:
        # If any error occurs during file processing, default to EWMAControlThreeSigmaDetector
        return "EWMAControlThreeSigmaDetector"

def update_algorithm_mapping(root_dirs, output_json_path):
    """
    Scans directories, determines the algorithm for each file, and updates the mapping file.

    Args:
        root_dirs (list): A list of directory paths to scan for data files.
        output_json_path (str): The path to the output JSON mapping file.
    """
    mapping_data = {}

    for root_dir in root_dirs:
        for subdir, _, files in os.walk(root_dir):
            for file in files:
                if file.endswith('.csv'):
                    data_file_path = os.path.join(subdir, file)
                    algorithm_name = determine_algorithm(data_file_path)
                    mapping_data[data_file_path] = algorithm_name
                    print(f"Processed '{data_file_path}': Selected Algorithm -> {algorithm_name}")
        
        # Write the updated dictionary back to the JSON file
        with open(output_json_path, 'w') as f:
            json.dump(mapping_data, f, indent=4)
            
    print(f"\nMapping successfully saved to '{output_json_path}'")

if __name__ == "__main__":
    # Define the directories to scan
    DIRECTORIES_TO_SCAN = ['output', 'traceOutput']
    
    # Define the JSON file to store the mapping
    MAPPING_JSON_FILE = 'anomaly_detection/scripts/algorithm_mapping.json'
    
    update_algorithm_mapping(DIRECTORIES_TO_SCAN, MAPPING_JSON_FILE) 