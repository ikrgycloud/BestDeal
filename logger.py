import os
from datetime import datetime

LOG_FILE = os.path.join(os.path.dirname(__file__), 'log.txt')

def log(message, level='INFO'):
    timestamp = datetime.now().isoformat()
    log_entry = f'[{timestamp}] [{level}] {message}\n'
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f'Failed to write log: {e}')

def info(msg):
    log(msg, 'INFO')

def warn(msg):
    log(msg, 'WARN')

def error(msg):
    log(msg, 'ERROR')
