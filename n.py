from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
import os
import csv
from io import StringIO
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# --- Configurações Iniciais ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///corridas.db'
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui_mude_em_producao'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'} # Para corridas/blog
app.config['ALLOWED_ZIP_EXTENSIONS'] = {'zip'} # Para importação de imagens

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "warning"

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

# --- Modelos de Dados ---
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Corrida(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    data = db.Column(db.DateTime, nullable=False)
    local = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    distancia = db.Column(db.Float, nullable=False)
    imagem = db.Column(db.String(100))
    descricao = db.Column(db.Text)
    promovida = db.Column(db.Boolean, default=False) # Nova flag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_publicacao = db.Column(db.DateTime, default=datetime.utcnow)
    imagem = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Promocao(db.Model): # Novo modelo para anúncios/afiliados
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(150), nullable=False)
    link = db.Column(db.String(255), nullable=False)
    descricao = db.Column(db.Text)
    imagem = db.Column(db.String(100))
    tipo = db.Column(db.String(50), nullable=False) # 'corrida_promovida' ou 'afiliado'
    ativo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Acesso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pagina = db.Column(db.String(50), nullable=False)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    ip = db.Column(db.String(45))

# --- Callbacks do Flask-Login ---
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# --- Rotas de Autenticação ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = Usuario.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin'))
        else:
            flash('Usuário ou senha inválidos.', 'error')
            
    return render_template('admin/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('index'))

# Rota para criar o primeiro usuário admin (remover em produção real ou proteger)
@app.route('/setup_admin')
def setup_admin():
    if Usuario.query.first():
        flash('Admin já existe.', 'warning')
        return redirect(url_for('login'))
    
    admin_user = Usuario(username='admin', email='admin@exemplo.com')
    admin_user.set_password('admin_password_123') # MUDE ESTA SENHA IMEDIATAMENTE!
    db.session.add(admin_user)
    db.session.commit()
    flash('Usuário admin criado (admin/admin_password_123). Mude a senha em produção!', 'success')
    return redirect(url_for('login'))

# --- Funções Auxiliares e Before Request ---
@app.before_request
def registrar_acesso():
    if not request.path.startswith('/uploads/'):
        acesso = Acesso(
            pagina=request.endpoint or 'unknown',
            ip=request.remote_addr
        )
        db.session.add(acesso)
        db.session.commit()

def save_image(file, folder):
    if file and allowed_file(file.filename, app.config['ALLOWED_EXTENSIONS']):
        extension = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{folder}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{extension}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], folder, filename)
        file.save(file_path)
        return filename
    return None

def delete_image(filename, folder):
    if filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], folder, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

# --- Rotas de Visualização (Públicas) ---
@app.route('/')
def index():
    corridas_proximas = Corrida.query.filter(Corrida.data >= datetime.now()).order_by(Corrida.data.asc()).all()
    promocoes_ativas = Promocao.query.filter_by(ativo=True).all()
    
    # Lógica para intercalar corridas e promoções
    lista_principal = []
    
    # Adicionar as corridas promovidas (marcadas no modelo Corrida) no início
    corridas_promovidas = [c for c in corridas_proximas if c.promovida]
    corridas_nao_promovidas = [c for c in corridas_proximas if not c.promovida]
    
    lista_principal.extend(corridas_promovidas)
    
    # Intercalar corridas não promovidas com anúncios/afiliados
    idx_corrida = 0
    idx_promocao = 0
    
    # Adiciona uma promoção a cada 3 corridas (exemplo)
    while idx_corrida < len(corridas_nao_promovidas) or idx_promocao < len(promocoes_ativas):
        # Adiciona até 3 corridas
        for _ in range(3):
            if idx_corrida < len(corridas_nao_promovidas):
                lista_principal.append({'tipo': 'corrida', 'item': corridas_nao_promovidas[idx_corrida]})
                idx_corrida += 1
            else:
                break
                
        # Adiciona 1 promoção/anúncio
        if idx_promocao < len(promocoes_ativas):
            lista_principal.append({'tipo': 'promocao', 'item': promocoes_ativas[idx_promocao]})
            idx_promocao += 1
    
    # Passa a lista intercalada para o template
    return render_template('index.html', lista_principal=lista_principal)

@app.route('/corrida/<int:id>')
def corrida_detalhes(id):
    corrida = Corrida.query.get_or_404(id)
    return render_template('corrida_detalhes.html', corrida=corrida)

@app.route('/blog')
def blog():
    posts = Post.query.order_by(Post.data_publicacao.desc()).all()
    return render_template('blog/index.html', posts=posts)

@app.route('/blog/post/<int:id>')
def post_detalhes(id):
    post = Post.query.get_or_404(id)
    return render_template('blog/post.html', post=post)

@app.route('/sobre')
def sobre():
    return render_template('sobre.html')

@app.route('/termos')
def termos():
    return render_template('termos.html')

@app.route('/privacidade')
def privacidade():
    return render_template('privacidade.html')

@app.route('/uploads/corridas/<filename>')
def upload_corridas(filename):
    return send_from_directory('uploads/corridas', filename)

@app.route('/uploads/blog/<filename>')
def upload_blog(filename):
    return send_from_directory('uploads/blog', filename)

@app.route('/uploads/promocoes/<filename>')
def upload_promocoes(filename):
    return send_from_directory('uploads/promocoes', filename)


# --- Rotas de Admin (Protegidas) ---
@app.route('/admin')
@login_required
def admin():
    total_acessos = Acesso.query.count()
    total_corridas = Corrida.query.count()
    total_posts = Post.query.count()
    acessos_hoje = Acesso.query.filter(
        Acesso.data >= datetime.today().date()
    ).count()
    return render_template('admin/index.html', 
                         total_acessos=total_acessos,
                         total_corridas=total_corridas,
                         total_posts=total_posts,
                         acessos_hoje=acessos_hoje)

# --- Admin: Corridas ---
@app.route('/admin/corridas')
@login_required
def admin_corridas():
    corridas = Corrida.query.order_by(Corrida.data.asc()).all()
    return render_template('admin/corridas.html', corridas=corridas)

@app.route('/admin/corrida/nova', methods=['GET', 'POST'])
@login_required
def nova_corrida():
    if request.method == 'POST':
        try:
            promovida = request.form.get('promovida') == 'on'
            corrida = Corrida(
                nome=request.form['nome'],
                data=datetime.strptime(request.form['data'], '%Y-%m-%dT%H:%M'),
                local=request.form['local'],
                valor=float(request.form['valor']),
                distancia=float(request.form['distancia']),
                descricao=request.form['descricao'],
                promovida=promovida
            )
            
            if 'imagem' in request.files:
                file = request.files['imagem']
                filename = save_image(file, 'corridas')
                if filename:
                    corrida.imagem = filename
            
            db.session.add(corrida)
            db.session.commit()
            flash('Corrida adicionada com sucesso!', 'success')
            return redirect(url_for('admin_corridas'))
        except Exception as e:
            flash(f'Erro ao adicionar corrida: {str(e)}', 'error')
    
    return render_template('admin/nova_corrida.html')

@app.route('/admin/corrida/importar', methods=['GET', 'POST'])
@login_required
def importar_corridas():
    if request.method == 'POST':
        # 1. Processar CSV
        if 'csv' in request.files:
            file_csv = request.files['csv']
            if file_csv.filename != '' and file_csv.filename.endswith('.csv'):
                try:
                    stream = StringIO(file_csv.stream.read().decode("UTF8"), newline=None)
                    csv_reader = csv.DictReader(stream, delimiter=',')
                    corridas_adicionadas = 0
                    
                    for row in csv_reader:
                        # Adapte o formato da data se necessário, mas mantenha o '%Y-%m-%d %H:%M:%S'
                        # Adicionando um fallback simples para imagem e promovida
                        promovida_val = row.get('promovida', 'false').lower() in ('true', '1', 'on')
                        
                        corrida = Corrida(
                            nome=row['nome'],
                            data=datetime.strptime(row['data'], '%Y-%m-%d %H:%M:%S'),
                            local=row['local'],
                            valor=float(row['valor']),
                            distancia=float(row['distancia']),
                            descricao=row.get('descricao', ''),
                            imagem=row.get('imagem', None), # Assume que a imagem já foi enviada ou será enviada via ZIP
                            promovida=promovida_val
                        )
                        db.session.add(corrida)
                        corridas_adicionadas += 1
                    
                    db.session.commit()
                    flash(f'{corridas_adicionadas} corridas do CSV importadas com sucesso! (Verifique as imagens)', 'success')
                except Exception as e:
                    flash(f'Erro ao importar CSV: {str(e)}', 'error')
            else:
                flash('Por favor, envie um arquivo CSV válido', 'error')

        # 2. Processar Imagens em ZIP (apenas a lógica inicial de upload)
        if 'imagens_zip' in request.files:
            file_zip = request.files['imagens_zip']
            if file_zip.filename != '' and file_zip.filename.endswith('.zip'):
                # LÓGICA DE EXTRAÇÃO E MATCH DE IMAGENS POR NOME AQUI
                # Por exemplo: extrair para 'uploads/corridas/' e garantir que o nome da imagem
                # no CSV corresponda ao nome do arquivo no ZIP.
                flash('Arquivo ZIP enviado. A lógica de extração e associação de imagens por ZIP precisa ser implementada.', 'warning')
            elif file_zip.filename != '':
                 flash('Por favor, envie um arquivo ZIP válido para as imagens', 'error')
                 
        return redirect(url_for('admin_corridas'))
    
    return render_template('admin/importar_corridas.html')


@app.route('/admin/corrida/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_corrida(id):
    corrida = Corrida.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            promovida = request.form.get('promovida') == 'on'
            
            corrida.nome = request.form['nome']
            corrida.data = datetime.strptime(request.form['data'], '%Y-%m-%dT%H:%M')
            corrida.local = request.form['local']
            corrida.valor = float(request.form['valor'])
            corrida.distancia = float(request.form['distancia'])
            corrida.descricao = request.form['descricao']
            corrida.promovida = promovida
            
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename:
                    # Remove imagem antiga se existir
                    delete_image(corrida.imagem, 'corridas')
                    
                    filename = save_image(file, 'corridas')
                    if filename:
                        corrida.imagem = filename
            
            db.session.commit()
            flash('Corrida atualizada com sucesso!', 'success')
            return redirect(url_for('admin_corridas'))
        except Exception as e:
            flash(f'Erro ao atualizar corrida: {str(e)}', 'error')
    
    return render_template('admin/editar_corrida.html', corrida=corrida)

@app.route('/admin/corrida/excluir/<int:id>')
@login_required
def excluir_corrida(id):
    corrida = Corrida.query.get_or_404(id)
    
    try:
        delete_image(corrida.imagem, 'corridas')
        
        db.session.delete(corrida)
        db.session.commit()
        flash('Corrida excluída com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir corrida: {str(e)}', 'error')
    
    return redirect(url_for('admin_corridas'))

# --- Admin: Blog ---
@app.route('/admin/blog')
@login_required
def admin_blog():
    posts = Post.query.order_by(Post.data_publicacao.desc()).all()
    return render_template('admin/blog.html', posts=posts)

@app.route('/admin/blog/novo', methods=['GET', 'POST'])
@login_required
def novo_post():
    if request.method == 'POST':
        try:
            post = Post(
                titulo=request.form['titulo'],
                conteudo=request.form['conteudo']
            )
            
            if 'imagem' in request.files:
                file = request.files['imagem']
                filename = save_image(file, 'blog')
                if filename:
                    post.imagem = filename
            
            db.session.add(post)
            db.session.commit()
            flash('Post criado com sucesso!', 'success')
            return redirect(url_for('admin_blog'))
        except Exception as e:
            flash(f'Erro ao criar post: {str(e)}', 'error')
    
    return render_template('admin/novo_post.html')

@app.route('/admin/blog/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_post(id):
    post = Post.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            post.titulo = request.form['titulo']
            post.conteudo = request.form['conteudo']
            
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename:
                    delete_image(post.imagem, 'blog')
                    
                    filename = save_image(file, 'blog')
                    if filename:
                        post.imagem = filename
            
            db.session.commit()
            flash('Post atualizado com sucesso!', 'success')
            return redirect(url_for('admin_blog'))
        except Exception as e:
            flash(f'Erro ao atualizar post: {str(e)}', 'error')
    
    return render_template('admin/editar_post.html', post=post)

@app.route('/admin/blog/excluir/<int:id>')
@login_required
def excluir_post(id):
    post = Post.query.get_or_404(id)
    
    try:
        delete_image(post.imagem, 'blog')
        
        db.session.delete(post)
        db.session.commit()
        flash('Post excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir post: {str(e)}', 'error')
    
    return redirect(url_for('admin_blog'))


# --- Admin: Promoções e Anúncios ---
@app.route('/admin/promocoes')
@login_required
def admin_promocoes():
    promocoes = Promocao.query.order_by(Promocao.created_at.desc()).all()
    return render_template('admin/promocoes.html', promocoes=promocoes)

@app.route('/admin/promocao/nova', methods=['GET', 'POST'])
@login_required
def nova_promocao():
    if request.method == 'POST':
        try:
            ativo = request.form.get('ativo') == 'on'
            promocao = Promocao(
                titulo=request.form['titulo'],
                link=request.form['link'],
                descricao=request.form['descricao'],
                tipo=request.form['tipo'],
                ativo=ativo
            )
            
            if 'imagem' in request.files:
                file = request.files['imagem']
                filename = save_image(file, 'promocoes')
                if filename:
                    promocao.imagem = filename
            
            db.session.add(promocao)
            db.session.commit()
            flash('Promoção/Anúncio criado com sucesso!', 'success')
            return redirect(url_for('admin_promocoes'))
        except Exception as e:
            flash(f'Erro ao criar promoção/anúncio: {str(e)}', 'error')
    
    return render_template('admin/nova_promocao.html')

@app.route('/admin/promocao/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_promocao(id):
    promocao = Promocao.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            ativo = request.form.get('ativo') == 'on'
            
            promocao.titulo = request.form['titulo']
            promocao.link = request.form['link']
            promocao.descricao = request.form['descricao']
            promocao.tipo = request.form['tipo']
            promocao.ativo = ativo
            
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename:
                    delete_image(promocao.imagem, 'promocoes')
                    
                    filename = save_image(file, 'promocoes')
                    if filename:
                        promocao.imagem = filename
            
            db.session.commit()
            flash('Promoção/Anúncio atualizado com sucesso!', 'success')
            return redirect(url_for('admin_promocoes'))
        except Exception as e:
            flash(f'Erro ao atualizar promoção/anúncio: {str(e)}', 'error')
    
    return render_template('admin/editar_promocao.html', promocao=promocao)

@app.route('/admin/promocao/excluir/<int:id>')
@login_required
def excluir_promocao(id):
    promocao = Promocao.query.get_or_404(id)
    
    try:
        delete_image(promocao.imagem, 'promocoes')
        
        db.session.delete(promocao)
        db.session.commit()
        flash('Promoção/Anúncio excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir promoção/anúncio: {str(e)}', 'error')
    
    return redirect(url_for('admin_promocoes'))


# --- Admin: Estatísticas ---
@app.route('/admin/estatisticas')
@login_required
def estatisticas():
    # Estatísticas básicas
    total_acessos = Acesso.query.count()
    total_corridas = Corrida.query.count()
    total_posts = Post.query.count()
    acessos_hoje = Acesso.query.filter(
        Acesso.data >= datetime.today().date()
    ).count()
    
    # Top páginas
    from sqlalchemy import func
    top_paginas = db.session.query(
        Acesso.pagina, 
        func.count(Acesso.id).label('total')
    ).group_by(Acesso.pagina).order_by(func.count(Acesso.id).desc()).limit(10).all()
    
    return render_template('admin/estatisticas.html',
                         total_acessos=total_acessos,
                         total_corridas=total_corridas,
                         total_posts=total_posts,
                         acessos_hoje=acessos_hoje,
                         top_paginas=top_paginas)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Chama a rota de setup para criar o admin na primeira execução se não existir
        if not Usuario.query.first():
            print("Criando usuário admin padrão: admin / admin_password_123. Mude a senha!")
            admin_user = Usuario(username='admin', email='admin@exemplo.com')
            admin_user.set_password('admin124') 
            db.session.add(admin_user)
            db.session.commit()
        
    app.run(host='0.0.0.0', port=5000, debug=False)
