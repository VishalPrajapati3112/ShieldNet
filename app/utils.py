import os
from werkzeug.utils import secure_filename

def save_uploaded_file(file, upload_folder):
    filename = secure_filename(file.filename)
    path = os.path.join(upload_folder, filename)
    file.save(path)
    return filename, path

def get_user_uploads(upload_folder):
    if not os.path.exists(upload_folder):
        return []
    return os.listdir(upload_folder)
