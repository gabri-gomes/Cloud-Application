from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
#from dask.distributed import Client, LocalCluster
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
from kubernetes import client, config
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, text
from flask_login import current_user
from flask import Flask, request, jsonify, render_template
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user



app = Flask(__name__)
CORS(app)
app.secret_key = 'uma_chave_muito_secreta_e_aleatoria' 

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'SQLALCHEMY_DATABASE_URI',
    'sqlite:///mycloud.db'
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['JOB_FOLDER'] = 'jobs'
STORAGE_LIMIT_BYTES = 100 * 1024 * 1024  # 100MB por usuário

db = SQLAlchemy(app)


PG_ADMIN_URL = os.getenv(
    "PG_ADMIN_URL",
    "postgresql://admin:admin@postgres:5432/postgres"
)
admin_engine = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modelos
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    storage_limit = db.Column(db.Integer, default=100 * 1024 * 1024)
    user = db.relationship('User', backref=db.backref('containers', lazy=True))


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
        login_user(user)   # ← aqui chamamos o Flask-Login para criar a sessão
        return jsonify({'message': 'Login bem-sucedido', 'redirect': '/dashboard'}), 200
    else:
        return jsonify({'message': 'Credenciais inválidas'}), 401
    

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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
    # Em vez de usar caminho relativo, monte o absoluto:
    host_job_folder = os.path.join(os.getcwd(), app.config['JOB_FOLDER'], safe_username)
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


@app.route('/databases', methods=['POST'])
def create_database():
    """
    Cria nova base de dados para o usuário autenticado.
    JSON esperado: { "dbname": "<nome>", "encoding": "<encod>" (opcional) }
    """
    if not current_user.is_authenticated:
        return jsonify({'error': 'Autenticação requerida'}), 401

    data = request.get_json() or {}
    nome_base = (data.get('dbname') or "").strip()
    encoding  = (data.get('encoding') or "UTF8").strip()

    if not nome_base:
        return jsonify({'error': 'dbname obrigatório'}), 400

    # Gera nome seguro e único
    safe = "".join(ch for ch in nome_base if ch.isalnum() or ch == '_').lower()
    user_id = current_user.id
    db_real = f"user_{user_id}_{safe}"

    # Verifica se já existe
    check = text("SELECT 1 FROM pg_database WHERE datname = :d")
    if admin_engine.execute(check, {'d': db_real}).fetchone():
        return jsonify({'error': 'Base já existe'}), 409

    try:
        create = text(f"CREATE DATABASE {db_real} ENCODING '{encoding}';")
        admin_engine.execute(create)
    except Exception as e:
        return jsonify({'error': f"Falhou ao criar base: {str(e)}"}), 500

    return jsonify({'message':'Base criada','database': db_real}), 201

@app.route('/databases', methods=['GET'])
def list_databases():
    """
    Retorna JSON com lista de bases criadas pelo usuário atual.
    """
    if not current_user.is_authenticated:
        return jsonify({'error': 'Autenticação requerida'}), 401

    prefix = f"user_{current_user.id}_"
    qry = text("SELECT datname FROM pg_database WHERE datname LIKE :p")
    rows = admin_engine.execute(qry, {'p': f"{prefix}%"}).fetchall()
    nomes = [r['datname'] for r in rows]
    return jsonify({'databases': nomes})


@app.route('/databases-ui', methods=['GET'])
def databases_ui():
    """
    Rota que entrega a interface HTML para o usuário ver e criar databases.
    """
    if not current_user.is_authenticated:
        # Se não estiver logado, redireciona (ou retorna 401, conforme sua lógica)
        return jsonify({'error': 'Autenticação requerida'}), 401

    return render_template('databases.html')

@app.route('/db-query', methods=['POST'])
@login_required
def db_query():
    """
    Recebe JSON: { "dbname": "<nome_da_base>", "sql": "<comando SQL>" }
    -> Verifica se current_user é dono de <nome_da_base>, executa lá dentro.
    Se for SELECT, retorna array de objetos; caso contrário, retorna mensagem ou rowcount.
    """
    data = request.get_json() or {}
    dbname = data.get('dbname', '').strip()
    sql_query = data.get('sql', '').strip()

    if not dbname:
        return jsonify({'error': 'dbname é obrigatório'}), 400
    if not sql_query:
        return jsonify({'error': 'SQL é obrigatório'}), 400

    # 1) Confere prefixo para garantir que é uma base do usuário atual
    prefixo = f"user_{current_user.id}_"
    if not dbname.startswith(prefixo):
        return jsonify({'error': 'Você não tem permissão para acessar essa base'}), 403

    # Use as variáveis que o Kubernetes define para o serviço postgres:
    pg_user = os.getenv("POSTGRES_USER", "admin")
    pg_pass = os.getenv("POSTGRES_PASSWORD", "admin")

    # Estas duas garantem que só peguemos o IP e a porta, sem o "tcp://"
    pg_host = os.getenv("POSTGRES_PORT_5432_TCP_ADDR", "postgres")
    pg_port = os.getenv("POSTGRES_PORT_5432_TCP_PORT", "5432")

    uri = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{dbname}"
    try:
        engine = create_engine(uri)
        with engine.connect() as conn:
            lower = sql_query.strip().lower()
            if lower.startswith("select") or lower.startswith("show") or lower.startswith("with"):
                result = conn.execute(text(sql_query))
                rows = [dict(row) for row in result.fetchall()]
                return jsonify({'rows': rows}), 200
            else:
                result = conn.execute(text(sql_query))
                conn.commit()
                try:
                    count = result.rowcount
                except:
                    count = None
                return jsonify({
                    'message': 'Comando executado com sucesso',
                    'rowcount': count
                }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['JOB_FOLDER'], exist_ok=True)
    print(f"[DEBUG] Pasta de uploads disponível em: {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    print(f"[DEBUG] Pasta de jobs disponível em: {os.path.abspath(app.config['JOB_FOLDER'])}")
    app.run(host='0.0.0.0', port=5000)