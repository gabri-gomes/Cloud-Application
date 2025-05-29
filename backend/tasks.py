import os
from celery import Celery
from executor_client import run_job

# Inicializa o Celery com o Redis como broker
app = Celery('worker', broker='redis://redis:6379/0')

@app.task
def execute_script(job_id: str, script_path: str, input_path: str, language: str):
    """
    Executa o script via HTTP no executor e grava
    o output em /app/jobs/<username>/<job_id>.out.txt
    """
    # Prepara ficheiros multipart para o executor
    files = {
        'file': (os.path.basename(script_path), open(script_path, 'rb'))
    }
    if input_path:
        files['input'] = (os.path.basename(input_path), open(input_path, 'rb'))

    # Dados adicionais (inclui job_id caso o executor use)
    data = {'language': language, 'job_id': job_id}
    response = run_job(files=files, data=data)
    output = response.json().get('output', '') if response.ok else f"❌ {response.status_code}: {response.text}"

    # Define o path de output usando o job_id como nome
    dirpath = os.path.dirname(script_path)
    out_filename = f"{job_id}.out.txt"
    out_path = os.path.join(dirpath, out_filename)

    # Grava o output no ficheiro corretamente nomeado
    with open(out_path, 'w') as f:
        f.write(output)

    return {'job_id': job_id, 'output_path': out_path}
