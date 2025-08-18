import re
import socks
import random
import smtplib
import traceback
from proxy_smtplib import SMTP, SmtpProxy, Proxifier
from var import logger
import var


class SmtpBase:

    def __init__(self, **kwargs):
        super().__init__()
        self.proxy_host = kwargs["proxy_host"]
        self.proxy_port = kwargs["proxy_port"]
        self.proxy_user = kwargs["proxy_user"]
        self.proxy_pass = kwargs["proxy_pass"]
        self.proxy = {
            "useproxy": True,
            "server": kwargs["proxy_host"],
            "port": kwargs["proxy_port"],
            "type": "SOCKS5",
            "username": kwargs["proxy_user"],
            "password": kwargs["proxy_pass"],
        }
        self.proxy_type = socks.PROXY_TYPE_SOCKS5
        self.user = kwargs["user"]
        self.passwd = kwargs["password"]
        self.first_from_name = kwargs["FIRSTFROMNAME"]
        self.last_from_name = kwargs["LASTFROMNAME"]
        self.local_hostname = None
        try:
            regex = re.compile("(?<=@)(\\S+$)")
            if len(regex.findall(self.user)) > 0:
                mail_domain = regex.findall(self.user)[0]
                mail_vendor = mail_domain.split(".")[0]
                parts = mail_domain.split(".")
                if len(parts) > 2:
                    mail_vendor = ".".join(parts[:-1])
                elif len(parts) == 2:
                    mail_vendor = parts[0]
                else:
                    mail_vendor = mail_domain
                self.smtp_server = var.mail_server[mail_vendor]["smtp"]["server"]
                self.smtp_port = var.mail_server[mail_vendor]["smtp"]["port"]
        except:
            logger.error(f"SmtpBase error: {traceback.format_exc()}")
            raise

    def _login(self):
        try:
            if var.add_custom_hostname:
                self.local_hostname = (
                    f"{self.first_from_name}-{random.choice(var.hostname_list)}"
                )
            if self.proxy_host != "" and var.proxy_on:
                print("with_proxy")
                logger.info("send mail with proxy")
                server = SmtpProxy(
                    self.smtp_server,
                    self.smtp_port,
                    proxifier=Proxifier.get_proxifier(self.proxy),
                    local_hostname=self.local_hostname,
                )
            else:
                logger.info("send mail without proxy")
                print("without_proxy")
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self.user, self.passwd)
            return server
        except Exception as e:
            logger.error(
                f"Error at {self.__class__.__name__}._login: {e}\n{traceback.format_exc()}"
            )
            raise
