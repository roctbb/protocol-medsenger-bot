import json
import time
from threading import Thread
from flask import Flask, request, render_template
from config import *
import threading
import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from agents_api import *

app = Flask(__name__)
db_string = "postgres://{}:{}@{}:{}/{}".format(DB_LOGIN, DB_PASSWORD, DB_HOST, DB_PORT, DB_DATABASE)
app.config['SQLALCHEMY_DATABASE_URI'] = db_string
db = SQLAlchemy(app)


class Contract(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column(db.Boolean, default=True)
    protocols = relationship('Protocol', secondary='contractprotocols')


class Protocol(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column(db.Boolean, default=True)
    contracts = relationship('Contract', secondary='contractprotocols')


class ContractProtocols(db.Model):
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id'), primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey('protocol.id'), primary_key=True)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column(db.Boolean, default=True)
    contracts = relationship('Contract', secondary='contractprotocols')

try:
    db.create_all()
except:
    print('cant create structure')


def delayed(delay, f, args):
    timer = threading.Timer(delay, f, args=args)
    timer.start()


def check_digit(number):
    try:
        int(number)
        return True
    except:
        return False


def gts():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")





@app.route('/status', methods=['POST'])
def status():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    contract_ids = [l[0] for l in db.session.query(Contract.id).all()]

    answer = {
        "is_tracking_data": True,
        "supported_scenarios": [],
        "tracked_contracts": contract_ids
    }
    print(answer)

    return json.dumps(answer)


@app.route('/init', methods=['POST'])
def init():
    data = request.json

    if data['api_key'] != APP_KEY:
        return 'invalid key'

    try:
        contract_id = int(data['contract_id'])
        query = Contract.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()
            contract.active = True
            contract.last_push = 0

            print("{}: Reactivate contract {}".format(gts(), contract.id))
        else:
            contract = Contract(id=contract_id)
            db.session.add(contract)

            print("{}: Add contract {}".format(gts(), contract.id))

        db.session.commit()


    except Exception as e:
        print(e)
        return "error"

    print('sending ok')
    delayed(1, send_iteration, [])
    return 'ok'


@app.route('/remove', methods=['POST'])
def remove():
    data = request.json

    if data['api_key'] != APP_KEY:
        print('invalid key')
        return 'invalid key'

    try:
        contract_id = str(data['contract_id'])
        query = Contract.query.filter_by(id=contract_id)

        if query.count() != 0:
            contract = query.first()
            contract.active = False

            db.session.commit()

            print("{}: Deactivate contract {}".format(gts(), contract.id))
        else:
            print('contract not found')

    except Exception as e:
        print(e)
        return "error"

    return 'ok'


@app.route('/settings', methods=['GET'])
def settings():
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id'))
        query = Contract.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()
        else:
            return "<strong>Ошибка. Контракт не найден.</strong> Попробуйте отключить и снова подключить интеллектуальный агент к каналу консультирвоания.  Если это не сработает, свяжитесь с технической поддержкой."

    except Exception as e:
        print(e)
        return "error"

    return render_template('settings.html', contract=contract)


@app.route('/settings', methods=['POST'])
def setting_save():
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id'))
        query = Contract.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()
            contract.mode = int(request.form.get('mode', 0))
            contract.scenario = int(request.form.get('scenario', 0))
            db.session.commit()
        else:
            return "<strong>Ошибка. Контракт не найден.</strong> Попробуйте отключить и снова подключить интеллектуальный агент к каналу консультирвоания.  Если это не сработает, свяжитесь с технической поддержкой."

    except Exception as e:
        print(e)
        return "error"

    return """
        <strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>
        """


@app.route('/', methods=['GET'])
def index():
    return 'waiting for the thunder!'


def send(contract_id):
    try:
        send_message(contract_id, "Пожалуйста, заполните анкету кардиомониторинга.", action_link="frame",
                     action_name="Заполнить анкету", action_onetime=True, only_doctor=False, only_patient=True,
                     action_deadline=int(time.time()) + 24 * 59 * 60)
    except Exception as e:
        print('connection error', e)


def send_warning(contract_id, a, scenario):
    diagnosis = "сердечной недостаточности"
    if scenario == 1:
        diagnosis = "стенокардии"
    elif scenario == 2:
        diagnosis = "фибрилляции предсердий"

    try:
        send_message(contract_id,
                     text="По итогам опроса и мониторинга у вас налюдаются следующие симптомы {}:\n - {}\n\nМы направили уведомление о симптомах вашему лечащему врачу, он свяжется с вами в ближайшее время.".format(
                         diagnosis, '\n - '.join(a)),
                     is_urgent=True, only_patient=True)
        send_message(contract_id, text="У пациента наблюдаются симптомы {} ({}).".format(diagnosis, ' / '.join(a)),
                     is_urgent=True, only_doctor=True, need_answer=True)
    except Exception as e:
        print('connection error', e)


def send_iteration():
    contracts = Contract.query.all()
    now = datetime.datetime.now()
    hour = now.hour
    for contract in contracts:
        pass

    db.session.commit()
    time.sleep(60 * 5)


def sender():
    while True:
        send_iteration()


@app.route('/message', methods=['POST'])
def save_message():
    data = request.json
    key = data['api_key']

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    return "ok"


@app.route('/frame', methods=['GET'])
def action():
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id', -1))
        query = Contract.query.filter_by(id=contract_id)

        if query.count() == 0:
            return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

        return render_template('measurement{}.html'.format(query.first().scenario))

    except:
        return "error"


@app.route('/frame', methods=['POST'])
def action_save():
    key = request.args.get('api_key', '')
    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id', -1))
        query = Contract.query.filter_by(id=contract_id)
        if query.count() == 0:
            return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."
    except:
        return "error"

    contract = query.first()

    # TODO

    print("{}: Form from {}".format(gts(), contract_id))

    return """
            <strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>
            """


t = Thread(target=sender)
t.start()

app.run(port=PORT, host=HOST)
