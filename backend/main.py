from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
import shutil
import subprocess
import uuid
import time

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://admin:admin@data_base:5432/my_cloud_db'
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
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Username e password são obrigatórios.'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Usuário já existe.'}), 409

    new_user = User(username=username, password=password)
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

    user = User.query.filter_by(username=username, password=password).first()
    if user:
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

    file = request.files['file']
    safe_username = secure_filename(username)
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], safe_username)
    os.makedirs(user_folder, exist_ok=True)

    total = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(user_folder)
        for f in files
    )

    if total + len(file.read()) > STORAGE_LIMIT_BYTES:
        return jsonify({'message': 'Limite de armazenamento excedido'}), 403

    file.seek(0)
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

# Uso de armazenamento
@app.route('/usage/<username>')
def get_usage(username):
    safe_username = secure_filename(username)
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], safe_username)

    total = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(user_folder)
        for f in files
    ) if os.path.exists(user_folder) else 0

    return jsonify({'used': total, 'limit': STORAGE_LIMIT_BYTES})

# Apagar tudo
@app.route('/delete-all-users', methods=['DELETE'])
def delete_all_users():
    db.session.query(User).delete()
    db.session.commit()

    shutil.rmtree(app.config['UPLOAD_FOLDER'], ignore_errors=True)
    shutil.rmtree(app.config['JOB_FOLDER'], ignore_errors=True)

    # Recriar diretórios base
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['JOB_FOLDER'], exist_ok=True)

    return jsonify({'message': 'Todos os usuários, uploads e jobs foram apagados com sucesso.'})


# Submissão de job em container isolado
@app.route('/submit-job', methods=['POST'])
def submit_job():
    username = request.form.get('username')
    job_file = request.files.get('job')

    if not username or not job_file:
        return jsonify({'message': 'Dados insuficientes'}), 400

    safe_username = secure_filename(username)
    job_folder = os.path.join(app.config['JOB_FOLDER'], safe_username)
    os.makedirs(job_folder, exist_ok=True)

    original_filename = secure_filename(job_file.filename)
    script_path = os.path.join(job_folder, original_filename)
    job_file.save(script_path)

    os.sync()
    time.sleep(0.2)

    if not os.path.exists(script_path):
        return jsonify({'message': 'Erro ao guardar o script.'}), 500

    name, ext = os.path.splitext(original_filename)
    ext = ext.lower()

    output = ""
    try:
        if ext == ".py":
            cmd = ["python3", script_path]

        elif ext == ".js":
            cmd = ["node", script_path]

        elif ext == ".c":
            exe_path = os.path.join(job_folder, f"{name}_c.out")
            compile_cmd = ["gcc", script_path, "-o", exe_path]
            subprocess.run(compile_cmd, check=True)
            cmd = [exe_path]

        elif ext == ".cpp":
            exe_path = os.path.join(job_folder, f"{name}_cpp.out")
            compile_cmd = ["g++", script_path, "-o", exe_path]
            subprocess.run(compile_cmd, check=True)
            cmd = [exe_path]

        elif ext == ".rs":
            exe_path = os.path.join(job_folder, f"{name}_rs.out")
            compile_cmd = ["rustc", script_path, "-o", exe_path]
            subprocess.run(compile_cmd, check=True)
            cmd = [exe_path]

        elif ext == ".java":
            compile_cmd = ["javac", script_path]
            subprocess.run(compile_cmd, check=True)
            cmd = ["java", "-cp", job_folder, name]  # .class file is generated in same folder

        else:
            return jsonify({'message': f'Extensão {ext} não suportada'}), 400

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr

    except subprocess.CalledProcessError as e:
        output = f"❌ Erro de compilação ou execução:\n{e.stderr or str(e)}"
    except subprocess.TimeoutExpired:
        output = "❌ Tempo limite excedido durante execução do job."
    except Exception as e:
        output = f"❌ Erro inesperado: {str(e)}"

    output_path = script_path + ".out.txt"
    with open(output_path, 'w') as f:
        f.write(output)

    return jsonify({'message': 'Job executado com sucesso!', 'output': output})



# Listar jobs
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

# Inicialização
if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['JOB_FOLDER'], exist_ok=True)
    print(f"[DEBUG] Pasta de uploads disponível em: {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    print(f"[DEBUG] Pasta de jobs disponível em: {os.path.abspath(app.config['JOB_FOLDER'])}")
    app.run(host='0.0.0.0', port=5000)
