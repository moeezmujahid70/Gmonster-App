from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, QObject
from threading import Thread

import utils
import var
from email_input_gui import Ui_Dialog
import os, sys
import html
from smtp import ForwardMail, TestMail
from mailgenius import MailGeniusClient, MailGeniusError, sanitize_mailgenius_html
from user_messages import mailgenius_message, smtp_message
import re

regex = '[^@]+@[^@]+\.[^@]+'


def check(email):
    # pass the regular expression
    # and the string in search() method
    if (re.search(regex, email)):
        return True
    else:
        return False


def set_icon(obj):
    try:
        def resource_path(relative_path):
            if hasattr(sys, '_MEIPASS'):
                return os.path.join(sys._MEIPASS, relative_path)
            return os.path.join(os.path.abspath("."), relative_path)

        p = resource_path('icons/icon.ico')
        obj.setWindowIcon(QtGui.QIcon(p))
    except Exception as e:
        print(e)


class Communicate(QObject):
    s = pyqtSignal(str, int, int)
    mailgenius = pyqtSignal(str, object)


class Send(Ui_Dialog):
    def __init__(self, dialog, parent='forward'):
        Ui_Dialog.__init__(self)
        self.setupUi(dialog)
        self.dialog = dialog
        set_icon(self.dialog)
        self.type = parent
        self._apply_platform_font()
        if self.type == "test":
            self.dialog.setMinimumSize(560, 260)
            self.dialog.resize(560, 260)
        self.pushButton_send.clicked.connect(self.thread_starter)
        self.lineEdit_email.setText(var.test_email)
        self.signal = Communicate()
        self.signal.s.connect(self.update_gui)
        self.signal.mailgenius.connect(self.update_mailgenius)
        self._setup_mailgenius_controls()

        if self.type == 'forward':
            self.label_linedit.setText("Forward To:")
        else:
            self.label_linedit.setText("Send Test To:")

    def _apply_platform_font(self):
        family = "Arial" if sys.platform == "darwin" else "Arial"
        font = QtGui.QFont(family, 12)
        for widget in (
            self.label_linedit,
            self.lineEdit_email,
            self.pushButton_send,
            self.label_status,
            self.progressBar,
        ):
            widget.setFont(font)
        self.dialog.setStyleSheet(
            "QDialog { background: #eff2f8; } "
            "QLabel { color: #374151; font-family: 'Helvetica Neue', Arial, sans-serif; } "
            "QLineEdit { color: #111827; background: #ffffff; font-family: 'Helvetica Neue', Arial, sans-serif; } "
            "QCheckBox { color: #374151; font-family: Arial, sans-serif; font-size: 13px; } "
            "QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #94a3b8; background: #ffffff; } "
            "QCheckBox::indicator:checked { background: #3b82a0; border-color: #3b82a0; }"
        )
        self.label_status.setStyleSheet(
            "QLabel { color: #374151; background: transparent; }"
        )
        self.pushButton_send.setStyleSheet(
            "QPushButton { background: rgb(0, 138, 191); color: white; "
            "border: 1px solid #0b5f80; border-radius: 4px; padding: 6px 28px; } "
            "QPushButton:hover { background: rgb(0, 120, 170); } "
            "QPushButton:pressed { background: rgb(0, 104, 150); }"
        )

    def _setup_mailgenius_controls(self):
        if not hasattr(self, "checkBox_mailgenius"):
            self.checkBox_mailgenius = QtWidgets.QCheckBox(
                "Also test spam score with MailGenius", self.dialog
            )
            self.frame_mailgenius_results = QtWidgets.QFrame(self.dialog)
            self.frame_mailgenius_results.setStyleSheet(
                "QFrame { background: #ffffff; border: 1px solid #e5e7eb; "
                "border-radius: 10px; color: #1f2937; font-family: -apple-system, "
                "'Helvetica Neue', Arial, sans-serif; }"
            )
            layout = QtWidgets.QVBoxLayout(self.frame_mailgenius_results)
            self.verticalLayout_mailgenius = layout
            self.label_mailgenius_state = QtWidgets.QLabel("MailGenius ready")
            self.label_mailgenius_state.setStyleSheet(
                "QLabel { color: #1f2937; font-weight: 600; background: transparent; }"
            )
            self.formLayout_mailgenius_results = QtWidgets.QFormLayout()
            layout.addWidget(self.label_mailgenius_state)
            layout.addLayout(self.formLayout_mailgenius_results)
            self.gridLayout.addWidget(self.checkBox_mailgenius, 4, 0, 1, 3)
            self.gridLayout.addWidget(self.frame_mailgenius_results, 5, 0, 1, 3)

        if not hasattr(self, "progressBar_mailgenius"):
            self.progressBar_mailgenius = QtWidgets.QProgressBar()
            self.progressBar_mailgenius.setTextVisible(False)
            self.progressBar_mailgenius.setFixedHeight(6)
            self.progressBar_mailgenius.setStyleSheet(
                "QProgressBar { border: 0; border-radius: 3px; background: #eef2f7; } "
                "QProgressBar::chunk { border-radius: 3px; background: #3b82a0; }"
            )
            self.verticalLayout_mailgenius.insertWidget(1, self.progressBar_mailgenius)

        if not hasattr(self, "pushButton_mailgenius_details"):
            self.pushButton_mailgenius_details = QtWidgets.QPushButton(
                "Show detailed checks", self.frame_mailgenius_results
            )
            self.pushButton_mailgenius_details.setCheckable(True)
            self.pushButton_mailgenius_details.setStyleSheet(
                "QPushButton { color: #3b82a0; background: transparent; border: 0; "
                "font-weight: 600; padding: 6px 0; text-align: left; }"
            )
            self.widget_mailgenius_details = QtWidgets.QWidget(
                self.frame_mailgenius_results
            )
            self.layout_mailgenius_details = QtWidgets.QVBoxLayout(
                self.widget_mailgenius_details
            )
            self.layout_mailgenius_details.setContentsMargins(0, 4, 0, 0)
            self.layout_mailgenius_details.setSpacing(6)
            self.verticalLayout_mailgenius.addWidget(self.pushButton_mailgenius_details)
            self.verticalLayout_mailgenius.addWidget(self.widget_mailgenius_details)
            self.pushButton_mailgenius_details.toggled.connect(
                self._toggle_mailgenius_details
            )

        configured = bool(str(getattr(var, "api", "")).strip())
        is_test = self.type == "test"
        self.checkBox_mailgenius.setVisible(is_test)
        self.checkBox_mailgenius.setFont(QtGui.QFont("Arial", 13))
        self.checkBox_mailgenius.setEnabled(is_test)
        self.checkBox_mailgenius.setStyleSheet(
            "QCheckBox { color: #374151; font-family: Arial; font-size: 13px; } "
            "QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #94a3b8; background: #ffffff; } "
            "QCheckBox::indicator:checked { background: #3b82a0; border-color: #3b82a0; }"
        )
        self.checkBox_mailgenius.setToolTip(
            "" if configured else "MailGenius requires the configured GMonster server."
        )
        self.frame_mailgenius_results.setVisible(False)
        self.progressBar_mailgenius.setVisible(False)
        self.pushButton_mailgenius_details.setVisible(False)
        self.widget_mailgenius_details.setVisible(False)
        self.checkBox_mailgenius.toggled.connect(self._toggle_mailgenius)

    def _toggle_mailgenius(self, enabled):
        self.frame_mailgenius_results.setVisible(enabled)
        if enabled:
            self.dialog.setMinimumWidth(560)
            self.dialog.setMinimumHeight(360)
        self.dialog.adjustSize()
        if enabled and self.dialog.width() < 560:
            self.dialog.resize(560, self.dialog.height())

    def _toggle_mailgenius_details(self, expanded):
        self.widget_mailgenius_details.setVisible(expanded)
        self.pushButton_mailgenius_details.setText(
            "Hide detailed checks" if expanded else "Show detailed checks"
        )
        self.dialog.adjustSize()

    @staticmethod
    def _mailgenius_factor_text(factor):
        if isinstance(factor, dict):
            values = [
                "{}: {}".format(str(key).replace("_", " ").title(), value)
                for key, value in factor.items()
                if isinstance(value, (str, int, float, bool)) and value not in ("", None)
            ]
            return " · ".join(values)
        return str(factor)

    def update_mailgenius(self, state, data):
        self.label_mailgenius_state.setText(state)
        loading = state in {
            "Creating MailGenius audit...",
            "Email sent — analyzing deliverability...",
        }
        self.progressBar_mailgenius.setVisible(loading)
        if loading:
            self.progressBar_mailgenius.setRange(0, 0)
            self.label_mailgenius_state.setStyleSheet(
                "QLabel { color: #1d4ed8; font-weight: 600; background: transparent; }"
            )
        elif state == "Spam score ready":
            self.progressBar_mailgenius.setRange(0, 100)
            self.progressBar_mailgenius.setValue(100)
            self.label_mailgenius_state.setStyleSheet(
                "QLabel { color: #15803d; font-weight: 700; background: transparent; }"
            )
        else:
            self.label_mailgenius_state.setStyleSheet(
                "QLabel { color: #b91c1c; font-weight: 600; background: transparent; }"
            )
        while self.formLayout_mailgenius_results.rowCount():
            self.formLayout_mailgenius_results.removeRow(0)
        while self.layout_mailgenius_details.count():
            item = self.layout_mailgenius_details.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if isinstance(data, dict):
            score = data.get("score")
            status = data.get("status")
            if score is not None:
                try:
                    score_value = float(score)
                    color = "#15803d" if score_value >= 80 else "#b45309" if score_value >= 60 else "#b91c1c"
                    score_text = "{:.0f} / 100".format(score_value)
                except (TypeError, ValueError):
                    color, score_text = "#374151", str(score)
                score_label = QtWidgets.QLabel(score_text)
                score_label.setStyleSheet(
                    "QLabel { color: %s; font-size: 18px; font-weight: 600; background: transparent; }" % color
                )
                self.formLayout_mailgenius_results.addRow("Score", score_label)
            if status:
                status_label = QtWidgets.QLabel(str(status).title())
                status_label.setStyleSheet(
                    "QLabel { color: #2f855a; font-weight: 600; background: transparent; }"
                )
                self.formLayout_mailgenius_results.addRow("Status", status_label)
            aspects = data.get("aspects")
            if isinstance(aspects, list):
                passed = sum(1 for aspect in aspects if aspect.get("passing"))
                issues = len(aspects) - passed
                self.formLayout_mailgenius_results.addRow(
                    "Checks", QtWidgets.QLabel(
                        "{} passed · {} need attention".format(passed, issues)
                    )
                )
                self.pushButton_mailgenius_details.setVisible(True)
                detail_sections = []
                for aspect in aspects:
                    passing = bool(aspect.get("passing"))
                    color = "#2f855a" if passing else "#b7791f"
                    title = html.escape(str(aspect.get("message", "MailGenius check")))
                    meta = "{} · {} severity · {} points deducted".format(
                        "Pass" if passing else "Needs attention",
                        html.escape(str(aspect.get("severity", "None")).title()),
                        html.escape(str(aspect.get("points_deducted", 0))),
                    )
                    lines = [
                        '<div style="margin:8px 0;padding:10px;border:1px solid #e5e7eb;border-radius:8px;background:#ffffff;">',
                        '<div style="color:#1f2937;font-weight:600;">{}</div>'.format(title),
                        '<div style="color:{};font-size:11px;margin-top:3px;">{}</div>'.format(color, meta),
                    ]
                    why = aspect.get("why_is_it_important")
                    if why:
                        lines.append('<div style="color:#4b5563;font-size:11px;margin-top:5px;">{}</div>'.format(sanitize_mailgenius_html(why)))
                    factors = aspect.get("factors")
                    if isinstance(factors, list):
                        for factor in factors:
                            factor_text = self._mailgenius_factor_text(factor)
                            if factor_text:
                                lines.append('<div style="color:#4b5563;font-size:11px;margin-top:3px;">• {}</div>'.format(sanitize_mailgenius_html(factor_text)))
                    lines.append("</div>")
                    detail_sections.append("".join(lines))
                details = QtWidgets.QTextBrowser()
                details.setOpenExternalLinks(False)
                details.setReadOnly(True)
                details.setMinimumHeight(250)
                details.setStyleSheet("QTextBrowser { border: 0; background: transparent; color: #1f2937; font-family: Arial, sans-serif; font-size: 12px; }")
                details.setHtml("".join(detail_sections))
                self.layout_mailgenius_details.addWidget(details)
        self.frame_mailgenius_results.setVisible(True)
        self.dialog.setMinimumWidth(560)
        self.dialog.adjustSize()
        if self.dialog.width() < 560:
            self.dialog.resize(560, self.dialog.height())

    def thread_starter(self):
        if self.type == 'forward':
            Thread(target=self.forward, daemon=True).start()
        else:
            Thread(target=self.test, daemon=True).start()

    def update_gui(self, label_text, p_value, button):
        self.label_status.setText(label_text)
        self.label_status.setToolTip(label_text)
        self.progressBar.setValue(p_value)
        self.pushButton_send.setDisabled(button)

    def forward(self):
        forward_to = var.test_email = self.lineEdit_email.text().strip()
        Thread(target=utils.update_config_json, args=[]).start()
        if check(forward_to):
            self.signal.s.emit("Sending...", 0, True)

            forward = ForwardMail(forward_to=forward_to)
            if forward.send():
                self.signal.s.emit("Sent", 100, False)
            else:
                self.signal.s.emit("Forward could not be sent. Check the sender account and connection, then try again.", 0, False)
        else:
            self.signal.s.emit("Enter a valid recipient email address.", 0, False)

    def test(self):
        send_to = var.test_email = self.lineEdit_email.text().strip()
        Thread(target=utils.update_config_json, args=[]).start()
        if check(send_to):
            audit = None
            if self.checkBox_mailgenius.isChecked():
                try:
                    var.logger.info("MailGenius: enabled for campaign test send")
                    self.signal.mailgenius.emit("Creating MailGenius audit...", {})
                    audit = MailGeniusClient().start_audit()
                except MailGeniusError as error:
                    message = mailgenius_message(error)
                    var.logger.error("MailGenius audit could not start [%s]: %s", message.code, error)
                    self.signal.mailgenius.emit(message.body, {})
                    self.signal.s.emit(message.body + " Error reference: " + message.code, 0, False)
                    return
            self.signal.s.emit("Sending...", 0, True)
            test = TestMail(
                send_to=send_to,
                audit_recipient=audit.test_email if audit else None,
            )
            if test.send():
                if audit:
                    try:
                        var.logger.info("MailGenius: test email sent; waiting for server audit")
                        self.signal.s.emit("Email sent — analyzing deliverability...", 100, True)
                        result = MailGeniusClient().wait_for_result(audit.audit_id)
                        self.signal.mailgenius.emit("Spam score ready", result.data)
                        var.logger.info("MailGenius: server audit completed")
                    except MailGeniusError as error:
                        message = mailgenius_message(error)
                        var.logger.error("MailGenius audit failed [%s]: %s", message.code, error)
                        self.signal.mailgenius.emit(message.body, {})
                        self.signal.s.emit("Test email sent. " + message.body + " Error reference: " + message.code, 100, False)
                        return
                    self.signal.s.emit("Sent", 100, False)
                else:
                    self.signal.s.emit("Sent", 100, False)
            else:
                if audit:
                    var.logger.error("MailGenius: SMTP test send failed before the audit could be analyzed")
                    if test.mailgenius_delivery_error:
                        self.signal.mailgenius.emit("MailGenius could not receive the test email. Check the sender account and try again.", {})
                        self.signal.s.emit("Test email was sent, but MailGenius could not receive its copy. Error reference: SMTP_RECIPIENT_REJECTED", 100, False)
                        return
                message = test.failure_message or smtp_message()
                self.signal.s.emit(message.body + " Error reference: " + message.code, 0, False)
        else:
            self.signal.s.emit("Enter a valid test email address.", 0, False)
