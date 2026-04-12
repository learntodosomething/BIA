# ── 1. Dependency check (ELSŐ dolog indításkor) ──────────
import sys, subprocess, importlib

def _quick_check(imp: str) -> bool:
    try: importlib.import_module(imp); return True
    except ImportError: return False

def _pip(pkg: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                       capture_output=True, timeout=300)
    return r.returncode == 0

_REQUIRED = [
    ("PyQt6",        "PyQt6"),
    ("Pillow",       "PIL"),
    ("numpy",        "numpy"),
    ("cryptography", "cryptography"),
    ("huggingface_hub", "huggingface_hub"),
]

_missing_required = []
for _pkg, _imp in _REQUIRED:
    if not _quick_check(_imp):
        print(f"[SETUP] Telepítés: {_pkg}…")
        if _pip(_pkg):
            print(f"[SETUP]   ✓ {_pkg} telepítve")
        else:
            print(f"[SETUP]   ✗ {_pkg} SIKERTELEN")
            _missing_required.append(_pkg)

if _missing_required:
    print(f"\nHIBA: Hiányzó kötelező csomagok: {_missing_required}")
    print("Futtasd manuálisan: pip install " + " ".join(_missing_required))
    sys.exit(1)

# ── 2. Rendes importok ───────────────────────────────────
import os, math, hashlib, random, base64, hmac, json
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSlider, QCheckBox, QLineEdit, QTextEdit,
    QFileDialog, QFrame, QSizePolicy, QComboBox, QProgressBar,
    QMessageBox, QScrollArea, QDialog, QDialogButtonBox, QSpinBox,
    QDoubleSpinBox,
)
from PyQt6.QtGui  import QPixmap, QImage, QFont, QPainter, QColor, QPen
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PIL import Image as PilImage

from engine.id_codec    import ImageID
from engine.palette     import Palette, ensure_palettes
from engine.image_codec import image_to_id, id_to_image, random_id_image
from engine.ai_worker   import AIWorker
from secure import (
    compute_real_hash, make_hash_bundle, open_hash_bundle,
    get_public_masked_hash, mask_hash,
    save_bid, load_bid,
    save_token_file, load_token_file, is_token_encrypted,
    is_bid_encrypted,
    save_hash_file, load_hash_file,
    load_public_masked_hash, is_hash_locked,
    encrypt_bytes, decrypt_bytes, SALT_SIZE,
)
from downloader import model_exists, ensure_model, MODEL_PATH

# ── Opcionális: AI ──────────────────────────────────────
try:
    from ai_server import AIServer
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# ── Opcionális: crypto ──────────────────────────────────
try:
    from cryptography.fernet import InvalidToken
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


# ══════════════════════════════════════════════════════════
def _excepthook(t, v, tb):
    import traceback; traceback.print_exception(t, v, tb)
sys.excepthook = _excepthook

PALETTE_NAMES = ["Grayscale", "Color"]
PALETTE_ENUMS = [Palette.GRAYSCALE, Palette.COLOR]
MAX_IMG = 2048


# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════
def pil_to_qpixmap(img: PilImage.Image) -> QPixmap:
    img = img.convert("RGB")
    qi  = QImage(img.tobytes(), img.width, img.height, img.width * 3,
                 QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qi)

def snap8(v: int) -> int:
    return max(8, (v // 8) * 8)

def _is_crypto_error(e: Exception) -> bool:
    return "InvalidToken" in type(e).__name__ or "Invalid" in str(e)

def is_binary_file(path: str) -> bool:
    """True ha a fájl nem olvasható UTF-8 szövegként (titkosított)."""
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        return not all(32 <= b < 127 for b in header)
    except Exception:
        return True


# ══════════════════════════════════════════════════════════
#  PASSWORD DIALOG  (egyszeri kérés betöltéskor)
# ══════════════════════════════════════════════════════════
_DLG_STYLE = """
    QDialog  { background:#0f0b07; }
    QLabel   { color:#c8b89a; font-family:'Courier New'; font-size:9pt; }
    QLineEdit{ background:#0d0a06; border:1px solid #5c4a28; color:#c8b89a;
               font-family:'Courier New'; font-size:9pt; padding:6px; }
    QPushButton{ background:#1e1810; border:1px solid #5c4a28; color:#c8b89a;
                 font-family:'Courier New'; padding:6px 18px; }
    QPushButton:hover { border-color:#d4a84b; color:#f0deb0; }
    QPushButton:default { border-color:#d4a84b; }
"""

def pw_dialog(parent, title: str, label: str) -> str | None:
    dlg = QDialog(parent); dlg.setWindowTitle(title); dlg.setFixedWidth(380)
    dlg.setStyleSheet(_DLG_STYLE)
    lay = QVBoxLayout(dlg); lay.setContentsMargins(20,20,20,20); lay.setSpacing(10)
    lay.addWidget(QLabel(label))
    edit = QLineEdit(); edit.setEchoMode(QLineEdit.EchoMode.Password)
    edit.setPlaceholderText("Jelszó…"); lay.addWidget(edit)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                          QDialogButtonBox.StandardButton.Cancel)
    bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
    edit.returnPressed.connect(dlg.accept); lay.addWidget(bb)
    return edit.text() if dlg.exec() == QDialog.DialogCode.Accepted else None


# ══════════════════════════════════════════════════════════
#  STYLESHEET
# ══════════════════════════════════════════════════════════
QSS = """
* { font-family:'Courier New','Consolas',monospace; color:#c8b89a; }
QMainWindow, QWidget#root { background:#0f0b07; }
QWidget#leftPanel  { background:#13100b; border-right:2px solid #3a2e1e; }
QWidget#rightPanel { background:#0f0b07; }
QWidget#section    { background:#1a1510; border:1px solid #3a2e1e; border-radius:2px; }

QLabel#canvas { background:#080604; border:2px solid #5c4a28;
                color:#3a2e1e; font-size:13pt; }
QLabel#sectionTitle {
    color:#d4a84b; font-size:9pt; letter-spacing:3px;
    padding:6px 8px; background:#1a1510; border-bottom:1px solid #3a2e1e; }
QLabel { font-size:9pt; }
QLabel#infoValue { color:#e8d5a8; font-size:8pt; }
QLabel#dimLabel  { color:#8a7355; font-size:8pt; }
QLabel#hashReal  { color:#d4a84b; font-size:7pt; font-family:'Courier New'; }
QLabel#hashMask  { color:#7a6040; font-size:7pt; font-family:'Courier New'; }
QLabel#lockIcon  { color:#d4a84b; font-size:11pt; }

QPushButton {
    background:#1e1810; border:1px solid #5c4a28; color:#c8b89a;
    font-size:8pt; letter-spacing:1px; padding:7px 12px; border-radius:1px; }
QPushButton:hover   { background:#2a2015; border-color:#d4a84b; color:#f0deb0; }
QPushButton:pressed { background:#3a2e1e; color:#d4a84b; }
QPushButton:disabled { background:#13100b; border-color:#2a2015; color:#3a2e1e; }
QPushButton#primaryBtn {
    background:#2a1e08; border:1px solid #d4a84b; color:#f0deb0;
    font-size:9pt; letter-spacing:2px; padding:10px; }
QPushButton#primaryBtn:hover    { background:#3d2d0e; color:#ffe9a0; }
QPushButton#primaryBtn:disabled { background:#13100b; border-color:#2a2015; color:#3a2e1e; }

QSlider::groove:horizontal  { height:3px; background:#2a2015; border-radius:1px; }
QSlider::sub-page:horizontal{ background:#d4a84b; border-radius:1px; }
QSlider::handle:horizontal  { background:#d4a84b; width:12px; height:12px;
                               margin:-5px 0; border-radius:1px; }
QSlider::handle:horizontal:hover { background:#ffe9a0; }

QCheckBox { font-size:8pt; spacing:6px; }
QCheckBox::indicator { width:14px; height:14px; border:1px solid #5c4a28;
                       background:#13100b; border-radius:1px; }
QCheckBox::indicator:checked { background:#d4a84b; border-color:#d4a84b; }

QLineEdit, QTextEdit {
    background:#0d0a06; border:1px solid #3a2e1e; color:#c8b89a;
    font-size:8pt; padding:5px 8px; border-radius:1px;
    selection-background-color:#5c4a28; }
QLineEdit:focus, QTextEdit:focus { border-color:#d4a84b; }
QLineEdit#pwField { border-color:#5c4a28; color:#d4a84b; letter-spacing:1px; }
QLineEdit#pwField:focus { border-color:#d4a84b; }

QSpinBox, QDoubleSpinBox {
    background:#0d0a06; border:1px solid #3a2e1e; color:#c8b89a;
    font-size:8pt; padding:3px 6px; border-radius:1px; }
QSpinBox:focus, QDoubleSpinBox:focus { border-color:#d4a84b; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background:#2a2015; border:none; width:16px; }

QComboBox { background:#13100b; border:1px solid #3a2e1e; color:#c8b89a;
            font-size:8pt; padding:4px 8px; border-radius:1px; }
QComboBox:hover { border-color:#d4a84b; }
QComboBox::drop-down { border:none; width:20px; }
QComboBox QAbstractItemView { background:#1a1510; border:1px solid #5c4a28;
    color:#c8b89a; selection-background-color:#3a2e1e; }

QProgressBar { border:1px solid #3a2e1e; background:#0d0a06;
               height:4px; border-radius:1px; }
QProgressBar::chunk { background:#d4a84b; border-radius:1px; }

QScrollBar:vertical { background:#0f0b07; width:6px; border:none; }
QScrollBar::handle:vertical { background:#3a2e1e; border-radius:3px; min-height:20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }

QStatusBar { background:#0a0806; border-top:1px solid #2a2015;
             font-size:7pt; color:#5c4a28; }
QFrame#divider { background:#2a2015; max-height:1px; }
"""


# ══════════════════════════════════════════════════════════
#  CANVAS
# ══════════════════════════════════════════════════════════
class CanvasWidget(QLabel):
    def __init__(self):
        super().__init__()
        self.setObjectName("canvas")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(640, 400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._raw: QPixmap | None = None
        self.show_grid = False

    def set_image(self, pil: PilImage.Image):
        self._raw = pil_to_qpixmap(pil); self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        W, H = self.width(), self.height()
        p.fillRect(0, 0, W, H, QColor("#080604"))
        if self._raw is None:
            p.setPen(QPen(QColor("#2a2015")))
            p.setFont(QFont("Courier New", 11))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "▣\n\nNo image loaded")
            p.end(); return
        pm = self._raw.scaled(W, H, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.FastTransformation)
        ox = (W - pm.width()) // 2
        oy = (H - pm.height()) // 2
        p.drawPixmap(ox, oy, pm)
        if self.show_grid:
            sw = self._raw.width(); cw = pm.width() / sw
            if cw >= 6:
                p.setPen(QPen(QColor(0,0,0,80), 0.5))
                sh = self._raw.height(); ch = pm.height() / sh
                for i in range(sw+1):
                    x = ox + int(i*cw); p.drawLine(x, oy, x, oy+pm.height())
                for j in range(sh+1):
                    y = oy + int(j*ch); p.drawLine(ox, y, ox+pm.width(), y)
        p.end()


# ══════════════════════════════════════════════════════════
#  UI FACTORIES
# ══════════════════════════════════════════════════════════
def make_section(title: str, *widgets) -> QWidget:
    box = QWidget(); box.setObjectName("section")
    lay = QVBoxLayout(box); lay.setContentsMargins(0,0,0,0); lay.setSpacing(0)
    hdr = QLabel(title); hdr.setObjectName("sectionTitle"); lay.addWidget(hdr)
    inner = QWidget()
    il = QVBoxLayout(inner); il.setContentsMargins(10,8,10,10); il.setSpacing(6)
    for w in widgets:
        if isinstance(w, QWidget): il.addWidget(w)
    lay.addWidget(inner); return box

def hdivider() -> QFrame:
    f = QFrame(); f.setObjectName("divider"); f.setFrameShape(QFrame.Shape.HLine); return f

def dim_lbl(t: str) -> QLabel:
    l = QLabel(t); l.setObjectName("dimLabel"); return l

def info_row(name: str, val: QLabel) -> QWidget:
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0,0,0,0)
    n = dim_lbl(name); n.setFixedWidth(90); h.addWidget(n); h.addWidget(val, 1); return w


# ══════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════
class BabylonWindow(QMainWindow):

    def __init__(self, ai_server=None):
        super().__init__()
        self.ai_server     = ai_server
        self.ai_worker     = None
        self.is_generating = False
        self.current_pil:  PilImage.Image | None = None
        self.current_id:   ImageID | None = None
        self.current_hash: str = ""          # igazi hash
        self.source_pil:   PilImage.Image | None = None
        self._raw_token:   str = ""          # titkositatlan token (alap allapot)

        self.setWindowTitle("BABYLON  IMAGE ARCHIVE")
        self.resize(1540, 920)
        sg = QApplication.primaryScreen().geometry()
        self.move((sg.width()-self.width())//2, (sg.height()-self.height())//2)

        ensure_palettes()
        self._build_ui()
        self.setStyleSheet(QSS)
        self._update_info()

    # ── Active password (from right panel field) ─────────
    @property
    def _active_pw(self) -> str | None:
        """None ha üres, string ha be van írva."""
        v = self.pw_field.text().strip()
        return v if v else None

    # ══════════════════════════════════════════════════════
    #  UI BUILD
    # ══════════════════════════════════════════════════════
    def _build_ui(self):
        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        m = QHBoxLayout(root); m.setContentsMargins(0,0,0,0); m.setSpacing(0)
        m.addWidget(self._left_panel(), 4)
        m.addWidget(self._right_panel(), 1)

    # ─── LEFT ────────────────────────────────────────────
    def _left_panel(self) -> QWidget:
        p = QWidget(); p.setObjectName("leftPanel")
        v = QVBoxLayout(p); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
        self.info_bar = QLabel("  BABYLON IMAGE ARCHIVE  ·  NO IMAGE")
        self.info_bar.setObjectName("sectionTitle"); self.info_bar.setMinimumHeight(32)
        v.addWidget(self.info_bar)
        self.canvas = CanvasWidget()
        v.addWidget(self.canvas, 1)
        v.addWidget(hdivider())
        v.addWidget(self._toolbar())
        return p

    def _toolbar(self) -> QWidget:
        bar = QWidget(); bar.setObjectName("section")
        lay = QHBoxLayout(bar); lay.setContentsMargins(10,8,10,8); lay.setSpacing(6)
        def B(lbl, fn): b = QPushButton(lbl); b.clicked.connect(fn); return b
        lay.addWidget(B("OPEN IMAGE",   self.open_source_image))
        lay.addWidget(B("PIXELATE→ID",  self.encode_image))
        lay.addWidget(B("RECONSTRUCT",  self.decode_id))
        lay.addWidget(B("⬡ RANDOM",     self.random_image))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background:#3a2e1e; max-width:1px;"); lay.addWidget(sep)
        lay.addWidget(B("SAVE IMAGE",   self.save_current_image))
        lay.addWidget(self._bid_save_widget())
        lay.addWidget(B("LOAD BID",     self.load_bid_action))
        lay.addWidget(B("SAVE TOKEN",   self.save_token_action))
        lay.addWidget(B("LOAD HASH",    self.load_hash_action))
        lay.addStretch()
        return bar

    # ── BID formátum választó + SAVE BID gomb ────────────
    def _bid_save_widget(self) -> QWidget:
        FMT_SS = (
            "QPushButton{background:#13100b;border:1px solid #3a2e1e;color:#5c4a28;"
            "font-family:'Courier New';font-size:7pt;padding:3px 7px;border-radius:1px;}"
            "QPushButton:checked{background:#2a1e08;border-color:#d4a84b;color:#d4a84b;}"
            "QPushButton:hover{border-color:#8a6a30;color:#c8b89a;}"
        )
        container = QWidget()
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(2)

        fmt_row = QWidget()
        flay = QHBoxLayout(fmt_row)
        flay.setContentsMargins(0, 0, 0, 0)
        flay.setSpacing(2)

        self._bid_fmt_btns = {}
        for fmt in ("zlib", "lzma", "raw"):
            btn = QPushButton(fmt)
            btn.setCheckable(True)
            btn.setStyleSheet(FMT_SS)
            btn.clicked.connect(lambda checked, f=fmt: self._select_bid_fmt(f))
            self._bid_fmt_btns[fmt] = btn
            flay.addWidget(btn)
        vlay.addWidget(fmt_row)

        btn_save = QPushButton("SAVE BID")
        btn_save.clicked.connect(self.save_bid_action)
        vlay.addWidget(btn_save)

        self._bid_fmt_selected = "zlib"
        self._bid_fmt_btns["zlib"].setChecked(True)
        return container

    def _select_bid_fmt(self, fmt: str):
        self._bid_fmt_selected = fmt
        for f, btn in self._bid_fmt_btns.items():
            btn.setChecked(f == fmt)

    # ─── RIGHT ───────────────────────────────────────────
    def _right_panel(self) -> QWidget:
        p = QWidget(); p.setObjectName("rightPanel")
        sc = QScrollArea(); sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.Shape.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner); lay.setContentsMargins(12,12,12,12); lay.setSpacing(10)
        lay.addWidget(self._pw_section())        # ← ELSŐ: jelszó
        lay.addWidget(self._size_section())
        lay.addWidget(self._codec_section())
        lay.addWidget(self._hash_section())      # hash kijelző
        lay.addWidget(self._id_info_section())
        lay.addWidget(self._ai_section())
        lay.addStretch()
        footer = QLabel("Made by: Ozogány László")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color:#3a2e1e; font-size:7pt; padding:8px;")
        lay.addWidget(footer)
        sc.setWidget(inner)
        out = QVBoxLayout(p); out.setContentsMargins(0,0,0,0); out.setSpacing(0)
        out.addWidget(sc); return p

    # ── Password section ─────────────────────────────────
    def _pw_section(self) -> QWidget:
        note = QLabel(
            "Ha be van írva jelszó, minden mentett\n"
            "BID és Hash fájl ezzel lesz titkosítva.\n"
            "A hash-t is maszkolja — a publikus hash\n"
            "szándékosan eltér az igazitól.")
        note.setStyleSheet("color:#5c4a28; font-size:7pt;"); note.setWordWrap(True)

        pw_row = QWidget(); pr = QHBoxLayout(pw_row)
        pr.setContentsMargins(0,0,0,0); pr.setSpacing(6)
        lock_lbl = QLabel("🔒"); lock_lbl.setObjectName("lockIcon"); lock_lbl.setFixedWidth(22)
        self.pw_field = QLineEdit()
        self.pw_field.setObjectName("pwField")
        self.pw_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_field.setPlaceholderText("Jelszó (opcionális)…")
        self.pw_field.textChanged.connect(self._on_pw_changed)
        self.pw_show_btn = QPushButton("👁")
        self.pw_show_btn.setFixedWidth(30); self.pw_show_btn.setCheckable(True)
        self.pw_show_btn.toggled.connect(
            lambda on: self.pw_field.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        pr.addWidget(lock_lbl); pr.addWidget(self.pw_field, 1); pr.addWidget(self.pw_show_btn)

        self.pw_status = QLabel("NINCS JELSZÓ — fájlok titkosítatlanok")
        self.pw_status.setStyleSheet("color:#5c4a28; font-size:7pt;")

        btn_clear = QPushButton("JELSZÓ TÖRLÉSE")
        btn_clear.clicked.connect(lambda: self.pw_field.clear())

        return make_section("🔐  JELSZÓVÉDELEM", note, pw_row, self.pw_status, btn_clear)

    def _on_pw_changed(self, txt: str):
        if txt.strip():
            self.pw_status.setText(f"🔒 AKTÍV — mentések titkosítva")
            self.pw_status.setStyleSheet("color:#d4a84b; font-size:7pt;")
        else:
            self.pw_status.setText("NINCS JELSZÓ — fájlok titkosítatlanok")
            self.pw_status.setStyleSheet("color:#5c4a28; font-size:7pt;")
        self._update_hash_display()
        self._update_token_display()

    # ── Size section ──────────────────────────────────────
    def _size_section(self) -> QWidget:
        self.w_val, self.h_val = 320, 180
        self.lbl_w = dim_lbl(f"WIDTH  {self.w_val}px")
        self.slider_w = QSlider(Qt.Orientation.Horizontal)
        self.slider_w.setRange(8, MAX_IMG); self.slider_w.setValue(self.w_val)
        self.slider_w.valueChanged.connect(self._on_w)
        self.lbl_h = dim_lbl(f"HEIGHT  {self.h_val}px")
        self.slider_h = QSlider(Qt.Orientation.Horizontal)
        self.slider_h.setRange(8, MAX_IMG); self.slider_h.setValue(self.h_val)
        self.slider_h.valueChanged.connect(self._on_h)
        self.chk_square  = QCheckBox("Maintain square pixels")
        self.chk_auto_wh = QCheckBox("Auto-match source ratio")
        return make_section("IMAGE DIMENSIONS",
            self.lbl_w, self.slider_w, self.lbl_h, self.slider_h,
            self.chk_square, self.chk_auto_wh)

    # ── Codec section ─────────────────────────────────────
    def _codec_section(self) -> QWidget:
        lp = dim_lbl("COLOR PALETTE")
        self.combo_palette = QComboBox(); self.combo_palette.addItems(PALETTE_NAMES)
        self.lbl_vps = dim_lbl("VALUES / SEGMENT  2")
        self.slider_vps = QSlider(Qt.Orientation.Horizontal)
        self.slider_vps.setRange(1, 15); self.slider_vps.setValue(2)
        self.slider_vps.valueChanged.connect(
            lambda v: self.lbl_vps.setText(f"VALUES / SEGMENT  {v}"))
        self.chk_grid = QCheckBox("Show pixel grid")
        self.chk_grid.stateChanged.connect(
            lambda s: (setattr(self.canvas, "show_grid", bool(s)), self.canvas.update()))
        help_txt = QLabel(
            "PIXELATE → ID  tömöríti a képet Babylon\n"
            "bit-csomagolt ID formátumba.\n"
            "RECONSTRUCT újrarajzolja az ID-ből.")
        help_txt.setStyleSheet("color:#5c4a28; font-size:7pt;"); help_txt.setWordWrap(True)
        return make_section("CODEC SETTINGS",
            lp, self.combo_palette, self.lbl_vps, self.slider_vps,
            self.chk_grid, help_txt)

    # ── Hash display section ──────────────────────────────
    def _hash_section(self) -> QWidget:
        BTN_SS = ("QPushButton{background:#13100b;border:1px solid #3a2e1e;color:#5c4a28;"
                  "font-size:7pt;padding:2px 5px;}"
                  "QPushButton:hover{border-color:#d4a84b;color:#d4a84b;}")

        def hash_block(label_txt, attr, copy_fn, save_fn):
            note = dim_lbl(label_txt)
            lbl = QLabel("—")
            lbl.setObjectName(attr)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            btn_row = QWidget(); br = QHBoxLayout(btn_row)
            br.setContentsMargins(0,0,0,0); br.setSpacing(4)
            btn_copy = QPushButton("COPY"); btn_copy.setStyleSheet(BTN_SS)
            btn_copy.setFixedWidth(46); btn_copy.clicked.connect(copy_fn)
            btn_save = QPushButton("SAVE"); btn_save.setStyleSheet(BTN_SS)
            btn_save.setFixedWidth(46); btn_save.clicked.connect(save_fn)
            br.addWidget(btn_copy); br.addWidget(btn_save); br.addStretch()
            return note, lbl, btn_row

        note_r, self.lbl_real_hash, row_r = hash_block(
            "IGAZI HASH  (SHA-256 a képről):", "hashReal",
            self._copy_real_hash, self._save_real_hash)
        note_p, self.lbl_pub_hash, row_p = hash_block(
            "PUBLIKUS HASH  (jelszóval maszkolt):", "hashMask",
            self._copy_pub_hash, self._save_pub_hash)

        note3 = QLabel(
            "A publikus hash mást mutat ha van jelszó.\n"
            "Ezt lehet megosztani — az igazi képet\n"
            "csak a helyes jelszóval lehet visszakapni.")
        note3.setStyleSheet("color:#5c4a28; font-size:7pt;"); note3.setWordWrap(True)

        return make_section("IMAGE HASH",
            note_r, self.lbl_real_hash, row_r,
            note_p, self.lbl_pub_hash, row_p,
            note3)

    # ── ID info section ───────────────────────────────────
    def _id_info_section(self) -> QWidget:
        def iv(): l = QLabel("—"); l.setObjectName("infoValue"); return l
        self.lbl_id_size  = iv(); self.lbl_id_segs  = iv()
        self.lbl_id_vps   = iv(); self.lbl_id_pal   = iv(); self.lbl_id_chars = iv()
        return make_section("CURRENT ID",
            info_row("SIZE",      self.lbl_id_size),
            info_row("SEGMENTS",  self.lbl_id_segs),
            info_row("VALS/SEG",  self.lbl_id_vps),
            info_row("PALETTE",   self.lbl_id_pal),
            info_row("ID LENGTH", self.lbl_id_chars))

    # ── AI section ────────────────────────────────────────
    def _ai_section(self) -> QWidget:
        # ── Image Token (önálló kép-karakterlánc) ─────────
        lbl_token = dim_lbl("IMAGE TOKEN — KÉP KARAKTERLÁNCBÓL")
        note_token = QLabel(
            "Illeszd be a megosztott Image Token szöveget és\n"
            "a kép azonnal megjelenik — BID fájl nem kell hozzá.\n"
            "Az Image Token önmaga tartalmazza az összes képadatot.")
        note_token.setStyleSheet("color:#5c4a28; font-size:7pt;")
        note_token.setWordWrap(True)

        self.txt_token_input = QTextEdit()
        self.txt_token_input.setPlaceholderText(
            "Illeszd be az Image Token szöveget ide…\n"
            "(a SAVE BID → Token gombbal generálható)")
        self.txt_token_input.setMaximumHeight(70)
        self.txt_token_input.setStyleSheet("font-family:\'Courier New\'; font-size:7pt;")

        self.btn_token_load = QPushButton("KÉP BETÖLTÉSE TOKENBŐL")
        self.btn_token_load.clicked.connect(self.load_from_token)
        self.btn_token_file = QPushButton("BETÖLTÉS FÁJLBÓL 🔒")
        self.btn_token_file.clicked.connect(self.load_token_file_action)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background:#2a2015; max-height:1px;")

        # ── AI generálás ───────────────────────────────────
        lbl_pos = dim_lbl("POSITIVE PROMPT")
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setPlaceholderText(
            "Describe the image…\npl. ancient mesopotamian relief, dramatic lighting")
        self.txt_prompt.setMaximumHeight(72)

        lbl_neg = dim_lbl("NEGATIVE PROMPT")
        self.txt_neg = QTextEdit()
        self.txt_neg.setPlaceholderText("What to avoid…")
        self.txt_neg.setMaximumHeight(50)
        self.txt_neg.setPlainText(
            "lowres, bad anatomy, bad hands, cropped, worst quality, low quality, watermark")

        params_row = QWidget(); pr = QHBoxLayout(params_row)
        pr.setContentsMargins(0,0,0,0); pr.setSpacing(6)
        pr.addWidget(dim_lbl("STEPS"))
        self.spin_steps = QSpinBox(); self.spin_steps.setRange(1, 10)
        self.spin_steps.setValue(2); self.spin_steps.setFixedWidth(55)
        pr.addWidget(self.spin_steps)
        pr.addWidget(dim_lbl("CFG"))
        self.spin_cfg = QDoubleSpinBox(); self.spin_cfg.setRange(0.0, 5.0)
        self.spin_cfg.setSingleStep(0.1); self.spin_cfg.setValue(0.0)
        self.spin_cfg.setFixedWidth(55); pr.addWidget(self.spin_cfg)
        pr.addStretch()

        btn_row = QWidget(); br = QHBoxLayout(btn_row)
        br.setContentsMargins(0,0,0,0); br.setSpacing(6)

        self.btn_ai_gen = QPushButton("GENERATE WITH AI")
        self.btn_ai_gen.setObjectName("primaryBtn")
        self.btn_ai_gen.clicked.connect(self.start_ai_generation)
        if not self.ai_server:
            self.btn_ai_gen.setEnabled(False)
            self.btn_ai_gen.setToolTip("AI server not loaded")
        br.addWidget(self.btn_ai_gen, 1)

        self.btn_ai_cancel = QPushButton("✕ STOP")
        self.btn_ai_cancel.setObjectName("dangerBtn")
        self.btn_ai_cancel.setVisible(False)
        self.btn_ai_cancel.clicked.connect(self.cancel_ai_generation)
        br.addWidget(self.btn_ai_cancel)

        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 0)    # indeterminate
        self.ai_progress.setVisible(False)
        self.ai_progress.setFixedHeight(6)
        self.ai_progress.setTextVisible(False)

        return make_section("AI GENERATION  &  IMAGE TOKEN",
            lbl_token, note_token,
            self.txt_token_input, self.btn_token_load, self.btn_token_file,
            sep,
            lbl_pos, self.txt_prompt,
            lbl_neg, self.txt_neg,
            params_row,
            btn_row, self.ai_progress)

    # ══════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════
    def _on_w(self, v): self.w_val = snap8(v); self.lbl_w.setText(f"WIDTH  {self.w_val}px")
    def _on_h(self, v): self.h_val = snap8(v); self.lbl_h.setText(f"HEIGHT  {self.h_val}px")
    def _palette(self) -> Palette: return PALETTE_ENUMS[self.combo_palette.currentIndex()]
    def _vps(self) -> int: return self.slider_vps.value()

    def _set_current(self, pil: PilImage.Image, iid: ImageID | None = None):
        self.current_pil  = pil
        self.current_id   = iid
        self.current_hash = compute_real_hash(pil)
        self.canvas.set_image(pil)
        # Token automatikus frissítése: ha van ID, generálja és jeleníti meg
        if iid is not None:
            try:
                self._set_raw_token(iid.to_token())
            except Exception:
                pass
        else:
            # AI kép vagy sima betöltött kép: nincs token
            self._raw_token = ""
            self.txt_token_input.setPlainText("")
            self.txt_token_input.setToolTip("Nincs Image Token — pixelezd a képet.")

    def _update_hash_display(self):
        """Frissíti a hash szekciót — igazi + maszkolt hash."""
        if not self.current_hash:
            self.lbl_real_hash.setText("—")
            self.lbl_pub_hash.setText("—")
            return

        # Igazi hash mindig látszik
        rh = self.current_hash
        self.lbl_real_hash.setText(rh[:32] + "\n" + rh[32:])

        # Publikus hash: jelszóval maszkolt, különben ugyanaz
        pw = self._active_pw
        if pw:
            import os
            salt = hashlib.sha256((pw + rh[:8]).encode()).digest()[:SALT_SIZE]
            pub = mask_hash(rh, pw, salt)
            self.lbl_pub_hash.setText(pub[:32] + "\n" + pub[32:])
        else:
            self.lbl_pub_hash.setText(rh[:32] + "\n" + rh[32:])
            self.lbl_pub_hash.setStyleSheet(
                "color:#7a6040; font-size:7pt; font-family:'Courier New';")

    def _set_raw_token(self, token: str):
        """
        Beállítja az alap (titkosítatlan) tokent és azonnal frissíti a megjelenítést.
        Ezt kell hívni minden kép-beállításkor.
        """
        self._raw_token = token
        self._update_token_display()

    def _update_token_display(self):
        """
        Élőben frissíti a token mezőt a jelszó alapján:
          - Ha van jelszó: titkosított base85 token jelenik meg
          - Ha nincs: az eredeti titkosítatlan token jelenik meg
          - Ha nincs token: üres / placeholder marad
        """
        if not self._raw_token:
            return  # nincs mit frissíteni

        pw = self._active_pw
        if pw:
            try:
                # Token titkosítása a jelszóval: base85(AES(raw_token))
                import base64 as _b64
                enc = encrypt_bytes(self._raw_token.encode("utf-8"), pw)
                # Külön prefix hogy betöltéskor felismerjük: ENC: + base85
                display = "ENC:" + _b64.b85encode(enc).decode("ascii")
                self.txt_token_input.setPlainText(display)
                self.txt_token_input.setToolTip(
                    "Ez a token jelszoval titkositott. "
                    "Csak ugyanezzel a jelszoval toltheto vissza."
                )
            except Exception:
                self.txt_token_input.setPlainText(self._raw_token)
        else:
            self.txt_token_input.setPlainText(self._raw_token)
            self.txt_token_input.setToolTip("Titkosítatlan Image Token.")

    # ══════════════════════════════════════════════════════
    #  OPEN IMAGE
    # ══════════════════════════════════════════════════════
    def open_source_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Source Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)")
        if not path: return
        try:
            self.source_pil = PilImage.open(path).convert("RGB")
            self._set_current(self.source_pil.copy())
            if self.chk_auto_wh.isChecked():
                sw, sh = self.source_pil.size
                self.slider_w.setValue(min(sw, MAX_IMG))
                self.slider_h.setValue(min(sh, MAX_IMG))
            self._update_info(f"OPENED  ·  {Path(path).name}  ·  "
                              f"{self.source_pil.width}×{self.source_pil.height}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════
    #  PIXELATE / RECONSTRUCT / RANDOM
    # ══════════════════════════════════════════════════════
    def encode_image(self):
        if self.source_pil is None:
            QMessageBox.information(self, "No source", "Open a source image first."); return
        try:
            iid = image_to_id(self.source_pil, (self.w_val, self.h_val),
                              self._vps(), self._palette())
            self._set_current(id_to_image(iid), iid)
            self._update_info()
            # Auto-fill token field
            try:
                self._set_raw_token(iid.to_token())
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Pixelate error", str(e))

    def decode_id(self):
        if self.current_id is None:
            QMessageBox.information(self, "No ID",
                "Pixelate an image or load a BID file first."); return
        try:
            self._set_current(id_to_image(self.current_id), self.current_id)
            self._update_info("RECONSTRUCTED FROM ID")
        except Exception as e:
            QMessageBox.critical(self, "Reconstruct error", str(e))

    def random_image(self):
        try:
            pil, iid = random_id_image((self.w_val, self.h_val), self._vps(), self._palette())
            self._set_current(pil, iid); self._update_info("RANDOM ID IMAGE")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════
    #  SAVE IMAGE
    # ══════════════════════════════════════════════════════
    def save_current_image(self):
        if self.current_pil is None:
            QMessageBox.information(self, "No image", "Nothing to save."); return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Image", "output.png",
            "PNG (*.png);;JPEG (*.jpg);;BMP (*.bmp)")
        if path:
            try:
                self.current_pil.save(path)
                self.statusBar().showMessage(f"IMAGE SAVED → {path}")
            except Exception as e:
                QMessageBox.critical(self, "Save error", str(e))

    # ══════════════════════════════════════════════════════
    #  SAVE / LOAD BID
    # ══════════════════════════════════════════════════════
    def save_bid_action(self):
        if self.current_id is None:
            QMessageBox.information(self, "No ID",
                "Pixelate an image, generate a random one, or load a BID first."); return
        fmt = getattr(self, "_bid_fmt_selected", "zlib")
        fpath, _ = QFileDialog.getSaveFileName(
            self, "Save BID", f"image_{fmt}.bid", "Babylon ID (*.bid);;All (*)")
        if not fpath: return
        pw = self._active_pw
        try:
            import zlib as _zlib, lzma as _lzma, struct as _st
            iid = self.current_id
            # Build raw payload (header + segments), format-specific compression
            w, h = iid.size
            from engine.id_codec import TOKEN_MAGIC
            header = TOKEN_MAGIC + _st.pack("<HHBBi",
                w, h, iid.values_per_segment, iid.palette_index, len(iid._segments))
            seg_data = _st.pack(f"<{len(iid._segments)}H",
                                *[s.value for s in iid._segments])
            raw_inner = header + seg_data
            if fmt == "zlib":
                raw = b"Z" + _zlib.compress(raw_inner, level=9)
            elif fmt == "lzma":
                raw = b"L" + _lzma.compress(raw_inner, preset=9)
            elif fmt == "raw":
                raw = b"R" + raw_inner
            else:
                raw = b"Z" + _zlib.compress(raw_inner, level=9)
            if pw:
                raw = encrypt_bytes(raw, pw)
            with open(fpath, "wb") as _f:
                _f.write(raw)
            lock = "🔒" if pw else ""
            self.statusBar().showMessage(f"BID SAVED {lock} [{fmt}] → {fpath}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def _parse_bid_bytes(self, raw: bytes):
        """Betölti az ImageID-t a nyers (már dekódolt) bájtokból.
        Kezeli a Z/L/R prefix formátumot és a legacy zlib-et."""
        import zlib as _zlib, lzma as _lzma
        from engine.id_codec import ImageID, TOKEN_MAGIC
        mode = raw[0:1]
        if mode == b"Z":
            inner = _zlib.decompress(raw[1:])
        elif mode == b"L":
            inner = _lzma.decompress(raw[1:])
        elif mode == b"R":
            inner = raw[1:]
        else:
            # Legacy: az egész adat zlib (prefix nélkül)
            inner = _zlib.decompress(raw)
        return ImageID.from_bytes(b"Z" + _zlib.compress(inner))  # újracsomagoljuk a from_bytes-hoz

    def load_bid_action(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load BID", "", "Babylon ID (*.bid);;All (*)")
        if not path: return

        # Magic-byte alapu detekció: pontosan tudja titkositott-e
        encrypted = is_bid_encrypted(path)
        pw = self._active_pw

        if encrypted and not pw:
            pw = pw_dialog(self, "Jelszo szukseges",
                           "Ez a BID fajl jelszoval vedett.\nAdd meg a jelszot:")
            if pw is None: return

        try:
            iid = load_bid(path, pw)
        except Exception as e:
            if "ENCRYPTED" in str(e):
                pw2 = pw_dialog(self, "Jelszo szukseges", "Add meg a jelszot:")
                if pw2 is None: return
                try:
                    iid = load_bid(path, pw2)
                except Exception:
                    QMessageBox.critical(self, "Hibas jelszo", "Helytelen jelszo."); return
            elif _is_crypto_error(e):
                QMessageBox.critical(self, "Hibas jelszo", "Helytelen jelszo."); return
            else:
                QMessageBox.critical(self, "Load error", str(e)); return

        try:
            self._set_current(id_to_image(iid), iid)
            self._update_info(f"BID LOADED  {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Decode error", str(e))

    def save_token_action(self):
        """Image Token mentese szovegfajlba — magic-byte alapu lock detection."""
        if self.current_id is None:
            QMessageBox.information(self, "Nincs ID",
                "Pixelate egy kepet vagy tolts be egy BID-et."); return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Image Token", "image_token.tok",
            "Token (*.tok);;Text (*.txt);;All (*)")
        if not path: return
        try:
            token = self.current_id.to_token()
            pw    = self._active_pw
            if pw:
                r = QMessageBox.question(self, "Titkositas?",
                    f"Be van allitva jelszo. Titkositod a token fajlt?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                    QMessageBox.StandardButton.Cancel)
                if r == QMessageBox.StandardButton.Cancel: return
                if r == QMessageBox.StandardButton.No: pw = None
            save_token_file(path, token, pw)
            if pw:
                self.statusBar().showMessage(f"TOKEN SAVED (titkositva) → {path}")
            else:
                self.txt_token_input.setPlainText(token)
                self.statusBar().showMessage(f"TOKEN SAVED → {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    # ══════════════════════════════════════════════════════
    #  HASH COPY / SAVE HELPERS
    # ══════════════════════════════════════════════════════
    def _copy_real_hash(self):
        if self.current_hash:
            QApplication.clipboard().setText(self.current_hash)
            self.statusBar().showMessage("✓ Igazi hash vágólapra másolva")

    def _copy_pub_hash(self):
        txt = self.lbl_pub_hash.text().replace("\n", "")
        if txt and txt != "—":
            QApplication.clipboard().setText(txt)
            self.statusBar().showMessage("✓ Publikus hash vágólapra másolva")

    def _save_real_hash(self):
        if not self.current_hash:
            QMessageBox.information(self, "No hash", "Nincs hash — tölts be vagy generálj képet."); return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Real Hash", "real_hash.bhash", "Babylon Hash (*.bhash);;Text (*.txt);;All (*)")
        if not path: return
        pw = self._active_pw
        try:
            save_hash_file(path, self.current_hash, pw)
            lock = "🔒" if pw else ""
            self.statusBar().showMessage(f"REAL HASH SAVED {lock} → {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def _save_pub_hash(self):
        pub = self.lbl_pub_hash.text().replace("\n", "")
        if not pub or pub == "—":
            QMessageBox.information(self, "No hash", "Nincs publikus hash."); return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Public Hash", "public_hash.txt", "Text (*.txt);;All (*)")
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(pub + "\n")
            self.statusBar().showMessage(f"PUBLIC HASH SAVED → {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    # ══════════════════════════════════════════════════════
    #  SAVE / LOAD HASH
    # ══════════════════════════════════════════════════════
    def save_hash_action(self):
        if not self.current_hash:
            QMessageBox.information(self, "No hash",
                "Open or generate an image first."); return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Hash", "image_hash.bhash", "Babylon Hash (*.bhash);;Text (*.txt);;All (*)")
        if not path: return
        pw = self._active_pw
        try:
            save_hash_file(path, self.current_hash, pw)
            lock = "🔒 maszkolt + titkosított" if pw else "titkosítatlan"
            self.statusBar().showMessage(f"HASH SAVED ({lock}) → {path}")
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    def load_hash_action(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Hash", "", "Babylon Hash (*.bhash);;Text (*.txt);;All (*)")
        if not path: return

        locked = is_hash_locked(path)
        pub_hash = load_public_masked_hash(path)

        pw = self._active_pw
        if locked and not pw:
            pw = pw_dialog(self, "Jelszó szükséges",
                           f"Védett hash fájl.\nPublikus (maszkolt) hash:\n{pub_hash[:32]}…\n\n"
                           "Add meg a jelszót a valódi hash-hez:")
            if pw is None: return

        try:
            real_hash = load_hash_file(path, pw)
            self.current_hash = real_hash
            self._update_hash_display()
            self.statusBar().showMessage(f"HASH LOADED  ·  {real_hash[:20]}…")
            QMessageBox.information(self, "Hash betöltve",
                f"Igazi SHA-256 hash:\n{real_hash}\n\n"
                f"Publikus (maszkolt) hash:\n{pub_hash}\n\n"
                "Megjegyzés: a hash önmagában nem elég\n"
                "a kép visszaállításához — BID fájl kell hozzá.")
        except Exception as e:
            if _is_crypto_error(e):
                QMessageBox.critical(self, "Hibás jelszó", "Helytelen jelszó.")
            else:
                QMessageBox.critical(self, "Load error", str(e))

    # ══════════════════════════════════════════════════════
    #  AI GENERATION
    # ══════════════════════════════════════════════════════
    def load_from_token(self):
        """
        Image Token mezőből visszaállítja a képet.
        Ha ENC: prefix van → jelszóval dekódolja előbb.
        Ha a _raw_token tele van → azt használja közvetlenül.
        """
        from engine.id_codec import ImageID
        from engine.image_codec import id_to_image
        import base64 as _b64

        # Ha van tárolt nyers token, azt használjuk (nem a megjelenített titkosítottat)
        if self._raw_token:
            token = self._raw_token
        else:
            token = self.txt_token_input.toPlainText().strip()

        if not token:
            QMessageBox.information(self, "Üres", "Illessz be egy Image Token szöveget.")
            return

        # Ha a beillesztett szöveg ENC: prefixű → jelszóval titkosított token
        if token.startswith("ENC:"):
            pw = self._active_pw
            if not pw:
                pw = pw_dialog(self, "Jelszó szükséges",
                               "Ez a token jelszóval titkosított.\nAdd meg a jelszót:")
                if pw is None: return
            try:
                enc_bytes = _b64.b85decode(token[4:].encode("ascii"))
                token = decrypt_bytes(enc_bytes, pw).decode("utf-8")
            except Exception:
                QMessageBox.critical(self, "Hibás jelszó",
                    "Nem sikerült dekódolni a tokent.\nEllenőrizd a jelszót."); return

        try:
            iid = ImageID.from_token(token)
            pil = id_to_image(iid)
            self._set_current(pil, iid)
            self._set_raw_token(token)
            self._update_info(f"TOKEN BETÖLTVE  ·  {iid.size[0]}×{iid.size[1]}")
            self.statusBar().showMessage("✓ Image Token sikeresen betöltve")
        except Exception as e:
            QMessageBox.critical(self, "Token hiba",
                f"Nem sikerült betölteni a tokent:\n{e}\n\n"
                "Ellenőrizd hogy a teljes token szöveg be van illesztve.")

    def load_token_file_action(self):
        """Token fajl betoltese — magic-byte alapu automatikus lock detection."""
        from engine.id_codec import ImageID
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Token File", "", "Token (*.tok);;Text (*.txt);;All (*)")
        if not path: return
        try:
            encrypted = is_token_encrypted(path)
            pw = self._active_pw
            if encrypted and not pw:
                pw = pw_dialog(self, "Jelszo szukseges",
                               "Ez a token fajl jelszoval vedett.\nAdd meg a jelszot:")
                if pw is None: return
            token = load_token_file(path, pw)
            iid = ImageID.from_token(token)
            from engine.image_codec import id_to_image
            pil = id_to_image(iid)
            self._set_current(pil, iid)
            self._set_raw_token(token)
            self._update_info(f"TOKEN BETOLTVE  {iid.size[0]}x{iid.size[1]}")
            self.statusBar().showMessage(f"Token betoltve: {path.split('/')[-1].split(chr(92))[-1]}")
        except Exception as e:
            if "ENCRYPTED" in str(e):
                QMessageBox.critical(self, "Titkositott", "Jelszoval vedett fajl.")
            elif "InvalidToken" in type(e).__name__ or "Invalid" in str(e):
                QMessageBox.critical(self, "Hibas jelszo", "Helytelen jelszo.")
            else:
                QMessageBox.critical(self, "Token hiba", str(e))

    def start_ai_generation(self):
        if self.is_generating: return
        if not self.ai_server:
            QMessageBox.critical(self, "No AI", "AI server not available."); return
        prompt = self.txt_prompt.toPlainText().strip()
        if not prompt:
            QMessageBox.information(self, "Empty", "Write a prompt first."); return
        self.is_generating = True
        self.btn_ai_gen.setEnabled(False)
        self.btn_ai_cancel.setVisible(True)
        self.ai_progress.setVisible(True)
        steps = self.spin_steps.value()
        cfg   = self.spin_cfg.value()
        neg   = self.txt_neg.toPlainText().strip()
        self._update_info(f"AI GENERATING  ·  {steps} steps  ·  CFG {cfg:.1f}")
        self.ai_worker = AIWorker(
            self.ai_server, prompt, neg,
            self.w_val, self.h_val, steps=steps, cfg=cfg)
        self.ai_worker.finished.connect(self._ai_done)
        self.ai_worker.error.connect(self._ai_error)
        self.ai_worker.cancelled.connect(self._ai_cancelled)
        self.ai_worker.start()

    def _ai_finish_ui(self):
        self.is_generating = False
        self.btn_ai_gen.setEnabled(True)
        self.btn_ai_cancel.setVisible(False)
        self.btn_ai_cancel.setEnabled(True)
        self.ai_progress.setVisible(False)

    def cancel_ai_generation(self):
        if self.ai_worker and self.is_generating:
            self.ai_worker.cancel()
            self.btn_ai_cancel.setEnabled(False)
            self.statusBar().showMessage("Megszakitas folyamatban...")

    def _ai_done(self, img):
        self.source_pil = img
        self._set_current(img)
        self._ai_finish_ui()
        self._update_info(f"AI GENERATED  ·  {img.width}x{img.height}")
        self.statusBar().showMessage("AI GENERATION COMPLETE")

    def _ai_cancelled(self):
        self._ai_finish_ui()
        self._update_info("AI generajas megszakitva")
        self.statusBar().showMessage("Megszakitva")

    def _ai_error(self, msg: str):
        self._ai_finish_ui()
        QMessageBox.critical(self, "AI Error", msg)

    # ══════════════════════════════════════════════════════
    #  INFO BAR
    # ══════════════════════════════════════════════════════
    def _update_info(self, override: str = ""):
        self._update_hash_display()

        if override:
            self.info_bar.setText(f"  {override}"); return

        if self.current_id:
            iid = self.current_id
            w, h = iid.size
            self.info_bar.setText(
                f"  {w}×{h}  ·  {iid.values_per_segment} vals/seg  ·  "
                f"{PALETTE_NAMES[iid.palette_index]}  ·  "
                f"{len(iid._segments)} segs  ·  ID {len(iid.to_string())} chars")
            self.lbl_id_size.setText(f"{w} × {h}")
            self.lbl_id_segs.setText(str(len(iid._segments)))
            self.lbl_id_vps.setText(str(iid.values_per_segment))
            self.lbl_id_pal.setText(PALETTE_NAMES[iid.palette_index])
            self.lbl_id_chars.setText(str(len(iid.to_string())))
        elif self.current_pil:
            w, h = self.current_pil.size
            self.info_bar.setText(f"  IMAGE  {w}×{h}  ·  (no ID)")
        else:
            self.info_bar.setText("  BABYLON IMAGE ARCHIVE  ·  NO IMAGE")


# ══════════════════════════════════════════════════════════
#  LOADING / SETUP SCREEN
# ══════════════════════════════════════════════════════════
class LoadingScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BABYLON")
        self.setFixedSize(520, 320)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QWidget { background:#0f0b07; color:#c8b89a; font-family:'Courier New',monospace; }
            QLabel  { color:#c8b89a; }
            QProgressBar { border:1px solid #3a2e1e; background:#0d0a06;
                           height:3px; border-radius:0; }
            QProgressBar::chunk { background:#d4a84b; }
        """)
        sg = QApplication.primaryScreen().geometry()
        self.move((sg.width()-self.width())//2, (sg.height()-self.height())//2)
        lay = QVBoxLayout(self); lay.setContentsMargins(50,40,50,40); lay.setSpacing(10)
        t1 = QLabel("B A B Y L O N")
        t1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t1.setFont(QFont("Courier New", 28, QFont.Weight.Bold))
        t1.setStyleSheet("color:#d4a84b; letter-spacing:8px;")
        t2 = QLabel("IMAGE  ARCHIVE")
        t2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t2.setFont(QFont("Courier New", 10))
        t2.setStyleSheet("color:#5c4a28; letter-spacing:4px;")
        lay.addWidget(t1); lay.addWidget(t2); lay.addStretch()
        self.bar = QProgressBar(); self.bar.setRange(0,0)
        self.bar.setTextVisible(False); self.bar.setFixedHeight(3); lay.addWidget(self.bar)
        self.lbl = QLabel("Inicializálás…")
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setStyleSheet("color:#d4a84b; font-size:8pt; letter-spacing:1px;")
        lay.addWidget(self.lbl)
        self.sub = QLabel("")
        self.sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub.setStyleSheet("color:#5c4a28; font-size:7pt;")
        self.sub.setWordWrap(True); lay.addWidget(self.sub)

    def set_status(self, s: str):
        self.lbl.setText(s)
    def set_sub(self, s: str):
        self.sub.setText(s)


# ══════════════════════════════════════════════════════════
#  STARTUP THREAD  (deps + model download + AI load)
# ══════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════
#  STARTUP THREAD  (deps + model download + AI load)
# ══════════════════════════════════════════════════════════
class StartupThread(QThread):
    progress = pyqtSignal(str)
    sub      = pyqtSignal(str)
    finished = pyqtSignal(object)   # emits AIServer or None

    def run(self):
        # 1. Modell letöltés ha szükséges
        if AI_AVAILABLE:
            self.progress.emit("Modell ellenőrzése…")
            if not model_exists():
                self.progress.emit("Modell letöltése HuggingFace-ről…")
                self.sub.emit(f"Repo: Lagyo/ImgenBasic  |  image.safetensors")
                result = ensure_model(lambda msg: self.sub.emit(msg))
                if result is None:
                    self.progress.emit("Modell letöltés sikertelen, AI nélkül indítunk")
                    self.finished.emit(None); return
                self.sub.emit("✓ Modell letöltve")
            else:
                self.sub.emit(f"✓ {MODEL_PATH}")

            # 2. AI szerver betöltése
            self.progress.emit("AI modell betöltése…")
            try:
                srv = AIServer()
                self.progress.emit(f"AI kesz [{srv.device.upper()}]")
                self.finished.emit(srv)
            except Exception as e:
                import traceback
                full_err = traceback.format_exc()
                print("[AI] HIBA a betolteskor:")
                print(full_err)
                err_str = str(e) + full_err
                # VRAM / memória hiba detekció
                is_vram = any(k in err_str for k in (
                    "MemoryError", "paging file", "out of memory",
                    "CUDA out of memory", "1455", "not enough memory",
                ))
                if is_vram:
                    tip = (
                        "Nincs elég VRAM / rendszermemória az AI modell betöltéséhez.\n\n"
                        "Megoldások:\n"
                        "  • Zárj be más programokat (böngésző, játékok)\n"
                        "  • Növeld a virtuális memória méretét (Windows: Vezérlőpult →\n"
                        "    Rendszer → Speciális → Teljesítmény → Lapozófájl)\n"
                        "  • Az SDXL Turbo ~4 GB VRAM-ot igényel GPU-n,\n"
                        "    ~8 GB RAM-ot CPU módban\n"
                        "  • Ha nincs elég erőforrás, az AI generálás nem elérhető"
                    )
                    self.progress.emit("Nincs elég VRAM / RAM az AI betöltéséhez")
                    self.sub.emit("Lásd az egérkurzor súgóját a Generate gombnál.")
                else:
                    tip = f"AI betöltési hiba:\n{str(e)[:300]}"
                    self.progress.emit(f"AI hiba: {str(e)[:80]}")
                    self.sub.emit("Részletes hiba a konzolon látszik.")
                self.finished.emit(("error", tip))
        else:
            self.progress.emit("AI nem elérhető — torch/diffusers hiányzik")
            self.sub.emit("Telepítsd: pip install torch diffusers transformers accelerate")
            self.finished.emit(None)


# ══════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════
class BabylonApp:
    def __init__(self):
        self.app = QApplication(sys.argv); self.app.setStyle("Fusion")
        self.splash = LoadingScreen(); self.splash.show()
        self.thread = StartupThread()
        self.thread.progress.connect(self.splash.set_status)
        self.thread.sub.connect(self.splash.set_sub)
        self.thread.finished.connect(self._on_ready)
        self.thread.start()

    def _on_ready(self, srv):
        self.win = BabylonWindow(ai_server=srv)
        QTimer.singleShot(400, self._show)

    def _show(self): self.splash.close(); self.win.show()
    def run(self): sys.exit(self.app.exec())


if __name__ == "__main__":
    BabylonApp().run()
