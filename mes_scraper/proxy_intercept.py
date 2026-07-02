"""
XPlatform Traffic Interceptor — netsh portproxy method.

XPlatform connects directly by IP so hosts file won't work.
netsh portproxy intercepts at kernel level — works on raw IP connections.

HOW IT WORKS:
  1. Adds loopback alias for MES IP on this machine
  2. netsh portproxy: connections TO 107.105.195.34:8080
                      → redirected to 127.0.0.1:18080 (our proxy)
  3. Our proxy captures XML, forwards to real server
  4. Ctrl+C: removes portproxy rule, cleans up

REQUIRES: Run as Administrator
"""

import json
import os
import sys
import socket
import threading
import subprocess
import zlib
import gzip
import io
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

MANILA_TZ = timezone(timedelta(hours=8))

def _ts():
    return datetime.now(MANILA_TZ).strftime("%Y-%m-%d %H:%M:%S")

load_dotenv()

MES_HOST    = os.getenv("MES_HOST", "107.105.195.34")
MES_PORT    = int(os.getenv("MES_PORT", "8080"))
LISTEN_PORT = 18080
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "xp_requests.json")


def _get_local_ip() -> str:
    """Get this machine's real NIC IP (not loopback) by connecting to MES."""
    override = os.getenv("LOCAL_IP", "")
    if override:
        return override
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((MES_HOST, MES_PORT))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""


LOCAL_IP = _get_local_ip()

SCREEN_MAP = {
    "RPT40281": "wip_status",
    "RPT40496": "monthly_plan",
}

captured: dict = {}
lock = threading.Lock()


# ── netsh portproxy ──────────────────────────────────────────────────────────

def _add_portproxy():
    # Add loopback alias so this machine accepts packets destined for MES_HOST
    subprocess.run(
        ["netsh", "interface", "ip", "add", "address",
         "Loopback", MES_HOST, "255.255.255.255"],
        capture_output=True
    )
    r = subprocess.run([
        "netsh", "interface", "portproxy", "add", "v4tov4",
        f"listenaddress={MES_HOST}", f"listenport={MES_PORT}",
        "connectaddress=127.0.0.1",  f"connectport={LISTEN_PORT}",
    ], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[ERROR] netsh failed: {r.stderr.strip()}")
        sys.exit(1)
    print(f"[NETSH] {MES_HOST}:{MES_PORT} → 127.0.0.1:{LISTEN_PORT}  ✓")


def _remove_portproxy():
    subprocess.run([
        "netsh", "interface", "portproxy", "delete", "v4tov4",
        f"listenaddress={MES_HOST}", f"listenport={MES_PORT}",
    ], capture_output=True)
    subprocess.run([
        "netsh", "interface", "ip", "delete", "address",
        "Loopback", MES_HOST,
    ], capture_output=True)
    print("[NETSH] portproxy removed  ✓")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _recv_headers(sock):
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return buf


def _parse(raw):
    end = raw.find(b"\r\n\r\n")
    if end == -1:
        return "", "/", {}, b""
    head = raw[:end].decode("utf-8", errors="replace")
    body_start = raw[end + 4:]
    lines = head.split("\r\n")
    parts = lines[0].split(" ", 2)
    method  = parts[0] if parts else "GET"
    path    = parts[1] if len(parts) > 1 else "/"
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
    return method, path, headers, body_start


def _identify(url, body):
    for sid, name in SCREEN_MAP.items():
        if sid in url or (isinstance(body, str) and sid in body) or (isinstance(body, bytes) and sid.encode() in body):
            return name
    return None


def _decode_chunked(data: bytes) -> bytes:
    """Decode HTTP chunked transfer encoding."""
    result = b""
    pos = 0
    while pos < len(data):
        # Find end of chunk size line
        end = data.find(b"\r\n", pos)
        if end == -1:
            break
        try:
            chunk_size = int(data[pos:end].split(b";")[0].strip(), 16)
        except ValueError:
            break
        if chunk_size == 0:
            break
        pos = end + 2
        result += data[pos:pos + chunk_size]
        pos += chunk_size + 2  # skip trailing \r\n
    return result


def _save():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2)





# ── Per-connection handler ────────────────────────────────────────────────────

def handle_client(client):
    try:
        raw = _recv_headers(client)
        if not raw:
            return

        method, path, headers, body_so_far = _parse(raw)

        clen = int(headers.get("content-length", 0))
        body = body_so_far
        while len(body) < clen:
            chunk = client.recv(min(4096, clen - len(body)))
            if not chunk:
                break
            body += chunk

        body_str = body.decode("utf-8", errors="replace")

        # Build forwarded request
        fwd = {k: v for k, v in headers.items()
               if k not in ("connection", "proxy-connection")}
        fwd["host"]       = f"{MES_HOST}:{MES_PORT}"
        fwd["connection"] = "close"
        if body:
            fwd["content-length"] = str(len(body))

        req = (f"{method} {path} HTTP/1.1\r\n"
               + "".join(f"{k}: {v}\r\n" for k, v in fwd.items())
               + "\r\n").encode() + body

        # Forward to real server — bind to LOCAL_IP (real NIC) so the
        # outbound connection doesn't get caught by our own portproxy rule
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.settimeout(60)
        if LOCAL_IP:
            srv.bind((LOCAL_IP, 0))
        srv.connect((MES_HOST, MES_PORT))
        srv.sendall(req)

        response = b""
        while True:
            chunk = srv.recv(8192)
            if not chunk:
                break
            response += chunk
        srv.close()

        # Parse response headers + body
        resp_end = response.find(b"\r\n\r\n")
        if resp_end != -1:
            resp_head_raw = response[:resp_end].decode("utf-8", errors="replace")
            resp_body_raw = response[resp_end + 4:]
        else:
            resp_head_raw = ""
            resp_body_raw = response

        # Parse response headers to detect encoding
        resp_headers = {}
        for line in resp_head_raw.split("\r\n")[1:]:
            if ":" in line:
                k, _, v = line.partition(":")
                resp_headers[k.strip().lower()] = v.strip()

        encoding = resp_headers.get("content-encoding", "").strip().lower()
        transfer_encoding = resp_headers.get("transfer-encoding", "").strip().lower()

        # Debug: print all response headers for POST to RptXPController
        if path in ("/RptXPController.do", "/CommonXPController.do") and method == "POST":
            print(f"       [HEADERS] {resp_headers}")

        # De-chunk first if chunked transfer encoding
        if "chunked" in transfer_encoding:
            try:
                resp_body_raw = _decode_chunked(resp_body_raw)
            except Exception:
                pass

        # Decompress response body - try multiple methods since server may not declare encoding
        resp_body_decoded = None

        def _try_decompress(data: bytes):
            """Try all known decompression methods, return decompressed bytes or None."""
            if len(data) < 2:
                return None
            # gzip magic
            if data[:2] == b'\x1f\x8b':
                try:
                    return gzip.decompress(data)
                except Exception:
                    pass
            # zlib magic (78 01, 78 9c, 78 da, 78 5e)
            if data[0:1] == b'\x78':
                try:
                    return zlib.decompress(data)
                except Exception:
                    try:
                        return zlib.decompress(data, -15)
                    except Exception:
                        pass
            # raw deflate
            try:
                return zlib.decompress(data, -15)
            except Exception:
                pass
            return None

        # Try declared encoding
        if encoding in ("gzip", "deflate", "x-gzip"):
            resp_body_decoded = _try_decompress(resp_body_raw)

        # Auto-detect: try from offset 0, then scan for magic bytes up to offset 8
        if resp_body_decoded is None:
            resp_body_decoded = _try_decompress(resp_body_raw)

        if resp_body_decoded is None:
            for offset in range(1, min(16, len(resp_body_raw))):
                result = _try_decompress(resp_body_raw[offset:])
                if result is not None:
                    resp_body_decoded = result
                    break
        
        # Fallback to raw if all decompression attempts failed
        if resp_body_decoded is None:
            resp_body_decoded = resp_body_raw

        resp_text = resp_body_decoded.decode("utf-8", errors="replace")

        # Also try to decompress request body (XPlatform sends compressed POSTs)
        body_decoded_str = body_str
        if body and not body_str.strip().startswith("<"):
            body_decoded = None
            if len(body) > 2:
                if body[:2] == b'\x1f\x8b':
                    try:
                        body_decoded = gzip.decompress(body)
                    except Exception:
                        pass
                if body_decoded is None and body[0:1] == b'\x78':
                    try:
                        body_decoded = zlib.decompress(body)
                    except Exception:
                        try:
                            body_decoded = zlib.decompress(body, -15)
                        except Exception:
                            pass
                # Try raw deflate (no header) as last resort
                if body_decoded is None:
                    try:
                        body_decoded = zlib.decompress(body, -15)
                    except Exception:
                        pass
            if body_decoded:
                body_decoded_str = body_decoded.decode("utf-8", errors="replace")

        # Log every request so we can see what's flowing through
        print(f"[{method}] {_ts()} {path[:65]}")
        if body_decoded_str.strip():
            print(f"       body: {body_decoded_str[:120]}")
        print(f"       resp: {resp_text[:120]}")
        print()

        # Capture binary XPlatform responses to RptXPController.do
        # Content-Type is application/octet-stream — proprietary binary format
        is_rpt_endpoint = path in ("/RptXPController.do", "/CommonXPController.do")
        content_type = resp_headers.get("content-type", "")
        is_xp_binary = b'\xff\xad' in resp_body_raw[:4] or b'\xff\xad' in resp_body_decoded[:4] if resp_body_decoded else False
        has_data = len(resp_body_raw) > 50

        if method == "POST" and is_rpt_endpoint:
            print(f"       [DEBUG] encoding={encoding!r}  raw_bytes={resp_body_raw[:4].hex()}  content_type={content_type!r}  resp_len={len(resp_body_raw)}")

        if method == "POST" and is_rpt_endpoint and has_data:
            real_url = f"http://{MES_HOST}:{MES_PORT}{path}"
            # Try to identify by decoded body text first
            name = _identify(real_url, body_decoded_str) or _identify(real_url, body_str)
            # Also search raw body bytes for screen ID (handles compressed bodies)
            if not name:
                for sid, sid_name in SCREEN_MAP.items():
                    if sid.encode() in body:
                        name = sid_name
                        break
            # For RptXPController large responses, capture even if unidentified
            # Large responses (>1000 bytes) from RptXPController are report data
            if not name and path == "/RptXPController.do" and len(resp_body_raw) > 1000:
                # Use a counter to distinguish multiple captures
                with lock:
                    idx = sum(1 for k in captured if k.startswith("rpt_capture_"))
                name = f"rpt_capture_{idx}"

            if name:
                entry = {
                    "url": real_url,
                    "headers": fwd,
                    "post_data_hex": body.hex(),  # store raw bytes as hex to preserve binary
                    "response_raw_hex": resp_body_raw[:8192].hex(),
                    "response_text_sample": resp_text[:2000],
                    "response_size": len(resp_body_raw),
                }
                with lock:
                    if name not in captured:
                        captured[name] = []
                    captured[name].append(entry)
                    _save()
                print(f"★ [CAPTURED] {_ts()} {name}  ({len(resp_body_raw)} bytes)")
                print()

        client.sendall(response)

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        try:
            client.close()
        except Exception:
            pass


# ── Main ─────────────────────────────────────────────────────────────────────

def run():
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("[ERROR] Must run as Administrator.")
        print("        Right-click PowerShell → 'Run as administrator'")
        sys.exit(1)

    print("=" * 60)
    print("  XPlatform Interceptor  (netsh portproxy)")
    print("=" * 60)
    print(f"Intercepts:  {MES_HOST}:{MES_PORT}")
    print(f"Proxy port:  127.0.0.1:{LISTEN_PORT}")
    print(f"Local NIC:   {LOCAL_IP or 'auto-detect failed — set LOCAL_IP in .env'}")
    print()

    _add_portproxy()

    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", LISTEN_PORT))
        srv.listen(50)
        srv.settimeout(1.0)
    except OSError as e:
        _remove_portproxy()
        print(f"[ERROR] Cannot bind port {LISTEN_PORT}: {e}")
        sys.exit(1)

    print(f"[PROXY] Listening on {LISTEN_PORT}  ✓")
    print()
    print("Open XPlatform and load:")
    print("  - RPT40281  WIP Status (Chip)")
    print("    → Filter: Major Process = Visual + Sorting + Outgoing Inspection")
    print("    → Select all three processes, then click Apply (F5)")
    print("  - RPT40496  Monthly Plan")
    print()
    print("You will see [GET]/[POST] lines for every request.")
    print("Press Ctrl+C when both grids have loaded.")
    print("=" * 60)
    print()

    try:
        while True:
            try:
                client, addr = srv.accept()
                print(f"[CONNECT] {_ts()} from {addr[0]}:{addr[1]}")
                threading.Thread(
                    target=handle_client, args=(client,), daemon=True
                ).start()
            except socket.timeout:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        _remove_portproxy()

    total = sum(len(v) for v in captured.values())
    print(f"\nCaptured {total} entries.")
    if captured:
        _save()
        print(f"Saved → {OUTPUT_FILE}")
        print("\nNext:  python main.py --once")
    else:
        print("\nNothing captured.")
        print("If you saw [CONNECT] lines above — proxy received connections")
        print("but no XML data matched. Share the [POST] output for analysis.")
        print()
        print("If NO [CONNECT] lines — portproxy rule didn't intercept traffic.")
        print("Verify with:  netsh interface portproxy show all")


if __name__ == "__main__":
    run()
