import base64
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AURORA - navegador en Python (PyQt6 + QtWebEngine / Chromium)

Ejecuta:  python aurora_browser.py
"""
import os, sys, json, re, time, zipfile, shutil, html, copy, tempfile, uuid, base64
import importlib.util, traceback, threading, subprocess
import urllib.request, urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

try:
    import ctypes
except Exception:
    ctypes = None


def ensure_deps():
    # Si está compilado con PyInstaller, no hace falta instalar nada
    if getattr(sys, 'frozen', False):
        return
        
    try:
        import PyQt6.QtWebEngineWidgets  # noqa: F401
        return
    except Exception:
        pass

ensure_deps()

from PyQt6.QtCore import (Qt, QUrl, QTimer, QObject, pyqtSignal, QSize, QStringListModel,
                          QCoreApplication, QEvent)
from PyQt6.QtGui import (QIcon, QPixmap, QPainter, QColor, QFont, QKeySequence, QShortcut,
                         QDesktopServices, QAction, QPainterPath, QPen)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QToolButton, QPushButton, QListWidget,
                             QListWidgetItem, QComboBox, QSplitter, QMenu,
                             QProgressBar, QDialog, QFormLayout, QPlainTextEdit, QTextEdit,
                             QCheckBox, QMessageBox, QInputDialog, QFileDialog, QCompleter,
                             QTabWidget, QTabBar, QDialogButtonBox, QSizePolicy, QSizeGrip,
                             QColorDialog)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (QWebEngineProfile, QWebEnginePage, QWebEngineSettings,
                                   QWebEngineScript, QWebEngineUrlRequestInterceptor,
                                   QWebEngineUrlRequestInfo)

APP = "Aurora"
DATA = Path.home() / ".aurora"
EXT_DIR = DATA / "extensions"
for _d in (DATA, EXT_DIR, DATA / "profile"):
    _d.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------------------
# Ajustes persistentes — motores ampliados
# ----------------------------------------------------------------------------------------
ENGINES = {
    "DuckDuckGo": "https://duckduckgo.com/?q=",
    "Google": "https://www.google.com/search?q=",
    "Brave": "https://search.brave.com/search?q=",
    "Bing": "https://www.bing.com/search?q=",
    "Startpage": "https://www.startpage.com/do/search?q=",
    "Firefox (Mozilla)": "https://www.google.com/search?q=",
    "Ecosia": "https://www.ecosia.org/search?q=",
    "Qwant": "https://www.qwant.com/?q=",
    "Mojeek": "https://www.mojeek.com/search?q=",
    "Yahoo": "https://search.yahoo.com/search?p=",
    "SearXNG": "https://searx.be/search?q=",
}

DEFAULTS = {
    "theme": "Aurora", "engine": "DuckDuckGo", "home": "", "adblock": True, "doh": True,
    "doh_url": "https://dns.adguard-dns.com/resolve",
    "hosts_url": "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
    "aliases": {
        "yt": "https://www.youtube.com/results?search_query=%s",
        "gh": "https://github.com/search?q=%s",
        "w": "https://es.wikipedia.org/wiki/Special:Search?search=%s",
        "maps": "https://www.google.com/maps/search/%s",
        "r": "https://www.reddit.com/search/?q=%s",
        "gm": "https://mail.google.com",
        "tr": "https://translate.google.com/?sl=auto&tl=es&text=%s",
    },
    "speed_dial": [["YouTube", "https://www.youtube.com"], ["GitHub", "https://github.com"],
                   ["Wikipedia", "https://es.wikipedia.org"], ["Reddit", "https://www.reddit.com"],
                   ["Maps", "https://www.google.com/maps"], ["Twitch", "https://www.twitch.tv"]],
    "bookmarks": [], "history": [], "restore": True, "perms": {},
    "adblock_whitelist": [], "ext_disabled": [], "download_dir": str(Path.home() / "Downloads"),
    "catalog_url": "", "examples_done": False, "last_list_update": 0,
    "last_profile": "default", "prompt_profile_on_new_tab": True,
    # --- personalización (nuevo) ---
    "custom_bg": "",
    "profile_pic": "",
    "custom_theme": {"bg": "#1a1d24", "panel": "#22262f", "card": "#2b303c", "hover": "#2f3542",
                     "text": "#e4e7ec", "sub": "#8b92a1", "accent": "#5b8def", "border": "#323844"},
    "custom_engines": {},
    "pip_enabled": True,
}


class Store:
    def __init__(self):
        self.path = DATA / "settings.json"
        self.d = copy.deepcopy(DEFAULTS)
        try:
            loaded = json.loads(self.path.read_text("utf-8"))
            if isinstance(loaded, dict):
                self.d.update(loaded)
        except Exception:
            pass
        self.dirty = False

    def __getitem__(self, k):
        return self.d.get(k, copy.deepcopy(DEFAULTS.get(k)))

    def get(self, k, default=None):
        if k in self.d:
            return self.d[k]
        if k in DEFAULTS:
            return copy.deepcopy(DEFAULTS[k])
        return default

    def pop(self, k, default=None):
        return self.d.pop(k, default)

    def __contains__(self, k):
        return k in self.d

    def __setitem__(self, k, v):
        self.d[k] = v
        self.save()

    def save_soon(self):
        self.dirty = True

    def flush(self):
        if self.dirty:
            self.save()

    def save(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), "utf-8")
            os.replace(tmp, self.path)
            self.dirty = False
        except Exception:
            traceback.print_exc()


# ----------------------------------------------------------------------------------------
# Temas
# ----------------------------------------------------------------------------------------
THEMES = {
    "Aurora": dict(bg="#1a1d24", panel="#22262f", card="#2b303c", hover="#2f3542",
                   text="#e4e7ec", sub="#8b92a1", accent="#5b8def", border="#323844"),
    "Medianoche": dict(bg="#0d0d0f", panel="#161618", card="#1e1e21", hover="#242428",
                       text="#e8e8ea", sub="#8a8a8e", accent="#5b8def", border="#26262a"),
    "Nord": dict(bg="#2e3440", panel="#3b4252", card="#434c5e", hover="#4a5468",
                 text="#eceff4", sub="#a3acc0", accent="#88c0d0", border="#4c566a"),
    "Dracula": dict(bg="#282a36", panel="#21222c", card="#343746", hover="#3d4055",
                    text="#f8f8f2", sub="#9aa0c0", accent="#bd93f9", border="#44475a"),
    "Matrix": dict(bg="#020a04", panel="#04110a", card="#0a2214", hover="#0d2c1a",
                   text="#b6ffcb", sub="#4fa36b", accent="#00ff66", border="#0f3a20"),
    "Sakura": dict(bg="#f8f6f8", panel="#fdfbfd", card="#f2eef2", hover="#eee5ee",
                   text="#2d2530", sub="#8a7a88", accent="#c94c85", border="#e5dce5"),
    "Claro": dict(bg="#f8f9fb", panel="#ffffff", card="#eef0f4", hover="#e8ebf0",
                  text="#1a1d23", sub="#6b7280", accent="#2563eb", border="#e2e5ec"),
}

QSS = """
QWidget{background:@bg;color:@text;font-family:'Inter','Segoe UI','Noto Sans',sans-serif;font-size:13px}
QLabel{background:transparent}
QFrame#tabbar_wrap{background:@panel;border-bottom:1px solid @border}
QFrame#bar{background:@panel;border-bottom:1px solid @border}
QFrame#find{background:@panel;border-top:1px solid @border}
QWidget#dragSpace{background:@panel}
QLineEdit{background:@card;border:1px solid @border;border-radius:16px;padding:6px 14px;selection-background-color:@accent}
QLineEdit:focus{border:1px solid @accent}
QToolButton,QPushButton{background:transparent;border:none;border-radius:6px;padding:5px 8px;color:@text}
QToolButton:hover,QPushButton:hover{background:@card}
QToolButton::menu-indicator{image:none}
QPushButton#primary{background:@accent;color:white}
QToolButton#winBtn{background:transparent;border:none;border-radius:0;padding:0;color:@text}
QToolButton#winBtn:hover{background:@hover}
QToolButton#closeBtn{background:transparent;border:none;border-radius:0;padding:0;color:@text}
QToolButton#closeBtn:hover{background:#e81123;color:#ffffff}
QMenu{background:@panel;border:1px solid @border;padding:6px;border-radius:8px}
QMenu::item{padding:6px 22px;border-radius:4px}
QMenu::item:selected{background:@accent;color:white}
QMenu::separator{height:1px;background:@border;margin:5px 8px}
QProgressBar{background:transparent;border:none}
QProgressBar::chunk{background:@accent}
QScrollBar:vertical{background:transparent;width:10px}
QScrollBar::handle:vertical{background:@border;border-radius:5px;min-height:30px}
QScrollBar::add-line,QScrollBar::sub-line{height:0}
QToolTip{background:@card;color:@text;border:1px solid @border;padding:4px;border-radius:4px}
QStatusBar{background:@panel;color:@sub}
QTabBar#browser_tabs{background:transparent}
QTabBar#browser_tabs::tab{background:transparent;color:@sub;padding:6px 12px;margin:2px 1px 0 1px;
  border:none;border-radius:6px;min-width:100px;max-width:220px;text-align:left}
QTabBar#browser_tabs::tab:selected{background:@card;color:@text}
QTabBar#browser_tabs::tab:hover:!selected{background:@hover}
QTabBar#browser_tabs QToolButton{background:transparent;border:none;color:@sub;padding:2px}
QTabBar#browser_tabs QToolButton:hover{background:@hover;border-radius:4px;color:@text}
QComboBox,QPlainTextEdit,QTextEdit{background:@card;border:1px solid @border;border-radius:6px;padding:4px 8px}
QComboBox QAbstractItemView{background:@panel;selection-background-color:@accent}
QListWidget{background:transparent;border:none;outline:0}
QListWidget::item{border-radius:6px;margin:1px 2px;padding:6px}
QListWidget::item:selected{background:@card}
QListWidget::item:hover{background:@hover}
QTabWidget::pane{border:1px solid @border;border-radius:8px;top:-1px}
QTabWidget > QTabBar::tab{background:transparent;padding:8px 18px;border:none;border-bottom:2px solid transparent;margin-right:2px}
QTabWidget > QTabBar::tab:selected{color:@accent;border-bottom:2px solid @accent}
QTabWidget > QTabBar::tab:hover:!selected{background:@hover}
"""


def make_qss(t):
    q = QSS
    for k, v in t.items():
        q = q.replace("@" + k, v)
    return q


# ----------------------------------------------------------------------------------------
# Media utils (fondo / avatar)
# ----------------------------------------------------------------------------------------
_VIDEO_EXTS = (".mp4", ".webm", ".ogv", ".ogg", ".mov", ".m4v")


def _is_video_spec(spec):
    if not spec:
        return False
    if spec.startswith("data:"):
        return "video/" in spec.split(";")[0]
    return spec.lower().split("?")[0].split("#")[0].endswith(_VIDEO_EXTS)


def _file_to_data_url(path):
    try:
        p = Path(path)
        if not p.is_file():
            return ""
        ext = p.suffix.lower()
        mimes = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
                 ".webp": "image/webp", ".svg": "image/svg+xml", ".bmp": "image/bmp",
                 ".mp4": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg", ".ogg": "video/ogg",
                 ".mov": "video/quicktime", ".m4v": "video/mp4"}
        mime = mimes.get(ext, "application/octet-stream")
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        return "data:%s;base64,%s" % (mime, data)
    except Exception:
        traceback.print_exc()
        return ""


def media_src(spec):
    if not spec:
        return ""
    if spec.startswith(("http://", "https://", "data:")):
        return spec
    path = QUrl(spec).toLocalFile() if spec.startswith("file://") else spec
    return _file_to_data_url(path)


def make_bg_content(spec):
    if not spec:
        return ""
    src = media_src(spec)
    if not src:
        return ""
    if _is_video_spec(spec):
        return '<video autoplay loop muted playsinline src="%s"></video>' % html.escape(src, True)
    return '<img src="%s" alt="">' % html.escape(src, True)


# ----------------------------------------------------------------------------------------
# Colores de grupo / perfiles
# ----------------------------------------------------------------------------------------
GROUP_COLORS = {
    "red":    "#e05c5c", "orange": "#e0885c", "yellow": "#d9b23c",
    "green":  "#5cb87a", "cyan":   "#5cc8e0", "blue":   "#5b8def",
    "purple": "#a05ce0", "pink":   "#e05c9e",
}
GROUP_LABELS = {
    "red": "Rojo", "orange": "Naranja", "yellow": "Amarillo", "green": "Verde",
    "cyan": "Cian", "blue": "Azul", "purple": "Púrpura", "pink": "Rosa",
}
PROFILE_COLORS = ["#5b8def", "#5cb87a", "#e0885c", "#a05ce0",
                  "#e05c9e", "#d9b23c", "#5cc8e0", "#e05c5c"]


class ColorTabBar(QTabBar):
    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i in range(self.count()):
            data = self.tabData(i)
            if not isinstance(data, dict):
                continue
            r = self.tabRect(i)
            if r.isEmpty():
                continue
            g = data.get("g")
            if g:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(g))
                bar_h = max(8, r.height() - 16)
                p.drawRoundedRect(r.x() + 2, r.y() + 10, 3, bar_h, 1.5, 1.5)
            pc = data.get("p")
            if pc:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(pc))
                p.drawEllipse(r.x() + 3, r.y() + 3, 6, 6)
        p.end()


# ----------------------------------------------------------------------------------------
# Iconos vectoriales
# ----------------------------------------------------------------------------------------
def win_icon(kind, color="#e4e7ec", size=10):
    s = max(size, 10) * 2
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(2)
    p.setPen(pen)
    if kind == "min":
        p.drawLine(int(s * 0.22), s // 2, int(s * 0.78), s // 2)
    elif kind == "max":
        p.drawRect(int(s * 0.22), int(s * 0.22), int(s * 0.56), int(s * 0.56))
    elif kind == "restore":
        p.drawRect(int(s * 0.34), int(s * 0.34), int(s * 0.46), int(s * 0.46))
        p.drawLine(int(s * 0.34), int(s * 0.34), int(s * 0.34), int(s * 0.20))
        p.drawLine(int(s * 0.34), int(s * 0.20), int(s * 0.80), int(s * 0.20))
        p.drawLine(int(s * 0.80), int(s * 0.20), int(s * 0.80), int(s * 0.66))
        p.drawLine(int(s * 0.80), int(s * 0.66), int(s * 0.66), int(s * 0.66))
    elif kind == "close":
        p.drawLine(int(s * 0.24), int(s * 0.24), int(s * 0.76), int(s * 0.76))
        p.drawLine(int(s * 0.76), int(s * 0.24), int(s * 0.24), int(s * 0.76))
    p.end()
    return QIcon(pm)


def letter_icon(ch, color):
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 28, 28, 7, 7)
    p.setPen(QColor("white"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(18)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, ch)
    p.end()
    return QIcon(pm)


def make_avatar_icon(color, initial, size=20):
    s = size * 2
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, s, s)
    p.setPen(QColor("white"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(int(s * 0.55))
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, initial)
    p.end()
    return QIcon(pm)


def make_circular_icon(pm, size=20):
    s = size * 2
    pm = pm.scaled(s, s, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    out = QPixmap(s, s)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, s, s)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return QIcon(out)


def get_avatar_icon(core, pid, size=20):
    pic = core.store.get("profile_pic", "")
    if pic:
        if not pic.startswith(("http://", "https://", "data:")):
            p = Path(QUrl(pic).toLocalFile() if pic.startswith("file://") else pic)
            if p.is_file():
                pm = QPixmap(str(p))
                if not pm.isNull():
                    return make_circular_icon(pm, size)
    
    color = core.profile_color(pid)
    name = core.profile_name(pid)
    return make_avatar_icon(color, name[:1].upper() or "?", size)


def shield_icon(color="#5b8def", size=20):
    s = size * 2
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    path = QPainterPath()
    path.moveTo(s * 0.5, s * 0.12)
    path.lineTo(s * 0.86, s * 0.28)
    path.lineTo(s * 0.86, s * 0.55)
    path.cubicTo(s * 0.86, s * 0.76, s * 0.70, s * 0.88, s * 0.5, s * 0.92)
    path.cubicTo(s * 0.30, s * 0.88, s * 0.14, s * 0.76, s * 0.14, s * 0.55)
    path.lineTo(s * 0.14, s * 0.28)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def globe_icon(color="#8b92a1", size=16):
    s = size * 2
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(2, 2, s - 4, s - 4)
    p.drawLine(2, s // 2, s - 2, s // 2)
    p.drawEllipse(s // 2 - s // 4, 2, s // 2, s - 4)
    p.end()
    return QIcon(pm)


def search_icon(color="#8b92a1", size=16):
    s = size * 2
    pm = QPixmap(s, s)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(2)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    r = int(s * 0.28)
    p.drawEllipse(int(s * 0.15), int(s * 0.15), r * 2, r * 2)
    p.drawLine(int(s * 0.15) + r * 2 - 3, int(s * 0.15) + r * 2 - 3,
               int(s * 0.85), int(s * 0.85))
    p.end()
    return QIcon(pm)


# ----------------------------------------------------------------------------------------
# Controles de ventana + drag space
# ----------------------------------------------------------------------------------------
class WindowControls(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.min_btn = self._btn("min", "Minimizar", self.window.showMinimized)
        self.max_btn = self._btn("max", "Maximizar", self._toggle_max)
        self.close_btn = self._btn("close", "Cerrar", self.window.close, obj="closeBtn")
        lay.addWidget(self.min_btn)
        lay.addWidget(self.max_btn)
        lay.addWidget(self.close_btn)

    def _btn(self, kind, tip, fn, obj="winBtn"):
        b = QToolButton()
        b.setObjectName(obj)
        b.setIcon(win_icon(kind))
        b.setIconSize(QSize(10, 10))
        b.setFixedSize(46, 32)
        b.setToolTip(tip)
        b.clicked.connect(lambda _=False: fn())
        return b

    def _toggle_max(self):
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    def refresh(self):
        if self.window.isMaximized():
            self.max_btn.setIcon(win_icon("restore"))
            self.max_btn.setToolTip("Restaurar")
        else:
            self.max_btn.setIcon(win_icon("max"))
            self.max_btn.setToolTip("Maximizar")


class DragSpace(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setObjectName("dragSpace")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            wh = self.window.windowHandle()
            if wh:
                wh.startSystemMove()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.window.isMaximized():
                self.window.showNormal()
            else:
                self.window.showMaximized()
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)


# ----------------------------------------------------------------------------------------
# Bloqueo DNS / anuncios
# ----------------------------------------------------------------------------------------
DEFAULT_BLOCK = """doubleclick.net googlesyndication.com googleadservices.com google-analytics.com
googletagmanager.com googletagservices.com adservice.google.com adnxs.com adsrvr.org adform.net
advertising.com amazon-adsystem.com criteo.com criteo.net taboola.com outbrain.com rubiconproject.com
pubmatic.com openx.net casalemedia.com contextweb.com yieldmo.com smartadserver.com moatads.com
scorecardresearch.com quantserve.com hotjar.com mixpanel.com segment.io fullstory.com
facebook.net connect.facebook.net ads.twitter.com analytics.twitter.com ads-twitter.com
ads.linkedin.com ads.pinterest.com ads.tiktok.com analytics.tiktok.com bat.bing.com
adcolony.com applovin.com unity3ds.com unityads.unity3d.com vungle.com chartboost.com
mopub.com inmobi.com flurry.com branch.io adjust.com appsflyer.com kochava.com
zedo.com popads.net popcash.net propellerads.com exoclick.com juicyads.com trafficjunky.net
revcontent.com mgid.com sharethrough.com 33across.com indexww.com lijit.com sovrn.com
adsafeprotected.com doubleverify.com serving-sys.com mathtag.com bluekai.com demdex.net
krxd.net agkn.com rlcdn.com tapad.com id5-sync.com liadm.com yandex.ru/ads adskeeper.com
ads.yahoo.com advertising.yahoo.com ad.doubleclick.net pagead2.googlesyndication.com""".split()
DEFAULT_BLOCK = {h for h in DEFAULT_BLOCK if "/" not in h}

URL_PATTERNS = ("/pagead/", "/adsbygoogle", "googleadservices", "/ads/ga-audiences", "amazon-adsystem",
                "/adserver/", "/banners/ad", "adservice.google")

COSMETIC_CSS = (".adsbygoogle,ins.adsbygoogle,[id^='google_ads'],[id^='div-gpt-ad'],[class*='ad-banner'],"
                "[class*='advert'],[aria-label='Advertisement'],[data-ad-slot],.ytd-ad-slot-renderer,"
                "#masthead-ad,ytd-promoted-sparkles-web-renderer,ytd-display-ad-renderer,"
                "ytd-in-feed-ad-layout-renderer,.ytp-ad-overlay-container{display:none!important}")
COSMETIC_JS = r"""(function(){
 try{var s=document.createElement('style');s.textContent=%CSS%;(document.head||document.documentElement).appendChild(s);}catch(e){}
 if(/(^|\.)youtube\.com$/.test(location.hostname)){
  setInterval(function(){
   var v=document.querySelector('video'),p=document.querySelector('.html5-video-player');
   if(p&&p.classList.contains('ad-showing')&&v&&isFinite(v.duration)){v.muted=true;v.currentTime=v.duration;}
   var b=document.querySelector('.ytp-skip-ad-button,.ytp-ad-skip-button,.ytp-ad-skip-button-modern');if(b)b.click();
  },400);
 }
})();""".replace("%CSS%", json.dumps(COSMETIC_CSS))

# Detector de doble clic derecho sobre <video> -> abre PiP propio
PIP_JS = r"""(function(){
 if(window.__aurora_pip_installed)return;window.__aurora_pip_installed=true;
 var last=0,target=null;
 document.addEventListener('contextmenu',function(e){
  var v=e.target&&e.target.closest&&e.target.closest('video');
  if(!v){last=0;target=null;return;}
  var now=Date.now();
  if(target===v&&now-last<700){
   e.preventDefault();e.stopPropagation();
   var data={src:v.currentSrc||v.src||'',time:v.currentTime||0,poster:v.poster||'',
             paused:!!v.paused,page_url:location.href};
   try{console.log('AURORA_PIP:'+JSON.stringify(data));}catch(err){}
   last=0;target=null;
  }else{last=now;target=v;}
 },true);
})();
"""


def _base(host):
    p = host.split(".")
    return ".".join(p[-2:])


class Blocker(QWebEngineUrlRequestInterceptor):
    updated = pyqtSignal(int)

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.hosts = set(DEFAULT_BLOCK)
        self.extra = set()
        self.count = 0
        self.doh_cache = {}
        self.pending = set()
        self.pool = ThreadPoolExecutor(3)
        self.whitelist = set(store["adblock_whitelist"] or [])
        self.load_file()

    def load_file(self):
        f = DATA / "hosts.txt"
        if f.exists():
            try:
                self.hosts |= {ln.strip() for ln in f.read_text("utf-8").splitlines() if ln.strip()}
            except Exception:
                pass

    def is_blocked(self, host):
        p = host.split(".")
        for i in range(len(p) - 1):
            h = ".".join(p[i:])
            if h in self.hosts or h in self.extra:
                return True
        return False

    def doh_check(self, host):
        try:
            u = self.store["doh_url"] + "?" + urllib.parse.urlencode({"name": host, "type": "A"})
            req = urllib.request.Request(u, headers={"accept": "application/dns-json"})
            with urllib.request.urlopen(req, timeout=4) as r:
                j = json.load(r)
            ans = [a.get("data", "") for a in j.get("Answer", [])]
            self.doh_cache[host] = any(a in ("0.0.0.0", "::") for a in ans)
        except Exception:
            self.doh_cache[host] = False
        finally:
            self.pending.discard(host)

    def interceptRequest(self, info):
        try:
            if not self.store["adblock"]:
                return
            if info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame:
                return
            url = info.requestUrl()
            host = url.host().lower()
            if not host:
                return
            fp = info.firstPartyUrl().host().lower()
            if fp and (fp in self.whitelist or _base(fp) in self.whitelist):
                return
            bad = self.is_blocked(host)
            third = bool(fp) and _base(host) != _base(fp)
            if not bad and third:
                s = url.toString()
                if any(p in s for p in URL_PATTERNS):
                    bad = True
                elif self.store["doh"]:
                    c = self.doh_cache.get(host)
                    if c is None and host not in self.pending and len(self.pending) < 40:
                        self.pending.add(host)
                        self.pool.submit(self.doh_check, host)
                    elif c:
                        bad = True
            if bad:
                info.block(True)
                self.count += 1
        except Exception:
            pass

    def update_lists(self):
        def run():
            try:
                req = urllib.request.Request(self.store["hosts_url"], headers={"User-Agent": "Aurora"})
                data = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
                out = set()
                for ln in data.splitlines():
                    ln = ln.split("#")[0].strip().split()
                    if len(ln) >= 2 and ln[0] in ("0.0.0.0", "127.0.0.1") and "." in ln[1]:
                        out.add(ln[1].lower())
                (DATA / "hosts.txt").write_text("\n".join(sorted(out)), "utf-8")
                self.hosts |= out
                self.store["last_list_update"] = int(time.time())
                self.updated.emit(len(out))
            except Exception:
                self.updated.emit(-1)
        threading.Thread(target=run, daemon=True).start()


# ----------------------------------------------------------------------------------------
# Disfraces / embed
# ----------------------------------------------------------------------------------------
DISGUISES = [
    ("Documento sin titulo - Documentos de Google", "D", "#4285f4"),
    ("Bandeja de entrada - Gmail", "M", "#ea4335"),
    ("Classroom - Tareas", "C", "#0f9d58"),
    ("Hoja de calculo sin titulo - Hojas de calculo", "S", "#188038"),
    ("Presentacion sin titulo - Presentaciones", "P", "#f4b400"),
    ("Wikipedia, la enciclopedia libre", "W", "#777777"),
]


def embed_html(u):
    try:
        p = urllib.parse.urlparse(u)
        h = p.netloc.lower().replace("www.", "")
        q = urllib.parse.parse_qs(p.query)
        src = None
        if h in ("youtube.com", "m.youtube.com", "music.youtube.com") and "v" in q:
            src = "https://www.youtube.com/embed/%s?autoplay=1" % q["v"][0]
        elif h == "youtu.be":
            src = "https://www.youtube.com/embed/%s?autoplay=1" % p.path.strip("/")
        elif h == "vimeo.com" and p.path.strip("/").isdigit():
            src = "https://player.vimeo.com/video/%s?autoplay=1" % p.path.strip("/")
        if not src:
            return None
        return ("<html><body style='margin:0;background:#000'>"
                "<iframe src='%s' style='border:0;width:100vw;height:100vh' "
                "allow='autoplay; fullscreen; picture-in-picture; encrypted-media' allowfullscreen>"
                "</iframe></body></html>" % src)
    except Exception:
        return None


# ----------------------------------------------------------------------------------------
# Nueva pestaña (con edición de accesos directos integrada)
# ----------------------------------------------------------------------------------------
NEWTAB = r"""<!doctype html><html><head><meta charset="utf-8"><title>Nueva pestaña</title><style>
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{display:flex;flex-direction:column;align-items:center;justify-content:center;
 background:@bg;color:@text;font-family:'Inter','Segoe UI',system-ui,sans-serif;padding:24px;position:relative}
#bg{position:fixed;inset:0;z-index:-2;overflow:hidden}
#bg video,#bg img{width:100%;height:100%;object-fit:cover;display:block}
#bg::after{content:'';position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,0.20),rgba(0,0,0,0.55))}
.logo{font-size:56px;font-weight:200;letter-spacing:-1.5px;color:@text;margin-bottom:34px;text-shadow:0 4px 20px rgba(0,0,0,0.6);display:flex;align-items:baseline;justify-content:center}
.logo b{color:@accent;font-weight:400;font-size:88px;line-height:1;text-shadow:0 0 15px @accent;margin-right:4px;font-family:'Gabriola', cursive}
form{width:min(620px,86vw)}
input{width:100%;padding:14px 22px;font-size:16px;border-radius:24px;border:1px solid @border;
 background:@panel;color:@text;outline:none}
input:focus{border-color:@accent}
input::placeholder{color:@sub}
.g{display:grid;grid-template-columns:repeat(6,88px);gap:14px;margin-top:38px}
.t{display:flex;flex-direction:column;align-items:center;gap:8px;text-decoration:none;color:@text;
 font-size:12px;padding:10px;border-radius:10px;text-shadow:0 1px 8px rgba(0,0,0,0.7)}
.t:hover{background:@panel}
.t i{font-style:normal;width:48px;height:48px;border-radius:12px;background:@card;color:@accent;
 display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:500;border:1px solid @border}
.t span{max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center}
</style></head><body>%%BG_CONTENT%%<div class="logo"><b>A</b>urora</div>
<form id="f"><input id="q" autofocus autocomplete="off" placeholder="Buscar o escribir una URL"></form>
<div class="g" id="grid">@tiles</div>
<script>var E=@engine;
document.getElementById('f').onsubmit=function(e){e.preventDefault();var q=document.getElementById('q').value.trim();
if(!q)return;
if(/^[^\s\/]+\.[a-z]{2,}(\/.*)?$/i.test(q))location.href='https://'+q;
else if(/^https?:\/\//i.test(q))location.href=q;
else location.href=E+encodeURIComponent(q);};
</script></body></html>"""


# ----------------------------------------------------------------------------------------
# Gestor de perfiles
# ----------------------------------------------------------------------------------------
class ProfileManager:
    def __init__(self):
        self.meta_path = DATA / "profiles.json"
        self.profiles_dir = DATA / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.profiles = self._load()
        if not self.profiles:
            self.profiles = [{"id": "default", "name": "Personal",
                              "color": PROFILE_COLORS[0], "created": int(time.time())}]
            self._save()

    def _load(self):
        try:
            data = json.loads(self.meta_path.read_text("utf-8"))
            return data.get("profiles", [])
        except Exception:
            return []

    def _save(self):
        try:
            self.meta_path.write_text(
                json.dumps({"profiles": self.profiles}, ensure_ascii=False, indent=1), "utf-8")
        except Exception:
            traceback.print_exc()

    def list(self):
        return list(self.profiles)

    def get(self, pid):
        for p in self.profiles:
            if p["id"] == pid:
                return p
        return None

    def storage_dirs(self, pid):
        if pid == "default":
            base = DATA / "profile"
        else:
            base = self.profiles_dir / pid
        return base / "storage", base / "cache"

    def create(self, name):
        used = {p["color"] for p in self.profiles}
        color = next((c for c in PROFILE_COLORS if c not in used), PROFILE_COLORS[0])
        pid = "p" + uuid.uuid4().hex[:10]
        entry = {"id": pid, "name": name, "color": color, "created": int(time.time())}
        self.profiles.append(entry)
        self._save()
        return entry

    def rename(self, pid, name):
        for p in self.profiles:
            if p["id"] == pid:
                p["name"] = name
                self._save()
                return True
        return False

    def delete(self, pid):
        if pid == "default":
            return False
        self.profiles = [p for p in self.profiles if p["id"] != pid]
        self._save()
        shutil.rmtree(self.profiles_dir / pid, ignore_errors=True)
        return True


# ----------------------------------------------------------------------------------------
# Extensiones
# ----------------------------------------------------------------------------------------
class TabAPI:
    def __init__(self, tab):
        self._t = tab

    @property
    def url(self):
        return self._t.view.url().toString()

    @property
    def title(self):
        return self._t.title

    def run_js(self, code, callback=None):
        if callback:
            self._t.view.page().runJavaScript(code, callback)
        else:
            self._t.view.page().runJavaScript(code)

    def load(self, url):
        self._t.view.load(QUrl(url))

    def reload(self):
        self._t.view.reload()


class Ext:
    def __init__(self, id_, path, man):
        self.id, self.path, self.man = id_, path, man
        self.enabled = True
        self.error = ""


class ExtAPI:
    def __init__(self, core, ext):
        self.core, self.ext = core, ext
        self.data_dir = DATA / "ext_data" / ext.id
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def add_toolbar_button(self, text, callback, tooltip=""):
        self.core.ext_buttons.append((self.ext.id, text, callback, tooltip))
        self.core.refresh_ext_ui()

    def add_menu_action(self, text, callback, shortcut=None):
        self.core.ext_menu.append((self.ext.id, text, callback, shortcut))
        self.core.refresh_ext_ui()

    def add_command(self, name, callback):
        self.core.ext_cmds.append((self.ext.id, name, callback))

    def on(self, event, callback):
        self.core.hooks.setdefault(event, []).append((self.ext.id, callback))

    def inject_css(self, css, matches=None):
        js = "(function(){var s=document.createElement('style');s.textContent=%s;(document.head||document.documentElement).appendChild(s)})();" % json.dumps(css)
        self.inject_js(js, matches)

    def inject_js(self, js, matches=None):
        self.core.add_script("ext:%s:%d" % (self.ext.id, len(self.core.scripts)), js, matches)

    def add_blocklist(self, domains):
        self.core.blocker.extra |= {d.lower().strip() for d in domains}

    def current_tab(self):
        w = self.core.active_window()
        return TabAPI(w.cur) if w and w.cur else None

    def open_url(self, url, background=False):
        w = self.core.active_window()
        if w:
            w.new_tab(url, background=background)

    def notify(self, text):
        w = self.core.active_window()
        if w:
            w.statusBar().showMessage("[%s] %s" % (self.ext.man.get("name", self.ext.id), text), 6000)

    def storage_get(self, key, default=None):
        try:
            return json.loads((self.data_dir / "storage.json").read_text("utf-8")).get(key, default)
        except Exception:
            return default

    def storage_set(self, key, value):
        f = self.data_dir / "storage.json"
        try:
            d = json.loads(f.read_text("utf-8"))
        except Exception:
            d = {}
        d[key] = value
        f.write_text(json.dumps(d), "utf-8")


EXAMPLE_READER = '''READER = "(function(){var i='aurora-reader',e=document.getElementById(i);if(e){e.remove();return}var s=document.createElement('style');s.id=i;s.textContent='header,footer,nav,aside,[role=banner],[class*=sidebar],[class*=cookie],[class*=popup]{display:none!important}body{max-width:760px!important;margin:40px auto!important;padding:0 20px!important;font:20px/1.75 Georgia,serif!important;background:#faf6ee!important;color:#222!important}img{max-width:100%!important}';document.head.appendChild(s)})();"


def run():
    t = API.current_tab()
    if t:
        t.run_js(READER)


API = None


def register(api):
    global API
    API = api
    api.add_toolbar_button("Aa", run, "Modo lectura")
    api.add_command("Modo lectura", run)
'''

EXAMPLE_DARK = '''JS = "(function(){var i='aurora-dark',e=document.getElementById(i);if(e){e.remove();return}var s=document.createElement('style');s.id=i;s.textContent='html{filter:invert(1) hue-rotate(180deg)!important}img,video,picture,canvas{filter:invert(1) hue-rotate(180deg)!important}';document.head.appendChild(s)})();"


def register(api):
    def toggle():
        t = api.current_tab()
        if t:
            t.run_js(JS)
    api.add_menu_action("Oscuro forzado en esta pagina", toggle, "Ctrl+Shift+D")
    api.add_command("Oscuro forzado", toggle)
'''


def install_examples():
    ex = {
        "modo-lectura": ({"id": "modo-lectura", "name": "Modo lectura", "version": "1.0", "author": "Aurora",
                          "description": "Limpia la pagina para leer comodo. Boton en la barra."}, EXAMPLE_READER),
        "oscuro-forzado": ({"id": "oscuro-forzado", "name": "Oscuro forzado", "version": "1.0", "author": "Aurora",
                            "description": "Invierte colores de cualquier pagina (Ctrl+Shift+D desde el menu)."}, EXAMPLE_DARK),
    }
    for k, (man, code) in ex.items():
        d = EXT_DIR / k
        d.mkdir(exist_ok=True)
        (d / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), "utf-8")
        (d / "main.py").write_text(code, "utf-8")


# ----------------------------------------------------------------------------------------
# Núcleo
# ----------------------------------------------------------------------------------------
class DownloadRec:
    def __init__(self, d, path):
        self.d, self.path = d, path


class Core(QObject):
    cat_loaded = pyqtSignal(object)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.store = Store()
        self.pm = ProfileManager()
        self.blocker = Blocker(self.store)
        self.windows, self.hooks = [], {}
        self.profile_instances = {}
        self.private_profiles = []
        self.ext_buttons, self.ext_menu, self.ext_cmds = [], [], []
        self.exts, self.scripts, self.downloads, self.minis = {}, {}, [], []
        self.cosm = None
        self.pip_script = None
        self.panicking = False

    def all_profiles(self):
        return list(self.profile_instances.values()) + list(self.private_profiles)

    # -- tema / motores ---------------------------------------------------------------
    def current_theme(self):
        name = self.store["theme"]
        if name == "Personalizado":
            base = dict(THEMES["Aurora"])
            base.update(self.store.get("custom_theme") or {})
            return base
        return THEMES.get(name, THEMES["Aurora"])

    def all_engines(self):
        d = dict(ENGINES)
        custom = self.store.get("custom_engines") or {}
        if isinstance(custom, dict):
            d.update(custom)
        return d

    def engine_url(self):
        return self.all_engines().get(self.store["engine"], ENGINES["DuckDuckGo"])

    # -- scripts ----------------------------------------------------------------------
    def make_script(self, name, js, point=QWebEngineScript.InjectionPoint.DocumentReady):
        s = QWebEngineScript()
        s.setName(name)
        s.setSourceCode(js)
        s.setInjectionPoint(point)
        s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        s.setRunsOnSubFrames(False)
        return s

    def add_script(self, name, js, matches=None):
        if matches:
            rx = [".*".join(re.escape(x) for x in m.split("*")) for m in matches]
            js = "(function(){var ok=%s.some(function(r){return new RegExp('^'+r+'$').test(location.href)});if(!ok)return;\n%s\n})();" % (json.dumps(rx), js)
        s = self.make_script(name, js)
        self.scripts[name] = s
        for p in self.all_profiles():
            try:
                p.scripts().insert(s)
            except Exception:
                pass

    def remove_scripts(self, prefix):
        for n in [n for n in self.scripts if n.startswith(prefix)]:
            s = self.scripts.pop(n)
            for p in self.all_profiles():
                try:
                    p.scripts().remove(s)
                except Exception:
                    pass

    def apply_adblock_scripts(self):
        for p in self.all_profiles():
            try:
                p.scripts().remove(self.cosm)
            except Exception:
                pass
            if self.store["adblock"] and self.cosm:
                try:
                    p.scripts().insert(self.cosm)
                except Exception:
                    pass

    def apply_pip_scripts(self):
        if self.pip_script is None:
            self.pip_script = self.make_script("aurora-pip", PIP_JS)
        for p in self.all_profiles():
            try:
                p.scripts().remove(self.pip_script)
            except Exception:
                pass
            if self.store.get("pip_enabled", True):
                try:
                    p.scripts().insert(self.pip_script)
                except Exception:
                    pass

    # -- perfiles ---------------------------------------------------------------------
    def make_profile(self, profile_id="default", private=False):
        if private:
            p = QWebEngineProfile(self.app)
            self.private_profiles.append(p)
        else:
            if profile_id in self.profile_instances:
                return self.profile_instances[profile_id]
            p = QWebEngineProfile(profile_id, self.app)
            storage_dir, cache_dir = self.pm.storage_dirs(profile_id)
            storage_dir.mkdir(parents=True, exist_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)
            p.setPersistentStoragePath(str(storage_dir))
            p.setCachePath(str(cache_dir))
            p.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
            self.profile_instances[profile_id] = p

        p.setUrlRequestInterceptor(self.blocker)
        p.downloadRequested.connect(self.on_download)
        if self.cosm is None:
            self.cosm = self.make_script("aurora-cosmetic", COSMETIC_JS)
        if self.store["adblock"]:
            try:
                p.scripts().insert(self.cosm)
            except Exception:
                pass
        if self.pip_script is None:
            self.pip_script = self.make_script("aurora-pip", PIP_JS)
        if self.store.get("pip_enabled", True):
            try:
                p.scripts().insert(self.pip_script)
            except Exception:
                pass
        for s in self.scripts.values():
            try:
                p.scripts().insert(s)
            except Exception:
                pass
        return p

    def forget_profile(self, pid):
        self.profile_instances.pop(pid, None)

    def profile_color(self, pid):
        meta = self.pm.get(pid)
        return meta.get("color", "#5b8def") if meta else "#5b8def"

    def profile_name(self, pid):
        meta = self.pm.get(pid)
        return meta.get("name", "?") if meta else "?"

    # -- descargas --------------------------------------------------------------------
    def on_download(self, d):
        try:
            folder = Path(self.store["download_dir"])
            folder.mkdir(parents=True, exist_ok=True)
            name = d.downloadFileName() or "descarga"
            stem, suf = os.path.splitext(name)
            n, final = 1, name
            while (folder / final).exists():
                final = "%s (%d)%s" % (stem, n, suf)
                n += 1
            d.setDownloadDirectory(str(folder))
            d.setDownloadFileName(final)
            d.accept()
            rec = DownloadRec(d, str(folder / final))
            self.downloads.append(rec)
            try:
                d.isFinishedChanged.connect(lambda r=rec: self.fire("download_finished", r.path))
            except Exception:
                pass
            w = self.active_window()
            if w:
                w.statusBar().showMessage("Descargando " + final, 5000)
        except Exception:
            traceback.print_exc()

    def fire(self, ev, *args):
        for _id, cb in list(self.hooks.get(ev, [])):
            try:
                cb(*args)
            except Exception:
                traceback.print_exc()

    def active_window(self):
        w = QApplication.activeWindow()
        if isinstance(w, BrowserWindow):
            return w
        return self.windows[0] if self.windows else None

    def refresh_ext_ui(self):
        for w in self.windows:
            w.rebuild_ext_ui()

    def refresh_profiles_ui(self):
        for w in self.windows:
            try:
                w.refresh_profile_ui()
                w.sync_tabbar()
            except Exception:
                traceback.print_exc()

    # -- extensiones ------------------------------------------------------------------
    def load_extensions(self):
        self.exts.clear()
        for d in sorted(EXT_DIR.iterdir()):
            if d.is_dir() and (d / "manifest.json").exists():
                self.load_ext(d)

    def load_ext(self, path):
        try:
            man = json.loads((path / "manifest.json").read_text("utf-8"))
        except Exception:
            return
        eid = man.get("id") or path.name
        ext = Ext(eid, path, man)
        self.exts[eid] = ext
        if eid in self.store["ext_disabled"]:
            ext.enabled = False
            return
        try:
            spec = importlib.util.spec_from_file_location("aurora_ext_" + re.sub(r"\W", "_", eid), path / man.get("main", "main.py"))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            mod.register(ExtAPI(self, ext))
        except Exception:
            ext.error = traceback.format_exc()
            print("Error en extension", eid, ext.error)

    def unload_ext(self, eid):
        self.ext_buttons = [x for x in self.ext_buttons if x[0] != eid]
        self.ext_menu = [x for x in self.ext_menu if x[0] != eid]
        self.ext_cmds = [x for x in self.ext_cmds if x[0] != eid]
        for k in self.hooks:
            self.hooks[k] = [x for x in self.hooks[k] if x[0] != eid]
        self.remove_scripts("ext:%s:" % eid)

    def reload_extensions(self):
        for eid in list(self.exts):
            self.unload_ext(eid)
        self.load_extensions()
        self.refresh_ext_ui()

    def install_zip(self, zpath):
        tmp = Path(tempfile.mkdtemp())
        try:
            with zipfile.ZipFile(zpath) as z:
                for m in z.namelist():
                    if not (tmp / m).resolve().is_relative_to(tmp.resolve()):
                        raise ValueError("Ruta insegura en el zip")
                z.extractall(tmp)
            return self.install_dir(self.find_manifest_dir(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def find_manifest_dir(self, root):
        if (root / "manifest.json").exists():
            return root
        for sub in root.iterdir():
            if sub.is_dir() and (sub / "manifest.json").exists():
                return sub
        raise ValueError("No hay manifest.json")

    def install_dir(self, src):
        src = Path(src)
        man = json.loads((src / "manifest.json").read_text("utf-8"))
        eid = str(man.get("id") or src.name)
        if not re.fullmatch(r"[a-z0-9_-]{2,40}", eid):
            raise ValueError("id invalido (usa a-z, 0-9, - o _)")
        if not (src / man.get("main", "main.py")).exists():
            raise ValueError("Falta el archivo main")
        dst = EXT_DIR / eid
        if dst.exists():
            self.unload_ext(eid)
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        self.reload_extensions()
        return eid

    # -- tema / nueva pestaña ---------------------------------------------------------
    def apply_theme(self):
        self.app.setStyleSheet(make_qss(self.current_theme()))
        for w in self.windows:
            try:
                w.reload_newtabs()
            except Exception:
                pass

    def newtab_html(self):
        t = dict(self.current_theme())

        parts = []
        for i, (n, u) in enumerate(self.store["speed_dial"]):
            try:
                n = str(n)
                u = str(u)
            except Exception:
                continue
            initial = (n[:1] or "?").upper()
            parts.append(
                '<a class="t" href="%s" title="%s">'
                '<i>%s</i><span>%s</span>'
                '</a>' % (
                    html.escape(u, True), html.escape(u, True),
                    html.escape(initial), html.escape(n)))

        tiles = "".join(parts)

        bg = self.store.get("custom_bg", "") or ""
        bg_content = ('<div id="bg">%s</div>' % make_bg_content(bg)) if bg else ""

        page = (NEWTAB
                .replace("%%BG_CONTENT%%", bg_content)
                .replace("@tiles", tiles)
                .replace("@engine", json.dumps(self.engine_url())))
        for k, v in t.items():
            page = page.replace("@" + k, v)
        return page

    def new_window(self, profile_id=None, private=False):
        if profile_id is None:
            profile_id = "default" if private else self.store["last_profile"]
        if not private and not self.pm.get(profile_id):
            profile_id = "default"
        w = BrowserWindow(self, profile_id=profile_id, private=private)
        self.windows.append(w)
        w.show()
        return w

    def start(self):
        if not self.store["examples_done"] and not any(EXT_DIR.iterdir()):
            install_examples()
        self.store["examples_done"] = True
        self.apply_theme()
        self.load_extensions()
        self.flush = QTimer(self)
        self.flush.timeout.connect(self.store.flush)
        self.flush.start(4000)
        try:
            self.app.aboutToQuit.connect(self.store.save)
        except Exception:
            pass
        w = self.new_window()
        w.restore_session()
        self.fire("startup")
        if time.time() - int(self.store["last_list_update"] or 0) > 3 * 86400:
            self.blocker.update_lists()


# ----------------------------------------------------------------------------------------
# Pestaña / página
# ----------------------------------------------------------------------------------------
class Tab:
    def __init__(self, view, profile_id="default"):
        self.view = view
        self.profile_id = profile_id
        self.pinned = False
        self.disguise = None
        self.newtab = False
        self.title = ""
        self.icon = QIcon()
        self.loading = False
        self.group = None

    def shown_title(self):
        if self.disguise:
            return self.disguise["title"]
        return self.title or ("Nueva pestaña" if self.newtab else "Cargando...")

    def shown_icon(self):
        if self.disguise:
            return letter_icon(self.disguise["letter"], self.disguise["color"])
        if self.icon.isNull():
            return globe_icon()
        return self.icon


class Page(QWebEnginePage):
    def __init__(self, profile, win):
        super().__init__(profile, win)
        self.win = win
        self.tab = None
        if hasattr(self, "permissionRequested"):
            self.permissionRequested.connect(self._perm_new)
        else:
            self.featurePermissionRequested.connect(self._perm_old)
        self.fullScreenRequested.connect(self._fs)

    def javaScriptConsoleMessage(self, level, message, line, source):
        if message and message.startswith("AURORA_PIP:"):
            try:
                data = json.loads(message[len("AURORA_PIP:"):])
                self.win.handle_pip_request(data, self.profile())
            except Exception:
                traceback.print_exc()
        elif message and message.startswith("AURORA_SPEEDDIAL:"):
            try:
                data = json.loads(message[len("AURORA_SPEEDDIAL:"):])
                self.win.handle_speeddial_request(data)
            except Exception:
                traceback.print_exc()

    def createWindow(self, wtype):
        bg = wtype == QWebEnginePage.WebWindowType.WebBrowserBackgroundTab
        if self.tab is not None:
            pid = self.tab.profile_id
        elif self.win.cur:
            pid = self.win.cur.profile_id
        else:
            pid = self.win.default_profile_id
        return self.win.new_tab(background=bg, blank=True, profile_id=pid).view.page()

    def _fs(self, req):
        req.accept()
        self.win.set_fs(req.toggleOn())

    def _ask(self, host, name, grant, deny):
        perms = self.win.core.store["perms"]
        key = "%s|%s" % (host, name)
        if key in perms:
            (grant if perms[key] else deny)()
            return
        box = QMessageBox(self.win)
        box.setWindowTitle("Permiso solicitado")
        box.setText("%s quiere usar: %s" % (host or "Esta pagina", name))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        cb = QCheckBox("Recordar mi decision")
        box.setCheckBox(cb)
        ok = box.exec() == QMessageBox.StandardButton.Yes
        if cb.isChecked():
            perms[key] = ok
            self.win.core.store.save()
        (grant if ok else deny)()

    def _perm_new(self, perm):
        name = getattr(perm.permissionType(), "name", str(perm.permissionType()))
        self._ask(perm.origin().host(), name, perm.grant, perm.deny)

    def _perm_old(self, url, feature):
        P = QWebEnginePage.PermissionPolicy
        name = getattr(feature, "name", str(feature))
        self._ask(url.host(), name,
                  lambda: self.setFeaturePermission(url, feature, P.PermissionGrantedByUser),
                  lambda: self.setFeaturePermission(url, feature, P.PermissionDeniedByUser))


# ----------------------------------------------------------------------------------------
# Mini reproductor (con soporte PiP)
# ----------------------------------------------------------------------------------------
class MiniPlayer(QWidget):
    SIZES = {"S": (320, 180), "M": (480, 270), "L": (720, 405)}

    def __init__(self, win, url, title, profile,
                 embed_override=None, direct_src=None, time_pos=0.0, paused=False):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.win, self.orig, self.drag, self.profile = win, url, None, profile
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("bar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 2, 4, 2)
        self.lbl = QLabel(("\u25b6 " + (title or url or ""))[:42])
        bl.addWidget(self.lbl, 1)

        def btn(txt, tip, fn):
            b = QToolButton()
            b.setText(txt)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False: fn())
            bl.addWidget(b)
        btn("\u23ef", "Play/Pausa", self.toggle_play)
        btn("Mudo", "Silenciar", self.toggle_mute)
        for k in ("S", "M", "L"):
            btn(k, "Tamano " + k, lambda k=k: self.resize(*self.SIZES[k]))
        btn("50%", "Opacidad", self.cycle_opacity)
        btn("Pestana", "Modo pagina original", self.page_mode)
        btn("Devolver", "Devolver a una pestana", self.back_to_tab)
        btn("\u2715", "Cerrar", self.close)
        lay.addWidget(bar)
        self.view = QWebEngineView()
        self.view.setPage(QWebEnginePage(profile, self.view))
        try:
            self.view.page().settings().setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        except Exception:
            pass
        lay.addWidget(self.view, 1)
        grip = QSizeGrip(self)
        lay.addWidget(grip, 0, Qt.AlignmentFlag.AlignRight)

        if embed_override:
            self.view.setHtml(embed_override, QUrl("https://aurora-player.local/"))
        elif direct_src:
            self._load_direct_html(direct_src, time_pos, paused)
        else:
            self.page_mode(embed=True)

        self.resize(*self.SIZES["M"])
        try:
            g = QApplication.primaryScreen().availableGeometry()
            self.move(g.right() - 500, g.bottom() - 330)
        except Exception:
            pass
        self.op = 1.0

    def _load_direct_html(self, src, time_pos=0.0, paused=False):
        self.orig = src
        self.lbl.setText("\u25b6 " + (os.path.basename(urllib.parse.urlparse(src).path)[:42] or "Video"))
        html_code = (
            "<!doctype html><html><body style='margin:0;background:#000;overflow:hidden'>"
            "<video id='v' src='%s' style='width:100%%;height:100vh;object-fit:contain' controls></video>"
            "<script>window.addEventListener('load',function(){var v=document.getElementById('v');"
            "try{v.currentTime=%f;}catch(e){}%s});</script></body></html>"
        ) % (html.escape(src, True), float(time_pos or 0.0),
             "" if paused else "v.play().catch(function(){});")
        self.view.setHtml(html_code, QUrl("https://aurora-player.local/"))

    def page_mode(self, embed=False):
        h = embed_html(self.orig) if embed else None
        if h:
            self.view.setHtml(h, QUrl("https://aurora-player.local/"))
        else:
            self.view.load(QUrl(self.orig))

    def toggle_play(self):
        self.view.page().runJavaScript("document.querySelectorAll('video,audio').forEach(function(v){v.paused?v.play():v.pause()})")

    def toggle_mute(self):
        p = self.view.page()
        p.setAudioMuted(not p.isAudioMuted())

    def cycle_opacity(self):
        self.op = 1.0 if self.op <= 0.45 else self.op - 0.25
        self.setWindowOpacity(self.op)

    def back_to_tab(self):
        self.win.new_tab(self.orig)
        self.close()

    def mousePressEvent(self, e):
        if e.position().y() < 34:
            self.drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, e):
        self.drag = None

    def closeEvent(self, e):
        try:
            self.win.core.minis.remove(self)
        except ValueError:
            pass
        try:
            self.view.setHtml("")
        except Exception:
            pass
        super().closeEvent(e)


# ----------------------------------------------------------------------------------------
# Diálogos
# ----------------------------------------------------------------------------------------
class Palette(QDialog):
    def __init__(self, win, entries):
        super().__init__(win)
        self.win, self.entries = win, entries
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.resize(640, 420)
        l = QVBoxLayout(self)
        self.q = QLineEdit()
        self.q.setPlaceholderText("Pestañas, marcadores, historial, comandos, o escribe una direccion...")
        self.lst = QListWidget()
        l.addWidget(self.q)
        l.addWidget(self.lst)
        self.q.textChanged.connect(self.fill)
        self.q.returnPressed.connect(self.run)
        self.lst.itemActivated.connect(lambda _i: self.run())
        self.fill("")

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            r = self.lst.currentRow() + (1 if e.key() == Qt.Key.Key_Down else -1)
            self.lst.setCurrentRow(max(0, min(self.lst.count() - 1, r)))
            return
        super().keyPressEvent(e)

    def fill(self, text):
        self.lst.clear()
        words = text.lower().split()
        self.shown = []
        if text.strip():
            self.shown.append(("Ir a \u00ab%s\u00bb" % text, lambda: self.win.go(text)))
        for label, fn in self.entries:
            if all(w in label.lower() for w in words):
                self.shown.append((label, fn))
            if len(self.shown) >= 60:
                break
        for label, _ in self.shown:
            self.lst.addItem(label)
        if self.shown:
            self.lst.setCurrentRow(0)

    def run(self):
        r = self.lst.currentRow()
        if 0 <= r < len(self.shown):
            fn = self.shown[r][1]
            self.accept()
            fn()


class ThemeEditor(QDialog):
    KEYS = ["bg", "panel", "card", "hover", "text", "sub", "accent", "border"]
    LABELS = {"bg": "Fondo", "panel": "Panel", "card": "Tarjeta", "hover": "Hover",
              "text": "Texto", "sub": "Texto secundario", "accent": "Acento", "border": "Borde"}

    def __init__(self, win):
        super().__init__(win)
        self.core = win.core
        self.setWindowTitle("Editor de tema personalizado")
        self.setMinimumWidth(420)
        f = QFormLayout(self)
        cur = dict(THEMES["Aurora"])
        cur.update(self.core.store.get("custom_theme") or {})
        self.colors = dict(cur)
        self.btns = {}
        for k in self.KEYS:
            b = QPushButton()
            b.setStyleSheet("background:%s;min-height:28px;border:1px solid #888" % self.colors.get(k, "#000"))
            b.clicked.connect(lambda _=False, k=k: self.pick(k))
            self.btns[k] = b
            f.addRow(self.LABELS[k], b)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def pick(self, key):
        c = QColorDialog.getColor(QColor(self.colors.get(key, "#000")), self,
                                  "Color para " + self.LABELS[key])
        if c.isValid():
            self.colors[key] = c.name()
            self.btns[key].setStyleSheet("background:%s;min-height:28px;border:1px solid #888" % c.name())

    def save(self):
        self.core.store["custom_theme"] = self.colors
        self.core.store["theme"] = "Personalizado"
        self.core.apply_theme()
        self.accept()


class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.core = win, win.core
        s = self.core.store
        self.setWindowTitle("Ajustes de Aurora")
        self.resize(720, 720)
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        outer.addWidget(tabs)

        # ---- General ----
        gen = QWidget()
        gf = QFormLayout(gen)
        self.engine = QComboBox()
        self.engine.addItems(list(self.core.all_engines()))
        self.engine.setCurrentText(s["engine"])
        self.home = QLineEdit(s["home"])
        self.rest = QCheckBox("Restaurar pestanas al abrir")
        self.rest.setChecked(s["restore"])
        self.prompt = QCheckBox("Preguntar que perfil usar al crear una pestaña nueva")
        self.prompt.setChecked(s["prompt_profile_on_new_tab"])
        self.al = QPlainTextEdit("\n".join("%s=%s" % kv for kv in s["aliases"].items()))
        self.al.setMaximumHeight(100)
        self.dial = QPlainTextEdit("\n".join("%s=%s" % (n, u) for n, u in s["speed_dial"]))
        self.dial.setMaximumHeight(140)
        gf.addRow("Buscador", self.engine)
        gf.addRow("Pagina de inicio", self.home)
        gf.addRow(self.rest)
        gf.addRow(self.prompt)
        gf.addRow("Alias (alias=url, %s = búsqueda)", self.al)
        gf.addRow("Accesos directos (nombre=url)", self.dial)
        tabs.addTab(gen, "General")

        # ---- Apariencia ----
        apa = QWidget()
        af = QFormLayout(apa)
        self.theme = QComboBox()
        self.theme.addItems(list(THEMES) + ["Personalizado"])
        self.theme.setCurrentText(s["theme"])
        btn_th = QPushButton("Editar colores...")
        btn_th.clicked.connect(lambda: ThemeEditor(self.win).exec())
        row_th = QHBoxLayout()
        row_th.addWidget(self.theme, 1)
        row_th.addWidget(btn_th)
        w_th = QWidget(); w_th.setLayout(row_th); w_th.layout().setContentsMargins(0, 0, 0, 0)

        self.bg = QLineEdit(s.get("custom_bg", ""))
        btn_bg = QPushButton("...")
        btn_bg.clicked.connect(self.pick_bg)
        row_bg = QHBoxLayout()
        row_bg.addWidget(self.bg, 1)
        row_bg.addWidget(btn_bg)
        w_bg = QWidget(); w_bg.setLayout(row_bg); w_bg.layout().setContentsMargins(0, 0, 0, 0)

        self.pic = QLineEdit(s.get("profile_pic", ""))
        btn_pic = QPushButton("...")
        btn_pic.clicked.connect(self.pick_pic)
        row_pic = QHBoxLayout()
        row_pic.addWidget(self.pic, 1)
        row_pic.addWidget(btn_pic)
        w_pic = QWidget(); w_pic.setLayout(row_pic); w_pic.layout().setContentsMargins(0, 0, 0, 0)

        af.addRow("Tema", w_th)
        af.addRow("Fondo de inicio (URL o archivo; .gif/.mp4 soportados)", w_bg)
        af.addRow("Foto de perfil (URL o archivo)", w_pic)
        af.addRow(QLabel("<small>Los archivos locales se incrustan como data URL. "
                         "Para archivos animados grandes mejor una URL http(s).</small>"))
        tabs.addTab(apa, "Apariencia")

        # ---- Bloqueo ----
        blo = QWidget()
        bf = QFormLayout(blo)
        self.adb = QCheckBox("Bloquear anuncios y rastreadores")
        self.adb.setChecked(s["adblock"])
        self.doh = QCheckBox("Consultar DNS-over-HTTPS con filtrado")
        self.doh.setChecked(s["doh"])
        self.doh_url = QLineEdit(s["doh_url"])
        self.hosts = QLineEdit(s["hosts_url"])
        self.cat = QLineEdit(s["catalog_url"])
        self.cat.setPlaceholderText("URL de un JSON con extensiones de la comunidad")
        bf.addRow(self.adb)
        bf.addRow(self.doh)
        bf.addRow("Resolvedor DoH (JSON)", self.doh_url)
        bf.addRow("Lista hosts", self.hosts)
        bf.addRow("Catalogo comunidad", self.cat)
        upd = QPushButton("Actualizar listas de bloqueo ahora")
        upd.clicked.connect(lambda: (self.core.blocker.update_lists(),
                                     win.statusBar().showMessage("Actualizando listas...", 4000)))
        bf.addRow(upd)
        tabs.addTab(blo, "Bloqueo")

        # ---- Avanzado ----
        av = QWidget()
        vf = QFormLayout(av)
        self.dl = QLineEdit(s["download_dir"])
        self.pip = QCheckBox("Activar PiP con doble clic derecho sobre un video")
        self.pip.setChecked(s.get("pip_enabled", True))
        vf.addRow("Carpeta descargas", self.dl)
        vf.addRow(self.pip)
        vf.addRow(QLabel("<small>Si activas el PiP, en cualquier &lt;video&gt; puedes hacer "
                         "doble clic derecho para abrirlo en el mini reproductor.</small>"))
        tabs.addTab(av, "Avanzado")

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    def pick_bg(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Fondo de inicio", "",
            "Imagenes/videos (*.png *.jpg *.jpeg *.gif *.webp *.svg *.mp4 *.webm *.mov);;Todos (*)")
        if p:
            self.bg.setText(p)

    def pick_pic(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Foto de perfil", "",
            "Imagenes (*.png *.jpg *.jpeg *.gif *.webp *.svg);;Todos (*)")
        if p:
            self.pic.setText(p)

    def save(self):
        s = self.core.store
        s.d["engine"] = self.engine.currentText()
        s.d["home"] = self.home.text().strip()
        s.d["adblock"] = self.adb.isChecked()
        s.d["doh"] = self.doh.isChecked()
        s.d["doh_url"] = self.doh_url.text().strip() or DEFAULTS["doh_url"]
        s.d["hosts_url"] = self.hosts.text().strip() or DEFAULTS["hosts_url"]
        s.d["download_dir"] = self.dl.text().strip() or DEFAULTS["download_dir"]
        s.d["catalog_url"] = self.cat.text().strip()
        s.d["restore"] = self.rest.isChecked()
        s.d["prompt_profile_on_new_tab"] = self.prompt.isChecked()
        s.d["aliases"] = {k.strip().lower(): v.strip()
                          for k, _, v in (ln.partition("=") for ln in self.al.toPlainText().splitlines())
                          if k.strip() and v.strip()}
        new_dial = []
        for ln in self.dial.toPlainText().splitlines():
            k, _, v = ln.partition("=")
            k, v = k.strip(), v.strip()
            if k and v:
                if not re.match(r"^https?://", v, re.I):
                    v = "https://" + v
                new_dial.append([k, v])
        s.d["speed_dial"] = new_dial
        s.d["theme"] = self.theme.currentText()
        s.d["custom_bg"] = self.bg.text().strip()
        s.d["profile_pic"] = self.pic.text().strip()
        s.d["pip_enabled"] = self.pip.isChecked()
        s.save()
        self.core.apply_adblock_scripts()
        self.core.apply_pip_scripts()
        self.core.apply_theme()
        for w in self.core.windows:
            try:
                w.refresh_completer()
                w.refresh_profile_ui()
            except Exception:
                pass
        self.accept()


class DownloadsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.core = win.core
        self.setWindowTitle("Descargas")
        self.resize(560, 380)
        l = QVBoxLayout(self)
        self.lst = QListWidget()
        self.lst.itemDoubleClicked.connect(self.open_item)
        l.addWidget(self.lst)
        h = QHBoxLayout()
        b = QPushButton("Abrir carpeta")
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.core.store["download_dir"])))
        h.addWidget(b)
        l.addLayout(h)
        self.t = QTimer(self)
        self.t.timeout.connect(self.refresh)
        self.t.start(600)
        self.refresh()

    def refresh(self):
        row = self.lst.currentRow()
        self.lst.clear()
        for r in reversed(self.core.downloads):
            try:
                tot, rec = r.d.totalBytes(), r.d.receivedBytes()
                pct = "%d%%" % (100 * rec / tot) if tot > 0 else "%d KB" % (rec // 1024)
                st = "listo" if r.d.isFinished() else pct
                self.lst.addItem("%s  -  %s" % (os.path.basename(r.path), st))
            except RuntimeError:
                pass
        self.lst.setCurrentRow(row)

    def open_item(self, item):
        i = self.lst.row(item)
        recs = list(reversed(self.core.downloads))
        if 0 <= i < len(recs):
            QDesktopServices.openUrl(QUrl.fromLocalFile(recs[i].path))


class ExtDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.core, self.win = win.core, win
        self.setWindowTitle("Extensiones")
        self.resize(640, 480)
        l = QVBoxLayout(self)
        tabs = QTabWidget()
        l.addWidget(tabs)
        inst = QWidget()
        il = QVBoxLayout(inst)
        self.lst = QListWidget()
        self.lst.itemChanged.connect(self.toggled)
        self.lst.currentRowChanged.connect(self.show_info)
        self.info = QLabel()
        self.info.setWordWrap(True)
        il.addWidget(self.lst)
        il.addWidget(self.info)
        h = QHBoxLayout()
        for txt, fn in (("Instalar .zip", self.install_zip), ("Instalar carpeta", self.install_folder),
                        ("Abrir carpeta", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(EXT_DIR)))),
                        ("Recargar", self.reload), ("Eliminar", self.remove)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            h.addWidget(b)
        il.addLayout(h)
        tabs.addTab(inst, "Instaladas")
        com = QWidget()
        cl = QVBoxLayout(com)
        self.cat = QListWidget()
        cl.addWidget(self.cat)
        hb = QHBoxLayout()
        b1 = QPushButton("Cargar catalogo")
        b1.clicked.connect(self.load_catalog)
        b2 = QPushButton("Instalar seleccionada")
        b2.clicked.connect(self.install_cat)
        hb.addWidget(b1)
        hb.addWidget(b2)
        cl.addLayout(hb)
        cl.addWidget(QLabel("JSON: [{\"id\":\"..\",\"name\":\"..\",\"description\":\"..\",\"zip_url\":\"https://..\"}]"))
        tabs.addTab(com, "Comunidad")
        self.items = []
        self.cat_items = []
        self.core.cat_loaded.connect(self.fill_catalog)
        self.fill()

    def fill(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        for eid, e in self.core.exts.items():
            it = QListWidgetItem("%s  v%s" % (e.man.get("name", eid), e.man.get("version", "?")))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if e.enabled else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, eid)
            self.lst.addItem(it)
        self.lst.blockSignals(False)

    def cur_id(self):
        it = self.lst.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def show_info(self, _r):
        e = self.core.exts.get(self.cur_id())
        if e:
            self.info.setText("%s\nAutor: %s\n%s%s" % (e.man.get("name", e.id), e.man.get("author", "?"), e.man.get("description", ""),
                                                      ("\n\nERROR:\n" + e.error[-400:]) if e.error else ""))

    def toggled(self, it):
        eid = it.data(Qt.ItemDataRole.UserRole)
        dis = set(self.core.store["ext_disabled"])
        if it.checkState() == Qt.CheckState.Checked:
            dis.discard(eid)
        else:
            dis.add(eid)
        self.core.store["ext_disabled"] = sorted(dis)
        self.core.reload_extensions()
        self.fill()

    def warn(self):
        return QMessageBox.question(self, "Seguridad", "Las extensiones ejecutan codigo Python con tus mismos permisos.\nContinuar?") == QMessageBox.StandardButton.Yes

    def install_zip(self):
        p, _ = QFileDialog.getOpenFileName(self, "Extension .zip", "", "Zip (*.zip)")
        if p and self.warn():
            try:
                self.core.install_zip(p)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
            self.fill()

    def install_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Carpeta de la extension")
        if p and self.warn():
            try:
                self.core.install_dir(p)
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
            self.fill()

    def reload(self):
        self.core.reload_extensions()
        self.fill()

    def remove(self):
        eid = self.cur_id()
        if eid and QMessageBox.question(self, "Eliminar", "Eliminar " + eid + "?") == QMessageBox.StandardButton.Yes:
            self.core.unload_ext(eid)
            shutil.rmtree(EXT_DIR / eid, ignore_errors=True)
            self.core.reload_extensions()
            self.fill()

    def load_catalog(self):
        url = self.core.store["catalog_url"]
        if not url:
            QMessageBox.information(self, "Catalogo", "Define la URL del catalogo en Ajustes.")
            return

        def run():
            try:
                with urllib.request.urlopen(url, timeout=15) as r:
                    data = json.load(r)
            except Exception:
                data = []
            self.core.cat_loaded.emit(data)
        threading.Thread(target=run, daemon=True).start()

    def fill_catalog(self, data):
        self.cat.clear()
        self.cat_items = [d for d in data if isinstance(d, dict) and d.get("zip_url")]
        for d in self.cat_items:
            self.cat.addItem("%s - %s" % (d.get("name", d.get("id")), d.get("description", "")))

    def install_cat(self):
        r = self.cat.currentRow()
        if 0 <= r < len(self.cat_items) and self.warn():
            try:
                tmp = Path(tempfile.mkdtemp()) / "e.zip"
                with urllib.request.urlopen(self.cat_items[r]["zip_url"], timeout=30) as resp, open(tmp, "wb") as f:
                    shutil.copyfileobj(resp, f)
                self.core.install_zip(str(tmp))
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))
            self.fill()


class ProfileDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.core = win.core
        self.setWindowTitle("Perfiles")
        self.resize(500, 420)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Cada perfil guarda sus propias cookies, cache y sesion.\n"
            "Puedes tener pestañas con perfiles distintos en la misma ventana."))
        self.lst = QListWidget()
        lay.addWidget(self.lst, 1)
        h = QHBoxLayout()
        for txt, fn in (("Nuevo", self.create), ("Renombrar", self.rename_selected),
                        ("Eliminar", self.delete)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, fn=fn: fn())
            h.addWidget(b)
        lay.addLayout(h)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.fill()

    def fill(self):
        self.lst.clear()
        for p in self.core.pm.list():
            text = p["name"]
            if p["id"] == "default":
                text += "   (predeterminado)"
            it = QListWidgetItem(get_avatar_icon(self.core, p["id"], 18), text)
            it.setData(Qt.ItemDataRole.UserRole, p["id"])
            self.lst.addItem(it)

    def selected_entry(self):
        it = self.lst.currentItem()
        if not it:
            return None
        return self.core.pm.get(it.data(Qt.ItemDataRole.UserRole))

    def create(self):
        n, ok = QInputDialog.getText(self, "Nuevo perfil", "Nombre del perfil:")
        if ok and n.strip():
            self.core.pm.create(n.strip())
            self.core.refresh_profiles_ui()
            self.fill()

    def rename_selected(self):
        entry = self.selected_entry()
        if not entry:
            return
        n, ok = QInputDialog.getText(self, "Renombrar perfil", "Nuevo nombre:", text=entry["name"])
        if ok and n.strip():
            self.core.pm.rename(entry["id"], n.strip())
            self.core.refresh_profiles_ui()
            self.fill()

    def delete(self):
        entry = self.selected_entry()
        if not entry:
            return
        if entry["id"] == "default":
            QMessageBox.information(self, "Perfil predeterminado",
                                    "El perfil predeterminado no se puede eliminar.")
            return
        in_use = any(t.profile_id == entry["id"] for w in self.core.windows for t in w.tabs)
        if in_use:
            QMessageBox.warning(self, "Perfil en uso",
                                "Hay pestañas abiertas con este perfil. Cierralas primero.")
            return
        if QMessageBox.question(self, "Eliminar perfil",
                                "¿Eliminar '%s'? Se borrarán sus cookies, caché y sesión." %
                                entry["name"]) == QMessageBox.StandardButton.Yes:
            self.core.pm.delete(entry["id"])
            self.core.forget_profile(entry["id"])
            self.core.refresh_profiles_ui()
            self.fill()


# ----------------------------------------------------------------------------------------
# Ventana principal
# ----------------------------------------------------------------------------------------
class BrowserWindow(QMainWindow):
    def __init__(self, core, profile_id="default", private=False):
        super().__init__()
        self.core, self.private = core, private
        self.default_profile_id = profile_id
        self.profile = core.make_profile(profile_id, private)

        self.tabs, self.cur, self.closed = [], None, []
        self._visible_tabs = []
        self.split_partner = None
        self._devs, self._ext_sc, self._fs = [], [], False
        self._caption_stripped = False

        self.resize(1360, 860)
        self.setWindowIcon(letter_icon("A", "#5b8def"))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        self.build_ui()
        self.build_shortcuts()
        self.rebuild_ext_ui()
        self.refresh_completer()
        self.refresh_profile_ui()

        self.shield_timer = QTimer(self)
        self.shield_timer.timeout.connect(self.update_shield)
        self.shield_timer.start(1000)

    def tb(self, text, tip, fn, obj=None):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.clicked.connect(lambda _=False: fn())
        if obj:
            b.setObjectName(obj)
        return b

    # -- construcción ------------------------------------------------------------------
    def build_ui(self):
        main = QWidget()
        self.setCentralWidget(main)
        vbox = QVBoxLayout(main)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ---- Tab bar fusionada con controles ----
        self.tabbar_wrap = QFrame()
        self.tabbar_wrap.setObjectName("tabbar_wrap")
        self.tabbar_wrap.setFixedHeight(40)
        tbl = QHBoxLayout(self.tabbar_wrap)
        tbl.setContentsMargins(8, 4, 0, 0)
        tbl.setSpacing(4)

        self.tabbar = ColorTabBar()
        self.tabbar.setObjectName("browser_tabs")
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabbar.setUsesScrollButtons(True)
        self.tabbar.setDrawBase(False)
        self.tabbar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabbar.setFixedHeight(34)
        self.tabbar.currentChanged.connect(self.on_tab_changed)
        self.tabbar.tabMoved.connect(self.on_tab_moved)
        self.tabbar.customContextMenuRequested.connect(self.on_tabbar_ctx)
        self.tabbar.installEventFilter(self)
        tbl.addWidget(self.tabbar, 0)

        self.new_tab_btn = QToolButton()
        self.new_tab_btn.setText("\uff0b")
        self.new_tab_btn.setToolTip("Nueva pestaña (elige perfil)")
        self.new_tab_btn.setFixedSize(28, 28)
        self.new_tab_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.new_tab_menu = QMenu(self)
        self.new_tab_menu.aboutToShow.connect(self.fill_new_tab_menu)
        self.new_tab_btn.setMenu(self.new_tab_menu)
        tbl.addWidget(self.new_tab_btn, 0)

        self.drag_space = DragSpace(self)
        tbl.addWidget(self.drag_space, 1)

        self.win_controls = WindowControls(self)
        tbl.addWidget(self.win_controls, 0)
        vbox.addWidget(self.tabbar_wrap)

        # ---- Barra de navegación ----
        bar = QFrame()
        bar.setObjectName("bar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(4)
        bl.addWidget(self.tb("\u2190", "Atras (Alt+Izq)", lambda: self.cur and self.cur.view.back()))
        bl.addWidget(self.tb("\u2192", "Adelante (Alt+Der)", lambda: self.cur and self.cur.view.forward()))
        self.b_reload = self.tb("\u27f3", "Recargar (F5)", self.reload_stop)
        bl.addWidget(self.b_reload)
        bl.addWidget(self.tb("\u2302", "Inicio", lambda: self.go(self.core.store["home"] or "aurora://newtab")))

        self.omni = QLineEdit()
        self.omni.setPlaceholderText("Buscar o escribir una direccion")
        self.omni.returnPressed.connect(lambda: self.go(self.omni.text()))
        self.completer = QCompleter(QStringListModel([]), self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.omni.setCompleter(self.completer)
        bl.addWidget(self.omni, 1)

        # Selector rápido de buscador
        self.b_engine = QToolButton()
        self.b_engine.setIcon(search_icon())
        self.b_engine.setIconSize(QSize(16, 16))
        self.b_engine.setToolTip("Motor de busqueda")
        self.b_engine.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.engine_menu = QMenu(self)
        self.engine_menu.aboutToShow.connect(self.fill_engine_menu)
        self.b_engine.setMenu(self.engine_menu)
        bl.addWidget(self.b_engine)

        self.b_star = self.tb("\u2606", "Marcador (Ctrl+D)", self.toggle_bookmark)
        bl.addWidget(self.b_star)

        self.b_shield = QToolButton()
        self.b_shield.setToolTip("Bloqueador de anuncios")
        self.b_shield.setIcon(shield_icon())
        self.b_shield.setIconSize(QSize(16, 16))
        self.b_shield.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.b_shield.setText("")
        self.shield_menu = QMenu(self)
        self.shield_menu.aboutToShow.connect(self.fill_shield)
        self.b_shield.setMenu(self.shield_menu)
        bl.addWidget(self.b_shield)

        self.ext_box = QHBoxLayout()
        self.ext_box.setContentsMargins(0, 0, 0, 0)
        self.ext_box.setSpacing(2)
        bl.addLayout(self.ext_box)

        self.avatar_btn = QToolButton()
        self.avatar_btn.setIconSize(QSize(20, 20))
        self.avatar_btn.setFixedSize(30, 30)
        self.avatar_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.avatar_menu = QMenu(self)
        self.avatar_menu.aboutToShow.connect(self.fill_avatar_menu)
        self.avatar_btn.setMenu(self.avatar_menu)
        bl.addWidget(self.avatar_btn)

        self.b_menu = QToolButton()
        self.b_menu.setText("\u22ee")
        self.b_menu.setToolTip("Menu")
        self.b_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.main_menu = QMenu(self)
        self.main_menu.aboutToShow.connect(self.fill_main_menu)
        self.b_menu.setMenu(self.main_menu)
        bl.addWidget(self.b_menu)

        vbox.addWidget(bar)

        self.prog = QProgressBar()
        self.prog.setFixedHeight(2)
        self.prog.setTextVisible(False)
        self.prog.setRange(0, 100)
        vbox.addWidget(self.prog)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(3)
        vbox.addWidget(self.splitter, 1)

        self.findbar = QFrame()
        self.findbar.setObjectName("find")
        fl = QHBoxLayout(self.findbar)
        fl.setContentsMargins(8, 4, 8, 4)
        self.find_in = QLineEdit()
        self.find_in.setPlaceholderText("Buscar en la pagina")
        self.find_in.textChanged.connect(lambda: self.find_text(True))
        self.find_in.returnPressed.connect(lambda: self.find_text(True))
        fl.addWidget(self.find_in, 1)
        fl.addWidget(self.tb("\u25b2", "Anterior", lambda: self.find_text(False)))
        fl.addWidget(self.tb("\u25bc", "Siguiente", lambda: self.find_text(True)))
        fl.addWidget(self.tb("\u2715", "Cerrar", self.close_find))
        self.findbar.hide()
        vbox.addWidget(self.findbar)

    # -- ventana nativa ---------------------------------------------------------------
    def showEvent(self, e):
        super().showEvent(e)
        if sys.platform == "win32" and not self._caption_stripped:
            QTimer.singleShot(0, self._strip_caption)

    def _strip_caption(self):
        self._caption_stripped = True
        if sys.platform != "win32" or ctypes is None:
            return
        try:
            hwnd = int(self.winId())
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            WS_SYSMENU = 0x00080000
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.restype = ctypes.c_long
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            new_style = (style & ~WS_CAPTION) | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
            user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
        except Exception:
            traceback.print_exc()

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange:
            try:
                self.win_controls.refresh()
            except Exception:
                pass
        super().changeEvent(e)

    def eventFilter(self, obj, ev):
        if obj is self.tabbar:
            if ev.type() == QEvent.Type.MouseButtonPress:
                if ev.button() == Qt.MouseButton.LeftButton and self.tabbar.tabAt(ev.position().toPoint()) < 0:
                    wh = self.windowHandle()
                    if wh:
                        wh.startSystemMove()
                    return True
            elif ev.type() == QEvent.Type.MouseButtonDblClick:
                if ev.button() == Qt.MouseButton.LeftButton and self.tabbar.tabAt(ev.position().toPoint()) < 0:
                    if self.isMaximized():
                        self.showNormal()
                    else:
                        self.showMaximized()
                    return True
        return super().eventFilter(obj, ev)

    def build_shortcuts(self):
        def sc(k, fn):
            s = QShortcut(QKeySequence(k), self)
            s.activated.connect(fn)
        sc("Ctrl+T", self.new_tab_with_chooser)
        sc("Ctrl+Alt+T", lambda: self.new_tab())
        sc("Ctrl+W", lambda: self.cur and self.close_tab(self.cur))
        sc("Ctrl+Shift+T", self.reopen_tab)
        sc("Ctrl+L", self.focus_omni)
        sc("Ctrl+K", self.open_palette)
        sc("Ctrl+R", self.reload_stop)
        sc("F5", self.reload_stop)
        sc("Ctrl+Tab", lambda: self.cycle(1))
        sc("Ctrl+Shift+Tab", lambda: self.cycle(-1))
        sc("Alt+Left", lambda: self.cur and self.cur.view.back())
        sc("Alt+Right", lambda: self.cur and self.cur.view.forward())
        sc("Ctrl+D", self.toggle_bookmark)
        sc("Ctrl+F", self.open_find)
        sc("Esc", self.close_find)
        sc("Ctrl+Shift+N", lambda: self.core.new_window(private=True).new_tab())
        sc("Ctrl+N", lambda: self.core.new_window(profile_id=self.default_profile_id).new_tab())
        sc("Ctrl+Shift+S", self.toggle_split)
        sc("Ctrl+Shift+M", self.mini_player)
        sc("Ctrl+Shift+Del", self.panic_wipe)
        sc("F11", lambda: self.set_fs(not self._fs))
        sc("F12", self.devtools)
        sc("Ctrl++", lambda: self.zoom(0.1))
        sc("Ctrl+=", lambda: self.zoom(0.1))
        sc("Ctrl+-", lambda: self.zoom(-0.1))
        sc("Ctrl+0", lambda: self.zoom(0))
        sc("Ctrl+J", lambda: DownloadsDialog(self).exec())
        sc("Ctrl+,", lambda: SettingsDialog(self).exec())
        sc("Ctrl+Shift+E", lambda: ExtDialog(self).exec())
        for i in range(1, 10):
            sc("Ctrl+%d" % i, lambda i=i: self.goto_index(i))

    # -- extensiones UI -----------------------------------------------------------------
    def rebuild_ext_ui(self):
        while self.ext_box.count():
            it = self.ext_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for _id, text, cb, tip in self.core.ext_buttons:
            self.ext_box.addWidget(self.tb(text, tip, lambda cb=cb: self.safe(cb)))
        for s in self._ext_sc:
            s.setEnabled(False)
            s.deleteLater()
        self._ext_sc = []
        for _id, text, cb, key in self.core.ext_menu:
            if key:
                s = QShortcut(QKeySequence(key), self)
                s.activated.connect(lambda cb=cb: self.safe(cb))
                self._ext_sc.append(s)

    def safe(self, cb):
        try:
            cb()
        except Exception:
            traceback.print_exc()
            self.statusBar().showMessage("Error en extension (ver consola)", 5000)

    # -- menú "+ Nueva pestaña" --------------------------------------------------------
    def fill_new_tab_menu(self):
        m = self.new_tab_menu
        m.clear()
        current_pid = self.cur.profile_id if self.cur else self.default_profile_id
        head = m.addAction("Nueva pestaña con perfil:")
        head.setEnabled(False)
        m.addSeparator()
        for p in self.core.pm.list():
            label = p["name"]
            if p["id"] == current_pid:
                label += "    \u2713"
            act = m.addAction(get_avatar_icon(self.core, p["id"], 14), label)
            act.triggered.connect(lambda _=False, pid=p["id"]: self.new_tab(profile_id=pid))
        m.addSeparator()
        act_new = m.addAction("+ Nuevo perfil...")
        act_new.triggered.connect(self.new_profile_and_tab)
        act_man = m.addAction("Administrar perfiles...")
        act_man.triggered.connect(lambda: ProfileDialog(self).exec())

    def new_tab_with_chooser(self):
        if not self.core.store["prompt_profile_on_new_tab"]:
            return self.new_tab()
        self.fill_new_tab_menu()
        self.new_tab_menu.exec(self.new_tab_btn.mapToGlobal(self.new_tab_btn.rect().bottomLeft()))

    def new_profile_and_tab(self):
        n, ok = QInputDialog.getText(self, "Nuevo perfil", "Nombre del perfil:")
        if ok and n.strip():
            entry = self.core.pm.create(n.strip())
            self.core.refresh_profiles_ui()
            self.new_tab(profile_id=entry["id"])

    # -- menú motor de búsqueda --------------------------------------------------------
    def fill_engine_menu(self):
        m = self.engine_menu
        m.clear()
        cur = self.core.store["engine"]
        for name in self.core.all_engines():
            self.act(m, name, lambda n=name: self.set_engine(n), checked=(n == cur))
        m.addSeparator()
        self.act(m, "Añadir motor personalizado...", self.add_custom_engine)
        self.act(m, "Ajustes...", lambda: SettingsDialog(self).exec())

    def set_engine(self, name):
        self.core.store["engine"] = name
        self.statusBar().showMessage("Buscador: " + name, 3000)
        self.core.reload_newtabs()

    def add_custom_engine(self):
        n, ok = QInputDialog.getText(self, "Motor personalizado", "Nombre:")
        if not ok or not n.strip():
            return
        u, ok = QInputDialog.getText(self, "Motor personalizado",
                                     "URL de búsqueda (usa %s como marcador):",
                                     text="https://ejemplo.com/search?q=%s")
        if ok and u.strip():
            e = dict(self.core.store.get("custom_engines") or {})
            e[n.strip()] = u.strip()
            self.core.store["custom_engines"] = e
            self.set_engine(n.strip())

    # -- avatar / perfiles -------------------------------------------------------------
    def refresh_profile_ui(self):
        if self.private:
            self.avatar_btn.setIcon(make_avatar_icon("#5f6368", "P"))
            self.avatar_btn.setToolTip("Ventana privada")
            self.avatar_btn.setEnabled(False)
        else:
            pid = self.cur.profile_id if self.cur else self.default_profile_id
            self.avatar_btn.setIcon(get_avatar_icon(self.core, pid, 20))
            name = self.core.profile_name(pid)
            self.avatar_btn.setToolTip("Perfil de esta pestaña: " + name)
            self.avatar_btn.setEnabled(True)
        self.update_title()

    def fill_avatar_menu(self):
        if self.private:
            return
        m = self.avatar_menu
        m.clear()
        pid = self.cur.profile_id if self.cur else self.default_profile_id
        head = m.addAction("Perfil de esta pestaña: " + self.core.profile_name(pid))
        head.setEnabled(False)
        m.addSeparator()
        self.act(m, "Nueva pestaña con este perfil", lambda: self.new_tab(profile_id=pid))
        self.act(m, "Nueva pestaña con otro perfil...", self.new_tab_with_chooser)
        m.addSeparator()
        self.act(m, "Nuevo perfil...", self.new_profile_and_tab)
        self.act(m, "Administrar perfiles...", lambda: ProfileDialog(self).exec())

    def update_title(self):
        t = self.cur
        base = (t.shown_title() + " - ") if t else ""
        if self.private:
            suffix = " (Privado)"
        else:
            pid = t.profile_id if t else self.default_profile_id
            if pid == "default":
                suffix = ""
            else:
                suffix = " (" + self.core.profile_name(pid) + ")"
        self.setWindowTitle(base + APP + suffix)

    # -- pestañas ----------------------------------------------------------------------
    def new_tab(self, url=None, background=False, blank=False, profile_id=None):
        if self.private:
            profile = self.profile
            pid = "private"
        else:
            if profile_id is None:
                profile_id = self.cur.profile_id if self.cur else self.default_profile_id
            if not self.core.pm.get(profile_id):
                profile_id = "default"
            pid = profile_id
            profile = self.core.make_profile(profile_id)

        v = QWebEngineView()
        pg = Page(profile, self)
        v.setPage(pg)
        st = pg.settings()
        A = QWebEngineSettings.WebAttribute
        for a, val in ((A.FullScreenSupportEnabled, True), (A.PlaybackRequiresUserGesture, False),
                       (A.JavascriptCanOpenWindows, True), (A.ScrollAnimatorEnabled, True)):
            try:
                st.setAttribute(a, val)
            except Exception:
                pass
        t = Tab(v, pid)
        pg.tab = t
        self.tabs.append(t)
        v.titleChanged.connect(lambda s, t=t: self.on_title(t, s))
        v.iconChanged.connect(lambda ic, t=t: self.on_icon(t, ic))
        v.urlChanged.connect(lambda u, t=t: self.on_url(t, u))
        v.loadStarted.connect(lambda t=t: self.on_load(t, True))
        v.loadFinished.connect(lambda ok, t=t: self.on_loaded(t, ok))
        v.loadProgress.connect(lambda p, t=t: self.prog.setValue(p if t is self.cur and p < 100 else 0))
        pg.linkHovered.connect(lambda u: self.statusBar().showMessage(u))
        pg.recentlyAudibleChanged.connect(lambda _a, t=t: self.sync_tab(t))
        pg.windowCloseRequested.connect(lambda t=t: self.close_tab(t))
        if url:
            v.load(QUrl(url))
        elif not blank:
            self.load_newtab(t)
        self.sync_tabbar()
        if not background:
            self.select(t)
        self.core.fire("tab_opened", TabAPI(t))
        return t

    def load_newtab(self, t):
        t.newtab = True
        try:
            t.view.setHtml(self.core.newtab_html(), QUrl("aurora://newtab"))
        except Exception:
            traceback.print_exc()
        if t is self.cur:
            self.focus_omni()

    def reload_newtabs(self):
        for t in self.tabs:
            if t.newtab:
                try:
                    t.view.setHtml(self.core.newtab_html(), QUrl("aurora://newtab"))
                except Exception:
                    pass

    def on_title(self, t, s):
        t.title = s
        self.sync_tab(t)
        if t is self.cur:
            self.update_title()

    def on_icon(self, t, ic):
        t.icon = ic
        self.sync_tab(t)

    def on_url(self, t, u):
        t.newtab = u.scheme() == "aurora"
        if t is self.cur:
            self.omni.setText("" if t.newtab else u.toString())
            self.update_star()

    def on_load(self, t, b):
        t.loading = b
        self.sync_tab(t)
        if t is self.cur:
            self.b_reload.setText("\u2715" if b else "\u27f3")

    def on_loaded(self, t, ok):
        self.on_load(t, False)
        if t is self.cur:
            self.prog.setValue(0)
        u = t.view.url()
        if ok and not self.private and not t.newtab and u.scheme() in ("http", "https"):
            h = self.core.store["history"]
            if not h or h[-1][2] != u.toString():
                h.append([int(time.time()), t.title or u.host(), u.toString()])
                del h[:-3000]
                self.core.store.save_soon()
        self.core.fire("page_loaded", TabAPI(t), u.toString())

    def _profile_tab_color(self, pid):
        if self.private:
            return "#5f6368"
        return self.core.profile_color(pid)

    def sync_tab(self, t):
        try:
            idx = self._visible_tabs.index(t)
        except (ValueError, AttributeError):
            return
        if idx >= self.tabbar.count():
            return
        self.tabbar.blockSignals(True)
        self.tabbar.setTabText(idx, t.shown_title())
        ic = t.shown_icon()
        if not ic.isNull():
            self.tabbar.setTabIcon(idx, ic)
        self.tabbar.setTabToolTip(idx, t.view.url().toString() or t.shown_title())
        self.tabbar.setTabData(idx, self._tab_data(t))
        self.tabbar.blockSignals(False)
        self.tabbar.update()

    def _tab_data(self, t):
        multi = len({x.profile_id for x in self.tabs}) > 1
        return {
            "g": GROUP_COLORS.get(t.group),
            "p": self._profile_tab_color(t.profile_id) if multi else None,
        }

    def visible_tabs(self):
        return self._visible_tabs

    def sync_tabbar(self):
        self._visible_tabs = list(self.tabs)
        self._visible_tabs.sort(key=lambda t: not t.pinned)
        multi = len({x.profile_id for x in self.tabs}) > 1
        self.tabbar.blockSignals(True)
        while self.tabbar.count() > 0:
            self.tabbar.removeTab(0)
        for i, t in enumerate(self._visible_tabs):
            self.tabbar.addTab(t.shown_icon(), t.shown_title())
            self.tabbar.setTabToolTip(i, t.view.url().toString() or t.shown_title())
            self.tabbar.setTabData(i, {
                "g": GROUP_COLORS.get(t.group),
                "p": self._profile_tab_color(t.profile_id) if multi else None,
            })
            if not t.pinned:
                close_btn = QToolButton()
                close_btn.setText("\u2715")
                close_btn.setAutoRaise(True)
                close_btn.setFixedSize(18, 18)
                close_btn.setCursor(Qt.CursorShape.ArrowCursor)
                close_btn.setToolTip("Cerrar pestaña")
                close_btn.clicked.connect(lambda _=False, t=t: self.close_tab(t))
                self.tabbar.setTabButton(i, QTabBar.ButtonPosition.RightSide, close_btn)
        if self.cur and self.cur in self._visible_tabs:
            self.tabbar.setCurrentIndex(self._visible_tabs.index(self.cur))
        self.tabbar.blockSignals(False)
        self.tabbar.setVisible(self.tabbar.count() > 0)
        self.tabbar.update()

    def on_tab_changed(self, idx):
        if 0 <= idx < len(self._visible_tabs):
            self.select(self._visible_tabs[idx])

    def on_tab_moved(self, from_idx, to_idx):
        if from_idx < 0 or to_idx < 0:
            return
        if from_idx >= len(self._visible_tabs) or to_idx >= len(self._visible_tabs):
            return
        t = self._visible_tabs.pop(from_idx)
        self._visible_tabs.insert(to_idx, t)
        others = [x for x in self.tabs if x not in self._visible_tabs]
        self.tabs = others + self._visible_tabs

    def select(self, t):
        self.cur = t
        self.layout_views()
        if t in self._visible_tabs:
            idx = self._visible_tabs.index(t)
            if self.tabbar.currentIndex() != idx:
                self.tabbar.blockSignals(True)
                self.tabbar.setCurrentIndex(idx)
                self.tabbar.blockSignals(False)
        self.omni.setText("" if t.newtab else t.view.url().toString())
        self.update_star()
        self.b_reload.setText("\u2715" if t.loading else "\u27f3")
        self.refresh_profile_ui()
        if t.newtab:
            self.focus_omni()
        else:
            t.view.setFocus()

    def layout_views(self):
        want = [self.cur.view] if self.cur else []
        sp = self.split_partner
        if sp and sp in self.tabs and sp is not self.cur:
            want.append(sp.view)
        for i in reversed(range(self.splitter.count())):
            w = self.splitter.widget(i)
            if w not in want:
                w.hide()
                w.setParent(None)
        for w in want:
            if self.splitter.indexOf(w) < 0:
                self.splitter.addWidget(w)
            w.show()

    def close_tab(self, t):
        if t not in self.tabs:
            return
        if not self.private and not t.newtab and t.view.url().isValid() and t.view.url().scheme() in ("http", "https"):
            self.closed.append((t.view.url().toString(), t.pinned, t.profile_id))
            del self.closed[:-30]
        was_cur = t is self.cur
        was_partner = self.split_partner is t
        vis_idx = self._visible_tabs.index(t) if t in self._visible_tabs else -1
        self.tabs.remove(t)
        if was_partner:
            self.split_partner = None
        self.core.fire("tab_closed", TabAPI(t))
        v = t.view
        v.hide()
        v.setParent(None)
        try:
            v.page().setAudioMuted(True)
        except Exception:
            pass
        v.deleteLater()
        if was_cur:
            self.cur = None
            remaining = list(self.tabs)
            remaining.sort(key=lambda x: not x.pinned)
            self._visible_tabs = remaining
            if remaining:
                ni = max(0, min(vis_idx, len(remaining) - 1))
                self.sync_tabbar()
                self.select(remaining[ni])
            else:
                self.sync_tabbar()
                self.new_tab()
        else:
            self.sync_tabbar()

    def reopen_tab(self):
        if self.closed:
            u, pin, pid = self.closed.pop()
            t = self.new_tab(u, profile_id=pid)
            t.pinned = pin
            self.sync_tabbar()

    def cycle(self, d):
        v = self.visible_tabs()
        if v and self.cur in v:
            self.select(v[(v.index(self.cur) + d) % len(v)])

    def goto_index(self, i):
        v = self.visible_tabs()
        if v:
            self.select(v[-1] if i == 9 else v[min(i - 1, len(v) - 1)])

    # -- navegación -------------------------------------------------------------------
    def resolve(self, text):
        t = text.strip()
        if not t:
            return None
        if t == "aurora://newtab":
            return t
        al = self.core.store["aliases"]
        first, _, rest = t.partition(" ")
        if first.lower() in al:
            u = al[first.lower()]
            if "%s" in u:
                if rest:
                    return u.replace("%s", urllib.parse.quote_plus(rest))
                p = urllib.parse.urlparse(u)
                return "%s://%s" % (p.scheme, p.netloc)
            return u
        if re.match(r"^[a-z][a-z0-9+.-]*://", t, re.I) or t.startswith(("about:", "file:", "data:")):
            return t
        if re.match(r"^(localhost|\d{1,3}(\.\d{1,3}){3})(:\d+)?([/?#].*)?$", t):
            return "http://" + t
        if " " not in t and re.match(r"^[^\s/]+\.[a-z]{2,}(:\d+)?([/?#].*)?$", t, re.I):
            return "https://" + t
        return self.core.engine_url() + urllib.parse.quote_plus(t)

    def go(self, text):
        if text == "aurora://newtab":
            if self.cur:
                self.load_newtab(self.cur)
            return
        u = self.resolve(text)
        if not u:
            return
        if not self.cur:
            self.new_tab(u)
        else:
            self.cur.newtab = False
            self.cur.view.load(QUrl(u))
            self.cur.view.setFocus()

    def reload_stop(self):
        if self.cur:
            self.cur.view.stop() if self.cur.loading else self.cur.view.reload()

    def focus_omni(self):
        self.omni.setFocus()
        self.omni.selectAll()

    def zoom(self, d):
        if self.cur:
            v = self.cur.view
            v.setZoomFactor(1.0 if d == 0 else max(0.25, min(5.0, v.zoomFactor() + d)))

    def open_find(self):
        self.findbar.show()
        self.find_in.setFocus()
        self.find_in.selectAll()

    def close_find(self):
        if self.findbar.isVisible():
            self.findbar.hide()
            if self.cur:
                self.cur.view.page().findText("")
                self.cur.view.setFocus()

    def find_text(self, fwd):
        if self.cur:
            F = QWebEnginePage.FindFlag
            self.cur.view.page().findText(self.find_in.text(), F(0) if fwd else F.FindBackward)

    def set_fs(self, on):
        self._fs = on
        self.tabbar_wrap.setVisible(not on)
        self.statusBar().setVisible(not on)
        self.showFullScreen() if on else self.showNormal()

    def devtools(self):
        if not self.cur:
            return
        dv = QWebEngineView()
        self.cur.view.page().setDevToolsPage(dv.page())
        dv.setWindowTitle("Herramientas de desarrollo")
        dv.resize(1000, 650)
        dv.show()
        self._devs.append(dv)

    # -- marcadores / completado ------------------------------------------------------
    def cur_url(self):
        return self.cur.view.url().toString() if self.cur and not self.cur.newtab else ""

    def update_star(self):
        u = self.cur_url()
        self.b_star.setText("\u2605" if any(b["u"] == u for b in self.core.store["bookmarks"]) and u else "\u2606")

    def toggle_bookmark(self):
        u = self.cur_url()
        if not u:
            return
        bm = self.core.store["bookmarks"]
        ex = [b for b in bm if b["u"] == u]
        if ex:
            bm.remove(ex[0])
        else:
            bm.append({"t": self.cur.title or u, "u": u})
        self.core.store.save()
        self.update_star()
        self.refresh_completer()

    def refresh_completer(self):
        s = self.core.store
        items = list(s["aliases"].keys()) + [b["u"] for b in s["bookmarks"]]
        seen = set(items)
        for _t, _ti, u in reversed(s["history"][-300:]):
            if u not in seen:
                seen.add(u)
                items.append(u)
        self.completer.setModel(QStringListModel(items))

    # -- grupos de color --------------------------------------------------------------
    def set_tab_group(self, t, name):
        t.group = name
        self.sync_tab(t)

    # -- split / mini ----------------------------------------------------------------
    def toggle_split(self):
        if self.split_partner:
            self.split_partner = None
        else:
            others = [t for t in self.visible_tabs() if t is not self.cur]
            if not others:
                self.new_tab(background=True)
                others = [t for t in self.visible_tabs() if t is not self.cur]
            if others:
                self.split_partner = others[-1]
        self.layout_views()
        self.sync_tabbar()

    def split_with(self, t):
        self.split_partner = t
        self.layout_views()
        self.sync_tabbar()

    def mini_player(self, tab=None):
        t = tab if isinstance(tab, Tab) else self.cur
        if not t or t.newtab:
            self.statusBar().showMessage("Abre un video primero", 3000)
            return
        profile = t.view.page().profile()
        m = MiniPlayer(self, t.view.url().toString(), t.title, profile)
        self.core.minis.append(m)
        m.show()
        try:
            t.view.page().setAudioMuted(True)
            t.view.page().runJavaScript("document.querySelectorAll('video,audio').forEach(function(v){v.pause()})")
        except Exception:
            pass

    # -- PiP handler ------------------------------------------------------------------
    def handle_pip_request(self, data, profile=None):
        if not self.core.store.get("pip_enabled", True):
            return
        try:
            page_url = (data.get("page_url") or "").strip()
            src = (data.get("src") or "").strip()
            time_pos = float(data.get("time") or 0.0)
            paused = bool(data.get("paused"))

            prof = profile
            if prof is None:
                prof = self.cur.view.page().profile() if self.cur else self.profile

            embed = embed_html(page_url) or embed_html(src)
            if embed:
                m = MiniPlayer(self, page_url or src, "Mini reproductor", prof, embed_override=embed)
                self.core.minis.append(m)
                m.show()
                self.statusBar().showMessage("PiP: video embebido", 3000)
                return
            if src.startswith(("http://", "https://")) and not src.startswith("blob:"):
                m = MiniPlayer(self, src,
                               os.path.basename(urllib.parse.urlparse(src).path) or "Video",
                               prof, direct_src=src, time_pos=time_pos, paused=paused)
                self.core.minis.append(m)
                m.show()
                self.statusBar().showMessage("PiP: video directo", 3000)
                return
            self.statusBar().showMessage(
                "Este video no se puede extraer (blob). Prueba el boton 'Mini reproductor'.", 5000)
        except Exception:
            traceback.print_exc()

    # -- accesos directos (nuevo) ------------------------------------------------------
    def handle_speeddial_request(self, data):
        try:
            action = data.get("action")
            sd = self.core.store["speed_dial"]
            changed = False

            if action == "delete":
                try:
                    idx = int(data.get("index", -1))
                except (TypeError, ValueError):
                    return
                if 0 <= idx < len(sd):
                    sd.pop(idx)
                    changed = True

            elif action == "add":
                name = (data.get("name") or "").strip()
                url = (data.get("url") or "").strip()
                if not name or not url:
                    return
                if not re.match(r"^https?://", url, re.I):
                    url = "https://" + url
                sd.append([name, url])
                changed = True

            elif action == "reorder":
                try:
                    fi = int(data.get("from", -1))
                    ti = int(data.get("to", -1))
                except (TypeError, ValueError):
                    return
                if 0 <= fi < len(sd) and 0 <= ti < len(sd) and fi != ti:
                    item = sd.pop(fi)
                    sd.insert(ti, item)
                    changed = True

            elif action == "reset":
                self.core.store["speed_dial"] = copy.deepcopy(DEFAULTS["speed_dial"])
                changed = True

            if changed:
                self.core.store.save()
                # Recargar todas las nuevas pestañas para reflejar el cambio
                for w in self.core.windows:
                    try:
                        w.reload_newtabs()
                    except Exception:
                        pass
        except Exception:
            traceback.print_exc()

    # -- modo pánico -----------------------------------------------------------------
    def panic_wipe(self):
        c = self.core
        c.panicking = True
        c.store.d["history"] = []
        c.store.save()
        for p in c.all_profiles():
            try:
                p.cookieStore().deleteAllCookies()
            except Exception:
                pass
            try:
                p.clearHttpCache()
            except Exception:
                pass
        for w in list(c.windows):
            try:
                w.close()
            except Exception:
                pass
        QTimer.singleShot(700, c.app.quit)

    # -- menús -----------------------------------------------------------------------
    def act(self, menu, text, fn, key=None, checked=None):
        a = QAction(text, menu)
        if key:
            a.setShortcut(QKeySequence(key))
            a.setShortcutVisibleInContextMenu(True)
        if checked is not None:
            a.setCheckable(True)
            a.setChecked(checked)
        a.triggered.connect(lambda _=False: fn())
        menu.addAction(a)
        return a

    def fill_main_menu(self):
        m = self.main_menu
        m.clear()
        c = self.core
        self.act(m, "Nueva pestaña (elige perfil)", self.new_tab_with_chooser, "Ctrl+T")
        self.act(m, "Nueva pestaña (mismo perfil)", lambda: self.new_tab(), "Ctrl+Alt+T")
        self.act(m, "Nueva ventana", lambda: c.new_window(profile_id=self.default_profile_id).new_tab(), "Ctrl+N")
        self.act(m, "Ventana privada", lambda: c.new_window(private=True).new_tab(), "Ctrl+Shift+N")
        m.addSeparator()
        self.act(m, "Paleta de comandos", self.open_palette, "Ctrl+K")
        bm = m.addMenu("Marcadores")
        for b in c.store["bookmarks"][-40:]:
            self.act(bm, b["t"][:50], lambda u=b["u"]: self.new_tab(u))
        if not c.store["bookmarks"]:
            bm.addAction("(vacio)").setEnabled(False)
        self.act(m, "Vista dividida", self.toggle_split, "Ctrl+Shift+S", checked=bool(self.split_partner))
        self.act(m, "Mini reproductor", self.mini_player, "Ctrl+Shift+M")
        m.addSeparator()

        em = m.addMenu("Motor de busqueda")
        for name in c.all_engines():
            self.act(em, name, lambda n=name: self.set_engine(n), checked=(name == c.store["engine"]))
        em.addSeparator()
        self.act(em, "Añadir personalizado...", self.add_custom_engine)

        th = m.addMenu("Tema")
        for n in THEMES:
            self.act(th, n, lambda n=n: self.set_theme(n), checked=(n == c.store["theme"]))
        self.act(th, "Personalizado", lambda: self.set_theme("Personalizado"),
                 checked=(c.store["theme"] == "Personalizado"))
        self.act(th, "Editar colores personalizados...", lambda: ThemeEditor(self).exec())

        if not self.private:
            pm = m.addMenu("Perfiles")
            self.act(pm, "Administrar perfiles...", lambda: ProfileDialog(self).exec())
            self.act(pm, "Nuevo perfil...", self.new_profile_and_tab)
        self.act(m, "Descargas", lambda: DownloadsDialog(self).exec(), "Ctrl+J")
        self.act(m, "Extensiones...", lambda: ExtDialog(self).exec(), "Ctrl+Shift+E")
        if c.ext_menu:
            em2 = m.addMenu("Acciones de extensiones")
            for _id, text, cb, key in c.ext_menu:
                self.act(em2, text, lambda cb=cb: self.safe(cb))
        self.act(m, "Ajustes...", lambda: SettingsDialog(self).exec(), "Ctrl+,")
        m.addSeparator()
        self.act(m, "Buscar en la pagina", self.open_find, "Ctrl+F")
        self.act(m, "Acercar", lambda: self.zoom(0.1), "Ctrl++")
        self.act(m, "Alejar", lambda: self.zoom(-0.1), "Ctrl+-")
        self.act(m, "Pantalla completa", lambda: self.set_fs(not self._fs), "F11")
        self.act(m, "Herramientas de desarrollo", self.devtools, "F12")
        m.addSeparator()
        self.act(m, "PÁNICO: borrar todo y salir", self.panic_wipe, "Ctrl+Shift+Del")
        self.act(m, "Salir", c.app.quit)

    def set_theme(self, n):
        self.core.store["theme"] = n
        self.core.apply_theme()

    def fill_shield(self):
        m = self.shield_menu
        m.clear()
        b = self.core.blocker
        s = self.core.store
        self.act(m, "Bloqueo activado", self.toggle_adblock, checked=s["adblock"])
        host = self.cur.view.url().host() if self.cur else ""
        if host:
            base = _base(host.lower())
            self.act(m, "Permitir anuncios en " + base, lambda: self.toggle_site(base), checked=(base in b.whitelist))
        m.addSeparator()
        a = m.addAction("Bloqueadas esta sesion: %d" % b.count)
        a.setEnabled(False)
        a = m.addAction("Dominios en lista: %d" % (len(b.hosts) + len(b.extra)))
        a.setEnabled(False)
        self.act(m, "Actualizar listas", lambda: (b.update_lists(), self.statusBar().showMessage("Actualizando listas...", 4000)))

    def toggle_adblock(self):
        self.core.store["adblock"] = not self.core.store["adblock"]
        self.core.apply_adblock_scripts()
        if self.cur:
            self.cur.view.reload()

    def toggle_site(self, base):
        b = self.core.blocker
        b.whitelist.symmetric_difference_update({base})
        self.core.store["adblock_whitelist"] = sorted(b.whitelist)
        if self.cur:
            self.cur.view.reload()

    def update_shield(self):
        n = self.core.blocker.count
        if not self.core.store["adblock"]:
            self.b_shield.setIcon(globe_icon("#8b92a1", 16))
            self.b_shield.setToolTip("Bloqueador desactivado")
        else:
            accent = self.core.current_theme().get("accent", "#5b8def")
            self.b_shield.setIcon(shield_icon(accent, 16))
            self.b_shield.setToolTip("Bloqueador activo (%d bloqueadas)" % n)

    # -- menú contextual de pestaña ---------------------------------------------------
    def on_tabbar_ctx(self, pos):
        idx = self.tabbar.tabAt(pos)
        if idx < 0 or idx >= len(self._visible_tabs):
            return
        t = self._visible_tabs[idx]
        m = QMenu(self)
        self.act(m, "Soltar" if t.pinned else "Fijar pestaña", lambda: self.pin(t))
        pg = t.view.page()
        self.act(m, "Activar sonido" if pg.isAudioMuted() else "Silenciar",
                 lambda: (pg.setAudioMuted(not pg.isAudioMuted()), self.sync_tab(t)))
        self.act(m, "Recargar", t.view.reload)
        self.act(m, "Duplicar", lambda: self.new_tab(t.view.url().toString(), profile_id=t.profile_id))
        self.act(m, "Vista dividida con esta", lambda: self.split_with(t))
        self.act(m, "Enviar al mini reproductor", lambda: self.mini_player(t))

        if not self.private:
            prof_m = m.addMenu("Reabrir con perfil...")
            for p in self.core.pm.list():
                if p["id"] != t.profile_id:
                    self.act(prof_m, p["name"],
                             lambda pid=p["id"], u=t.view.url().toString(): self.new_tab(u, profile_id=pid))

        gm = m.addMenu("Color de grupo")
        for key in ("red", "orange", "yellow", "green", "cyan", "blue", "purple", "pink"):
            self.act(gm, GROUP_LABELS[key],
                     lambda k=key: self.set_tab_group(t, k),
                     checked=(t.group == key))
        gm.addSeparator()
        self.act(gm, "Sin grupo", lambda: self.set_tab_group(t, None))

        d = m.addMenu("Disfrazar pestaña")
        for title, ch, col in DISGUISES:
            self.act(d, title, lambda title=title, ch=ch, col=col: self.disguise(t, {"title": title, "letter": ch, "color": col}))
        self.act(d, "Personalizado...", lambda: self.custom_disguise(t))
        if t.disguise:
            self.act(m, "Quitar disfraz", lambda: self.disguise(t, None))
        m.addSeparator()
        self.act(m, "Cerrar", lambda: self.close_tab(t))
        self.act(m, "Cerrar las demas", lambda: [self.close_tab(x) for x in list(self._visible_tabs) if x is not t and not x.pinned])
        m.exec(self.tabbar.mapToGlobal(pos))

    def pin(self, t):
        t.pinned = not t.pinned
        self.sync_tabbar()

    def disguise(self, t, d):
        t.disguise = d
        self.sync_tabbar()
        self.update_title()

    def custom_disguise(self, t):
        n, ok = QInputDialog.getText(self, "Disfraz", "Titulo falso de la pestaña:")
        if ok and n.strip():
            self.disguise(t, {"title": n.strip(), "letter": n.strip()[:1].upper(), "color": "#5f6368"})

    # -- paleta -----------------------------------------------------------------------
    def commands(self):
        cmds = [
            ("Comando: Nueva pestaña (elige perfil)", self.new_tab_with_chooser),
            ("Comando: Nueva pestaña (mismo perfil)", lambda: self.new_tab()),
            ("Comando: Ventana privada", lambda: self.core.new_window(private=True).new_tab()),
            ("Comando: Vista dividida", self.toggle_split),
            ("Comando: Mini reproductor", self.mini_player),
            ("Comando: Ajustes", lambda: SettingsDialog(self).exec()),
            ("Comando: Editar tema personalizado", lambda: ThemeEditor(self).exec()),
            ("Comando: Extensiones", lambda: ExtDialog(self).exec()),
            ("Comando: Descargas", lambda: DownloadsDialog(self).exec()),
            ("Comando: Reabrir pestaña cerrada", self.reopen_tab),
            ("Comando: Herramientas de desarrollo", self.devtools),
            ("Comando: Actualizar listas de bloqueo", self.core.blocker.update_lists),
            ("Comando: PÁNICO: borrar todo y salir", self.panic_wipe),
            ("Comando: Administrar perfiles", lambda: ProfileDialog(self).exec()),
            ("Comando: Nuevo perfil", self.new_profile_and_tab),
            ("Comando: Añadir motor de busqueda", self.add_custom_engine),
        ]
        for n in THEMES:
            cmds.append(("Tema: " + n, lambda n=n: self.set_theme(n)))
        cmds.append(("Tema: Personalizado", lambda: self.set_theme("Personalizado")))
        for name in self.core.all_engines():
            cmds.append(("Buscador: " + name, lambda n=name: self.set_engine(n)))
        for _id, name, cb in self.core.ext_cmds:
            cmds.append(("Extension: " + name, lambda cb=cb: self.safe(cb)))
        return cmds

    def open_palette(self):
        ent = [("Pestaña: %s  -  %s" % (t.shown_title(), t.view.url().toString()[:70]), lambda t=t: self.select(t)) for t in self.tabs]
        ent += self.commands()
        for k, u in self.core.store["aliases"].items():
            ent.append(("Alias: %s -> %s" % (k, u), lambda k=k: self.go(k)))
        for b in reversed(self.core.store["bookmarks"]):
            ent.append(("Marcador: %s  -  %s" % (b["t"], b["u"][:70]), lambda u=b["u"]: self.new_tab(u)))
        seen = set()
        for _t, ti, u in reversed(self.core.store["history"][-400:]):
            if u not in seen:
                seen.add(u)
                ent.append(("Historial: %s  -  %s" % (ti, u[:70]), lambda u=u: self.new_tab(u)))
        d = Palette(self, ent)
        d.move(self.geometry().center().x() - 320, self.geometry().top() + 90)
        d.exec()

    # -- sesión / cierre --------------------------------------------------------------
    def session_path(self):
        return DATA / "session.json"

    def restore_session(self):
        s = []
        if self.core.store["restore"] and not self.private:
            try:
                s = json.loads(self.session_path().read_text("utf-8"))
            except Exception:
                s = []
        if not s:
            self.new_tab(self.core.store["home"] or None)
            return
        first = None
        for e in s:
            pid = e.get("pid", "default")
            if not self.core.pm.get(pid):
                pid = "default"
            t = self.new_tab(None if e.get("nt") else e.get("u"),
                             background=True, profile_id=pid)
            t.pinned = bool(e.get("pin"))
            t.disguise = e.get("dis")
            t.group = e.get("group")
            first = first or t
        if first:
            self.select(first)

    def save_session(self):
        data = []
        for t in self.tabs:
            u = t.view.url().toString()
            data.append({"u": u, "pid": t.profile_id, "pin": t.pinned,
                         "dis": t.disguise, "group": t.group,
                         "nt": t.newtab or not u})
        try:
            p = self.session_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data), "utf-8")
        except Exception:
            traceback.print_exc()

    def closeEvent(self, e):
        panic = getattr(self.core, "panicking", False)
        if not panic and not self.private:
            self.save_session()
            if self.cur:
                self.core.store["last_profile"] = self.cur.profile_id
        if self in self.core.windows:
            self.core.windows.remove(self)
        for m in list(self.core.minis):
            if m.win is self:
                m.close()
        for t in self.tabs:
            try:
                t.view.page().setAudioMuted(True)
            except Exception:
                pass
            t.view.deleteLater()
        if self.private:
            if self.profile in self.core.private_profiles:
                self.core.private_profiles.remove(self.profile)
            QTimer.singleShot(1500, self.profile.deleteLater)
        if not panic:
            self.core.store.save()
        super().closeEvent(e)


def main():
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--enable-smooth-scrolling --disable-features=TranslateUI")
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setStyle("Fusion")
    core = Core(app)
    core.start()




    sys.exit(app.exec())


if __name__ == "__main__":
    main()