import logging
from datetime import datetime

def setup_recorder(log_file):
    """Sets up a logger to log to a file."""
    logger = logging.getLogger('anomaly_detection_recorder')
    logger.setLevel(logging.INFO)
    
    # Avoid adding multiple handlers if the logger is already configured
    if not logger.handlers:
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

def record(logger, anomaly_file, data_file, last_line):
    """
    Records information about a detection run.
    """
    log_message = (
        f"Detection run complete. "
        f"Data file: '{data_file}', "
        f"processed from line: {last_line}. "
        f"Anomalies written to: '{anomaly_file}'."
    )
    logger.info(log_message)

if __name__ == '__main__':
    # Example Usage
    test_logger = setup_recorder('test_anomaly.log')
    record(test_logger, 'anomalies.csv', 'dummy_data.csv', 0)
    record(test_logger, 'anomalies.csv', 'dummy_data.csv', 20)
    print("Check 'test_anomaly.log' for output.") 