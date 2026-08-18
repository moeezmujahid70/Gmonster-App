"""
TLS-fingerprint hypothesis test:
for each failing provider endpoint, retry the SOCKS5+TLS handshake
under three TLS variants (default / TLS1.2-pinned / TLS1.3-pinned)
with 3 attempts each. Prints pass/fail per (account, endpoint, variant, attempt).
"""
import os, sys, time, ssl, socket
sys.path.insert(0, os.path.dirname(__file__))
import openpyxl, socks
from proxy_diag import make_ctx, open_socks, mask_email, PROVIDERS

# Endpoints that failed in the baseline run
FAILING = {
    "gmx":   [("imap.gmx.com", 993), ("mail.gmx.com", 587, "starttls")],
    "yahoo": [("imap.mail.yahoo.com", 993), ("smtp.mail.yahoo.com", 465)],
    "ru":    [("imap.mail.ru", 993)],
    "aol":   [("imap.aol.com", 993), ("smtp.aol.com", 465)],
}

VARIANTS = ["default", "tls12", "tls13"]
ATTEMPTS = 3

def recv_line(sock, maxlen=4096):
    buf = b""
    sock.settimeout(10)
    while b"\n" not in buf and len(buf) < maxlen:
        try:
            chunk = sock.recv(4096)
        except Exception:
            break
        if not chunk: break
        buf += chunk
    return buf

def try_ssl(proxy, host, port, variant):
    ph, pp, pu, pw = proxy
    raw = open_socks(ph, pp, pu, pw, host, port, timeout=15)
    try:
        ctx = make_ctx(variant)
        ss = ctx.wrap_socket(raw, server_hostname=host)
        cipher = ss.cipher()[0]
        ss.close()
        return f"OK cipher={cipher}"
    finally:
        try: raw.close()
        except: pass

def try_starttls(proxy, host, port, variant):
    ph, pp, pu, pw = proxy
    s = open_socks(ph, pp, pu, pw, host, port, timeout=15)
    banner = recv_line(s)
    if not banner.startswith(b"220"):
        s.close()
        return f"FAIL empty/early-close banner={banner!r}"
    s.sendall(b"EHLO diag.local\r\n")
    ehlo = recv_line(s, 8192)
    if not ehlo.startswith(b"250"):
        s.close()
        return f"FAIL ehlo={ehlo!r}"
    s.sendall(b"STARTTLS\r\n")
    st = recv_line(s)
    if not st.startswith(b"220"):
        s.close()
        return f"FAIL starttls_reply={st!r}"
    ctx = make_ctx(variant)
    ss = ctx.wrap_socket(s, server_hostname=host)
    cipher = ss.cipher()[0]
    ss.close()
    return f"OK cipher={cipher}"

def main():
    wb = openpyxl.load_workbook(os.path.join(os.path.dirname(__file__), "..", "data", "sheets", "group_a.xlsx"))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    idx = {h: i for i, h in enumerate(rows[0])}

    # one row per failing provider is enough; pick first
    by_provider = {}
    for r in rows[1:]:
        if not r or r[idx["EMAIL"]] is None: continue
        prov = (r[idx["LASTFROMNAME"]] or "").lower().strip()
        by_provider.setdefault(prov, r)

    for prov, endpoints in FAILING.items():
        row = by_provider.get(prov)
        if not row:
            print(f"\n### {prov}: no row in sheet, skip"); continue
        email = row[idx["EMAIL"]]
        ph, pp = row[idx["PROXY:PORT"]].split(":")
        proxy = (ph.strip(), int(pp), row[idx["PROXY_USER"]], row[idx["PROXY_PASS"]])
        print(f"\n### {prov}  account={mask_email(email)}  proxy_port=***:{pp}")
        for ep in endpoints:
            mode = "starttls" if len(ep) == 3 else "ssl"
            host, port = ep[0], ep[1]
            print(f"  -- {host}:{port} ({mode})")
            for variant in VARIANTS:
                ok = 0
                last = ""
                for attempt in range(1, ATTEMPTS + 1):
                    t0 = time.time()
                    try:
                        if mode == "ssl":
                            res = try_ssl(proxy, host, port, variant)
                        else:
                            res = try_starttls(proxy, host, port, variant)
                        if res.startswith("OK"):
                            ok += 1
                        last = res
                    except Exception as e:
                        last = f"FAIL {type(e).__name__}: {e}"
                    dt = time.time() - t0
                    print(f"     [{variant:8s}] attempt {attempt}: {last}  ({dt:.2f}s)")
                    time.sleep(0.5 + (attempt * 0.7))  # small jittered backoff
                print(f"     [{variant:8s}] ==> {ok}/{ATTEMPTS} successes")

if __name__ == "__main__":
    main()
