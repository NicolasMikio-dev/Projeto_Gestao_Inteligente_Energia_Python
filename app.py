"""Gestão Inteligente de Energia — API Flask + MySQL.

A camada IoT aceita dados enviados por sensores autenticados. Sem hardware,
use /api/aparelhos/<id>/simular para gerar estimativas, não medições reais.
"""
import calendar
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, g, jsonify, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", ""),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    MAX_CONTENT_LENGTH=64 * 1024,
)
if not app.config["SECRET_KEY"]:
    raise RuntimeError("Configure SECRET_KEY no arquivo .env")


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


@app.errorhandler(ApiError)
def api_error(error):
    return jsonify(erro=error.message), error.status


@app.errorhandler(mysql.connector.Error)
def database_error(error):
    app.logger.exception("Erro no MySQL: %s", error)
    if "db" in g:
        try:
            g.db.rollback()
        except mysql.connector.Error:
            pass
    return jsonify(erro="Erro de banco de dados. Verifique o MySQL e os scripts SQL."), 500


def get_connection():
    if "db" not in g:
        g.db = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME", "gestao_inteligente_de_energia"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "Aluno@2025"),
            charset="utf8mb4",
            connection_timeout=8,
        )
    return g.db


@app.teardown_appcontext
def close_connection(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=(), one=False):
    cursor = get_connection().cursor(dictionary=True, buffered=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchone() if one else cursor.fetchall()
    finally:
        cursor.close()


def write(sql, params=()):
    cursor = get_connection().cursor()
    try:
        cursor.execute(sql, params)
        return cursor.lastrowid
    finally:
        cursor.close()


def commit():
    get_connection().commit()


def data():
    if not request.is_json or not isinstance(request.get_json(silent=True), dict):
        raise ApiError("Envie um objeto JSON válido (Content-Type: application/json).")
    return request.get_json()


def required_text(payload, key, length=100):
    value = payload.get(key, "")
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > length:
        raise ApiError(f"Campo '{key}' obrigatório (até {length} caracteres).")
    return value.strip()


def positive_int(value, label, maximum=100000):
    if isinstance(value, bool) or not str(value).isdigit():
        raise ApiError(f"'{label}' deve ser um número inteiro positivo.")
    number = int(value)
    if not 1 <= number <= maximum:
        raise ApiError(f"'{label}' deve estar entre 1 e {maximum}.")
    return number


def number(value, label, minimum=Decimal("0"), maximum=Decimal("1000000")):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ApiError(f"'{label}' deve ser um número válido.")
    if not n.is_finite() or n < minimum or n > maximum:
        raise ApiError(f"'{label}' fora da faixa permitida.")
    return n


def logged(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "cliente_id" not in session:
            raise ApiError("Faça login para continuar.", 401)
        return fn(*args, **kwargs)
    return wrapper


def own_unit(unit_id):
    row = query("SELECT ID_Unidade FROM Unidade_Consumidora "
                "WHERE ID_Unidade=%s AND ID_Cliente=%s",
                (unit_id, session["cliente_id"]), one=True)
    if not row:
        raise ApiError("Unidade não encontrada.", 404)


def own_room(room_id):
    row = query("SELECT c.ID_Comodo, c.ID_Unidade FROM Comodo c "
                "JOIN Unidade_Consumidora u ON u.ID_Unidade=c.ID_Unidade "
                "WHERE c.ID_Comodo=%s AND u.ID_Cliente=%s",
                (room_id, session["cliente_id"]), one=True)
    if not row:
        raise ApiError("Cômodo não encontrado.", 404)
    return row


def own_appliance(device_id):
    row = query("SELECT a.ID_Aparelho,a.Potencia_W,c.ID_Unidade FROM Aparelho a "
                "JOIN Comodo c ON c.ID_Comodo=a.ID_Comodo "
                "JOIN Unidade_Consumidora u ON u.ID_Unidade=c.ID_Unidade "
                "WHERE a.ID_Aparelho=%s AND u.ID_Cliente=%s",
                (device_id, session["cliente_id"]), one=True)
    if not row:
        raise ApiError("Aparelho não encontrado.", 404)
    return row


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/auth/cadastro")
def register():
    d = data()
    name = required_text(d, "nome")
    email = required_text(d, "email").lower()
    cpf = re.sub(r"\D", "", str(d.get("cpf", "")))
    phone = re.sub(r"\D", "", str(d.get("telefone", "")))
    password = d.get("senha", "")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ApiError("Informe um e-mail válido.")
    if len(cpf) != 11 or not 10 <= len(phone) <= 13:
        raise ApiError("Informe CPF com 11 dígitos e telefone com 10 a 13 dígitos.")
    if not isinstance(password, str) or len(password) < 8:
        raise ApiError("A senha deve ter pelo menos 8 caracteres.")
    if query("SELECT ID_Cliente FROM Cliente WHERE Email=%s OR CPF=%s", (email, cpf), one=True):
        raise ApiError("E-mail ou CPF já cadastrado.", 409)
    client_id = write("INSERT INTO Cliente(Nome_Cliente,CPF,Email,Telefone) "
                      "VALUES (%s,%s,%s,%s)", (name, cpf, email, phone))
    write("INSERT INTO Credencial(ID_Cliente,Senha_Hash) VALUES(%s,%s)",
          (client_id, generate_password_hash(password)))
    commit()
    session.clear()
    session["cliente_id"] = client_id
    return jsonify(id=client_id, nome=name), 201


@app.post("/api/auth/login")
def login():
    d = data()
    email = required_text(d, "email").lower()
    password = d.get("senha", "")
    user = query("SELECT c.ID_Cliente,c.Nome_Cliente,cr.Senha_Hash FROM Cliente c "
                 "JOIN Credencial cr ON cr.ID_Cliente=c.ID_Cliente WHERE c.Email=%s",
                 (email,), one=True)
    if not user or not isinstance(password, str) or not check_password_hash(user["Senha_Hash"], password):
        raise ApiError("E-mail ou senha incorretos.", 401)
    session.clear()
    session["cliente_id"] = user["ID_Cliente"]
    return jsonify(id=user["ID_Cliente"], nome=user["Nome_Cliente"])


@app.post("/api/auth/sair")
def logout():
    session.clear()
    return jsonify(mensagem="Sessão encerrada.")


@app.get("/api/auth/eu")
@logged
def me():
    user = query("SELECT ID_Cliente id,Nome_Cliente nome,Email email FROM Cliente "
                 "WHERE ID_Cliente=%s", (session["cliente_id"],), one=True)
    return jsonify(user)


@app.get("/api/estados")
def states():
    return jsonify(query("SELECT ID_Estado id,Nome nome,Sigla sigla "
                         "FROM Estado ORDER BY Nome"))


@app.route("/api/unidades", methods=["GET", "POST"])
@logged
def units():
    if request.method == "GET":
        return jsonify(query("SELECT u.ID_Unidade id,c.Nome_Unidade nome," 
                             "c.Tipo_Unidade tipo,c.Tarifa_kWh tarifa "
                             "FROM Unidade_Consumidora u JOIN Configuracao_Unidade c "
                             "ON c.ID_Unidade=u.ID_Unidade "
                             "WHERE u.ID_Cliente=%s ORDER BY u.ID_Unidade",
                             (session["cliente_id"],)))
    d = data()
    name = required_text(d, "nome", 100)
    tipo = d.get("tipo")
    if tipo not in ("RESIDENCIA", "COMERCIO"):
        raise ApiError("Tipo deve ser RESIDENCIA ou COMERCIO.")
    cep = required_text(d, "cep", 9)
    rua = required_text(d, "rua", 100)
    numero = required_text(d, "numero", 10)
    complemento = str(d.get("complemento", "")).strip()[:100]
    uf_id = positive_int(d.get("estadoId"), "estadoId")
    tarifa = number(d.get("tarifa", 0.9), "tarifa", maximum=Decimal("10"))
    if not query("SELECT ID_Estado FROM Estado WHERE ID_Estado=%s", (uf_id,), one=True):
        raise ApiError("Estado não cadastrado.")
    address_id = write("INSERT INTO Endereco (Cep,Rua,Numero,Complemento,ID_Estado,ID_Cliente) "
                       "VALUES (%s,%s,%s,%s,%s,%s)",
                       (cep, rua, numero, complemento, uf_id, session["cliente_id"]))
    unit_id = write("INSERT INTO Unidade_Consumidora (ID_Cliente,ID_Endereco) VALUES (%s,%s)",
                    (session["cliente_id"], address_id))
    write("INSERT INTO Configuracao_Unidade (ID_Unidade,Nome_Unidade,Tipo_Unidade,Tarifa_kWh) "
          "VALUES (%s,%s,%s,%s)", (unit_id, name, tipo, tarifa))
    commit()
    return jsonify(id=unit_id, nome=name), 201


@app.route("/api/unidades/<int:unit_id>/comodos", methods=["GET", "POST"])
@logged
def rooms(unit_id):
    own_unit(unit_id)
    if request.method == "GET":
        return jsonify(query("SELECT ID_Comodo id,Nome_Comodo nome FROM Comodo "
                             "WHERE ID_Unidade=%s ORDER BY ID_Comodo", (unit_id,)))
    name = required_text(data(), "nome", 80)
    room_id = write("INSERT INTO Comodo (ID_Unidade,Nome_Comodo) VALUES (%s,%s)",
                    (unit_id, name))
    commit()
    return jsonify(id=room_id, nome=name), 201


@app.delete("/api/comodos/<int:room_id>")
@logged
def delete_room(room_id):
    own_room(room_id)
    write("DELETE FROM Comodo WHERE ID_Comodo=%s", (room_id,))
    commit()
    return jsonify(mensagem="Cômodo e histórico associado removidos.")


@app.get("/api/catalogo")
@logged
def catalog():
    return jsonify(query("SELECT ID_Tipo id,Nome nome,Potencia_Referencia_W potencia "
                         "FROM Aparelho_Catalogo ORDER BY Nome"))


@app.route("/api/comodos/<int:room_id>/aparelhos", methods=["GET", "POST"])
@logged
def appliances(room_id):
    own_room(room_id)
    if request.method == "GET":
        return jsonify(query("SELECT a.ID_Aparelho id,t.Nome tipo," 
                             "COALESCE(NULLIF(a.Nome_Personalizado,''),t.Nome) nome, "
                             "a.Potencia_W potencia FROM Aparelho a "
                             "JOIN Aparelho_Catalogo t ON t.ID_Tipo=a.ID_Tipo "
                             "WHERE a.ID_Comodo=%s ORDER BY a.ID_Aparelho", (room_id,)))
    d = data()
    tipo_id = positive_int(d.get("tipoId"), "tipoId")
    ref = query("SELECT Potencia_Referencia_W FROM Aparelho_Catalogo "
                "WHERE ID_Tipo=%s", (tipo_id,), one=True)
    if not ref:
        raise ApiError("Aparelho não encontrado no catálogo.")
    power = positive_int(d.get("potencia", ref["Potencia_Referencia_W"]), "potencia", 30000)
    name = str(d.get("nome", "")).strip()[:100]
    device_id = write("INSERT INTO Aparelho "
                      "(ID_Comodo,ID_Tipo,Nome_Personalizado,Potencia_W) "
                      "VALUES (%s,%s,%s,%s)", (room_id, tipo_id, name, power))
    commit()
    return jsonify(id=device_id), 201


@app.delete("/api/aparelhos/<int:device_id>")
@logged
def delete_appliance(device_id):
    own_appliance(device_id)
    write("DELETE FROM Aparelho WHERE ID_Aparelho=%s", (device_id,))
    commit()
    return jsonify(mensagem="Aparelho e histórico associado removidos.")


'''/@app.post("/api/aparelhos/<int:device_id>/simular")
@logged
def simulate(device_id):
    appliance = own_appliance(device_id)
    minutes = positive_int(data().get("minutos"), "minutos", 43200)
    kwh = (Decimal(appliance["Potencia_W"]) * minutes / Decimal("60000")).quantize(Decimal("0.000001"))
    write("INSERT INTO Consumo_Aparelho "
          "(ID_Aparelho,Duracao_Minutos,Energia_kWh) VALUES (%s,%s,%s)",
          (device_id, minutes, kwh))
    check_goal(appliance["ID_Unidade"])
    commit()
    return jsonify(energiaKwh=float(kwh), observacao="Estimativa calculada, não medição de sensor."), 201'''


@app.post("/api/aparelhos/<int:device_id>/simular")
@logged
def simulate(device_id):
    appliance = own_appliance(device_id)

    minutes = positive_int(
        data().get("minutos"), "minutos", 43200
    )

    kwh = (
        Decimal(appliance["Potencia_W"])
        * minutes
        / Decimal("60000")
    ).quantize(Decimal("0.000001"))

    write(
        """
        INSERT INTO Consumo_Aparelho
        (
            ID_Aparelho,
            Data_Hora,
            Duracao_Minutos,
            Energia_kWh,
            Origem
        )
        VALUES (%s, NOW(), %s, %s, 'SIMULACAO')
        """,
        (device_id, minutes, kwh)
    )

    check_goal(appliance["ID_Unidade"])
    commit()

    return jsonify(
        energiaKwh=float(kwh),
        observacao="Estimativa calculada, não medição de sensor."
    ), 201



def summary(unit_id):
    unit = query("SELECT c.Tarifa_kWh tarifa,c.Nome_Unidade nome FROM Configuracao_Unidade c "
                 "WHERE c.ID_Unidade=%s", (unit_id,), one=True)
    if not unit:
        raise ApiError("Configuração da unidade não encontrada.", 404)
    start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    room_rows = query("SELECT ID_Comodo id,Nome_Comodo nome FROM Comodo "
                      "WHERE ID_Unidade=%s ORDER BY ID_Comodo", (unit_id,))
    manual = query("SELECT a.ID_Comodo room,DATE(ca.Data_Hora) day,SUM(ca.Energia_kWh) kwh "
                   "FROM Consumo_Aparelho ca JOIN Aparelho a ON ca.ID_Aparelho=a.ID_Aparelho "
                   "JOIN Comodo c ON c.ID_Comodo=a.ID_Comodo "
                   "WHERE c.ID_Unidade=%s AND ca.Data_Hora >= %s "
                   "GROUP BY a.ID_Comodo, DATE(ca.Data_Hora)", (unit_id, start))
    readings = query("SELECT s.ID_Comodo room,DATE(l.Data_Hora) day,SUM(l.Energia_kWh) kwh "
                     "FROM Leitura_Sensor l JOIN Sensor_IoT s ON s.ID_Sensor=l.ID_Sensor "
                     "JOIN Comodo c ON c.ID_Comodo=s.ID_Comodo "
                     "WHERE c.ID_Unidade=%s AND l.Data_Hora >= %s "
                     "GROUP BY s.ID_Comodo, DATE(l.Data_Hora)", (unit_id, start))
    manual_by_room = {}
    sensor_by_room = {}
    for item in manual:
        manual_by_room.setdefault(item["room"], []).append(item)
    for item in readings:
        sensor_by_room.setdefault(item["room"], []).append(item)
    per_day = {}
    rooms_result = []
    gross = Decimal("0")
    tariff = Decimal(unit["tarifa"])
    for room in room_rows:
        # Se há qualquer leitura IoT no mês, não somar simulações desse cômodo:
        # as duas séries podem descrever a mesma energia.
        real = bool(sensor_by_room.get(room["id"]))
        entries = sensor_by_room.get(room["id"], []) if real else manual_by_room.get(room["id"], [])
        room_total = sum((Decimal(item["kwh"]) for item in entries), Decimal("0"))
        gross += room_total
        rooms_result.append({"id": room["id"], "nome": room["nome"], "kwh": round(float(room_total), 3),
                             "custo": round(float(room_total * tariff), 2),
                             "origem": "IOT" if real else "SIMULACAO"})
        for item in entries:
            day = item["day"].isoformat()
            per_day[day] = per_day.get(day, Decimal("0")) + Decimal(item["kwh"])
    renewable_row = query("SELECT COALESCE(SUM(gr.Energia_kWh),0) kwh "
                          "FROM Geracao_Renovavel gr JOIN Fonte_Renovavel f ON f.ID_Fonte=gr.ID_Fonte "
                          "WHERE f.ID_Unidade=%s AND gr.Data_Hora >= %s", (unit_id, start), one=True)
    renewable = Decimal(renewable_row["kwh"])
    net = max(Decimal("0"), gross - renewable)
    now = datetime.now()
    projection = (gross * Decimal(calendar.monthrange(now.year, now.month)[1]) /
                  Decimal(now.day)) if gross else Decimal("0")
    goal = query("SELECT Limite_kWh limite,Valor_Alerta_kWh aviso FROM Meta_Consumo "
                 "WHERE ID_Unidade=%s AND Mes_Ano=%s ORDER BY ID_Meta DESC LIMIT 1",
                 (unit_id, now.strftime("%m/%Y")), one=True)
    alerts = query("SELECT ID_Alerta id,Tipo_Alerta tipo,Mensagem mensagem,Data_Hora data "
                   "FROM Alerta WHERE ID_Unidade=%s ORDER BY Data_Hora DESC LIMIT 12", (unit_id,))
    return {
        "unidade": unit["nome"], "mes": now.strftime("%m/%Y"),
        "totalKwh": round(float(gross), 3), "renovavelKwh": round(float(renewable), 3),
        "liquidoKwh": round(float(net), 3), "custoEstimado": round(float(net * tariff), 2),
        "previsaoMesKwh": round(float(projection), 2), "tarifa": float(tariff),
        "meta": {"limite": float(goal["limite"]), "aviso": float(goal["aviso"])} if goal else None,
        "comodos": rooms_result,
        "serie": [{"dia": day, "kwh": round(float(value), 3)} for day, value in sorted(per_day.items())],
        "alertas": [{"id": a["id"], "tipo": a["tipo"], "mensagem": a["mensagem"],
                     "data": a["data"].isoformat()} for a in alerts],
        "nota": "Aparelhos produzem estimativas. Se existir medição IoT no mês, ela substitui as simulações daquele cômodo."
    }


def check_goal(unit_id):
    view = summary(unit_id)
    if not view["meta"]:
        return
    used = Decimal(str(view["totalKwh"]))
    for kind, threshold, msg in (
        ("META_AVISO", Decimal(str(view["meta"]["aviso"])), "Atenção: consumo atingiu o patamar de aviso."),
        ("META_EXCEDIDA", Decimal(str(view["meta"]["limite"])), "O consumo já atingiu sua meta mensal."),
    ):
        if used >= threshold and not query(
            "SELECT ID_Alerta FROM Alerta WHERE ID_Unidade=%s AND Tipo_Alerta=%s "
            "AND Data_Hora >= %s LIMIT 1",
            (unit_id, kind, datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)), one=True
        ):
            write("INSERT INTO Alerta (Tipo_Alerta,Mensagem,Data_Hora,ID_Unidade) "
                  "VALUES (%s,%s,NOW(),%s)", (kind, msg, unit_id))


@app.get("/api/unidades/<int:unit_id>/resumo")
@logged
def dashboard(unit_id):
    own_unit(unit_id)
    return jsonify(summary(unit_id))


@app.post("/api/unidades/<int:unit_id>/meta")
@logged
def set_goal(unit_id):
    own_unit(unit_id)
    d = data()
    limit = number(d.get("limite"), "limite", Decimal("0.01"), Decimal("100000"))
    warning = (limit * Decimal("0.8")).quantize(Decimal("0.01"))
    month = datetime.now().strftime("%m/%Y")
    old = query("SELECT ID_Meta FROM Meta_Consumo WHERE ID_Unidade=%s AND Mes_Ano=%s "
                "ORDER BY ID_Meta DESC LIMIT 1", (unit_id, month), one=True)
    if old:
        write("UPDATE Meta_Consumo SET Limite_kWh=%s,Valor_Alerta_kWh=%s WHERE ID_Meta=%s",
              (limit, warning, old["ID_Meta"]))
    else:
        write("INSERT INTO Meta_Consumo(Mes_Ano,Limite_kWh,Valor_Alerta_kWh,ID_Unidade) "
              "VALUES(%s,%s,%s,%s)", (month, limit, warning, unit_id))
    check_goal(unit_id)
    commit()
    return jsonify(limite=float(limit), aviso=float(warning))


@app.route("/api/unidades/<int:unit_id>/sensores", methods=["GET", "POST"])
@logged
def sensors(unit_id):
    own_unit(unit_id)
    if request.method == "GET":
        return jsonify(query("SELECT s.ID_Sensor id,s.Nome nome,c.ID_Comodo comodoId," 
                             "c.Nome_Comodo comodo FROM Sensor_IoT s "
                             "JOIN Comodo c ON c.ID_Comodo=s.ID_Comodo "
                             "WHERE c.ID_Unidade=%s ORDER BY s.ID_Sensor", (unit_id,)))
    d = data()
    room_id = positive_int(d.get("comodoId"), "comodoId")
    room = own_room(room_id)
    if room["ID_Unidade"] != unit_id:
        raise ApiError("Cômodo não pertence à unidade.", 403)
    name = required_text(d, "nome")
    api_key = secrets.token_urlsafe(32)
    sensor_id = write("INSERT INTO Sensor_IoT(ID_Comodo,Nome,Chave_SHA256) VALUES (%s,%s,%s)",
                      (room_id, name, hashlib.sha256(api_key.encode()).hexdigest()))
    commit()
    return jsonify(id=sensor_id, chave=api_key, aviso="Guarde a chave: ela será mostrada apenas agora."), 201


@app.post("/api/iot/leituras")
def ingest_reading():
    d = data()
    sensor_id = positive_int(d.get("sensorId"), "sensorId")
    key = request.headers.get("X-Sensor-Key", "")
    sensor = query("SELECT s.Chave_SHA256 hash,c.ID_Unidade unidade FROM Sensor_IoT s "
                   "JOIN Comodo c ON c.ID_Comodo=s.ID_Comodo WHERE s.ID_Sensor=%s", (sensor_id,), one=True)
    if not sensor or not hmac.compare_digest(sensor["hash"], hashlib.sha256(key.encode()).hexdigest()):
        raise ApiError("Sensor ou chave inválidos.", 401)
    power = number(d.get("potenciaW"), "potenciaW", maximum=Decimal("30000"))
    duration = positive_int(d.get("duracaoMinutos"), "duracaoMinutos", 1440)
    kwh = (power * duration / Decimal("60000")).quantize(Decimal("0.000001"))
    write("INSERT INTO Leitura_Sensor (ID_Sensor,Potencia_W,Duracao_Minutos,Energia_kWh) "
          "VALUES(%s,%s,%s,%s)", (sensor_id, power, duration, kwh))
    if power >= 5000 and not query("SELECT ID_Alerta FROM Alerta WHERE ID_Unidade=%s "
                                   "AND Tipo_Alerta='PICO_POTENCIA' "
                                   "AND DATE(Data_Hora)=CURRENT_DATE LIMIT 1",
                                   (sensor["unidade"],), one=True):
        write("INSERT INTO Alerta (Tipo_Alerta,Mensagem,Data_Hora,ID_Unidade) "
              "VALUES ('PICO_POTENCIA','Sensor detectou potência de 5 kW ou mais.',NOW(),%s)",
              (sensor["unidade"],))
    check_goal(sensor["unidade"])
    commit()
    return jsonify(energiaKwh=float(kwh), modo="MEDICAO_IOT_RECEBIDA"), 201


@app.route("/api/unidades/<int:unit_id>/renovaveis", methods=["GET", "POST"])
@logged
def renewables(unit_id):
    own_unit(unit_id)
    if request.method == "GET":
        return jsonify(query("SELECT ID_Fonte id,Nome nome,Tipo tipo FROM Fonte_Renovavel "
                             "WHERE ID_Unidade=%s ORDER BY ID_Fonte", (unit_id,)))
    d = data()
    name = required_text(d, "nome")
    tipo = d.get("tipo")
    if tipo not in ("SOLAR", "EOLICA", "OUTRA"):
        raise ApiError("Tipo de fonte inválido.")
    source_id = write("INSERT INTO Fonte_Renovavel (ID_Unidade,Nome,Tipo) VALUES (%s,%s,%s)",
                      (unit_id, name, tipo))
    commit()
    return jsonify(id=source_id), 201


@app.post("/api/renovaveis/<int:source_id>/geracao")
@logged
def register_generation(source_id):
    row = query("SELECT f.ID_Unidade FROM Fonte_Renovavel f "
                "JOIN Unidade_Consumidora u ON u.ID_Unidade=f.ID_Unidade "
                "WHERE f.ID_Fonte=%s AND u.ID_Cliente=%s",
                (source_id, session["cliente_id"]), one=True)
    if not row:
        raise ApiError("Fonte não encontrada.", 404)
    kwh = number(data().get("energiaKwh"), "energiaKwh", Decimal("0.000001"))
    write("INSERT INTO Geracao_Renovavel(ID_Fonte,Energia_kWh) VALUES (%s,%s)",
          (source_id, kwh))
    commit()
    return jsonify(energiaKwh=float(kwh)), 201


@app.post("/api/unidades/<int:unit_id>/previsoes")
@logged
def save_forecast(unit_id):
    own_unit(unit_id)
    forecast = Decimal(str(summary(unit_id)["previsaoMesKwh"]))
    now = datetime.now()
    last_day = now.replace(day=calendar.monthrange(now.year, now.month)[1]).date()
    # Mantém a grafia da coluna presente no SQL original: Cosumo_kWh.
    old = query("SELECT ID_Previsao FROM Previsao_Consumo WHERE ID_Unidade=%s "
                "AND Data_Previsao=%s ORDER BY ID_Previsao DESC LIMIT 1",
                (unit_id, last_day), one=True)
    if old:
        write("UPDATE Previsao_Consumo SET Cosumo_kWh=%s,Possibilidade=%s "
              "WHERE ID_Previsao=%s", (forecast, "PROJECAO_LINEAR", old["ID_Previsao"]))
    else:
        write("INSERT INTO Previsao_Consumo "
              "(Cosumo_kWh,Data_Previsao,Possibilidade,ID_Unidade) "
              "VALUES(%s,%s,%s,%s)", (forecast, last_day, "PROJECAO_LINEAR", unit_id))
    commit()
    return jsonify(previsaoMesKwh=float(forecast), dataPrevisao=last_day.isoformat())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.getenv("FLASK_DEBUG", "0") == "1")
