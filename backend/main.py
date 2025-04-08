from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import os
import shutil

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://admin:admin@data_base:5432/my_cloud_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
STORAGE_LIMIT_BYTES = 100 * 1024 * 1024  # 100MB por usuário

db = SQLAlchemy(app)

# Modelo de usuário
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

# Criar tabelas
with app.app_context():
    db.create_all()

# Páginas estáticas
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
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], safe_username)
    os.makedirs(user_folder, exist_ok=True)

    print(f"[DEBUG] Pasta criada para o usuário em: {os.path.abspath(user_folder)}")
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

# Upload
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

    # Verificar uso atual de armazenamento
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
    files = os.listdir(user_folder)
    return jsonify(files)

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

# ❌ Apagar todos os usuários
@app.route('/delete-all-users', methods=['DELETE'])
def delete_all_users():
    # 1. Remover todos os usuários do banco
    num_deleted = db.session.query(User).delete()
    db.session.commit()

    # 2. Apagar todas as pastas de uploads
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        for folder in os.listdir(app.config['UPLOAD_FOLDER']):
            path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
            if os.path.isdir(path):
                shutil.rmtree(path)

    return jsonify({'message': f'{num_deleted} usuários e pastas apagados com sucesso.'}), 200

# Inicialização
if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    print(f"[DEBUG] Pasta de uploads disponível em: {os.path.abspath(app.config['UPLOAD_FOLDER'])}")
    app.run(host='0.0.0.0', port=5000)
