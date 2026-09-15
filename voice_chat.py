#!/usr/bin/env python3
"""VoiceLink — Radmin VPN üzeri sesli iletişim"""

import tkinter as tk
from tkinter import messagebox
import socket
import threading
import pyaudio
import json
import queue
import array as _arr
import struct
import time

try:
    import keyboard as _kb
    _KB = True
except ImportError:
    _KB = False

# ─── Sabitler ─────────────────────────────────────────────
CHUNK        = 1024
FORMAT       = pyaudio.paInt16
CHANNELS     = 1
RATE         = 44100
SAMPLE_WIDTH = 2
UDP_PORT     = 7654

AUDIO_HDR = b'\x01'
CTRL_HDR  = b'\x00'

HOST_TAG  = b'\x00\x00\x00\x00\x00\x00'
HOST_ADDR = ('0.0.0.0', 0)

DEFAULT_HOTKEY = 'f12'

# ─── Yardımcı fonksiyonlar ────────────────────────────────

def scale_audio(data: bytes, volume: float) -> bytes:
    if abs(volume - 1.0) < 0.005:
        return data
    samples = _arr.array('h', data)
    for i in range(len(samples)):
        v = int(samples[i] * volume)
        samples[i] = max(-32768, min(32767, v))
    return samples.tobytes()


def addr_to_tag(addr) -> bytes:
    try:
        return socket.inet_aton(addr[0]) + struct.pack('>H', addr[1])
    except Exception:
        return HOST_TAG


def tag_to_addr(tag: bytes):
    try:
        ip   = socket.inet_ntoa(tag[:4])
        port = struct.unpack('>H', tag[4:6])[0]
        return (ip, port)
    except Exception:
        return HOST_ADDR


# ─── Ana uygulama ─────────────────────────────────────────

class VoiceLink:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("VoiceLink")
        self.root.geometry("440x570")
        self.root.configure(bg='#0d0d0d')
        self.root.resizable(False, False)

        self.nickname     = tk.StringVar()
        self.is_hosting   = False
        self.is_connected = False
        self.running      = False
        self.mic_muted    = False
        self.mute_hotkey  = DEFAULT_HOTKEY

        self.peers       = {}
        self.peer_names  = {}
        self.server_sock = None
        self.client_sock = None
        self.server_addr = None

        self.audio      = pyaudio.PyAudio()
        self.stream_in  = None
        self.stream_out = None
        self.play_queue = queue.Queue(maxsize=80)

        self.peer_volumes: dict[tuple, float] = {}
        self._vol_vars: dict[tuple, tk.IntVar] = {}

        self._build_login()

    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()

    def _build_login(self):
        self._clear()
        frm = tk.Frame(self.root, bg='#0d0d0d')
        frm.pack(expand=True)

        tk.Label(frm, text="🎙", font=("Segoe UI Emoji", 52),
                 bg='#0d0d0d', fg='#7c3aed').pack(pady=(0, 4))
        tk.Label(frm, text="VoiceLink",
                 font=("Segoe UI", 24, "bold"), bg='#0d0d0d', fg='#ffffff').pack()
        tk.Label(frm, text="Radmin VPN  ·  Sesli İletişim",
                 font=("Segoe UI", 10), bg='#0d0d0d', fg='#555555').pack(pady=(2, 28))
        tk.Label(frm, text="Kullanıcı Adın",
                 font=("Segoe UI", 11), bg='#0d0d0d', fg='#aaaaaa').pack(anchor='w')

        ent = tk.Entry(frm, textvariable=self.nickname,
                       font=("Segoe UI", 14), width=22,
                       bg='#181818', fg='#ffffff',
                       insertbackground='#7c3aed',
                       relief='flat', bd=8,
                       highlightthickness=2,
                       highlightbackground='#2a2a2a',
                       highlightcolor='#7c3aed')
        ent.pack(pady=(6, 18))
        ent.focus_set()
        ent.bind('<Return>', lambda _e: self._confirm_nick())

        tk.Button(frm, text="Giriş Yap  →",
                  font=("Segoe UI", 12, "bold"),
                  bg='#7c3aed', fg='white',
                  activebackground='#6d28d9', activeforeground='white',
                  relief='flat', bd=0, padx=28, pady=10,
                  cursor='hand2',
                  command=self._confirm_nick).pack()

    def _confirm_nick(self):
        nick = self.nickname.get().strip()
        if not nick:
            messagebox.showwarning("VoiceLink", "Kullanıcı adı boş bırakılamaz.")
            return
        if len(nick) > 20:
            messagebox.showwarning("VoiceLink", "Kullanıcı adı en fazla 20 karakter.")
            return
        self._register_hotkey()
        self._build_main()

    def _build_main(self):
        self._clear()
        nick = self.nickname.get()
        self.root.title(f"VoiceLink  —  {nick}")

        hdr = tk.Frame(self.root, bg='#111111', height=52)
        hdr.pack(fill='x')
        hdr.pack_propagate(False)
        tk.Label(hdr, text="🎙  VoiceLink",
                 font=("Segoe UI", 13, "bold"), bg='#111111', fg='#7c3aed').pack(side='left', padx=14)
        tk.Button(hdr, text="⚙",
                  font=("Segoe UI", 13), bg='#111111', fg='#888888',
                  activebackground='#111111', activeforeground='#ffffff',
                  relief='flat', bd=0, padx=6, cursor='hand2',
                  command=self._open_settings).pack(side='right', padx=6)
        self.lbl_status = tk.Label(hdr, text="⬤  Çevrimdışı",
                                   font=("Segoe UI", 9), bg='#111111', fg='#444444')
        self.lbl_status.pack(side='right', padx=6)

        body = tk.Frame(self.root, bg='#0d0d0d')
        body.pack(fill='both', expand=True, padx=16, pady=12)

        chip = tk.Frame(body, bg='#161616')
        chip.pack(fill='x', pady=(0, 8))
        tk.Label(chip, text=f"👤  {nick}",
                 font=("Segoe UI", 11), bg='#161616', fg='#cccccc',
                 padx=10, pady=6).pack(side='left')
        lip = self._local_ip()
        tk.Label(chip, text=f"IP: {lip}",
                 font=("Segoe UI", 9), bg='#161616', fg='#7c3aed',
                 padx=10).pack(side='right')

        self._sep(body, "ODA AÇ")
        rh = tk.Frame(body, bg='#0d0d0d')
        rh.pack(fill='x', pady=(0, 2))
        tk.Label(rh, text=f"Port {UDP_PORT}  ·  {lip}",
                 font=("Segoe UI", 9), bg='#0d0d0d', fg='#4a9eff').pack(side='left')
        self.btn_host = tk.Button(rh, text="Oda Aç",
                                  font=("Segoe UI", 10, "bold"),
                                  bg='#1e3a5f', fg='white',
                                  activebackground='#2a4f7e',
                                  relief='flat', bd=0, padx=14, pady=5,
                                  cursor='hand2', command=self._toggle_host)
        self.btn_host.pack(side='right')

        self._sep(body, "ODAYA KATIL")
        rj = tk.Frame(body, bg='#0d0d0d')
        rj.pack(fill='x', pady=(0, 2))
        self.entry_ip = tk.Entry(rj, font=("Segoe UI", 12), width=18,
                                  bg='#181818', fg='#ffffff',
                                  insertbackground='#7c3aed',
                                  relief='flat', bd=6,
                                  highlightthickness=1,
                                  highlightbackground='#2a2a2a',
                                  highlightcolor='#7c3aed')
        self.entry_ip.pack(side='left')
        self.entry_ip.bind('<Return>', lambda _e: self._toggle_join())
        self.btn_join = tk.Button(rj, text="Bağlan",
                                  font=("Segoe UI", 10, "bold"),
                                  bg='#7c3aed', fg='white',
                                  activebackground='#6d28d9',
                                  relief='flat', bd=0, padx=14, pady=5,
                                  cursor='hand2', command=self._toggle_join)
        self.btn_join.pack(side='right')

        self._sep(body, "BAĞLI KULLANICILAR")
        self.frm_users = tk.Frame(body, bg='#111111')
        self.frm_users.pack(fill='both', expand=True, pady=(0, 4))
        tk.Label(self.frm_users, text="Henüz kimse bağlı değil",
                 font=("Segoe UI", 10), bg='#111111', fg='#3a3a3a').pack(pady=14)

        bar = tk.Frame(self.root, bg='#111111', height=62)
        bar.pack(fill='x', side='bottom')
        bar.pack_propagate(False)
        hk_text = f"({self.mute_hotkey.upper()})" if _KB else ""
        self.btn_mic = tk.Button(bar,
                                  text=f"🎙  Mikrofon Açık  {hk_text}",
                                  font=("Segoe UI", 11, "bold"),
                                  bg='#16a34a', fg='#f0fdf4',
                                  activebackground='#15803d',
                                  relief='flat', bd=0, padx=22, pady=9,
                                  cursor='hand2', state='disabled',
                                  command=self._toggle_mic)
        self.btn_mic.pack(expand=True)

    def _sep(self, parent, text):
        tk.Label(parent, text=text,
                 font=("Segoe UI", 8, "bold"),
                 bg='#0d0d0d', fg='#444444').pack(anchor='w', pady=(8, 2))

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Ayarlar")
        win.geometry("320x200")
        win.configure(bg='#0d0d0d')
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text="⚙  Ayarlar",
                 font=("Segoe UI", 13, "bold"), bg='#0d0d0d', fg='#ffffff').pack(pady=(16, 12))

        hk_frame = tk.Frame(win, bg='#161616')
        hk_frame.pack(fill='x', padx=16, pady=4)
        tk.Label(hk_frame, text="Mikrofon Sessiz Tuşu",
                 font=("Segoe UI", 10), bg='#161616', fg='#aaaaaa',
                 padx=10, pady=8).pack(side='left')
        self._hk_var = tk.StringVar(value=self.mute_hotkey.upper())
        hk_lbl = tk.Label(hk_frame, textvariable=self._hk_var,
                           font=("Segoe UI", 10, "bold"),
                           bg='#2a2a2a', fg='#7c3aed',
                           padx=8, pady=4)
        hk_lbl.pack(side='right', padx=(0, 6))

        if _KB:
            tk.Button(win, text="Tuş Değiştir",
                      font=("Segoe UI", 10),
                      bg='#1e3a5f', fg='white',
                      activebackground='#2a4f7e',
                      relief='flat', bd=0, padx=12, pady=6,
                      cursor='hand2',
                      command=lambda: self._capture_hotkey(win, hk_lbl)).pack(pady=10)
        else:
            tk.Label(win, text="⚠  'keyboard' kütüphanesi kurulu değil\nGlobal hotkey devre dışı",
                     font=("Segoe UI", 9), bg='#0d0d0d', fg='#dc2626',
                     justify='center').pack(pady=8)
            tk.Label(win, text="Kurmak için:  pip install keyboard",
                     font=("Segoe UI", 9), bg='#0d0d0d', fg='#555555').pack()

        tk.Button(win, text="Kapat",
                  font=("Segoe UI", 10),
                  bg='#222222', fg='#aaaaaa',
                  activebackground='#333333',
                  relief='flat', bd=0, padx=16, pady=5,
                  cursor='hand2',
                  command=win.destroy).pack(pady=(4, 0))

    def _capture_hotkey(self, win, label):
        label.config(text="...", fg='#f59e0b')
        win.update()

        def do_capture():
            try:
                hk = _kb.read_hotkey(suppress=False)
                self.mute_hotkey = hk
                self._hk_var.set(hk.upper())
                label.config(fg='#7c3aed')
                self._register_hotkey()
                if hasattr(self, 'btn_mic'):
                    muted = self.mic_muted
                    txt = (f"🔇  Mikrofon Kapalı  ({hk.upper()})" if muted
                           else f"🎙  Mikrofon Açık  ({hk.upper()})")
                    self.root.after(0, lambda: self.btn_mic.config(text=txt))
            except Exception:
                label.config(text=self.mute_hotkey.upper(), fg='#7c3aed')

        threading.Thread(target=do_capture, daemon=True).start()

    def _register_hotkey(self):
        if not _KB:
            return
        try:
            _kb.unhook_all_hotkeys()
            _kb.add_hotkey(self.mute_hotkey, self._toggle_mic)
        except Exception:
            pass

    def _toggle_host(self):
        if self.is_hosting: self._stop_host()
        else:               self._start_host()

    def _start_host(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', UDP_PORT))
            sock.settimeout(0.5)
            self.server_sock = sock
        except Exception as e:
            messagebox.showerror("VoiceLink", f"Soket açılamadı:\n{e}")
            return

        self.is_hosting = True
        self.running    = True
        self.peers      = {}

        self.btn_host.config(text="Kapat", bg='#7f1d1d')
        self.lbl_status.config(text=f"⬤  Oda Açık  ·  Port {UDP_PORT}", fg='#22c55e')
        self.btn_mic.config(state='normal')

        self._open_audio()
        threading.Thread(target=self._host_recv, daemon=True).start()
        threading.Thread(target=self._host_send, daemon=True).start()
        threading.Thread(target=self._playback,  daemon=True).start()

    def _stop_host(self):
        self.is_hosting = False
        self.running    = False
        self._close_audio()
        if self.server_sock:
            try: self.server_sock.close()
            except: pass
            self.server_sock = None
        self.peers = {}
        self.btn_host.config(text="Oda Aç", bg='#1e3a5f')
        self.lbl_status.config(text="⬤  Çevrimdışı", fg='#444444')
        self.btn_mic.config(state='disabled', bg='#16a34a')
        self._update_mic_text()
        self._refresh_users()

    def _toggle_join(self):
        if self.is_connected: self._disconnect()
        else:                 self._connect()

    def _connect(self):
        ip = self.entry_ip.get().strip()
        if not ip:
            messagebox.showwarning("VoiceLink", "IP adresi girin.")
            return
        try:
            socket.inet_aton(ip)
        except OSError:
            messagebox.showerror("VoiceLink", "Geçersiz IP adresi.")
            return

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.5)
            self.client_sock = sock
            self.server_addr = (ip, UDP_PORT)
        except Exception as e:
            messagebox.showerror("VoiceLink", f"Soket açılamadı:\n{e}")
            return

        self.is_connected = True
        self.running      = True
        self.peer_names   = {}

        self._send_ctrl(self.client_sock, self.server_addr,
                        {'type': 'join', 'nick': self.nickname.get()})

        self.btn_join.config(text="Ayrıl", bg='#7f1d1d')
        self.lbl_status.config(text=f"⬤  Bağlandı  ·  {ip}", fg='#22c55e')
        self.btn_mic.config(state='normal')

        self._open_audio()
        threading.Thread(target=self._client_recv, daemon=True).start()
        threading.Thread(target=self._client_send, daemon=True).start()
        threading.Thread(target=self._playback,    daemon=True).start()

    def _disconnect(self):
        self.is_connected = False
        self.running      = False
        if self.client_sock and self.server_addr:
            try:
                self._send_ctrl(self.client_sock, self.server_addr,
                                {'type': 'leave', 'nick': self.nickname.get()})
            except: pass
            try: self.client_sock.close()
            except: pass
            self.client_sock = None
        self._close_audio()
        self.peer_names = {}
        self.btn_join.config(text="Bağlan", bg='#7c3aed')
        self.lbl_status.config(text="⬤  Çevrimdışı", fg='#444444')
        self.btn_mic.config(state='disabled', bg='#16a34a')
        self._update_mic_text()
        self._refresh_users()

    def _open_audio(self):
        self.stream_in  = self.audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                          input=True, frames_per_buffer=CHUNK)
        self.stream_out = self.audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                          output=True, frames_per_buffer=CHUNK)

    def _close_audio(self):
        for attr in ('stream_in', 'stream_out'):
            s = getattr(self, attr, None)
            if s:
                try: s.stop_stream(); s.close()
                except: pass
                setattr(self, attr, None)
        while not self.play_queue.empty():
            try: self.play_queue.get_nowait()
            except: break

    def _playback(self):
        while self.running:
            try:
                data = self.play_queue.get(timeout=0.15)
                if self.stream_out:
                    try: self.stream_out.write(data)
                    except: pass
            except queue.Empty:
                continue

    def _enqueue(self, pcm: bytes, src_addr):
        vol = self.peer_volumes.get(src_addr, 1.0)
        scaled = scale_audio(pcm, vol)
        try:
            self.play_queue.put_nowait(scaled)
        except queue.Full:
            pass

    def _host_recv(self):
        while self.is_hosting:
            try:
                data, addr = self.server_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            if not data:
                continue

            if data[:1] == CTRL_HDR:
                try:
                    msg = json.loads(data[1:].decode())
                    t = msg.get('type')
                    if t == 'join':
                        self.peers[addr] = msg['nick']
                        if addr not in self.peer_volumes:
                            self.peer_volumes[addr] = 1.0
                        self.root.after(0, self._refresh_users)
                        peer_list = [{'ip': a[0], 'port': a[1], 'nick': n}
                                     for a, n in self.peers.items() if a != addr]
                        self._send_ctrl(self.server_sock, addr,
                                        {'type': 'ack',
                                         'nick': self.nickname.get(),
                                         'peers': peer_list})
                        for peer in list(self.peers.keys()):
                            if peer != addr:
                                self._send_ctrl(self.server_sock, peer,
                                                {'type': 'peer_join',
                                                 'ip': addr[0], 'port': addr[1],
                                                 'nick': msg['nick']})
                    elif t == 'leave':
                        self.peers.pop(addr, None)
                        self.root.after(0, self._refresh_users)
                        for peer in list(self.peers.keys()):
                            self._send_ctrl(self.server_sock, peer,
                                            {'type': 'peer_leave',
                                             'ip': addr[0], 'port': addr[1]})
                except Exception:
                    pass

            elif data[:1] == AUDIO_HDR:
                pcm = data[1:]
                self._enqueue(pcm, addr)
                src_tag = addr_to_tag(addr)
                fwd = AUDIO_HDR + src_tag + pcm
                for peer in list(self.peers.keys()):
                    if peer != addr:
                        try: self.server_sock.sendto(fwd, peer)
                        except: pass

    def _host_send(self):
        while self.is_hosting:
            try:
                if self.stream_in and self.peers and not self.mic_muted:
                    raw = self.stream_in.read(CHUNK, exception_on_overflow=False)
                    pkt = AUDIO_HDR + HOST_TAG + raw
                    for peer in list(self.peers.keys()):
                        try: self.server_sock.sendto(pkt, peer)
                        except: pass
                else:
                    time.sleep(0.015)
            except OSError:
                break

    def _client_recv(self):
        while self.is_connected:
            try:
                data, addr = self.client_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break

            if not data:
                continue

            if data[:1] == CTRL_HDR:
                try:
                    msg = json.loads(data[1:].decode())
                    t = msg.get('type')
                    if t == 'ack':
                        self.peer_names[HOST_ADDR] = msg['nick']
                        if HOST_ADDR not in self.peer_volumes:
                            self.peer_volumes[HOST_ADDR] = 1.0
                        for p in msg.get('peers', []):
                            pa = (p['ip'], p['port'])
                            self.peer_names[pa] = p['nick']
                            if pa not in self.peer_volumes:
                                self.peer_volumes[pa] = 1.0
                        self.root.after(0, self._refresh_users)
                    elif t == 'peer_join':
                        pa = (msg['ip'], msg['port'])
                        self.peer_names[pa] = msg['nick']
                        if pa not in self.peer_volumes:
                            self.peer_volumes[pa] = 1.0
                        self.root.after(0, self._refresh_users)
                    elif t == 'peer_leave':
                        pa = (msg['ip'], msg['port'])
                        self.peer_names.pop(pa, None)
                        self.root.after(0, self._refresh_users)
                except Exception:
                    pass

            elif data[:1] == AUDIO_HDR:
                if len(data) > 7:
                    src_tag  = data[1:7]
                    pcm      = data[7:]
                    src_addr = tag_to_addr(src_tag)
                else:
                    pcm      = data[1:]
                    src_addr = HOST_ADDR
                self._enqueue(pcm, src_addr)

    def _client_send(self):
        while self.is_connected:
            try:
                if self.stream_in and self.server_addr and not self.mic_muted:
                    raw = self.stream_in.read(CHUNK, exception_on_overflow=False)
                    self.client_sock.sendto(AUDIO_HDR + raw, self.server_addr)
                else:
                    time.sleep(0.015)
            except OSError:
                break

    def _toggle_mic(self):
        self.mic_muted = not self.mic_muted
        if self.btn_mic.cget('state') == 'disabled':
            return
        self.btn_mic.config(bg='#dc2626' if self.mic_muted else '#16a34a')
        self._update_mic_text()

    def _update_mic_text(self):
        hk = f"  ({self.mute_hotkey.upper()})" if _KB else ""
        txt = f"🔇  Mikrofon Kapalı{hk}" if self.mic_muted else f"🎙  Mikrofon Açık{hk}"
        try:
            self.btn_mic.config(text=txt)
        except Exception:
            pass

    def _send_ctrl(self, sock, addr, msg):
        try:
            sock.sendto(CTRL_HDR + json.dumps(msg, ensure_ascii=False).encode(), addr)
        except Exception:
            pass

    def _local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _get_vol_var(self, addr) -> tk.IntVar:
        if addr not in self._vol_vars:
            self._vol_vars[addr] = tk.IntVar(value=int(self.peer_volumes.get(addr, 1.0) * 100))
        return self._vol_vars[addr]

    def _change_volume(self, addr, delta: int):
        var = self._get_vol_var(addr)
        new_val = max(0, min(200, var.get() + delta))
        var.set(new_val)
        self.peer_volumes[addr] = new_val / 100.0

    def _refresh_users(self):
        for w in self.frm_users.winfo_children():
            w.destroy()

        source = self.peers if self.is_hosting else (self.peer_names if self.is_connected else {})

        if not source:
            tk.Label(self.frm_users, text="Henüz kimse bağlı değil",
                     font=("Segoe UI", 10), bg='#111111', fg='#3a3a3a').pack(pady=14)
            return

        for addr, nick in source.items():
            if addr not in self.peer_volumes:
                self.peer_volumes[addr] = 1.0
            var = self._get_vol_var(addr)

            row = tk.Frame(self.frm_users, bg='#1a1a1a')
            row.pack(fill='x', padx=4, pady=2)
            tk.Label(row, text=f"🔊  {nick}",
                     font=("Segoe UI", 11), bg='#1a1a1a', fg='#4ade80',
                     padx=8, pady=5).pack(side='left')

            right = tk.Frame(row, bg='#1a1a1a')
            right.pack(side='right', padx=6)
            tk.Button(right, text="−", font=("Segoe UI", 11, "bold"),
                      bg='#2a2a2a', fg='#ffffff', activebackground='#3a3a3a',
                      relief='flat', bd=0, width=2, cursor='hand2',
                      command=lambda a=addr: self._change_volume(a, -10)).pack(side='left')
            tk.Label(right, textvariable=var, font=("Segoe UI", 9, "bold"),
                     bg='#1a1a1a', fg='#7c3aed', width=4).pack(side='left', padx=2)
            tk.Label(right, text="%", font=("Segoe UI", 9),
                     bg='#1a1a1a', fg='#555555').pack(side='left')
            tk.Button(right, text="+", font=("Segoe UI", 11, "bold"),
                      bg='#2a2a2a', fg='#ffffff', activebackground='#3a3a3a',
                      relief='flat', bd=0, width=2, cursor='hand2',
                      command=lambda a=addr: self._change_volume(a, 10)).pack(side='left', padx=(0, 4))

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.running      = False
        self.is_hosting   = False
        self.is_connected = False
        if _KB:
            try: _kb.unhook_all_hotkeys()
            except: pass
        self._close_audio()
        for sock in (self.server_sock, self.client_sock):
            if sock:
                try: sock.close()
                except: pass
        self.audio.terminate()
        self.root.destroy()


if __name__ == "__main__":
    app = VoiceLink()
    app.run()