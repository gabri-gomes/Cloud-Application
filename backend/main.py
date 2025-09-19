import os
import shutil
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, request, jsonify, send_from_directory, render_template,
    redirect, url_for, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from sqlalchemy import create_engine, text
import docker

# ==================================================
# 1) Tentar importar execute_script de tasks.py
#    Se não existir, criamos um stub que não faz nada.
# ==================================================
try:
    from tasks import execute_script
except ImportError:
    class DummyTask:
        @staticmethod
        def delay(*args, **kwargs):
            return
    execute_script = DummyTask

# --------------------
# Configurações Iniciais
# --------------------
app = Flask(__name__)
CORS(app)

app.secret_key = 'uma_chave_muito_secreta_e_aleatoria'

# Banco de dados principal (SQLite por padrão)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'SQLALCHEMY_DATABASE_URI', 'sqlite:///mycloud.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Diretórios
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['JOB_FOLDER']    = 'jobs'
app.config['CONTAINER_FOLDER'] = 'containers'

# Limite de armazenamento padrão (100 MB / usuário)
STORAGE_LIMIT_BYTES = 100 * 1024 * 1024

# Criar pastas iniciais se não existirem
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['JOB_FOLDER'], exist_ok=True)
os.makedirs(app.config['CONTAINER_FOLDER'], exist_ok=True)

# Instância do SQLAlchemy
db = SQLAlchemy(app)

# PostgreSQL Admin (para criar/drop de bancos pelo usuário)
PG_ADMIN_URL = os.getenv(
    "PG_ADMIN_URL", "postgresql://admin:admin@postgres:5432/postgres"
)
admin_engine = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

# Docker Client (global)
docker_client = docker.DockerClient(base_url='unix://var/run/docker.sock')

# --------------------
# Modelos
# --------------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password      = db.Column(db.String(120), nullable=False)
    storage_limit = db.Column(db.Integer, default=STORAGE_LIMIT_BYTES)

class Container(db.Model):
    __tablename__ = 'containers'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    image_name      = db.Column(db.String(128), nullable=False)
    container_name  = db.Column(db.String(128), nullable=False)
    run_command     = db.Column(db.String(256), nullable=True)
    status          = db.Column(db.String(32), nullable=False, default="PENDING")
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('containers', lazy=True))

# Bundles pré-construídos
AVAILABLE_IMAGES = [
    {'tag': 'python:3.9-slim', 'description': 'Python 3.9-Slim'},
    {'tag': 'datasci:latest',   'description': 'Data Science (Jupyter, Pandas, Seaborn)'},
    {'tag': 'ml:latest',        'description': 'Machine Learning (TensorFlow, PyTorch)'}
]


# Criar tabelas (se ainda não existirem)
with app.app_context():
    db.create_all()

# --------------------
# Loader do Flask-Login
# --------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --------------------
# Rotas de Autenticação
# --------------------
@app.route('/')
def index():
    # Faz serve de um index.html que contém formulário de login/registro
    return send_from_directory('templates', 'index.html')

@app.route('/app.js')
def serve_js():
    # Serve o script front-end de dentro da raiz do projeto
    return send_from_directory('.', 'app.js')

@app.route('/register', methods=['POST'])
def register():
    data = request.json or {}
    username = secure_filename(data.get('username', '').strip())
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'message': 'Username e password são obrigatórios.'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Usuário já existe.'}), 409

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    # Criar diretórios do usuário: uploads, jobs e containers
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], username), exist_ok=True)
    os.makedirs(os.path.join(app.config['JOB_FOLDER'], username), exist_ok=True)
    os.makedirs(os.path.join(app.config['CONTAINER_FOLDER'], username), exist_ok=True)

    return jsonify({'message': 'Usuário registrado com sucesso!'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password, password):
        login_user(user)
        return jsonify({'message': 'Login bem-sucedido', 'redirect': '/dashboard'}), 200
    else:
        return jsonify({'message': 'Credenciais inválidas'}), 401

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')

# --------------------
# Dashboard
# --------------------
@app.route('/dashboard')
@login_required
def dashboard():
    containers = Container.query \
        .filter_by(user_id=current_user.id) \
        .order_by(Container.created_at.desc()) \
        .all()

    return render_template(
        'dashboard.html',
        containers=containers,
        available_images=AVAILABLE_IMAGES
    )

# --------------------
# Upload / Listagem / Download de Arquivos
# --------------------
@app.route('/upload', methods=['POST'])
def upload_file():
    username = request.form.get('username', '').strip()
    if not username:
        return jsonify({'message': 'Usuário não especificado.'}), 400

    if 'file' not in request.files:
        return jsonify({'message': 'Nenhum arquivo encontrado.'}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'message': 'Usuário não encontrado.'}), 404

    file = request.files['file']
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
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
        return jsonify({'message': 'Limite de armazenamento excedido.'}), 403

    file.save(os.path.join(user_folder, secure_filename(file.filename)))
    return jsonify({'message': 'Arquivo enviado com sucesso.'}), 200

@app.route('/files/<username>')
def list_files(username):
    safe_username = secure_filename(username)
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], safe_username)
    if not os.path.exists(user_folder):
        return jsonify({'message': 'Usuário não encontrado.'}), 404
    return jsonify(os.listdir(user_folder))

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
    total = 0
    if os.path.exists(user_folder):
        total = sum(
            os.path.getsize(os.path.join(root, f))
            for root, _, files in os.walk(user_folder)
            for f in files
        )
    return jsonify({'used': total, 'limit': user.storage_limit})

# --------------------
# Apagar Todos os Usuários / Diretórios
# --------------------
@app.route('/delete-all-users', methods=['DELETE'])
def delete_all_users():
    db.session.query(User).delete()
    db.session.commit()

    shutil.rmtree(app.config['UPLOAD_FOLDER'], ignore_errors=True)
    shutil.rmtree(app.config['JOB_FOLDER'], ignore_errors=True)
    shutil.rmtree(app.config['CONTAINER_FOLDER'], ignore_errors=True)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['JOB_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CONTAINER_FOLDER'], exist_ok=True)

    return jsonify({'message': 'Todos os usuários, uploads, jobs e containers foram apagados.'})

# --------------------
# Submissão de Jobs de Script
# --------------------
@app.route('/submit-job', methods=['POST'])
def submit_job():
    username   = request.form.get('username', '').strip()
    job_file   = request.files.get('job')
    input_file = request.files.get('input')

    if not username or not job_file:
        return jsonify({'message': 'Dados insuficientes.'}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'message': 'Usuário não encontrado.'}), 404

    host_job_folder = os.path.join(os.getcwd(), app.config['JOB_FOLDER'], username)
    os.makedirs(host_job_folder, exist_ok=True)

    original_filename = secure_filename(job_file.filename)
    script_path       = os.path.join(host_job_folder, original_filename)
    job_file.save(script_path)

    input_path = None
    if input_file:
        input_path = os.path.join(host_job_folder, secure_filename(input_file.filename))
        input_file.save(input_path)

    _, ext = os.path.splitext(original_filename)
    ext = ext.lower()
    supported_languages = {
        '.py':   'python',
        '.cpp':  'cpp',
        '.js':   'js',
        '.rs':   'rust',
        '.java':'java'
    }
    if ext not in supported_languages:
        return jsonify({'message': f'Extensão {ext} não suportada.'}), 400
    language = supported_languages[ext]

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
    username = request.args.get('username', '').strip()
    job_id   = request.args.get('job_id', '').strip()
    if not username or not job_id:
        return jsonify({'message':'username e job_id são obrigatórios.'}), 400

    user_folder = os.path.join(app.config['JOB_FOLDER'], username)
    if not os.path.isdir(user_folder):
        return jsonify({'message':'Usuário não encontrado.'}), 404

    for fname in os.listdir(user_folder):
        if fname.startswith(job_id) and fname.endswith('.out.txt'):
            path = os.path.join(user_folder, fname)
            with open(path, 'r') as f:
                output = f.read()
            return jsonify({'job_id': job_id, 'output': output}), 200

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

# --------------------
# Excluir Arquivos de Upload
# --------------------
@app.route('/delete-file', methods=['POST'])
def delete_file():
    data     = request.json or {}
    username = secure_filename(data.get('username', '').strip())
    filename = secure_filename(data.get('filename', '').strip())

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], username, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({'message': f'Arquivo {filename} apagado.'}), 200
    return jsonify({'message': 'Arquivo não encontrado.'}), 404

@app.route('/delete-all-files', methods=['POST'])
def delete_all_files():
    data     = request.json or {}
    username = secure_filename(data.get('username', '').strip())
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], username)
    if os.path.exists(user_folder):
        shutil.rmtree(user_folder)
        os.makedirs(user_folder, exist_ok=True)
        return jsonify({'message': 'Todos os arquivos foram apagados.'}), 200
    return jsonify({'message': 'Diretório não encontrado.'}), 404

# --------------------
# Atualizar Nome de Usuário e Plano de Armazenamento
# --------------------
@app.route("/update-username", methods=["POST"])
def update_username():
    data         = request.json or {}
    old_username = secure_filename(data.get("oldUsername", '').strip())
    new_username = secure_filename(data.get("newUsername", '').strip())

    user = User.query.filter_by(username=old_username).first()
    if not user:
        return jsonify({"message": "Usuário não encontrado.", "success": False})

    if User.query.filter_by(username=new_username).first():
        return jsonify({"message": "Novo nome de usuário já está em uso.", "success": False})

    old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_username)
    new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_username)
    if os.path.exists(old_path):
        os.rename(old_path, new_path)

    old_job = os.path.join(app.config['JOB_FOLDER'], old_username)
    new_job = os.path.join(app.config['JOB_FOLDER'], new_username)
    if os.path.exists(old_job):
        os.rename(old_job, new_job)

    old_cont = os.path.join(app.config['CONTAINER_FOLDER'], old_username)
    new_cont = os.path.join(app.config['CONTAINER_FOLDER'], new_username)
    if os.path.exists(old_cont):
        os.rename(old_cont, new_cont)

    user.username = new_username
    db.session.commit()
    return jsonify({"message": "Nome de usuário atualizado com sucesso.", "success": True})

@app.route("/update-password", methods=["POST"])
def update_password():
    data         = request.json or {}
    username     = secure_filename(data.get("username", '').strip())
    old_password = data.get("oldPassword", '').strip()
    new_password = data.get("newPassword", '').strip()

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, old_password):
        return jsonify({"message": "Credenciais incorretas.", "success": False})

    user.password = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({"message": "Palavra-passe atualizada com sucesso.", "success": True})

@app.route("/update-plan", methods=["POST"])
def update_plan():
    data     = request.json or {}
    username = secure_filename(data.get("username", '').strip())
    limit_mb = data.get("limit")
    try:
        limit = int(limit_mb) * 1024 * 1024
    except:
        return jsonify({"message": "Valor de limite inválido."}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"message": "Usuário não encontrado.", "success": False})

    user.storage_limit = limit
    db.session.commit()
    return jsonify({"message": f"Plano atualizado para {limit // (1024*1024)}MB.", "success": True})

# --------------------
# Gerenciamento de Bancos de Dados PostgreSQL
# --------------------
@app.route('/databases', methods=['POST'])
def create_database():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Autenticação requerida'}), 401

    data      = request.get_json() or {}
    nome_base = (data.get('dbname') or '').strip()
    encoding  = (data.get('encoding') or 'UTF8').strip()

    if not nome_base:
        return jsonify({'error': 'dbname obrigatório'}), 400

    safe = "".join(ch for ch in nome_base if ch.isalnum() or ch == '_').lower()
    user_id = current_user.id
    db_real = f"user_{user_id}_{safe}"

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
    if not current_user.is_authenticated:
        return jsonify({'error': 'Autenticação requerida'}), 401

    prefix = f"user_{current_user.id}_"
    qry    = text("SELECT datname FROM pg_database WHERE datname LIKE :p")
    rows   = admin_engine.execute(qry, {'p': f"{prefix}%"}).fetchall()
    nomes  = [r['datname'] for r in rows]
    return jsonify({'databases': nomes})

@app.route('/databases-ui', methods=['GET'])
def databases_ui():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Autenticação requerida'}), 401
    return render_template('databases.html')

@app.route('/db-query', methods=['POST'])
@login_required
def db_query():
    data     = request.get_json() or {}
    dbname   = (data.get('dbname') or '').strip()
    sql_query = (data.get('sql') or '').strip()

    if not dbname:
        return jsonify({'error': 'dbname é obrigatório'}), 400
    if not sql_query:
        return jsonify({'error': 'SQL é obrigatório'}), 400

    prefixo = f"user_{current_user.id}_"
    if not dbname.startswith(prefixo):
        return jsonify({'error': 'Você não tem permissão para acessar essa base'}), 403

    pg_user = os.getenv("POSTGRES_USER", "admin")
    pg_pass = os.getenv("POSTGRES_PASSWORD", "admin")
    pg_host = os.getenv("POSTGRES_PORT_5432_TCP_ADDR", "postgres")
    pg_port = os.getenv("POSTGRES_PORT_5432_TCP_PORT", "5432")

    uri = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{dbname}"
    try:
        engine = create_engine(uri)
        with engine.connect() as conn:
            lower = sql_query.strip().lower()
            if lower.startswith(("select", "show", "with")):
                result = conn.execute(text(sql_query))
                rows = [dict(row) for row in result.fetchall()]
                return jsonify({'rows': rows}), 200
            else:
                result = conn.execute(text(sql_query))
                conn.commit()
                count = None
                try:
                    count = result.rowcount
                except:
                    pass
                return jsonify({
                    'message': 'Comando executado com sucesso',
                    'rowcount': count
                }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# --------------------
# Container (embutido no Dashboard)
# --------------------
@app.route('/containers/create', methods=['GET', 'POST'])
@login_required
def create_container():
    if request.method == 'POST':
        image_tag   = request.form.get('image_tag', '').strip()
        run_command = request.form.get('run_command', '').strip()

        if not image_tag:
            flash('Tens de selecionar uma imagem.', 'warning')
            return redirect(request.url)
        if not run_command:
            flash('Tens de indicar o comando a executar.', 'warning')
            return redirect(request.url)

        container_id   = uuid.uuid4().hex
        container_name = f"{current_user.username}_{container_id}".lower()

        user_folder   = os.path.join(app.config['CONTAINER_FOLDER'], current_user.username)
        os.makedirs(user_folder, exist_ok=True)
        container_dir = os.path.join(user_folder, container_id)
        os.makedirs(container_dir, exist_ok=True)

        user_file = request.files.get('user_file')
        bind_src  = None
        if user_file and user_file.filename:
            bind_src = os.path.join(container_dir, secure_filename(user_file.filename))
            user_file.save(bind_src)

        novo = Container(
            user_id=current_user.id,
            image_name=image_tag,
            container_name=container_name,
            run_command=run_command,
            status='BUILDING'
        )
        db.session.add(novo)
        db.session.commit()

        try:
            # 1) Garantir que a imagem existe (fazer pull se necessário)
            try:
                docker_client.images.get(image_tag)
            except docker.errors.ImageNotFound:
                docker_client.images.pull(image_tag)

            # 2) Configurar volumes (se enviou arquivo)
            volumes = {}
            if bind_src:
                container_path = f"/app/input/{os.path.basename(bind_src)}"
                volumes[bind_src] = {'bind': container_path, 'mode': 'ro'}

            # 3) Executar container em modo destacável
            docker_client.containers.run(
                image=image_tag,
                name=container_name,
                command=run_command.split(),
                detach=True,
                volumes=volumes,
                tty=True
            )

            # 4) Atualizar status para RUNNING
            novo.status = 'RUNNING'
            db.session.commit()
            flash('Container criado e iniciado com sucesso.', 'success')
        except Exception as e:
            novo.status = 'ERROR'
            db.session.commit()
            flash(f'Erro ao criar container: {e}', 'danger')

        return redirect(url_for('dashboard'))

    # GET: renderizar formulário de criação
    return render_template('create_container.html', available_images=AVAILABLE_IMAGES)

@app.route('/containers/<int:container_id>/stop', methods=['POST'])
@login_required
def stop_container(container_id):
    c = Container.query.filter_by(id=container_id, user_id=current_user.id).first_or_404()
    try:
        docker_c = docker_client.containers.get(c.container_name)
        docker_c.stop()
        c.status = 'STOPPED'
        db.session.commit()
        flash(f'Container {c.container_name} parado.', 'success')
    except docker.errors.NotFound:
        c.status = 'DELETED'
        db.session.commit()
        flash('Container não encontrado; marcado como DELETED.', 'warning')
    except Exception as e:
        c.status = 'ERROR'
        db.session.commit()
        flash(f'Erro ao parar container: {e}', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/containers/<int:container_id>/run', methods=['POST'])
@login_required
def run_container_again(container_id):
    c = Container.query.filter_by(id=container_id, user_id=current_user.id).first_or_404()
    try:
        # 1) Remover container antigo, se existir
        try:
            old = docker_client.containers.get(c.container_name)
            if old.status == 'running':
                old.stop()
            old.remove()
        except docker.errors.NotFound:
            pass

        # 2) Configurar volumes novamente (se arquivo ainda estiver em disco)
        volumes = {}
        user_folder = os.path.join(
            app.config['CONTAINER_FOLDER'], current_user.username, str(c.id)
        )
        if os.path.isdir(user_folder):
            files = os.listdir(user_folder)
            if files:
                bind_src = os.path.join(user_folder, files[0])
                container_path = f"/app/input/{os.path.basename(bind_src)}"
                volumes[bind_src] = {'bind': container_path, 'mode': 'ro'}

        # 3) Rodar container novamente
        docker_client.containers.run(
            image=c.image_name,
            name=c.container_name,
            command=c.run_command.split(),
            detach=True,
            volumes=volumes,
            tty=True
        )

        c.status = 'RUNNING'
        db.session.commit()
        flash(f'Container {c.container_name} iniciado novamente.', 'success')
    except Exception as e:
        c.status = 'ERROR'
        db.session.commit()
        flash(f'Erro ao rodar container: {e}', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/containers/<int:container_id>/delete', methods=['POST'])
@login_required
def delete_container(container_id):
    c = Container.query.filter_by(id=container_id, user_id=current_user.id).first_or_404()
    try:
        docker_c = docker_client.containers.get(c.container_name)
        if docker_c.status == 'running':
            docker_c.stop()
        docker_c.remove()
        c.status = 'DELETED'
        db.session.commit()
        flash(f'Container {c.container_name} removido.', 'success')
    except docker.errors.NotFound:
        c.status = 'DELETED'
        db.session.commit()
        flash('Container já não existia; marcado como eliminado.', 'info')
    except Exception as e:
        c.status = 'ERROR'
        db.session.commit()
        flash(f'Erro ao eliminar container: {e}', 'danger')
    return redirect(url_for('dashboard'))

# --------------------
# Rotas Adicionais (ex.: build-image, run-job, run-container API, etc.)
# --------------------
@app.route("/run-job", methods=["POST"])
def run_job_api():
    dados  = request.json or {}
    imagem = dados.get("imagem", "ubuntu:20.04")
    cmd    = dados.get("cmd", ["echo", "Olá"])
    cid    = docker_client.containers.run(
        image=imagem,
        command=cmd,
        volumes={"/tmp/jobs": {"bind": "/jobs", "mode": "rw"}},
        detach=True
    )
    return jsonify({"container_id": cid.id}), 201

@app.route("/run-container", methods=["POST"])
@login_required
def run_container_api():
    data    = request.get_json() or {}
    imagem  = data.get("image", "").strip()
    nome    = secure_filename(data.get("name", "").strip())
    cmd_str = data.get("command", "").strip()

    if not imagem or not nome or not cmd_str:
        return jsonify({"message": "image, name e command são obrigatórios"}), 400

    username       = current_user.username
    container_name = f"{username}_{nome}"
    comando        = cmd_str.split()

    host_base = os.path.join(os.getcwd(), app.config['JOB_FOLDER'], username, "containers", nome)
    os.makedirs(host_base, exist_ok=True)
    volumes = {
        f"{host_base}": {
            "bind": "/workspace",
            "mode": "rw"
        }
    }

    try:
        container = docker_client.containers.run(
            image=imagem,
            name=container_name,
            command=comando,
            volumes=volumes,
            detach=True
        )
        return jsonify({
            "container_id": container.id,
            "name":         container.name,
            "status":       container.status
        }), 201
    except docker.errors.APIError as e:
        return jsonify({"message": f"Erro ao criar container: {str(e)}"}), 500

@app.route("/list-containers", methods=["GET"])
@login_required
def list_containers_api():
    username = current_user.username
    prefixo  = f"{username}_"
    todos    = docker_client.containers.list(all=True, filters={"name": prefixo})
    resultado = []
    for c in todos:
        resultado.append({
            "id":     c.id,
            "name":   c.name,
            "status": c.status
        })
    return jsonify(resultado)

@app.route("/stop-container", methods=["POST"])
@login_required
def stop_container_api():
    data = request.get_json() or {}
    nome = secure_filename(data.get("name", "").strip())
    if not nome:
        return jsonify({"message": "name é obrigatório"}), 400

    username       = current_user.username
    container_name = f"{username}_{nome}"
    try:
        cont = docker_client.containers.get(container_name)
        cont.stop()
        return jsonify({"message": f"Container {container_name} parado."}), 200
    except docker.errors.NotFound:
        return jsonify({"message": "Container não encontrado."}), 404
    except Exception as e:
        return jsonify({"message": f"Erro ao parar container: {str(e)}"}), 500

@app.route("/remove-container", methods=["DELETE"])
@login_required
def remove_container_api():
    data = request.get_json() or {}
    nome = secure_filename(data.get("name", "").strip())
    if not nome:
        return jsonify({"message": "name é obrigatório"}), 400

    username       = current_user.username
    container_name = f"{username}_{nome}"
    try:
        cont = docker_client.containers.get(container_name)
        cont.remove(force=True)
        return jsonify({"message": f"Container {container_name} removido."}), 200
    except docker.errors.NotFound:
        return jsonify({"message": "Container não encontrado."}), 404
    except Exception as e:
        return jsonify({"message": f"Erro ao remover container: {str(e)}"}), 500

@app.route("/build-image", methods=["POST"])
@login_required
def build_image():
    data = request.get_json() or {}
    df_text    = data.get("dockerfile", "").strip()
    image_name = data.get("image_name", "").strip()
    tag        = data.get("tag", "latest").strip()

    if not df_text or not image_name:
        return jsonify({"message": "dockerfile e image_name são obrigatórios"}), 400

    username  = current_user.username
    build_id  = str(uuid.uuid4())[:8]
    build_path = os.path.join(os.getcwd(), "dockerbuilds", username, build_id)
    os.makedirs(build_path, exist_ok=True)

    dockerfile_path = os.path.join(build_path, "Dockerfile")
    with open(dockerfile_path, "w") as f:
        f.write(df_text)

    full_image_tag = f"{username}_{image_name}:{tag}"

    try:
        image_obj, build_logs = docker_client.images.build(
            path=build_path,
            tag=full_image_tag,
            rm=True,
            forcerm=True
        )
        return jsonify({
            "image": full_image_tag,
            "build_status": "sucesso"
        }), 201
    except docker.errors.BuildError as be:
        return jsonify({"message": f"Erro no build: {str(be)}"}), 500
    except docker.errors.APIError as ae:
        return jsonify({"message": f"Erro na API Docker: {str(ae)}"}), 500

# --------------------
# Execução (main)
# --------------------
if __name__ == '__main__':
    print(f"[DEBUG] Pasta de uploads:     {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    print(f"[DEBUG] Pasta de jobs:        {os.path.abspath(app.config['JOB_FOLDER'])}")
    print(f"[DEBUG] Pasta de containers:  {os.path.abspath(app.config['CONTAINER_FOLDER'])}")
    app.run(host='0.0.0.0', port=5000)
