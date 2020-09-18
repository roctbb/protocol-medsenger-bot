import json
import time
from threading import Thread
from flask import Flask, request, render_template
from datetime import datetime
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
    protocols = relationship('Protocol', secondary='contract_protocols')
    events = relationship('Event', secondary='event_results')


class Protocol(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(512))
    description = db.Column(db.Text, nullable=True)
    contracts = relationship('Contract', secondary='contract_protocols')
    events = db.relationship('Event', backref='protocol', lazy=True)


class ContractProtocols(db.Model):
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id'), primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey('protocol.id'), primary_key=True)
    start = db.Column(db.Date, nullable=True)


class EventResults(db.Model):
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id'), primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), primary_key=True)

    patient_confirmation = db.Column(db.Date, nullable=True)
    doctor_confirmation = db.Column(db.Date, nullable=True)

    patient_comment = db.Column(db.Text, nullable=True)
    doctor_comment = db.Column(db.Text, nullable=True)


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    patient_title = db.Column(db.String(512))
    patient_description = db.Column(db.Text, nullable=True)
    doctor_title = db.Column(db.String(512))
    doctor_description = db.Column(db.Text, nullable=True)

    start_day = db.Column(db.Integer, default=0)
    end_day = db.Column(db.Integer, nullable=True)
    notification_day = db.Column(db.Integer, nullable=True)

    notify_doctor = db.Column(db.Boolean, default=False)
    notify_patient = db.Column(db.Boolean, default=False)

    need_confirmation_doctor = db.Column(db.Boolean, default=False)
    need_confirmation_patient = db.Column(db.Boolean, default=False)

    need_comment_doctor = db.Column(db.Boolean, default=False)
    need_comment_patient = db.Column(db.Boolean, default=False)

    protocol_id = db.Column(db.Integer, db.ForeignKey('protocol.id'),
                            nullable=False)

    def get_patient_message(self, contract):
        return (self.patient_title, self.patient_text)

    def get_doctor_message(self, contract):
        if self.doctor_title:
            title = self.doctor_title
        else:
            title = self.patient_title

        if self.doctor_text:
            text = self.doctor_text
        else:
            text = self.patient_text

        message = "<b>{}</b><br><br>{}<br><br><small>Планируемый срок выполения - с <b>{}</b> по <b>{}</b></small>".format(
            title, text, contract.start + datetime.timedelta(days=self.start_day),
                         contract.start + datetime.timedelta(days=self.end_day))

        return message


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


def validate_date(date):
    try:
        datetime.strptime(date, '%Y-%m-%d')
        return True
    except:
        return False


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
            protocols = Protocol.query.all()

            for protocol in protocols:
                if request.form.get('protocol_{}'.format(protocol.id), None) == 'on':
                    if protocol in contract.protocols and validate_date(
                            request.form.get('protocol_{}_date'.format(protocol.id))):
                        connection = ContractProtocols.query.filter_by(contract_id=contract_id,
                                                                       protocol_id=protocol.id).first()
                        connection.start = request.form.get('protocol_{}_date'.format(protocol.id))

                    elif protocol not in contract.protocols:
                        connection = ContractProtocols(contract_id=contract_id, protocol_id=protocol.id)
                        if validate_date(request.form.get('protocol_{}_date'.format(protocol.id))):
                            connection.start = request.form.get('protocol_{}_date'.format(protocol.id))
                else:
                    if protocol in contract.protocols:
                        ContractProtocols.query.filter_by(contract_id=contract_id, protocol_id=protocol.id).delete()

            db.session.commit()
        else:
            return "<strong>Ошибка. Контракт не найден.</strong> Попробуйте отключить и снова подключить интеллектуальный агент к каналу консультирвоания.  Если это не сработает, свяжитесь с технической поддержкой."

    except Exception as e:
        print(e)
        return "error"

    return """
        <strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>
        """


@app.route('/<role>/event/<event_id>', methods=['GET'])
def save_event_page(role, event_id):
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id', ''))
        event_id = int(event_id)

        if role not in ['doctor', 'patient']:
            return "error"

        contract_query = Contract.query.filter_by(id=contract_id)
        event_query = Event.query.filter_by(id=event_id)

        if contract_query.count() == 0:
            return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

        if event_query.count() == 0:
            return "<strong>Запрашиваемое событие не найдено.</strong> Свяжитесь с технической поддержкой."

        contract = contract_query.first()
        event = event_query.first()

        if event.protocol not in contract.protocols:
            return "<strong>Запрашиваемое событие не найдено.</strong> Скорее всего этот протокол лечения уже отменен врачом."

        if (role == 'doctor' and not event.need_comment_doctor) or (
                role == 'patient' and not event.need_comment_patient):
            if role == 'doctor':
                EventResults(event_id=event_id, contract_id=contract_id, doctor_confirmation=datetime.today().date())
            if role == 'patient':
                EventResults(event_id=event_id, contract_id=contract_id, doctor_confirmation=datetime.today().date())
            db.session.commit()
            return "<strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>"

        return render_template('event.html', contract=contract, event=event)

    except:
        return "error"


@app.route('/<role>/event/<event_id>', methods=['POST'])
def save_event(role, event_id):
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        contract_id = int(request.args.get('contract_id', ''))
        event_id = int(event_id)

        if role not in ['doctor', 'patient']:
            return "error"

        contract_query = Contract.query.filter_by(id=contract_id)
        event_query = Event.query.filter_by(id=event_id)

        if contract_query.count() == 0:
            return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

        if event_query.count() == 0:
            return "<strong>Запрашиваемое событие не найдено.</strong> Свяжитесь с технической поддержкой."

        contract = contract_query.first()
        event = event_query.first()

        if event.protocol not in contract.protocols:
            return "<strong>Запрашиваемое событие не найдено.</strong> Скорее всего этот протокол лечения уже отменен врачом."

        comment = request.form.get('comment')
        date = request.form.get('date')

        if not comment or not validate_date(date):
            return "<strong>Ошибки при заполнении формы.</strong> Пожалуйста, что все поля заполнены.<br><a onclick='history.go(-1);'>Назад</a>"

        if role == 'doctor':
            EventResults(event_id=event_id, contract_id=contract_id, doctor_confirmation=date, doctor_comment=comment)
        if role == 'patient':
            EventResults(event_id=event_id, contract_id=contract_id, patient_confirmation=date, patient_comment=comment)
        db.session.commit()

        return "<strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>"

    except:
        return "error"


@app.route('/', methods=['GET'])
def index():
    return 'waiting for the thunder!'


def get_days(A, B):
    return (A - B).days


def send_iteration():
    contracts = Contract.query.all()
    today = datetime.today().date()

    for contract in contracts:
        for protocol in contract.protocols:
            for event in protocol.events:
                if get_days(event.notification_day, today) == 0 and not EventResults.query.filter_by(event_id=event.id,
                                                                                                     contract_id=contract.id).count():
                    EventResults(event_id=event.id, contract_id=contract.id)

                    if event.notify_doctor:
                        text = event.get_doctor_message()

                        if not event.need_confirmation_doctor:
                            action_link = "doctor/event/{}".format(event.id)
                            action_name = "Подтвердить выполнение"
                        else:
                            action_link = None
                            action_name = None

                        send_message(contract_id=contract.id, text=text, only_doctor=True, action_link=action_link,
                                     action_name=action_name, action_onetime=True)

                    if event.notify_patient:
                        text = event.get_doctor_message()

                        if not event.need_confirmation_doctor:
                            action_link = "doctor/event/{}".format(event.id)
                            action_name = "Подтвердить выполнение"
                        else:
                            action_link = None
                            action_name = None

                        send_message(contract_id=contract.id, text=text, only_patient=True, action_link=action_link,
                                     action_name=action_name, action_onetime=True)

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


t = Thread(target=sender)
t.start()

app.run(port=PORT, host=HOST)
