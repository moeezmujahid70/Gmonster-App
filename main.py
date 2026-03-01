from email_validator import validate_email
from textblob import TextBlob
from gui import Ui_MainWindow
from database import update_target_verified
from openai import OpenAI
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
global app
global mainWindow
global myMC
global quit_application
global GUI

quit_application = False


class AIPromptDialog(QDialog):
    promptSubmitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = OpenAI(api_key=var.open_ai_key)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(300, 200, 400, 300)
        layout = QVBoxLayout(self)
        self.title_label = QLabel("AI Assistant")
        layout.addWidget(self.title_label)
        self.text_input = QTextEdit(var.compose_prompt)
        layout.addWidget(self.text_input)
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

    def get_ai_response(self):
        prompt = self.text_input.toPlainText().strip()
        var.compose_prompt = prompt
        Thread(target=update_config_json, daemon=True).start()
        if not prompt:
            alert(text="Please enter a prompt.", title="Warning", button="OK")
            return
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert email copywriter.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            answer = response.choices[0].message.content
            self.promptSubmitted.emit(answer)
        except Exception as e:
            alert(text=f"Failed to connect: {str(e)}",
                  title="Error", button="OK")


class MyGui(Ui_MainWindow, QtWidgets.QWidget):
    def __init__(self, main_window):
        Ui_MainWindow.__init__(self)
        QtWidgets.QWidget.__init__(self)
        self.setupUi(main_window)


class MyMainClass:
    def __init__(self):
        self.compose_font_size = 13
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
        GUI.checkBox_inbox_whitelist.setChecked(var.inbox_whitelist_checkbox)
        GUI.checkBox_space_encoding.setChecked(var.space_encoding_checkbox)
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
        GUI.lineEdit_open_ai_key.setText(var.open_ai_key)
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
        GUI.checkBox_inbox_whitelist.stateChanged.connect(
            self.update_checkbox_status)
        GUI.checkBox_enable_cc_emails.stateChanged.connect(
            self.update_checkbox_status)
        GUI.pushButton_email_verify.clicked.connect(self.email_verify)
        GUI.pushButton_select_toggle.toggled.connect(
            self.toggle_checkbox_section)
        # Initialize dropdown visibility
        GUI.frame_verifier_dropdown.setVisible(True)
        GUI.frame_checkboxes.setVisible(True)
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
        GUI.pushButton_delete.clicked.connect(self.batch_delete)
        GUI.pushButton_forward.clicked.connect(self.forward)
        GUI.pushButton_test.clicked.connect(self.test_send)
        GUI.textBrowser_show_email.anchorClicked.connect(
            QtGui.QDesktopServices.openUrl)
        GUI.textBrowser_compose.textChanged.connect(self.compose_update)
        GUI.textEdit_reply.textChanged.connect(self.update_rely_text)
        GUI.label_desktop_app_id.setText(
            f"Desktop ID: {var.gmonster_desktop_id}")
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
            lambda: threading.Thread(
                target=self.schedule_campaign, daemon=True, args=[]
            ).start()
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
        if index in {4, 0, 1, 3, 2}:
            GUI.stackedWidget.setCurrentIndex(index)
        elif index == 9:
            self.launch_wum()
        elif index == 10:
            GUI.stackedWidget.setCurrentIndex(5)
        else:
            url_mappings = {
                "Store": "https://gmonster.co/store",
                "Leads": "https://gmonster.co/leads",
                "Tutorials": "https://gmonster.co/tutorials",
                "Support": "https://gmonster.co/support"
            }
            item = GUI.listWidget.item(index)
            item_text = item.text()
            if item_text in url_mappings:
                webbrowser.open(url_mappings[item_text])
            else:
                print("Invalid Index")

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

        if os.path.exists("database/verify_blacklist.txt"):
            with open("database/verify_blacklist.txt", "r") as f:
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
                    url, headers=headers, json=data, timeout=120)
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
                        response = requests.post(url, timeout=10)
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
            verification_folder = "Email verification"
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
        response = requests.post(url, data=payload, headers=headers)
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
        wum_path = os.path.join(os.getcwd(), var.wum_exe_path)
        if os.path.exists(wum_path):
            subprocess.Popen([wum_path])
            return

        mac_app_path = os.path.join(os.getcwd(), "WUM.app")
        if sys.platform == "darwin" and os.path.exists(mac_app_path):
            subprocess.Popen(["open", mac_app_path])
            return

        alert(text="WUM executable not found for this platform.",
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

    def schedule_campaign(self):
        try:
            group_selected = (
                "group_a" if GUI.radioButton_campaign_group_a.isChecked() else "group_b"
            )
            group = (
                var.group_a
                if GUI.radioButton_campaign_group_a.isChecked()
                else var.group_b
            )
            var.num_emails_per_address = str(
                GUI.lineEdit_num_per_address.text())
            num_emails_per_address_range = {
                "start": int(var.num_emails_per_address.split("-")[0].strip()),
                "end": int(var.num_emails_per_address.split("-")[1].strip()),
            }
            var.delay_between_emails = GUI.lineEdit_delay_between_emails.text()
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

            result = confirm(f"This campaign is going to take approximately "
                             f"{maximum_duration:.4f} hours to complete AT MAX.\n"
                             f"And this campaign will be scheduled at "
                             f"{scheduled_time.strftime('%m/%d/%Y, %H:%M:%S')}. "
                             f"\nAre you sure?",
                             title="Campaign Scheduler", buttons=['OK', 'Cancel'])

            if result == 'OK':
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

    def set_campaign_config(self):
        GUI.lineEdit_num_per_address.setText(str(var.num_emails_per_address))
        GUI.lineEdit_delay_between_emails.setText(
            str(var.delay_between_emails))
        GUI.lineEdit_number_of_threads.setText(str(var.limit_of_thread))

    def remove_schedule_campaign(self, job_id):
        try:
            logger.info(f"Removing job {job_id} from list")
            var.scheduler.remove_job(job_id=job_id)
            self.reset_schedule_campaign_job_list()
            logger.info(f"Removed successfully job {job_id} from list")
        except Exception as e:
            logger.error(f"Error at remove_schedule_campaign: {e}")

    def reset_schedule_campaign_job_list(self):
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
                self.set_campaign_config()
                if campaign_group == "group_a":
                    GUI.radioButton_campaign_group_a.setChecked(True)
                else:
                    GUI.radioButton_campaign_group_b.setChecked(True)
                if var.AirtableConfig.continuous_loading:
                    pull_target_airtable = database.PullTargetAirtable()
                    pull_target_airtable.start()
                    while database.PullTargetAirtable.still_running:
                        time.sleep(1)
                var.stop_send_campaign = False
                var.thread_open_campaign = 0
                var.send_campaign_email_count = 0
                self.send_button_visibility(on=False)
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
            try:
                client = OpenAI(api_key=var.open_ai_key)
                if not var.autoReply_prompt or not var.autoReply_prompt.strip():
                    alert(text="Please enter a prompt.",
                          title="Warning", button="OK")
                    return
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {str(e)}")
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
                            response = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[
                                    {
                                        "role": "system",
                                        "content": "You are an expert email copywriter.",
                                    },
                                    {"role": "user", "content": new_prompt},
                                ],
                            )
                            answer = response.choices[0].message.content
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
        file_path = "database/autoReply_address.txt"
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
            with open("database/blacklist.txt", "r") as file:
                negative_words = file.read().strip().splitlines()
        except FileNotFoundError:
            logger.info(
                "Warning: 'database/blacklist.txt' not found. Using default negative words."
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
            var.inbox_whitelist = inbox_whitelist.split(",")
            var.inbox_whitelist = list(filter(None, var.inbox_whitelist))
        else:
            var.inbox_whitelist = list()

    def update_checkbox_proxy(self):
        var.proxy_on = GUI.checkBox_proxy_enabled.isChecked()

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
        var.inbox_whitelist_checkbox = GUI.checkBox_inbox_whitelist.isChecked()
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
                response = requests.post(url, timeout=10)
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
        result = confirm(
            text="Are you sure?", title="Confirmation Window", buttons=["OK", "Cancel"]
        )
        if result == "OK":
            Thread(target=database.load_db, daemon=True).start()
        else:
            print("cancelled")

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
            value = (
                var.send_campaign_email_count / var.total_email_to_be_sent * 100
            )
            GUI.label_campaign_status.setText(
                "{}/{}".format(
                    var.send_campaign_email_count, var.total_email_to_be_sent
                )
            )
            if value >= 100:
                GUI.lable_campaign_status_text.setText("Finished")
            elif var.stop_send_campaign:
                GUI.lable_campaign_status_text.setText("Stopped")
            else:
                GUI.lable_campaign_status_text.setText("Sending")
            GUI.progressBar_compose.setValue(int(value))
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
                            "INBOX", '"[Gmail]/Sent Mail"']
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
                            folders=["INBOX", '"[Gmail]/Sent Mail"'],
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
            unread_count = sum(
                (1 for flag in var.inbox_data[var.inbox_group]
                 ["flag"] if flag == "UNSEEN")
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
        message_blocks = []
        for _, row_data in thread_df.iterrows():
            from_text = html.escape(
                str(row_data.get("from", "") or row_data.get("from_mail", "")))
            to_text = html.escape(
                str(row_data.get("to", "") or row_data.get("to_mail", "")))
            subject_text = html.escape(str(row_data.get("subject", "")))

            date_value = row_data.get("date", "")
            if hasattr(date_value, "strftime"):
                date_text = date_value.strftime("%Y-%m-%d %H:%M:%S")
            else:
                date_text = str(date_value)
            date_text = html.escape(date_text)

            body_text = str(row_data.get("body", "") or "")
            if "</body>" in body_text.lower():
                body_match = re.search(
                    r"<body[^>]*>(.*?)</body>",
                    body_text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                body_html = body_match.group(1) if body_match else body_text
            else:
                body_html = html.escape(body_text).replace("\n", "<br>")

            message_blocks.append(
                f"""
                <div style=\"margin:0 0 14px 0; padding:10px; border:1px solid #ddd; background:#fafafa;\">
                    <div style=\"font-size:12px; color:#444; margin-bottom:8px;\"><b>From:</b> {from_text}</div>
                    <div style=\"font-size:12px; color:#444; margin-bottom:8px;\"><b>To:</b> {to_text}</div>
                    <div style=\"font-size:12px; color:#666; margin-bottom:8px;\"><b>Date:</b> {date_text}</div>
                    <div style=\"font-size:20px; font-weight:600; margin:0 0 10px 0;\">{subject_text}</div>
                    <div>{body_html}</div>
                </div>
                """
            )

        return (
            "<html><body style='font-family: Arial, sans-serif; font-size: 14px;'>"
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
            "border: none; color: #7a7a7a; font-weight: bold;"
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
