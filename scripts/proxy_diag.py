"""
Diagnostic for SOCKS5 proxy -> mail provider TLS path.

For each row in data/sheets/group_a.xlsx, runs three stages per protocol:
  proxy_tcp -> ssl_handshake -> protocol_greeting/EHLO/CAPABILITY

No login attempt, no email send. Credentials never printed.
"""
import socket, ssl, sys, os, time
import socks
import openpyxl

PROVIDERS = {
    "gmail":  {"imap": ("imap.gmail.com", 993, "ssl"),
               "smtp": ("smtp.gmail.com", 587, "starttls")},
    "gmx":    {"imap": ("imap.gmx.com", 993, "ssl"),
               "smtp": ("mail.gmx.com", 587, "starttls")},
    "yahoo":  {"imap": ("imap.mail.yahoo.com", 993, "ssl"),
               "smtp": ("smtp.mail.yahoo.com", 465, "ssl")},
    "ru":     {"imap": ("imap.mail.ru", 993, "ssl"),
               "smtp": ("smtp.mail.ru", 465, "ssl")},
    "aol":    {"imap": ("imap.aol.com", 993, "ssl"),
               "smtp": ("smtp.aol.com", 465, "ssl")},
}

def mask_email(e):
    if not e or "@" not in e: return e
    local, dom = e.split("@", 1)
    return local[:2] + "***@" + dom

def open_socks(proxy_host, proxy_port, proxy_user, proxy_pass, dest_host, dest_port, timeout=15):
    s = socks.socksocket()
    s.set_proxy(socks.SOCKS5, proxy_host, int(proxy_port),
                username=proxy_user, password=proxy_pass)
    s.settimeout(timeout)
    s.connect((dest_host, dest_port))
    return s

def try_stage(label, fn):
    try:
        r = fn()
        return ("OK", label, r)
    except Exception as e:
        return ("FAIL", label, f"{type(e).__name__}: {e}")

def recv_line(sock, maxlen=4096):
    buf = b""
    sock.settimeout(10)
    while b"\n" not in buf and len(buf) < maxlen:
        chunk = sock.recv(4096)
        if not chunk: break
        buf += chunk
    return buf

def make_ctx(variant):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    if variant == "tls12":
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=2")
        except ssl.SSLError:
            pass
    elif variant == "tls13":
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.maximum_version = ssl.TLSVersion.TLSv1_3
    return ctx

def test_ssl(proxy, host, port, variant="default"):
    ph, pp, pu, pw = proxy
    results = []
    raw = None
    sslsock = None
    try:
        t0 = time.time()
        raw = open_socks(ph, pp, pu, pw, host, port)
        results.append(("OK", "proxy_tcp", f"connect_ok in {time.time()-t0:.2f}s"))
    except Exception as e:
        results.append(("FAIL", "proxy_tcp", f"{type(e).__name__}: {e}"))
        return results
    try:
        ctx = make_ctx(variant)
        t0 = time.time()
        sslsock = ctx.wrap_socket(raw, server_hostname=host)
        results.append(("OK", f"tls_handshake[{variant}]", f"cipher={sslsock.cipher()[0]} in {time.time()-t0:.2f}s"))
    except Exception as e:
        results.append(("FAIL", f"tls_handshake[{variant}]", f"{type(e).__name__}: {e}"))
        try: raw.close()
        except: pass
        return results
    try:
        if port == 993:
            line = recv_line(sslsock)
            results.append(("OK", "imap_greeting", line[:120].decode("latin1", "replace").strip()))
        else:
            line = recv_line(sslsock)
            results.append(("OK", "smtp_banner", line[:120].decode("latin1", "replace").strip()))
    except Exception as e:
        results.append(("FAIL", "greeting", f"{type(e).__name__}: {e}"))
    try: sslsock.close()
    except: pass
    return results

def test_starttls(proxy, host, port):
    ph, pp, pu, pw = proxy
    results = []
    try:
        t0 = time.time()
        sock = open_socks(ph, pp, pu, pw, host, port)
        results.append(("OK", "proxy_tcp", f"connect_ok in {time.time()-t0:.2f}s"))
    except Exception as e:
        results.append(("FAIL", "proxy_tcp", f"{type(e).__name__}: {e}"))
        return results
    try:
        banner = recv_line(sock)
        results.append(("OK", "smtp_banner", banner[:120].decode("latin1","replace").strip()))
    except Exception as e:
        results.append(("FAIL", "smtp_banner", f"{type(e).__name__}: {e}"))
        return results
    try:
        sock.sendall(b"EHLO diag.local\r\n")
        ehlo = recv_line(sock, 8192)
        ok = b"250" in ehlo[:4] or ehlo.startswith(b"250")
        results.append(("OK" if ok else "WARN", "ehlo", ehlo[:120].decode("latin1","replace").strip()))
        sock.sendall(b"STARTTLS\r\n")
        st = recv_line(sock)
        results.append(("OK" if st.startswith(b"220") else "FAIL", "starttls_reply",
                        st[:120].decode("latin1","replace").strip()))
        if not st.startswith(b"220"):
            return results
        ctx = ssl.create_default_context()
        sslsock = ctx.wrap_socket(sock, server_hostname=host)
        results.append(("OK", "tls_handshake", f"cipher={sslsock.cipher()[0]}"))
        sslsock.close()
    except Exception as e:
        results.append(("FAIL", "starttls", f"{type(e).__name__}: {e}"))
    return results

def main():
    wb = openpyxl.load_workbook(os.path.join(os.path.dirname(__file__), "..", "data", "sheets", "group_a.xlsx"))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    headers = rows[0]
    idx = {h: i for i, h in enumerate(headers)}
    for row in rows[1:]:
        if not row or row[idx["EMAIL"]] is None: continue
        email = row[idx["EMAIL"]]
        provider_tag = (row[idx["LASTFROMNAME"]] or "").lower().strip()
        proxy_hostport = row[idx["PROXY:PORT"]]
        puser = row[idx["PROXY_USER"]]
        ppass = row[idx["PROXY_PASS"]]
        provider_key = "ru" if provider_tag == "ru" else provider_tag
        prov = PROVIDERS.get(provider_key)
        if not prov:
            print(f"\n--- {mask_email(email)}  provider={provider_tag}  SKIP (unknown provider)\n")
            continue
        ph, pp = proxy_hostport.split(":")
        proxy = (ph.strip(), int(pp), puser, ppass)
        print(f"\n=== {mask_email(email)} via proxy ***:{pp} provider={provider_tag} ===")
        ih, ip, imode = prov["imap"]
        print(f"  IMAP {ih}:{ip} ({imode})")
        for status, stage, info in test_ssl(proxy, ih, ip):
            print(f"    {status:4s} {stage}: {info}")
        sh, sp, smode = prov["smtp"]
        print(f"  SMTP {sh}:{sp} ({smode})")
        fn = test_ssl if smode == "ssl" else test_starttls
        for status, stage, info in fn(proxy, sh, sp):
            print(f"    {status:4s} {stage}: {info}")

if __name__ == "__main__":
    main()
