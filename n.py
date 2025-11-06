import os
import textwrap
from werkzeug.security import generate_password_hash
from hashlib import sha256 

# --- CONFIGURAÇÃO DE SEGURANÇA (MUDAR ANTES DE PRODUÇÃO) ---
PASSWORD_TO_HASH = "minha_senha_super_secreta_123"
ADMIN_PASSWORD_HASH = generate_password_hash(PASSWORD_TO_HASH)
# -----------------------------------------------------------

# Estrutura de diretórios a ser criada
PROJECT_NAME = "correr-na-rua"
STRUCTURE = {
    PROJECT_NAME: {
        "routes": {},
        "templates": {
            "blog": {},
            "pages": {},
            "admin": {}
        },
        "static": {
            "css": {},
            "images": { 
                "corridas": {},
                "blog": {} # NOVA PASTA PARA IMAGENS DO BLOG
            }
        }
    }
}

# Conteúdo dos arquivos (string formatada com f-string)
FILES = {
    # --- ARQUIVOS RAIZ ---
    f"{PROJECT_NAME}/requirements.txt": textwrap.dedent("""
        Flask==2.3.3
        SQLAlchemy==2.0.23
        Flask-SQLAlchemy==3.1.1
        Flask-Admin==1.6.1
        gunicorn==21.2.0
        python-slugify==8.0.1
        Flask-HTTPAuth==4.1.0
        werkzeug==2.3.7
    """).strip(),
    
    f"{PROJECT_NAME}/config.py": textwrap.dedent("""
        import os

        class Config:
            # ESSENCIAL: Mude a chave para algo complexo ANTES de ir para produção.
            SECRET_KEY = os.environ.get('SECRET_KEY') or 'chave-secreta-para-o-portal-correr-na-rua' 
            SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/app.db'
            SQLALCHEMY_TRACK_MODIFICATIONS = False
    """).strip(),
    
    f"{PROJECT_NAME}/models.py": textwrap.dedent("""
        from flask_sqlalchemy import SQLAlchemy
        from datetime import datetime

        db = SQLAlchemy()

        # Modelo de Corridas (Com campo imagem)
        class Corrida(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            nome = db.Column(db.String(120), nullable=False)
            slug = db.Column(db.String(120), unique=True, nullable=False) 
            data = db.Column(db.Date, nullable=False)
            local = db.Column(db.String(100), nullable=False)
            valor = db.Column(db.Float, default=0.0)
            distancia = db.Column(db.String(50)) 
            descricao_detalhada = db.Column(db.Text, nullable=False)
            link_inscricao = db.Column(db.String(255), nullable=False)
            is_patrocinada = db.Column(db.Boolean, default=False)
            imagem = db.Column(db.String(120), nullable=True, default='default.jpg')
            
        # Modelo de Postagens do Blog (Com campo imagem_capa opcional)
        class Postagem(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            titulo = db.Column(db.String(150), nullable=False)
            slug = db.Column(db.String(150), unique=True, nullable=False)
            data_publicacao = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
            conteudo = db.Column(db.Text, nullable=False)
            is_patrocinado = db.Column(db.Boolean, default=False) 
            imagem_capa = db.Column(db.String(120), nullable=True) # Nome do arquivo de imagem do blog (opcional)

        # Modelo de Log de Acessos
        class Acesso(db.Model):
            id = db.Column(db.Integer, primary_key=True)
            ip_hash = db.Column(db.String(64), nullable=False, index=True) 
            endpoint = db.Column(db.String(100), nullable=False) 
            timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    """).strip(),

    # --- ROUTES ---
    f"{PROJECT_NAME}/routes/blog.py": textwrap.dedent("""
        from flask import Blueprint, render_template
        from models import db, Postagem

        blog_bp = Blueprint('blog', __name__)

        @blog_bp.route('/blog')
        def listagem():
            posts = db.session.execute(
                db.select(Postagem).order_by(Postagem.data_publicacao.desc())
            ).scalars().all()
            return render_template('blog/blog_listagem.html', posts=posts)

        @blog_bp.route('/blog/<string:slug>')
        def postagem(slug):
            post = db.session.execute(
                db.select(Postagem).filter_by(slug=slug)
            ).scalar_one_or_404()
            return render_template('blog/blog_postagem.html', post=post)
    """).strip(),

    # --- APP.PY ---
    f"{PROJECT_NAME}/app.py": textwrap.dedent(f"""
        from flask import Flask, render_template, request, url_for
        from config import Config
        from models import db, Corrida, Postagem, Acesso
        from flask_admin import Admin, BaseView, expose
        from flask_admin.contrib.sqla import ModelView
        from slugify import slugify
        from flask_httpauth import HTTPBasicAuth
        from werkzeug.security import generate_password_hash, check_password_hash
        from werkzeug.utils import secure_filename
        from datetime import datetime, timedelta
        from hashlib import sha256
        from routes.blog import blog_bp 
        
        # Imports para CSV
        import csv
        import io
        import os

        # -----------------------------------------------------------------
        # 1. SEGURANÇA DO ADMIN
        # -----------------------------------------------------------------
        auth = HTTPBasicAuth()
        # Senha padrão hashada: {PASSWORD_TO_HASH} (MUDAR)
        USERS = {{
            "admin_correruar": "{ADMIN_PASSWORD_HASH}" 
        }}

        @auth.verify_password
        def verify_password(username, password):
            if username in USERS and check_password_hash(USERS.get(username), password):
                return username
            return None

        class AdminSecuredView(ModelView):
            def is_accessible(self):
                return auth.current_user() is not None
            def inaccessible_callback(self, name, **kwargs):
                return auth.challenge_auth()

        # -----------------------------------------------------------------
        # 2. ADMIN VIEWS (CRUD, SLUG e Patrocínio)
        # -----------------------------------------------------------------
        class CorridaAdminView(AdminSecuredView):
            column_list = ('nome', 'data', 'local', 'valor', 'distancia', 'is_patrocinada', 'imagem') 
            # Cadastro manual (via painel)
            form_columns = ['nome', 'slug', 'data', 'local', 'distancia', 'valor', 'descricao_detalhada', 'link_inscricao', 'is_patrocinada', 'imagem']
            column_labels = dict(is_patrocinada='Patrocinada', nome='Nome', valor='Valor (R$)', link_inscricao='Link Inscrição', imagem='Nome do Arquivo de Imagem (static/images/corridas)')
            
            def on_model_change(self, form, model, is_created):
                if not model.slug: model.slug = slugify(model.nome)
                model.slug = slugify(model.slug)
                # Garante que a imagem tenha um nome seguro
                if model.imagem:
                    model.imagem = secure_filename(model.imagem)
                super(CorridaAdminView, self).on_model_change(form, model, is_created)

        class PostagemAdminView(AdminSecuredView):
            column_list = ('titulo', 'data_publicacao', 'is_patrocinado', 'imagem_capa')
            # Inclui imagem_capa
            form_columns = ['titulo', 'slug', 'data_publicacao', 'is_patrocinado', 'imagem_capa', 'conteudo']
            column_labels = dict(is_patrocinado='Post Patrocinado', titulo='Título', imagem_capa='Imagem de Capa (static/images/blog)')
            
            def on_model_change(self, form, model, is_created):
                if not model.slug: model.slug = slugify(model.titulo)
                model.slug = slugify(model.slug)
                # Garante que a imagem tenha um nome seguro (se existir)
                if model.imagem_capa:
                    model.imagem_capa = secure_filename(model.imagem_capa)
                super(PostagemAdminView, self).on_model_change(form, model, is_created)
        
        # -----------------------------------------------------------------
        # 3. ANALYTICS VIEW
        # -----------------------------------------------------------------
        class AnalyticsView(AdminSecuredView, BaseView):
            @expose('/')
            def index(self):
                total_acessos = db.session.scalar(db.select(db.func.count(Acesso.id)))
                data_7dias = datetime.utcnow() - timedelta(days=7)
                acessos_7dias = db.session.scalar(
                    db.select(db.func.count(Acesso.id)).filter(Acesso.timestamp >= data_7dias)
                )
                top_rotas = db.session.execute(
                    db.select(Acesso.endpoint, db.func.count(Acesso.id).label('contagem'))
                    .group_by(Acesso.endpoint).order_by(db.func.count(Acesso.id).desc()).limit(5)
                ).all()
                return self.render('admin/analytics_dashboard.html', total_acessos=total_acessos, acessos_7dias=acessos_7dias, top_rotas=top_rotas)

        def log_acesso(endpoint):
            ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)
            ip_hash = sha256(ip_addr.encode()).hexdigest()
            hoje = datetime.utcnow().date()
            acesso_hoje = db.session.execute(
                db.select(Acesso).filter(Acesso.ip_hash == ip_hash, Acesso.timestamp >= hoje)
            ).first()
            
            if acesso_hoje is None:
                novo_acesso = Acesso(ip_hash=ip_hash, endpoint=endpoint)
                db.session.add(novo_acesso)
                try: db.session.commit()
                except Exception: db.session.rollback()

        # -----------------------------------------------------------------
        # 4. ADMIN VIEW: Importação CSV (Cadastro em Massa)
        # -----------------------------------------------------------------
        ALLOWED_EXTENSIONS_CSV = {{'csv'}}
        
        def allowed_file(filename, allowed_extensions):
            return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

        class ImportView(AdminSecuredView, BaseView):
            @expose('/', methods=('GET', 'POST'))
            def index(self):
                if request.method == 'POST':
                    file = request.files.get('file')
                    
                    if not file or file.filename == '' or not allowed_file(file.filename, ALLOWED_EXTENSIONS_CSV):
                        return self.render('admin/import_csv.html', message='❌ Arquivo inválido ou não selecionado.', success=False)
                    
                    try:
                        # Leitura do CSV
                        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                        csv_reader = csv.reader(stream, delimiter=';') 
                        header = next(csv_reader) # Pula o cabeçalho
                        
                        rows_imported = 0
                        for row in csv_reader:
                            # Colunas esperadas: 
                            # 0:nome; 1:data(DD/MM/AAAA); 2:local; 3:valor; 4:distancia; 
                            # 5:descricao_detalhada; 6:link_inscricao; 7:is_patrocinada; 8:nome_arquivo_imagem
                            
                            data_obj = datetime.strptime(row[1], '%d/%m/%Y').date() 
                            valor_float = float(row[3].replace(',', '.')) 

                            corrida = Corrida(
                                nome=row[0],
                                slug=slugify(row[0]), 
                                data=data_obj,
                                local=row[2],
                                valor=valor_float,
                                distancia=row[4],
                                descricao_detalhada=row[5],
                                link_inscricao=row[6],
                                is_patrocinada=True if row[7].lower() in ['sim', 'true', '1'] else False
                            )
                            
                            # Lógica da Imagem 
                            nome_imagem_csv = row[8].strip() if len(row) > 8 and row[8].strip() else 'default.jpg'
                            corrida.imagem = secure_filename(nome_imagem_csv)

                            db.session.add(corrida)
                            rows_imported += 1

                        db.session.commit()
                        return self.render('admin/import_csv.html', message=f'✅ Sucesso! {{rows_imported}} corridas importadas.', success=True)
                        
                    except Exception as e:
                        db.session.rollback()
                        return self.render('admin/import_csv.html', message=f'❌ Erro na importação: {{e}}. Verifique o formato do CSV (separador ";") e a ordem das colunas.', success=False)

                return self.render('admin/import_csv.html', message='Aguardando upload do CSV.')

        def create_app():
            app = Flask(__name__, instance_relative_config=True)
            app.config.from_object(Config)
            db.init_app(app)
            app.jinja_env.globals.update(now=datetime.now)

            admin = Admin(app, name='Admin - Correr na Rua', template_mode='bootstrap3', url='/admin')
            admin.add_view(CorridaAdminView(Corrida, db.session, name='Corridas (Manual)')) # Alterado o nome para 'Manual'
            admin.add_view(PostagemAdminView(Postagem, db.session, name='Blog'))
            admin.add_view(AnalyticsView(name='Visão de Acessos', endpoint='analytics'))
            admin.add_view(ImportView(name='Importar Corridas (CSV)', endpoint='import_csv')) # Adicionado
            
            app.register_blueprint(blog_bp)
            
            @app.after_request
            def after_request_log(response):
                if response.status_code == 200 and request.endpoint and not request.path.startswith('/static') and not request.path.startswith('/admin'):
                    log_acesso(request.endpoint)
                return response

            @app.route('/')
            def index():
                corridas = db.session.execute(db.select(Corrida).order_by(Corrida.data)).scalars().all()
                posts = db.session.execute(db.select(Postagem).order_by(Postagem.data_publicacao.desc()).limit(3)).scalars().all()
                return render_template('index.html', corridas=corridas, posts=posts)

            @app.route('/corridas/<string:slug>')
            def detalhe_corrida(slug):
                corrida = db.session.execute(db.select(Corrida).filter_by(slug=slug)).scalar_one_or_404()
                return render_template('corrida_detalhe.html', corrida=corrida)

            @app.route('/sobre')
            def sobre():
                return render_template('pages/sobre.html')

            @app.route('/termos-de-uso')
            def termos():
                return render_template('pages/termos_de_uso.html')

            @app.route('/politica-de-privacidade')
            def privacidade():
                return render_template('pages/politica_de_privacidade.html')

            with app.app_context():
                db.create_all()

            return app

        if __name__ == '__main__':
            app = create_app()
            app.run(debug=True)
    """).strip(),
    
    # --- TEMPLATES ---
    f"{PROJECT_NAME}/templates/base.html": textwrap.dedent("""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
            
            <title>{% block title %}Correr na Rua - Encontre sua Próxima Corrida{% endblock %}</title>
            
            <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=SEU_AD_CLIENT_ID"
                    crossorigin="anonymous"></script>
            {% block head_extras %}{% endblock %} 
        </head>
        <body>
            <header class="main-header">
                <div class="container header-content">
                    <a href="{{ url_for('index') }}" class="logo">Correr na Rua</a>
                    <nav class="main-nav">
                        <a href="{{ url_for('index') }}">Corridas</a>
                        <a href="{{ url_for('blog.listagem') }}">Blog</a>
                        <a href="{{ url_for('sobre') }}">Sobre</a>
                    </nav>
                </div>
            </header>

            <main class="main-content">
                <div class="container">
                    {% block content %}{% endblock %}
                </div>
            </main>

            <footer class="main-footer">
                <div class="container footer-content">
                    <p>&copy; {{ now().year }} Correr na Rua. Todos os direitos reservados.</p>
                    <nav class="footer-nav">
                        <a href="{{ url_for('termos') }}">Termos de Uso</a>
                        <span class="separator">|</span>
                        <a href="{{ url_for('privacidade') }}">Política de Privacidade</a>
                    </nav>
                </div>
            </footer>
        </body>
        </html>
    """).strip(),
    
    f"{PROJECT_NAME}/templates/index.html": textwrap.dedent("""
        {% extends "base.html" %}

        {% block title %}Correr na Rua | Calendário e Agenda de Corridas{% endblock %}

        {% block content %}
            <h1>🏃 Corridas Próximas</h1>
            
            <div class="ad-banner">
                <ins class="adsbygoogle"
                    style="display:block"
                    data-ad-client="SEU_AD_CLIENT_ID"
                    data-ad-slot="SEU_AD_SLOT_HOME_BANNER"
                    data-ad-format="auto"
                    data-full-width-responsive="true"></ins>
                <script>
                    (adsbygoogle = window.adsbygoogle || []).push({});
                </script>
            </div>

            <div class="corridas-grid">
                {% for corrida in corridas %}
                <a href="{{ url_for('detalhe_corrida', slug=corrida.slug) }}" class="card corrida-card {% if corrida.is_patrocinada %}patrocinado{% endif %}">
                    {% if corrida.is_patrocinada %}
                        <span class="patrocinado-label">PATROCINADA</span>
                    {% endif %}
                    
                    <div class="card-image-wrapper">
                        <img src="{{ url_for('static', filename='images/corridas/' + corrida.imagem) }}" 
                             alt="Imagem da corrida {{ corrida.nome }}" 
                             class="card-image">
                    </div>

                    <div class="card-content-body">
                        <h2>{{ corrida.nome }}</h2>
                        <p>🗓️ **Data:** {{ corrida.data.strftime('%d/%m/%Y') }}</p>
                        <p>📍 **Local:** {{ corrida.local }}</p>
                        <p>📏 **Distância:** {{ corrida.distancia }}</p>
                        <p class="valor-card">💰 **Valor:** R$ {{ "%.2f"|format(corrida.valor) }}</p>
                    </div>
                </a>
                {% else %}
                <p>Nenhuma corrida cadastrada no momento. Volte em breve!</p>
                {% endfor %}
            </div>

            <h2 style="margin-top: 50px;">📰 Últimos Posts do Blog</h2>
            <div class="posts-grid">
                {% for post in posts %}
                <a href="{{ url_for('blog.postagem', slug=post.slug) }}" class="card blog-card {% if post.is_patrocinado %}patrocinado{% endif %}">
                    {% if post.is_patrocinado %}
                        <span class="patrocinado-label">POST PATROCINADO</span>
                    {% endif %}
                    
                    {% if post.imagem_capa %}
                        <div class="card-image-wrapper">
                            <img src="{{ url_for('static', filename='images/blog/' + post.imagem_capa) }}" 
                                 alt="Imagem de Capa do post {{ post.titulo }}" 
                                 class="card-image">
                        </div>
                    {% endif %}
                    
                    <div class="card-content-body">
                        <h2>{{ post.titulo }}</h2>
                        <p>🗓️ **Publicado em:** {{ post.data_publicacao.strftime('%d/%m/%Y') }}</p>
                    </div>
                </a>
                {% endfor %}
            </div>

        {% endblock %}
    """).strip(),
    
    f"{PROJECT_NAME}/templates/corrida_detalhe.html": textwrap.dedent("""
        {% extends "base.html" %}

        {% block title %}{{ corrida.nome }} | Detalhes e Inscrição{% endblock %}

        {% block content %}
            <div class="detalhe-corrida-container">
                
                <div class="text-center mb-4">
                    <img src="{{ url_for('static', filename='images/corridas/' + corrida.imagem) }}" 
                         alt="Imagem da corrida {{ corrida.nome }}" 
                         class="img-fluid" 
                         style="max-width: 100%; height: auto; border-radius: 8px;">
                </div>

                <header class="detalhe-header">
                    <h1>{{ corrida.nome }}</h1>
                    <p class="data-local">
                        🗓️ **{{ corrida.data.strftime('%d de %B de %Y') }}** | 
                        📍 **{{ corrida.local }}**
                    </p>
                    {% if corrida.is_patrocinada %}
                        <span class="patrocinado-tag">✨ Corrida Patrocinada - Destaque</span>
                    {% endif %}
                </header>
                
                <hr class="detalhe-separator">

                <section class="inscricao-box">
                    <div class="info-box">
                        <p>💰 **Valor:** R$ {{ "%.2f"|format(corrida.valor) }}</p>
                        <p>📏 **Distâncias:** {{ corrida.distancia }}</p>
                    </div>
                    
                    <a href="{{ corrida.link_inscricao }}" 
                       class="btn-inscricao" 
                       target="_blank" 
                       rel="noopener noreferrer">
                        👉 INSCREVA-SE AGORA
                    </a>
                </section>

                <div class="ad-container ad-meio-detalhe">
                    <ins class="adsbygoogle"
                         style="display:block; text-align:center;"
                         data-ad-layout="in-article"
                         data-ad-format="fluid"
                         data-ad-client="SEU_AD_CLIENT_ID"
                         data-ad-slot="SEU_AD_SLOT_CORRIDA_DETALHE_1"></ins>
                    <script> (adsbygoogle = window.adsbygoogle || []).push({}); </script>
                </div>

                <section class="detalhes-texto">
                    <h2>Sobre a Corrida</h2>
                    <div class="descricao-completa">
                        {{ corrida.descricao_detalhada|safe }}
                    </div>
                </section>

                <div class="ad-container ad-fim-detalhe">
                    <ins class="adsbygoogle"
                         style="display:block; text-align:center;"
                         data-ad-layout="in-article"
                         data-ad-format="fluid"
                         data-ad-client="SEU_AD_CLIENT_ID"
                         data-ad-slot="SEU_AD_SLOT_CORRIDA_DETALHE_2"></ins>
                    <script> (adsbygoogle = window.adsbygoogle || []).push({}); </script>
                </div>

                <p class="voltar"><a href="{{ url_for('index') }}">← Voltar para a lista de Corridas</a></p>

            </div>
        {% endblock %}
    """).strip(),
    
    # --- ADMIN TEMPLATES ---
    f"{PROJECT_NAME}/templates/admin/analytics_dashboard.html": textwrap.dedent("""
        {% extends 'admin/master.html' %}

        {% block body %}
            <div class="container-fluid">
                <h1>Dashboard de Acessos</h1>
                <p class="lead">Dados de acesso diário (único por IP/dia) para visão de performance do portal **Correr na Rua**.</p>
                
                <div class="row" style="margin-top: 20px;">
                    <div class="col-md-4">
                        <div class="card text-center bg-primary text-white">
                            <div class="card-body">
                                <h4 class="card-title">Total de Acessos Únicos</h4>
                                <p class="card-text" style="font-size: 2.5em;">{{ total_acessos }}</p>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card text-center bg-success text-white">
                            <div class="card-body">
                                <h4 class="card-title">Últimos 7 Dias</h4>
                                <p class="card-text" style="font-size: 2.5em;">{{ acessos_7dias }}</p>
                            </div>
                        </div>
                    </div>
                </div>

                <h2 style="margin-top: 40px;">Rotas Mais Acessadas (Top 5)</h2>
                <table class="table table-striped">
                    <thead>
                        <tr>
                            <th>Rota/Endpoint</th>
                            <th>Contagem (Acessos Únicos)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for rota, contagem in top_rotas %}
                        <tr>
                            <td><code>{{ rota }}</code></td>
                            <td>{{ contagem }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% endblock %}
    """).strip(),
    
    f"{PROJECT_NAME}/templates/admin/import_csv.html": textwrap.dedent("""
        {% extends 'admin/master.html' %}

        {% block body %}
            <div class="container-fluid">
                <h1>Importação de Corridas via CSV</h1>
                
                {% if message %}
                    <div class="alert {% if success %}alert-success{% else %}alert-danger{% endif %}">{{ message }}</div>
                {% endif %}

                <p class="lead">Para cadastrar corridas em massa, utilize o formato CSV (separado por ponto e vírgula **;**).</p>

                <h2>⚠️ ATENÇÃO - Regras do CSV e Imagens</h2>
                <ul class="list-group mb-4">
                    <li class="list-group-item list-group-item-warning">1. O separador de colunas DEVE ser o **ponto e vírgula (;)**.</li>
                    <li class="list-group-item list-group-item-warning">2. O formato da data DEVE ser **DD/MM/AAAA**.</li>
                    <li class="list-group-item list-group-item-warning">3. O separador decimal do valor DEVE ser a **vírgula (,)**.</li>
                    <li class="list-group-item list-group-item-info">4. **A IMAGEM:** O arquivo CSV só deve conter o **nome do arquivo da imagem** (ex: `maratona.jpg`).</li>
                    <li class="list-group-item list-group-item-info">5. **Você deve garantir** que o arquivo de imagem referenciado já foi enviado manualmente para a pasta: **`static/images/corridas/`**.</li>
                </ul>
                
                <h2>Estrutura Obrigatória do CSV (Cabeçalho)</h2>
                <pre class="bg-light p-3">nome;data;local;valor;distancia;descricao_detalhada;link_inscricao;is_patrocinada;nome_arquivo_imagem</pre>


                <form method="POST" enctype="multipart/form-data" class="mt-4">
                    <div class="form-group">
                        <label for="file">Selecione o arquivo CSV:</label>
                        <input type="file" name="file" id="file" required class="form-control-file">
                    </div>
                    <button type="submit" class="btn btn-primary mt-3">Importar Corridas</button>
                </form>
            </div>
        {% endblock %}
    """).strip(),


    # --- PÁGINAS ESTÁTICAS (Inclusas para Completude) ---
    f"{PROJECT_NAME}/templates/pages/sobre.html": textwrap.dedent("""
        {% extends "base.html" %}

        {% block title %}Sobre Nós | Correr na Rua{% endblock %}

        {% block content %}
            <article class="static-page-content">
                <h1>Sobre o Correr na Rua</h1>
                
                <p>O Correr na Rua nasceu da paixão por esporte, saúde e, acima de tudo, pela corrida de rua. Nosso objetivo é ser o **portal mais leve, rápido e confiável** para corredores amadores e profissionais que buscam informações completas sobre eventos em todo o país.</p>

                <section class="missao-visao">
                    <h2>Nossa Missão</h2>
                    <p>Conectar corredores às suas próximas grandes aventuras. Simplificamos a busca, garantindo que você encontre todos os detalhes essenciais – nome, data, local, valor e distância – de forma clara e acessível, mesmo em conexões lentas.</p>
                </section>

                <section class="valores">
                    <h2>Nossos Pilares</h2>
                    <ul>
                        <li><strong>Leveza e Velocidade:</strong> Desenvolvemos este portal com foco extremo em performance, garantindo que a informação chegue a você rapidamente, em qualquer dispositivo.</li>
                        <li><strong>Transparência:</strong> Todas as informações sobre as corridas são verificadas e apresentadas com transparência.</li>
                        <li><strong>Comunidade:</strong> Através do nosso Blog, oferecemos conteúdo relevante sobre treinamento, nutrição e notícias do universo da corrida.</li>
                    </ul>
                </section>
                
                <p>Somos movidos pela satisfação de ver a comunidade de corrida crescendo. Conte conosco para encontrar, planejar e correr!</p>
            </article>
        {% endblock %}
    """).strip(),
    
    f"{PROJECT_NAME}/templates/pages/termos_de_uso.html": textwrap.dedent("""
        {% extends "base.html" %}

        {% block title %}Termos de Uso | Correr na Rua{% endblock %}

        {% block content %}
            <article class="static-page-content">
                <h1>Termos de Uso do Portal Correr na Rua</h1>
                
                <p>Última atualização: Novembro de 2025</p>

                <h2>1. Aceitação dos Termos</h2>
                <p>Ao acessar e utilizar o portal Correr na Rua, você concorda em cumprir e se sujeitar aos presentes Termos de Uso e à nossa Política de Privacidade. Caso não concorde com qualquer ponto destes Termos, você não deve utilizar o portal.</p>

                <h2>2. Uso do Conteúdo</h2>
                <p>Todo o conteúdo, incluindo textos, dados de corridas e posts de blog, é propriedade do Correr na Rua ou utilizado sob licença. É proibida a cópia, reprodução ou distribuição do conteúdo para fins comerciais sem autorização expressa.</p>

                <h2>3. Isenção de Responsabilidade sobre Corridas</h2>
                <p>O Correr na Rua atua como um agregador de informações de eventos de terceiros. Embora busquemos a máxima precisão:</p>
                <ul>
                    <li>Não nos responsabilizamos por alterações de data, local, valor ou cancelamentos de eventos realizados pelas organizadoras.</li>
                    <li>Os links de inscrição direcionam para plataformas de terceiros (organizadoras ou parceiras). A responsabilidade pelo processo de inscrição, pagamento e execução da corrida é inteiramente da entidade responsável pelo link.</li>
                    <li>Recomendamos sempre verificar as informações diretamente com a organizadora oficial da corrida antes de efetuar qualquer pagamento ou deslocamento.</li>
                </ul>

                <h2>4. Monetização</h2>
                <p>O portal Correr na Rua é monetizado através de publicidade (Google AdSense) e conteúdo patrocinado (corridas e posts de blog). A presença de anúncios ou de uma corrida patrocinada não implica em endosso de nossa parte, apenas um acordo comercial.</p>
                
                <h2>5. Alterações nos Termos</h2>
                <p>Reservamos o direito de modificar estes Termos a qualquer momento. As alterações entrarão em vigor imediatamente após a publicação no portal. O uso contínuo do serviço após a publicação das modificações constitui sua aceitação dos novos Termos.</p>
            </article>
        {% endblock %}
    """).strip(),

    f"{PROJECT_NAME}/templates/pages/politica_de_privacidade.html": textwrap.dedent("""
        {% extends "base.html" %}

        {% block title %}Política de Privacidade | Correr na Rua{% endblock %}

        {% block content %}
            <article class="static-page-content">
                <h1>Política de Privacidade</h1>

                <p>Última atualização: Novembro de 2025</p>

                <p>A privacidade dos nossos usuários é de extrema importância. Esta política descreve como coletamos, usamos, armazenamos e protegemos suas informações.</p>

                <h2>1. Coleta de Informações</h2>
                <p>Não coletamos diretamente informações pessoais identificáveis (como nome, CPF ou e-mail) dos usuários, a menos que você as forneça voluntariamente.</p>

                <h2>2. Dados de Navegação (Analytics Local)</h2>
                <p>Utilizamos um sistema de log interno minimalista para registrar o primeiro acesso de cada IP por dia. Estes dados são usados exclusivamente para medir a performance e otimizar a experiência do usuário, sem identificar o indivíduo.</p>

                <h2>3. Cookies e Publicidade (Google AdSense)</h2>
                <p>Utilizamos o serviço de publicidade **Google AdSense** para monetização. O Google pode utilizar cookies e tecnologias similares para exibir anúncios com base em visitas anteriores a este ou outros sites. Isto é conhecido como publicidade baseada em interesse.</p>
                <ul>
                    <li>**Cookies:** Pequenos arquivos armazenados no seu computador que ajudam a fornecer uma experiência personalizada. Você pode desativar o uso de cookies nas configurações do seu navegador.</li>
                    <li>**Publicidade Personalizada:** Você pode optar por não receber publicidade personalizada visitando as Configurações de anúncios do Google.</li>
                </ul>

                <h2>4. Links de Terceiros</h2>
                <p>Nosso portal contém links para websites externos (organizadoras de corrida, plataformas de inscrição). Não nos responsabilizamos pelas práticas de privacidade ou conteúdo desses websites de terceiros.</p>

                <h2>5. Segurança e Armazenamento</h2>
                <p>Tomamos medidas razoáveis para proteger as informações que coletamos. Contudo, nenhum sistema é 100% seguro. Devido à nossa arquitetura leve, armazenamos o mínimo de dados possível para mitigar riscos.</p>
            </article>
        {% endblock %}
    """).strip(),

    f"{PROJECT_NAME}/templates/blog/blog_listagem.html": textwrap.dedent("""
        {% extends "base.html" %}

        {% block title %}Blog | Notícias e Dicas de Corrida{% endblock %}

        {% block content %}
            <h1>📰 Blog Correr na Rua</h1>
            <p class="lead">Conteúdo de treinamento, nutrição e análise de eventos.</p>
            
            <div class="posts-grid">
                {% for post in posts %}
                <a href="{{ url_for('blog.postagem', slug=post.slug) }}" class="card blog-card {% if post.is_patrocinado %}patrocinado{% endif %}">
                    {% if post.is_patrocinado %}
                        <span class="patrocinado-label">POST PATROCINADO</span>
                    {% endif %}
                    
                    {% if post.imagem_capa %}
                        <div class="card-image-wrapper">
                            <img src="{{ url_for('static', filename='images/blog/' + post.imagem_capa) }}" 
                                 alt="Imagem de Capa do post {{ post.titulo }}" 
                                 class="card-image">
                        </div>
                    {% endif %}

                    <div class="card-content-body">
                        <h2>{{ post.titulo }}</h2>
                        <p>🗓️ **Publicado em:** {{ post.data_publicacao.strftime('%d/%m/%Y') }}</p>
                    </div>
                </a>
                {% else %}
                <p>Nenhum post no blog ainda. Em breve teremos novidades!</p>
                {% endfor %}
            </div>
        {% endblock %}
    """).strip(),

    f"{PROJECT_NAME}/templates/blog/blog_postagem.html": textwrap.dedent("""
        {% extends "base.html" %}

        {% block title %}{{ post.titulo }} | Blog{% endblock %}

        {% block content %}
            <div class="post-container">
                <header class="detalhe-header" style="text-align: left;">
                    {% if post.imagem_capa %}
                        <div class="text-center mb-4">
                            <img src="{{ url_for('static', filename='images/blog/' + post.imagem_capa) }}" 
                                 alt="Imagem de capa do post" 
                                 class="img-fluid" 
                                 style="max-width: 100%; height: auto; border-radius: 8px;">
                        </div>
                    {% endif %}
                    <h1>{{ post.titulo }}</h1>
                    <p class="data-local">Publicado em: {{ post.data_publicacao.strftime('%d de %B de %Y') }}</p>
                    {% if post.is_patrocinado %}
                        <div class="aviso-patrocinio">
                            Este post foi criado em parceria com um patrocinador e pode conter conteúdo promocional.
                        </div>
                    {% endif %}
                </header>
                
                <hr class="detalhe-separator">
                
                <section class="post-conteudo detalhes-texto">
                    {{ post.conteudo|safe }}
                </section>
                
                <p class="voltar" style="margin-top: 30px;"><a href="{{ url_for('blog.listagem') }}">← Voltar para a lista de posts</a></p>
            </div>
        {% endblock %}
    """).strip(),


    # --- CSS (COM ESTILO PARA IMAGEM DO CARD E BLOG) ---
    f"{PROJECT_NAME}/static/css/style.css": textwrap.dedent(
        """
        /* static/css/style.css */

        /* --- Reset e Base --- */
        :root {
            --primary-color: #007bff; /* Azul primário */
            --secondary-color: #6c757d; 
            --light-bg: #f8f9fa; 
            --card-bg: #ffffff; 
            --border-color: #dee2e6;
            --patrocinado-color: #ffc107; /* Amarelo para destaque de patrocínio */
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: var(--light-bg);
        }

        .container { max-width: 1200px; margin: 0 auto; padding: 0 15px; }
        h1, h2, h3 { margin-bottom: 0.5em; color: #212529; }

        /* --- Header e Navegação --- */
        .main-header { background-color: var(--card-bg); border-bottom: 1px solid var(--border-color); padding: 15px 0; }
        .header-content { display: flex; justify-content: space-between; align-items: center; }
        .logo { font-size: 1.5em; font-weight: bold; color: var(--primary-color); text-decoration: none; }
        .main-nav a { text-decoration: none; color: var(--secondary-color); margin-left: 20px; }
        .main-nav a:hover { color: var(--primary-color); }

        /* --- Conteúdo Principal e Cards --- */
        .main-content { padding: 40px 0; min-height: 80vh; }

        .corridas-grid, .posts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }

        .card {
            display: block; 
            background-color: var(--card-bg);
            padding: 0; 
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s, box-shadow 0.2s;
            text-decoration: none; 
            color: #333;
            overflow: hidden; 
            height: 100%; /* Garante que os cards da grade tenham altura uniforme */
        }
        .card:hover { transform: translateY(-3px); box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15); }
        
        /* Estilo do Conteúdo de Texto do Card */
        .corrida-card .card-content-body, .blog-card .card-content-body {
            padding: 15px 20px; 
            flex-grow: 1; /* Garante que o corpo ocupe o espaço restante */
        }
        
        /* Imagem do Card (Corridas e Blog) */
        .card-image-wrapper {
            width: 100%;
            height: 180px; 
            overflow: hidden;
        }
        .card-image {
            width: 100%;
            height: 100%;
            object-fit: cover; 
            transition: transform 0.3s;
        }
        .corrida-card:hover .card-image, .blog-card:hover .card-image {
            transform: scale(1.05); 
        }

        .card h2 { color: var(--primary-color); margin-bottom: 10px; font-size: 1.2em; }
        .card p { font-size: 0.9em; margin: 5px 0; }
        .valor-card {
            font-weight: bold;
            color: #333;
            margin-top: 10px !important;
        }

        /* --- Destaque Patrocinado --- */
        .patrocinado { border: 3px solid var(--patrocinado-color); background-color: #fffde7; position: relative; }
        .patrocinado-label {
            position: absolute; top: 0; right: 0;
            background-color: var(--patrocinado-color);
            color: #333; font-size: 0.7em; font-weight: bold;
            padding: 4px 8px; border-bottom-left-radius: 8px; z-index: 10;
        }
        .patrocinado-tag {
            display: inline-block; background-color: var(--patrocinado-color);
            color: #333; padding: 5px 12px; border-radius: 50px; font-weight: bold; margin-top: 10px;
        }
        .aviso-patrocinio {
            border-left: 5px solid var(--patrocinado-color);
            padding: 10px 15px;
            margin: 20px 0;
            background-color: #fff8e1;
            color: #333;
            font-style: italic;
        }

        /* --- Estilo Detalhes da Corrida/Post --- */
        .detalhe-corrida-container, .post-container {
            background-color: var(--card-bg);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); 
        }
        
        /* Imagem de Destaque no Detalhe */
        .post-container img, .detalhe-corrida-container img {
             /* Remove o estilo inline se estiver presente, e garante que a imagem de destaque do post seja responsiva */
             width: 100%;
             height: auto;
        }


        .detalhe-header { text-align: center; margin-bottom: 25px; }
        .detalhe-header h1 { font-size: 2em; color: var(--primary-color); margin-bottom: 5px; }
        .data-local { color: var(--secondary-color); font-size: 1.1em; }
        .detalhe-separator { border: 0; height: 1px; background-color: var(--border-color); margin: 30px 0; }

        /* Box de Inscrição (DESTAQUE) */
        .inscricao-box {
            display: flex; justify-content: space-around; align-items: center;
            padding: 20px 40px; background-color: #e9ecef; 
            border-radius: 8px; margin-bottom: 30px;
        }
        .inscricao-box .info-box p { font-size: 1.2em; font-weight: 500; margin: 5px 0; }
        .btn-inscricao {
            background-color: #28a745; 
            color: white; padding: 15px 30px; text-decoration: none;
            border-radius: 50px; font-size: 1.2em; font-weight: bold;
            letter-spacing: 0.5px; transition: background-color 0.2s, transform 0.1s;
        }
        .btn-inscricao:hover { background-color: #218838; transform: translateY(-1px); }
        .detalhes-texto { font-size: 1.05em; color: #495057; }

        /* --- Páginas Estáticas --- */
        .static-page-content {
            background-color: var(--card-bg); padding: 40px; border-radius: 10px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); line-height: 1.7; font-size: 1.05em;
        }
        .static-page-content h1 { font-size: 2em; color: var(--primary-color); margin-bottom: 20px; text-align: center; }
        .static-page-content h2 { 
            font-size: 1.5em; margin-top: 30px; margin-bottom: 15px; 
            border-bottom: 2px solid var(--border-color); padding-bottom: 5px; 
        }
        .static-page-content p { margin-bottom: 1em; }
        .static-page-content ul { margin-left: 25px; margin-bottom: 1.5em; list-style: disc; }


        /* --- Anúncios e Footer --- */
        .ad-banner, .ad-container {
            width: 100%; margin: 25px 0; text-align: center; min-height: 50px; 
            border: 1px dashed var(--border-color); display: flex;
            justify-content: center; align-items: center; font-size: 0.8em;
            color: var(--secondary-color);
        }
        .main-footer { background-color: #343a40; color: #fff; padding: 20px 0; font-size: 0.9em; }
        .footer-content { display: flex; justify-content: space-between; align-items: center; }
        .footer-nav a { color: #adb5bd; text-decoration: none; margin-left: 15px; }
        .footer-nav a:hover { color: #fff; }
        .separator { margin-left: 10px; color: #6c757d; }

        /* --- Media Queries --- */
        @media (max-width: 768px) {
            .header-content { flex-direction: column; }
            .main-nav a { margin: 0 10px; }
            .footer-content { flex-direction: column; text-align: center; }
            .inscricao-box { flex-direction: column; text-align: center; }
            .inscricao-box .info-box { margin-bottom: 20px; }
        }
        """
    ).strip()
}

def create_folders(base_path, structure):
    """Cria a estrutura de pastas recursivamente."""
    for folder, sub_structure in structure.items():
        path = os.path.join(base_path, folder)
        os.makedirs(path, exist_ok=True)
        if sub_structure:
            create_folders(path, sub_structure)

def create_files(files_dict):
    """Cria e preenche todos os arquivos."""
    for filename, content in files_dict.items():
        try:
            # Garante que o diretório pai existe antes de criar o arquivo
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ Criado: {filename}")
        except Exception as e:
            print(f"❌ Erro ao criar {filename}: {e}")

if __name__ == "__main__":
    print(f"Iniciando a criação do projeto '{PROJECT_NAME}'...")
    
    # 1. Criar a estrutura de pastas
    create_folders(os.getcwd(), STRUCTURE)
    
    # 2. Criar pastas auxiliares
    os.makedirs(os.path.join(PROJECT_NAME, "instance"), exist_ok=True)
    
    # 3. Criar e preencher os arquivos
    create_files(FILES)
    
    # 4. Cria arquivos 'default.jpg' de placeholder para evitar erros na primeira execução
    try:
        placeholder_corrida_path = os.path.join(PROJECT_NAME, "static", "images", "corridas", "default.jpg")
        with open(placeholder_corrida_path, "w") as f: f.write("")
        print(f"✅ Criado: Placeholder de imagem de corrida.")
        
        placeholder_blog_path = os.path.join(PROJECT_NAME, "static", "images", "blog", "default_blog.jpg")
        with open(placeholder_blog_path, "w") as f: f.write("")
        print(f"✅ Criado: Placeholder de imagem de blog.")
    except:
        pass
    
    print("\n--- ✅ PROJETO CRIADO COM SUCESSO! ---")
    print(f"Acesse a pasta '{PROJECT_NAME}' para começar.")
    print("\nPróximos passos:")
    print("1. Crie o ambiente e instale as dependências: pip install -r requirements.txt")
    print("2. Adicione imagens nos diretórios `static/images/corridas` e `static/images/blog`.")
    print("3. Execute: python app.py")
    print("\nCredenciais de Admin Padrão:")
    print(f"Usuário: admin_correruar")
    print(f"Senha: {PASSWORD_TO_HASH} (MUDAR IMEDIATAMENTE)")
