from anomaly_utils.stream_generator import StreamGenerator
import pandas as pd
import numpy as np
import os

def parse_metric_name(file_path):
    """
    Parse metric name from file path.
    Remove path and extension, keep only the filename.
    
    Args:
        file_path (str): Full file path
        
    Returns:
        str: Clean metric name
    """
    # Get the filename without path
    filename = os.path.basename(file_path)
    # Remove extension
    metric_name = os.path.splitext(filename)[0]
    return metric_name

def detect(model, data_path, output_path, metric_name, has_pid = 0, last_line=0):
    """
    Detect anomalies in a data file.

    Args:
        model: The anomaly detection model instance.
        data_path (str): Path to the data file (CSV).
        output_path (str): Path to write anomalies to.
        metric_name (str): Name of the metric being monitored.
        last_line (int): The last line number that was processed.
    """
    try:
        # Parse the metric name to get clean name
        clean_metric_name = parse_metric_name(metric_name)
        
        # Read new data from the file
        df = pd.read_csv(data_path, header=0, skiprows=range(1, last_line + 1))
        if df.empty:
            return

        # Assuming the first column is timestamp, second is value, third is pid (ignored for detection)
        timestamp_column = df.columns[0]
        metric_column = df.columns[1]
        if has_pid == 1:
            metric_column = df.columns[2]
        # Note: df.columns[2] would be 'Pid' but we don't use it for anomaly detection
        ds = df[metric_column].values.tolist()
        ds = np.array(ds)
        ds_nested = np.expand_dims(ds, axis=1)
        
        
        stream = StreamGenerator(ds_nested)

        anomalies = []
        for index, x in enumerate(stream.iter_item()):
            score = model.fit_score(x)
            anomaly = model.predict(score) # 0: normal, 1: anomaly
            if anomaly: 
                anomaly_timestamp = df[timestamp_column].iloc[index]
                anomaly_value = x[0]
                print(f"Anomaly detected at {anomaly_timestamp} metric: {clean_metric_name}")
                if(has_pid == 0):
                    anomalies.append(f"{anomaly_timestamp},{clean_metric_name},{anomaly_value},{score}\n")
                else:
                    anomalies.append(f"{anomaly_timestamp},{clean_metric_name},{df.iloc[index]['Pid']}, {anomaly_value},{score}\n")
        if anomalies:
            with open(output_path, 'a') as f:
                f.writelines(anomalies)
    except Exception as e:
        print(f"Error during detection: {e}")

if __name__ == '__main__':
    # Example usage for testing
    # Create a dummy csv file
    dummy_data = {'value': np.random.rand(20)}
    dummy_df = pd.DataFrame(dummy_data)
    dummy_df.iloc[10] = 10 # inject anomaly
    dummy_df.to_csv('dummy_data.csv', index=False)

    from model.spot import SpotDetector
    test_model = SpotDetector()
    detect(test_model, 'dummy_data.csv', 'anomalies.csv', 'test_metric', 0)
    detect(test_model, 'dummy_data.csv', 'anomalies.csv', 'test_metric', 15)
