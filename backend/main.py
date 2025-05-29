from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dask.distributed import Client, LocalCluster
from tasks import execute_script
import os
import shutil
import subprocess
import uuid
import time
import requests
import zipfile
import tempfile
from flask import request, jsonify
from werkzeug.utils import secure_filename



app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mycloud.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['JOB_FOLDER'] = 'jobs'
STORAGE_LIMIT_BYTES = 100 * 1024 * 1024  # 100MB por usuário

db = SQLAlchemy(app)

# Modelos
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    storage_limit = db.Column(db.Integer, default=100 * 1024 * 1024)  # 100MB


# Criação de tabelas
with app.app_context():
    db.create_all()

# Rotas estáticas
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/app.js')
def serve_js():
    return send_from_directory('.', 'app.js')

@app.route('/dashboard')
def dashboard():
    return send_from_directory('.', 'dashboard.html')

# Registro
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = secure_filename(data.get('username'))
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username e password são obrigatórios.'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Usuário já existe.'}), 409

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    safe_username = secure_filename(username)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], safe_username), exist_ok=True)
    os.makedirs(os.path.join(app.config['JOB_FOLDER'], safe_username), exist_ok=True)

    return jsonify({'message': 'Usuário registrado com sucesso!'}), 201

# Login
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        return jsonify({'message': 'Login bem-sucedido', 'redirect': '/dashboard'}), 200
    else:
        return jsonify({'message': 'Credenciais inválidas'}), 401


# Upload de arquivo
@app.route('/upload', methods=['POST'])
def upload_file():
    username = request.form.get('username')
    if not username:
        return jsonify({'message': 'Usuário não especificado'}), 400

    if 'file' not in request.files:
        return jsonify({'message': 'Nenhum arquivo encontrado'}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'message': 'Usuário não encontrado'}), 404

    file = request.files['file']
    safe_username = secure_filename(username)
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], safe_username)
    os.makedirs(user_folder, exist_ok=True)

    total = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(user_folder)
        for f in files
    )

    file.seek(0, os.SEEK_END)
    file_length = file.tell()
    file.seek(0)

    if total + file_length > user.storage_limit:
        return jsonify({'message': 'Limite de armazenamento excedido'}), 403

    file.save(os.path.join(user_folder, file.filename))
    return jsonify({'message': 'Arquivo enviado com sucesso'}), 200

# Listar arquivos
@app.route('/files/<username>')
def list_files(username):
    safe_username = secure_filename(username)
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], safe_username)
    if not os.path.exists(user_folder):
        return jsonify({'message': 'Usuário não encontrado'}), 404
    return jsonify(os.listdir(user_folder))

# Download
@app.route('/download/<username>/<filename>')
def download_file(username, filename):
    safe_username = secure_filename(username)
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], safe_username)
    return send_from_directory(user_folder, filename, as_attachment=True)

@app.route('/usage/<username>')
def get_usage(username):
    safe_username = secure_filename(username)
    user = User.query.filter_by(username=safe_username).first()
    if not user:
        return jsonify({'used': 0, 'limit': 0})

    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], safe_username)

    total = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(user_folder)
        for f in files
    ) if os.path.exists(user_folder) else 0

    return jsonify({'used': total, 'limit': user.storage_limit})


# Apagar tudo
@app.route('/delete-all-users', methods=['DELETE'])
def delete_all_users():
    db.session.query(User).delete()
    db.session.commit()

    shutil.rmtree(app.config['UPLOAD_FOLDER'], ignore_errors=True)
    shutil.rmtree(app.config['JOB_FOLDER'], ignore_errors=True)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['JOB_FOLDER'], exist_ok=True)

    return jsonify({'message': 'Todos os usuários, uploads e jobs foram apagados com sucesso.'})


@app.route('/submit-job', methods=['POST'])
def submit_job():
    username    = request.form.get('username')
    job_file    = request.files.get('job')
    input_file  = request.files.get('input')

    if not username or not job_file:
        return jsonify({'message': 'Dados insuficientes'}), 400

    safe_username   = secure_filename(username)
    host_job_folder = os.path.join(app.config['JOB_FOLDER'], safe_username)
    os.makedirs(host_job_folder, exist_ok=True)

    original_filename = secure_filename(job_file.filename)
    script_path       = os.path.join(host_job_folder, original_filename)
    job_file.save(script_path)

    input_path = None
    if input_file:
        input_path = os.path.join(host_job_folder, secure_filename(input_file.filename))
        input_file.save(input_path)

    # valida extensão
    _, ext = os.path.splitext(original_filename)
    ext = ext.lower()
    supported_languages = {'.py':'python', '.cpp':'cpp', '.js':'js', '.rs':'rust', '.java':'java'}
    if ext not in supported_languages:
        return jsonify({'message': f'Extensão {ext} não suportada.'}), 400
    language = supported_languages[ext]

    # gera ID e enfileira no Celery
    job_id = str(uuid.uuid4())
    execute_script.delay(
        job_id=job_id,
        script_path=script_path,
        input_path=input_path,
        language=language
    )

    return jsonify({
        'message': 'Job enfileirado com sucesso!',
        'job_id': job_id,
        'status': 'queued'
    }), 202

@app.route('/job-result', methods=['GET'])
def job_result():
    """
    Endpoint para o cliente consultar o output de um job enfileirado.
    Parâmetros:
      - username (query param)
      - job_id   (query param)
    Retorna:
      - 200 + {'job_id', 'output'} quando o .out.txt existir
      - 202 + {'status':'pending'} enquanto não existir
      - 400 em parâmetros em falta
    """
    username = request.args.get('username')
    job_id   = request.args.get('job_id')
    if not username or not job_id:
        return jsonify({'message':'username e job_id são obrigatórios'}), 400

    safe_user = secure_filename(username)
    user_folder = os.path.join(app.config['JOB_FOLDER'], safe_user)
    if not os.path.isdir(user_folder):
        return jsonify({'message':'usuário não encontrado'}), 404

    # Procura qualquer ficheiro <job_id>*.out.txt
    for fname in os.listdir(user_folder):
        if fname.startswith(job_id) and fname.endswith('.out.txt'):
            path = os.path.join(user_folder, fname)
            with open(path, 'r') as f:
                output = f.read()
            return jsonify({'job_id': job_id, 'output': output}), 200

    # Se chegar aqui, o worker ainda não gravou o .out.txt
    return jsonify({'status':'pending'}), 202

@app.route('/jobs/<username>')
def list_jobs(username):
    user_job_folder = os.path.join(app.config['JOB_FOLDER'], secure_filename(username))
    results = []

    if os.path.exists(user_job_folder):
        for fname in os.listdir(user_job_folder):
            if fname.endswith(".out.txt"):
                job_name = fname.replace(".py.out.txt", ".py")
                with open(os.path.join(user_job_folder, fname)) as f:
                    results.append({
                        "job": job_name,
                        "output": f.read()
                    })

    return jsonify(results)

# Apagar ficheiro específico
@app.route('/delete-file', methods=['POST'])
def delete_file():
    data = request.json
    username = secure_filename(data.get('username'))
    filename = secure_filename(data.get('filename'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], username, filename)

    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({'message': f'Arquivo {filename} apagado.'}), 200
    return jsonify({'message': 'Arquivo não encontrado'}), 404

# Apagar todos os ficheiros do utilizador
@app.route('/delete-all-files', methods=['POST'])
def delete_all_files():
    data = request.json
    username = secure_filename(data.get('username'))
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)

    if os.path.exists(user_folder):
        shutil.rmtree(user_folder)
        os.makedirs(user_folder, exist_ok=True)
        return jsonify({'message': 'Todos os arquivos foram apagados.'}), 200
    return jsonify({'message': 'Diretório não encontrado.'}), 404


@app.route("/update-username", methods=["POST"])
def update_username():
    data = request.json
    old_username = secure_filename(data.get("oldUsername"))
    new_username = secure_filename(data.get("newUsername"))

    user = User.query.filter_by(username=old_username).first()
    if not user:
        return jsonify({"message": "Usuário não encontrado.", "success": False})

    if User.query.filter_by(username=new_username).first():
        return jsonify({"message": "Novo nome de usuário já está em uso.", "success": False})

    # renomear pasta de uploads
    old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_username)
    new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_username)

    if os.path.exists(old_path):
        os.rename(old_path, new_path)
    
    # Renomear pasta de jobs
    old_job = os.path.join(app.config['JOB_FOLDER'], old_username)
    new_job = os.path.join(app.config['JOB_FOLDER'], new_username)
    if os.path.exists(old_job):
        os.rename(old_job, new_job)


    user.username = new_username
    db.session.commit()
    return jsonify({"message": "Nome de usuário atualizado com sucesso.", "success": True})


@app.route("/update-password", methods=["POST"])
def update_password():
    data = request.json
    username = secure_filename(data.get("username"))
    old_password = data.get("oldPassword")
    new_password = data.get("newPassword")

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, old_password):
        return jsonify({"message": "Credenciais incorretas."})

    user.password = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({"message": "Palavra-passe atualizada com sucesso.", "success": True})



@app.route("/update-plan", methods=["POST"])
def update_plan():
    data = request.json
    username = secure_filename(data.get("username"))
    limit = int(data.get("limit")) * 1024 * 1024  # Convert MB to bytes

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"message": "Usuário não encontrado."})

    user.storage_limit = limit
    db.session.commit()
    return jsonify({"message": f"Plano atualizado para {limit // (1024*1024)}MB."})

@app.route('/submit-dask-job', methods=['POST'])
def submit_dask_job():
    zip_file = request.files.get('zip')
    main_file = request.form.get('mainFile')
    username = secure_filename(request.form.get('username'))

    if not zip_file or not main_file or not username:
        return jsonify({"message": "Preencha todos os campos."}), 400
    try:
        # Descompactar o zip para uma pasta temporária
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, zip_file.filename)
            zip_file.save(zip_path)

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(tmpdir)

            # Criar cluster local do Dask
            cluster = LocalCluster(n_workers=2, threads_per_worker=2)
            client = Client(cluster)

            # Caminho para o ficheiro principal
            script_path = os.path.join(tmpdir, main_file)
            if not os.path.exists(script_path):
                return jsonify({"message": "Ficheiro principal não encontrado."}), 400

            # Executar o ficheiro principal
            result = subprocess.run(['python3', script_path], capture_output=True, text=True, cwd=tmpdir)

            return jsonify({
                "message": result.stdout or result.stderr or "Código executado com Dask."
            })

    except Exception as e:
        return jsonify({"message": f"Erro ao executar com Dask: {str(e)}"}), 500



if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['JOB_FOLDER'], exist_ok=True)
    print(f"[DEBUG] Pasta de uploads disponível em: {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    print(f"[DEBUG] Pasta de jobs disponível em: {os.path.abspath(app.config['JOB_FOLDER'])}")
    app.run(host='0.0.0.0', port=5000)