import var
from var import logger
import os
import time
import traceback
import requests
import subprocess
from zipfile import ZipFile


class UpdateHandler:

    def __init__(self, name, link, size):
        self.file_path = var.update_temp_path
        self.link = link
        self.name = name
        self.size = size

    def download(self):
        try:
            logger.info("Internal Process: Update downloading process starting.")
            headers = {"user-agent": "Wget/1.16 (linux-gnu)"}
            filepath = "{}/GMonster{}.zip".format(self.file_path, self.name)
            temp_path = f"{self.file_path}"
            if not os.path.exists(temp_path):
                os.makedirs(temp_path)
                logger.info("Internal Process: Created temp dir for extraction process")
            url = var.api + "verify/version/download/{}".format(self.name)
            response = requests.post(url, timeout=10)
            data = response.json()
            url = self.link
            r = requests.get(url, stream=True, headers=headers)
            downloaded = 0
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        downloaded += len(chunk)
                        f.write(chunk)
            logger.info("Internal Process: Update downloaded.")
            with ZipFile(filepath, "r") as zip_file:
                zip_file.extractall(path=temp_path)
            if os.name == "nt":
                subprocess.Popen([var.update_bat_file_path], shell=True)
                logger.info("Internal Process: Closing the application.")
                var.command_q.put("QtCore.QCoreApplication.quit()")
            else:
                logger.info("Internal Process: Update extracted. Auto-replace is only supported on Windows.")
        except:
            logger.info(
                "Error at UpdateHandler.download: {}".format(traceback.format_exc())
            )


def update_checker():
    while True:
        try:
            time.sleep(300)
            url = var.api + "verify/version/{}".format(var.version)
            response = requests.post(url, timeout=10)
            data = response.json()
            if data["update_needed"] and (not var.send_campaign_run_status):
                logger.info("Internal Process: Updates available.")
                update_handler = UpdateHandler(data["name"], data["link"], data["size"])
                update_handler.download()
            else:
                logger.info(
                    f"Internal Process, update_checker: campaign status - {var.send_campaign_run_status}"
                )
            logger.info("Internal Process: No updates available.")
        except:
            logger.info(
                "Internal Process, error at update_checker: {}".format(
                    traceback.format_exc()
                )
            )
