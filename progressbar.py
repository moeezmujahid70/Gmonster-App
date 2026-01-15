from PyQt5 import QtCore, QtGui, QtWidgets
from threading import Thread
import var
from var import logger
from p_gui import Ui_Dialog
import os
import requests
import sys
import time
import shutil
import subprocess
import traceback
from PyQt5.QtCore import pyqtSignal, QObject
from zipfile import ZipFile

cancel = False
total_email_count = 0
delete_status = False


class Communicate(QObject):
    s = pyqtSignal(int, str)


class Download(Ui_Dialog):

    def __init__(self, dialog, name, link, size):
        Ui_Dialog.__init__(self)
        self.setupUi(dialog)
        self.dialog = dialog
        set_icon(self.dialog)
        self.signal = Communicate()
        self.signal.s.connect(self.update_gui)
        self.name = name
        self.link = link
        self.size = size
        self.size_in_kb = int(round(size / 1024))
        self.file_path = var.update_temp_path
        self.pushButton_cancel.clicked.connect(self.cancel)
        self.label_status.setText("Dowloaded  {} of {} kb".format(0, self.size_in_kb))
        Thread(target=self.download, daemon=True).start()

    def update_gui(self, dowloaded, message):
        if message != "":
            self.label_status.setText(message)
            self.pushButton_cancel.setText("Close")
        else:
            self.label_status.setText(
                "Dowloaded  {} of {} kb".format(dowloaded, self.size_in_kb)
            )
            value = dowloaded / self.size_in_kb * 100
            self.progressBar.setValue(value)

    def cancel(self):
        global cancel
        cancel = True
        self.dialog.accept()

    def download(self):
        try:
            headers = {"user-agent": "Wget/1.16 (linux-gnu)"}
            filepath = "{}/GMonster{}.zip".format(self.file_path, self.name)
            temp_path = f"{self.file_path}"
            if not os.path.exists(temp_path):
                os.makedirs(temp_path)
                logger.info("Created temp dir for extraction process")
            url = var.api + "verify/version/download/{}".format(self.name)
            response = requests.post(url, timeout=10)
            data = response.json()
            url = self.link
            r = requests.get(url, stream=True, headers=headers)
            downloaded = 0
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        if cancel:
                            break
                        downloaded += len(chunk)
                        print("Dowloaded {}/{}".format(downloaded, self.size), end="\r")
                        self.signal.s.emit(int(round(downloaded / 1024)), "")
                        f.write(chunk)
            logger.info("Update downloaded")
            self.signal.s.emit(int(round(downloaded / 1024)), "Download Finished")
            with ZipFile(filepath, "r") as zip_file:
                zip_file.extractall(path=temp_path)
            subprocess.Popen([var.update_bat_file_path], shell=True)
            logger.info("Closing the application.")
            QtCore.QCoreApplication.quit()
        except:
            logger.info("Error at download update: {}".format(traceback.format_exc()))


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


class DeleteEmail(Ui_Dialog):

    def __init__(self, dialog):
        global delete_status
        delete_status = True
        Ui_Dialog.__init__(self)
        self.setupUi(dialog)
        self.dialog = dialog
        set_icon(self.dialog)
        self.timer = QtCore.QTimer()
        self.timer.setInterval(10)
        self.timer.timeout.connect(self.progressbar)
        self.pushButton_cancel.clicked.connect(self.cancel_delete)
        Thread(target=thread_starter, daemon=True).start()
        self.timer.start()

    def cancel_delete(self):
        var.stop_delete = True
        self.timer.stop()
        self.dialog.accept()

    def progressbar(self):
        if total_email_count != 0 and delete_status == True:
            value = int(var.delete_email_count / total_email_count * 100)
            self.label_status.setText(
                "Deleted : {}/{}".format(var.delete_email_count, total_email_count)
            )
            self.progressBar.setValue(value)
        elif not delete_status:
            value = int(var.delete_email_count / total_email_count * 100)
            self.label_status.setText(
                "Deleting Finished : {}/{}".format(
                    var.delete_email_count, total_email_count
                )
            )
            self.progressBar.setValue(value)
            self.pushButton_cancel.setText("Close")
        else:
            self.label_status.setText("Preparing for deleting ...")


def thread_starter():
    global delete_status
    global total_email_count
    temp_df = var.inbox_data[var.inbox_group].copy()
    temp_df = temp_df.loc[temp_df["checkbox_status"] == 1]
    total_email_count = len(temp_df)
    temp_df = temp_df.groupby("user")
    var.delete_email_count = 0
    var.stop_delete = False
    from imap import ImapDeleteEmail

    for group_name, df_group in temp_df:
        if var.stop_delete:
            break
        while var.thread_open >= var.limit_of_thread and var.stop_delete == False:
            time.sleep(1)
        delete_email = ImapDeleteEmail(df_group)
        delete_email.start()
    while var.thread_open != 0 and (not var.stop_delete):
        time.sleep(1)

    # for row_index, row in var.inbox_data[var.inbox_group].iterrows():
    #     var.email_q.put(row.to_dict().copy())

    var.inbox_data[var.inbox_group]["checkbox_status"] = 0
    delete_status = False
    logger.info("deleting finished")
