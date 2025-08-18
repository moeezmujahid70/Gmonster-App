from PyQt5 import QtCore, QtGui
from threading import Thread
import var
from p_gui import Ui_Dialog
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
        self.timer = QtCore.QTimer()
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.update_gui)
        from imap import main

        Thread(target=main, daemon=True, args=[group, folders, var.date]).start()
        self.timer.start()

    def update_gui(self):
        try:
            if var.download_email_status:
                self.label_status.setText(
                    f"Total Email Downloaded : {var.total_email_downloaded}"
                )
            else:
                self.label_status.setText(
                    f"Total Email Downloaded : {var.total_email_downloaded} Accounts failed : {var.email_failed}"
                )
                self.pushButton_cancel.setText("Close")
            value = var.acc_finished / var.total_acc * 100
            self.progressBar.setValue(value)
        except Exception as e:
            print("Error at download_email.Download.update_gui : {}".format(e))

    def cancel(self):
        var.stop_download = True
        self.dialog.accept()
