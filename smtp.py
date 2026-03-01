import os
import pandas as pd
from followup_smtp import FollowUpSend
from proxy_smtplib import SMTP, SmtpProxy, Proxifier
from smtp_base import SmtpBase
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import socks
import threading
import time
import utils
import smtplib
import csv
import random
import json
import uuid
from pyairtable import Table
from pyairtable.formulas import match
from compat_ui import alert, password, confirm
from datetime import datetime, timedelta
from imap import ImapCheckForBlocks, ImapFollowUpCheck
from webhook import SendWebhook, CampaignReportWebhook
from main import GUI
from database import Database as DB
from database import db_to_pandas
from bs4 import BeautifulSoup
import traceback
import queue
import var
from var import logger

logger = logger
email_failed = 0
sent_q = queue.Queue()


def contains_non_ascii_characters(str):
    return not all((ord(c) < 128 for c in str))


def html_to_text(body):
    # soup = BeautifulSoup(body, features="html.parser")
    #
    # for script in soup(["script", "style"]):
    #     script.extract()
    #
    # text = soup.get_text()
    #
    # # break into lines and remove leading and trailing space on each
    # lines = (line.strip() for line in text.splitlines())
    # # break multi-headlines into a line each
    # chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    # # drop blank lines
    # text = '\n'.join(chunk for chunk in chunks if chunk)

    soup = BeautifulSoup(body, features="html.parser")
    return soup.get_text("\n")


class TestMail(SmtpBase):

    def __init__(self, send_to=None):
        if GUI.radioButton_campaign_group_a.isChecked():
            self.send_info = var.group_a.iloc[0].to_dict()
        else:
            self.send_info = var.group_b.iloc[0].to_dict()
        if self.send_info["PROXY:PORT"] != " ":
            proxy_host = self.send_info["PROXY:PORT"].split(":")[0]
            proxy_port = int(self.send_info["PROXY:PORT"].split(":")[1])
        else:
            proxy_host = ""
            proxy_port = ""
        kwargs = {
            "proxy_host": proxy_host,
            "proxy_port": proxy_port,
            "proxy_user": self.send_info["PROXY_USER"],
            "proxy_pass": self.send_info["PROXY_PASS"],
            "user": self.send_info["EMAIL"],
            "password": self.send_info["EMAIL_PASS"],
            "FIRSTFROMNAME": self.send_info["FIRSTFROMNAME"],
            "LASTFROMNAME": self.send_info["LASTFROMNAME"],
        }
        super().__init__(**kwargs)
        self.send_to = send_to
        self.target = var.target.iloc[0].to_dict()
        self.compose_email_subject = GUI.lineEdit_subject.text().strip()
        self.compose_email_body = GUI.textBrowser_compose.toPlainText().strip()

    def send(self):
        try:
            msg = MIMEMultipart("alternative")
            server = self._login()
            t_part = []
            for path in var.files:
                part = MIMEBase("application", "octet-stream")
                with open(path, "rb") as file:
                    part.set_payload(file.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    'attachment; filename="{}"'.format(Path(path).name),
                )
                t_part.append(part)
            msg["Subject"] = utils.format_email(
                self.compose_email_subject,
                self.first_from_name,
                self.last_from_name,
                self.target["1"],
                self.target["2"],
                self.target["3"],
                self.target["4"],
                self.target["5"],
                self.target["6"],
                self.target["TONAME"],
            )
            msg["From"] = formataddr(
                (
                    str(
                        Header(
                            "{} {}".format(self.first_from_name,
                                           self.last_from_name),
                            "utf-8",
                        )
                    ),
                    self.user,
                )
            )
            msg["To"] = self.send_to
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=self.user.split("@")[1])
            if var.body_type == "Html":
                body = utils.format_email(
                    var.compose_email_body_html,
                    self.first_from_name,
                    self.last_from_name,
                    self.target["1"],
                    self.target["2"],
                    self.target["3"],
                    self.target["4"],
                    self.target["5"],
                    self.target["6"],
                    self.target["TONAME"],
                    source="body",
                )
                html_part = MIMEText(body, "html")
                html_part["Content-Transfer-Encoding"] = "quoted-printable"
                msg.attach(html_part)
            else:
                body = utils.format_email(
                    var.compose_email_body,
                    self.first_from_name,
                    self.last_from_name,
                    self.target["1"],
                    self.target["2"],
                    self.target["3"],
                    self.target["4"],
                    self.target["5"],
                    self.target["6"],
                    self.target["TONAME"],
                )
                plain_part = MIMEText(body, "plain")
                plain_part["Content-Transfer-Encoding"] = "quoted-printable"
                msg.attach(plain_part)
                html_body = (
                    "<html><body><p>"
                    + body.replace("\n", "<br>")
                    + "</p></body></html>"
                )
                html_part = MIMEText(html_body, "html")
                html_part["Content-Transfer-Encoding"] = "quoted-printable"
                msg.attach(html_part)
            for part in t_part:
                msg.attach(part)
            server.sendmail(self.user, self.send_to, msg.as_string())
            server.quit()
            server.close()
            logger.info(
                f"Testing Done: send to - {self.send_to} sent_from - {self.user}"
            )
            return True
        except Exception as e:
            logger.error(
                "Error at test send - {} - {}".format(
                    self.user, traceback.format_exc())
            )
            return False


class ForwardMail(SmtpBase):

    def __init__(self, forward_to=None):
        kwargs = {
            "proxy_host": var.email_in_view["proxy_host"],
            "proxy_port": int(var.email_in_view["proxy_port"]),
            "proxy_user": var.email_in_view["proxy_user"],
            "proxy_pass": var.email_in_view["proxy_pass"],
            "user": var.email_in_view["user"],
            "password": var.email_in_view["pass"],
            "FIRSTFROMNAME": var.email_in_view["FIRSTFROMNAME"],
            "LASTFROMNAME": var.email_in_view["LASTFROMNAME"],
        }
        super().__init__(**kwargs)
        self.forward_to = forward_to
        self.from_mail = var.email_in_view["from"]
        self.to_mail = var.email_in_view["to_mail"]
        self.original_subject = var.email_in_view["original_subject"]
        self.original_body = var.email_in_view["original_body"]

    def send(self):
        try:
            msg = MIMEMultipart("alternative")
            server = self._login()
            msg["Subject"] = "Fwd: " + self.original_subject
            msg["From"] = formataddr(
                (
                    str(
                        Header(
                            "{} {}".format(self.first_from_name,
                                           self.last_from_name),
                            "utf-8",
                        )
                    ),
                    self.user,
                )
            )
            msg["To"] = self.forward_to
            send_to = self.forward_to
            if var.cc_emails_enabled:
                msg["Cc"] = var.cc_emails
                send_to = var.cc_emails.split(",") + [send_to]
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=self.user.split("@")[1])
            checked_emails = var.inbox_data[var.inbox_group].loc[var.inbox_data[var.inbox_group]
                                                                 ["checkbox_status"] == 1]
            if checked_emails.empty:
                logger.warning("No emails selected for forwarding.")
                return False
            forwarded_messages = []
            for _, row in checked_emails.iterrows():
                forwarded_message = f"                ---------- Forwarded message ---------\n                From: {row['from_name']} <{row['from_mail']}>\n                Date: {row['date']}\n                Subject: {row['subject']}\n                To: {row['to_mail']}\n\n                {row['body']}\n                "
                forwarded_messages.append(forwarded_message)
            combined_message = "\n\n".join(forwarded_messages)
            plain_part = MIMEText(combined_message, "plain")
            plain_part["Content-Transfer-Encoding"] = "quoted-printable"
            msg.attach(plain_part)
            html_body = (
                "<html><body><p>"
                + combined_message.replace("\n", "<br>")
                + "</p></body></html>"
            )
            html_part = MIMEText(html_body, "html")
            html_part["Content-Transfer-Encoding"] = "quoted-printable"
            msg.attach(html_part)
            server.sendmail(self.user, send_to, msg.as_string())
            server.quit()
            server.close()
            logger.info(
                f"Forwarded {len(checked_emails)} emails to {self.forward_to}")
            return True
        except Exception as e:
            logger.error(
                "Error at forward - {} - {}".format(
                    self.user, traceback.format_exc())
            )
            return False


class ReplyMail(SmtpBase):

    def __init__(self):
        kwargs = {
            "proxy_host": var.email_in_view["proxy_host"],
            "proxy_port": int(var.email_in_view["proxy_port"]),
            "proxy_user": var.email_in_view["proxy_user"],
            "proxy_pass": var.email_in_view["proxy_pass"],
            "user": var.email_in_view["user"],
            "password": var.email_in_view["pass"],
            "FIRSTFROMNAME": var.email_in_view["FIRSTFROMNAME"],
            "LASTFROMNAME": var.email_in_view["LASTFROMNAME"],
        }
        super().__init__(**kwargs)
        self.from_name = var.email_in_view["from_name"]
        self.subject = var.email_in_view["subject"]
        self.from_mail = var.email_in_view["from_mail"]
        self.mail_body = var.email_in_view["body"]
        self.msg_id = var.email_in_view["message-id"]

    def send(self):
        try:
            send_to = self.from_mail
            msg = MIMEMultipart("alternative")
            server = self._login()
            toname = self.from_name
            msg["Subject"] = utils.format_email(
                self.subject,
                self.first_from_name,
                self.last_from_name,
                "",
                "",
                "",
                "",
                "",
                "",
                toname,
            )
            msg["From"] = formataddr(
                (
                    str(
                        Header(
                            "{} {}".format(self.first_from_name,
                                           self.last_from_name),
                            "utf-8",
                        )
                    ),
                    self.user,
                )
            )
            msg["To"] = self.from_mail
            if var.cc_emails_enabled:
                msg["Cc"] = var.cc_emails
                send_to = var.cc_emails.split(",") + [send_to]
            msg["Date"] = formatdate(localtime=True)
            msg["Message-ID"] = make_msgid(domain=self.user.split("@")[1])
            body = utils.format_email(
                self.mail_body,
                self.first_from_name,
                self.last_from_name,
                "",
                "",
                "",
                "",
                "",
                "",
                toname,
                source="body",
            )
            if var.body_type == "Html":
                html_part = MIMEText(body, "html")
                html_part["Content-Transfer-Encoding"] = "quoted-printable"
                msg.attach(html_part)
            else:
                plain_part = MIMEText(body, "plain")
                plain_part["Content-Transfer-Encoding"] = "quoted-printable"
                msg.attach(plain_part)
                html_body = (
                    "<html><body><p>"
                    + body.replace("\n", "<br>")
                    + "</p></body></html>"
                )
                html_part = MIMEText(html_body, "html")
                html_part["Content-Transfer-Encoding"] = "quoted-printable"
                msg.attach(html_part)
            msg.add_header("In-Reply-To", self.msg_id)
            msg.add_header("References", self.msg_id)
            for path in var.reply_files:
                part = MIMEBase("application", "octet-stream")
                with open(path, "rb") as file:
                    part.set_payload(file.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    'attachment; filename="{}"'.format(Path(path).name),
                )
                msg.attach(part)
            server.sendmail(self.user, send_to, msg.as_string())
            server.quit()
            server.close()
            logger.info(f"Replied to {self.from_mail}")
            return True
        except Exception as e:
            logger.error(
                "Error at replying - {} - {}".format(
                    self.user, traceback.format_exc())
            )
            return False


class Smtp(SmtpBase, threading.Thread):
    followup_queue = queue.Queue()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.threadID = kwargs["index"]
        self.name = kwargs["name"]
        self.setDaemon(True)
        self.target = kwargs["target"]
        self.logger = logger
        self.d_start = kwargs["d_start"]
        self.d_end = kwargs["d_end"]
        self.campaign_id = kwargs["campaign_id"]
        self.local_hostname = None
        self.followup_enabled = kwargs["followup_enabled"]
        self.logger.info(
            "SMTP thread starting: Length - {} {}".format(
                len(self.target), self.user)
        )

    def _login(self):
        try:
            if var.add_custom_hostname:
                self.local_hostname = (
                    f"{self.first_from_name.lower()}-{random.choice(var.hostname_list)}"
                )
            if self.proxy_host != "" and var.proxy_on:
                logger.info("send mail with proxy")
                print("send mail with proxy")
                server = SmtpProxy(
                    self.smtp_server,
                    self.smtp_port,
                    proxifier=Proxifier.get_proxifier(self.proxy),
                    local_hostname=self.local_hostname,
                )
            else:
                logger.info("send mail without proxy")
                print("send mail without proxy")
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.set_debuglevel(0)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self.user, self.passwd)
            return server
        except Exception as e:
            logger.info(
                f"Error at SMTP_.login {self.name} : {e.__class__.__name__} : {str(e)}"
            )
            if var.enable_webhook_status:
                t_dict = {
                    "sender": self.user,
                    "sender_name": f"{self.first_from_name} {self.last_from_name}",
                    "time": datetime.utcnow().strftime("%m/%d/%Y %H:%M:%S"),
                    "error_details": f"{e.__class__.__name__} : {str(e)}",
                }
                var.webhook_q.put(t_dict.copy())
            raise

    def sleep(self):
        duration = random.randint(self.d_start, self.d_end)
        count = 0
        while not var.stop_send_campaign:
            time.sleep(1)
            count += 1
            if count >= duration:
                break

    def run(self):
        global email_failed
        try:
            last_recipient = ""
            var.thread_open_campaign += 1
            t_part = []
            for path in var.files:
                part = MIMEBase("application", "octet-stream")
                with open(path, "rb") as file:
                    part.set_payload(file.read())
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    'attachment; filename="{}"'.format(Path(path).name),
                )
                t_part.append(part)
            count = 0
            for index, item in self.target.iterrows():
                self.sleep()
                if var.stop_send_campaign:
                    break
                server = self._login()
                msg = MIMEMultipart("alternative")
                msg["Subject"] = utils.format_email(
                    var.compose_email_subject,
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
                msg["To"] = item["EMAIL"]
                last_recipient = item["EMAIL"]
                msg["Date"] = formatdate(localtime=True)
                msg["Message-ID"] = make_msgid(domain=self.user.split("@")[1])
                if var.body_type == "Html":
                    body = utils.format_email(
                        var.compose_email_body_html,
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
                    html_part = MIMEText(body, "html")
                    html_part["Content-Transfer-Encoding"] = "quoted-printable"
                    msg.attach(html_part)
                else:
                    body = utils.format_email(
                        var.compose_email_body,
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
                    plain_part = MIMEText(body, "plain")
                    plain_part["Content-Transfer-Encoding"] = "quoted-printable"
                    msg.attach(plain_part)
                    html_body = (
                        "<html><body><p>"
                        + body.replace("\n", "<br>")
                        + "</p></body></html>"
                    )
                    html_part = MIMEText(html_body, "html")
                    html_part["Content-Transfer-Encoding"] = "quoted-printable"
                    msg.attach(html_part)
                for part in t_part:
                    msg.attach(part)
                if count == 1:
                    first_time = datetime.now()
                if var.stop_send_campaign:
                    break
                for counter in range(0, 3):
                    try:
                        server.sendmail(
                            self.user, item["EMAIL"], msg.as_string())
                        break
                    except:
                        if counter == 2:
                            raise
                        time.sleep(random.randint(10, 100))
                        logger.warning(
                            "Reconnecting smtp - {}".format(self.name))
                        try:
                            server = self._login()
                        except:
                            pass
                AddCachedTargets.targets_q.put(item["EMAIL"])
                self.logger.info(f"Sent - {self.user} {item['EMAIL']}")
                sent_q.put((item["EMAIL"], index))
                var.send_campaign_email_count += 1
                count += 1
                t_dict = {
                    "TARGET": item["EMAIL"],
                    "FROMEMAIL": self.user,
                    "STATUS": "sent",
                    "CAMPAIGN": self.campaign_id,
                    "DATE": str(datetime.today().date()),
                }
                var.send_report.put(t_dict.copy())
                if self.followup_enabled:
                    target_info = item.to_dict()
                    target_info["target_email"] = target_info.pop("EMAIL")
                    target_info["email_subject"] = msg["Subject"]
                    Smtp.followup_queue.put(
                        {
                            "group_email": self.user,
                            "group_info": {
                                "proxy_host": self.proxy_host,
                                "proxy_port": self.proxy_port,
                                "proxy_user": self.proxy_user,
                                "proxy_pass": self.proxy_pass,
                                "user": self.user,
                                "password": self.passwd,
                                "proxy_type": socks.PROXY_TYPE_SOCKS5,
                                "FIRSTFROMNAME": self.first_from_name,
                                "LASTFROMNAME": self.last_from_name,
                            },
                            "target_email": item["EMAIL"],
                            "target_info": target_info,
                            "campaign_id": self.campaign_id,
                        }
                    )
                if var.enable_webhook_status:
                    t_dict = {
                        "target": item["EMAIL"],
                        "sender": self.user,
                        "sender_name": f"{self.first_from_name} {self.last_from_name}",
                        "time": datetime.utcnow().strftime("%m/%d/%Y %H:%M:%S"),
                        "subject": msg["Subject"],
                        "body": body,
                    }
                    var.webhook_q.put(t_dict.copy())
                var.command_q.put("self.update_compose_progressbar()")
                if var.remove_email_from_target:
                    RemoveTarget.remove_target_q.put(item["ID"])
                if var.AirtableConfig.mark_sent_airtable:
                    MarkTargetSentAirtable.airtable_target_q.put(item["EMAIL"])
                if count % 5 == 0 and var.check_for_blocks:
                    last_time = datetime.now()
                    elapsed_time = utils.difference_between_time(
                        first_time, last_time
                    )
                    imap_check = ImapCheckForBlocks(
                        time_limit=elapsed_time,
                        proxy_host=self.proxy_host,
                        proxy_port=self.proxy_port,
                        proxy_user=self.proxy_user,
                        proxy_pass=self.proxy_pass,
                        user=self.user,
                        password=self.passwd,
                    )
                    if imap_check.check_for_block_messages():
                        self.logger.error(
                            f"Found block messages : {self.name} {str(datetime.now())}"
                        )
                        break
                    else:
                        self.logger.error(
                            f"Found no block messages : {self.name}")
                        # self.logger.error(
                        #     f"Found no block messages : {self.name} {str(datetime.now())}")

                    # this is where you might want to anything that you want every campaign threads to do

                server.quit()
        except Exception as e:
            email_failed += 1
            self.logger.error(
                "Error at Sending - {} - {}".format(
                    self.name, traceback.format_exc())
            )
            t_dict = {
                "TARGET": last_recipient,
                "FROMEMAIL": self.user,
                "STATUS": str(e),
                "CAMPAIGN": self.campaign_id,
                "DATE": str(datetime.today().date()),
            }
            var.send_report.put(t_dict.copy())
        finally:
            server = None
            var.thread_open_campaign -= 1


class MarkTargetSentAirtable(threading.Thread):
    airtable_target_q = queue.Queue()

    def __init__(self):
        super().__init__()
        self.threadID = "MarkTargetAsSent01"
        self.name = "MarkTargetAsSent"
        self.setDaemon(True)
        self._close = False
        self.config = var.AirtableConfig
        self.table = Table(
            self.config.api_key, self.config.base_id, self.config.table_name
        )

    def run(self):
        logger.info(f"Starting {self.__class__.__name__}...")
        list_of_email = []
        while not self.close:
            try:
                if not MarkTargetSentAirtable.airtable_target_q.empty():
                    email = MarkTargetSentAirtable.airtable_target_q.get()
                    list_of_email.append(email)
                elif len(list_of_email) > 0:
                    if var.AirtableConfig.use_desktop_id:
                        formula = self.formulas_with_desktop_id(list_of_email)
                    else:
                        formula = self.formulas_normal(list_of_email)
                    list_of_email = []
                    try:
                        results = self.table.all(formula=formula)
                    except Exception as e:
                        logger.error(
                            f"Error at {self.__class__.__name__} : "
                            + f"formula - {formula} | {traceback.format_exc()}"
                        )
                        raise
                    update_dict_list = []
                    if len(results) > 0:
                        for item in results:
                            item["fields"]["has_sent_email"] = 1
                            update_dict_list.append(item)
                        self.table.batch_update(update_dict_list)
            except Exception as e:
                logger.error(
                    f"Error at {self.__class__.__name__} : {traceback.format_exc()}"
                )
            time.sleep(1)
        else:
            logger.info(f"Completed {self.__class__.__name__}...")

    def formulas_with_desktop_id(self, list_of_email):
        logger.info(f"formulas_with_desktop_id {self.__class__.__name__}...")

        formula = (
            "AND(OR("
            + ",".join([f"{{EMAIL}}='{item}'" for item in list_of_email])
            + f", {{desktop_app_id}}='{var.gmonster_desktop_id}', {{has_sent_email}}=0))"
        )

        return formula

    def formulas_normal(self, list_of_email):
        logger.info(f"formulas_normal {self.__class__.__name__}...")

        formula = (
            "AND(OR("
            + ",".join([f"{{EMAIL}}='{item}'" for item in list_of_email])
            + f", {{has_sent_email}}=0))"
        )

        return formula

    @property
    def close(self) -> bool:
        return self._close

    @close.setter
    def close(self, value: bool):
        self._close = value


class RemoveTarget(threading.Thread):
    remove_target_q = queue.Queue()

    def __init__(self):
        super().__init__()
        self.threadID = "RemoveTarget01"
        self.name = "RemoveTarget"
        self.setDaemon(True)
        self.close = False
        self.target = DB()

    def run(self):
        while not self.close:
            try:
                if not RemoveTarget.remove_target_q.empty():
                    _id = RemoveTarget.remove_target_q.get()
                    result = self.target.remove(table="targets", id=_id)
            except Exception as e:
                logger.error(
                    f"Error at remove_target_from_database : {traceback.format_exc()}"
                )
            time.sleep(1)
        logger.info("Remove target thread class terminating")

    def stop(self):
        self.close = True


class AddCachedTargets(threading.Thread):
    targets_q = queue.Queue()

    def __init__(self):
        super().__init__()
        self.threadID = "AddCachedTargets"
        self.name = "AddCachedTargets"
        self.setDaemon(True)
        self._close = False
        self.db = DB()

    def run(self) -> None:
        while not self._close:
            try:
                if not AddCachedTargets.targets_q.empty():
                    email = AddCachedTargets.targets_q.get()
                    self.db.add_to_cached_targets(email)
            except Exception as e:
                logger.error(
                    f"Error at AddCachedTargets : {traceback.format_exc()}")
            time.sleep(1)
        logger.info("AddCachedTargets thread class terminating")

    @property
    def close(self):
        return self._close

    @close.setter
    def close(self, value):
        self._close = value


class AddFollowUps:

    def __init__(self, followup_queue: queue.Queue, campaign_time: datetime):
        self.db = DB()
        self.followup_queue = followup_queue
        self.campaign_time = campaign_time

    def send(self) -> None:
        logger.info(f"{self.__class__.__name__} starting...")
        followups = []
        while not self.followup_queue.empty():
            followup = self.followup_queue.get()
            followup["campaign_time"] = self.campaign_time
            followups.append(followup.copy())
        result = self.db.add_follow_up(followups)
        if result:
            logger.info(f"{self.__class__.__name__} successful")
        else:
            logger.info(f"{self.__class__.__name__} unsuccessful")


def main(group, d_start, d_end, group_selected, num_emails_per_address_range):
    global sent_q, email_failed, remove_target_q
    try:

        var.command_q.put("self.compose_config_visibility(on=False)")
        var.command_q.put("self.update_compose_progressbar()")

        email_failed = 0
        sent_q = queue.Queue()
        target = var.target.copy()
        # it removes the rows that doesn't any email address
        target = target[target["EMAIL"] != ""]

        # Filter targets upfront to be unique by EMAIL
        original_count = len(target)
        target = target.drop_duplicates(subset=['EMAIL'], keep='first')
        unique_count = len(target)
        logger.info(
            f"Target filtering: {original_count} -> {unique_count} (removed {original_count - unique_count} duplicates)")

        target.insert(9, "flag", "")
        target["flag"] = 0
        group.insert(8, "flag", "")
        group["flag"] = 0
        target_len = len(target)
        group_len = len(group)
        campaign_id = str(uuid.uuid4())

        # Pre-calculate num_emails_per_address for all workers upfront
        worker_email_counts = {}
        total_emails_to_be_sent = 0
        for index, item in group.iterrows():
            emails_to_be_sent = random.randint(
                num_emails_per_address_range["start"],
                num_emails_per_address_range["end"],
            )
            worker_email_counts[index] = emails_to_be_sent
            total_emails_to_be_sent += emails_to_be_sent
        var.total_email_to_be_sent = min(total_emails_to_be_sent, target_len)

        logger.info(
            f"\n Starting Send Campaign : "
            + f"\n Target Removal - {var.remove_email_from_target}"
            + f"\n Group Selected: {group_selected}"
            + f"\n Webhook Enabled: {var.enable_webhook_status}"
            + f"\n Email Block Check: {var.check_for_blocks}"
            + f"\n Emails Per Account: {var.num_emails_per_address}"
            + f"\n Len of Group: {group_len}"
            + f"\n Len of Targets: {target_len}"
            + f"\n Delay: {d_start} - {d_end}"
            + f"\n Campaign ID: {campaign_id}"
            + f"\n Add Custom Hostname: {var.add_custom_hostname}"
        )

        with var.send_report.mutex:
            var.send_report.queue.clear()
        with var.webhook_q.mutex:
            var.webhook_q.queue.clear()
        if var.enable_webhook_status:
            webhook = SendWebhook()
            webhook.start()
        with RemoveTarget.remove_target_q.mutex:
            RemoveTarget.remove_target_q.queue.clear()
        if var.remove_email_from_target:
            remove_target = RemoveTarget()
            remove_target.start()
        MarkTargetSentAirtable.airtable_target_q = queue.Queue()
        if var.AirtableConfig.mark_sent_airtable:
            mark_target_sent_airtable = MarkTargetSentAirtable()
            mark_target_sent_airtable.start()
        with AddCachedTargets.targets_q.mutex:
            AddCachedTargets.targets_q.queue.clear()
        add_cached_targets = AddCachedTargets()
        add_cached_targets.start()
        followup_enabled = var.followup_enabled
        campaign_time = datetime.utcnow()
        with Smtp.followup_queue.mutex:
            Smtp.followup_queue.queue.clear()
        while (
            var.send_campaign_email_count < target_len
            and group["flag"].sum() < group_len
        ):
            target = target[target["flag"] == 0]
            target = target.reset_index(drop=True)
            e_target_len = len(target)
            temp = 0
            end = 0
            if var.stop_send_campaign:
                break
            for index, item in group.loc[group["flag"] == 0].iterrows():
                try:
                    if var.stop_send_campaign or temp > e_target_len - 1:
                        break

                    user = item["EMAIL"]
                    name = item["EMAIL"]

                    if item["PROXY:PORT"] != " ":
                        proxy_host = item["PROXY:PORT"].split(":")[0]
                        proxy_port = int(item["PROXY:PORT"].split(":")[1])
                    else:
                        proxy_host = ""
                        proxy_port = ""

                    # Use pre-calculated value instead of calculating in loop
                    num_emails_per_address = worker_email_counts[index]
                    start = temp
                    end = start + num_emails_per_address - 1
                    temp = end + 1
                    group.at[index, "flag"] = 1

                    logger.info(
                        f"\nStarting Thread : Name - {name}"
                        f"\nTargets Count - {len(target.loc[start:end])}"
                    )
                    # + f"\nTargets - {json.dumps(target.loc[start:end].to_dict())}")

                    kwargs = {
                        "index": index,
                        "name": item["EMAIL"],
                        "proxy_host": proxy_host,
                        "proxy_port": proxy_port,
                        "proxy_user": item["PROXY_USER"],
                        "proxy_pass": item["PROXY_PASS"],
                        "user": item["EMAIL"],
                        "password": item["EMAIL_PASS"],
                        "FIRSTFROMNAME": item["FIRSTFROMNAME"],
                        "LASTFROMNAME": item["LASTFROMNAME"],
                        "target": target.loc[start:end].copy(),
                        "d_start": d_start,
                        "d_end": d_end,
                        "campaign_id": campaign_id,
                        "followup_enabled": followup_enabled,
                    }

                    Smtp(**kwargs).start()

                    logger.info(
                        f"{name} set to sent {num_emails_per_address} emails")

                    while (
                        var.thread_open_campaign >= var.limit_of_thread
                        and not var.stop_send_campaign
                    ):
                        time.sleep(1)
                except:
                    logger.error(
                        f"Error at smtp thread opening {campaign_id} - {user} - {traceback.format_exc()}"
                    )

            while var.thread_open_campaign != 0 and not var.stop_send_campaign:
                time.sleep(1)
            while not sent_q.empty():
                temp = sent_q.get()
                email, index = temp[0], temp[1]
                target.at[index, 'flag'] = 1

        # while var.thread_open_campaign != 0 and var.stop_send_campaign == False:
        #     time.sleep(1)

        # wait for all thread to be closed
        while var.thread_open_campaign != 0:
            time.sleep(1)

        # wait for webhook queue to be emptied
        if var.enable_webhook_status:
            time.sleep(2)
            while not var.webhook_q.empty():
                time.sleep(1)
            webhook.quit()
        save_report()
        if var.remove_email_from_target:
            logger.info("removing email from target...")
            while not RemoveTarget.remove_target_q.empty():
                time.sleep(1)
            remove_target.stop()
            db_to_pandas(group_a=False, group_b=False, target=True)
            var.command_q.put("self.update_db_table()")
        if var.AirtableConfig.mark_sent_airtable:
            logger.info("Marking target as sent...")
            while not MarkTargetSentAirtable.airtable_target_q.empty():
                time.sleep(1)
            mark_target_sent_airtable.close = True
        while not AddCachedTargets.targets_q.empty():
            time.sleep(1)
        add_cached_targets.close = True

        if followup_enabled and not var.stop_send_campaign:
            add_follow_ups = AddFollowUps(Smtp.followup_queue, campaign_time)
            add_follow_ups.send()

            next_run_time = datetime.now() + timedelta(days=var.followup_days)
            var.scheduler.add_job(
                follow_up,
                "date",
                args=(campaign_id,),
                next_run_time=next_run_time,
                misfire_grace_time=None,
            )
            logger.info(f"FollowUp scheduled: {next_run_time} {campaign_id}")

        var.email_failed = email_failed
        if var.enable_webhook_status:
            campaign_report_webhook = CampaignReportWebhook(
                {
                    "total_emails_sent": var.send_campaign_email_count,
                    "accounts_failed": email_failed,
                    "targets_remaining": len(var.target),
                    "group": group_selected,
                    "registered_mail": var.login_email,
                }.copy()
            )

            campaign_report_webhook.start()
    except:
        logger.error(f"Error at smtp.main: {traceback.format_exc()}")

    finally:
        var.command_q.put("GUI.pushButton_send.setEnabled(True)")

        var.command_q.put("self.update_compose_progressbar()")
        var.command_q.put("GUI.pushButton_send.setText('Send \\nCampaign')")
        var.command_q.put("self.compose_config_visibility(on=True)")
        var.send_campaign_run_status = False

        logger.info(f"Sending Finished {campaign_id}")

        # Show different message based on whether campaign was stopped or completed
        if var.stop_send_campaign:
            alert_message = "Campaign Stopped!\nTotal Emails Sent : {}\nAccounts Failed : {}\nTargets Remaining : {}\ncheck app.log and report.csv".format(
                var.send_campaign_email_count, email_failed, len(var.target)
            )
            alert_title = "Campaign Stopped"
        else:
            alert_message = "Campaign Completed!\nTotal Emails Sent : {}\nAccounts Failed : {}\nTargets Remaining : {}\ncheck app.log and report.csv".format(
                var.send_campaign_email_count, email_failed, len(var.target)
            )
            alert_title = "Campaign Completed"

        alert(
            text=alert_message,
            title=alert_title,
            button="OK",
        )


def save_report():
    try:
        field_names = ["TARGET", "FROMEMAIL", "STATUS", "CAMPAIGN", "DATE"]
        with open(
            var.base_dir + "/report.csv", "a", newline="", encoding="utf-8"
        ) as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=field_names)
            writer.writeheader()
            while not var.send_report.empty():
                temp_dict = var.send_report.get()
                writer.writerow(temp_dict)
    except Exception as e:
        logger.error("Error while saving report - {}".format(e))


def follow_up(campaign_id: str):
    try:
        logger.info(f"Starting Followup process, Campaign ID - {campaign_id}")
        while var.send_campaign_run_status:
            time.sleep(var.waiting_period_for_followup)
            logger.info(
                f"Waiting to start Followup process because campaign is running, Campaign ID - {campaign_id}"
            )
        logger.info(
            f"Starting Followup process again, Campaign ID - {campaign_id}")
        var.command_q.put("GUI.progressBar_compose.setValue(0)")
        var.command_q.put("self.send_button_visibility(on=False)")
        var.command_q.put("self.compose_config_visibility(on=False)")
        var.command_q.put("GUI.label_compose_status.setText('Follow Up: 0/2')")
        ImapFollowUpCheck.followup_required = []
        ImapFollowUpCheck.thread_open = 0
        ImapFollowUpCheck.email_to_be_sent = 0
        FollowUpSend.thread_open = 0
        db = DB()
        followups = db.get_all_followup(campaign_id)
        if len(followups) > 0:
            followups_df = pd.DataFrame(followups)
            followup_group_df = followups_df.groupby("group_email")
            ImapFollowUpCheck.total_follow_up_checks = len(followup_group_df)
            for group_name, df_group in followup_group_df:
                groups_dict = df_group.to_dict("records")[0]
                groups_dict.update(groups_dict["group_info"])
                groups_dict.pop("group_info")
                groups_dict["target_info"] = []
                for row_index, row in df_group.iterrows():
                    groups_dict["target_info"] = groups_dict["target_info"] + [
                        row["target_info"].copy()
                    ]
                imap_followup_check_thread = ImapFollowUpCheck(**groups_dict)
                imap_followup_check_thread.start()
                time.sleep(5)
                while ImapFollowUpCheck.thread_open >= var.limit_of_thread:
                    time.sleep(1)
            while ImapFollowUpCheck.thread_open != 0:
                time.sleep(1)
            var.command_q.put(
                "GUI.label_compose_status.setText('Follow Up: 1/2')")
            followup_required = ImapFollowUpCheck.followup_required
            FollowUpSend.email_to_be_sent = ImapFollowUpCheck.email_to_be_sent
            if len(followup_required) > 0:
                logger.info(
                    f"follow_up, Campaign Id - {campaign_id}: {FollowUpSend.email_to_be_sent} email to be sent"
                )
                for item in followup_required:
                    item["delay_start"] = var.delay_start
                    item["delay_end"] = var.delay_end
                    item["attachment_files"] = var.files
                    item["campaign_id"] = campaign_id
                    follow_up_send = FollowUpSend(**item)
                    follow_up_send.start()
                    time.sleep(5)
                    while FollowUpSend.thread_open >= var.limit_of_thread:
                        time.sleep(1)
                while FollowUpSend.thread_open != 0:
                    time.sleep(1)
                try:
                    field_names = ["TARGET", "FROMEMAIL",
                                   "STATUS", "CAMPAIGN", "DATE"]
                    with open(
                        os.path.join(
                            os.getcwd(), var.base_dir, var.followup_report_file_path
                        ),
                        "a",
                        newline="",
                        encoding="utf-8",
                    ) as csvfile:
                        writer = csv.DictWriter(
                            csvfile, fieldnames=field_names)
                        writer.writeheader()
                        while not FollowUpSend.send_report.empty():
                            report = FollowUpSend.send_report.get()
                            writer.writerow(report)
                        logger.info(
                            f"Saving followup report, Campaign Id - {campaign_id}"
                        )
                except Exception as e:
                    logger.error(
                        f"Error at follow_up, Campaign Id - {campaign_id} - {e}\n{traceback.format_exc()}"
                    )
            else:
                logger.info(
                    f"No Followups required. Campaign Id - {campaign_id}")
        else:
            logger.info(
                f"No Followups entry found. Campaign Id - {campaign_id}")
        var.command_q.put(
            "GUI.label_compose_status.setText('Follow Up: 2/2 Done')")
    except Exception as e:
        logger.error(
            f"Error at follow_up, Campaign Id - {campaign_id}: {e}\n{traceback.format_exc()}"
        )
    finally:
        var.command_q.put("self.send_button_visibility(on=True)")
        var.command_q.put("self.compose_config_visibility(on=True)")
        logger.info(f"Finishing Followup process, Campaign Id - {campaign_id}")
