# worker/tasks.py
import os
from celery import Celery
from executor_client import run_job

app = Celery('worker', broker='redis://redis:6379/0')

@app.task
def execute_script(job_id: str, script_path: str, input_path: str, language: str):
    # Prepara os ficheiros para enviar
    files = {'file': (os.path.basename(script_path), open(script_path, 'rb'))}
    if input_path:
        files['input'] = (os.path.basename(input_path), open(input_path, 'rb'))

    data = {'language': language, 'job_id': job_id}
    response = run_job(files=files, data=data)
    output = response.json().get('output', '') if response.ok else f"❌ {response.status_code}: {response.text}"

    out_path = script_path + ".out.txt"
    with open(out_path, 'w') as f:
        f.write(output)

    return {'job_id': job_id, 'output_path': out_path}
