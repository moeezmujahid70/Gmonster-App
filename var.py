import os
import sys
from logger import logger
import var
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
import tempfile
if os.name == 'nt':
    import msvcrt
else:
    import fcntl
from queue import LifoQueue
import queue
import pandas as pd
from pathlib import Path
from json import load, dumps
import uuid
import traceback
global scheduler


def override_where():
    """ overrides certifi.core.where to return actual location of cacert.pem"""
    return os.path.abspath(os.path.join(os.getcwd(), 'data', 'gmonster_config', 'cacert.pem'))


if hasattr(sys, 'frozen'):
    import certifi.core
    os.environ['REQUESTS_CA_BUNDLE'] = override_where()
    certifi.core.where = override_where
    import requests
    import requests.utils
    import requests.adapters
    requests.utils.DEFAULT_CA_BUNDLE_PATH = override_where()
    requests.adapters.DEFAULT_CA_BUNDLE_PATH = override_where()
else:
    import requests


class SingleInstance:
    """ Limits application to single instance """

    def __init__(self):
        self.mutexname = 'testmutex_{D0E858DF-985E-4907-B7FB-8D732C3FC3B9}'
        self.lasterror = 0
        self.lock_file = None
        lock_file_path = os.path.join(
            tempfile.gettempdir(), f'{self.mutexname}.lock')
        self.lock_file = open(lock_file_path, 'a+')
        try:
            if os.name == 'nt':
                self.lock_file.seek(0)
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self.lock_file.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lasterror = 0
        except OSError:
            self.lasterror = 1

    def already_running(self):
        return self.lasterror != 0

    def __del__(self):
        if self.lock_file:
            try:
                if os.name == 'nt':
                    self.lock_file.seek(0)
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                self.lock_file.close()
            except Exception:
                pass


try:

    def resource_path(relative_path):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath('.'), relative_path)
    mail_unread_icon = resource_path('icons/email.ico')
    mail_read_icon = resource_path('icons/mail.ico')
except Exception as e:
    print(e)
version = '2.2r'
DATA_DIR = os.path.join(os.getcwd(), 'data')
DATA_SHEETS_DIR = os.path.join(DATA_DIR, 'sheets')
DATA_EMAIL_DIR = os.path.join(DATA_DIR, 'email')
DATA_EMAIL_VERIFICATION_DIR = os.path.join(
    DATA_EMAIL_DIR, 'email_verification')
DATA_EMAIL_TOOLS_DIR = os.path.join(DATA_EMAIL_DIR, 'tools')
DATA_EMAIL_RESULTS_DIR = os.path.join(DATA_EMAIL_DIR, 'results')
DATA_LOGS_DIR = os.path.join(DATA_DIR, 'logs')
DATA_LOGS_GMONSTER_DIR = os.path.join(DATA_LOGS_DIR, 'gmonster')
DATA_LOGS_WUM_DIR = os.path.join(DATA_LOGS_DIR, 'wum')
DATA_LOGS_APP_DIR = os.path.join(DATA_LOGS_DIR, 'app')
DATA_GMONSTER_CONFIG_DIR = os.path.join(DATA_DIR, 'gmonster_config')
DATA_WUM_CONFIG_DIR = os.path.join(DATA_DIR, 'wum_config')
DATA_BACKUPS_DIR = os.path.join(DATA_DIR, 'backups')
SCRIPTS_DIR = os.path.join(os.getcwd(), 'scripts')

for _path in [
    DATA_DIR,
    DATA_SHEETS_DIR,
    DATA_EMAIL_DIR,
    DATA_EMAIL_VERIFICATION_DIR,
    DATA_EMAIL_TOOLS_DIR,
    DATA_EMAIL_RESULTS_DIR,
    DATA_LOGS_DIR,
    DATA_LOGS_GMONSTER_DIR,
    DATA_LOGS_WUM_DIR,
    DATA_LOGS_APP_DIR,
    DATA_GMONSTER_CONFIG_DIR,
    DATA_WUM_CONFIG_DIR,
    DATA_BACKUPS_DIR,
    SCRIPTS_DIR,
]:
    os.makedirs(_path, exist_ok=True)

base_dir = DATA_GMONSTER_CONFIG_DIR
followup_report_file_path = os.path.join(
    DATA_EMAIL_RESULTS_DIR, 'followup_report.csv')
report_file_path = os.path.join(DATA_EMAIL_RESULTS_DIR, 'report.csv')
database_csv_file_path = os.path.join(DATA_EMAIL_RESULTS_DIR, 'database.csv')
verify_blacklist_file_path = os.path.join(
    DATA_GMONSTER_CONFIG_DIR, 'verify_blacklist.txt')
blacklist_file_path = os.path.join(DATA_GMONSTER_CONFIG_DIR, 'blacklist.txt')
autoreply_address_file_path = os.path.join(
    DATA_GMONSTER_CONFIG_DIR, 'autoReply_address.txt')
group_db_path = os.path.join(DATA_GMONSTER_CONFIG_DIR, 'group.DB')
jobs_db_path = os.path.join(DATA_GMONSTER_CONFIG_DIR, 'jobs.sqlite')
config_file_path = os.path.join(DATA_GMONSTER_CONFIG_DIR, 'config.json')
cacert_file_path = os.path.join(DATA_GMONSTER_CONFIG_DIR, 'cacert.pem')
update_temp_path = 'temp'
update_bat_file_path = os.path.join(SCRIPTS_DIR, 'updater.bat')
if os.name == 'nt':
    try:
        with open(update_bat_file_path, 'w') as file:
            file.write('\n@echo off\n\nrem Wait for a period of time (e.g., 20 seconds)\ntimeout /t 20\n\nrem Replace the original executable with the updated one\nset "tempExePath=.\\temp\\GMonster.exe"  rem Replace with the actual path of the updated executable\nset "originalExePath=.\\GMonster.exe"  rem Replace with the actual path of the original executable\ncopy /y "%tempExePath%" "%originalExePath%"\n\nrem Execute the updated version of the application\nstart "" "%originalExePath%"\n\nset "tempExePath=.\\temp\\WUM.exe"  rem Replace with the actual path of the updated executable\nset "originalExePath=.\\WUM.exe"  rem Replace with the actual path of the original executable\ncopy /y "%tempExePath%" "%originalExePath%"\n            \n            ')
    except:
        logger.error(
            f'Error at updater.bat file creating: {traceback.format_exc()}')
compose_email_subject = 'Just a friendly outreach about [3]'
compose_email_body = "{Hey|Hi|Hello} [TONAME|Something],\n\nI'm reaching out to you because i {noticed|came across|found|visited} you website {the other day|yesterday} and thought you'd be interested in a {collaboration|partnership}.\n\n{Hope you don't mind my outreach!|Looking forward to your reply!}\n\nRegards,\n[FIRSTFROMNAME]"
compose_email_body_html = "<html>\n    <body>\n        <p>{Hey|Hi|Hello} [TONAME|Something],<br>\n        I'm reaching out to you because i {noticed|came across|found|visited} you website {the other day|yesterday} and thought you'd be interested in a {collaboration|partnership}.<br>\n        {Hope you don't mind my outreach!|Looking forward to your reply!}<br>\n        </p>\n    </body>\n</html>\n"
body_type = 'Normal'
jobstores = {'default': SQLAlchemyJobStore(
    url=f'sqlite:///{jobs_db_path}')}
logger.info('Logger Started')
scheduler = BackgroundScheduler(logger=logger)
scheduler.start()


def exit_gracefully(signum, frame):
    logger.info('shutdown scheduler gracefully')
    scheduler.shutdown()


db_file_loading_config = {'group_a': True, 'group_b': True, 'target': True}


class AirtableConfig:
    base_id = ''
    api_key = ''
    table_name = ''
    use_desktop_id = False
    mark_sent_airtable = False
    continuous_loading = False
    continuous_loading_time_period = 24

    def __init__(self):
        return


wum_exe_path = 'WUM.exe' if os.name == 'nt' else 'WUM'
gmaps_scraper_base_path = os.path.join('data', 'tools', 'google_maps_scraper')
gmaps_scraper_exe_path = (
    os.path.join(gmaps_scraper_base_path, 'windows', 'google_maps_scraper.exe')
    if os.name == 'nt'
    else os.path.join(gmaps_scraper_base_path, 'macos', 'google_maps_scraper')
)
gmaps_scraper_mac_app_path = os.path.join(
    gmaps_scraper_base_path,
    'macos',
    'google_maps_scraper.app'
)
gmaps_scraper_port = 8080
gmaps_scraper_url = 'http://localhost:8080'
gmaps_scraper_process = None
CONFUSABLES_CHARACTER = ['\u2003', '\u2002', '\u2001', '\u2000']
add_custom_hostname = False
window_title = 'GMonster'
email_failed = 0
total_email_downloaded = 0
waiting_period_for_followup = 600
sign_up_label = ''
sign_in_label = ''
signed_in = False
check_for_blocks = False
email_tracking_state = False
rid_list = []
files = []
reply_files = []
reply_body = ''
inbox_data = [pd.DataFrame(), pd.DataFrame()]
inbox_data_table = [pd.DataFrame(), pd.DataFrame()]
email_in_view = {}
email_q = LifoQueue()
total_email = 0
row_pos = 0
thread_open = 0
acc_finished = 0
total_acc = 0
stop_download = False
airtable_base_id = 'appaCmKFn3MWDzjsF'
airtable_api_key = 'keyajjzgPaHo8VjWA'
thread_open_campaign = 0
stop_send_campaign = False
send_campaign_email_count = 0
send_campaign_run_status = False
download_email_status = False
send_report = queue.Queue()
command_q = queue.Queue()
webhook_q = queue.Queue()
enable_webhook_status = False
remove_email_from_target = False
limit_of_thread = 100
imap_server = 'imap.gmail.com'
imap_port = 993
smtp_server = 'smtp.gmail.com'
smtp_port = 587
button_style = 'QPushButton {\n    color: rgb(255, 255, 255);\n    border: 0px solid #555;\n    border-radius: 3px;\n    border-style: Solid;\n    padding: 5px 28px;\n    }\n'
date = '8/24/2020'
num_emails_per_address = 0
delay_between_emails = ''
inbox_group = 0
limit_of_thread = 100
login_email = ''
tracking = {}
webhook_link = ''
api = 'https://enzim.pythonanywhere.com/'
API_CONNECT_TIMEOUT = 5
API_READ_TIMEOUT = 20
API_TIMEOUT = (API_CONNECT_TIMEOUT, API_READ_TIMEOUT)
API_SLOW_TIMEOUT = (API_CONNECT_TIMEOUT, 30)
API_EMAIL_VERIFY_TIMEOUT = (API_CONNECT_TIMEOUT, 100)
FILE_DOWNLOAD_TIMEOUT = (10, 120)
gmail_provider = 'https://gmonster.co/product/gmail-accounts/'
proxy_provider = 'https://gmonster.co/product/gmonster-proxies/'
campaign_scheduler_cache_path = os.path.join(
    DATA_GMONSTER_CONFIG_DIR, 'campaign_scheduler')
try:
    if not os.path.exists(campaign_scheduler_cache_path):
        os.makedirs(campaign_scheduler_cache_path, exist_ok=True)
except Exception as e:
    logger.error(f'Error while creating campaign_scheduler folder - {e}')
responses_webhook_enabled = False
auto_fire_responses_webhook = False
auto_fire_responses_webhook_interval = 6
inbox_blacklist = []
inbox_whitelist = []
gmonster_desktop_id = ''
id_file_name = 'gmonster_id'
id_file_path = os.path.join(DATA_GMONSTER_CONFIG_DIR, id_file_name)
hostname_list = []
inbox_whitelist_checkbox = False
space_encoding_checkbox = False
hide_warmup_emails = False
warmup_pool_accounts = []
test_email = ''
cc_emails = ''
cc_emails_enabled = False
open_ai_key = ''
open_ai_model = 'gpt-5-mini'
total_email_to_be_sent = 0
try:
    if os.path.exists(id_file_path):
        with open(id_file_path, 'r', encoding='utf-8') as file:
            gmonster_desktop_id = file.read().strip()
    else:
        gmonster_desktop_id = str(uuid.uuid4())
        with open(id_file_path, 'w', encoding='utf-8') as file:
            file.write(gmonster_desktop_id)
except Exception as e:
    logger.info('Exception occurred at id file loading : {}'.format(e))
try:
    with open(config_file_path) as json_file:
        data = load(json_file)
    config = data['config']
    if 'inbox_whitelist' not in config:
        config['inbox_whitelist'] = var.inbox_whitelist
    if 'inbox_whitelist_checkbox' not in config:
        config['inbox_whitelist_checkbox'] = inbox_whitelist_checkbox
    if 'space_encoding_checkbox' not in config:
        config['space_encoding_checkbox'] = space_encoding_checkbox
    if 'hide_warmup_emails' not in config:
        config['hide_warmup_emails'] = hide_warmup_emails
    if 'test_email' not in config:
        config['test_email'] = test_email
    if 'open_ai_key' not in config:
        config['open_ai_key'] = open_ai_key
    if 'open_ai_model' not in config:
        config['open_ai_model'] = open_ai_model
    if 'api' not in config:
        config['api'] = api
    if 'cc_emails' not in config:
        config['cc_emails'] = cc_emails
    if 'cc_emails_enabled' not in config:
        config['cc_emails_enabled'] = cc_emails_enabled
    if 'auto_fire_responses_webhook_interval' not in config:
        config['auto_fire_responses_webhook_interval'] = auto_fire_responses_webhook_interval
    date = config['date']
    if config['compose_email_subject']:
        compose_email_subject = config['compose_email_subject']
    if config['compose_email_body']:
        compose_email_body = config['compose_email_body']
    if config['compose_email_body_html']:
        compose_email_body_html = config['compose_email_body_html']
    compose_prompt = config['compose_prompt']
    num_emails_per_address = config['num_emails_per_address']
    delay_between_emails = config['delay_between_emails']
    limit_of_thread = config['limit_of_thread']
    login_email = config['login_email']
    api = config.get('api', api)
    tracking = config['tracking']
    webhook_link = config['webhook_link']
    check_for_blocks = config['check_for_blocks']
    remove_email_from_target = config['remove_email_from_target']
    add_custom_hostname = config['custom_hostname']
    enable_webhook_status = config['enable_webhook']
    email_tracking_state = config['enable_email_tracking']
    campaign_group = config['campaign_group']
    body_type = config['body_type']
    target_blacklist = config['target_blacklist']
    inbox_blacklist = config['inbox_blacklist']
    inbox_whitelist = config['inbox_whitelist']
    responses_webhook_enabled = config['responses_webhook_enabled']
    auto_fire_responses_webhook = config['auto_fire_responses_webhook']
    auto_fire_responses_webhook_interval = config['auto_fire_responses_webhook_interval']
    followup_enabled = config['followup_enabled']
    followup_days = config['followup_days']
    followup_subject = config['followup_subject']
    followup_body = config['followup_body']
    autoReply_body = config['autoReply_body']
    autoReply_prompt = config['autoReply_prompt']
    autoReply_canned_switch = config['autoReply_canned_switch']
    autoReply_intervals = config['autoReply_intervals']
    autoReply_switch = config['autoReply_switch']
    autoReply_enabled = config['autoReply_enabled']
    mail_server = config['mail_server']
    hostname_list = config['hostname_list']
    inbox_whitelist_checkbox = config['inbox_whitelist_checkbox']
    space_encoding_checkbox = config['space_encoding_checkbox']
    hide_warmup_emails = config.get('hide_warmup_emails', False)
    test_email = config['test_email']
    open_ai_key = config.get('open_ai_key', '')
    open_ai_model = config.get('open_ai_model', open_ai_model)
    cc_emails = config['cc_emails']
    cc_emails_enabled = config['cc_emails_enabled']
    AirtableConfig.base_id = config['airtable']['base_id']
    AirtableConfig.api_key = config['airtable']['api_key']
    AirtableConfig.table_name = config['airtable']['table_name']
    AirtableConfig.use_desktop_id = config['airtable']['use_desktop_id']
    AirtableConfig.mark_sent_airtable = config['airtable']['mark_sent_airtable']
    AirtableConfig.continuous_loading = config['airtable']['continuous_loading']
    AirtableConfig.continuous_loading_time_period = config[
        'airtable']['continuous_loading_time_period']
    proxy_on = config['proxy_on']
except Exception as e:
    logger.info('Exception occurred at config loading : {}'.format(e))
    sys.exit()
delay_start = int(delay_between_emails.split('-')[0].strip())
delay_end = int(delay_between_emails.split('-')[1].strip())


def email_tracking_link():
    return f"{tracking['domain_name']}/track-email-open.php?client_id=123456789.987654321&event_name={tracking['campaign_name']}"


delete_email_count = 0
stop_delete = False
group_a = pd.DataFrame()
group_b = pd.DataFrame()
target = pd.DataFrame()
db_path = group_db_path
if __name__ == '__main__':
    myapp = SingleInstance()
    if myapp.already_running():
        from compat_ui import alert
        alert(text='Another instance of this program is already running')
        logger.info('Another instance of this program is already running')
        sys.exit(1)
    is_testing_environment = 0
    try:
        if os.getenv('fa414ce5-05d1-45e2-ba53-df760ad35fa0'):
            is_testing_environment = int(
                os.getenv('fa414ce5-05d1-45e2-ba53-df760ad35fa0'))
    except:
        pass
    logger.info('gmonster_desktop_id - {}'.format(gmonster_desktop_id))
    from utils import update_config_json
    update_config_json()
    # add comment here
    if is_testing_environment:
        import main
    else:
        import dialog

# pyinstaller --onedir --icon=icons/icon.ico --name=GMonster --noconsole --noconfirm var.py
# pyi-makespec --onefile --icon=icons/icon.ico --name=GMonster --noconsole var.py
# pyinstaller --onefile --icon=icons/icon.ico --name=GMonster --noconsole --add-data="icons/icon.ico;imag" --add-data="icons/mail.ico;imag" --add-data="icons/email.ico;imag" var.py
# pyinstaller --onefile --icon=icons/icon.ico --name=GMonster --upx-dir=E:\Upwork\2020\upx-3.96-win64 GMonster.spec
# pyinstaller GMonster.spec
# a.datas += Tree('E:\\Upwork\\2020\\gmail_app\\gmail_app\\icons', prefix='icons\\')

# https://plainenglish.io/blog/pyinstaller-exe-false-positive-trojan-virus-resolved-b33842bd3184
