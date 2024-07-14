from flask import Flask, request, render_template, redirect, url_for, send_file
from threading import Thread
import os
import time
import csv
from templates.util import get_next_14_days, obter_data_do_sorteio
from datetime import datetime
import random
import pytz
import pandas as pd

manaus = pytz.timezone("America/Manaus") 
now = datetime.today().strftime('%d-%m-%Y')
#now = "18-07-2024"

primeiro_dia = "14-07-2024"
next_14_days = get_next_14_days(primeiro_dia)

print(now)
print(next_14_days)

app = Flask(__name__)


def obter_nome_arquivo_csv(dia):
  pasta_sorteio = "sorteio"
  nome_arquivo = f"{dia}.csv"
  caminho_arquivo = os.path.join(pasta_sorteio, nome_arquivo)
  return caminho_arquivo

@app.route('/list_files', defaults={'req_path': ''})
@app.route('/list_files/<path:req_path>')
def list_files(req_path):
    # Diretório base (pode ser ajustado conforme necessário)
    BASE_DIR = '/'

    # Construir caminho absoluto
    abs_path = os.path.join(BASE_DIR, req_path)

    # Verificar se o caminho é um diretório
    if os.path.isdir(abs_path):
        files = os.listdir(abs_path)
        return jsonify(files)
    elif os.path.isfile(abs_path):
        return send_from_directory(BASE_DIR, req_path)
    else:
        return jsonify({"error": "Caminho não encontrado"}), 404

@app.route('/')
def home():
  return 'I am Alive in ' + str(now)


@app.route('/index')
def index():
  return render_template('index.html', today=now)


@app.route('/add')
def add():
  return render_template('add.html')


@app.route('/realizar_sorteio', methods=['POST'])
def realizar_sorteio():
  data = request.get_json()
  time.sleep(2)
  quantidade_sorteados = int(data['quantidadeSorteados'])
  hoje = now.replace("/", "-")

  # Ler o arquivo CSV correspondente ao dia do sorteio
  nome_arquivo = obter_nome_arquivo_csv(hoje)

  with open(nome_arquivo, 'r') as arquivo_csv:
    registros = list(csv.reader(arquivo_csv))
    participantes_presentes = [
      registro[1] for registro in registros if registro[2] == '0'
    ]

    if quantidade_sorteados > len(participantes_presentes):
      return {
        'success':
        False,
        'message':
        'Não há participantes suficientes para sortear a quantidade desejada.'
      }

    ganhadores = random.sample(participantes_presentes, quantidade_sorteados)

    # Atualizar o arquivo CSV com o status dos ganhadores
    for registro in registros:
      if registro[1] in ganhadores:
        registro[2] = '1'

    with open(nome_arquivo, 'w', newline='') as arquivo_csv_atualizado:
      writer = csv.writer(arquivo_csv_atualizado)
      writer.writerows(registros)

    return {'success': True, 'ganhadores': ganhadores}


@app.route('/sorteio')
def sorteio():
  hoje = now.replace("/", "-")
  pessoas_presentes = []

  # Ler o arquivo CSV correspondente ao dia do sorteio
  nome_arquivo = obter_nome_arquivo_csv(hoje)
  print(f"Nome do arquivo: {nome_arquivo}")  # Debug

  if os.path.isfile(nome_arquivo):
    print("Arquivo encontrado.")  # Debug

    with open(nome_arquivo, 'r') as arquivo_csv:
      leitor_csv = csv.reader(arquivo_csv)
      for linha in leitor_csv:
        nome = linha[1]
        id = linha[0]
        status = linha[2]
        if status == '0':  # Verificar se o status é '0'
          pessoas_presentes.append({'nome': nome, 'id': id})
  else:
    print("Arquivo não encontrado.")  # Debug

  return render_template('sorteio.html',
                         pessoas_presentes=pessoas_presentes,
                         now=now)


@app.route('/criar_excel')
def criar_excel():
  df = pd.read_csv('dados.csv')
  df.to_excel('indicadores.xlsx', index=False)

  return send_file('indicadores.xlsx', as_attachment=True)


@app.route('/indicadores')
def indicadores():
  with open('dados.csv', 'r') as arquivo_csv:
    registros = list(csv.reader(arquivo_csv))
    indicadores = []
    como_soube_data = {'convite': 0, 'propaganda': 0, 'banner': 0, 'outro': 0}

    for i in range(9, len(next_14_days) + 9):
      pessoas_presentes = [
        registro[1] for registro in registros
        if len(registro) > i and registro[i] == '1' and registro[1] != ''
      ]
      quantidade_presentes = len(pessoas_presentes)
      variacao = quantidade_presentes - sum(
        1 for registro in registros if len(registro) > i -
        1 and registro[i - 1] == '1' and registro[1] != '')
      indicadores.append((next_14_days[i - 9], quantidade_presentes, variacao,
                          pessoas_presentes))
    for registro in registros:
      if registro[0] != 'id':
        como_soube = registro[8]
        como_soube_data[como_soube] += 1

  return render_template('indicadores.html',
                         indicadores=indicadores,
                         como_soube_data=como_soube_data,
                         registros=registros,
                         quantidade_presentes = len(registros)-1,
                         criar_excel_url="/criar_excel")


@app.route('/add_person', methods=['POST'])
def add_person():
  nome = request.form.get('nome')
  idade = request.form.get('idade')
  cep = request.form.get('cep')
  rua = request.form.get('rua')
  bairro = request.form.get('bairro')
  casa = request.form.get('casa')
  telefone = request.form.get('telefone')
  como_soube = request.form.get('como_soube')  # Adicionado

  if nome and idade and cep and rua and casa and telefone:
    with open('dados.csv', 'r') as arquivo_csv:
      reader = csv.reader(arquivo_csv)
      next(reader)  # Pular a primeira linha (cabeçalho)

      try:
        ultimo_id = max(int(row[0]) for row in reader)
        novo_id = ultimo_id + 1
      except ValueError:
        novo_id = 1

    with open('dados.csv', 'a', newline='') as arquivo_csv:
      writer = csv.writer(arquivo_csv)
      dados = [
        novo_id, nome, idade, cep, rua, bairro, casa, telefone, como_soube
      ] + [''] * 14  # Atualizado
      writer.writerow(dados)

  return redirect(url_for('index'))


def obter_nome_pessoa(pessoa_id):
  with open('dados.csv', 'r') as arquivo_csv:
    registros = list(csv.reader(arquivo_csv))
    for registro in registros:
      if registro[0] == str(pessoa_id):
        return registro[1]
  return None


presenca_dia = {}


@app.route('/marcar_presenca', methods=['POST'])
def marcar_presenca():
  data = request.get_json()
  pessoa_id = data['pessoa_id']
  dia = data['dia']

  nome = obter_nome_pessoa(pessoa_id)
  if nome is None:
    return {'success': False, 'message': 'Pessoa não encontrada.'}

  data_sorteio = now
  if data_sorteio is None:
    return {'success': False, 'message': 'Data do sorteio não encontrada.'}

  with open('dados.csv', 'r') as arquivo_csv:
    registros = list(csv.reader(arquivo_csv))
    if any(registro[0] == str(pessoa_id) for registro in registros):
      for registro in registros:
        if registro[0] == str(pessoa_id):
          while len(registro) < dia + 9:
            registro.append('')
          registro[dia + 8] = '1'

          break

      with open('dados.csv', 'w', newline='') as arquivo_csv_atualizado:
        writer = csv.writer(arquivo_csv_atualizado)
        writer.writerows(registros)

      # Atualiza o dicionário de presença por dia
      data_str = f'{dia:02d}-' + str(datetime.today().strftime('%d-%m-%Y')[3:])

      if data_str not in presenca_dia:
        presenca_dia[data_str] = []
      if pessoa_id not in presenca_dia[data_str]:
        presenca_dia[data_str].append(pessoa_id)

        # Escreve no arquivo de sorteio
        nome_arquivo = f'sorteio/{data_sorteio.replace("/", "-")}.csv'
        with open(nome_arquivo, 'a', newline='') as arquivo_sorteio:
          writer = csv.writer(arquivo_sorteio)
          writer.writerow([pessoa_id, nome,
                           "0"])  # Inicializa o status como '0'

      return {'success': True}
    else:
      return {'success': False}


@app.route('/letter/<selected_letter>')
def letter(selected_letter):
  pessoas_com_selected_letter = []
  with open('dados.csv', 'r') as arquivo_csv:
    reader = csv.DictReader(arquivo_csv)
    for row in reader:
      if 'nome' in row and row['nome'].startswith(selected_letter):
        pessoas_com_selected_letter.append(row)

  #next_14_days = get_next_14_days(now)

  return render_template('letter.html',
                         selected_letter=selected_letter,
                         pessoas=pessoas_com_selected_letter,
                         next_14_days=next_14_days,
                        now=now)


def run():
  app.run(host='0.0.0.0', port=8080)


def keep():
  t = Thread(target=run)
  t.start()
