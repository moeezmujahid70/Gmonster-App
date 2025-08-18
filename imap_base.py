import var
import re
import socks
import traceback
import imaplib
import proxy_imaplib
from var import logger


class ImapBase:

    def __init__(self, **kwargs):
        super().__init__()
        self.proxy_host = kwargs["proxy_host"]
        self.proxy_port = kwargs["proxy_port"]
        self.proxy_type = socks.PROXY_TYPE_SOCKS5
        self.proxy_user = kwargs["proxy_user"]
        self.proxy_pass = kwargs["proxy_pass"]
        self.imap_user = kwargs["user"]
        self.imap_pass = kwargs["password"]
        self.logger = logger
        try:
            regex = re.compile("(?<=@)(\\S+$)")
            if len(regex.findall(self.imap_user)) > 0:
                mail_domain = regex.findall(self.imap_user)[0]
                mail_vendor = mail_domain.split(".")[0]
                parts = mail_domain.split(".")
                if len(parts) > 2:
                    mail_vendor = ".".join(parts[:-1])
                elif len(parts) == 2:
                    mail_vendor = parts[0]
                else:
                    mail_vendor = mail_domain
                self.imap_server = var.mail_server[mail_vendor]["imap"]["server"]
                self.imap_port = var.mail_server[mail_vendor]["imap"]["port"]
        except:
            logger.error(f"ImapBase error: {traceback.format_exc()}")
            raise

    def _login(self):
        if self.proxy_host != "":
            server = proxy_imaplib.IMAP(
                proxy_host=self.proxy_host,
                proxy_port=self.proxy_port,
                proxy_type=self.proxy_type,
                proxy_user=self.proxy_user,
                proxy_pass=self.proxy_pass,
                host=self.imap_server,
                port=self.imap_port,
                timeout=30,
            )
        else:
            server = imaplib.IMAP4_SSL(self.imap_server)
        server.login(self.imap_user, self.imap_pass)
        return server
