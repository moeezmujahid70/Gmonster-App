import queue
import threading
import traceback
import smtplib
import random
import time
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from pathlib import Path
from datetime import datetime
import utils
from proxy_smtplib import SMTP
from smtp_base import SmtpBase
from var import logger
import var
from unsubscribe_email import compose_alternatives


class FollowUpSend(SmtpBase, threading.Thread):
    thread_open = 0
    stop_follow_up = False
    send_report = queue.Queue()
    email_to_be_sent = int()
    email_sent = int()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.threadID = kwargs["user"]
        self.name = kwargs["user"]
        self.setDaemon(True)
        self.target_info = kwargs["target_info"]
        self.delay_start = kwargs["delay_start"]
        self.delay_end = kwargs["delay_end"]
        self.attachment_files = kwargs["attachment_files"]
        self.campaign_id = kwargs["campaign_id"]

    def run(self) -> None:
        try:
            from smtp import html_to_text

            logger.info(f"Starting {self.__class__.__name__}: {self.user}")
            FollowUpSend.thread_open += 1

            t_part = []
            for path in self.attachment_files:
                part = MIMEBase("application", "octet-stream")
                with open(path, "rb") as file:
                    part.set_payload(file.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    'attachment; filename="{}"'.format(Path(path).name),
                )
                t_part.append(part)

            for item in self.target_info:
                self.sleep()
                if FollowUpSend.stop_follow_up:
                    break

                server = self._login()
                msg = MIMEMultipart("alternative")
                msg["Subject"] = utils.format_email(
                    var.followup_subject,
                    self.first_from_name,
                    self.last_from_name,
                    item["1"],
                    item["2"],
                    item["3"],
                    item["4"],
                    item["5"],
                    item["6"],
                    item["TONAME"],
                )
                msg["From"] = formataddr(
                    (
                        str(
                            Header(
                                "{} {}".format(
                                    self.first_from_name, self.last_from_name
                                ),
                                "utf-8",
                            )
                        ),
                        self.user,
                    )
                )
                msg["To"] = item["target_email"]
                msg["Date"] = formatdate(localtime=True)

                body = utils.format_email(
                    var.followup_body,
                    self.first_from_name,
                    self.last_from_name,
                    item["1"],
                    item["2"],
                    item["3"],
                    item["4"],
                    item["5"],
                    item["6"],
                    item["TONAME"],
                    source="body",
                )
                plain_body, html_body = compose_alternatives(
                    html_to_text(body),
                    body,
                    item.get("unsubscribe_url", ""),
                    bool(item.get("unsubscribe_enabled", False)),
                )
                msg.attach(MIMEText(plain_body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))

                for part in t_part:
                    msg.attach(part)

                for counter in range(0, 3):
                    try:
                        server.sendmail(
                            self.user, item["target_email"], msg.as_string()
                        )
                        FollowUpSend.email_sent += 1
                        var.command_q.put(
                            f"GUI.progressBar_compose.setValue({FollowUpSend.email_sent / FollowUpSend.email_to_be_sent * 100})"
                        )
                        break
                    except Exception as e:
                        if counter == 2:
                            raise
                        time.sleep(random.randint(10, 100))
                        logger.error(
                            f"{self.__class__.__name__} Reconnecting {counter} - {self.name} : {e}"
                        )
                        try:
                            server = self._login()
                        except:
                            pass

                report = {
                    "TARGET": item["target_email"],
                    "FROMEMAIL": self.user,
                    "STATUS": "sent",
                    "CAMPAIGN": self.campaign_id,
                    "DATE": str(datetime.today().date()),
                }
                FollowUpSend.send_report.put(report.copy())

            logger.info(f"Exiting {self.__class__.__name__}: {self.user}")

        except Exception as e:
            logger.error(
                f"Error at {self.__class__.__name__} {self.user}: {e}\n{traceback.format_exc()}"
            )
        finally:
            FollowUpSend.thread_open -= 1

    def sleep(self):
        duration = random.randint(self.delay_start, self.delay_end)
        count = 0
        while not self.stop_follow_up:
            time.sleep(1)
            count += 1
            if count >= duration:
                break
