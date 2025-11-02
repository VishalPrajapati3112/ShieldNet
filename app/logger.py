import logging
import os

def setup_logging(app):
    log_folder = os.path.join(app.root_path, 'logs')
    os.makedirs(log_folder, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_folder, 'app.log'))
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
