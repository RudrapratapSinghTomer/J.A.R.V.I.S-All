import os
import time
import psutil
import logging
from datetime import datetime

# Setup logging to a file in the data directory
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "system_monitor.log")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

class SystemMonitor:
    """
    Background monitor for Jarvis 8.0 to ensure proactive system awareness.
    """
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True
        logging.info("Jarvis System Monitor started.")
        print("[Monitor] System awareness loop initiated. Logging to data/system_monitor.log")
        
        try:
            while self.running:
                cpu = psutil.cpu_percent(interval=1)
                mem = psutil.virtual_memory().percent
                disk = psutil.disk_usage("/").percent
                
                status = f"CPU: {cpu}% | RAM: {mem}% | Disk: {disk}%"
                logging.info(status)
                
                # Proactive check: High resource usage
                if cpu > 90 or mem > 90:
                    logging.warning(f"High resource usage detected! {status}")
                
                time.sleep(60) # Check every minute
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.running = False
        logging.info("Jarvis System Monitor stopped.")

if __name__ == "__main__":
    monitor = SystemMonitor()
    monitor.start()
