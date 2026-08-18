import var
import re
import socks
import traceback
import imaplib
import proxy_imaplib
from var import logger


class ImapBase:
    SENT_FOLDER_TOKEN = "__SENT__"

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
                self.mail_vendor = mail_vendor
                self.provider_config = var.mail_server[mail_vendor]
                self.imap_server = self.provider_config["imap"]["server"]
                self.imap_port = self.provider_config["imap"]["port"]
                self.proxy_fallback_direct = self.provider_config.get(
                    "proxy_fallback_direct", False
                )
        except:
            logger.error(f"ImapBase error: {traceback.format_exc()}")
            raise
        if not hasattr(self, "mail_vendor"):
            self.mail_vendor = ""
        if not hasattr(self, "provider_config"):
            self.provider_config = {}
        if not hasattr(self, "proxy_fallback_direct"):
            self.proxy_fallback_direct = False

    def _open_imap_server(self, use_proxy):
        if use_proxy:
            return proxy_imaplib.IMAP(
                proxy_host=self.proxy_host,
                proxy_port=self.proxy_port,
                proxy_type=self.proxy_type,
                proxy_user=self.proxy_user,
                proxy_pass=self.proxy_pass,
                host=self.imap_server,
                port=self.imap_port,
                timeout=30,
            )
        return imaplib.IMAP4_SSL(self.imap_server)

    def _login_server(self, use_proxy):
        server = self._open_imap_server(use_proxy)
        server.login(self.imap_user, self.imap_pass)
        return server

    def _login(self):
        use_proxy = self.proxy_host != "" and var.proxy_on
        try:
            return self._login_server(use_proxy)
        except Exception as proxy_error:
            if use_proxy and self.proxy_fallback_direct:
                logger.warning(
                    "IMAP proxy login failed for %s; retrying without proxy: %s",
                    self.imap_user,
                    proxy_error.__class__.__name__,
                )
                return self._login_server(False)
            raise

    def get_sent_folder(self):
        if self.provider_config:
            sent_folder = self.provider_config.get("sent_folder")
            if sent_folder:
                return sent_folder
        if self.mail_vendor == "gmail":
            return '"[Gmail]/Sent Mail"'
        return None

    def resolve_folder(self, folder_name):
        if not folder_name:
            return None
        if folder_name.upper() == "INBOX":
            return "INBOX"
        if folder_name == self.SENT_FOLDER_TOKEN:
            return self.get_sent_folder()
        if folder_name == '"[Gmail]/Sent Mail"':
            return self.get_sent_folder()
        return folder_name

    def delete_message(self, imap, uid):
        if self.mail_vendor == "gmail":
            imap.uid("STORE", uid, "+X-GM-LABELS", "\\Trash")
            return False
        imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
        return True
