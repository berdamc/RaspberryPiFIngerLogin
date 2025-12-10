import time
from flask import Flask, jsonify, request, render_template, redirect, url_for, session
import board
from digitalio import DigitalInOut, Direction
import adafruit_fingerprint
import serial
from functools import wraps
from datetime import datetime  # adicionado para timestamp no log

led = DigitalInOut(board.D13)
led.direction = Direction.OUTPUT

uart = serial.Serial("/dev/ttyS0", baudrate=57600, timeout=1)
finger = adafruit_fingerprint.Adafruit_Fingerprint(uart)

app = Flask(__name__)
app.secret_key = "uma_chave_secreta_aqui"

USERNAME = "rasp"
PASSWORD = "rasp"

def log_operation(operation_description):
    log_file = 'log.txt'
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f'[{timestamp}] {operation_description}\n')

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated

def get_fingerprint():
    while finger.get_image() != adafruit_fingerprint.OK:
        pass
    if finger.image_2_tz(1) != adafruit_fingerprint.OK:
        return False
    if finger.finger_fast_search() != adafruit_fingerprint.OK:
        return False
    return True

def get_next_available_id():
    try:
        used_indices = finger.templates
        for i in range(1, 128):
            if i not in used_indices:
                return i
        return None
    except Exception:
        return None

def enroll_finger(location):
    for fingerimg in range(1, 3):
        while True:
            i = finger.get_image()
            if i == adafruit_fingerprint.OK:
                break
            elif i == adafruit_fingerprint.NOFINGER:
                continue
            else:
                return False
        if finger.image_2_tz(fingerimg) != adafruit_fingerprint.OK:
            return False
        if fingerimg == 1:
            time.sleep(1)
            while finger.get_image() != adafruit_fingerprint.NOFINGER:
                pass
    if finger.create_model() != adafruit_fingerprint.OK:
        return False
    if finger.store_model(location) != adafruit_fingerprint.OK:
        return False
    return True

def delete_finger(location):
    return finger.delete_model(location) == adafruit_fingerprint.OK

@app.route("/")
def home():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    return render_template("login.html", error=None)

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    if username == USERNAME and password == PASSWORD:
        session["user"] = username
        log_operation(f"Usuário '{username}' logou com sucesso.")
        return redirect(url_for("dashboard"))
    log_operation(f"Tentativa de login falhou para usuário '{username}'.")
    return render_template("login.html", error="Usuário ou senha inválidos")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/logout")
def logout():
    user = session.get("user")
    session.pop("user", None)
    if user:
        log_operation(f"Usuário '{user}' realizou logout.")
    return redirect(url_for("home"))

@app.route("/templates", methods=["GET"])
@login_required
def list_templates():
    if finger.read_templates() != adafruit_fingerprint.OK:
        log_operation("Falha ao ler os templates de digitais.")
        return "Falha ao ler os templates", 500

    banco = {}
    try:
        with open("banco.txt", "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    partes = linha.split(",", 1)
                    if len(partes) == 2:
                        indice, nome = partes
                        banco[int(indice)] = nome
    except FileNotFoundError:
        log_operation("Arquivo banco.txt não encontrado ao listar templates.")
        return "Arquivo banco.txt não encontrado", 500

    linhas = []
    for idx in finger.templates:
        nome = banco.get(idx, "Desconhecido")
        linhas.append(f"{idx}:{nome}")

    log_operation("Templates listados com sucesso.")
    return "<br>".join(linhas)

@app.route("/enroll", methods=["POST"])
@login_required
def enroll():
    try:
        data = request.get_json()
        name = data.get("name")

        if not name or not name.strip():
            log_operation("Tentativa de cadastro com nome inválido.")
            return jsonify({"error": "Nome inválido"}), 400

        location = get_next_available_id()
        if location is None:
            log_operation("Falha no cadastro: não há índices disponíveis.")
            return jsonify({"error": "Não há índices disponíveis"}), 400

        success = enroll_finger(location)
        if not success:
            log_operation(f"Falha ao cadastrar digital para '{name.strip()}' no índice {location}.")
            return jsonify({"error": "Falha ao cadastrar digital"}), 500

        try:
            with open("banco.txt", "r", encoding="utf-8") as f:
                linhas = f.readlines()
        except FileNotFoundError:
            linhas = []

        linhas = [linha for linha in linhas if not linha.startswith(f"{location},")]
        linhas.append(f"{location},{name.strip()}\n")

        with open("banco.txt", "w", encoding="utf-8") as f:
            f.writelines(linhas)

        log_operation(f"Digital cadastrada: '{name.strip()}' no índice {location}.")
        return jsonify({"success": True, "id": location, "name": name.strip()})

    except Exception as e:
        log_operation(f"Erro inesperado ao cadastrar digital: {str(e)}")
        return jsonify({"error": f"Erro inesperado: {str(e)}"}), 500

@app.route("/find", methods=["GET"])
@login_required
def find():
    try:
        if get_fingerprint():
            log_operation(f"Digital encontrada: ID {finger.finger_id} com confiança {finger.confidence}.")
            return jsonify({
                "found": True,
                "id": finger.finger_id,
                "confidence": finger.confidence
            })
        else:
            log_operation("Digital não encontrada na busca.")
            return jsonify({"found": False})
    except AttributeError:
        log_operation("Erro: dados da digital ausentes ou corrompidos na busca.")
        return jsonify({"error": "Fingerprint data is missing or corrupted"}), 500
    except Exception as e:
        log_operation(f"Erro inesperado na busca de digital: {str(e)}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route("/delete", methods=["POST"])
@login_required
def delete():
    try:
        data = request.json
        location = data.get("id")

        if not location or not (1 <= location <= 127):
            log_operation(f"Tentativa de exclusão com ID inválido: {location}")
            return jsonify({"error": "Invalid ID (must be 1-127)"}), 400

        success = delete_finger(location)

        try:
            with open("banco.txt", "r", encoding="utf-8") as f:
                linhas = f.readlines()
        except FileNotFoundError:
            linhas = []

        linhas = [linha for linha in linhas if not linha.startswith(f"{location},")]

        with open("banco.txt", "w", encoding="utf-8") as f:
            f.writelines(linhas)

        if success:
            log_operation(f"Digital no índice {location} excluída com sucesso.")
        else:
            log_operation(f"Falha ao excluir digital no índice {location}.")

        return jsonify({"success": success})

    except ValueError:
        log_operation("Erro: tipo de dado inválido para ID na exclusão.")
        return jsonify({"error": "Invalid data type for ID"}), 400
    except Exception as e:
        log_operation(f"Erro inesperado na exclusão de digital: {str(e)}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=True)
    finally:
        uart.close()
        print("UART Closed")
