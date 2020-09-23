import json
import sys
import time
from threading import Thread
from flask import Flask, request, render_template
from datetime import datetime, timedelta
from config import *
import threading
from flask_sqlalchemy import SQLAlchemy
from agents_api import *

app = Flask(__name__)
db_string = "postgres://{}:{}@{}:{}/{}".format(DB_LOGIN, DB_PASSWORD, DB_HOST, DB_PORT, DB_DATABASE)
app.config['SQLALCHEMY_DATABASE_URI'] = db_string
db = SQLAlchemy(app)


class Contract(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    active = db.Column(db.Boolean, default=True)
    protocols = db.relationship('Protocol', secondary='contract_protocols')
    events = db.relationship('Event', secondary='event_results')


class Protocol(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(512))
    description = db.Column(db.Text, nullable=True)
    contracts = db.relationship('Contract', secondary='contract_protocols')
    events = db.relationship('Event', backref='protocol', lazy=True)

    def get_connection(self, contract):
        return ContractProtocols.query.filter_by(contract_id=contract.id, protocol_id=self.id).first()


class ContractProtocols(db.Model):
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id'), primary_key=True)
    protocol_id = db.Column(db.Integer, db.ForeignKey('protocol.id'), primary_key=True)
    start = db.Column(db.Date, nullable=True)

    def get_event_start_date(self, event):
        return self.start + timedelta(days=event.start_day)

    def get_event_end_date(self, event):
        if not event.end_day:
            return None
        return self.start + timedelta(days=event.end_day)

    def get_notification_date(self, event):
        if event.notify_doctor or event.notify_patient:
            return self.start + timedelta(days=event.notification_day)
        return None

    def get_formatted_event_start_date(self, event):
        return format(self.get_event_start_date(event))

    def get_formatted_event_end_date(self, event):
        return format(self.get_event_end_date(event))

    def get_formatted_notification_date(self, event):
        return format(self.get_notification_date(event))


class EventResults(db.Model):
    contract_id = db.Column(db.Integer, db.ForeignKey('contract.id'), primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), primary_key=True)

    patient_confirmation = db.Column(db.Date, nullable=True)
    doctor_confirmation = db.Column(db.Date, nullable=True)

    patient_comment = db.Column(db.Text, nullable=True)
    doctor_comment = db.Column(db.Text, nullable=True)

    def get_patient_confirmation(self):
        if not self.patient_confirmation:
            return None
        return self.patient_confirmation.strftime('%d.%m.%y')

    def get_doctor_confirmation(self):
        if not self.doctor_confirmation:
            return None
        return self.doctor_confirmation.strftime('%d.%m.%y')


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

    def get_patient_message(self, protocol: ContractProtocols):
        text = self.patient_description
        title = self.patient_title

        message = "<b>{}</b><br><br>{}<br><br><small>Планируемый срок выполения - с <b>{}</b> по <b>{}</b></small>".format(
            title, text, protocol.start + timedelta(days=self.start_day),
                         protocol.start + timedelta(days=self.end_day))

        return message

    def get_doctor_message(self, protocol: ContractProtocols):
        if self.doctor_title:
            title = self.doctor_title
        else:
            title = self.patient_title

        if self.doctor_description:
            text = self.doctor_description
        else:
            text = self.patient_description

        message = "<b>{}</b><br><br>{}<br><br><small>Планируемый срок выполения - с <b>{}</b> по <b>{}</b></small>".format(
            title, text, protocol.start + timedelta(days=self.start_day),
                         protocol.start + timedelta(days=self.end_day))

        return message

    def get_doctor_title(self):
        if self.doctor_title:
            title = self.doctor_title
        else:
            title = self.patient_title

        return title


try:
    db.create_all()
except:
    print('cant create structure')


def delayed(delay, f, args):
    timer = threading.Timer(delay, f, args=args)
    timer.start()


def format(date):
    if not date:
        return None
    return date.strftime('%d.%m.%y')


def check_digit(number):
    try:
        int(number)
        return True
    except:
        return False


def gts():
    now = datetime.now()
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


@app.route('/actions', methods=['POST'])
def actions():
    data = request.json

    if data['api_key'] != APP_KEY:
        print('invalid key')
        return 'invalid key'

    actions = []

    try:
        contract_id = str(data['contract_id'])
        query = Contract.query.filter_by(id=contract_id)

        if query.count() != 0:
            contract = query.first()

            for protocol in contract.protocols:
                actions.append({
                    "name": 'Протокол "{}"'.format(protocol.title),
                    "link": "/protocol/{}".format(protocol.id),
                    "type": "doctor"
                })

        return json.dumps(actions)

    except Exception as e:
        print(e)
        return "error"


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

    protocols = Protocol.query.all()
    connections = {}

    try:
        contract_id = int(request.args.get('contract_id'))
        query = Contract.query.filter_by(id=contract_id)
        if query.count() != 0:
            contract = query.first()

            for protocol in contract.protocols:
                connections[protocols.id] = ContractProtocols.query.filter_by(contract_id=contract_id,
                                                                              protocol_id=protocol.id).first()
        else:
            return "<strong>Ошибка. Контракт не найден.</strong> Попробуйте отключить и снова подключить интеллектуальный агент к каналу консультирвоания.  Если это не сработает, свяжитесь с технической поддержкой."

    except Exception as e:
        print(e)
        return "error"

    return render_template('settings.html', contract=contract, protocols=protocols, connections=connections)


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
                        db.session.add(connection)

                    elif protocol not in contract.protocols:
                        connection = ContractProtocols(contract_id=contract_id, protocol_id=protocol.id)
                        if validate_date(request.form.get('protocol_{}_date'.format(protocol.id))):
                            connection.start = request.form.get('protocol_{}_date'.format(protocol.id))

                        db.session.add(connection)
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
            result = EventResults.query.filter_by(event_id=event_id, contract_id=contract_id).first()
            if role == 'doctor':
                result.doctor_confirmation = datetime.today().date()
            if role == 'patient':
                result.patient_confirmation = datetime.today().date()
            db.session.commit()

            return "<strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>"

        return render_template('event.html', contract=contract, event=event)

    except:
        return "error"


@app.route('/protocol/<protocol_id>', methods=['GET'])
def protocol_page(protocol_id):
    key = request.args.get('api_key', '')

    if key != APP_KEY:
        return "<strong>Некорректный ключ доступа.</strong> Свяжитесь с технической поддержкой."

    try:
        today = datetime.today().date()
        contract_id = int(request.args.get('contract_id', ''))
        protocol_id = int(protocol_id)

        contract_query = Contract.query.filter_by(id=contract_id)
        events = Event.query.filter_by(protocol_id=protocol_id).all()

        if contract_query.count() == 0:
            return "<strong>Запрашиваемый канал консультирования не найден.</strong> Попробуйте отключить и заного подключить интеллектуального агента. Если это не сработает, свяжитесь с технической поддержкой."

        event_results = {}
        event_periods = {}
        event_notifications = {}
        event_status = {}

        protocol = Protocol.query.get(protocol_id)
        contract = Contract.query.get(contract_id)

        for event in events:
            result_query = EventResults.query.filter_by(event_id=event.id, contract_id=contract_id)

            if result_query.count():
                event_results[event.id] = result_query.first()

            connection = protocol.get_connection(contract)
            S = connection.get_formatted_event_start_date(event)
            E = connection.get_formatted_event_end_date(event)

            if E:
                event_periods[event.id] = "{} - {}".format(S, E)
            else:
                event_periods[event.id] = S

            event_notifications[event.id] = connection.get_formatted_notification_date(event)

            if event.id in event_results:
                end_date = connection.get_event_end_date(event)
                if (not event.need_confirmation_doctor or event_results[event.id].doctor_confirmation) and (
                        not event.need_confirmation_patient or event_results[event.id].patient_confirmation):
                    if (not event_results[event.id].doctor_confirmation or event_results[
                        event.id].doctor_confirmation < end_date) and (
                            not event_results[event.id].patient_confirmation or event_results[event.id].patient_confirmation < end_date):
                        event_status[event.id] = 'done'
                    else:
                        event_status[event.id] = 'delayed'
                else:
                    if not event.need_confirmation_doctor and not event.need_confirmation_patient:
                        event_status[event.id] = 'pass'
                    else:
                        if today < end_date:
                            event_status[event.id] = 'progress'
                        else:
                            event_status[event.id] = 'fail'
            else:
                event_status[event.id] = 'pre'

        stats = {
            "total": len(events),
            "done": len(list(filter(lambda x: x == 'done', event_status.values()))),
            "failed": len(list(filter(lambda x: x == 'fail', event_status.values()))),
            "delayed": len(list(filter(lambda x: x == 'delay', event_status.values())))
        }

        return render_template('protocol.html', events=events, event_results=event_results, protocol=protocol,
                               event_periods=event_periods, event_notifications=event_notifications,
                               event_status=event_status, stats=stats)

    except Exception as e:
        print(e, sys.exc_info()[-1].tb_lineno)
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

        if not validate_date(date):
            return "<strong>Ошибки при заполнении формы.</strong> Пожалуйста, что все поля заполнены.<br><a onclick='history.go(-1);'>Назад</a>"

        result = EventResults.query.filter_by(event_id=event_id, contract_id=contract_id).first()
        if role == 'doctor':
            result.doctor_confirmation = date
            result.doctor_comment = comment
        if role == 'patient':
            result.patient_confirmation = date
            result.patient_comment = comment
        db.session.commit()

        return "<strong>Спасибо, окно можно закрыть</strong><script>window.parent.postMessage('close-modal-success','*');</script>"

    except:
        return "error"


@app.route('/', methods=['GET'])
def index():
    return 'waiting for the thunder!'


def event_active(protocol: ContractProtocols, event):
    today = datetime.today().date()
    target_date = protocol.start + timedelta(days=event.notification_day)

    return (today - target_date).days == 0


def send_iteration():
    contracts = Contract.query.all()

    for contract in contracts:
        for protocol in contract.protocols:
            for event in protocol.events:
                if event_active(protocol.get_connection(contract), event) and EventResults.query.filter_by(
                        event_id=event.id, contract_id=contract.id).count() == 0:
                    result = EventResults(event_id=event.id, contract_id=contract.id)
                    db.session.add(result)

                    if event.notify_doctor:
                        text = event.get_doctor_message(protocol.get_connection(contract))

                        if event.need_confirmation_doctor:
                            action_link = "doctor/event/{}".format(event.id)
                            action_name = "Подтвердить выполнение"
                        else:
                            action_link = None
                            action_name = None

                        send_message(contract_id=contract.id, text=text, only_doctor=True, action_link=action_link,
                                     action_name=action_name, action_onetime=True)

                    if event.notify_patient:
                        text = event.get_patient_message(protocol.get_connection(contract))

                        if event.need_confirmation_patient:
                            action_link = "patient/event/{}".format(event.id)
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
