from email_validator import validate_email
from textblob import TextBlob
from gui import Ui_MainWindow
from database import update_target_verified
from email_thread_display import header_date_text, message_to_thread_html
from inbox_search import filter_inbox_emails, normalize_inbox_search_query
from openai import OpenAI, AuthenticationError as OpenAIAuthError
from statistics_report import (
    DateRange,
    StatisticsCalculator,
    create_statistics_report_preview,
    export_statistics_pdf,
    format_currency,
    format_number,
)
from subscription_cancel import (
    build_cancel_request_payload,
    build_cancel_request_url,
)
from unsubscribe_client import add_manual, get_records, get_setting, update_setting
from unsubscribe_management import default_export_path, export_records
from unsubscribe_page import UnsubscribePage
from unsubscribe_setting import UnsubscribeSettingController
from campaign_progress import campaign_progress_state
from runtime_paths import open_sheets_folder as open_runtime_sheets_folder
from runtime_paths import wum_executable_path
import subprocess
import signal
from datetime import datetime
import traceback
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt, pyqtSignal, QDate, QItemSelection
from compat_ui import alert, confirm
from PyQt5.QtWidgets import (
    QFileDialog,
    QTableWidgetItem,
    QWidget,
    QLabel,
    QHBoxLayout,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QLineEdit,
    QSpinBox,
    QProgressBar,
)
from PyQt5 import QtCore, QtGui, QtWidgets
import pandas as pd
from time import sleep
from threading import Thread
from json import load, dumps
import requests
import webbrowser
import uuid
import time
import threading
import sys
import socket
import re
import random
import os
import html
import importlib
try:
    qta = importlib.import_module("qtawesome")
except Exception:
    qta = None

TOOL_NAVIGATION_ITEMS = (
    "Follow-up",
    "Auto-reply",
    "Statistics",
    "Leads",
    "Warm up",
)

TOOL_MENU_ICON_NAMES = {
    "Follow-up": "fa5s.reply",
    "Auto-reply": "fa5s.robot",
    "Statistics": "fa5s.chart-bar",
    "Leads": "fa5s.user-friends",
    "Warm up": "fa5s.fire",
}

global app
global mainWindow
global myMC
global quit_application
global GUI

quit_application = False


def get_effective_openai_key():
    return (var.open_ai_key or "").strip()


def get_effective_openai_model():
    model_name = (var.open_ai_model or "").strip()
    if model_name:
        return model_name
    return "gpt-5-nano"


def _call_server_ai(prompt):
    """Call the server-side AI endpoint when no user OpenAI key is configured."""
    import requests as _requests
    url = var.api + 'verify/ai_response'
    last_error = None
    for attempt in range(2):
        try:
            return _call_server_ai_once(prompt, _requests, url)
        except Exception as e:
            last_error = e
            if attempt == 0 and _should_retry_ai_error(e):
                sleep(1)
                continue
            raise
    raise last_error


def _call_server_ai_once(prompt, _requests, url):
    resp = _requests.post(
        url,
        json={
            'email': var.login_email,
            'password': var.login_password,
            'machine_uuid': var.login_machine_uuid,
            'processor_id': var.login_processor_id,
            'prompt': prompt,
        },
        timeout=(var.API_CONNECT_TIMEOUT, 40),
    )
    if not resp.ok:
        raise ServerAIResponseError(_server_ai_error_message(resp), resp)
    data = resp.json()
    if data.get("status") == "ok":
        return data.get('answer', '')
    if data.get("error") or data.get("error_code") or data.get("message"):
        raise ServerAIResponseError(_server_ai_error_message(resp), resp)
    return data.get('answer', '')


class ServerAIResponseError(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response


def _server_ai_error_message(response):
    data = {}
    try:
        data = response.json()
    except Exception:
        data = {}
    message = data.get("message")
    if message:
        return message
    error_code = data.get("error_code") or data.get("error")
    status_code = response.status_code
    return _map_ai_error_message(status_code=status_code, error_code=error_code)


def _map_ai_error_message(status_code=None, error_code=None):
    if status_code == 504 or error_code == "ai_upstream_timeout":
        return "The AI is taking too long to respond. Please try again."
    if status_code == 429 or error_code == "ai_rate_limited":
        return "The AI service is busy right now. Please wait a moment and retry."
    if status_code == 503 or error_code == "ai_connection_error":
        return "The server could not reach the AI service. Please try again."
    if (
        status_code == 502
        or error_code in ("ai_provider_server_error", "ai_upstream_error")
    ):
        return "The AI service failed temporarily. Please try again later."
    return "The AI service failed temporarily. Please try again later."


def _should_retry_ai_error(error):
    if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(error, ServerAIResponseError) and error.response is not None:
        try:
            data = error.response.json()
        except Exception:
            data = {}
        if data.get("retryable") is True:
            return True
        status_code = error.response.status_code
        error_code = data.get("error_code") or data.get("error")
        return status_code in (502, 503, 504) or error_code in (
            "ai_upstream_timeout",
            "ai_connection_error",
            "ai_provider_server_error",
            "ai_upstream_error",
        )
    return False


def _ai_exception_message(error):
    if isinstance(error, ServerAIResponseError):
        return str(error)
    if isinstance(error, requests.exceptions.Timeout):
        return "The request took too long. Please try again."
    if isinstance(error, requests.exceptions.ConnectionError):
        return "Network error. Please check your internet connection and try again."
    return "The AI service failed temporarily. Please try again later."


STATISTICS_REPLY_CATEGORIES = {
    "neutral_replies",
    "interested_replies",
    "objection_replies",
    "not_now_replies",
    "referral_replies",
    "out_of_office_replies",
    "automated_replies",
}


def _statistics_ai_reply_prompt(row):
    subject = str(row.get("subject", "") or "")[:500]
    sender = str(row.get("from_mail", "") or row.get("from", "") or "")[:300]
    body = str(row.get("body", "") or "")[:2500]
    return (
        "Classify this inbound sales email reply into exactly one category key.\n"
        "Return only the category key, with no punctuation or explanation.\n\n"
        "Allowed category keys:\n"
        "- interested_replies: positive buying intent, asks for more info, wants a call, says yes.\n"
        "- objection_replies: objection, rejection, budget/price issue, not interested, not a fit.\n"
        "- not_now_replies: asks to follow up later, timing delay, not now.\n"
        "- referral_replies: points to another person or says someone else handles this.\n"
        "- out_of_office_replies: vacation, away, OOO, unavailable auto-reply.\n"
        "- automated_replies: delivery notification, mailer daemon, system-generated response.\n"
        "- neutral_replies: real human reply that does not fit a stronger category.\n\n"
        f"Sender: {sender}\n"
        f"Subject: {subject}\n"
        f"Body:\n{body}"
    )


def build_statistics_openai_reply_classifier():
    api_key = get_effective_openai_key()
    if not api_key:
        return None
    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        var.logger.error(f"Failed to initialize statistics OpenAI classifier: {str(e)}")
        return None

    cache = {}

    def classify(row):
        cache_key = (
            str(row.get("from_mail", "") or row.get("from", "") or ""),
            str(row.get("subject", "") or ""),
            str(row.get("body", "") or "")[:2500],
        )
        if cache_key in cache:
            return cache[cache_key]
        try:
            response = client.chat.completions.create(
                model=get_effective_openai_model(),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You classify cold email replies for sales analytics. "
                            "You return exactly one allowed category key."
                        ),
                    },
                    {"role": "user", "content": _statistics_ai_reply_prompt(row)},
                ],
            )
            category = (response.choices[0].message.content or "").strip()
            if category in STATISTICS_REPLY_CATEGORIES:
                cache[cache_key] = category
                return category
        except Exception as e:
            var.logger.error(f"Statistics OpenAI reply classification failed: {str(e)}")
        return ""

    return classify


class AIPromptDialog(QDialog):
    promptSubmitted = pyqtSignal(str)
    aiSucceeded = pyqtSignal(str)
    aiFailed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = None
        self._request_in_progress = False
        self._worker_thread = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(300, 200, 400, 300)
        layout = QVBoxLayout(self)
        self.title_label = QLabel("AI Assistant")
        layout.addWidget(self.title_label)
        self.text_input = QTextEdit(var.compose_prompt)
        layout.addWidget(self.text_input)
        self.status_label = QLabel("")
        self.status_label.hide()
        layout.addWidget(self.status_label)
        self.loader = QProgressBar()
        self.loader.setRange(0, 0)
        self.loader.hide()
        layout.addWidget(self.loader)
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 10, 10)
        self.send_button = QPushButton("Send Prompt")
        self.send_button.clicked.connect(self.get_ai_response)
        self.close_button = QPushButton("Close Prompt")
        self.close_button.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)
        self.setStyleSheet(
            "\n            QLabel::indicator {\n                width: 0px; /* Hide the circle indicator */\n                height: 0px;\n            }\n            QLabel {\n                font-size: 20px;\n                color: #000;\n                background-color: transparent;\n                border: none;\n                padding: 10px;\n            }\n                                    \n            QDialog {\n                background-color: #f9f9f9;\n                border-radius: 20px;\n                padding: 10px;\n            }\n\n            QTextEdit {\n                border: 2px solid black;    /* Black border */\n                border-radius: 10px;\n                padding: 5px;\n                background-color: #ffffff;\n            }\n\n            QDialogButtonBox {\n                background-color: #d4d4d4;\n                border-radius: 10px;\n                padding: 5px;\n            }\n\n            QPushButton {\n                border: 1px solid #555;\n                border-radius: 3px;\n                border-style: Solid;\n                background: rgba(0, 138, 191);\n                padding: 5px 28px;\n                color: rgb(255, 255, 255);\n                }\n            \n            QPushButton:hover {\n                background: rgba(0, 138, 191, 0.6);\n                opacity: 0.2\n                }\n            \n            QPushButton:pressed {\n                border-style: inset;\n                background: rgb(0, 138, 191);\n                }\n        "
        )
        self.aiSucceeded.connect(self._handle_ai_success)
        self.aiFailed.connect(self._handle_ai_failure)

    def get_ai_response(self):
        if self._request_in_progress:
            return
        prompt = self.text_input.toPlainText().strip()
        var.compose_prompt = prompt
        Thread(target=update_config_json, daemon=True).start()
        if not prompt:
            alert(text="Please enter a prompt.", title="Warning", button="OK")
            return
        self._set_ai_loading(True, "Generating response...")
        QtCore.QTimer.singleShot(10000, self._show_slow_ai_status)
        self._worker_thread = Thread(
            target=self._run_ai_request,
            daemon=True,
            args=(prompt,),
        )
        self._worker_thread.start()

    def _run_ai_request(self, prompt):
        effective_key = get_effective_openai_key()
        try:
            if effective_key:
                self.client = OpenAI(api_key=effective_key)
                response = self.client.chat.completions.create(
                    model=get_effective_openai_model(),
                    messages=[
                        {"role": "system",
                            "content": "You are an expert email copywriter."},
                        {"role": "user", "content": prompt},
                    ],
                )
                answer = response.choices[0].message.content
            else:
                answer = _call_server_ai(prompt)
            self.aiSucceeded.emit(answer)
        except OpenAIAuthError:
            self.aiFailed.emit(
                "Your OpenAI API key is invalid or has expired.\n\n"
                "To use the built-in AI access instead, go to "
                "Settings -> OpenAI key and clear the key field, then save."
            )
        except Exception as e:
            self.aiFailed.emit(_ai_exception_message(e))

    def _set_ai_loading(self, is_loading, status_text=""):
        self._request_in_progress = is_loading
        self.send_button.setEnabled(not is_loading)
        self.loader.setVisible(is_loading)
        self.status_label.setText(status_text)
        self.status_label.setVisible(bool(status_text))

    def _show_slow_ai_status(self):
        if self._request_in_progress:
            self.status_label.setText("Still working, this can take a little longer...")

    def _handle_ai_success(self, answer):
        self._set_ai_loading(False)
        self.promptSubmitted.emit(answer)

    def _handle_ai_failure(self, message):
        self._set_ai_loading(False)
        alert(text=message, title="Error", button="OK")


class ImportSlotsDialog(QDialog):
    def __init__(self, plan_limit, sheet_counts, group_a_enabled, group_b_enabled, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Accounts")
        self.setModal(True)
        self._plan_limit = plan_limit

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Plan limit: {plan_limit} accounts total"))

        a_row = QHBoxLayout()
        a_row.addWidget(QLabel("Group A:"))
        self._spin_a = QSpinBox()
        self._spin_a.setRange(0, plan_limit)
        self._spin_a.setEnabled(group_a_enabled)
        a_row.addWidget(self._spin_a)
        a_row.addWidget(
            QLabel(f"(Sheet has {sheet_counts['group_a']} available)"))
        layout.addLayout(a_row)

        b_row = QHBoxLayout()
        b_row.addWidget(QLabel("Group B:"))
        self._spin_b = QSpinBox()
        self._spin_b.setRange(0, plan_limit)
        self._spin_b.setEnabled(group_b_enabled)
        b_row.addWidget(self._spin_b)
        b_row.addWidget(
            QLabel(f"(Sheet has {sheet_counts['group_b']} available)"))
        layout.addLayout(b_row)

        self._total_label = QLabel()
        layout.addWidget(self._total_label)

        btn_row = QHBoxLayout()
        self._ok_btn = QPushButton("Import")
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._ok_btn)
        layout.addLayout(btn_row)

        self._spin_a.valueChanged.connect(self._update_total)
        self._spin_b.valueChanged.connect(self._update_total)
        self._ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self._update_total()

    def _update_total(self):
        total = self._spin_a.value() + self._spin_b.value()
        self._total_label.setText(
            f"Total selected: {total} / {self._plan_limit}")
        over = total > self._plan_limit
        self._total_label.setStyleSheet("color: red;" if over else "")
        self._ok_btn.setEnabled(not over)

    def slots(self):
        return self._spin_a.value(), self._spin_b.value()


class CancelSubscriptionDialog(QDialog):
    def __init__(self, parent=None, email="", user_id="", plan=""):
        super().__init__(parent)
        self.setWindowTitle("Cancel Subscription")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Send a manual subscription cancellation request to Gmonster support."
            )
        )

        form = QtWidgets.QFormLayout()
        self.name_input = QtWidgets.QLineEdit()
        self.email_input = QtWidgets.QLineEdit(email)
        self.user_id_input = QtWidgets.QLineEdit(user_id)
        self.plan_input = QtWidgets.QLineEdit(plan)
        form.addRow("Name *", self.name_input)
        form.addRow("Email", self.email_input)
        form.addRow("User ID", self.user_id_input)
        form.addRow("Current Plan", self.plan_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #c62828;")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Send Request")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        if not self.name_input.text().strip():
            self.error_label.setText("Name is required.")
            self.error_label.show()
            self.name_input.setFocus()
            return
        self.accept()

    def values(self):
        return {
            "name": self.name_input.text().strip(),
            "email": self.email_input.text().strip(),
            "user_id": self.user_id_input.text().strip(),
            "plan": self.plan_input.text().strip(),
        }


class MyGui(Ui_MainWindow, QtWidgets.QWidget):
    def __init__(self, main_window):
        Ui_MainWindow.__init__(self)
        QtWidgets.QWidget.__init__(self)
        self.setupUi(main_window)


class MyMainClass:
    def __init__(self):
        self.compose_font_size = 13
        self.inbox_zoom_level = 0
        self.statistics_summary = None
        self.statistics_page_index = None
        self.statistics_manual_fields = {}
        self.statistics_calculated_labels = {}
        self.statistics_kpi_value_labels = {}
        self.unsubscribe_page_index = None
        self.setup_statistics_page()
        self.setup_inbox_date_header()
        self.setup_inbox_search()
        self.setup_sidebar_icons()
        GUI.checkBox_delete_all.stateChanged.connect(
            lambda state: self.toggle_all_checkboxes(
                state, GUI.checkBox_delete_all)
        )
        GUI.listWidget.currentRowChanged.connect(
            self.on_listwidget_row_changed)
        GUI.listWidget.setCurrentRow(0)
        GUI.lable_campaign_status_text.hide()
        GUI.label_campaign_status.hide()
        GUI.progressBar_compose.hide()
        GUI.model = TableModel(var.group_a)
        GUI.tableView_database.setModel(GUI.model)
        GUI.tableView_database.show()
        GUI.tableView_database.resizeColumnsToContents()
        delegate = InLineEditDelegate()
        GUI.tableView_database.setItemDelegate(delegate)
        GUI.label_target_count.hide()
        GUI.pushButton_export_targets.hide()
        self.logger = var.logger
        self.sub_exp = 0
        self.try_failed = 0
        GUI.stackedWidget.setCurrentIndex(0)
        self.unsubscribe_page = UnsubscribePage(GUI.stackedWidget)
        self.unsubscribe_page_index = GUI.stackedWidget.addWidget(self.unsubscribe_page)
        GUI.listWidget.addItem("Unsubscribes")
        self.unsubscribe_page.refreshRequested.connect(self.load_unsubscribe_records)
        self.unsubscribe_page.manualAddRequested.connect(self.add_manual_unsubscribe)
        self.unsubscribe_page.exportRequested.connect(self.export_unsubscribe_records)
        self.setup_sidebar_tools_menu()
        self.setup_sidebar_icons()
        GUI.listWidget.currentRowChanged.connect(self.list_clicked)
        GUI.lineEdit_email_tracking_analytics_account.setText(
            str(var.tracking["analytics_account"])
        )
        GUI.lineEdit_email_tracking_campaign_name.setText(
            str(var.tracking["campaign_name"])
        )
        GUI.lineEdit_email_tracking_domain_name.setText(
            str(var.tracking["domain_name"])
        )
        GUI.lineEdit_email_tracking_analytics_api_key.setText(
            str(var.tracking["api_key"])
        )
        GUI.lineEdit_webhook_link.setText(str(var.webhook_link))
        GUI.lineEdit_target_blacklist.setText(",".join(var.target_blacklist))
        GUI.lineEdit_inbox_blacklist.setText(",".join(var.inbox_blacklist))
        GUI.lineEdit_inbox_whitelist.setText(",".join(var.inbox_whitelist))
        GUI.lineEdit_subject.setText(var.compose_email_subject)
        self.set_campaign_config()
        self.time_interval_sub_check = 3600
        subscription_thread = Thread(
            target=self.check_for_subscription, daemon=True)
        subscription_thread.start()
        if var.hide_warmup_emails:
            Thread(target=self._fetch_warmup_pool_accounts, daemon=True).start()
        GUI.pushButton_account_refresh.clicked.connect(
            self.refresh_account_info)
        GUI.pushButton_account_tutorials.clicked.connect(
            lambda: webbrowser.open("https://gmonster.co/tutorials")
        )
        GUI.pushButton_account_support.clicked.connect(
            lambda: webbrowser.open("https://gmonster.co/support")
        )
        GUI.pushButton_account_cancel_subscription.clicked.connect(
            self.request_subscription_cancel)
        self.command_timer = QtCore.QTimer()
        self.command_timer.setInterval(10)
        self.command_timer.timeout.connect(self.run_command)
        self.command_timer.start()
        self.autoReply_timer = QtCore.QTimer()
        self.autoReply_timer.setInterval(
            max(1, int(var.autoReply_intervals * 60 * 1000)))
        self.autoReply_timer.timeout.connect(self.autoReply_start)
        if var.autoReply_enabled:
            self.autoReply_timer.start()
        self.autoReply_email_timer = QtCore.QTimer()
        self.autoReply_email_timer.setInterval(1000)
        self.autoReply_email_timer.timeout.connect(self.autoReply_email_read)
        self.autoReply_finished = False
        self.autoReply_finished_timer = QtCore.QTimer()
        self.autoReply_finished_timer.setInterval(1000)
        self.autoReply_finished_timer.timeout.connect(
            self.wait_autoReply_finished)
        date = QtCore.QDate.fromString(var.date, "M/d/yyyy")
        GUI.dateEdit_imap_since.setDate(date)
        GUI.dateEdit_imap_since.dateChanged.connect(self.date_update)
        GUI.dateTimeEdit_campaign_scheduler.setDateTime(
            QtCore.QDateTime.currentDateTime()
        )
        GUI.radioButton_group_a.clicked.connect(self.select_inbox_group)
        GUI.radioButton_group_b.clicked.connect(self.select_inbox_group)
        self.option = GUI.pushButton_sort_date.text()
        GUI.pushButton_send.clicked.connect(self.send_camp)
        GUI.pushButton_reply.clicked.connect(self.send_reply)
        GUI.pushButton_export_targets.clicked.connect(self.export_targets)
        GUI.lineEdit_subject.setText(var.compose_email_subject)
        GUI.textBrowser_compose.setPlainText(var.compose_email_body)
        GUI.checkBox_remove_email_from_target.setChecked(
            var.remove_email_from_target)
        GUI.checkBox_add_custom_hostname.setChecked(var.add_custom_hostname)
        GUI.checkBox_enable_webhook.setChecked(var.enable_webhook_status)
        GUI.checkBox_email_tracking.setChecked(var.email_tracking_state)
        GUI.checkBox_check_for_blocks.setChecked(var.check_for_blocks)
        GUI.checkBox_responses_webhook.setChecked(
            var.responses_webhook_enabled)
        GUI.checkBox_auto_fire_responses_webhook.setChecked(
            var.auto_fire_responses_webhook
        )
        GUI.checkBox_enable_cc_emails.setChecked(var.cc_emails_enabled)
        GUI.checkBox_proxy_enabled.setChecked(var.proxy_on)
        GUI.checkBox_space_encoding.setChecked(var.space_encoding_checkbox)
        GUI.checkBox_hide_warmup_emails.setChecked(var.hide_warmup_emails)
        self.unsubscribe_setting = UnsubscribeSettingController(
            GUI.checkBox_insert_unsubscribe_link, get_setting, update_setting
        )
        GUI.checkBox_insert_unsubscribe_link.setEnabled(False)
        GUI.checkBox_insert_unsubscribe_link.stateChanged.connect(
            self.begin_save_unsubscribe_setting
        )
        Thread(target=self.load_unsubscribe_setting, daemon=True).start()
        self.auto_fire_responses_webhook_timer = QtCore.QTimer()
        self.auto_fire_responses_webhook_timer.setInterval(
            max(1, int(var.auto_fire_responses_webhook_interval * 3600 * 1000))
        )
        self.auto_fire_responses_webhook_timer.timeout.connect(
            lambda: threading.Thread(
                target=self.fire_responses_webhook, daemon=True, args=[]
            ).start()
        )
        if var.auto_fire_responses_webhook:
            logger.info(
                f"auto_fire_responses_webhook Interval: {var.auto_fire_responses_webhook_interval} hour"
            )
            self.start_auto_fire_responses_timer()
        GUI.checkBox_configuration_followup_enabled.setChecked(
            var.followup_enabled)
        GUI.lineEdit_configuration_followup_days.setText(
            str(var.followup_days))
        GUI.lineEdit_follow_up_subject.setText(var.followup_subject)
        GUI.textBrowser_follow_up_body.setText(var.followup_body)
        GUI.lineEdit_delay_between_emails.setText(var.delay_between_emails)
        GUI.lineEdit_auto_fire_responses_webhook_interval.setText(
            str(var.auto_fire_responses_webhook_interval)
        )
        GUI.lineEdit_cc_emails.setText(var.cc_emails)
        GUI.lineEdit_configuration_scan_interval.setText(
            str(var.autoReply_intervals))
        if var.autoReply_canned_switch:
            GUI.textBrowser_autoReply_body.setText(var.autoReply_body)
        else:
            GUI.textBrowser_autoReply_body.setText(var.autoReply_prompt)
        GUI.radioButton_all.setChecked(~var.autoReply_switch)
        GUI.radioButton_positive.setChecked(var.autoReply_switch)
        GUI.checkBox_configuration_autoReply_enabled.setChecked(
            var.autoReply_enabled)
        GUI.radioButton_canned_reply.setChecked(var.autoReply_canned_switch)
        GUI.radioButton_ai_reply.setChecked(~var.autoReply_canned_switch)
        GUI.lineEdit_open_ai_key.setEchoMode(QtWidgets.QLineEdit.Password)
        GUI.lineEdit_open_ai_key.setPlaceholderText(
            "Enter your OpenAI API key"
        )
        GUI.lineEdit_open_ai_key.setText(var.open_ai_key)
        GUI.lineEdit_open_ai_model.setText(var.open_ai_model)
        GUI.lineEdit_airtable_table_name.setText(var.AirtableConfig.table_name)
        GUI.lineEdit_airtable_base_id.setText(var.AirtableConfig.base_id)
        GUI.lineEdit_airtable_api_key.setText(var.AirtableConfig.api_key)
        GUI.checkBox_airtable_use_desktop_id.setChecked(
            var.AirtableConfig.use_desktop_id
        )
        GUI.checkBox_mark_sent_airtable.setChecked(
            var.AirtableConfig.mark_sent_airtable
        )
        GUI.checkBox_continuous_loading_airtable.setChecked(
            var.AirtableConfig.continuous_loading
        )
        GUI.tableWidget_inbox.cellClicked.connect(self.email_show)
        self.continuous_loading_airtable_timer = QtCore.QTimer()
        self.continuous_loading_airtable_timer.setInterval(
            max(1, int(var.AirtableConfig.continuous_loading_time_period * 3600 * 1000))
        )
        self.continuous_loading_airtable_timer.timeout.connect(
            self.pull_target_from_airtable
        )
        if var.AirtableConfig.continuous_loading:
            self.schedule_airtable_loading()
        if var.campaign_group == "group_a":
            GUI.radioButton_campaign_group_a.setChecked(True)
        else:
            GUI.radioButton_campaign_group_b.setChecked(True)
        GUI.checkBox_ai_assistant.stateChanged.connect(self.show_ai_assistant)
        GUI.checkBox_responses_webhook.stateChanged.connect(
            self.update_checkbox_status)
        GUI.checkBox_auto_fire_responses_webhook.stateChanged.connect(
            self.update_checkbox_status
        )
        GUI.checkBox_auto_fire_responses_webhook.stateChanged.connect(
            self.start_auto_fire_responses_timer
        )
        GUI.checkBox_check_for_blocks.stateChanged.connect(
            self.update_checkbox_status)
        GUI.checkBox_email_tracking.stateChanged.connect(
            self.update_checkbox_status)
        GUI.checkBox_enable_webhook.stateChanged.connect(
            self.update_checkbox_status)
        GUI.checkBox_remove_email_from_target.stateChanged.connect(
            self.update_checkbox_status
        )
        GUI.checkBox_add_custom_hostname.stateChanged.connect(
            self.update_checkbox_status
        )
        GUI.checkBox_configuration_followup_enabled.stateChanged.connect(
            self.update_checkbox_status
        )
        GUI.checkBox_proxy_enabled.stateChanged.connect(
            self.update_checkbox_proxy)
        GUI.lineEdit_follow_up_subject.textChanged.connect(
            self.update_followup_subject)
        GUI.textBrowser_follow_up_body.textChanged.connect(
            self.update_followup_body)
        GUI.pushButton_follow_up_save.clicked.connect(self.configuration_save)
        GUI.pushButton_autoReply_save.clicked.connect(self.configuration_save)
        GUI.textBrowser_autoReply_body.textChanged.connect(
            self.update_autoReply_body)
        GUI.lineEdit_configuration_scan_interval.textChanged.connect(
            self.update_autoReply_intervals
        )
        GUI.checkBox_configuration_autoReply_enabled.stateChanged.connect(
            self.update_autoReply_enabled
        )
        GUI.radioButton_positive.clicked.connect(self.update_autoReply_switch)
        GUI.radioButton_all.clicked.connect(self.update_autoReply_switch)
        GUI.radioButton_canned_reply.clicked.connect(
            self.update_autoReply_canned_switch
        )
        GUI.radioButton_ai_reply.clicked.connect(
            self.update_autoReply_canned_switch)
        GUI.lineEdit_airtable_base_id.textChanged.connect(
            self.update_airtable_config)
        GUI.lineEdit_airtable_api_key.textChanged.connect(
            self.update_airtable_config)
        GUI.lineEdit_airtable_table_name.textChanged.connect(
            self.update_airtable_config
        )
        GUI.checkBox_airtable_use_desktop_id.stateChanged.connect(
            self.update_airtable_config
        )
        GUI.checkBox_mark_sent_airtable.stateChanged.connect(
            self.update_airtable_config
        )
        GUI.checkBox_continuous_loading_airtable.stateChanged.connect(
            self.update_airtable_config
        )
        GUI.checkBox_continuous_loading_airtable.stateChanged.connect(
            lambda: self.schedule_airtable_loading(
                flag=GUI.checkBox_continuous_loading_airtable.isChecked()
            )
        )
        GUI.pushButton_database_load_target_from_airtable.clicked.connect(
            self.pull_target_from_airtable
        )
        GUI.checkBox_space_encoding.stateChanged.connect(
            self.update_checkbox_status)
        GUI.checkBox_enable_cc_emails.stateChanged.connect(
            self.update_checkbox_status)
        GUI.checkBox_hide_warmup_emails.stateChanged.connect(
            self.update_hide_warmup_emails)
        GUI.pushButton_email_verify.clicked.connect(self.email_verify)
        GUI.pushButton_select_toggle.toggled.connect(
            self.toggle_checkbox_section)
        # Initialize dropdown visibility
        GUI.frame_verifier_dropdown.setVisible(True)
        GUI.pushButton_select_toggle.setChecked(False)
        GUI.frame_checkboxes.setVisible(False)
        GUI.radioButton_html.clicked.connect(self.compose_change)
        GUI.radioButton_plain_text.clicked.connect(self.compose_change)
        if var.body_type == "Html":
            GUI.radioButton_html.setChecked(True)
        else:
            GUI.radioButton_plain_text.setChecked(True)
        GUI.checkBox_compose_preview.clicked.connect(self.compose_preview)
        GUI.lineEdit_subject.textChanged.connect(self.compose_subject_update)
        GUI.lineEdit_num_per_address.textChanged.connect(
            self.update_num_per_address)
        GUI.lineEdit_delay_between_emails.editingFinished.connect(
            self.update_delay_between_emails
        )
        GUI.radioButton_campaign_group_a.clicked.connect(
            self.update_campaign_group)
        GUI.radioButton_campaign_group_b.clicked.connect(
            self.update_campaign_group)
        GUI.pushButton_attachments_reply.clicked.connect(
            self.openFileNamesDialog_reply)
        GUI.pushButton_attachments_campaign.clicked.connect(
            self.openFileNamesDialog)
        GUI.pushButton_load_db.clicked.connect(self.load_db)
        GUI.pushButton_open_sheets_folder.clicked.connect(
            self.open_sheets_folder)
        GUI.pushButton_delete.clicked.connect(self.batch_delete)
        GUI.pushButton_forward.clicked.connect(self.forward)
        GUI.pushButton_test.clicked.connect(self.test_send)
        GUI.textBrowser_show_email.anchorClicked.connect(
            QtGui.QDesktopServices.openUrl)
        GUI.textBrowser_compose.textChanged.connect(self.compose_update)
        GUI.textEdit_reply.textChanged.connect(self.update_rely_text)
        GUI.label_desktop_app_id2.setText(var.gmonster_desktop_id)
        GUI.lineEdit_number_of_threads.textChanged.connect(
            self.update_limit_of_thread)
        GUI.radioButton_db_groupa.clicked.connect(self.update_db_table)
        GUI.radioButton_db_groupb.clicked.connect(self.update_db_table)
        GUI.radioButton_db_target.clicked.connect(self.update_db_table)
        GUI.pushButton_add_row.clicked.connect(self.insert_row)
        GUI.pushButton_remove_row.clicked.connect(self.remove_row)
        # Connect status checkboxes to selection method
        GUI.checkBox_safe.stateChanged.connect(self.select_rows_by_status)
        GUI.checkBox_risky.stateChanged.connect(self.select_rows_by_status)
        GUI.checkBox_unknown.stateChanged.connect(self.select_rows_by_status)
        GUI.checkBox_not_checked.stateChanged.connect(
            self.select_rows_by_status)
        Thread(target=database.startup_load_db,
               daemon=True, args=("dialog",)).start()
        GUI.pushButton_sort_date.clicked.connect(self.date_sort)
        GUI.pushButton_sort_alpha.clicked.connect(self.alpha_sort)
        GUI.lineEdit_email_tracking_analytics_account.textChanged.connect(
            self.update_email_tracking_link
        )
        GUI.lineEdit_email_tracking_campaign_name.textChanged.connect(
            self.update_email_tracking_link
        )
        GUI.lineEdit_email_tracking_domain_name.textChanged.connect(
            self.update_email_tracking_php
        )
        GUI.lineEdit_email_tracking_analytics_api_key.textChanged.connect(
            self.update_email_tracking_php
        )
        GUI.pushButton_download_track.clicked.connect(self.download_track_php)
        GUI.pushButton_configuration_save.clicked.connect(
            self.configuration_save)
        GUI.lineEdit_webhook_link.textChanged.connect(self.update_webhook_link)
        GUI.pushButton_compose_zoomIn.clicked.connect(
            lambda: self.compose_zoomInOut("zoomIn")
        )
        GUI.pushButton_compose_zoomOut.clicked.connect(
            lambda: self.compose_zoomInOut("zoomOut")
        )
        try:
            GUI.pushButton_3.clicked.disconnect()
        except TypeError:
            pass
        try:
            GUI.pushButton_4.clicked.disconnect()
        except TypeError:
            pass
        GUI.pushButton_3.clicked.connect(
            lambda: self.inbox_zoomInOut("zoomIn")
        )
        GUI.pushButton_4.clicked.connect(
            lambda: self.inbox_zoomInOut("zoomOut")
        )
        GUI.checkBox_database_group_a.stateChanged.connect(
            self.update_db_file_upload_config
        )
        GUI.checkBox_database_group_b.stateChanged.connect(
            self.update_db_file_upload_config
        )
        GUI.checkBox_database_target.stateChanged.connect(
            self.update_db_file_upload_config
        )
        GUI.lineEdit_open_ai_key.textChanged.connect(self.change_open_ai_key)
        GUI.lineEdit_open_ai_model.textChanged.connect(
            self.change_open_ai_model)
        GUI.pushButton_fire_inbox_webhook.clicked.connect(
            self.start_inbox_stream_thread
        )
        GUI.lineEdit_target_blacklist.textChanged.connect(
            self.change_target_blacklist)
        GUI.lineEdit_inbox_blacklist.textChanged.connect(
            self.change_inbox_blacklist)
        GUI.lineEdit_inbox_whitelist.textChanged.connect(
            self.change_inbox_whitelist)
        GUI.lineEdit_configuration_followup_days.textChanged.connect(
            self.change_followup_days
        )
        GUI.lineEdit_auto_fire_responses_webhook_interval.textChanged.connect(
            self.update_auto_fire_responses_webhook_interval
        )
        GUI.lineEdit_cc_emails.textChanged.connect(self.update_cc_emails)
        GUI.pushButton_clear_cached_targets.clicked.connect(
            lambda: threading.Thread(
                target=self.clear_cached_targets, daemon=True, args=[]
            ).start()
        )
        GUI.pushButton_schedule_campaign.clicked.connect(
            lambda: self._start_schedule_campaign()
        )
        GUI.pushButton_schedule_campaign_remove.clicked.connect(
            lambda: threading.Thread(
                target=self.remove_schedule_campaign,
                daemon=True,
                args=[
                    GUI.comboBox_scheduled_campaign_list.itemData(
                        GUI.comboBox_scheduled_campaign_list.currentIndex()
                    )
                ],
            ).start()
        )
        GUI.radioButton_email_all.clicked.connect(self.inbox_show_changed)
        GUI.radioButton_email_sent.clicked.connect(self.inbox_show_changed)
        GUI.radioButton_email_positive.clicked.connect(self.inbox_show_changed)
        GUI.radioButton_email_negative.clicked.connect(self.inbox_show_changed)
        self.autoReply_positive_last_date = pd.to_datetime(
            var.date, format="%m/%d/%Y").strftime("%Y-%m-%d %H:%M:%S")
        self.autoReply_all_last_date = pd.to_datetime(
            var.date, format="%m/%d/%Y").strftime("%Y-%m-%d %H:%M:%S")
        self.update_target_count()
        threading.Thread(
            target=self.reset_schedule_campaign_job_list, daemon=True, args=[]
        ).start()
        threading.Thread(target=update_checker, daemon=True, args=[]).start()
        self._apply_button_typography()

    @staticmethod
    def _apply_button_typography():
        """Keep all built-in controls on the same button typeface and weight."""
        for button in GUI.centralwidget.findChildren(QtWidgets.QAbstractButton):
            font = button.font()
            font.setFamily("Arial")
            font.setWeight(QtGui.QFont.Normal)
            font.setBold(False)
            button.setFont(font)
            button.setStyleSheet(
                button.styleSheet()
                .replace("font-weight: bold", "font-weight: 400")
                .replace("font-weight: 600", "font-weight: 400")
                .replace("font-weight: 700", "font-weight: 400")
            )

    def setup_inbox_date_header(self):
        if hasattr(GUI, "lineEdit_original_date"):
            return
        group_box = QtWidgets.QGroupBox(GUI.groupBox)
        group_box.setMinimumSize(QtCore.QSize(50, 0))
        font = QtGui.QFont()
        font.setPointSize(10)
        group_box.setFont(font)
        group_box.setStyleSheet("border:none;")
        group_box.setTitle("")
        group_box.setObjectName("groupBox_original_date")

        grid = QtWidgets.QGridLayout(group_box)
        grid.setObjectName("gridLayout_original_date")

        value_label = QtWidgets.QLabel(group_box)
        value_label.setStyleSheet("color: #555;")
        value_label.setText("")
        value_label.setObjectName("lineEdit_original_date")
        grid.addWidget(value_label, 0, 1, 1, 1)

        title_label = QtWidgets.QLabel(group_box)
        title_label.setMinimumSize(QtCore.QSize(50, 0))
        title_label.setMaximumSize(QtCore.QSize(50, 16777215))
        title_font = QtGui.QFont()
        title_font.setBold(True)
        title_font.setWeight(75)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #555;")
        title_label.setText("Date:")
        title_label.setObjectName("label_original_date")
        grid.addWidget(title_label, 0, 0, 1, 1)

        GUI.groupBox_original_date = group_box
        GUI.lineEdit_original_date = value_label
        GUI.label_original_date = title_label
        GUI.verticalLayout_23.insertWidget(2, group_box)

    def setup_inbox_search(self):
        if hasattr(GUI, "lineEdit_inbox_search"):
            return

        search_widget = QtWidgets.QWidget(GUI.frame)
        search_widget.setObjectName("widget_inbox_search")
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 4, 0, 4)
        search_layout.setSpacing(6)

        search_button = QPushButton(search_widget)
        search_button.setObjectName("pushButton_inbox_search")
        search_button.setCursor(Qt.PointingHandCursor)
        search_button.setFixedSize(34, 34)
        search_button.setToolTip("Search emails")
        search_button.setText("")
        search_button.setFlat(True)
        search_button.setStyleSheet(
            "QPushButton { border: none; color: #555; }"
            "QPushButton:hover { color: #000; background-color: #e6eaf2; }"
        )
        if qta is not None:
            search_button.setIcon(qta.icon("fa5s.search", color="#555"))
            search_button.setIconSize(QtCore.QSize(16, 16))
        else:
            search_button.setText("Search")

        search_input = QLineEdit(search_widget)
        search_input.setObjectName("lineEdit_inbox_search")
        search_input.setPlaceholderText("Search emails")
        search_input.setClearButtonEnabled(True)
        search_input.setMinimumHeight(34)
        search_input.setStyleSheet(
            "QLineEdit { background-color: #fff; border: 1px solid #d6dce8; "
            "border-radius: 4px; padding: 6px 10px; color: #222; }"
            "QLineEdit:focus { border-color: #9aa8c0; }"
        )
        search_input.hide()

        search_layout.addWidget(search_button)
        search_layout.addWidget(search_input)
        GUI.verticalLayout_17.insertWidget(1, search_widget)

        GUI.widget_inbox_search = search_widget
        GUI.pushButton_inbox_search = search_button
        GUI.lineEdit_inbox_search = search_input

        search_button.clicked.connect(self.toggle_inbox_search)
        search_input.textChanged.connect(self.inbox_show_changed)

    def toggle_inbox_search(self):
        search_input = GUI.lineEdit_inbox_search
        should_show = not search_input.isVisible()
        search_input.setVisible(should_show)
        if should_show:
            search_input.setFocus()
            search_input.selectAll()
        else:
            search_input.clear()

    def get_inbox_search_text(self):
        if not hasattr(GUI, "lineEdit_inbox_search"):
            return ""
        return normalize_inbox_search_query(GUI.lineEdit_inbox_search.text())

    def select_inbox_group(self):
        if GUI.radioButton_group_a.isChecked():
            var.inbox_group = 0
        else:
            var.inbox_group = 1
        self.downloading_email()
        self.inbox_show_changed()

    def show_ai_assistant(self):
        dialog = AIPromptDialog(GUI)
        button_position = GUI.checkBox_ai_assistant.mapToGlobal(
            GUI.checkBox_ai_assistant.rect().bottomLeft()
        )
        dialog_width = dialog.width()
        dialog_height = dialog.height()
        new_x = (
            button_position.x() - dialog_width + GUI.checkBox_ai_assistant.width() + 5
        )
        new_y = button_position.y() - dialog_height + GUI.checkBox_ai_assistant.height()
        dialog.move(new_x, new_y)
        dialog.promptSubmitted.connect(self.handle_prompt_response)
        dialog.exec_()

    def handle_prompt_response(self, response_text):
        GUI.textBrowser_compose.setText(response_text)

    def on_listwidget_row_changed(self, index):
        if index != 0:
            GUI.pushButton_delete.hide()
            GUI.checkBox_delete_all.hide()
            GUI.pushButton_fire_inbox_webhook.hide()
        else:
            GUI.pushButton_delete.show()
            GUI.checkBox_delete_all.show()
            GUI.pushButton_fire_inbox_webhook.show()

    def list_clicked(self, index):
        item = GUI.listWidget.item(index)
        item_text = item.text() if item else ""
        if item_text == "Tools":
            self.show_tools_menu()
            GUI.listWidget.setCurrentRow(-1)
            return

        self.navigate_to_item(item_text, index)

    def navigate_to_item(self, item_text, index=-1):
        nav_map = {
            "Inbox": 0,
            "Campaign": 1,
            "Database": 2,
            "Follow-up": 3,
            "Auto-reply": 4,
            "Settings": 5,
            "Account": 6,
        }
        url_mappings = {
            "Store": "https://gmonster.co/store",
            "Tutorials": "https://gmonster.co/tutorials",
            "Support": "https://gmonster.co/support",
        }
        if item_text == "Statistics" and self.statistics_page_index is not None:
            GUI.stackedWidget.setCurrentIndex(self.statistics_page_index)
            self.refresh_statistics()
        elif item_text == "Unsubscribes" and self.unsubscribe_page_index is not None:
            GUI.stackedWidget.setCurrentIndex(self.unsubscribe_page_index)
            self.load_unsubscribe_records()
        elif item_text in nav_map:
            GUI.stackedWidget.setCurrentIndex(nav_map[item_text])
            if item_text == "Account":
                self.refresh_account_info()
        elif item_text == "Leads":
            self.show_leads_popup()
            GUI.listWidget.setCurrentRow(-1)
        elif item_text == "Warm up":
            self.launch_wum()
        else:
            if item_text in url_mappings:
                webbrowser.open(url_mappings[item_text])
            elif item_text:
                print(f"Invalid Index: {index} ({item_text})")

    def setup_sidebar_tools_menu(self):
        """Group secondary navigation into a popup without growing the sidebar."""
        tools_item = None
        database_index = -1
        for index in range(GUI.listWidget.count()):
            item = GUI.listWidget.item(index)
            if item is None:
                continue
            if item.text() in TOOL_NAVIGATION_ITEMS:
                item.setHidden(True)
            elif item.text() == "Tools":
                tools_item = item
            elif item.text() == "Database":
                database_index = index

        if tools_item is None:
            tools_item = QtWidgets.QListWidgetItem("Tools")
            GUI.listWidget.insertItem(database_index + 1, tools_item)

        tools_item.setHidden(False)
        GUI.listWidget.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )
        GUI.listWidget.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )

    def show_tools_menu(self):
        menu = QtWidgets.QMenu(GUI.listWidget)
        menu.setMinimumWidth(210)
        menu.setFont(QtGui.QFont("Arial", 12))
        menu.setStyleSheet(
            "QMenu { background: #ffffff; color: #374151; border: 1px solid #d8e3ee; "
            "border-radius: 8px; font-family: Arial; font-size: 14px; "
            "font-weight: 400; padding: 6px; } "
            "QMenu::item { padding: 10px 30px 10px 12px; border-radius: 5px; } "
            "QMenu::item:selected { background: #e6f5fa; color: #0f4c67; }"
        )
        for item_text in TOOL_NAVIGATION_ITEMS:
            action = menu.addAction(item_text)
            icon_name = TOOL_MENU_ICON_NAMES[item_text]
            if qta is not None:
                action.setIcon(qta.icon(icon_name, color="#64748b"))
            action.triggered.connect(
                lambda checked=False, text=item_text: self.navigate_to_item(text)
            )

        current_item = GUI.listWidget.currentItem()
        if current_item is None:
            return
        item_rect = GUI.listWidget.visualItemRect(current_item)
        menu.exec_(GUI.listWidget.viewport().mapToGlobal(item_rect.bottomLeft()))

    def email_verify(self):
        emails = var.target["EMAIL"].tolist() if not var.target.empty else []
        if not emails:
            alert(
                text="No emails to verify. Please load target database first.",
                title="Warning",
                button="OK",
            )
            return
        # remove duplicates
        var.target = var.target.drop_duplicates(subset=["EMAIL"])

        def is_valid_email_format(email):
            # Remove emails that begin with a dot
            if email.startswith('.'):
                return False

            # Remove emails with invalid symbols (?$!% etc.)
            invalid_chars = ['?', '$', '!', '%', '#', '&', '*',
                             '(', ')', '[', ']', '{', '}', '|', '\\', '/', '<', '>', '=', '+']
            if any(char in email for char in invalid_chars):
                return False

            return True

        if os.path.exists(var.verify_blacklist_file_path):
            with open(var.verify_blacklist_file_path, "r") as f:
                blacklist = f.readlines()
                blacklist = [line.strip() for line in blacklist]
        else:
            blacklist = []
        if blacklist:
            var.target = var.target[~var.target["EMAIL"].isin(blacklist)]

        var.target = var.target[var.target["EMAIL"].apply(
            is_valid_email_format)]
        emails = var.target["EMAIL"].tolist()
        valid_emails = []
        for email in emails:
            try:
                if validate_email(email, check_deliverability=False):
                    valid_emails.append(email)
            except Exception as e:
                logger.error(f"Error verifying email {email}: {str(e)}")
        var.target = var.target[var.target["EMAIL"].isin(valid_emails)].copy()
        var.target["STATUS"] = "not checked"
        update_target_verified()
        self.update_db_table()
        if not valid_emails:
            alert(
                text="No emails with valid format found. Please check your target database.",
                title="Warning",
                button="OK",
            )
            return

        # --- Email Verification Quota Check ---
        email_count = len(valid_emails)
        try:
            quota_url = f"{var.api}verify/use_email_verification/{var.login_email}"
            quota_response = requests.post(
                quota_url, json={"count": email_count}, timeout=var.API_SLOW_TIMEOUT
            )
            quota_data = quota_response.json()

            if quota_response.status_code == 429:
                # Monthly limit reached
                alert(
                    text=(
                        f"Monthly email verification limit reached.\n\n"
                        f"Limit: {quota_data.get('email_verification_limit', 'N/A')}\n"
                        f"Used: {quota_data.get('email_verifications_used', 'N/A')}\n"
                        f"Remaining: {quota_data.get('email_verifications_remaining', 0)}\n"
                        f"Resets on: {quota_data.get('email_verification_reset_date', 'N/A')}"
                    ),
                    title="Verification Limit Reached",
                    button="OK",
                )
                return

            elif quota_response.status_code == 400:
                error_type = quota_data.get("error", "")
                if error_type == "not_enough_remaining":
                    remaining = quota_data.get(
                        "email_verifications_remaining", 0)
                    result = confirm(
                        text=(
                            f"Not enough email verifications remaining.\n\n"
                            f"Requested: {email_count}\n"
                            f"Remaining: {remaining}\n"
                            f"Limit: {quota_data.get('email_verification_limit', 'N/A')}\n"
                            f"Used: {quota_data.get('email_verifications_used', 'N/A')}\n"
                            f"Resets on: {quota_data.get('email_verification_reset_date', 'N/A')}\n\n"
                            f"Would you like to verify only {remaining} emails instead?"
                        ),
                        title="Insufficient Quota",
                        buttons=["Yes", "No"],
                    )
                    if result == "Yes" and remaining > 0:
                        # Trim valid_emails to the remaining quota and retry
                        valid_emails = valid_emails[:remaining]
                        var.target = var.target[var.target["EMAIL"].isin(
                            valid_emails)].copy()
                        var.target["STATUS"] = "not checked"
                        update_target_verified()
                        self.update_db_table()
                        # Consume the reduced quota
                        quota_resp2 = requests.post(
                            quota_url,
                            json={"count": remaining},
                            timeout=var.API_SLOW_TIMEOUT,
                        )
                        if quota_resp2.status_code != 200:
                            quota_data2 = quota_resp2.json()
                            alert(
                                text=(
                                    quota_data2.get("message")
                                    or quota_data2.get("error", "Unknown error")
                                ),
                                title="Quota Error",
                                button="OK",
                            )
                            return
                    else:
                        return
                else:
                    alert(
                        text=(
                            quota_data.get("message")
                            or quota_data.get("error", "Unknown error")
                        ),
                        title="Quota Error",
                        button="OK",
                    )
                    return

            elif quota_response.status_code in (401, 402, 404):
                alert(
                    text=(
                        quota_data.get("message")
                        or quota_data.get("error", "Subscription error")
                    ),
                    title="Subscription Error",
                    button="OK",
                )
                return

            elif quota_response.status_code != 200:
                alert(
                    text=(
                        f"Error checking verification quota: "
                        f"{quota_data.get('message') or quota_data.get('error', 'Unknown error')}"
                    ),
                    title="Error",
                    button="OK",
                )
                return

            # Success – quota consumed, log remaining balance
            logger.info(
                f"Email verification quota consumed: {quota_data.get('consumed', email_count)} | "
                f"Remaining: {quota_data.get('email_verifications_remaining', 'N/A')} | "
                f"Used: {quota_data.get('email_verifications_used', 'N/A')}"
            )

        except requests.exceptions.ConnectionError:
            alert(
                text="Cannot reach the server to verify quota. Please check your internet connection.",
                title="Connection Error",
                button="OK",
            )
            return
        except requests.RequestException as e:
            alert(
                text=f"Error checking verification quota: {str(e)}",
                title="Error",
                button="OK",
            )
            return
        except Exception as e:
            logger.error(f"Unexpected error during quota check: {str(e)}")
            alert(
                text=f"Unexpected error checking verification quota: {str(e)}",
                title="Error",
                button="OK",
            )
            return
        # --- End Quota Check ---

        progress_dialog = QtWidgets.QProgressDialog(
            "Verifying emails...", "Cancel", 0, len(valid_emails), None
        )
        progress_dialog.setWindowTitle("Email Verification")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)

        checked_emails = [[] for _ in range(len(valid_emails))]

        try:
            def resource_path(relative_path):
                if hasattr(sys, "_MEIPASS"):
                    return os.path.join(sys._MEIPASS, relative_path)
                return os.path.join(os.path.abspath("."), relative_path)

            icon_path = resource_path("icons/icon.ico")
            progress_dialog.setWindowIcon(QtGui.QIcon(icon_path))
        except Exception as e:
            logger.error(f"Error setting progress dialog icon: {str(e)}")
        progress_dialog.setValue(0)
        progress_dialog.setLabelText("Verifying emails... (0)")
        # Simple threading approach
        checked_emails = [[] for _ in range(len(valid_emails))]
        json_results = []
        completed_count = 0
        thread_lock = threading.Lock()

        def verify_single_email_thread(email, email_index, proxy_config):
            nonlocal completed_count

            # url = "http://3.93.77.2/v0/check_email"
            url = "http://194.32.107.15/v0/check_email"
            # url = "http://localhost/v0/check_email"
            # url = "http://localhost:81/v0/check_email"
            # url = "http://localhost:82/v0/check_email"
            headers = {"Content-Type": "application/json"}
            # proxy_config = {
            #     "host": "81.28.96.97",
            #     "port": 3130,
            #     "username": "HPBGqbRbahPhs5rA",
            #     "password": "Vk4ANxZDMYKjTEVc"
            # }

            # get the ehlo name and domain from the proxy config
            proxy_ip = proxy_config["host"].split(":")[0]

            try:
                ehlo_name = socket.gethostbyaddr(proxy_ip)[0]
                email_domain = ".".join(ehlo_name.split(".")[-2:])
            except socket.herror:
                ehlo_name = proxy_ip

            if ehlo_name == proxy_ip:
                ehlo_name = "gigahost.no"
                email_domain = "gigahost.no"

            from_email = f"verify@{email_domain}"

            data = {
                "to_email": email,
                "from_email": from_email,
                "hello_name": ehlo_name,
                "proxy": proxy_config
            }

            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=var.API_EMAIL_VERIFY_TIMEOUT,
                )
                if response.status_code == 200:
                    try:
                        result = response.json()
                        # if result["is_reachable"] == 'invalid':
                        #     checked_emails[email_index].append("invalid email")
                        # if result["misc"].get("is_disposable"):
                        #     checked_emails[email_index].append("disposable email")
                        # if result["mx"].get("accepts_mail") == False:
                        #     checked_emails[email_index].append("mx does not accept mail")
                        # if result["smtp"].get("is_disabled"):
                        #     checked_emails[email_index].append("smtp disabled")
                        # if result["smtp"].get("is_deliverable") == False:
                        #     checked_emails[email_index].append("smtp not deliverable")
                        # if result["smtp"].get("has_full_inbox"):
                        #     checked_emails[email_index].append("smtp has full inbox")
                        # if result["smtp"].get("can_connect_smtp") == False:
                        #     checked_emails[email_index].append("smtp can not connect")
                        # if len(checked_emails[email_index]) == 0:
                        #     checked_emails[email_index].append(result["is_reachable"])
                        checked_emails[email_index].append(dumps(result))
                        with thread_lock:
                            json_results.append(dumps(result))
                            var.target.loc[var.target["EMAIL"] ==
                                           email, "STATUS"] = result["is_reachable"]
                    except ValueError as e:
                        checked_emails[email_index].append(response.text)
                        with thread_lock:
                            json_results.append(response.text)
                        logger.error(
                            f"JSON decode error for {email}: {str(e)}")
                        logger.error(f"Response content: {response.text}")
                else:
                    logger.error(
                        f"HTTP {response.status_code} for {email}: {response.text}")

            except requests.exceptions.ConnectionError as e:
                logger.error(
                    f"Connection error for {email} to {url}: {str(e)}")
                logger.error(
                    f"Email verification service unreachable. Check if service at 194.32.107.15:80 is running.")
            except requests.RequestException as e:
                logger.error(f"Request failed for {email}: {str(e)}")

            # Update completion count
            with thread_lock:
                completed_count += 1

        # Thread pool with proxy fetching every 10 tasks
        import concurrent.futures
        import queue

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {}
            proxy_config = None

            for i, email in enumerate(valid_emails):
                if progress_dialog.wasCanceled():
                    break

                # Get new proxy every 10 tasks
                if i % 10 == 0:
                    url = var.api + \
                        "verify/get_proxy/{}".format(var.login_email)
                    try:
                        response = requests.post(url, timeout=var.API_TIMEOUT)
                        if response.status_code == 200:
                            next_proxy = response.json()["proxy"]
                            ip, username, password = next_proxy.split()
                            proxy_config = {
                                "host": ip.split(":")[0].strip(),
                                "port": int(ip.split(":")[1].strip()),
                                "username": username.strip(),
                                "password": password.strip()
                            }
                        else:
                            error_message = "Service not available. Please try again later."
                            try:
                                payload = response.json()
                                backend_message = payload.get(
                                    "message") or payload.get("error")
                                if backend_message:
                                    error_message = backend_message
                            except ValueError:
                                if response.text:
                                    error_message = response.text.strip()
                            logger.error(
                                f"get_proxy failed at {url}: HTTP {response.status_code} - {response.text}"
                            )
                            alert(text=error_message,
                                  title="Error", button="OK")
                            break
                    except requests.exceptions.ConnectionError as e:
                        logger.error(
                            f"Cannot connect to proxy service at {url}: {str(e)}"
                        )
                        error_message = f"Cannot reach proxy service. Check if {var.api} is accessible."
                        alert(text=error_message, title="Error", button="OK")
                        break
                    except requests.RequestException as e:
                        logger.error(
                            f"Request error to proxy service at {url}: {str(e)}"
                        )
                        alert(
                            text=f"Error fetching proxy: {str(e)}", title="Error", button="OK")
                        break

                # Submit first 10 immediately, then rate limit
                if i % 10 != 0:
                    time.sleep(random.uniform(0.20, 0.25))

                future = executor.submit(
                    verify_single_email_thread, email, i, proxy_config)
                futures[future] = i

                # Check completed tasks and update UI
                for completed_future in list(futures.keys()):
                    if completed_future.done():
                        futures.pop(completed_future)
                        progress_dialog.setValue(completed_count)
                        progress_dialog.setLabelText(
                            f"Verifying emails... ({completed_count}/{len(valid_emails)})")
                        QtWidgets.QApplication.processEvents()

            # Wait for remaining tasks
            while futures:
                if progress_dialog.wasCanceled():
                    executor.shutdown(wait=False, cancel_futures=True)
                    QtWidgets.QApplication.processEvents()
                    break
                for completed_future in list(futures.keys()):
                    if completed_future.done():
                        futures.pop(completed_future)
                progress_dialog.setValue(completed_count)
                progress_dialog.setLabelText(
                    f"Verifying emails... ({completed_count}/{len(valid_emails)})")
                QtWidgets.QApplication.processEvents()
                time.sleep(0.01)
        var.target = var.target[var.target["STATUS"] != "invalid"].copy()
        update_target_verified()
        self.update_db_table()
        total_emails = len(valid_emails)
        verified_emails = len(var.target["EMAIL"].tolist())
        bad_emails = total_emails - verified_emails

        try:
            verification_folder = var.DATA_EMAIL_VERIFICATION_DIR
            os.makedirs(verification_folder, exist_ok=True)
            current_date = datetime.now().strftime("%Y-%m-%d-%H-%M")
            excel_filename = os.path.join(
                verification_folder, f"email_verification_{current_date}.xlsx"
            )
            jsonl_filename = os.path.join(
                verification_folder, f"email_verification_{current_date}.jsonl"
            )

            # Save JSON results as JSONL
            try:
                with open(jsonl_filename, 'w') as jsonl_file:
                    for json_result in json_results:
                        jsonl_file.write(json_result + '\n')
                logger.info(f"JSON results saved to {jsonl_filename}")
            except Exception as e:
                logger.error(f"Error saving JSONL file: {str(e)}")

            # # Get verified and bad emails properly
            # verified_email_list = var.target["EMAIL"].tolist()
            # bad_email_list = [email for email in valid_emails if email not in verified_email_list]

            # # Create a comprehensive report with all emails and their status
            # all_emails_data = []

            # for i, email in enumerate(valid_emails):
            #     if i < len(checked_emails):
            #         # Fill empty checked_emails entries
            #         if len(checked_emails[i]) == 0:
            #             error_message = "not checked"
            #         else:
            #             error_message = " | ".join(checked_emails[i])
            #     else:
            #         error_message = "not checked"

            #     # Determine status
            #     if email in verified_email_list:
            #         status = "Good"
            #     else:
            #         status = "Bad"

            #     all_emails_data.append({
            #         "Email": email,
            #         "Status": status,
            #         "Error Messages": error_message
            #     })

            # # Create DataFrame
            # df_report = pd.DataFrame(all_emails_data)

            # # Ensure we have data to write
            # if df_report.empty:
            #     df_report = pd.DataFrame({
            #         "Email": ["No data"],
            #         "Status": ["No data"],
            #         "Error Messages": ["No data"]
            #     })

            # with pd.ExcelWriter(excel_filename, engine="openpyxl") as writer:
            #     df_report.to_excel(
            #         writer, index=False, sheet_name="Verification Results"
            #     )
            #     worksheet = writer.sheets["Verification Results"]

            #     # Auto-adjust column widths
            #     for idx, col in enumerate(df_report.columns):
            #         max_length = max(
            #             df_report[col].astype(str).apply(len).max(), len(col)
            #         )
            #         # Cap the width at 50 characters for readability
            #         worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)

            # logger.info(f"Verification report saved to {excel_filename}")

        except Exception as e:
            logger.error(f"Error creating Excel report: {str(e)}")
            alert(
                text=f"Error creating verification report: {str(e)}",
                title="Warning",
                button="OK",
            )
        alert(
            text=f"Email verification completed.\nVerified: {verified_emails}\nBad: {bad_emails}",
            title="Success",
            button="OK",
        )

    def toggle_checkbox_section(self, checked):
        """Toggle the visibility of the checkbox section within the dropdown"""
        GUI.frame_checkboxes.setVisible(checked)
        # Update the arrow direction
        if checked:
            GUI.pushButton_select_toggle.setText("▼ Select")
        else:
            GUI.pushButton_select_toggle.setText("► Select")

    def verify_bulk_emails(self, api_url, emails, proxySetting):
        url = f"{api_url}/bulk-verify"
        payload = dumps({"emails": emails, "proxy_setting": proxySetting})
        headers = {"Content-Type": "application/json"}
        response = requests.post(
            url,
            data=payload,
            headers=headers,
            timeout=var.API_SLOW_TIMEOUT,
        )
        print(response.json())
        return response.json()

    def change_tab(self, index):
        if index != 0:
            GUI.pushButton_delete.hide()
            GUI.checkBox_delete_all.hide()
        else:
            GUI.pushButton_delete.show()
            GUI.checkbox_delete_all.show()

    def launch_wum(self):
        wum_path = str(wum_executable_path(var.APP_DIR))
        if os.path.exists(wum_path):
            subprocess.Popen([wum_path])
            return

        mac_app_path = os.path.join(os.getcwd(), "WUM.app")
        if sys.platform == "darwin" and os.path.exists(mac_app_path):
            subprocess.Popen(["open", mac_app_path])
            return

        alert(text="WUM executable not found for this platform.",
              title="Warning", button="OK")

    def show_leads_popup(self):
        msg = QMessageBox()
        msg.setWindowTitle("Leads")
        icon_path = (os.path.join(sys._MEIPASS, "icons/icon.png")
                     if hasattr(sys, "_MEIPASS")
                     else os.path.join(os.path.abspath("."), "icons/icon.png"))
        msg.setWindowIcon(QtGui.QIcon(icon_path))
        pixmap = QtGui.QPixmap(icon_path).scaled(
            64, 64, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        msg.setIconPixmap(pixmap)
        msg.setText("Choose a lead generation option:")
        gmaps_btn = msg.addButton(
            "Google Maps Scraper", QMessageBox.ActionRole)
        more_leads_btn = msg.addButton("More Leads", QMessageBox.ActionRole)
        msg.addButton(QMessageBox.Cancel)
        msg.exec_()
        clicked = msg.clickedButton()
        if clicked == gmaps_btn:
            self.launch_gmaps_scraper()
        elif clicked == more_leads_btn:
            webbrowser.open("https://gmonster.co/leads")

    def launch_gmaps_scraper(self):
        if var.gmaps_scraper_process and var.gmaps_scraper_process.poll() is None:
            webbrowser.open(var.gmaps_scraper_url)
            return

        def _resolve_existing_path(relative_path):
            candidates = []

            # PyInstaller onefile runtime extraction directory
            if hasattr(sys, "_MEIPASS"):
                candidates.append(os.path.join(sys._MEIPASS, relative_path))

            # Folder containing packaged executable
            if getattr(sys, "frozen", False):
                candidates.append(
                    os.path.join(os.path.dirname(
                        sys.executable), relative_path)
                )

            # Source run and fallback to current working directory
            candidates.append(os.path.join(os.path.dirname(
                os.path.abspath(__file__)), relative_path))
            candidates.append(os.path.join(os.getcwd(), relative_path))

            for path in candidates:
                if os.path.exists(path):
                    return path
            return candidates[0] if candidates else relative_path

        scraper_path = _resolve_existing_path(var.gmaps_scraper_exe_path)
        data_dir = os.path.join(var.DATA_DIR, 'gmaps')
        os.makedirs(data_dir, exist_ok=True)

        if os.path.exists(scraper_path):
            var.gmaps_scraper_process = subprocess.Popen(
                [scraper_path, '-web', '-c', '1', '-data-folder', data_dir]
            )
            webbrowser.open(var.gmaps_scraper_url)
            return

        if sys.platform == "darwin":
            mac_path = _resolve_existing_path(var.gmaps_scraper_mac_app_path)
            if os.path.exists(mac_path):
                var.gmaps_scraper_process = subprocess.Popen(
                    ["open", mac_path])
                webbrowser.open(var.gmaps_scraper_url)
                return

        alert(text="Google Maps Scraper executable not found.\n"
                   "Please place the binary under data/tools/google_maps_scraper.",
              title="Warning", button="OK")

    def update_auto_fire_responses_webhook_interval(self, data):
        if is_number(data):
            var.auto_fire_responses_webhook_interval = int(data)
        else:
            alert(text="Only Numbers allowed", title="Warning", button="OK")

    def start_auto_fire_responses_timer(self):
        if GUI.checkBox_auto_fire_responses_webhook.isChecked():
            logger.info("auto_fire_responses_webhook timer started")
            self.auto_fire_responses_webhook_timer.start()
        else:
            self.stop_auto_fire_responses_timer()

    def stop_auto_fire_responses_timer(self):
        logger.info("auto_fire_responses_webhook timer stopped")
        self.auto_fire_responses_webhook_timer.stop()

    def fire_responses_webhook(self):
        logger.info("auto_fire_responses_webhook started")
        try:
            var.total_email = 0
            var.thread_open = 0
            var.acc_finished = 0
            var.stop_download = False
            groups = pd.concat([var.group_a.copy(), var.group_b.copy()])
            var.download_email_status = True
            _responses_webhook_enabled = var.responses_webhook_enabled
            var.responses_webhook_enabled = True
            imap.ImapDownload.auto_fire_responses_enabled = True
            imap.main(groups)
            imap.ImapDownload.auto_fire_responses_enabled = False
            var.responses_webhook_enabled = _responses_webhook_enabled
            var.download_email_status = False
        except Exception as e:
            logger.error(
                f"auto_fire_responses_webhook error: {traceback.format_exc()}")
        finally:
            logger.info("auto_fire_responses_webhook finished")

    def schedule_airtable_loading(self, flag=None):
        if flag or flag is None:
            logger.info(
                f"Continuous Loading airtable timer started. Interval - {var.AirtableConfig.continuous_loading_time_period} hr"
            )
            self.continuous_loading_airtable_timer.start()
        else:
            self.stop_airtable_loading()

    def stop_airtable_loading(self):
        logger.info("Continuous Loading airtable timer stopped")
        self.continuous_loading_airtable_timer.stop()

    def _start_schedule_campaign(self):
        try:
            num_per_addr_text = GUI.lineEdit_num_per_address.text().strip()
            delay_text = GUI.lineEdit_delay_between_emails.text().strip()

            if "-" not in num_per_addr_text or "-" not in delay_text:
                alert(
                    text="Please set 'Emails per address' and 'Delay between emails' "
                         "in the Campaign tab first (e.g. 5-10).",
                    title="Campaign Scheduler", button="OK",
                )
                return

            group_a_selected = GUI.radioButton_campaign_group_a.isChecked()
            group = var.group_a if group_a_selected else var.group_b

            if group.empty:
                alert(
                    text="No email accounts loaded in the selected group. "
                         "Please add accounts in the Campaign tab first.",
                    title="Campaign Scheduler", button="OK",
                )
                return

            if var.target.empty:
                alert(
                    text="No target database loaded. "
                         "Please load targets in the Database tab first.",
                    title="Campaign Scheduler", button="OK",
                )
                return

            var.num_emails_per_address = num_per_addr_text
            num_emails_per_address_range = {
                "start": int(var.num_emails_per_address.split("-")[0].strip()),
                "end": int(var.num_emails_per_address.split("-")[1].strip()),
            }
            var.delay_between_emails = delay_text
            delay_start = int(var.delay_between_emails.split("-")[0].strip())
            delay_end = int(var.delay_between_emails.split("-")[1].strip())
            len_group = len(group)
            len_target = len(var.target)
            avg_emails_per_address = (
                num_emails_per_address_range["end"] + num_emails_per_address_range["start"]) / 2
            avg_delay = (delay_end + delay_start) / 2
            if len_group * avg_emails_per_address > len_target:
                total_email_to_be_sent = len_target
                maximum_duration = (
                    total_email_to_be_sent * avg_delay
                    if total_email_to_be_sent - avg_emails_per_address < 0
                    else avg_emails_per_address * avg_delay
                )
            else:
                total_email_to_be_sent = len_group * avg_emails_per_address
                maximum_duration = avg_emails_per_address * avg_delay
            maximum_duration = maximum_duration / 3600
            scheduled_time = GUI.dateTimeEdit_campaign_scheduler.dateTime().toPyDateTime()

            if scheduled_time <= datetime.now():
                alert(
                    text="Scheduled time must be in the future. "
                         "Please select a future date and time.",
                    title="Campaign Scheduler", button="OK",
                )
                return

            msg = QMessageBox()
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle("Campaign Scheduler")
            msg.setText(
                f"This campaign is going to take approximately "
                f"{maximum_duration:.4f} hours to complete AT MAX.\n"
                f"And this campaign will be scheduled at "
                f"{scheduled_time.strftime('%m/%d/%Y, %H:%M:%S')}.\n"
                f"Are you sure?"
            )
            ok_btn = msg.addButton("OK", QMessageBox.AcceptRole)
            msg.addButton("Cancel", QMessageBox.RejectRole)
            msg.exec_()

            if msg.clickedButton() == ok_btn:
                config_filename = str(uuid.uuid4()) + f"-{var.campaign_group}"
                Thread(
                    target=update_config_json,
                    daemon=True,
                    kwargs={"alternative_name": config_filename},
                ).start()
                job = var.scheduler.add_job(
                    func=self.run_scheduled_campaign,
                    trigger="date",
                    args=(config_filename,),
                    id=config_filename,
                    name=config_filename,
                    next_run_time=scheduled_time,
                    misfire_grace_time=None,
                )
                self.reset_schedule_campaign_job_list()
                logger.info(
                    f"Scheduled job id: {job.id} at {str(scheduled_time)}")
        except Exception as e:
            logger.error(
                f"Error at {self.__class__.__name__}: {traceback.format_exc()}"
            )
            alert(
                text=f"Failed to schedule campaign: {e}",
                title="Campaign Scheduler", button="OK",
            )

    def set_campaign_config(self):
        GUI.lineEdit_num_per_address.setText(str(var.num_emails_per_address))
        GUI.lineEdit_delay_between_emails.setText(
            str(var.delay_between_emails))
        GUI.lineEdit_number_of_threads.setText(str(var.limit_of_thread))

    def remove_schedule_campaign(self, job_id):
        try:
            if not job_id:
                alert(text="No scheduled campaign selected.",
                      title="Warning", button="OK")
                return
            logger.info(f"Removing job {job_id} from list")
            var.scheduler.remove_job(job_id=job_id)
            config_file = os.path.join(
                var.campaign_scheduler_cache_path, f"{job_id}.json")
            if os.path.exists(config_file):
                os.remove(config_file)
                logger.info(f"Removed config file: {config_file}")
            self.reset_schedule_campaign_job_list()
            logger.info(f"Removed successfully job {job_id} from list")
        except Exception as e:
            logger.error(f"Error at remove_schedule_campaign: {e}")
            alert(text=f"Failed to remove scheduled campaign: {e}",
                  title="Warning", button="OK")

    def reset_schedule_campaign_job_list(self):
        jobs = var.scheduler.get_jobs()
        logger.info(f"Refreshing job list: {len(jobs)} jobs found")
        if threading.current_thread() is threading.main_thread():
            GUI.comboBox_scheduled_campaign_list.clear()
            for item in jobs:
                text = f"{item.next_run_time} - {item.id}"
                GUI.comboBox_scheduled_campaign_list.addItem(
                    text, userData=item.id)
                logger.info(f"Added job to combobox: {text}")
        else:
            var.command_q.put("GUI.comboBox_scheduled_campaign_list.clear()")
            for item in var.scheduler.get_jobs():
                text = f"{item.next_run_time} - {item.id}"
                var.command_q.put(
                    f"GUI.comboBox_scheduled_campaign_list.addItem('{text}', userData='{item.id}')"
                )

    def run_scheduled_campaign(self, config_filename: str):
        try:
            logger.info(
                f"Starting {self.__class__.__name__}.run_scheduled_campaign id: {config_filename}"
            )
            if not var.send_campaign_run_status:
                with open(
                    "{}/{}.json".format(
                        var.campaign_scheduler_cache_path, config_filename
                    )
                ) as json_file:
                    data = load(json_file)
                    campaign_group = data["config"]["campaign_group"]
                    var.num_emails_per_address = data["config"][
                        "num_emails_per_address"
                    ]
                    var.delay_between_emails = data["config"]["delay_between_emails"]
                    var.limit_of_thread = data["config"]["limit_of_thread"]
                var.command_q.put(
                    f"GUI.lineEdit_num_per_address.setText('{var.num_emails_per_address}')")
                var.command_q.put(
                    f"GUI.lineEdit_delay_between_emails.setText('{var.delay_between_emails}')")
                var.command_q.put(
                    f"GUI.lineEdit_number_of_threads.setText('{var.limit_of_thread}')")
                if campaign_group == "group_a":
                    var.command_q.put(
                        "GUI.radioButton_campaign_group_a.setChecked(True)")
                else:
                    var.command_q.put(
                        "GUI.radioButton_campaign_group_b.setChecked(True)")
                if var.AirtableConfig.continuous_loading:
                    pull_target_airtable = database.PullTargetAirtable()
                    pull_target_airtable.start()
                    while database.PullTargetAirtable.still_running:
                        time.sleep(1)
                var.stop_send_campaign = False
                var.thread_open_campaign = 0
                var.send_campaign_email_count = 0
                var.command_q.put("GUI.pushButton_send.setEnabled(False)")
                self.send_campaign()
            else:
                logger.info(
                    "Campaign running, scheduled campaign cancelled || campaign id: {config_filename}"
                )
            logger.info(
                f"Completing {self.__class__.__name__}.run_scheduled_campaign id: {config_filename}"
            )
            self.reset_schedule_campaign_job_list()
        except Exception as e:
            logger.info(
                f"Error at main.run_scheduled_campaign id - ({config_filename}) : {traceback.format_exc()}"
            )

    def pull_target_from_airtable(self):
        pull_target_airtable = database.PullTargetAirtable()
        pull_target_airtable.start()

    def update_cc_emails(self):
        var.cc_emails = GUI.lineEdit_cc_emails.text().replace(" ", "")

    def update_airtable_config(self):
        var.AirtableConfig.base_id = GUI.lineEdit_airtable_base_id.text()
        var.AirtableConfig.api_key = GUI.lineEdit_airtable_api_key.text()
        var.AirtableConfig.table_name = GUI.lineEdit_airtable_table_name.text()
        var.AirtableConfig.use_desktop_id = (
            True if GUI.checkBox_airtable_use_desktop_id.isChecked() else False
        )
        var.AirtableConfig.mark_sent_airtable = (
            True if GUI.checkBox_mark_sent_airtable.isChecked() else False
        )
        var.AirtableConfig.continuous_loading = (
            True if GUI.checkBox_continuous_loading_airtable.isChecked() else False
        )
        self.configuration_save()

    def update_autoReply_body(self):
        if var.autoReply_canned_switch:
            var.autoReply_body = GUI.textBrowser_autoReply_body.toPlainText()
        else:
            var.autoReply_prompt = GUI.textBrowser_autoReply_body.toPlainText()

    def update_autoReply_switch(self):
        var.autoReply_switch = GUI.radioButton_positive.isChecked()
        self.configuration_save()

    def update_autoReply_canned_switch(self):
        var.autoReply_canned_switch = GUI.radioButton_canned_reply.isChecked()
        if var.autoReply_canned_switch:
            GUI.textBrowser_autoReply_body.setText(var.autoReply_body)
        else:
            GUI.textBrowser_autoReply_body.setText(var.autoReply_prompt)
        self.configuration_save()

    def update_autoReply_enabled(self):
        var.autoReply_enabled = GUI.checkBox_configuration_autoReply_enabled.isChecked()
        self.configuration_save()
        if GUI.checkBox_configuration_autoReply_enabled.isChecked():
            self.autoReply_timer.start()
        else:
            self.autoReply_timer.stop()

    def update_autoReply_intervals(self):
        value = GUI.lineEdit_configuration_scan_interval.text()
        self.configuration_save()
        if is_number(value):
            var.autoReply_intervals = float(value)
        else:
            self.logger.error(
                "Auto-reply scan interval value can only be Numerical")

    def autoReply_start(self):
        try:
            self.autoReply_timer.stop()
            if var.download_email_status:
                return
            var.download_email_status = True
            var.stop_download = False
            self.autoReply_finished = False
            logger.info("autoReply Start")
            from imap import main
            # Get the appropriate last date based on autoReply switch
            # if var.autoReply_switch:
            #     last_date = self.autoReply_positive_last_date
            #     self.autoReply_positive_last_date = datetime.now().strftime(
            #             "%Y-%m-%d %H:%M:%S"
            #         )
            # else:
            #     last_date = self.autoReply_all_last_date
            #     self.autoReply_all_last_date = datetime.now().strftime(
            #             "%Y-%m-%d %H:%M:%S"
            #         )
            # # Convert the date string to QDate and format it
            # date_obj = QtCore.QDate.fromString(last_date[:10], "yyyy-MM-dd")
            # if date_obj >= QtCore.QDate.currentDate():
            #     date_obj = QtCore.QDate.currentDate().addDays(-1)  # Set to 1 day before today if date is today or later
            # date = date_obj.toString("M/d/yyyy")
            # logger.info(date)
            Thread(target=main, daemon=True, args=[pd.concat(
                [var.group_a, var.group_b]), ["INBOX"], var.date]).start()
            self.autoReply_email_timer.start()
        except Exception as e:
            self.autoReply_timer.start()

    def autoReply_email_read(self):
        if not var.download_email_status:
            logger.info("autoReply email download end")
            var.stop_download = True
            self.autoReply_email_timer.stop()
            self.autoReply_save_emails()

    def autoReply_save_emails(self):
        try:
            email_list = []
            while not var.email_q.empty():
                row_data = var.email_q.get()
                row_data["checkbox_status"] = 0
                email_list.append(row_data)
            if email_list:
                new_data = pd.DataFrame(email_list)
                new_data = new_data[new_data["is_sent"] == False].copy()
                for data in new_data.itertuples():
                    logger.info(
                        f"Adding email from {data.from_mail} to inbox_data"
                    )
                valid_emails = set()
                for group in [var.group_a, var.group_b]:
                    if not group.empty and "EMAIL" in group.columns:
                        valid_emails.update(group["EMAIL"])
                new_data = new_data[new_data["to_mail"].isin(valid_emails)]
                logger.info("Read email success")
                logger.info(len(new_data))
                self.autoReply_sentiment_detect(new_data)
            else:
                self.autoReply_timer.start()
                self.autoReply_finished_timer.stop()
        except Exception as e:
            self.autoReply_timer.start()
            self.autoReply_finished_timer.stop()
            self.logger.error("Error at add data to inbox_data - {}".format(e))

    def autoReply_sentiment_detect(self, temp_inbox_data):
        try:
            if var.autoReply_switch:
                new_emails_positive = temp_inbox_data[
                    temp_inbox_data.apply(
                        lambda row: self.get_sentiment_textblob(
                            row["body"], row["to_mail"]
                        ),
                        axis=1,
                    )
                ]
                new_emails_duplicate = new_emails_positive[
                    new_emails_positive.apply(
                        lambda row: self.get_duplicate_autoReply_state(
                            row["from_mail"]
                        ),
                        axis=1,
                    )
                ]
                logger.info("email sentiment finished.")
                logger.info(len(temp_inbox_data))
                if not new_emails_positive.empty:
                    logger.info(
                        f"Count of positive emails: {new_emails_duplicate.shape[0]}"
                    )
                    Thread(
                        target=self.send_autoReply,
                        args=(new_emails_duplicate,),
                        daemon=True,
                    ).start()
                    self.autoReply_finished_timer.start()
                else:
                    self.autoReply_timer.start()
                    self.autoReply_finished_timer.stop()
            else:
                new_emails_duplicate = temp_inbox_data[
                    temp_inbox_data.apply(
                        lambda row: self.get_duplicate_autoReply_state(
                            row["from_mail"]
                        ),
                        axis=1,
                    )
                ]
                if not new_emails_duplicate.empty:
                    Thread(
                        target=self.send_autoReply,
                        args=(new_emails_duplicate,),
                        daemon=True,
                    ).start()
                    self.autoReply_finished_timer.start()
                else:
                    self.autoReply_timer.start()
                    self.autoReply_finished_timer.stop()
            self.configuration_save()
        except Exception as e:
            self.autoReply_timer.start()
            self.autoReply_finished_timer.stop()

    def wait_autoReply_finished(self):
        if self.autoReply_finished:
            self.autoReply_finished_timer.stop()
            self.autoReply_timer.start()

    def send_autoReply(self, emails):
        client = None
        if not var.autoReply_canned_switch:
            logger.info("send auto reply")
            if not var.autoReply_prompt or not var.autoReply_prompt.strip():
                alert(text="Please enter a prompt.",
                      title="Warning", button="OK")
                return
            effective_key = get_effective_openai_key()
            if effective_key:
                try:
                    client = OpenAI(api_key=effective_key)
                except Exception as e:
                    logger.error(
                        f"Failed to initialize OpenAI client: {str(e)}")
                    return

        file_path = None
        if not var.autoReply_canned_switch:
            try:
                sent_folder = "sent"
                os.makedirs(sent_folder, exist_ok=True)
                today_date = datetime.now().strftime("%Y-%m-%d")
                file_path = os.path.join(
                    sent_folder, f"{today_date}_responses.txt")
            except Exception as e:
                logger.error(f"Failed to setup file handling: {str(e)}")
                return

        if emails.empty:
            logger.warning("No emails to process.")
            return

        try:
            for index, row in emails.iterrows():
                try:
                    var.email_in_view = row.to_dict()
                    var.email_in_view["original_body"] = row["body"]
                    var.email_in_view["original_subject"] = row["subject"]

                    if var.autoReply_canned_switch:
                        var.email_in_view["body"] = var.autoReply_body
                    else:
                        prompt = (
                            var.autoReply_prompt.strip() if var.autoReply_prompt else ""
                        )
                        if not prompt:
                            alert(
                                text="Please enter a prompt.",
                                title="Warning",
                                button="OK",
                            )
                            return

                        new_prompt = prompt.replace(
                            "[RECEIVEDEMAIL]", row["body"])
                        try:
                            if client:
                                response = client.chat.completions.create(
                                    model=get_effective_openai_model(),
                                    messages=[
                                        {"role": "system",
                                            "content": "You are an expert email copywriter."},
                                        {"role": "user", "content": new_prompt},
                                    ],
                                )
                                answer = response.choices[0].message.content
                            else:
                                answer = _call_server_ai(new_prompt)
                            var.email_in_view["body"] = answer

                            with open(file_path, "a", encoding="utf-8") as file:
                                file.write(
                                    "==================================================\n"
                                )
                                file.write(
                                    f"Time: {datetime.now().strftime('%H:%M:%S')}\n"
                                )
                                file.write(
                                    f"Original Subject: {var.email_in_view['original_subject']}\n"
                                )
                                file.write(
                                    f"Original Body: {var.email_in_view['original_body']}\n"
                                )
                                file.write(f"GPT Answer:\n{answer}\n")
                                file.write(
                                    "==================================================\n\n"
                                )

                            logger.info(f"Response saved to {file_path}")
                        except OpenAIAuthError:
                            alert(
                                text=(
                                    "Your OpenAI API key is invalid or has expired.\n\n"
                                    "To use the built-in AI access instead, go to "
                                    "Configuration \u2192 OpenAI key and clear the key field, then save."
                                ),
                                title="Invalid API Key",
                                button="OK",
                            )
                            return
                        except Exception as e:
                            logger.error(
                                f"Failed to generate AI response: {str(e)}")
                            continue

                    from smtp import ReplyMail

                    reply_mail = ReplyMail()
                    result = reply_mail.send()

                    if result == 1:
                        logger.info("Reply successful")
                    else:
                        logger.error("Replying Failed!!!")

                except Exception as e:
                    logger.error(f"Error processing email {index}: {str(e)}")
                    continue

            logger.info("autoReply_ended")

        except Exception as e:
            logger.error(f"Error in auto-reply process: {str(e)}")
        finally:
            # Ensure this is always set, even if an exception occurs
            self.autoReply_finished = True

    def get_duplicate_autoReply_state(self, from_mail):
        file_path = var.autoreply_address_file_path
        try:
            with open(file_path, "r") as file:
                addresses = set((line.strip() for line in file))
        except FileNotFoundError:
            addresses = set()
            with open(file_path, "w") as file:
                pass
        if from_mail in addresses:
            return False
        with open(file_path, "a") as file:
            file.write(from_mail + "\n")
        return True

    def get_sentiment_textblob(self, body, to_mail):
        logger.info("sentiment")
        if not isinstance(body, str):
            body = str(body)
        if not isinstance(to_mail, str):
            to_mail = str(to_mail)
        cleaned_body = body.encode("utf-8", errors="ignore").decode("utf-8")
        logger.info(f"body: {cleaned_body}")
        logger.info(to_mail)
        parts = cleaned_body.split(to_mail)
        text = parts[0]
        blob = TextBlob(text)
        sentiment_score = blob.sentiment.polarity
        try:
            with open(var.blacklist_file_path, "r") as file:
                negative_words = file.read().strip().splitlines()
        except FileNotFoundError:
            logger.info(
                f"Warning: '{var.blacklist_file_path}' not found. Using default negative words."
            )
            negative_words = [
                "no",
                "stop",
                "nope",
                "nah",
                "not interested",
                "decline",
                "can't",
                "won't",
                "don't want",
            ]
        if negative_words:
            negative_words = [n.strip() for n in negative_words if n.strip()]
            logger.info(negative_words[0])
            negative_patterns = re.compile(
                "\\b(" + "|".join(map(re.escape, negative_words)) +
                ")\\b", re.IGNORECASE
            )
            if negative_patterns.search(text):
                sentiment_score = -1
        logger.info(f"sentiment {sentiment_score}")
        if sentiment_score > 0:
            logger.info("positive:")
            logger.info(text)
            return True
        if sentiment_score < 0:
            logger.info("negative:")
            logger.info(text)
            return False
        logger.info("neutral(slight positive):")
        logger.info(text)
        return True

    def update_followup_body(self):
        var.followup_body = GUI.textBrowser_follow_up_body.toPlainText()

    def update_followup_subject(self):
        var.followup_subject = GUI.lineEdit_follow_up_subject.text()

    def change_followup_days(self):
        value = GUI.lineEdit_configuration_followup_days.text()
        if is_number(value):
            var.followup_days = float(value)
        else:
            self.logger.error("FollowUp days value can only be Numerical")

    def update_delay_between_emails(self):
        try:
            delay_between_emails = GUI.lineEdit_delay_between_emails.text()
            var.delay_start = int(delay_between_emails.split("-")[0].strip())
            var.delay_end = int(delay_between_emails.split("-")[1].strip())
            var.delay_between_emails = delay_between_emails
        except:
            self.logger.error(traceback.format_exc())

    def update_campaign_group(self):
        if GUI.radioButton_campaign_group_a.isChecked():
            var.campaign_group = "group_a"
        else:
            var.campaign_group = "group_b"

    def update_num_per_address(self):
        try:
            temp_input = str(
                GUI.lineEdit_num_per_address.text()).replace(" ", "")
            if "-" not in temp_input:
                GUI.lineEdit_num_per_address.setText(
                    temp_input if "-" in temp_input else temp_input + " - "
                )
            var.num_emails_per_address = str(
                GUI.lineEdit_num_per_address.text()
            ).replace(" ", "")
        except:
            self.logger.error(traceback.format_exc())

    def compose_subject_update(self, value: str):
        var.compose_email_subject = value

    def clear_cached_targets(self):
        db = database.Database()
        db.clear_cached_targets()
        alert(text="Cached cleared.", title="Alert", button="OK")

    def change_open_ai_key(self):
        var.open_ai_key = GUI.lineEdit_open_ai_key.text().strip().replace(" ", "")

    def change_open_ai_model(self):
        var.open_ai_model = GUI.lineEdit_open_ai_model.text().strip()

    def setup_statistics_page(self):
        if self.statistics_page_index is not None:
            return

        stats_item = QtWidgets.QListWidgetItem("Statistics")
        GUI.listWidget.insertItem(5, stats_item)

        page = QtWidgets.QWidget()
        page.setObjectName("statisticsPage")
        page.setStyleSheet(
            "QWidget#statisticsPage { background-color: #ffffff; }"
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QWidget#statisticsContent { background: transparent; }"
            "QWidget#statisticsContent QLabel { background: transparent; border: none; padding: 0; }"
            "QFrame#statisticsControls QLabel, QFrame#statisticsKpiCard QLabel { "
            "background: transparent; border: none; padding: 0; }"
        )
        outer_layout = QtWidgets.QVBoxLayout(page)
        outer_layout.setContentsMargins(24, 24, 24, 24)

        scroll_area = QtWidgets.QScrollArea(page)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        content.setObjectName("statisticsContent")
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 6)
        header.setSpacing(16)
        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(6)
        title = QtWidgets.QLabel("Statistics")
        title.setMinimumHeight(34)
        title.setStyleSheet(
            "QLabel { background: transparent; border: none; padding: 0; "
            "font-family: Arial; font-size: 26px; font-weight: bold; color: #111827; }"
        )
        subtitle = QtWidgets.QLabel("Executive campaign report and white-label PDF export")
        subtitle.setMinimumHeight(18)
        subtitle.setStyleSheet(
            "QLabel { background: transparent; border: none; padding: 0; "
            "font-family: Arial; font-size: 12px; color: #667085; }"
        )
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.pushButton_statistics_refresh = QtWidgets.QPushButton("Refresh")
        self.pushButton_statistics_export_pdf = QtWidgets.QPushButton("Export PDF")
        for button in [self.pushButton_statistics_refresh, self.pushButton_statistics_export_pdf]:
            button.setMinimumSize(QtCore.QSize(126, 40))
            button.setMaximumHeight(40)
            button.setStyleSheet(self._statistics_button_style())
            header.addWidget(button)
        layout.addLayout(header)

        controls = QtWidgets.QFrame()
        controls.setObjectName("statisticsControls")
        controls.setStyleSheet(self._statistics_panel_style())
        controls_layout = QtWidgets.QGridLayout(controls)
        controls_layout.setContentsMargins(24, 20, 24, 20)
        controls_layout.setHorizontalSpacing(20)
        controls_layout.setVerticalSpacing(14)
        for column in range(4):
            controls_layout.setColumnStretch(column, 1)

        self.comboBox_statistics_date_filter = QtWidgets.QComboBox()
        self.comboBox_statistics_date_filter.addItems(["Last 30 Days", "All Time", "Custom"])
        self.dateEdit_statistics_start = QtWidgets.QDateEdit()
        self.dateEdit_statistics_end = QtWidgets.QDateEdit()
        self.comboBox_statistics_date_filter.setMinimumHeight(42)
        self.comboBox_statistics_date_filter.setStyleSheet(
            self._statistics_input_style())
        for date_edit in [self.dateEdit_statistics_start, self.dateEdit_statistics_end]:
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setStyleSheet(self._statistics_input_style())
            date_edit.setMinimumHeight(42)
        today = QtCore.QDate.currentDate()
        self.dateEdit_statistics_start.setDate(today.addDays(-30))
        self.dateEdit_statistics_end.setDate(today)

        self.doubleSpinBox_statistics_product_price = QtWidgets.QDoubleSpinBox()
        self.doubleSpinBox_statistics_product_price.setPrefix("$ ")
        self.doubleSpinBox_statistics_product_price.setMaximum(100000000)
        self.doubleSpinBox_statistics_product_price.setDecimals(2)
        self.doubleSpinBox_statistics_product_price.setSingleStep(100)
        self.doubleSpinBox_statistics_product_price.setMinimumHeight(42)
        self.doubleSpinBox_statistics_product_price.setStyleSheet(
            self._statistics_input_style())

        self.label_statistics_logo_value = QtWidgets.QLabel("No logo selected")
        self.label_statistics_logo_value.setMinimumHeight(44)
        self.label_statistics_logo_value.setStyleSheet(
            "QLabel { border: 1px solid #d8e0ea; border-radius: 8px; "
            "background-color: #ffffff; padding: 0 12px; color: #667085; "
            "font-family: Arial; font-size: 12px; }"
        )
        self.pushButton_statistics_choose_logo = QtWidgets.QPushButton("Choose Logo")
        self.pushButton_statistics_clear_logo = QtWidgets.QPushButton("Clear Logo")
        for button in [self.pushButton_statistics_choose_logo, self.pushButton_statistics_clear_logo]:
            button.setMinimumHeight(44)
            button.setStyleSheet(self._statistics_secondary_button_style())

        controls_layout.addWidget(self._statistics_field_label("Date Range"), 0, 0)
        controls_layout.addWidget(self.comboBox_statistics_date_filter, 1, 0)
        controls_layout.addWidget(self._statistics_field_label("Start"), 0, 1)
        controls_layout.addWidget(self.dateEdit_statistics_start, 1, 1)
        controls_layout.addWidget(self._statistics_field_label("End"), 0, 2)
        controls_layout.addWidget(self.dateEdit_statistics_end, 1, 2)
        controls_layout.addWidget(self._statistics_field_label("Product Price"), 0, 3)
        controls_layout.addWidget(self.doubleSpinBox_statistics_product_price, 1, 3)
        controls_layout.addWidget(self._statistics_field_label("White-label Logo"), 2, 0)
        controls_layout.addWidget(self.label_statistics_logo_value, 3, 0, 1, 2)
        controls_layout.addWidget(self.pushButton_statistics_choose_logo, 3, 2)
        controls_layout.addWidget(self.pushButton_statistics_clear_logo, 3, 3)
        layout.addWidget(controls)

        self.statistics_kpi_frame = self._build_statistics_kpi_frame(content)
        layout.addWidget(self.statistics_kpi_frame)

        self.statistics_metric_tabs = self._build_statistics_metric_tabs(content)
        layout.addWidget(self.statistics_metric_tabs)

        self.statistics_preview = create_statistics_report_preview(content)
        layout.addWidget(self.statistics_preview)
        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)
        self.statistics_page_index = GUI.stackedWidget.addWidget(page)

        self._load_statistics_settings()
        self._update_statistics_date_controls()
        self.pushButton_statistics_refresh.clicked.connect(self.refresh_statistics)
        self.pushButton_statistics_export_pdf.clicked.connect(self.export_statistics_pdf)
        self.pushButton_statistics_choose_logo.clicked.connect(self.choose_statistics_logo)
        self.pushButton_statistics_clear_logo.clicked.connect(self.clear_statistics_logo)
        self.comboBox_statistics_date_filter.currentTextChanged.connect(
            self._update_statistics_date_controls)
        self.doubleSpinBox_statistics_product_price.editingFinished.connect(
            self.save_statistics_settings)
        self.refresh_statistics(save_settings=False)

    def _build_statistics_kpi_frame(self, parent):
        frame = QtWidgets.QFrame(parent)
        frame.setObjectName("statisticsControls")
        frame.setStyleSheet(self._statistics_panel_style())
        grid = QtWidgets.QGridLayout(frame)
        grid.setContentsMargins(18, 18, 18, 18)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        cards = [
            ("meetings_booked", "Meetings Booked"),
            ("opportunities", "Opportunities"),
            ("revenue_generated", "Revenue"),
            ("positive_reply_rate", "Positive Reply"),
            ("delivery_rate", "Deliverability"),
            ("roi", "ROI"),
            ("cost_per_meeting", "Cost / Meeting"),
            ("valid_email_rate", "Lead Quality"),
        ]
        for index, (key, label) in enumerate(cards):
            card = QtWidgets.QFrame(frame)
            card.setObjectName("statisticsKpiCard")
            card.setStyleSheet(self._statistics_panel_style())
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(6)
            title = QtWidgets.QLabel(label)
            title.setStyleSheet(
                "QLabel { color: #667085; font-family: Arial; font-size: 10px; "
                "font-weight: bold; text-transform: uppercase; }"
            )
            value = QtWidgets.QLabel("0")
            value.setMinimumHeight(28)
            value.setStyleSheet(
                "QLabel { color: #111827; font-family: Arial; font-size: 22px; "
                "font-weight: bold; }"
            )
            card_layout.addWidget(title)
            card_layout.addWidget(value)
            self.statistics_kpi_value_labels[key] = value
            grid.addWidget(card, index // 4, index % 4)
        return frame

    def _build_statistics_metric_tabs(self, parent):
        tabs = QtWidgets.QTabWidget(parent)
        tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #d8e3ee; background: #ffffff; "
            "border-radius: 8px; } "
            "QTabWidget::pane > QWidget { background: #ffffff; } "
            "QTabBar::tab { background: #dce5f0; color: #344054; padding: 9px 14px; "
            "font-family: Arial; font-size: 11px; font-weight: bold; border-top-left-radius: 6px; "
            "border-top-right-radius: 6px; margin-right: 3px; } "
            "QTabBar::tab:selected { background: #ffffff; color: #028fc3; }"
        )
        for section_title, auto_fields, manual_fields, calculated_fields in self._statistics_sections():
            page = QtWidgets.QWidget()
            page.setAutoFillBackground(True)
            page.setStyleSheet("QWidget { background-color: #ffffff; }")
            layout = QtWidgets.QGridLayout(page)
            layout.setContentsMargins(18, 18, 18, 18)
            layout.setHorizontalSpacing(8)
            layout.setVerticalSpacing(8)
            for column in range(2):
                layout.setColumnStretch(column, 1)
            row = 0
            if auto_fields:
                auto_header = self._statistics_section_header("Auto-detected", kind="auto")
                layout.addWidget(auto_header, row, 0, 1, 2)
                row += 1
                for index, (key, label, kind) in enumerate(auto_fields):
                    self._add_statistics_calculated_field(
                        layout, row + index // 2, index % 2, key, label, kind, source="auto"
                    )
                row += (len(auto_fields) + 1) // 2
            if manual_fields:
                manual_header = self._statistics_section_header("Manual overrides", kind="manual")
                layout.addWidget(manual_header, row, 0, 1, 2)
                row += 1
                for index, (key, label, kind) in enumerate(manual_fields):
                    self._add_statistics_manual_field(layout, row + index // 2, index % 2, key, label, kind)
                row += (len(manual_fields) + 1) // 2
            if calculated_fields:
                calc_header = self._statistics_section_header("Calculated rates", kind="calc")
                layout.addWidget(calc_header, row, 0, 1, 2)
                row += 1
                for index, (key, label, kind) in enumerate(calculated_fields):
                    self._add_statistics_calculated_field(layout, row + index // 2, index % 2, key, label, kind)
            tabs.addTab(page, section_title)
        return tabs

    def _statistics_section_header(self, text, kind="calc"):
        container = QtWidgets.QWidget()
        container.setStyleSheet("QWidget { background: transparent; }")
        h = QtWidgets.QHBoxLayout(container)
        h.setContentsMargins(0, 6, 0, 4)
        h.setSpacing(6)
        dot = QtWidgets.QLabel()
        dot.setFixedSize(8, 8)
        if kind == "manual":
            color = "#6366f1"
        elif kind == "auto":
            color = "#059669"
        else:
            color = "#028fc3"
        dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        lbl = QtWidgets.QLabel(text.upper())
        lbl.setStyleSheet(
            "QLabel { color: #374151; font-family: Arial; font-size: 10px; "
            "font-weight: bold; letter-spacing: 0.7px; background: transparent; border: none; }"
        )
        h.addWidget(dot)
        h.addWidget(lbl)
        h.addStretch()
        return container

    def _add_statistics_manual_field(self, layout, row, column, key, label, kind):
        chip = QtWidgets.QFrame()
        chip.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #d1d5db; border-radius: 8px; }"
            "QFrame QLabel { background: transparent; border: none; }"
        )
        chip_layout = QtWidgets.QVBoxLayout(chip)
        chip_layout.setContentsMargins(10, 8, 10, 8)
        chip_layout.setSpacing(4)
        lbl = QtWidgets.QLabel(label)
        lbl.setStyleSheet(
            "QLabel { color: #6b7280; font-family: Arial; font-size: 10px; font-weight: 600; }"
        )
        chip_layout.addWidget(lbl)
        if kind == "text":
            field = QtWidgets.QLineEdit()
            field.setStyleSheet(
                "QLineEdit { border: none; background: transparent; padding: 0; "
                "font-family: Arial; font-size: 13px; font-weight: 600; color: #374151; }"
            )
            field.editingFinished.connect(self.refresh_statistics)
        else:
            field = QtWidgets.QDoubleSpinBox()
            field.setMaximum(1000000000)
            field.setDecimals(2 if kind in ("currency", "decimal") else 0)
            field.setSingleStep(100 if kind == "currency" else 1)
            if kind == "currency":
                field.setPrefix("$ ")
            if kind == "percent":
                field.setSuffix(" %")
                field.setMaximum(100)
            field.setStyleSheet(
                "QDoubleSpinBox { border: none; background: transparent; padding: 0; "
                "font-family: Arial; font-size: 13px; font-weight: 600; color: #374151; }"
                "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button "
                "{ width: 18px; border: none; background: transparent; }"
            )
            field.editingFinished.connect(self.refresh_statistics)
            field.valueChanged.connect(self.refresh_statistics)
        self.statistics_manual_fields[key] = field
        chip_layout.addWidget(field)
        layout.addWidget(chip, row, column)

    def _add_statistics_calculated_field(self, layout, row, column, key, label, kind, source="calc"):
        chip = QtWidgets.QFrame()
        if source == "auto":
            chip.setStyleSheet(
                "QFrame { background: #ecfdf3; border: 1px solid #bbf7d0; border-radius: 8px; }"
                "QFrame QLabel { background: transparent; border: none; }"
            )
            value_color = "#047857"
        else:
            chip.setStyleSheet(
                "QFrame { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; }"
                "QFrame QLabel { background: transparent; border: none; }"
            )
            value_color = "#0369a1"
        chip_layout = QtWidgets.QVBoxLayout(chip)
        chip_layout.setContentsMargins(10, 8, 10, 8)
        chip_layout.setSpacing(3)
        lbl = QtWidgets.QLabel(label)
        lbl.setStyleSheet(
            "QLabel { color: #6b7280; font-family: Arial; font-size: 10px; font-weight: 600; }"
        )
        value = QtWidgets.QLabel("0")
        value.setStyleSheet(
            f"QLabel {{ color: {value_color}; font-family: Arial; font-size: 15px; font-weight: 700; }}"
        )
        chip_layout.addWidget(lbl)
        chip_layout.addWidget(value)
        self.statistics_calculated_labels.setdefault(key, []).append((value, kind))
        layout.addWidget(chip, row, column)

    def _statistics_field_label(self, text):
        label = QtWidgets.QLabel(text)
        label.setMinimumHeight(18)
        label.setStyleSheet(
            "QLabel { background: transparent; border: none; padding: 0; "
            "font-family: Arial; font-size: 11px; color: #667085; font-weight: bold; }"
        )
        return label

    def _statistics_panel_style(self):
        return (
            "QFrame#statisticsControls, QFrame#statisticsKpiCard { "
            "background-color: #eef2f7; border: 1px solid #d8e3ee; "
            "border-radius: 10px; } "
            "QFrame#statisticsControls QLabel, QFrame#statisticsKpiCard QLabel { "
            "background: transparent; border: none; padding: 0; }"
        )

    def _statistics_button_style(self):
        return (
            "QPushButton { border: 1px solid #028fc3; border-radius: 8px; "
            "background-color: #028fc3; color: #ffffff; padding: 8px 18px; "
            "font-family: Arial; font-size: 12px; font-weight: 400; } "
            "QPushButton:hover { background-color: #027faf; }"
        )

    def _statistics_secondary_button_style(self):
        return (
            "QPushButton { border: 1px solid #cbd5e1; border-radius: 8px; "
            "background-color: #ffffff; color: #344054; padding: 6px 12px; "
            "font-family: Arial; font-size: 12px; font-weight: 400; } "
            "QPushButton:hover { background-color: #f8fafc; }"
        )

    def _statistics_input_style(self):
        return (
            "QComboBox, QDateEdit, QDoubleSpinBox { "
            "background-color: #ffffff; color: #111827; border: 1px solid #d8e0ea; "
            "border-radius: 8px; padding: 7px 12px; font-family: Arial; font-size: 12px; "
            "font-weight: bold; } "
            "QComboBox::drop-down, QDateEdit::drop-down, QDoubleSpinBox::up-button, "
            "QDoubleSpinBox::down-button { width: 22px; border: none; background: transparent; }"
        )

    def _statistics_text_input_style(self):
        return (
            "QLineEdit { background-color: #ffffff; color: #111827; border: 1px solid #d8e0ea; "
            "border-radius: 8px; padding: 7px 12px; font-family: Arial; font-size: 12px; "
            "font-weight: bold; }"
        )

    def _statistics_sections(self):
        return [
            (
                "Deliverability",
                [
                    ("sent_emails", "Emails Sent", "number"),
                    ("emails_delivered", "Emails Delivered", "number"),
                ],
                [
                    ("hard_bounces", "Hard Bounces", "number"),
                    ("soft_bounces", "Soft Bounces", "number"),
                    ("deferred_emails", "Deferred Emails", "number"),
                    ("blocked_emails", "Blocked Emails", "number"),
                    ("inbox_placement", "Inbox Placement", "number"),
                    ("spam_placement", "Spam Placement", "number"),
                    ("spam_complaints", "Spam Complaints", "number"),
                ],
                [
                    ("delivery_rate", "Delivery Rate", "percent"),
                    ("bounce_rate", "Bounce Rate", "percent"),
                    ("hard_bounce_rate", "Hard Bounce Rate", "percent"),
                    ("soft_bounce_rate", "Soft Bounce Rate", "percent"),
                    ("inbox_placement_rate", "Inbox Placement Rate", "percent"),
                    ("spam_folder_placement_rate", "Spam Folder Rate", "percent"),
                    ("spam_complaint_rate", "Spam Complaint Rate", "percent"),
                    ("sending_velocity", "Sending Velocity / Day", "decimal"),
                ],
            ),
            (
                "Lead Quality",
                [
                    ("leads_sourced", "Leads Sourced", "number"),
                    ("valid_email_count", "Valid Emails", "number"),
                    ("invalid_email_count", "Invalid Emails", "number"),
                    ("catch_all_count", "Catch-all Emails", "number"),
                    ("verified_email_count", "Verified Emails", "number"),
                    ("duplicate_lead_count", "Duplicate Leads", "number"),
                    ("leads_not_emailed", "Leads Not Emailed", "number"),
                ],
                [
                    ("high_value_accounts", "High-value Accounts", "number"),
                ],
                [
                    ("valid_email_rate", "Valid Email Rate", "percent"),
                    ("invalid_email_rate", "Invalid Email Rate", "percent"),
                    ("catch_all_domain_percentage", "Catch-all Percentage", "percent"),
                    ("verified_email_percentage", "Verified Percentage", "percent"),
                    ("duplicate_lead_rate", "Duplicate Lead Rate", "percent"),
                    ("high_value_account_percentage", "High-value Percentage", "percent"),
                ],
            ),
            (
                "Campaign",
                [
                    ("positive_replies", "Positive Replies", "number"),
                    ("negative_replies", "Negative Replies", "number"),
                ],
                [
                    ("open_total", "Total Opens", "number"),
                    ("unique_opens", "Unique Opens", "number"),
                    ("clicks", "Clicks", "number"),
                    ("unsubscribes", "Unsubscribes", "number"),
                    ("forwards", "Forwards", "number"),
                ],
                [
                    ("open_rate", "Open Rate", "percent"),
                    ("unique_open_rate", "Unique Open Rate", "percent"),
                    ("click_through_rate", "CTR", "percent"),
                    ("total_reply_rate", "Reply Rate", "percent"),
                    ("unsubscribe_rate", "Unsubscribe Rate", "percent"),
                    ("forwarding_rate", "Forwarding Rate", "percent"),
                    ("calendar_booking_rate", "Calendar Booking Rate", "percent"),
                    ("conversion_rate", "Conversion Rate", "percent"),
                ],
            ),
            (
                "Replies",
                [
                    ("neutral_replies", "Neutral Replies", "number"),
                    ("interested_replies", "Interested Replies", "number"),
                    ("objection_replies", "Objection Replies", "number"),
                    ("not_now_replies", "Not-now Replies", "number"),
                    ("referral_replies", "Referral Replies", "number"),
                    ("out_of_office_replies", "Out-of-office Replies", "number"),
                    ("automated_replies", "Automated Replies", "number"),
                    ("average_response_time_hours", "Avg Response Time Hours", "decimal"),
                ],
                [
                    ("ongoing_conversations", "Ongoing Conversations", "number"),
                    ("sales_qualified_conversations", "Sales-qualified Conversations", "number"),
                ],
                [
                    ("positive_sentiment_ratio", "Positive Sentiment Ratio", "percent"),
                    ("negative_sentiment_ratio", "Negative Sentiment Ratio", "percent"),
                    ("positive_reply_rate", "Positive Reply Rate", "percent"),
                    ("negative_reply_rate", "Negative Reply Rate", "percent"),
                    ("neutral_reply_rate", "Neutral Reply Rate", "percent"),
                    ("interested_reply_rate", "Interested Reply Rate", "percent"),
                    ("objection_rate", "Objection Rate", "percent"),
                    ("conversation_continuation_rate", "Continuation Rate", "percent"),
                    ("sales_qualified_conversation_rate", "SQ Conversation Rate", "percent"),
                ],
            ),
            (
                "Sales / ROI",
                [],
                [
                    ("meetings_booked", "Meetings Booked", "number"),
                    ("meetings_held", "Meetings Held", "number"),
                    ("no_shows", "No-shows", "number"),
                    ("opportunities", "Opportunities", "number"),
                    ("accepted_opportunities", "Accepted Opportunities", "number"),
                    ("closed_deals", "Closed Deals", "number"),
                    ("pipeline_generated", "Pipeline Generated", "currency"),
                    ("revenue_generated", "Revenue Generated", "currency"),
                    ("total_cost", "Total Cost", "currency"),
                    ("lifetime_value", "Lifetime Value", "currency"),
                    ("payback_period_days", "Payback Period Days", "decimal"),
                    ("sales_cycle_length_days", "Sales Cycle Length Days", "decimal"),
                ],
                [
                    ("potential_earnings", "Potential Earnings", "currency"),
                    ("meeting_rate", "Meeting Rate", "percent"),
                    ("show_up_rate", "Show-up Rate", "percent"),
                    ("no_show_rate", "No-show Rate", "percent"),
                    ("opportunity_acceptance_rate", "Opportunity Acceptance", "percent"),
                    ("lead_to_opportunity_rate", "Lead-to-opportunity", "percent"),
                    ("lead_to_close_rate", "Lead-to-close", "percent"),
                    ("revenue_per_email_sent", "Revenue / Email", "currency"),
                    ("revenue_per_lead", "Revenue / Lead", "currency"),
                    ("revenue_per_meeting", "Revenue / Meeting", "currency"),
                    ("roi", "ROI", "percent"),
                    ("cost_per_meeting", "Cost / Meeting", "currency"),
                    ("cost_per_opportunity", "Cost / Opportunity", "currency"),
                    ("cost_per_acquisition", "Cost / Acquisition", "currency"),
                ],
            ),
            (
                "Warm-up",
                [
                    ("warmup_email_amounts", "Warm-up Emails", "number"),
                    ("second_emails", "Follow-ups / Warm-up Sent", "number"),
                    ("mailbox_provider_summary", "Mailbox Provider Distribution", "text"),
                ],
                [
                    ("warmup_time_days", "Time in Warm-up Days", "decimal"),
                    ("warmup_progress_percent", "Warm-up Progress", "percent"),
                    ("best_sending_time", "Best Sending Time", "text"),
                    ("best_sending_day", "Best Sending Day", "text"),
                    ("best_subject_line", "Best Subject Line", "text"),
                ],
                [
                    ("sent_emails", "Emails Sent", "number"),
                    ("warmup_progress_rate", "Warm-up Progress Rate", "percent"),
                ],
            ),
        ]

    def _load_statistics_settings(self):
        settings = getattr(var, "statistics", {}) or {}
        self.doubleSpinBox_statistics_product_price.setValue(
            float(settings.get("product_price") or 0)
        )
        date_filter = settings.get("date_filter", "last_30_days")
        index_by_filter = {"last_30_days": 0, "all_time": 1, "custom": 2}
        self.comboBox_statistics_date_filter.setCurrentIndex(
            index_by_filter.get(date_filter, 0)
        )
        self._load_statistics_manual_metrics(settings.get("manual_metrics", {}))
        self._update_statistics_logo_label()

    def _load_statistics_manual_metrics(self, manual_metrics):
        manual_metrics = manual_metrics or {}
        for key, field in self.statistics_manual_fields.items():
            value = manual_metrics.get(key, "")
            if isinstance(field, QtWidgets.QLineEdit):
                field.setText(str(value or ""))
            else:
                try:
                    field.setValue(float(value or 0))
                except Exception:
                    field.setValue(0)

    def _update_statistics_logo_label(self):
        logo_path = (getattr(var, "statistics", {}) or {}).get("logo_path", "")
        if logo_path:
            self.label_statistics_logo_value.setText(os.path.basename(logo_path))
        else:
            self.label_statistics_logo_value.setText("No logo selected")

    def _update_statistics_date_controls(self):
        custom = self.comboBox_statistics_date_filter.currentText() == "Custom"
        self.dateEdit_statistics_start.setEnabled(custom)
        self.dateEdit_statistics_end.setEnabled(custom)

    def _statistics_date_range(self):
        selected = self.comboBox_statistics_date_filter.currentText()
        if selected == "All Time":
            return DateRange(), "All time", "all_time"
        if selected == "Custom":
            start = self.dateEdit_statistics_start.date().toString("yyyy-MM-dd")
            end = self.dateEdit_statistics_end.date().toString("yyyy-MM-dd")
            return DateRange.from_dates(start, end), f"{start} to {end}", "custom"
        end = datetime.now()
        start = end - pd.Timedelta(days=30)
        return DateRange(start=start.to_pydatetime() if hasattr(start, "to_pydatetime") else start, end=end), "Last 30 days", "last_30_days"

    def save_statistics_settings(self):
        _, _, date_filter = self._statistics_date_range()
        var.statistics["product_price"] = self.doubleSpinBox_statistics_product_price.value()
        var.statistics["date_filter"] = date_filter
        var.statistics["manual_metrics"] = self._statistics_manual_metrics()
        Thread(target=update_config_json, daemon=True).start()

    def _statistics_manual_metrics(self):
        metrics = {}
        for key, field in self.statistics_manual_fields.items():
            if isinstance(field, QtWidgets.QLineEdit):
                metrics[key] = field.text().strip()
            else:
                metrics[key] = field.value()
        return metrics

    def _statistics_negative_words(self):
        try:
            with open(var.blacklist_file_path, "r", encoding="utf-8") as file:
                return [line.strip() for line in file if line.strip()]
        except FileNotFoundError:
            return None

    def refresh_statistics(self, save_settings=True):
        if save_settings:
            self.save_statistics_settings()
        date_range, date_label, _ = self._statistics_date_range()
        calculator = StatisticsCalculator(
            report_path=var.report_file_path,
            followup_report_path=var.followup_report_file_path,
            negative_words=self._statistics_negative_words(),
            reply_classifier=build_statistics_openai_reply_classifier(),
        )
        summary = calculator.calculate(
            inbox_tables=var.inbox_data_table,
            date_range=date_range,
            product_price=self.doubleSpinBox_statistics_product_price.value(),
            manual_metrics=self._statistics_manual_metrics(),
            target_table=getattr(var, "target", None),
            account_tables=[getattr(var, "group_a", None), getattr(var, "group_b", None)],
        )
        self.statistics_summary = summary
        self._update_statistics_metric_labels(summary)
        logo_path = var.statistics.get("logo_path", "")
        self.statistics_preview.set_report(
            summary,
            logo_path=logo_path,
            title="Outreach Performance",
            date_label=date_label,
        )

    def _update_statistics_metric_labels(self, summary):
        for key, labels in self.statistics_calculated_labels.items():
            for label, kind in labels:
                label.setText(self._format_statistics_value(getattr(summary, key, 0), kind))
        kpi_kinds = {
            "meetings_booked": "number",
            "opportunities": "number",
            "revenue_generated": "currency",
            "positive_reply_rate": "percent",
            "delivery_rate": "percent",
            "roi": "percent",
            "cost_per_meeting": "currency",
            "valid_email_rate": "percent",
        }
        for key, label in self.statistics_kpi_value_labels.items():
            label.setText(self._format_statistics_value(getattr(summary, key, 0), kpi_kinds.get(key, "number")))

    def _format_statistics_value(self, value, kind):
        if kind == "currency":
            return format_currency(value)
        if kind == "percent":
            try:
                return "{}%".format(int(round(float(value) * 100)))
            except Exception:
                return "0%"
        if kind == "decimal":
            try:
                return "{:,.2f}".format(float(value)).rstrip("0").rstrip(".")
            except Exception:
                return "0"
        if kind == "text":
            return str(value or "")
        return format_number(value)

    def choose_statistics_logo(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            mainWindow,
            "Choose Logo",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp)",
        )
        if not file_path:
            return
        var.statistics["logo_path"] = file_path
        self._update_statistics_logo_label()
        self.save_statistics_settings()
        self.refresh_statistics(save_settings=False)

    def clear_statistics_logo(self):
        var.statistics["logo_path"] = ""
        self._update_statistics_logo_label()
        self.save_statistics_settings()
        self.refresh_statistics(save_settings=False)

    def export_statistics_pdf(self):
        self.refresh_statistics()
        default_name = os.path.join(
            self._downloads_folder(),
            f"gmonster-statistics-{datetime.now().strftime('%Y%m%d-%H%M')}.pdf",
        )
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            mainWindow,
            "Export Statistics PDF",
            default_name,
            "PDF Files (*.pdf)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"
        try:
            _, date_label, _ = self._statistics_date_range()
            export_statistics_pdf(
                file_path,
                self.statistics_summary,
                logo_path=var.statistics.get("logo_path", ""),
                title="Outreach Performance",
                date_label=date_label,
            )
            alert(text=f"Statistics PDF exported to:\n{file_path}", title="Export complete", button="OK")
        except Exception as e:
            logger.error(f"Statistics PDF export failed: {traceback.format_exc()}")
            alert(text=f"Statistics PDF export failed: {e}", title="Error", button="OK")

    def _downloads_folder(self):
        download_path = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.DownloadLocation
        )
        if download_path:
            return download_path
        fallback = os.path.join(os.path.expanduser("~"), "Downloads")
        if os.path.isdir(fallback):
            return fallback
        return os.path.expanduser("~")

    def setup_sidebar_icons(self):
        if qta is None:
            return
        icon_map = {
            "Inbox": "fa5s.inbox",
            "Campaign": "fa5s.paper-plane",
            "Database": "fa5s.database",
            "Tools": "fa5s.tools",
            "Follow-up": "fa5s.reply",
            "Auto-reply": "fa5s.robot",
            "Statistics": "fa5s.chart-bar",
            "Store": "fa5s.shopping-bag",
            "Leads": "fa5s.user-friends",
            "Tutorials": "fa5s.book-open",
            "Support": "fa5s.life-ring",
            "Warm up": "fa5s.fire",
            "Settings": "fa5s.cog",
            "Account": "fa5s.user-circle",
            "Unsubscribes": "fa5s.user-slash",
        }
        GUI.listWidget.setIconSize(QtCore.QSize(16, 16))
        for index in range(GUI.listWidget.count()):
            item = GUI.listWidget.item(index)
            if item is None:
                continue
            icon_name = icon_map.get(item.text())
            if not icon_name:
                continue
            item.setIcon(qta.icon(icon_name, color="#666666"))

    def change_target_blacklist(self):
        target_blacklist = GUI.lineEdit_target_blacklist.text().strip().replace(" ", "")
        if target_blacklist:
            var.target_blacklist = target_blacklist.split(",")
        else:
            var.target_blacklist = list()

    def change_inbox_blacklist(self):
        inbox_blacklist = GUI.lineEdit_inbox_blacklist.text().strip().replace(" ", "")
        if inbox_blacklist:
            var.inbox_blacklist = inbox_blacklist.split(",")
            var.inbox_blacklist = list(filter(None, var.inbox_blacklist))
        else:
            var.inbox_blacklist = list()

    def change_inbox_whitelist(self):
        inbox_whitelist = GUI.lineEdit_inbox_whitelist.text().strip().replace(" ", "")
        if inbox_whitelist:
            var.inbox_whitelist_checkbox = True
            var.inbox_whitelist = inbox_whitelist.split(",")
            var.inbox_whitelist = list(filter(None, var.inbox_whitelist))
        else:
            var.inbox_whitelist_checkbox = False
            var.inbox_whitelist = list()

    def update_checkbox_proxy(self):
        var.proxy_on = GUI.checkBox_proxy_enabled.isChecked()

    def update_hide_warmup_emails(self):
        var.hide_warmup_emails = GUI.checkBox_hide_warmup_emails.isChecked()
        if var.hide_warmup_emails:
            threading.Thread(
                target=self._fetch_warmup_pool_accounts, daemon=True).start()
        else:
            var.warmup_pool_accounts = []
        self.configuration_save()

    def _fetch_warmup_pool_accounts(self):
        try:
            resp = requests.get(
                f"{var.api}warming/pool_accounts",
                timeout=var.API_SLOW_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                var.warmup_pool_accounts = [
                    acc['email'].lower()
                    for acc in data.get('accounts', [])
                    if acc.get('email')
                ]
                self.logger.info(
                    f"Fetched {len(var.warmup_pool_accounts)} warmup pool accounts"
                )
            else:
                self.logger.error(
                    f"Failed to fetch warmup pool accounts: {resp.status_code}"
                )
        except Exception as e:
            self.logger.error(f"Error fetching warmup pool accounts: {e}")

    def update_checkbox_status(self):
        var.add_custom_hostname = GUI.checkBox_add_custom_hostname.isChecked()
        var.responses_webhook_enabled = GUI.checkBox_responses_webhook.isChecked()
        var.enable_webhook_status = GUI.checkBox_enable_webhook.isChecked()
        var.remove_email_from_target = GUI.checkBox_remove_email_from_target.isChecked()
        var.check_for_blocks = GUI.checkBox_check_for_blocks.isChecked()
        var.email_tracking_state = GUI.checkBox_email_tracking.isChecked()
        var.followup_enabled = GUI.checkBox_configuration_followup_enabled.isChecked()
        var.auto_fire_responses_webhook = (
            GUI.checkBox_auto_fire_responses_webhook.isChecked()
        )
        var.space_encoding_checkbox = GUI.checkBox_space_encoding.isChecked()
        var.inbox_whitelist_checkbox = bool(
            GUI.lineEdit_inbox_whitelist.text().strip())
        var.cc_emails_enabled = GUI.checkBox_enable_cc_emails.isChecked()

    def update_db_file_upload_config(self):
        var.db_file_loading_config["group_a"] = (
            GUI.checkBox_database_group_a.isChecked()
        )
        var.db_file_loading_config["group_b"] = (
            GUI.checkBox_database_group_b.isChecked()
        )
        var.db_file_loading_config["target"] = GUI.checkBox_database_target.isChecked(
        )

    def showContextMenu(self, pos):
        print("pos " + str(pos))
        index = GUI.tableView_database.indexAt(pos)
        menu = QtWidgets.QMenu()
        menu.addAction("Copy")
        menu.exec_(GUI.tableView_database.viewport().mapToGlobal(pos))

    def update_webhook_link(self, text):
        var.webhook_link = str(text)

    def start_inbox_stream_thread(self):
        Thread(target=start_inbox_stream, daemon=True).start()

    def configuration_save(self):
        Thread(target=update_config_json, daemon=True).start()

    def update_email_tracking_link(self):
        var.tracking["analytics_account"] = str(
            GUI.lineEdit_email_tracking_analytics_account.text()
        ).strip()
        pattern = re.compile("[^a-zA-Z0-9_ ]+")
        if not bool(
            pattern.search(
                str(GUI.lineEdit_email_tracking_campaign_name.text()).strip()
            )
        ):
            var.tracking["campaign_name"] = str(
                GUI.lineEdit_email_tracking_campaign_name.text()
            ).strip()
        else:
            GUI.lineEdit_email_tracking_campaign_name.setText(
                str(var.tracking["campaign_name"])
            )
        self.configuration_save()

    def update_email_tracking_php(self):
        var.tracking["domain_name"] = str(
            GUI.lineEdit_email_tracking_domain_name.text()
        ).strip()
        var.tracking["api_key"] = str(
            GUI.lineEdit_email_tracking_analytics_api_key.text()
        ).strip()
        self.configuration_save()

    def download_track_php(self):
        file_name = "./output_php/track-email-open.php"
        directory = os.path.dirname(file_name)
        if not os.path.exists(directory):
            os.makedirs(directory)
        if file_name:
            php_code = '<?php\n            // Enable error reporting to display errors in the browser (for local testing)\n            ini_set("display_errors", 1);\n            ini_set("display_startup_errors", 1);\n            error_reporting(E_ALL);          \n            // GA4 Measurement Protocol POST URL\n            $ga_url = "https://www.google-analytics.com/mp/collect";          \n            // GA4 Required Parameters\n            $measurement_id = {tracking_analytics_account};\n            $api_secret = {tracking_analytics_api_key};\n            // Generate a random client_id for testing purposes (could be replaced with something persistent)\n            $client_id = isset($_GET[\'client_id\']) ? $_GET[\'client_id\'] : uniqid(\'\', true);          \n            // Get the event_name from the query string or use a default value\n            $event_name = $_GET[\'event_name\'] ?? \'email_open\';          \n            // Data for the POST request (JSON)\n            $data = array(\n                "client_id" => $client_id,\n                "events" => array(\n                array(\n                        "name" => $event_name,\n                        "params" => array(\n                            "engagement_time_msec" => 1\n                        )\n                    )\n                )\n            );           \n            // Initialize cURL for POST request\n            $ch = curl_init();\n            curl_setopt($ch, CURLOPT_URL, $ga_url . "?measurement_id=" . $measurement_id . "&api_secret=" . $api_secret . "&debug_mode=1"); // Enable debug mode for testing\n            curl_setopt($ch, CURLOPT_POST, 1);\n            curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));\n            curl_setopt($ch, CURLOPT_HTTPHEADER, array(\'Content-Type: application/json\'));\n            curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);\n            // Execute the POST request\n            $response = curl_exec($ch);\n            // Check if the request was successful\n            if ($response === false) {\n            // Log cURL error if needed\n            error_log("cURL error: " . curl_error($ch));\n            echo "Error occurred while sending event.";\n            } else {\n            // Log response for testing/debugging\n            error_log("GA4 Response: " . $response);\n            echo "GA4 Response: " . htmlspecialchars($response);\n            }\n            // Close the cURL session\n            curl_close($ch);\n            // Output a 1x1 pixel transparent GIF image to simulate the tracking pixel\n            header("Content-Type: image/gif");\n            echo base64_decode("R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==");\n            ?>\n            '
            php_code = php_code.replace(
                "{tracking_analytics_account}", f"'{var.tracking['analytics_account']}'"
            )
            php_code = php_code.replace(
                "{tracking_analytics_api_key}", f"'{var.tracking['api_key']}'"
            )
            try:
                with open(file_name, "w") as file:
                    file.write(php_code)
                alert(
                    text=f"PHP code successfully written to:\n{file_name}",
                    title="Success",
                    button="OK",
                )
            except Exception as e:
                logger.info(f"Error saving file: {e}")

    def run_command(self):
        try:
            if not var.command_q.empty():
                command = var.command_q.get()
                eval(command)
        except Exception as e:
            self.logger.error("Error at run_command - {}".format(e))

    def load_unsubscribe_setting(self):
        try:
            self._loaded_unsubscribe_setting = get_setting()
            var.command_q.put("self.finish_load_unsubscribe_setting()")
        except Exception:
            var.command_q.put("self.fail_load_unsubscribe_setting()")

    def finish_load_unsubscribe_setting(self):
        self.unsubscribe_setting.apply_loaded_value(self._loaded_unsubscribe_setting)

    def fail_load_unsubscribe_setting(self):
        GUI.checkBox_insert_unsubscribe_link.setEnabled(False)
        alert(
            text="Unable to load unsubscribe setting. Retry by reopening Gmonster.",
            title="Unsubscribe setting",
            button="OK",
        )

    def begin_save_unsubscribe_setting(self, _state):
        requested = GUI.checkBox_insert_unsubscribe_link.isChecked()
        GUI.checkBox_insert_unsubscribe_link.setEnabled(False)
        Thread(target=self.save_unsubscribe_setting, args=(requested,), daemon=True).start()

    def save_unsubscribe_setting(self, requested):
        try:
            self._saved_unsubscribe_setting = self.unsubscribe_setting.persist_value(requested)
            var.command_q.put("self.finish_save_unsubscribe_setting()")
        except Exception:
            var.command_q.put("self.fail_save_unsubscribe_setting()")

    def finish_save_unsubscribe_setting(self):
        self.unsubscribe_setting.apply_loaded_value(self._saved_unsubscribe_setting)

    def fail_save_unsubscribe_setting(self):
        self.unsubscribe_setting.restore_current_value()
        alert(
            text="Unable to save unsubscribe setting. Your previous setting is still active.",
            title="Unsubscribe setting",
            button="OK",
        )

    def load_unsubscribe_records(self):
        self.unsubscribe_page.set_loading()
        Thread(target=self._load_unsubscribe_records, daemon=True).start()

    def _load_unsubscribe_records(self):
        try:
            self._loaded_unsubscribe_records = get_records()
            var.command_q.put("self.finish_load_unsubscribe_records()")
        except Exception:
            var.command_q.put("self.fail_load_unsubscribe_records()")

    def finish_load_unsubscribe_records(self):
        self.unsubscribe_page.set_records(self._loaded_unsubscribe_records)

    def fail_load_unsubscribe_records(self):
        self.unsubscribe_page.set_error("Unable to load unsubscribes. Please retry.")

    def add_manual_unsubscribe(self, email):
        self.unsubscribe_page.set_loading()
        Thread(target=self._add_manual_unsubscribe, args=(email,), daemon=True).start()

    def _add_manual_unsubscribe(self, email):
        try:
            add_manual(email)
            var.command_q.put("self.load_unsubscribe_records()")
        except Exception:
            var.command_q.put("self.fail_manual_unsubscribe()")

    def fail_manual_unsubscribe(self):
        self.unsubscribe_page.set_error("Unable to add unsubscribe. Check the email and retry.")

    def export_unsubscribe_records(self):
        path, _ = QFileDialog.getSaveFileName(
            None,
            "Export unsubscribes",
            default_export_path(self._downloads_folder()),
            "CSV files (*.csv)",
        )
        if not path:
            return
        try:
            count = export_records(path, self.unsubscribe_page.filtered_records)
            alert(text="Exported {} unsubscribe record(s).".format(count), title="Export complete", button="OK")
        except Exception:
            alert(text="Unable to export unsubscribes.", title="Export failed", button="OK")

    def insert_row(self):
        GUI.model.insertRows()
        self.update_target_count()

    # def remove_row(self):
    #     rows = GUI.tableView_database.selectedIndexes()
    #     rows = list(set([item.row() for item in rows]))
    #     if len(rows) == 1:
    #         GUI.model.removeRows(rows[0])
    #         # Enqueue refresh to main thread so behavior matches multi-row delete
    #         try:
    #             var.command_q.put("self.update_db_table()")
    #         except Exception:
    #                 pass
    #     else:
    #         if len(rows) > 1:
    #             ids = (
    #                 GUI.model._data[GUI.model._data.index.isin(rows)]
    #                 .iloc[:, 0]
    #                 .to_list()
    #             )
    #             Thread(target=database.db_remove_rows, daemon=True, args=(ids,)).start()
    #             var.command_q.put(f"GUI.model._data.drop({rows}, inplace=True)")
    #             var.command_q.put(
    #                 "GUI.model._data.reset_index(drop=True, inplace=True)"
    #             )
    #             var.command_q.put("self.update_db_table()")
    #         else:
    #             self.logger.warning("Select something")
    #     GUI.tableView_database.clearSelection()

    def remove_row(self):
        rows = GUI.tableView_database.selectedIndexes()
        rows = list(set([item.row() for item in rows]))
        if len(rows) == 1:
            GUI.model.removeRows(rows[0])
        else:
            if len(rows) > 1:
                index_labels = GUI.model._data.index[rows].tolist()
                ids = GUI.model._data.iloc[rows, 0].to_list()
                GUI.model.layoutAboutToBeChanged.emit()
                GUI.model._data.drop(index_labels, inplace=True)
                GUI.model._data.reset_index(drop=True, inplace=True)
                GUI.model.layoutChanged.emit()
                Thread(target=database.db_remove_rows,
                       daemon=True, args=(ids,)).start()
            else:
                self.logger.warning("Select something")
        GUI.tableView_database.clearSelection()
        self.update_target_count()

    def select_rows_by_status(self):
        """Select all rows in the table that match the checked status filters"""
        try:
            # Check if STATUS column exists in the data
            if "STATUS" not in GUI.model._data.columns:
                return

            # Get the checked statuses
            selected_statuses = []
            if GUI.checkBox_safe.isChecked():
                selected_statuses.append("safe")
            if GUI.checkBox_risky.isChecked():
                selected_statuses.append("risky")
            if GUI.checkBox_unknown.isChecked():
                selected_statuses.append("unknown")
            if GUI.checkBox_not_checked.isChecked():
                selected_statuses.append("not checked")

            # Clear existing selection
            GUI.tableView_database.clearSelection()

            # If no checkboxes are checked, return
            if not selected_statuses:
                return

            # Get selection model
            selection_model = GUI.tableView_database.selectionModel()

            # Select rows matching the selected statuses
            for row_index in range(GUI.model.rowCount(None)):
                status_value = str(
                    GUI.model._data.iloc[row_index]["STATUS"]).lower()

                # Check if this row's status matches any selected status
                if status_value in selected_statuses:
                    # Select the entire row - get the model index for the row
                    index = GUI.model.index(row_index, 0)
                    # Use Select | Rows flags to select entire row and keep previous selections
                    selection_model.select(
                        index,
                        QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows
                    )

        except Exception as e:
            self.logger.error(f"Error at select_rows_by_status - {e}")

    def update_db_table(self):
        GUI.model.layoutAboutToBeChanged.emit()
        if GUI.radioButton_db_groupa.isChecked():
            GUI.model._data = var.group_a
        else:
            if GUI.radioButton_db_groupb.isChecked():
                GUI.model._data = var.group_b
            else:
                GUI.model._data = var.target
        GUI.model.layoutChanged.emit()
        self.update_target_count()

    def update_limit_of_thread(self):
        try:
            var.limit_of_thread = int(GUI.lineEdit_number_of_threads.text())
        except Exception as e:
            GUI.lineEdit_number_of_threads.setText(str(var.limit_of_thread))
            alert(text="Must be a number", title="Alert", button="OK")

    def update_target_count(self):
        if GUI.radioButton_db_target.isChecked():
            count = 0
            try:
                count = len(
                    GUI.model._data) if GUI.model._data is not None else 0
            except Exception:
                count = 0
            GUI.label_target_count.setText(f"Targets: {count}")
            GUI.label_target_count.show()
            GUI.pushButton_export_targets.show()
        else:
            GUI.label_target_count.hide()
            GUI.pushButton_export_targets.hide()

    def export_targets(self):
        if not GUI.radioButton_db_target.isChecked():
            return
        data = GUI.model._data
        if data is None or data.empty:
            alert(text="No targets to export.", title="Export", button="OK")
            return
        default_name = f"targets-{datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            mainWindow, "Export Targets", default_name, "Excel Files (*.xlsx)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".xlsx"):
            file_path += ".xlsx"
        try:
            data.to_excel(file_path, index=False)
            alert(
                text=f"Exported {len(data)} targets to:\n{file_path}",
                title="Export complete",
                button="OK",
            )
        except Exception as e:
            logger.error(f"Export targets failed: {e}")
            alert(text=f"Export failed: {e}", title="Error", button="OK")

    def check_for_subscription(self):
        global quit_application
        while True:
            try:
                url = var.api + "verify/check_for_subscription/{}".format(
                    var.login_email
                )
                response = requests.post(url, timeout=var.API_TIMEOUT)
                print(response, url)
                data = response.json()
                print(data)
                if response.status_code == 200:
                    if data["status"] == 2:
                        self.try_failed = 0
                        date = str(data["end_date"])
                        quit_application = True
                        var.command_q.put("mainWindow.close()")
                        alert(
                            text="Subscription Expired at {}.\nSoftware will exit soon.".format(
                                date
                            ),
                            title="Alert",
                            button="OK",
                        )
                    else:
                        if data["status"] == 3:
                            self.try_failed = 0
                            self.logger.info("sub deactivated")
                            quit_application = True
                            var.command_q.put("mainWindow.close()")
                            alert(
                                text="Subscription deativated.\nSoftware will exit soon.",
                                title="Alert",
                                button="OK",
                            )
                        else:
                            if data["status"] == 1:
                                self.try_failed = 0
                                self.logger.info(data["days_left"])
                            else:
                                self.try_failed = 0
                                quit_application = True
                                var.command_q.put("mainWindow.close()")
                                alert(
                                    text="Account not found", title="Alert", button="OK"
                                )
                else:
                    quit_application = True
                    var.command_q.put("mainWindow.close()")
                    alert(
                        text="Error on server.\nContact Admin.",
                        title="Alert",
                        button="OK",
                    )
            except Exception as e:
                self.try_failed += 1
                self.logger.error(
                    "error at check_for_subscription: {}".format(
                        traceback.format_exc())
                )
                if self.try_failed > 3:
                    quit_application = True
                    var.command_q.put("mainWindow.close()")
                    alert(
                        text="Check your internet connection.",
                        title="Alert",
                        button="OK",
                    )
            sleep(self.time_interval_sub_check)

    def refresh_account_info(self):
        """Fetch subscription info from API and populate the Account page labels."""
        GUI.label_account_email_val.setText(var.login_email or "—")
        try:
            url = var.api + \
                "verify/check_for_subscription/{}".format(var.login_email)
            response = requests.post(url, timeout=var.API_TIMEOUT)
            data = response.json()
            if response.status_code == 200:
                status_code = data.get("status")
                if status_code == 1:
                    GUI.label_account_status_val.setText("Active")
                    GUI.label_account_status_val.setStyleSheet(
                        "color: #2e7d32; font-weight: bold;")
                    GUI.label_account_days_left_val.setText(
                        str(data.get("days_left", "—")))
                    GUI.label_account_acc_limit_val.setText(
                        str(data.get("accounts_limit", "—")))
                    limit = data.get("email_verification_limit", 0)
                    used = data.get("email_verifications_used", 0)
                    remaining = data.get("email_verifications_remaining", 0)
                    reset_date = data.get("email_verification_reset_date", "—")
                    GUI.label_account_verif_limit_val.setText(str(limit))
                    GUI.label_account_verif_used_val.setText(str(used))
                    GUI.label_account_verif_remaining_val.setText(
                        str(remaining))
                    GUI.label_account_verif_reset_val.setText(str(reset_date))
                    # Update progress bar
                    if limit and limit > 0:
                        pct = int((used / limit) * 100)
                        GUI.progressBar_account_verif.setValue(pct)
                        GUI.progressBar_account_verif.setFormat(
                            f"{used} / {limit}")
                    else:
                        GUI.progressBar_account_verif.setValue(0)
                        GUI.progressBar_account_verif.setFormat("N/A")
                elif status_code == 2:
                    GUI.label_account_status_val.setText("Expired")
                    GUI.label_account_status_val.setStyleSheet(
                        "color: #c62828; font-weight: bold;")
                    end_date = data.get("end_date", "—")
                    GUI.label_account_days_left_val.setText(
                        f"Expired on {end_date}")
                    for lbl in [GUI.label_account_acc_limit_val, GUI.label_account_verif_limit_val,
                                GUI.label_account_verif_used_val, GUI.label_account_verif_remaining_val,
                                GUI.label_account_verif_reset_val]:
                        lbl.setText("—")
                    GUI.progressBar_account_verif.setValue(0)
                elif status_code == 3:
                    GUI.label_account_status_val.setText("Deactivated")
                    GUI.label_account_status_val.setStyleSheet(
                        "color: #e65100; font-weight: bold;")
                    end_date = data.get("end_date", "—")
                    GUI.label_account_days_left_val.setText(
                        f"Deactivated (end: {end_date})")
                    for lbl in [GUI.label_account_acc_limit_val, GUI.label_account_verif_limit_val,
                                GUI.label_account_verif_used_val, GUI.label_account_verif_remaining_val,
                                GUI.label_account_verif_reset_val]:
                        lbl.setText("—")
                    GUI.progressBar_account_verif.setValue(0)
                else:
                    GUI.label_account_status_val.setText("Unknown")
                    GUI.label_account_status_val.setStyleSheet("color: #888;")
            else:
                GUI.label_account_status_val.setText("Error")
                GUI.label_account_status_val.setStyleSheet("color: #c62828;")
                logger.error(
                    f"Account info fetch failed: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            GUI.label_account_status_val.setText("Connection error")
            GUI.label_account_status_val.setStyleSheet("color: #c62828;")
            logger.error(
                f"Error fetching account info: {traceback.format_exc()}")

    def request_subscription_cancel(self):
        dialog = CancelSubscriptionDialog(
            parent=mainWindow,
            email=(var.login_email or "").strip(),
            user_id=getattr(var, "gmonster_desktop_id", ""),
            plan="",
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        request_values = dialog.values()

        GUI.pushButton_account_cancel_subscription.setEnabled(False)
        GUI.pushButton_account_cancel_subscription.setText("Sending...")
        Thread(
            target=self._send_subscription_cancel_request,
            args=(request_values,),
            daemon=True,
        ).start()

    def _send_subscription_cancel_request(self, request_values):
        try:
            payload = build_cancel_request_payload(
                name=request_values["name"],
                email=request_values["email"],
                user_id=request_values["user_id"],
                plan=request_values["plan"],
            )
            response = requests.post(
                build_cancel_request_url(var.api),
                json=payload,
                timeout=var.API_TIMEOUT,
            )

            if response.status_code == 200:
                message = "Cancellation request sent successfully"
                try:
                    data = response.json()
                    message = data.get("message") or message
                except Exception:
                    pass
                self._subscription_cancel_result = (True, message)
            else:
                self._subscription_cancel_result = (
                    False,
                    "Unable to send cancellation request. Please try again or contact support.",
                )
                logger.error(
                    f"Subscription cancellation failed: HTTP {response.status_code} - {response.text}"
                )
        except Exception:
            self._subscription_cancel_result = (
                False,
                "Unable to send cancellation request. Please try again or contact support.",
            )
            logger.error(
                f"Error sending subscription cancellation request: {traceback.format_exc()}"
            )
        var.command_q.put("self._finish_subscription_cancel_request()")

    def _finish_subscription_cancel_request(self):
        success, message = getattr(
            self,
            "_subscription_cancel_result",
            (False, "Cancellation request failed."),
        )
        GUI.pushButton_account_cancel_subscription.setEnabled(True)
        GUI.pushButton_account_cancel_subscription.setText(
            "Cancel Subscription")
        alert(
            text=message,
            title="Cancel Subscription" if success else "Error",
            button="OK",
        )

    def test_send(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Send(dialog, parent="test")
        dialog.exec_()

    def forward(self):
        dialog = QtWidgets.QDialog()
        dialog.ui = Send(dialog, parent="forward")
        dialog.exec_()

    def batch_delete(self):
        try:
            inbox_df = None
            try:
                inbox_df = var.inbox_data[var.inbox_group]
            except Exception:
                inbox_df = None
            selected_count = 0
            if inbox_df is not None and not inbox_df.empty and "checkbox_status" in inbox_df.columns:
                try:
                    selected_count = int(inbox_df["checkbox_status"].sum())
                except Exception:
                    selected_count = 0
            if selected_count > 0 or GUI.checkBox_delete_all.isChecked():
                result = confirm(
                    text="Are you sure?",
                    title="Confirmation Window",
                    buttons=["OK", "Cancel"],
                )
                if result == "OK":
                    if GUI.checkBox_delete_all.isChecked():
                        result = confirm(
                            text="You are going to delete all?",
                            title="Confirmation Window",
                            buttons=["Yes", "No"],
                        )
                        if result == "Yes":
                            var.inbox_data[var.inbox_group]["checkbox_status"] = 1
                        else:
                            return
                    var.thread_open = 0
                    dialog = QtWidgets.QDialog()
                    dialog.ui = DeleteEmail(dialog)
                    dialog.exec_()
                    self.sort_inbox_data(self.option)
                else:
                    print("Cancelled")
            else:
                alert(
                    text="You have to make selection first!!!",
                    title="Alert",
                    button="OK",
                )
            unread_count = sum(
                (1 for flag in var.inbox_data[var.inbox_group]
                 ["flag"] if flag == "UNSEEN")
            )
            if unread_count > 0:
                GUI.label_unread_count.setText(str(unread_count))
            else:
                GUI.label_unread_count.setText("")
        except Exception as e:
            self.logger.error("Error at batch_delete - {}".format(e))

    def load_db(self):
        plan_limit = database._fetch_accounts_limit()
        sheet_counts = database.get_sheet_counts()
        group_a_enabled = var.db_file_loading_config.get("group_a", True)
        group_b_enabled = var.db_file_loading_config.get("group_b", True)
        dlg = ImportSlotsDialog(plan_limit, sheet_counts,
                                group_a_enabled, group_b_enabled, parent=None)
        if dlg.exec_() == QDialog.Accepted:
            a_slots, b_slots = dlg.slots()
            Thread(target=database.load_db, args=(
                a_slots, b_slots), daemon=True).start()
        else:
            print("cancelled")

    def open_sheets_folder(self):
        try:
            open_runtime_sheets_folder(
                var.DATA_DIR,
                lambda sheets_dir: QtGui.QDesktopServices.openUrl(
                    QtCore.QUrl.fromLocalFile(str(sheets_dir))
                ),
            )
        except OSError as error:
            self.logger.error("Could not open sheets folder: %s", error)
            alert(
                text="Could not open the sheets folder.",
                title="Sheets folder",
                button="OK",
            )

    def change_subject(self):
        try:
            subject = str(var.email_in_view.get("subject", "")).strip()
            raw_is_sent = var.email_in_view.get("is_sent", None)
            if isinstance(raw_is_sent, str):
                is_sent = raw_is_sent.strip().lower() in {
                    "1",
                    "true",
                    "yes",
                    "y",
                    "sent",
                }
            elif raw_is_sent is None:
                is_sent = GUI.radioButton_email_sent.isChecked()
            else:
                is_sent = bool(raw_is_sent)
            # if not is_sent and subject and not subject.lower().startswith("re:"):
            #     subject = "RE: {}".format(subject)
            GUI.textBrowser_subject.setPlainText(subject)
        except Exception as e:
            print("Error while setting subject : {}".format(e))

    def proxy_provider(self):
        webbrowser.open_new(var.proxy_provider)

    def clear_files(self):
        var.files = []

    def openFileNamesDialog(self):
        options = QFileDialog.Options()
        files, _ = QFileDialog.getOpenFileNames(
            None, "Attach files", "", "All Files (*)", options=options
        )
        if files:
            var.files.extend(files)
            for file_path in files:
                file_widget = FileWidget(
                    file_path,
                    True,
                    GUI.scrollAreaWidgetContents_attachments_campaign.layout(),
                )
                GUI.scrollAreaWidgetContents_attachments_campaign.layout().addWidget(
                    file_widget
                )

    def openFileNamesDialog_reply(self):
        options = QFileDialog.Options()
        files, _ = QFileDialog.getOpenFileNames(
            None, "Attach files", "", "All Files (*)", options=options
        )
        if files:
            var.reply_files.extend(files)
            for file_path in files:
                file_widget = FileWidget(
                    file_path,
                    False,
                    GUI.scrollAreaWidgetContents_attachments_reply.layout(),
                )
                GUI.scrollAreaWidgetContents_attachments_reply.layout().addWidget(
                    file_widget
                )

    def compose_zoomInOut(self, source):
        if source == "zoomIn":
            GUI.textBrowser_compose.selectAll()
            self.compose_font_size += 1
            GUI.textBrowser_compose.setFontPointSize(self.compose_font_size)
        else:
            if self.compose_font_size > 2:
                GUI.textBrowser_compose.selectAll()
                self.compose_font_size -= 1
                GUI.textBrowser_compose.setFontPointSize(
                    self.compose_font_size)

    def inbox_zoomInOut(self, source):
        if source == "zoomIn":
            if self.inbox_zoom_level < 8:
                self.inbox_zoom_level += 1
        else:
            if self.inbox_zoom_level > -6:
                self.inbox_zoom_level -= 1
        self.refresh_inbox_email_view()

    def refresh_inbox_email_view(self):
        if not isinstance(var.email_in_view, dict) or not var.email_in_view:
            return
        selected_row_data = dict(var.email_in_view)
        thread_df = self._get_conversation_thread(selected_row_data)
        GUI.textBrowser_show_email.setHtml(
            self._build_thread_view_html(thread_df))

    def compose_update(self):
        if not GUI.checkBox_compose_preview.isChecked():
            if GUI.radioButton_html.isChecked():
                var.compose_email_body_html = GUI.textBrowser_compose.toPlainText()
            else:
                var.compose_email_body = GUI.textBrowser_compose.toPlainText()

    def update_rely_text(self):
        var.reply_body = GUI.textEdit_reply.toPlainText()

    def compose_preview(self):
        if GUI.checkBox_compose_preview.isChecked():
            if GUI.radioButton_html.isChecked():
                GUI.textBrowser_compose.setHtml(var.compose_email_body_html)
                GUI.textBrowser_compose.setReadOnly(True)
            else:
                GUI.textBrowser_compose.setReadOnly(False)
                GUI.checkBox_compose_preview.setCheckState(False)
        else:
            if GUI.radioButton_html.isChecked():
                GUI.textBrowser_compose.setPlainText(
                    var.compose_email_body_html)
                GUI.textBrowser_compose.setReadOnly(False)
            else:
                GUI.textBrowser_compose.setPlainText(var.compose_email_body)
                GUI.textBrowser_compose.setReadOnly(False)

    def compose_change(self):
        if GUI.radioButton_html.isChecked():
            GUI.textBrowser_compose.setReadOnly(False)
            GUI.checkBox_compose_preview.setCheckState(False)
            GUI.textBrowser_compose.setPlainText(var.compose_email_body_html)
            var.body_type = "Html"
        else:
            GUI.textBrowser_compose.setReadOnly(False)
            GUI.checkBox_compose_preview.setCheckState(False)
            GUI.textBrowser_compose.setPlainText(var.compose_email_body)
            var.body_type = "Normal"

    def send_button_visibility(self, on=None):
        if on:
            GUI.pushButton_send.setEnabled(True)
        else:
            GUI.pushButton_send.setEnabled(False)

    def compose_config_visibility(self, on=None):
        if on:
            GUI.lineEdit_number_of_threads.setEnabled(True)
            GUI.lineEdit_num_per_address.setEnabled(True)
            GUI.radioButton_plain_text.setEnabled(True)
            GUI.radioButton_html.setEnabled(True)
            GUI.checkBox_email_tracking.setEnabled(True)
            GUI.checkBox_enable_webhook.setEnabled(True)
            GUI.checkBox_remove_email_from_target.setEnabled(True)
            GUI.checkBox_check_for_blocks.setEnabled(True)
            GUI.lineEdit_webhook_link.setEnabled(True)
            GUI.lineEdit_email_tracking_campaign_name.setEnabled(True)
            GUI.lineEdit_email_tracking_analytics_account.setEnabled(True)
            GUI.lineEdit_email_tracking_domain_name.setEnabled(True)
            GUI.lineEdit_email_tracking_analytics_api_key.setEnabled(True)
            GUI.lineEdit_delay_between_emails.setEnabled(True)
            GUI.tab_database.setEnabled(True)
            GUI.checkBox_add_custom_hostname.setEnabled(True)
        else:
            GUI.lineEdit_number_of_threads.setEnabled(False)
            GUI.lineEdit_num_per_address.setEnabled(False)
            GUI.radioButton_plain_text.setEnabled(False)
            GUI.radioButton_html.setEnabled(False)
            GUI.checkBox_email_tracking.setEnabled(False)
            GUI.checkBox_enable_webhook.setEnabled(False)
            GUI.checkBox_remove_email_from_target.setEnabled(False)
            GUI.checkBox_check_for_blocks.setEnabled(False)
            GUI.lineEdit_webhook_link.setEnabled(False)
            GUI.lineEdit_email_tracking_campaign_name.setEnabled(False)
            GUI.lineEdit_email_tracking_analytics_account.setEnabled(False)
            GUI.lineEdit_email_tracking_domain_name.setEnabled(False)
            GUI.lineEdit_email_tracking_analytics_api_key.setEnabled(False)
            GUI.lineEdit_delay_between_emails.setEnabled(False)
            GUI.tab_database.setEnabled(False)
            GUI.checkBox_add_custom_hostname.setEnabled(False)

    def send_reply(self):
        result = confirm(
            text="Are you sure?", title="Confirmation Window", buttons=["OK", "Cancel"]
        )
        if result == "OK":
            self.reply()
        else:
            self.logger.info("cancelled")

    def send_camp(self):
        GUI.pushButton_send.setEnabled(False)
        if var.send_campaign_run_status:
            result = confirm(
                text="Are you sure you want to stop the campaign?",
                title="Stop Campaign",
                buttons=["OK", "Cancel"]
            )
            if result == "OK":
                self.logger.info("Stopping campaign...")
                if var.send_campaign_run_status:
                    GUI.pushButton_send.setText("Stopping...")
                    GUI.lable_campaign_status_text.setText("Stopping")
                    var.stop_send_campaign = True
                else:
                    self.logger.info("Campaign is not running")
                    self.send_button_visibility(on=True)
            else:
                self.logger.info("Cancel stop cancelled")
                self.send_button_visibility(on=True)
        else:
            result = confirm(
                text="Are you sure?", title="Confirmation Window", buttons=["OK", "Cancel"]
            )
            if result == "OK":
                var.stop_send_campaign = False
                var.thread_open_campaign = 0
                var.send_campaign_email_count = 0
                self.logger.info("send_campaign")
                self.send_campaign()
            else:
                self.send_button_visibility(on=True)
                self.logger.info("cancelled")

    def update_compose_progressbar(self):
        try:
            value, count_label, status = campaign_progress_state(
                var.send_campaign_email_count,
                var.total_email_to_be_sent,
                var.stop_send_campaign,
            )
            GUI.label_campaign_status.setText(count_label)
            GUI.lable_campaign_status_text.setText(status)
            GUI.progressBar_compose.setValue(value)
        except Exception as e:
            logger.error(
                "Error at main.py->update_compose_progressbar : {}".format(e))

    def send_campaign(self):
        try:
            GUI.lable_campaign_status_text.show()
            GUI.label_campaign_status.show()
            GUI.progressBar_compose.show()
            var.send_campaign_run_status = True
            GUI.pushButton_send.setText("Stop \nCampaign")
            GUI.pushButton_send.setEnabled(True)
            var.num_emails_per_address = str(
                GUI.lineEdit_num_per_address.text())
            num_emails_per_address_range = {
                "start": int(var.num_emails_per_address.split("-")[0].strip()),
                "end": int(var.num_emails_per_address.split("-")[1].strip()),
            }
            var.delay_between_emails = GUI.lineEdit_delay_between_emails.text()
            delay_start = int(var.delay_between_emails.split("-")[0].strip())
            delay_end = int(var.delay_between_emails.split("-")[1].strip())
            Thread(target=update_config_json, daemon=True).start()
            var.compose_email_subject = GUI.lineEdit_subject.text()
            if GUI.radioButton_campaign_group_a.isChecked():
                if len(var.group_a) > 0 and len(var.target) > 0:
                    Thread(
                        target=smtp.main,
                        daemon=True,
                        args=[
                            var.group_a.copy(),
                            delay_start,
                            delay_end,
                            "Group A",
                            num_emails_per_address_range,
                        ],
                    ).start()
                    self.logger.info("send_campaign Group a starting thread")
                else:
                    self.logger.error("At send_campaign - Empty Target table")
                    self.send_button_visibility(on=True)
                    var.send_campaign_run_status = False
            else:
                self.logger.info("Group b")
                if len(var.group_b) > 0 and len(var.target) > 0:
                    Thread(
                        target=smtp.main,
                        daemon=True,
                        args=[
                            var.group_b.copy(),
                            delay_start,
                            delay_end,
                            "Group B",
                            num_emails_per_address_range,
                        ],
                    ).start()
                    self.logger.info("send_campaign Group b starting thread")
                else:
                    self.logger.error("At send_campaign - Empty Target table")
                    self.send_button_visibility(on=True)
                    var.send_campaign_run_status = False
        except Exception as e:
            self.logger.error(
                "Error at send_campaign - {}".format(traceback.format_exc())
            )
            alert(
                text="Error at send_campaign : {}".format(e), title="Error", button="OK"
            )
            var.send_campaign_run_status = False

    def reply(self):
        self.change_subject()
        var.email_in_view["subject"] = GUI.textBrowser_subject.toPlainText()
        var.email_in_view["body"] = var.reply_body
        dialog = QtWidgets.QDialog()
        dialog.ui = Reply(dialog)
        dialog.exec_()
        self.send_button_visibility(on=True)

    def downloading_email(self):
        try:
            result = confirm(
                text="Are you sure?",
                title="Confirmation Window",
                buttons=["OK", "Cancel"],
            )
            if result == "OK":
                with var.email_q.mutex:
                    var.email_q.queue.clear()
                if var.download_email_status:
                    alert(
                        text="Emails was downloaded by the auto Reply. Please try again few minutes later.",
                        title="Warning",
                        button="OK",
                    )
                    return
                var.total_email = 0
                var.thread_open = 0
                var.acc_finished = 0
                var.stop_download = False
                var.inbox_data_table[var.inbox_group] = pd.DataFrame()
                var.row_pos = 0
                GUI.tableWidget_inbox.setRowCount(0)
                dialog = QtWidgets.QDialog()
                if GUI.radioButton_group_a.isChecked() and len(var.group_a) > 0:
                    self.logger.info("Downloading_email Group a")
                    var.total_acc = len(var.group_a)
                    var.download_email_status = True
                    Thread(target=update_config_json, daemon=True).start()
                    dialog.ui = Download(
                        dialog, var.group_a, folders=[
                            "INBOX", "__SENT__"]
                    )
                else:
                    if GUI.radioButton_group_b.isChecked() and len(var.group_b) > 0:
                        self.logger.info("Downloading_email Group b")
                        var.total_acc = len(var.group_b)
                        var.download_email_status = True
                        Thread(target=update_config_json, daemon=True).start()
                        dialog.ui = Download(
                            dialog,
                            var.group_b,
                            folders=["INBOX", "__SENT__"],
                        )
                    else:
                        self.logger.info("Downloading_email no db")
                        alert(
                            text="No database loaded yet!!!", title="Error", button="OK"
                        )
                dialog.exec_()
                var.download_email_status = False
                self.add_to_table()
            else:
                self.logger.info("Cancelled")
        except Exception as e:
            var.download_email_status = False
            self.logger.error("Error at downloading_email - {}".format(e))

    def email_cancel(self):
        result = confirm(
            text="Are you sure?", title="Confirmation Window", buttons=["OK", "Cancel"]
        )
        if result == "OK":
            self.logger.info("email_cancel Download Cancel")
            var.stop_download = True
        else:
            self.logger.info("email_cancel denied")

    def add_to_table(self):
        try:
            while not var.email_q.empty():
                row_data = var.email_q.get()
                row_data["checkbox_status"] = 0
                var.inbox_data_table[var.inbox_group] = pd.concat(
                    [var.inbox_data_table[var.inbox_group], pd.DataFrame([row_data])], ignore_index=True
                )
            self.inbox_show_changed()
            unread_count = 0
            if (
                not var.inbox_data[var.inbox_group].empty
                and "flag" in var.inbox_data[var.inbox_group].columns
            ):
                unread_count = sum(
                    1
                    for flag in var.inbox_data[var.inbox_group]["flag"]
                    if flag == "UNSEEN"
                )
            if unread_count > 0:
                GUI.label_unread_count.setText(str(unread_count))
            else:
                GUI.label_unread_count.setText("")
        except Exception as e:
            self.logger.error("Error at add_to_table - {}".format(e))

    def inbox_show_changed(self):
        # First, get the base data based on sent/received filter
        if not var.inbox_data_table[var.inbox_group].empty:
            if GUI.radioButton_email_all.isChecked():
                base_data = var.inbox_data_table[var.inbox_group][
                    var.inbox_data_table[var.inbox_group]["is_sent"] == False
                ].copy()
            elif GUI.radioButton_email_sent.isChecked():
                base_data = var.inbox_data_table[var.inbox_group][
                    var.inbox_data_table[var.inbox_group]["is_sent"] == True
                ].copy()
            elif GUI.radioButton_email_positive.isChecked():
                temp_inbox = var.inbox_data_table[var.inbox_group][
                    var.inbox_data_table[var.inbox_group]["is_sent"] == False
                ].copy()
                base_data = temp_inbox[
                    temp_inbox.apply(
                        lambda row: self.get_sentiment_textblob(
                            row["body"], row["to_mail"]
                        ),
                        axis=1,
                    )
                ].copy()
            elif GUI.radioButton_email_negative.isChecked():
                temp_inbox = var.inbox_data_table[var.inbox_group][
                    var.inbox_data_table[var.inbox_group]["is_sent"] == False
                ].copy()
                base_data = temp_inbox[
                    temp_inbox.apply(
                        lambda row: not self.get_sentiment_textblob(
                            row["body"], row["to_mail"]
                        ),
                        axis=1,
                    )
                ].copy()
            else:
                base_data = var.inbox_data_table[var.inbox_group].copy()
            var.inbox_data[var.inbox_group] = base_data
        else:
            var.inbox_data[var.inbox_group] = pd.DataFrame()

        # Filter out warmup pool emails if the setting is enabled
        if var.hide_warmup_emails and var.warmup_pool_accounts and not var.inbox_data[var.inbox_group].empty:
            pool_set = set(var.warmup_pool_accounts)
            var.inbox_data[var.inbox_group] = var.inbox_data[var.inbox_group][
                ~var.inbox_data[var.inbox_group]['from_mail'].str.lower().isin(
                    pool_set)
            ].copy()

        search_text = self.get_inbox_search_text()
        if search_text and not var.inbox_data[var.inbox_group].empty:
            var.inbox_data[var.inbox_group] = filter_inbox_emails(
                var.inbox_data[var.inbox_group],
                search_text,
            )

        self.sort_inbox_data(self.option)

    def display_email_in_table(self):
        try:
            inbox_data = var.inbox_data[var.inbox_group]
            row_count = len(inbox_data)

            # Set row count once instead of incrementally
            GUI.tableWidget_inbox.setRowCount(row_count)

            # Pre-create reusable objects
            mail_read_icon = QtGui.QIcon(var.mail_read_icon)
            mail_unread_icon = QtGui.QIcon(var.mail_unread_icon)
            checkbox_style = "text-align: center; margin-left:15%; margin-right:10%;"

            # Batch processing with enumerate for cleaner iteration
            for row_pos, (_, row_data) in enumerate(inbox_data.iterrows()):
                # Set text items efficiently
                GUI.tableWidget_inbox.setItem(
                    row_pos, 2, QTableWidgetItem(row_data.get("from_name", "")))
                GUI.tableWidget_inbox.setItem(
                    row_pos, 3, QTableWidgetItem(row_data.get("subject", "")))
                # Safely format the date even if missing or not a datetime
                date_val = row_data.get("date", "")
                try:
                    date_text = date_val.strftime(
                        "%d/%b") if hasattr(date_val, "strftime") else str(date_val)
                except Exception:
                    date_text = ""
                GUI.tableWidget_inbox.setItem(
                    row_pos, 4, QTableWidgetItem(date_text))

                # Create and configure button
                button_show_mail = QtWidgets.QPushButton("")
                button_show_mail.setStyleSheet(var.button_style)
                button_show_mail.clicked.connect(self.email_show)
                button_show_mail.setIcon(
                    mail_unread_icon if row_data["flag"] == "UNSEEN" else mail_read_icon)
                GUI.tableWidget_inbox.setCellWidget(
                    row_pos, 1, button_show_mail)

                # Create and configure checkbox
                checkbox_inbox = QtWidgets.QCheckBox(
                    parent=GUI.tableWidget_inbox)
                checkbox_inbox.setStyleSheet(checkbox_style)
                checkbox_inbox.stateChanged.connect(self.clickBox)
                GUI.tableWidget_inbox.setCellWidget(row_pos, 0, checkbox_inbox)

            # Resize columns once after all data is populated
            for col in range(6):
                GUI.tableWidget_inbox.resizeColumnToContents(col)

        except Exception as e:
            self.logger.error(f"Error at display_email_in_table - {e}")

    def clickBox(self, state):
        checkbox = GUI.sender()
        index = GUI.tableWidget_inbox.indexAt(checkbox.pos())
        print(index.row())
        if index.isValid():
            row = index.row()
            if state == QtCore.Qt.Checked:
                print("Checked")
                var.inbox_data[var.inbox_group].loc[row, "checkbox_status"] = 1
                matching_row = None
                if (
                    not var.inbox_data_table[var.inbox_group].empty
                    and "uid" in var.inbox_data_table[var.inbox_group].columns
                    and "uid" in var.inbox_data[var.inbox_group].columns
                ):
                    match = var.inbox_data_table[var.inbox_group][
                        var.inbox_data_table[var.inbox_group]["uid"]
                        == var.inbox_data[var.inbox_group].iloc[row]["uid"]
                    ]
                    if not match.empty:
                        matching_row = match.index[0]
                if matching_row is None:
                    match = var.inbox_data_table[var.inbox_group][
                        (var.inbox_data_table[var.inbox_group]["from"] ==
                         var.inbox_data[var.inbox_group].iloc[row]["from"])
                        & (
                            var.inbox_data_table[var.inbox_group]["subject"]
                            == var.inbox_data[var.inbox_group].iloc[row]["subject"]
                        )
                        & (var.inbox_data_table[var.inbox_group]["date"] == var.inbox_data[var.inbox_group].iloc[row]["date"])
                    ]
                    if not match.empty:
                        matching_row = match.index[0]
                if matching_row is not None:
                    var.inbox_data_table[var.inbox_group].loc[matching_row,
                                                              "checkbox_status"] = 1
                print(var.inbox_data[var.inbox_group].iloc[row]["subject"])
            else:
                print("Unchecked")
                var.inbox_data[var.inbox_group].loc[row, "checkbox_status"] = 0
                matching_row = None
                if (
                    not var.inbox_data_table[var.inbox_group].empty
                    and "uid" in var.inbox_data_table[var.inbox_group].columns
                    and "uid" in var.inbox_data[var.inbox_group].columns
                ):
                    match = var.inbox_data_table[var.inbox_group][
                        var.inbox_data_table[var.inbox_group]["uid"]
                        == var.inbox_data[var.inbox_group].iloc[row]["uid"]
                    ]
                    if not match.empty:
                        matching_row = match.index[0]
                if matching_row is None:
                    match = var.inbox_data_table[var.inbox_group][
                        (var.inbox_data_table[var.inbox_group]["from"] ==
                         var.inbox_data[var.inbox_group].iloc[row]["from"])
                        & (
                            var.inbox_data_table[var.inbox_group]["subject"]
                            == var.inbox_data[var.inbox_group].iloc[row]["subject"]
                        )
                        & (var.inbox_data_table[var.inbox_group]["date"] == var.inbox_data[var.inbox_group].iloc[row]["date"])
                    ]
                    if not match.empty:
                        matching_row = match.index[0]
                if matching_row is not None:
                    var.inbox_data_table[var.inbox_group].loc[matching_row,
                                                              "checkbox_status"] = 0
                print(var.inbox_data[var.inbox_group].iloc[row]["subject"])

    def toggle_all_checkboxes(self, state, header_checkbox):
        row_count = GUI.tableWidget_inbox.rowCount()
        checked = state == QtCore.Qt.Checked
        for row in range(row_count):
            checkbox = GUI.tableWidget_inbox.cellWidget(row, 0)
            if checkbox and isinstance(checkbox, QtWidgets.QCheckBox):
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
        inbox_df = None
        try:
            inbox_df = var.inbox_data[var.inbox_group]
        except Exception:
            inbox_df = None
        if inbox_df is not None and not inbox_df.empty and "checkbox_status" in inbox_df.columns:
            var.inbox_data[var.inbox_group].loc[:,
                                                "checkbox_status"] = 1 if checked else 0
            table_df = var.inbox_data_table[var.inbox_group]
            if (
                table_df is not None
                and not table_df.empty
                and "uid" in table_df.columns
                and "uid" in inbox_df.columns
            ):
                uids = inbox_df["uid"].tolist()
                var.inbox_data_table[var.inbox_group].loc[
                    var.inbox_data_table[var.inbox_group]["uid"].isin(uids),
                    "checkbox_status",
                ] = 1 if checked else 0
        all_checked = all(
            (
                GUI.tableWidget_inbox.cellWidget(row, 0).isChecked()
                for row in range(row_count)
                if GUI.tableWidget_inbox.cellWidget(row, 0)
            )
        )
        header_checkbox.setChecked(all_checked)

    def _normalize_thread_subject(self, subject):
        text = str(subject or "").strip()
        while True:
            updated = re.sub(r"^(\s*(re|fwd|fw)\s*:\s*)",
                             "", text, flags=re.IGNORECASE)
            if updated == text:
                break
            text = updated.strip()
        return text.lower()

    def _extract_row_participants(self, row_data):
        participants = set()
        for key in ["from_mail", "to_mail", "from", "to", "user"]:
            value = str(row_data.get(key, "") or "").strip().lower()
            if value:
                participants.add(value)
                for email_match in re.findall(
                    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value
                ):
                    participants.add(email_match.lower())
        return participants

    def _build_thread_view_html(self, thread_df):
        zoom_multiplier = 1 + (self.inbox_zoom_level * 0.1)
        base_font_size = max(10, int(round(14 * zoom_multiplier)))
        message_blocks = []
        for index, (_, row_data) in enumerate(thread_df.iterrows()):
            message_blocks.append(
                message_to_thread_html(
                    row_data.to_dict(),
                    show_metadata=index > 0,
                )
            )

        return (
            f"<html><body style='font-family: Arial, sans-serif; font-size: {base_font_size}px; line-height:1.5;'>"
            + "".join(message_blocks)
            + "</body></html>"
        )

    def _deduplicate_thread_messages(self, thread_df):
        if thread_df is None or thread_df.empty:
            return thread_df

        deduped = thread_df.copy()

        if "uid" in deduped.columns:
            uid_values = deduped["uid"].astype(str).str.strip()
            valid_uid = uid_values.ne("") & uid_values.ne(
                "nan") & uid_values.ne("none")
            with_uid = deduped[valid_uid].drop_duplicates(
                subset=["uid"], keep="first")
            without_uid = deduped[~valid_uid]
            deduped = pd.concat([with_uid, without_uid], ignore_index=True)

        if "message-id" in deduped.columns:
            message_id_values = deduped["message-id"].astype(
                str).str.strip().str.lower()
            valid_message_id = (
                message_id_values.ne("")
                & message_id_values.ne("nan")
                & message_id_values.ne("none")
            )
            with_message_id = deduped[valid_message_id].drop_duplicates(
                subset=["message-id"], keep="first"
            )
            without_message_id = deduped[~valid_message_id]
            deduped = pd.concat(
                [with_message_id, without_message_id], ignore_index=True)

        key_columns = [
            "from_mail",
            "to_mail",
            "from",
            "to",
            "subject",
            "body",
            "date",
        ]
        available_key_columns = [
            column_name for column_name in key_columns if column_name in deduped.columns
        ]
        if available_key_columns:
            deduped["_thread_dedupe_key"] = deduped[available_key_columns].apply(
                lambda row: "|".join(
                    [
                        str(cell_value or "").strip().lower()
                        for cell_value in row.values.tolist()
                    ]
                ),
                axis=1,
            )
            deduped = deduped.drop_duplicates(
                subset=["_thread_dedupe_key"], keep="first")
            deduped = deduped.drop(columns=["_thread_dedupe_key"])

        return deduped.reset_index(drop=True)

    def _get_conversation_thread(self, selected_row_data):
        inbox_table = var.inbox_data_table[var.inbox_group]
        if inbox_table is None or inbox_table.empty:
            return pd.DataFrame([selected_row_data])

        thread_subject = self._normalize_thread_subject(
            selected_row_data.get("subject", ""))
        selected_participants = self._extract_row_participants(
            selected_row_data)

        candidates = inbox_table.copy()
        if "subject" in candidates.columns:
            candidates = candidates[
                candidates["subject"].apply(
                    self._normalize_thread_subject) == thread_subject
            ]

        if not candidates.empty and selected_participants:
            candidates = candidates[
                candidates.apply(
                    lambda row: bool(
                        self._extract_row_participants(
                            row.to_dict()) & selected_participants
                    ),
                    axis=1,
                )
            ]

        if candidates.empty:
            candidates = pd.DataFrame([selected_row_data])

        if "date" in candidates.columns:
            sort_dates = pd.to_datetime(candidates["date"], errors="coerce")
            candidates = candidates.assign(_sort_date=sort_dates).sort_values(
                by="_sort_date", ascending=False
            )
        candidates = self._deduplicate_thread_messages(candidates)

        if "_sort_date" in candidates.columns:
            candidates = candidates.drop(columns=["_sort_date"])

        return candidates.reset_index(drop=True)

    def email_show(self, row=0, column=0):
        try:
            if var.inbox_data[var.inbox_group].iloc[row]["flag"] == "UNSEEN":
                imap_set_read = imap.ImapReadFlagEmail(row)
                Thread(target=imap_set_read.change_flag,
                       daemon=True, args=[]).start()
                var.inbox_data[var.inbox_group] = var.inbox_data[var.inbox_group].copy(
                )
                var.inbox_data[var.inbox_group].iloc[row, var.inbox_data[var.inbox_group].columns.get_loc("flag")] = (
                    "SEEN"
                )
                matching_row = var.inbox_data_table[var.inbox_group][
                    (var.inbox_data_table[var.inbox_group]["from"] ==
                     var.inbox_data[var.inbox_group].iloc[row]["from"])
                    & (
                        var.inbox_data_table[var.inbox_group]["subject"]
                        == var.inbox_data[var.inbox_group].iloc[row]["subject"]
                    )
                    & (var.inbox_data_table[var.inbox_group]["date"] == var.inbox_data[var.inbox_group].iloc[row]["date"])
                ].index[0]
                var.inbox_data_table[var.inbox_group].loc[matching_row,
                                                          "flag"] = "SEEN"
                button_show_mail = QtWidgets.QPushButton("")
                button_show_mail.setStyleSheet(var.button_style)
                button_show_mail.clicked.connect(self.email_show)
                button_show_mail.setIcon(QtGui.QIcon(var.mail_read_icon))
                GUI.tableWidget_inbox.setCellWidget(row, 1, button_show_mail)
            GUI.lineEdit_original_recipient.setText(
                var.inbox_data[var.inbox_group].iloc[row]["to"])
            var.email_in_view = var.inbox_data[var.inbox_group].iloc[row].to_dict(
            )
            var.email_in_view["original_body"] = var.inbox_data[var.inbox_group].iloc[row]["body"]
            var.email_in_view["original_subject"] = var.inbox_data[var.inbox_group].iloc[row]["subject"]
            self.change_subject()
            GUI.lineEdit_original_from.setText(
                var.inbox_data[var.inbox_group].iloc[row]["from"])
            GUI.lineEdit_original_date.setText(header_date_text(var.email_in_view))
            GUI.textBrowser_show_email.clear()
            selected_row_data = var.inbox_data[var.inbox_group].iloc[row].to_dict(
            )
            thread_df = self._get_conversation_thread(selected_row_data)
            GUI.textBrowser_show_email.setHtml(
                self._build_thread_view_html(thread_df))
            unread_count = sum(
                (1 for flag in var.inbox_data[var.inbox_group]
                 ["flag"] if flag == "UNSEEN")
            )
            if unread_count > 0:
                GUI.label_unread_count.setText(str(unread_count))
            else:
                GUI.label_unread_count.setText("")
        except Exception as e:
            print("Error at email_show : {}".format(e))
            self.logger.error("Error at email_show - {}".format(e))

    def date_update(self):
        new_date = GUI.dateEdit_imap_since.date().toString("M/d/yyyy")
        new_date_datetime = pd.to_datetime(new_date, format="%m/%d/%Y")
        date_datetime = pd.to_datetime(var.date, format="%m/%d/%Y")
        if new_date_datetime < date_datetime:
            self.autoReply_positive_last_date = new_date_datetime.strftime(
                "%Y-%m-%d %H:%M:%S")
            self.autoReply_all_last_date = new_date_datetime.strftime(
                "%Y-%m-%d %H:%M:%S")
        var.date = new_date

    def date_sort(self):
        GUI.pushButton_sort_alpha.setEnabled(False)
        GUI.pushButton_sort_date.setEnabled(False)
        self.option = GUI.pushButton_sort_date.text()
        if self.option == "Earliest":
            GUI.pushButton_sort_date.setText("Latest")
        else:
            GUI.pushButton_sort_date.setText("Earliest")
        self.sort_inbox_data(self.option)
        GUI.pushButton_sort_alpha.setEnabled(True)
        GUI.pushButton_sort_date.setEnabled(True)

    def alpha_sort(self):
        print("alpha_sort")
        GUI.pushButton_sort_alpha.setEnabled(False)
        GUI.pushButton_sort_date.setEnabled(False)
        self.option = GUI.pushButton_sort_alpha.text()
        if self.option == "A - Z":
            GUI.pushButton_sort_alpha.setText("Z - A")
        else:
            GUI.pushButton_sort_alpha.setText("A - Z")
        self.sort_inbox_data(self.option)
        GUI.pushButton_sort_alpha.setEnabled(True)
        GUI.pushButton_sort_date.setEnabled(True)

    def sort_inbox_data(self, option):
        var.email_in_view = {}
        var.row_pos = 0
        GUI.tableWidget_inbox.setRowCount(0)
        inbox_data = var.inbox_data[var.inbox_group].copy()
        # Only attempt to sort if the relevant column exists to avoid KeyError
        cols = inbox_data.columns
        if option == "Latest":
            if "date" in cols:
                inbox_data.sort_values(by="date", inplace=True, ascending=True)
        else:
            if option == "A - Z":
                if "subject" in cols:
                    inbox_data.sort_values(
                        by="subject", inplace=True, ascending=False)
            else:
                if option == "Z - A":
                    if "subject" in cols:
                        inbox_data.sort_values(
                            by="subject", inplace=True, ascending=True)
                else:
                    if "date" in cols:
                        inbox_data.sort_values(
                            by="date", inplace=True, ascending=False)
        inbox_data.reset_index(drop=True, inplace=True)
        var.inbox_data[var.inbox_group] = inbox_data
        self.display_email_in_table()

    def get_index_of_button(self, table):
        button = QtWidgets.qApp.focusWidget()
        index = table.indexAt(button.pos())
        if index.isValid():
            return (index.row(), index.column())


def set_icon(obj):
    try:

        def resource_path(relative_path):
            if hasattr(sys, "_MEIPASS"):
                return os.path.join(sys._MEIPASS, relative_path)
            return os.path.join(os.path.abspath("."), relative_path)

        p = resource_path("icons/icon.ico")
        obj.setWindowIcon(QtGui.QIcon(p))
    except Exception as e:
        print(e)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)

    def closeEvent(self, event):
        close = QtWidgets.QMessageBox.question(
            self,
            "QUIT",
            "Are you sure?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if close == QtWidgets.QMessageBox.Yes or quit_application == True:
            myMC.command_timer.stop()
            event.accept()
        else:
            event.ignore()


class CustomListWidgetItem(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label_inbox = QLabel("Inbox", self)
        self.label_unread_count = QLabel("10", self)
        self.label_inbox.setStyleSheet("font-size: 12px;")
        self.label_unread_count.setStyleSheet("font-size: 12px;")
        layout = QHBoxLayout()
        layout.addWidget(self.label_inbox)
        layout.addWidget(self.label_unread_count)
        layout.addStretch()
        self.setLayout(layout)


class FileWidget(QtWidgets.QWidget):
    def __init__(self, file_path, is_campaign, parent_layout):
        super().__init__()
        self.file_path = file_path
        self.is_campaign = is_campaign
        self.parent_layout = parent_layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setPixmap(QtGui.QIcon(
            ":/icons/icons/file.svg").pixmap(80, 50))
        self.icon_label.setToolTip(os.path.basename(file_path))
        self.close_button = QtWidgets.QPushButton("✖")
        if is_campaign:
            self.close_button.setFixedSize(70, 20)
        else:
            self.close_button.setFixedSize(50, 20)
        self.close_button.setStyleSheet(
            "border: none; color: #7a7a7a;"
        )
        self.close_button.clicked.connect(self.remove_widget)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.close_button)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

    def remove_widget(self):
        if self.is_campaign:
            if self.file_path in var.files:
                var.files.remove(self.file_path)
        else:
            if self.file_path in var.reply_files:
                var.reply_files.remove(self.file_path)
        self.setParent(None)
        self.deleteLater()


if __name__ == "__main__":
    print("ran from here")
else:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(
        "QPushButton, QToolButton { font-family: Arial; font-weight: 400; }"
    )
    if sys.platform == "darwin":
        app.setStyle("Fusion")
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#E3E3E3"))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#333333"))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#FFFFFF"))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#EFF2F8"))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#222222"))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor("#FFFFFF"))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#333333"))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#028FC3"))
        palette.setColor(QtGui.QPalette.HighlightedText,
                         QtGui.QColor("#FFFFFF"))
        app.setPalette(palette)
    mainWindow = MainWindow()
    set_icon(mainWindow)
    mainWindow.setWindowFlags(
        mainWindow.windowFlags()
        | QtCore.Qt.WindowMinimizeButtonHint
        | QtCore.Qt.WindowSystemMenuHint
    )
    GUI = MyGui(mainWindow)
    mainWindow.showMaximized()
    import var
    from var import logger
    import imap
    import smtp
    from utils import update_config_json, prepare_html, is_number, get_config_json
    from progressbar import DeleteEmail
    from download_email import Download
    from campaign_reply import Reply
    from send_dialog import Send
    from table_view import TableModel, InLineEditDelegate
    import database
    from webhook import start_inbox_stream
    from update_checker import update_checker

    myMC = MyMainClass()

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        var.exit_gracefully(signum, frame)
        app.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    app.exec_()
    logger.info("Exiting")
    sys.exit()
