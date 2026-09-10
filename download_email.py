from PyQt5 import QtCore, QtGui
from threading import Thread
import var
from p_gui import Ui_Dialog
from user_messages import summary_text
import os
import sys


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


class Download(Ui_Dialog):

    def __init__(self, dialog, group=None, folders=["INBOX"]):
        Ui_Dialog.__init__(self)
        self.setupUi(dialog)
        self.dialog = dialog
        set_icon(self.dialog)
        self.pushButton_cancel.clicked.connect(self.cancel)
        self.label_status.setWordWrap(True)
        self._summary_shown = False
        self.timer = QtCore.QTimer()
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.update_gui)
        from imap import main

        Thread(target=main, daemon=True, args=[
               group, folders, var.date, False]).start()
        self.timer.start()

    def update_gui(self):
        try:
            if var.download_email_status:
                self.label_status.setText(
                    f"Total Email Downloaded : {var.total_email_downloaded}"
                )
            elif not self._summary_shown:
                self._summary_shown = True
                msg = f"Total Email Downloaded : {var.total_email_downloaded}   Accounts failed : {var.email_failed}"
                if var.hide_warmup_emails:
                    msg += " | Hide warm up filter enabled"
                if var.email_failed and var.inbox_user_messages:
                    msg += "\n\n" + summary_text(var.inbox_user_messages)
                    self.dialog.setMinimumWidth(480)
                self.label_status.setText(msg)
                self.pushButton_cancel.setText("Close")
                self.dialog.adjustSize()
            # compute percentage safely (avoid ZeroDivisionError) and pass int to setValue
            try:
                if var.total_acc and var.total_acc > 0:
                    value = int(round(var.acc_finished / var.total_acc * 100))
                else:
                    value = 0
            except Exception:
                value = 0
            # clamp between 0 and 100
            value = max(0, min(100, value))
            self.progressBar.setValue(value)
        except Exception as e:
            print("Error at download_email.Download.update_gui : {}".format(e))

    def cancel(self):
        var.stop_download = True
        self.dialog.accept()
