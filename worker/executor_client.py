import requests
import os

EXECUTOR_URL = os.environ.get("EXECUTOR_URL", "http://executor:8000/execute")

def run_job(files: dict, data: dict, timeout: int = 30):
    """
    files: dict para multipart/form-data (script e input)
    data: dict com language, job_id, etc.
    """
    return requests.post(EXECUTOR_URL, files=files, data=data, timeout=timeout)
