from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, QObject
from threading import Thread

import utils
import var
from email_input_gui import Ui_Dialog
import os, sys
from smtp import ForwardMail, TestMail
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


class Send(Ui_Dialog):
    def __init__(self, dialog, parent='forward'):
        Ui_Dialog.__init__(self)
        self.setupUi(dialog)
        self.dialog = dialog
        set_icon(self.dialog)
        self.type = parent
        self.pushButton_send.clicked.connect(self.thread_starter)
        self.lineEdit_email.setText(var.test_email)
        self.signal = Communicate()
        self.signal.s.connect(self.update_gui)

        if self.type == 'forward':
            self.label_linedit.setText("Forward To:")
        else:
            self.label_linedit.setText("Send Test To:")

    def thread_starter(self):
        if self.type == 'forward':
            Thread(target=self.forward, daemon=True).start()
        else:
            Thread(target=self.test, daemon=True).start()

    def update_gui(self, label_text, p_value, button):
        self.label_status.setText(label_text)
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
                self.signal.s.emit("Error happened while sending!!!", 0, False)
        else:
            self.signal.s.emit("Enter a proper email address...", 0, False)

    def test(self):
        send_to = var.test_email = self.lineEdit_email.text().strip()
        Thread(target=utils.update_config_json, args=[]).start()
        if check(send_to):
            self.signal.s.emit("Sending...", 0, True)

            test = TestMail(send_to=send_to)
            if test.send():
                self.signal.s.emit("Sent", 100, False)
            else:
                self.signal.s.emit("Error happened while sending!!!", 0, False)
        else:
            self.signal.s.emit("Enter a proper email address...", 0, False)
