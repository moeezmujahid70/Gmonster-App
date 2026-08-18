import re
import socks
import random
import smtplib
import traceback
from proxy_smtplib import SMTP, SmtpProxy, SmtpProxySSL, Proxifier
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
                self.provider_config = var.mail_server[mail_vendor]
                self.smtp_server = self.provider_config["smtp"]["server"]
                self.smtp_port = self.provider_config["smtp"]["port"]
                self.smtp_require_ssl = self.provider_config["smtp"].get(
                    "require_ssl", False
                )
                self.proxy_fallback_direct = self.provider_config.get(
                    "proxy_fallback_direct", False
                )
        except:
            logger.error(f"SmtpBase error: {traceback.format_exc()}")
            raise
        if not hasattr(self, "smtp_require_ssl"):
            self.smtp_require_ssl = False
        if not hasattr(self, "proxy_fallback_direct"):
            self.proxy_fallback_direct = False

    def _open_smtp_server(self, use_proxy):
        if use_proxy:
            print("with_proxy")
            logger.info("send mail with proxy")
            if self.smtp_require_ssl:
                return SmtpProxySSL(
                    self.smtp_server,
                    self.smtp_port,
                    proxifier=Proxifier.get_proxifier(self.proxy),
                    local_hostname=self.local_hostname,
                    timeout=45,
                )
            return SmtpProxy(
                self.smtp_server,
                self.smtp_port,
                proxifier=Proxifier.get_proxifier(self.proxy),
                local_hostname=self.local_hostname,
                timeout=45,
            )

        logger.info("send mail without proxy")
        print("without_proxy")
        if self.smtp_require_ssl:
            return smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=45)
        return smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=45)

    def _login_server(self, use_proxy):
        server = self._open_smtp_server(use_proxy)
        server.ehlo()
        if not self.smtp_require_ssl:
            server.starttls()
            server.ehlo()
        server.login(self.user, self.passwd)
        return server

    def _login(self):
        try:
            if var.add_custom_hostname:
                self.local_hostname = (
                    f"{self.first_from_name}-{random.choice(var.hostname_list)}"
                )
            use_proxy = self.proxy_host != "" and var.proxy_on
            try:
                return self._login_server(use_proxy)
            except Exception as proxy_error:
                if use_proxy and self.proxy_fallback_direct:
                    logger.warning(
                        "SMTP proxy login failed for %s; retrying without proxy: %s",
                        self.user,
                        proxy_error.__class__.__name__,
                    )
                    return self._login_server(False)
                raise
        except Exception as e:
            logger.error(
                f"Error at {self.__class__.__name__}._login: {e}\n{traceback.format_exc()}"
            )
            raise
