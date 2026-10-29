"""SERVİS TAKİP PRO 3.0 — TEK DOSYA SÜRÜM

Projenin tamamı (çekirdek katman + tkinter arayüzü + PyQt5 arayüzü) bu tek
dosyada toplanmıştır. build_tek_dosya.py tarafından üretilir; kaynak proje:
core/ klasörü, app_tk.py ve app_qt.py.

Çalıştırmak için
    python servis_takip_tek_dosya.py          tkinter arayüzü (kurulum gerekmez)
    python servis_takip_tek_dosya.py --qt     PyQt5 arayüzü (pip install pyqt5)
Konsol penceresi istemiyorsan dosyayı .pyw uzantısıyla kaydet.

Veriler bu dosyanın yanındaki data/ klasöründe tutulur:
    data/servis.db      tek veritabanı (tkinter ve PyQt5 sürümleri paylaşır)
    data/urunler.md     ürün listesi, otomatik güncellenir
    data/yedekler/      "Yedek Al" çıktıları
    data/aktarim/       CSV çıktıları

İlk giriş: admin / 1234   ·   personel / 1234   ·   musteri / 1111
(İlk açılışta oluşturulur; şifreleri hemen değiştirin.)

İÇİNDEKİLER
     1. core/ayarlar.py
     2. core/guvenlik.py
     3. core/veritabani.py
     4. core/urunler.py
     5. core/servisler.py
     6. core/goc.py
     7. core/mesajlar.py
     8. core/fis.py
     9. core/aktarim.py
    10. app_tk.py   (tkinter arayüzü)
    11. app_qt.py   (PyQt5 arayüzü)
"""
import csv
import datetime
import hashlib
import hmac
import json
import os
import random
import secrets
import shutil
import sqlite3
import sys
import tempfile
import tkinter as tk
import urllib.parse
import webbrowser
from tkinter import messagebox, ttk

# ==========================================================================
# MODÜL TAKMA ADLARI
# --------------------------------------------------------------------------
# Kaynak dosyalardaki "db.para(...)", "ayar.FIRMA", "srv.servis_ekle(...)"
# gibi çağrıların değişmeden çalışması için bütün takma adlar bu dosyanın
# kendi modülüne bağlanır.
# ==========================================================================
_BU_MODUL = sys.modules[__name__]
ayar = ayarlar = _BU_MODUL
guvenlik = _BU_MODUL
db = veritabani = _BU_MODUL
urn = urunler = _BU_MODUL
srv = servisler = _BU_MODUL
goc = _BU_MODUL
msj = mesajlar = _BU_MODUL
fis = _BU_MODUL
aktarim = _BU_MODUL


# ==========================================================================
# core/ayarlar.py
# ==========================================================================

# --------------------------------------------------------------------------
# FİRMA
# --------------------------------------------------------------------------
FIRMA = "Servis Merkezi"
ALT_BASLIK = "Yetkili Servis ve Satış"
SURUM = "3.0"
FATURA_ONEK = "SRV"

# --------------------------------------------------------------------------
# DOSYA YOLLARI  (uygulamanın yanındaki data/ klasörü)
# --------------------------------------------------------------------------
def _kok_klasor():
    """Program klasörü: normal çalıştırma, tek dosya sürüm ve .exe için."""
    if getattr(sys, "frozen", False):                 # PyInstaller .exe
        return os.path.dirname(os.path.abspath(sys.executable))
    if "__file__" in globals():
        bulundugu = os.path.dirname(os.path.abspath(__file__))
        # core/ayarlar.py ise bir üst klasör, tek dosya sürümde kendi klasörü
        return (os.path.dirname(bulundugu)
                if os.path.basename(bulundugu).lower() == "core" else bulundugu)
    return os.path.dirname(os.path.abspath(sys.argv[0])) or os.getcwd()


KOK = _kok_klasor()
VERI_KLASOR = os.path.join(KOK, "data")
DB_YOL = os.path.join(VERI_KLASOR, "servis.db")
YEDEK_KLASOR = os.path.join(VERI_KLASOR, "yedekler")
URUN_MD = os.path.join(VERI_KLASOR, "urunler.md")

# --------------------------------------------------------------------------
# FİRMA BİLGİLERİ  (data/firma.json — her kuruluma özel)
# --------------------------------------------------------------------------
FIRMA_JSON = os.path.join(VERI_KLASOR, "firma.json")
FIRMA_TELEFON = ""
FIRMA_ADRES = ""

FIRMA_VARSAYILAN = {
    "firma": "Servis Merkezi",
    "alt_baslik": "Yetkili Servis ve Satış",
    "telefon": "",
    "adres": "",
    "fatura_onek": "SRV",
}


def firma_tanimli():
    """İlk kurulum yapılmış mı?"""
    return os.path.exists(FIRMA_JSON)


def firma_yukle():
    """data/firma.json varsa firma bilgilerini oradan alır."""
    global FIRMA, ALT_BASLIK, FIRMA_TELEFON, FIRMA_ADRES, FATURA_ONEK
    bilgi = dict(FIRMA_VARSAYILAN)
    try:
        with open(FIRMA_JSON, encoding="utf-8") as f:
            okunan = json.load(f)
        if isinstance(okunan, dict):
            bilgi.update({a: str(d) for a, d in okunan.items() if d is not None})
    except (OSError, ValueError):
        pass
    FIRMA = bilgi["firma"].strip() or FIRMA_VARSAYILAN["firma"]
    ALT_BASLIK = bilgi["alt_baslik"].strip()
    FIRMA_TELEFON = bilgi["telefon"].strip()
    FIRMA_ADRES = bilgi["adres"].strip()
    FATURA_ONEK = (bilgi["fatura_onek"].strip().upper()
                   or FIRMA_VARSAYILAN["fatura_onek"])
    return bilgi


def firma_kaydet(firma, alt_baslik="", telefon="", adres="", fatura_onek=""):
    """İlk kurulum penceresinden gelen bilgileri yazar."""
    os.makedirs(VERI_KLASOR, exist_ok=True)
    with open(FIRMA_JSON, "w", encoding="utf-8") as f:
        json.dump({"firma": firma.strip(), "alt_baslik": alt_baslik.strip(),
                   "telefon": telefon.strip(), "adres": adres.strip(),
                   "fatura_onek": fatura_onek.strip().upper()},
                  f, ensure_ascii=False, indent=2)
    return firma_yukle()

# Eski sürümlerden devralınacak dosyalar (varsa bir kereliğine aktarılır)
ESKI_DOSYALAR = {
    "kayitlar_json": os.path.join(KOK, "kayitlar.json"),
    "kullanicilar_json": os.path.join(KOK, "kullanicilar.json"),
    "eski_db": os.path.join(KOK, "servis.db"),
    "eski_urun_md": os.path.join(KOK, "urunler.md"),
    "fatura_sayac": os.path.join(KOK, "fatura_sayac.txt"),
}

# --------------------------------------------------------------------------
# ROLLER
# --------------------------------------------------------------------------
ROL_YONETICI = "yonetici"
ROL_PERSONEL = "personel"
ROL_MUSTERI = "musteri"
ROLLER = [ROL_YONETICI, ROL_PERSONEL, ROL_MUSTERI]
ROL_ADI = {
    ROL_YONETICI: "Yönetici",
    ROL_PERSONEL: "Personel",
    ROL_MUSTERI: "Müşteri",
}
# Eski sürümlerdeki rol isimleri
ROL_ESKI = {"admin": ROL_YONETICI, "yonetici": ROL_YONETICI,
            "teknisyen": ROL_PERSONEL, "personel": ROL_PERSONEL,
            "musteri": ROL_MUSTERI, "": ROL_PERSONEL}

# Yetkiler: hangi rol hangi işi yapabilir
YETKI = {
    "servis_gor_hepsi": (ROL_YONETICI, ROL_PERSONEL),
    "servis_ekle": (ROL_YONETICI, ROL_PERSONEL),
    "servis_duzenle": (ROL_YONETICI, ROL_PERSONEL),
    "servis_sil": (ROL_YONETICI,),
    "urun_yonet": (ROL_YONETICI, ROL_PERSONEL),
    "fiyat_gor": (ROL_YONETICI, ROL_PERSONEL),
    "gelis_fiyat_gor": (ROL_YONETICI,),
    "fatura_kes": (ROL_YONETICI, ROL_PERSONEL),
    "fatura_revize": (ROL_YONETICI,),
    "masraf_onayla": (ROL_MUSTERI,),
    "rapor_gor": (ROL_YONETICI,),
    "kullanici_yonet": (ROL_YONETICI,),
    "veri_aktar": (ROL_YONETICI,),
    "yedek_al": (ROL_YONETICI,),
    "siparis": (ROL_YONETICI, ROL_PERSONEL),
}

MAX_DENEME = 5          # 0 veya negatif verilirse sınır kalkar

# --------------------------------------------------------------------------
# MARKA / ÜRÜN KATALOĞU
# --------------------------------------------------------------------------
YETKILI_MARKALAR = ["Karaca", "Korkmaz", "Shark Ninja"]
MARKALAR = YETKILI_MARKALAR + ["Cook Plus", "Emsan", "King", "Jumbo",
                               "Diğer marka"]
# Bu markalarda parça değişiminde tüm parçaların bulunması şart
PARCA_GEREKEN = ["Shark Ninja", "Ninja", "Shark"]

MODELLER = {
    "Karaca": [
        "Çay Makinesi", "Semaver", "Su Isıtıcı (Kettle)",
        "Filtre Kahve Makinesi", "Türk Kahvesi Makinesi", "Espresso Makinesi",
        "Blender Seti", "El Blenderi", "Mikser", "Doğrayıcı",
        "Mutfak Robotu", "Katı Meyve Sıkacağı", "Narenciye Sıkacağı",
        "Tost Makinesi", "Izgara ve Tost Makinesi", "Ekmek Kızartma Makinesi",
        "Air Fryer (Yağsız Fritöz)", "Fritöz", "Waffle Makinesi",
        "Ütü", "Buharlı Ütü", "Buhar Kazanlı Ütü", "Dikey Buharlı Ütü",
        "Elektrikli Süpürge", "Şarjlı Dikey Süpürge", "Robot Süpürge",
        "Elektrikli Pişirici", "Yumurta Pişirici", "Sıcak Çikolata Makinesi",
        "Saç Kurutma Makinesi", "Saç Düzleştirici",
    ],
    "Korkmaz": [
        "Çay Makinesi", "Semaver", "Su Isıtıcı (Kettle)",
        "Filtre Kahve Makinesi", "Türk Kahvesi Makinesi",
        "Blender Seti", "El Blenderi", "Mikser", "Doğrayıcı",
        "Mutfak Robotu", "Katı Meyve Sıkacağı", "Narenciye Sıkacağı",
        "Tost Makinesi", "Izgara ve Tost Makinesi", "Ekmek Kızartma Makinesi",
        "Air Fryer (Yağsız Fritöz)", "Fritöz", "Waffle Makinesi",
        "Ütü", "Buharlı Ütü", "Buhar Kazanlı Ütü",
        "Elektrikli Süpürge", "Şarjlı Dikey Süpürge",
        "Elektrikli Düdüklü Tencere", "Çok Amaçlı Pişirici",
        "Elektrikli Izgara", "Kıyma Makinesi", "Yoğurt Yapma Makinesi",
    ],
    "Shark Ninja": [
        "Air Fryer (Yağsız Fritöz)", "Çift Hazneli Air Fryer",
        "Çok Amaçlı Pişirici", "Blender", "Kişisel Blender",
        "Mutfak Robotu", "Buz Kırıcı / Dondurma Makinesi",
        "Kahve Makinesi", "Şarjlı Dikey Süpürge", "Elektrikli Süpürge",
        "Robot Süpürge", "Buharlı Temizleyici", "Buharlı Mop",
    ],
}
_GENEL_MODELLER = [
    "Çay Makinesi", "Su Isıtıcı (Kettle)", "Kahve Makinesi", "Blender",
    "Mikser", "Doğrayıcı", "Mutfak Robotu", "Meyve Sıkacağı",
    "Tost Makinesi", "Ekmek Kızartma Makinesi", "Air Fryer (Yağsız Fritöz)",
    "Fritöz", "Ütü", "Buhar Kazanlı Ütü", "Elektrikli Süpürge",
    "Robot Süpürge", "Elektrikli Pişirici", "Diğer / Listede yok",
]
for _m in MARKALAR:
    MODELLER.setdefault(_m, list(_GENEL_MODELLER))


def modeller(marka):
    return MODELLER.get(marka, _GENEL_MODELLER)


# --------------------------------------------------------------------------
# SERVİS AKIŞI
# --------------------------------------------------------------------------
DURUMLAR = [
    "Kayıt Alındı",
    "İnceleniyor",
    "Parça Bekleniyor",
    "Tamir Ediliyor",
    "Test Ediliyor",
    "Teslime Hazır",
    "Teslim Edildi",
]
DURUM_RENK = {
    "Kayıt Alındı": "#6b7785",
    "İnceleniyor": "#b9770e",
    "Parça Bekleniyor": "#c0392b",
    "Tamir Ediliyor": "#1f618d",
    "Test Ediliyor": "#6c3483",
    "Teslime Hazır": "#1e8449",
    "Teslim Edildi": "#4a4a4a",
}

GARANTI_SECENEKLERI = ["Garanti kapsamında", "Garanti süresi doldu",
                       "Garanti dışı (kullanıcı hatası)", "Bilinmiyor"]
FATURA_SECENEKLERI = ["Fatura var", "Fatura yok"]
ONAY_SECENEKLERI = ["Bekliyor", "Onaylandı", "Reddedildi"]
FATURA_DURUMLARI = ["Bekliyor", "Ödendi", "İptal"]

TESLIM_GUN = 15         # kayıttan kaç gün sonra teslim alınmalı
HATIRLATMA_GUN = 15     # teslim tarihi geçince kaç gün sonra mesaj atılır
KDV_ORANI = 0.20

# --------------------------------------------------------------------------
# RENK PALETİ  (koyu tema - NETBANK PRO temasından)
# --------------------------------------------------------------------------
BG = "#0e1726"
PANEL = "#16213a"
PANEL2 = "#1b2748"
LINE = "#2a3654"
INK = "#e6edf7"
MUTED = "#8aa0be"
ACCENT = "#00b4a6"
ACCENT2 = "#1e88e5"
OK = "#3ddc84"
NO = "#ff5470"
WAIT = "#ffb84d"
WARN = "#ff6b4a"
WA = "#25d366"
LACIVERT = "#0b2545"

# ==========================================================================
# core/guvenlik.py
# ==========================================================================

TUR = 200_000


def yeni_tuz() -> str:
    return secrets.token_hex(16)


def _pbkdf2(sifre: str, tuz: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", sifre.encode("utf-8"), bytes.fromhex(tuz), TUR).hex()


def hashle(sifre: str, tuz: str = None) -> tuple:
    """(hash, tuz) döndürür. Tuz verilmezse yenisi üretilir."""
    tuz = tuz or yeni_tuz()
    return _pbkdf2(sifre, tuz), tuz


def _sha256(sifre: str, tuz: str = "") -> str:
    return hashlib.sha256((tuz + sifre).encode("utf-8")).hexdigest()


def dogrula(sifre: str, kayitli_hash: str, tuz: str = "") -> bool:
    """Şifreyi kayıtlı hash ile karşılaştırır (timing-safe).

    Üç format desteklenir:
      * PBKDF2 (bu sürüm)            -> 64 hane hash + 32 hane tuz
      * salt'lı SHA-256 (v2 sürümü)  -> sha256(tuz + sifre)
      * düz SHA-256 (ilk sürüm)      -> sha256(sifre)
    """
    if not kayitli_hash:
        return False
    tuz = tuz or ""
    try:
        if tuz and len(tuz) == 32:
            if hmac.compare_digest(_pbkdf2(sifre, tuz), kayitli_hash):
                return True
        if tuz and hmac.compare_digest(_sha256(sifre, tuz), kayitli_hash):
            return True
        return hmac.compare_digest(_sha256(sifre), kayitli_hash)
    except (ValueError, TypeError):
        return False


def eski_format_mi(kayitli_hash: str, tuz: str) -> bool:
    """Kayıt PBKDF2 dışında bir formatta mı tutuluyor?"""
    return not (tuz and len(tuz) == 32 and len(kayitli_hash or "") == 64)


def onay_kodu(uzunluk: int = 6) -> str:
    """Müşterinin servis kaydını doğrulaması için tek kullanımlık kod."""
    return "".join(secrets.choice("0123456789") for _ in range(uzunluk))


def gecici_sifre(uzunluk: int = 6) -> str:
    havuz = "ABCDEFGHJKLMNPRSTUVYZ23456789"
    return "".join(secrets.choice(havuz) for _ in range(uzunluk))


# NETBANK PRO uyumluluğu: 'tuz$hash' tek alan formatı
def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    return f"{salt}${_pbkdf2(password, salt)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        tuz, h = stored.split("$", 1)
        return hmac.compare_digest(_pbkdf2(password, tuz), h)
    except (ValueError, AttributeError):
        return False

# ==========================================================================
# core/veritabani.py
# ==========================================================================

# --------------------------------------------------------------------------
# ŞEMA
# --------------------------------------------------------------------------
SEMA = """
CREATE TABLE IF NOT EXISTS kullanicilar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kullanici_adi TEXT UNIQUE NOT NULL,
    ad_soyad      TEXT NOT NULL,
    telefon       TEXT DEFAULT '',
    eposta        TEXT DEFAULT '',
    rol           TEXT NOT NULL DEFAULT 'personel',
    sifre         TEXT NOT NULL,
    tuz           TEXT DEFAULT '',
    aktif         INTEGER NOT NULL DEFAULT 1,
    olusturma     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS musteriler (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_soyad     TEXT NOT NULL,
    telefon      TEXT DEFAULT '',
    adres        TEXT DEFAULT '',
    eposta       TEXT DEFAULT '',
    kullanici_id INTEGER REFERENCES kullanicilar(id),
    olusturma    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS urunler (
    kod            TEXT PRIMARY KEY,
    ad             TEXT NOT NULL,
    kategori       TEXT DEFAULT 'Yedek Parça',
    stok           INTEGER NOT NULL DEFAULT 0,
    kritik_stok    INTEGER NOT NULL DEFAULT 5,
    gelis_fiyat    INTEGER NOT NULL DEFAULT 0,
    satis_fiyat    INTEGER NOT NULL DEFAULT 0,
    garanti_suresi TEXT DEFAULT '2 yıl üretici garantisi',
    guncelleme     TEXT
);

CREATE TABLE IF NOT EXISTS servisler (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    kod               TEXT UNIQUE NOT NULL,
    musteri_id        INTEGER NOT NULL REFERENCES musteriler(id),
    marka             TEXT NOT NULL DEFAULT 'Diğer marka',
    urun              TEXT NOT NULL DEFAULT '',
    model             TEXT DEFAULT '',
    seri_no           TEXT DEFAULT '',
    ariza             TEXT DEFAULT '',
    cozum             TEXT DEFAULT '',
    durum             TEXT NOT NULL DEFAULT 'Kayıt Alındı',
    garanti           TEXT NOT NULL DEFAULT 'Bilinmiyor',
    fatura_durumu     TEXT NOT NULL DEFAULT 'Fatura yok',
    kayit_onay        TEXT NOT NULL DEFAULT 'Bekliyor',
    masraf_onay       TEXT NOT NULL DEFAULT 'Bekliyor',
    masraf_tutar      INTEGER NOT NULL DEFAULT 0,
    iscilik           INTEGER NOT NULL DEFAULT 0,
    onay_kodu         TEXT DEFAULT '',
    not_servis        TEXT DEFAULT '',
    giris_tarihi      TEXT NOT NULL,
    teslim_tarihi     TEXT,
    cikis_tarihi      TEXT,
    hatirlatma_tarihi TEXT,
    hatirlatma_sayisi INTEGER NOT NULL DEFAULT 0,
    arsiv             INTEGER NOT NULL DEFAULT 0,
    olusturan_id      INTEGER,
    guncelleme        TEXT
);

CREATE TABLE IF NOT EXISTS servis_parcalari (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    servis_id   INTEGER NOT NULL REFERENCES servisler(id) ON DELETE CASCADE,
    urun_kod    TEXT NOT NULL,
    ad          TEXT DEFAULT '',
    adet        INTEGER NOT NULL DEFAULT 1,
    birim_fiyat INTEGER NOT NULL DEFAULT 0,
    tarih       TEXT
);

CREATE TABLE IF NOT EXISTS faturalar (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_no    TEXT UNIQUE NOT NULL,
    servis_id    INTEGER REFERENCES servisler(id),
    ara_toplam   INTEGER NOT NULL DEFAULT 0,
    kdv          INTEGER NOT NULL DEFAULT 0,
    toplam       INTEGER NOT NULL DEFAULT 0,
    durum        TEXT NOT NULL DEFAULT 'Bekliyor',
    revizyon     INTEGER NOT NULL DEFAULT 0,
    aciklama     TEXT DEFAULT '',
    tarih        TEXT NOT NULL,
    olusturan_id INTEGER
);

CREATE TABLE IF NOT EXISTS siparisler (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    fatura_no    TEXT,
    musteri_id   INTEGER REFERENCES musteriler(id),
    musteri_adi  TEXT DEFAULT '',
    telefon      TEXT DEFAULT '',
    toplam       INTEGER NOT NULL DEFAULT 0,
    tarih        TEXT NOT NULL,
    olusturan_id INTEGER
);

CREATE TABLE IF NOT EXISTS siparis_satirlari (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    siparis_id  INTEGER NOT NULL REFERENCES siparisler(id) ON DELETE CASCADE,
    urun_kod    TEXT DEFAULT '',
    ad          TEXT NOT NULL,
    adet        INTEGER NOT NULL DEFAULT 1,
    birim_fiyat INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS loglar (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kullanici_id INTEGER,
    eylem        TEXT NOT NULL,
    detay        TEXT DEFAULT '',
    tarih        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ayarlar (
    anahtar TEXT PRIMARY KEY,
    deger   TEXT
);

CREATE INDEX IF NOT EXISTS ix_servis_durum   ON servisler(durum);
CREATE INDEX IF NOT EXISTS ix_servis_musteri ON servisler(musteri_id);
CREATE INDEX IF NOT EXISTS ix_parca_servis   ON servis_parcalari(servis_id);
"""


# --------------------------------------------------------------------------
# BAĞLANTI
# --------------------------------------------------------------------------
def baglan():
    os.makedirs(ayar.VERI_KLASOR, exist_ok=True)
    con = sqlite3.connect(ayar.DB_YOL, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def sorgu(sql, deger=()):
    con = baglan()
    try:
        return [dict(r) for r in con.execute(sql, deger).fetchall()]
    finally:
        con.close()


def tek(sql, deger=()):
    con = baglan()
    try:
        r = con.execute(sql, deger).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def calistir(sql, deger=()):
    con = baglan()
    try:
        imlec = con.execute(sql, deger)
        con.commit()
        return imlec.lastrowid
    finally:
        con.close()


# --------------------------------------------------------------------------
# PARA / TARİH YARDIMCILARI
# --------------------------------------------------------------------------
def sayi(metin, varsayilan=0.0):
    """'1.900,50' ve '1900.50' yazımlarını da anlar."""
    m = str(metin if metin is not None else "").strip()
    m = "".join(ch for ch in m if ch.isdigit() or ch in ".,-")
    if not m:
        return varsayilan
    if "." in m and "," in m:
        if m.rfind(",") > m.rfind("."):
            m = m.replace(".", "").replace(",", ".")
        else:
            m = m.replace(",", "")
    elif "," in m:
        m = m.replace(",", ".", 1) if m.count(",") == 1 else m.replace(",", "")
    elif m.count(".") > 1:
        m = m.replace(".", "")              # 1.900.000 -> binlik ayraç
    elif m.count(".") == 1 and len(m.split(".")[1]) == 3:
        m = m.replace(".", "")              # 2.500 -> TR binlik ayraç (2500)
    try:
        return float(m)
    except ValueError:
        return varsayilan


def kurus(metin) -> int:
    """Serbest metin/sayıyı kuruş integer'a çevirir."""
    if isinstance(metin, int):
        return metin
    return int(round(sayi(metin) * 100))


def para(kurus_int, simge=True) -> str:
    """1234567 -> '12.345,67 ₺'"""
    try:
        kurus_int = int(kurus_int or 0)
    except (TypeError, ValueError):
        kurus_int = 0
    s = f"{kurus_int / 100:,.2f}".replace(",", "X").replace(".", ",")
    s = s.replace("X", ".")
    return f"{s} ₺" if simge else s


def simdi() -> str:
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


def bugun() -> str:
    return datetime.date.today().isoformat()


def iso_simdi() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def gun_ekle(tarih_iso: str, gun: int) -> str:
    try:
        t = datetime.date.fromisoformat(str(tarih_iso)[:10])
    except ValueError:
        t = datetime.date.today()
    return (t + datetime.timedelta(days=gun)).isoformat()


def gun_farki(tarih_iso: str):
    """Bugünden kaç gün önce/sonra olduğunu döndürür (None = çözülemedi)."""
    try:
        t = datetime.date.fromisoformat(str(tarih_iso)[:10])
    except (ValueError, TypeError):
        return None
    return (datetime.date.today() - t).days


def tel_temizle(t) -> str:
    """Sadece rakamları alır, 90XXXXXXXXXX formatına çevirir; geçersizse ''."""
    r = "".join(ch for ch in str(t or "") if ch.isdigit())
    if not r:
        return ""
    if r.startswith("0090"):
        r = r[4:]
    if r.startswith("90") and len(r) == 12:
        return r
    if r.startswith("0"):
        r = r[1:]
    if len(r) != 10:
        return ""
    return "90" + r


# --------------------------------------------------------------------------
# KOD ÜRETİCİLER
# --------------------------------------------------------------------------
def servis_kodu_uret(con=None) -> str:
    """Yıl-ay önekli servis kodu: 2609-4471"""
    kapat = con is None
    con = con or baglan()
    try:
        onek = datetime.datetime.now().strftime("%y%m")
        for _ in range(500):
            k = f"{onek}-{random.randint(1000, 9999)}"
            if not con.execute("SELECT 1 FROM servisler WHERE kod=?",
                               (k,)).fetchone():
                return k
        i = 1
        while True:
            k = f"{onek}-{i:04d}"
            if not con.execute("SELECT 1 FROM servisler WHERE kod=?",
                               (k,)).fetchone():
                return k
            i += 1
    finally:
        if kapat:
            con.close()


def urun_kodu_uret() -> str:
    onek = datetime.datetime.now().strftime("%Y%m%d%H%M")
    mevcut = {u["kod"] for u in sorgu("SELECT kod FROM urunler")}
    i = 0
    while f"{onek}{i}" in mevcut:
        i += 1
    return f"{onek}{i}"


def ayar_oku(anahtar, varsayilan=""):
    r = tek("SELECT deger FROM ayarlar WHERE anahtar=?", (anahtar,))
    return r["deger"] if r else varsayilan


def ayar_yaz(anahtar, deger):
    calistir("INSERT INTO ayarlar (anahtar,deger) VALUES (?,?) "
             "ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
             (anahtar, str(deger)))


def fatura_no_uret() -> str:
    """Sıralı fatura numarası: KT-2026-00001 (sayaç veritabanında)."""
    con = baglan()
    try:
        con.execute("BEGIN IMMEDIATE")
        r = con.execute("SELECT deger FROM ayarlar WHERE anahtar='fatura_sayac'"
                        ).fetchone()
        son = int(r["deger"]) if r and str(r["deger"]).isdigit() else 0
        yeni = son + 1
        con.execute("INSERT INTO ayarlar (anahtar,deger) VALUES ('fatura_sayac',?) "
                    "ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger",
                    (str(yeni),))
        con.commit()
        return f"{ayar.FATURA_ONEK}-{datetime.datetime.now().year}-{yeni:05d}"
    finally:
        con.close()


def log(kullanici_id, eylem, detay=""):
    try:
        calistir("INSERT INTO loglar (kullanici_id,eylem,detay,tarih) "
                 "VALUES (?,?,?,?)", (kullanici_id, eylem, str(detay),
                                      iso_simdi()))
    except sqlite3.Error:
        pass


# --------------------------------------------------------------------------
# KURULUM
# --------------------------------------------------------------------------
def _eksik_kolonlari_tamamla(con):
    """Eski servis.db dosyalarına yeni kolonları veri kaybetmeden ekler."""
    beklenen = {
        "servisler": {
            "model": "TEXT DEFAULT ''", "seri_no": "TEXT DEFAULT ''",
            "cozum": "TEXT DEFAULT ''", "garanti": "TEXT DEFAULT 'Bilinmiyor'",
            "fatura_durumu": "TEXT DEFAULT 'Fatura yok'",
            "kayit_onay": "TEXT DEFAULT 'Bekliyor'",
            "masraf_onay": "TEXT DEFAULT 'Bekliyor'",
            "masraf_tutar": "INTEGER DEFAULT 0", "iscilik": "INTEGER DEFAULT 0",
            "onay_kodu": "TEXT DEFAULT ''", "not_servis": "TEXT DEFAULT ''",
            "teslim_tarihi": "TEXT", "cikis_tarihi": "TEXT",
            "hatirlatma_tarihi": "TEXT",
            "hatirlatma_sayisi": "INTEGER DEFAULT 0",
            "arsiv": "INTEGER DEFAULT 0", "olusturan_id": "INTEGER",
            "guncelleme": "TEXT",
        },
        "kullanicilar": {"tuz": "TEXT DEFAULT ''", "telefon": "TEXT DEFAULT ''",
                         "eposta": "TEXT DEFAULT ''"},
        "urunler": {"kategori": "TEXT DEFAULT 'Yedek Parça'",
                    "kritik_stok": "INTEGER DEFAULT 5",
                    "guncelleme": "TEXT"},
    }
    for tablo, kolonlar in beklenen.items():
        try:
            mevcut = {s["name"] for s in
                      con.execute(f"PRAGMA table_info({tablo})").fetchall()}
        except sqlite3.Error:
            continue
        if not mevcut:
            continue
        for ad, tanim in kolonlar.items():
            if ad not in mevcut:
                try:
                    con.execute(f"ALTER TABLE {tablo} ADD COLUMN {ad} {tanim}")
                except sqlite3.Error:
                    pass
    con.commit()


def kur(ornek_veri=True):
    """Tabloları oluşturur, eksikleri tamamlar, ilk kullanıcıları ekler."""
    os.makedirs(ayar.VERI_KLASOR, exist_ok=True)
    con = baglan()
    try:
        con.executescript(SEMA)
        con.commit()
        _eksik_kolonlari_tamamla(con)
        _varsayilan_kullanicilar(con)
    finally:
        con.close()
    goc_tumunu_aktar()
    urunler.md_hazirla()
    if ornek_veri:
        _ornek_veri()


def _varsayilan_kullanicilar(con):
    if con.execute("SELECT COUNT(*) c FROM kullanicilar").fetchone()["c"]:
        return
    demo = [
        ("admin", "Sistem Yöneticisi", ayar.ROL_YONETICI, "1234"),
        ("personel", "Servis Personeli", ayar.ROL_PERSONEL, "1234"),
        ("musteri", "Örnek Müşteri", ayar.ROL_MUSTERI, "1111"),
    ]
    for kadi, ad, rol, sifre in demo:
        h, t = guvenlik.hashle(sifre)
        con.execute("INSERT INTO kullanicilar "
                    "(kullanici_adi,ad_soyad,rol,sifre,tuz,olusturma) "
                    "VALUES (?,?,?,?,?,?)", (kadi, ad, rol, h, t, iso_simdi()))
    con.commit()


def _ornek_veri():
    """Veritabanı bomboşsa tanıtım amaçlı örnek kayıtlar ekler."""
    if sorgu("SELECT 1 FROM musteriler LIMIT 1"):
        return
    kul = tek("SELECT id FROM kullanicilar WHERE kullanici_adi='musteri'")
    admin = tek("SELECT id FROM kullanicilar WHERE kullanici_adi='admin'")
    m1 = srv.musteri_ekle("Ahmet Yılmaz", "0532 111 22 33",
                          "Akyazı / Sakarya", kullanici_id=kul["id"] if kul else None)
    m2 = srv.musteri_ekle("Zeynep Kaya", "0505 444 55 66", "Adapazarı / Sakarya")
    m3 = srv.musteri_ekle("Mehmet Demir", "0542 777 88 99", "Hendek / Sakarya")

    for kod, ad, stok, kritik, gelis, satis in [
        ("PRC-001", "Rezistans 1800W", 14, 5, "330,00", "420,00"),
        ("PRC-002", "Termostat", 3, 5, "140,00", "185,00"),
        ("PRC-003", "Motor Kömürü (çift)", 22, 8, "60,00", "95,00"),
        ("PRC-004", "Cam Demlik", 7, 4, "195,00", "260,00"),
        ("PRC-005", "Güç Kablosu", 1, 6, "95,00", "140,00"),
        ("PRC-006", "Bıçak Ünitesi", 11, 5, "225,00", "310,00"),
    ]:
        srv.urun_ekle(kod, ad, stok, kritik, gelis, satis, kategori="Yedek Parça")

    admin_id = admin["id"] if admin else None
    s1 = srv.servis_ekle(m1, "Karaca", "Çay Makinesi", "Hatır Mono",
                         "KRC-2024-1187", "Su ısıtmıyor, rezistans devrede değil",
                         garanti="Garanti kapsamında", fatura_durumu="Fatura var",
                         iscilik="350,00", olusturan_id=admin_id)
    s2 = srv.servis_ekle(m2, "Korkmaz", "El Blenderi", "A365 Robomax",
                         "KKM-2023-9042", "Motor çalışırken yüksek ses",
                         garanti="Garanti süresi doldu", iscilik="300,00",
                         olusturan_id=admin_id)
    s3 = srv.servis_ekle(m3, "Shark Ninja", "Air Fryer (Yağsız Fritöz)",
                         "Foodi Dual", "SNJ-2025-7788", "Isıtmıyor, fan sesi var",
                         iscilik="150,00", olusturan_id=admin_id)
    srv.durum_guncelle(s1, "Tamir Ediliyor", admin_id)
    srv.durum_guncelle(s2, "Parça Bekleniyor", admin_id)
    srv.parca_ekle(s1, "PRC-001", 1, admin_id)
    srv.parca_ekle(s3, "PRC-004", 1, admin_id)
    srv.durum_guncelle(s3, "Teslime Hazır", admin_id)
    srv.fatura_kes(s3, "Teslime hazır ürün faturası", admin_id)


# --------------------------------------------------------------------------
# YEDEKLEME
# --------------------------------------------------------------------------
def yedek_al() -> str:
    os.makedirs(ayar.YEDEK_KLASOR, exist_ok=True)
    damga = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    hedef = os.path.join(ayar.YEDEK_KLASOR, f"servis_{damga}.db")
    con = baglan()
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        con.close()
    shutil.copy2(ayar.DB_YOL, hedef)
    return hedef

# ==========================================================================
# core/urunler.py
# ==========================================================================

BASLIK = "# Ürünler"
ALANLAR = ["Ürün Kodu", "Ürün Adı", "Stok Adedi", "Geliş Fiyatı",
           "Satış Fiyatı", "Garanti Süresi"]

# urunler.md hiç yoksa ilk oluşturmada kullanılacak örnek katalog
KATALOG = [
    ("Tencere Seti", 450.0), ("Tava 24cm", 320.0),
    ("Çaydanlık", 189.90), ("Bıçak Seti", 275.0),
]


# --------------------------------------------------------------------------
# MD DOSYASI
# --------------------------------------------------------------------------
def md_yukle(yol=None):
    """urunler.md tablosunu dict listesine çevirir."""
    yol = yol or ayar.URUN_MD
    if not os.path.exists(yol):
        return []
    satirlar = []
    with open(yol, "r", encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if not satir.startswith("|"):
                continue
            hucreler = [h.strip() for h in satir.strip("|").split("|")]
            if len(hucreler) != len(ALANLAR):
                continue
            if hucreler == ALANLAR:
                continue
            if all(set(h) <= set("-: ") for h in hucreler):
                continue
            satirlar.append(dict(zip(ALANLAR, hucreler)))
    return satirlar


def md_yaz(urun_listesi=None):
    """Veritabanındaki ürünleri md tablosu olarak yazar."""
    kayitlar = urun_listesi if urun_listesi is not None else listele()
    satirlar = [BASLIK, "",
                "| " + " | ".join(ALANLAR) + " |",
                "|" + "|".join("---" for _ in ALANLAR) + "|"]
    for u in kayitlar:
        hucre = [
            str(u["kod"]),
            str(u["ad"]).replace("|", "/"),
            str(u["stok"]),
            db.para(u["gelis_fiyat"], simge=False),
            db.para(u["satis_fiyat"], simge=False),
            str(u.get("garanti_suresi") or "").replace("|", "/"),
        ]
        satirlar.append("| " + " | ".join(hucre) + " |")
    os.makedirs(os.path.dirname(ayar.URUN_MD), exist_ok=True)
    with open(ayar.URUN_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar) + "\n")
    return ayar.URUN_MD


def md_ice_aktar(yol=None):
    """md dosyasındaki satırları veritabanına işler (kod = anahtar)."""
    sayac = 0
    for s in md_yukle(yol):
        kod = s["Ürün Kodu"].strip()
        if not kod:
            continue
        varsa = db.tek("SELECT kod FROM urunler WHERE kod=?", (kod,))
        deger = (s["Ürün Adı"], int(db.sayi(s["Stok Adedi"])),
                 db.kurus(s["Geliş Fiyatı"]), db.kurus(s["Satış Fiyatı"]),
                 s["Garanti Süresi"], db.iso_simdi(), kod)
        if varsa:
            db.calistir("UPDATE urunler SET ad=?,stok=?,gelis_fiyat=?,"
                        "satis_fiyat=?,garanti_suresi=?,guncelleme=? WHERE kod=?",
                        deger)
        else:
            db.calistir("INSERT INTO urunler (ad,stok,gelis_fiyat,satis_fiyat,"
                        "garanti_suresi,guncelleme,kod) VALUES (?,?,?,?,?,?,?)",
                        deger)
        sayac += 1
    return sayac


def md_hazirla():
    """İlk çalıştırmada ürün tablosunu ve md dosyasını hazırlar."""
    os.makedirs(ayar.VERI_KLASOR, exist_ok=True)
    # eski sürümün yanındaki urunler.md varsa data/ altına taşı
    eski = ayar.ESKI_DOSYALAR["eski_urun_md"]
    if not os.path.exists(ayar.URUN_MD) and os.path.exists(eski):
        try:
            os.replace(eski, ayar.URUN_MD)
        except OSError:
            pass
    if os.path.exists(ayar.URUN_MD):
        md_ice_aktar()
    if not db.tek("SELECT 1 FROM urunler LIMIT 1"):
        for i, (ad, fiyat) in enumerate(KATALOG):
            db.calistir(
                "INSERT OR IGNORE INTO urunler (kod,ad,kategori,stok,kritik_stok,"
                "gelis_fiyat,satis_fiyat,garanti_suresi,guncelleme) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (db.urun_kodu_uret() + str(i), ad, "Satış Ürünü", 0, 3,
                 int(fiyat * 80), int(fiyat * 100),
                 "2 yıl üretici garantisi", db.iso_simdi()))
    md_yaz()


# --------------------------------------------------------------------------
# SORGU / GÜNCELLEME
# --------------------------------------------------------------------------
def listele(arama="", sadece_kritik=False):
    sql = "SELECT * FROM urunler"
    kosul, deger = [], []
    if arama:
        kosul.append("(kod LIKE ? OR ad LIKE ?)")
        deger += [f"%{arama}%", f"%{arama}%"]
    if sadece_kritik:
        kosul.append("stok <= kritik_stok")
    if kosul:
        sql += " WHERE " + " AND ".join(kosul)
    sql += " ORDER BY ad COLLATE NOCASE"
    return db.sorgu(sql, tuple(deger))


def bul(kod):
    return db.tek("SELECT * FROM urunler WHERE kod=?", (str(kod).strip(),))


def kritik_stoklar():
    return db.sorgu("SELECT * FROM urunler WHERE stok <= kritik_stok "
                    "ORDER BY stok ASC")


def stok_degistir(kod, fark, kullanici_id=None, sebep=""):
    """Stoğu artırır/azaltır. Negatife düşürmez. Yeni stoğu döndürür."""
    u = bul(kod)
    if not u:
        return None
    yeni = max(0, int(u["stok"]) + int(fark))
    db.calistir("UPDATE urunler SET stok=?, guncelleme=? WHERE kod=?",
                (yeni, db.iso_simdi(), u["kod"]))
    db.log(kullanici_id, "stok", f"{u['kod']} {fark:+d} -> {yeni} {sebep}".strip())
    md_yaz()
    return yeni


def stok_dus(kod, adet=1, kullanici_id=None, sebep=""):
    return stok_degistir(kod, -abs(int(adet)), kullanici_id, sebep)


def stok_ata(kod, yeni_stok, kullanici_id=None):
    u = bul(kod)
    if not u:
        return None
    yeni = max(0, int(yeni_stok))
    db.calistir("UPDATE urunler SET stok=?, guncelleme=? WHERE kod=?",
                (yeni, db.iso_simdi(), u["kod"]))
    db.log(kullanici_id, "stok_ata", f"{u['kod']} = {yeni}")
    md_yaz()
    return yeni


def kar_marji(u):
    """Ürünün kâr marjını yüzde olarak döndürür."""
    gelis = int(u.get("gelis_fiyat") or 0)
    satis = int(u.get("satis_fiyat") or 0)
    if not gelis:
        return 0.0
    return (satis - gelis) / gelis * 100

# ==========================================================================
# core/servisler.py
# ==========================================================================

class ServisHata(Exception):
    """Kullanıcıya gösterilebilir iş kuralı hatası."""


# ==========================================================================
# KİMLİK / KULLANICI
# ==========================================================================
def giris(kullanici_adi, sifre):
    kullanici_adi = (kullanici_adi or "").strip()
    if not kullanici_adi or not sifre:
        raise ServisHata("Kullanıcı adı ve şifre zorunludur.")
    k = db.tek("SELECT * FROM kullanicilar WHERE kullanici_adi=? COLLATE NOCASE",
               (kullanici_adi,))
    if not k or not guvenlik.dogrula(sifre, k["sifre"], k["tuz"] or ""):
        raise ServisHata("Kullanıcı adı veya şifre hatalı.")
    if not k["aktif"]:
        raise ServisHata("Bu hesap yönetici tarafından kapatılmış.")
    if guvenlik.eski_format_mi(k["sifre"], k["tuz"] or ""):
        h, t = guvenlik.hashle(sifre)
        db.calistir("UPDATE kullanicilar SET sifre=?, tuz=? WHERE id=?",
                    (h, t, k["id"]))
        k["sifre"], k["tuz"] = h, t
    db.log(k["id"], "giris", f"rol={k['rol']}")
    return k


def yetki(kullanici, izin) -> bool:
    if not kullanici:
        return False
    return kullanici.get("rol") in ayar.YETKI.get(izin, ())


def yetki_iste(kullanici, izin):
    if not yetki(kullanici, izin):
        raise ServisHata("Bu işlem için yetkiniz yok.")


def kullanici_listele(rol=None):
    if rol:
        return db.sorgu("SELECT * FROM kullanicilar WHERE rol=? "
                        "ORDER BY ad_soyad COLLATE NOCASE", (rol,))
    return db.sorgu("SELECT * FROM kullanicilar ORDER BY rol, ad_soyad "
                    "COLLATE NOCASE")


def kullanici_ekle(kullanici_adi, ad_soyad, sifre, rol=ayar.ROL_PERSONEL,
                   telefon="", eposta="", olusturan_id=None):
    kullanici_adi = (kullanici_adi or "").strip()
    if not kullanici_adi or not (ad_soyad or "").strip():
        raise ServisHata("Kullanıcı adı ve ad soyad zorunludur.")
    if len(sifre or "") < 4:
        raise ServisHata("Şifre en az 4 karakter olmalı.")
    if rol not in ayar.ROLLER:
        raise ServisHata("Geçersiz rol.")
    if db.tek("SELECT 1 FROM kullanicilar WHERE kullanici_adi=? COLLATE NOCASE",
              (kullanici_adi,)):
        raise ServisHata("Bu kullanıcı adı zaten kayıtlı.")
    h, t = guvenlik.hashle(sifre)
    uid = db.calistir(
        "INSERT INTO kullanicilar (kullanici_adi,ad_soyad,telefon,eposta,rol,"
        "sifre,tuz,olusturma) VALUES (?,?,?,?,?,?,?,?)",
        (kullanici_adi, ad_soyad.strip(), telefon, eposta, rol, h, t,
         db.iso_simdi()))
    db.log(olusturan_id, "kullanici_ekle", f"{kullanici_adi}/{rol}")
    return uid


def kullanici_sil(kullanici_id, olusturan_id=None):
    k = db.tek("SELECT * FROM kullanicilar WHERE id=?", (kullanici_id,))
    if not k:
        raise ServisHata("Kullanıcı bulunamadı.")
    if k["rol"] == ayar.ROL_YONETICI and yonetici_sayisi() <= 1:
        raise ServisHata("Son yönetici silinemez.")
    db.calistir("UPDATE musteriler SET kullanici_id=NULL WHERE kullanici_id=?",
                (kullanici_id,))
    db.calistir("DELETE FROM kullanicilar WHERE id=?", (kullanici_id,))
    db.log(olusturan_id, "kullanici_sil", k["kullanici_adi"])


def kullanici_durum(kullanici_id, aktif, olusturan_id=None):
    k = db.tek("SELECT * FROM kullanicilar WHERE id=?", (kullanici_id,))
    if not k:
        raise ServisHata("Kullanıcı bulunamadı.")
    if not aktif and k["rol"] == ayar.ROL_YONETICI and yonetici_sayisi() <= 1:
        raise ServisHata("Son yönetici kapatılamaz.")
    db.calistir("UPDATE kullanicilar SET aktif=? WHERE id=?",
                (1 if aktif else 0, kullanici_id))
    db.log(olusturan_id, "kullanici_durum", f"{k['kullanici_adi']}={aktif}")


def sifre_degistir(kullanici_id, yeni_sifre, eski_sifre=None):
    k = db.tek("SELECT * FROM kullanicilar WHERE id=?", (kullanici_id,))
    if not k:
        raise ServisHata("Kullanıcı bulunamadı.")
    if eski_sifre is not None and not guvenlik.dogrula(
            eski_sifre, k["sifre"], k["tuz"] or ""):
        raise ServisHata("Mevcut şifre hatalı.")
    if len(yeni_sifre or "") < 4:
        raise ServisHata("Yeni şifre en az 4 karakter olmalı.")
    h, t = guvenlik.hashle(yeni_sifre)
    db.calistir("UPDATE kullanicilar SET sifre=?, tuz=? WHERE id=?",
                (h, t, kullanici_id))
    db.log(kullanici_id, "sifre_degistir", k["kullanici_adi"])


def yonetici_sayisi():
    return db.tek("SELECT COUNT(*) c FROM kullanicilar WHERE rol=? AND aktif=1",
                  (ayar.ROL_YONETICI,))["c"]


# ==========================================================================
# MÜŞTERİ
# ==========================================================================
def musteri_listele(arama=""):
    if arama:
        like = f"%{arama}%"
        return db.sorgu(
            "SELECT * FROM musteriler WHERE ad_soyad LIKE ? OR telefon LIKE ? "
            "ORDER BY ad_soyad COLLATE NOCASE", (like, like))
    return db.sorgu("SELECT * FROM musteriler ORDER BY ad_soyad COLLATE NOCASE")


def musteri_bul(musteri_id):
    return db.tek("SELECT * FROM musteriler WHERE id=?", (musteri_id,))


def musteri_kullanicidan(kullanici_id):
    return db.tek("SELECT * FROM musteriler WHERE kullanici_id=?",
                  (kullanici_id,))


def musteri_ekle(ad_soyad, telefon="", adres="", eposta="", kullanici_id=None,
                 olusturan_id=None):
    if not (ad_soyad or "").strip():
        raise ServisHata("Müşteri adı zorunludur.")
    mid = db.calistir(
        "INSERT INTO musteriler (ad_soyad,telefon,adres,eposta,kullanici_id,"
        "olusturma) VALUES (?,?,?,?,?,?)",
        (ad_soyad.strip(), telefon, adres, eposta, kullanici_id, db.iso_simdi()))
    db.log(olusturan_id, "musteri_ekle", f"{ad_soyad} #{mid}")
    return mid


def musteri_guncelle(musteri_id, **alanlar):
    izinli = {"ad_soyad", "telefon", "adres", "eposta", "kullanici_id"}
    alanlar = {k: v for k, v in alanlar.items() if k in izinli}
    if not alanlar:
        return
    set_ = ", ".join(f"{k}=?" for k in alanlar)
    db.calistir(f"UPDATE musteriler SET {set_} WHERE id=?",
                tuple(alanlar.values()) + (musteri_id,))


def musteri_bul_veya_ekle(ad_soyad, telefon="", adres="", olusturan_id=None):
    """Aynı isim+telefonla kayıt varsa onu kullanır, yoksa yeni açar."""
    tel = db.tel_temizle(telefon)
    for m in musteri_listele():
        if m["ad_soyad"].strip().lower() == (ad_soyad or "").strip().lower() and \
                (not tel or db.tel_temizle(m["telefon"]) == tel):
            if telefon and not m["telefon"]:
                musteri_guncelle(m["id"], telefon=telefon)
            return m["id"]
    return musteri_ekle(ad_soyad, telefon, adres, olusturan_id=olusturan_id)


# ==========================================================================
# SERVİS KAYITLARI
# ==========================================================================
SERVIS_SELECT = """
SELECT s.*, m.ad_soyad, m.telefon, m.adres, m.eposta,
       m.kullanici_id AS musteri_kullanici_id
FROM servisler s JOIN musteriler m ON m.id = s.musteri_id
"""


def servis_listele(arama="", durum=None, arsiv=0, musteri_id=None, limit=None):
    sql = SERVIS_SELECT
    kosul, deger = [], []
    if arsiv is not None:
        kosul.append("s.arsiv=?")
        deger.append(1 if arsiv else 0)
    if durum:
        kosul.append("s.durum=?")
        deger.append(durum)
    if musteri_id:
        kosul.append("s.musteri_id=?")
        deger.append(musteri_id)
    if arama:
        like = f"%{arama}%"
        kosul.append("(s.kod LIKE ? OR m.ad_soyad LIKE ? OR m.telefon LIKE ? "
                     "OR s.marka LIKE ? OR s.urun LIKE ? OR s.ariza LIKE ?)")
        deger += [like] * 6
    if kosul:
        sql += " WHERE " + " AND ".join(kosul)
    sql += " ORDER BY s.id DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db.sorgu(sql, tuple(deger))


def servis_bul(servis_id=None, kod=None):
    if kod:
        return db.tek(SERVIS_SELECT + " WHERE s.kod=?", (str(kod).strip(),))
    return db.tek(SERVIS_SELECT + " WHERE s.id=?", (servis_id,))


def servis_ekle(musteri_id, marka, urun, model="", seri_no="", ariza="",
                garanti="Bilinmiyor", fatura_durumu="Fatura yok",
                iscilik=0, not_servis="", olusturan_id=None):
    if not musteri_id:
        raise ServisHata("Müşteri seçilmedi.")
    if not (urun or "").strip():
        raise ServisHata("Ürün/cihaz bilgisi zorunludur.")
    if not (ariza or "").strip():
        raise ServisHata("Arıza açıklaması zorunludur.")
    con = db.baglan()
    try:
        kod = db.servis_kodu_uret(con)
        bugun = db.bugun()
        imlec = con.execute(
            "INSERT INTO servisler (kod,musteri_id,marka,urun,model,seri_no,"
            "ariza,garanti,fatura_durumu,iscilik,not_servis,onay_kodu,"
            "giris_tarihi,teslim_tarihi,olusturan_id,guncelleme) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kod, musteri_id, marka or "Diğer marka", urun.strip(), model,
             seri_no, ariza.strip(), garanti, fatura_durumu, db.kurus(iscilik),
             not_servis, guvenlik.onay_kodu(), bugun,
             db.gun_ekle(bugun, ayar.TESLIM_GUN), olusturan_id, db.iso_simdi()))
        con.commit()
        sid = imlec.lastrowid
    finally:
        con.close()
    db.log(olusturan_id, "servis_ekle", f"{kod} {marka} {urun}")
    return sid


def servis_guncelle(servis_id, kullanici_id=None, **alanlar):
    izinli = {"marka", "urun", "model", "seri_no", "ariza", "cozum", "durum",
              "garanti", "fatura_durumu", "kayit_onay", "masraf_onay",
              "masraf_tutar", "iscilik", "not_servis", "teslim_tarihi",
              "cikis_tarihi", "arsiv"}
    temiz = {}
    for k, v in alanlar.items():
        if k not in izinli:
            continue
        if k in ("masraf_tutar", "iscilik"):
            v = db.kurus(v)
        if k == "durum" and v not in ayar.DURUMLAR:
            raise ServisHata("Geçersiz durum.")
        temiz[k] = v
    if not temiz:
        return
    temiz["guncelleme"] = db.iso_simdi()
    set_ = ", ".join(f"{k}=?" for k in temiz)
    db.calistir(f"UPDATE servisler SET {set_} WHERE id=?",
                tuple(temiz.values()) + (servis_id,))
    db.log(kullanici_id, "servis_guncelle",
           f"#{servis_id} " + ", ".join(f"{k}={v}" for k, v in temiz.items()
                                        if k != "guncelleme"))


def durum_guncelle(servis_id, yeni_durum, kullanici_id=None):
    if yeni_durum not in ayar.DURUMLAR:
        raise ServisHata("Geçersiz durum.")
    ek = {}
    if yeni_durum == "Teslim Edildi":
        ek["cikis_tarihi"] = db.bugun()
    servis_guncelle(servis_id, kullanici_id, durum=yeni_durum, **ek)


def durum_ilerlet(servis_id, kullanici_id=None):
    s = servis_bul(servis_id)
    if not s:
        raise ServisHata("Servis kaydı bulunamadı.")
    i = ayar.DURUMLAR.index(s["durum"]) if s["durum"] in ayar.DURUMLAR else 0
    if i >= len(ayar.DURUMLAR) - 1:
        raise ServisHata("Kayıt zaten teslim edilmiş.")
    yeni = ayar.DURUMLAR[i + 1]
    durum_guncelle(servis_id, yeni, kullanici_id)
    return yeni


def servis_sil(servis_id, kullanici_id=None):
    s = servis_bul(servis_id)
    if not s:
        raise ServisHata("Servis kaydı bulunamadı.")
    if db.tek("SELECT 1 FROM faturalar WHERE servis_id=?", (servis_id,)):
        raise ServisHata("Faturası kesilmiş kayıt silinemez; arşivleyin.")
    db.calistir("DELETE FROM servis_parcalari WHERE servis_id=?", (servis_id,))
    db.calistir("DELETE FROM servisler WHERE id=?", (servis_id,))
    db.log(kullanici_id, "servis_sil", s["kod"])


def arsivle(servis_id, arsiv=True, kullanici_id=None):
    servis_guncelle(servis_id, kullanici_id, arsiv=1 if arsiv else 0)


def kod_dogrula(kod, onay_kodu):
    """Müşteri kod sorgusu: servis kodu + onay kodu doğruysa kaydı döndürür."""
    s = servis_bul(kod=kod)
    if not s:
        raise ServisHata("Bu servis kodu bulunamadı.")
    if (onay_kodu or "").strip() != (s["onay_kodu"] or ""):
        raise ServisHata("Onay kodu hatalı.")
    return s


def kayit_onay_ver(servis_id, karar, kullanici_id=None):
    if karar not in ayar.ONAY_SECENEKLERI:
        raise ServisHata("Geçersiz karar.")
    servis_guncelle(servis_id, kullanici_id, kayit_onay=karar)


def masraf_bildir(servis_id, tutar, kullanici_id=None):
    """Personel tamir ücretini girer, müşteri onayına düşer."""
    servis_guncelle(servis_id, kullanici_id, masraf_tutar=tutar,
                    masraf_onay="Bekliyor")


def masraf_onayla(servis_id, karar, kullanici_id=None):
    if karar not in ayar.ONAY_SECENEKLERI:
        raise ServisHata("Geçersiz karar.")
    servis_guncelle(servis_id, kullanici_id, masraf_onay=karar)


# ==========================================================================
# SERVİSE PARÇA / ÜRÜN KULLANIMI
# ==========================================================================
def parca_listele(servis_id):
    return db.sorgu("SELECT * FROM servis_parcalari WHERE servis_id=? "
                    "ORDER BY id", (servis_id,))


def parca_ekle(servis_id, urun_kod, adet=1, kullanici_id=None):
    u = urn.bul(urun_kod)
    if not u:
        raise ServisHata("Ürün/parça bulunamadı.")
    adet = max(1, int(adet))
    if int(u["stok"]) < adet:
        raise ServisHata(f"Yetersiz stok. Mevcut: {u['stok']} adet.")
    db.calistir("INSERT INTO servis_parcalari (servis_id,urun_kod,ad,adet,"
                "birim_fiyat,tarih) VALUES (?,?,?,?,?,?)",
                (servis_id, u["kod"], u["ad"], adet, u["satis_fiyat"],
                 db.iso_simdi()))
    urn.stok_dus(u["kod"], adet, kullanici_id, f"servis #{servis_id}")
    db.log(kullanici_id, "parca_ekle", f"#{servis_id} {u['kod']} x{adet}")


def parca_sil(parca_id, kullanici_id=None, stok_geri=True):
    p = db.tek("SELECT * FROM servis_parcalari WHERE id=?", (parca_id,))
    if not p:
        raise ServisHata("Parça kaydı bulunamadı.")
    db.calistir("DELETE FROM servis_parcalari WHERE id=?", (parca_id,))
    if stok_geri:
        urn.stok_degistir(p["urun_kod"], int(p["adet"]), kullanici_id, "iade")
    db.log(kullanici_id, "parca_sil", f"{p['urun_kod']} x{p['adet']}")


def maliyet(servis_id):
    """{'parca':…, 'iscilik':…, 'ara_toplam':…, 'kdv':…, 'toplam':…} (kuruş)"""
    s = servis_bul(servis_id)
    if not s:
        raise ServisHata("Servis kaydı bulunamadı.")
    r = db.tek("SELECT COALESCE(SUM(adet*birim_fiyat),0) t "
               "FROM servis_parcalari WHERE servis_id=?", (servis_id,))
    parca = int(r["t"])
    iscilik = int(s["iscilik"] or 0)
    if not iscilik and s["masraf_tutar"]:
        iscilik = int(s["masraf_tutar"])
    ara = parca + iscilik
    kdv = int(round(ara * ayar.KDV_ORANI))
    return {"parca": parca, "iscilik": iscilik, "ara_toplam": ara,
            "kdv": kdv, "toplam": ara + kdv}


# ==========================================================================
# TESLİM TAKİBİ / HATIRLATMA
# ==========================================================================
def teslim_bekleyenler():
    return db.sorgu(SERVIS_SELECT + " WHERE s.durum='Teslime Hazır' AND s.arsiv=0"
                    " ORDER BY s.teslim_tarihi")


def hatirlatma_gerekenler():
    """Teslim tarihi + HATIRLATMA_GUN geçmiş, hâlâ teslim alınmamış kayıtlar."""
    sonuc = []
    for s in teslim_bekleyenler():
        gecen = db.gun_farki(s["teslim_tarihi"] or s["giris_tarihi"])
        if gecen is None:
            continue
        if gecen >= ayar.HATIRLATMA_GUN:
            son = db.gun_farki(s["hatirlatma_tarihi"]) if s["hatirlatma_tarihi"] else None
            if son is None or son >= ayar.HATIRLATMA_GUN:
                s["gecikme_gun"] = gecen
                sonuc.append(s)
    return sonuc


def hatirlatma_isaretle(servis_id, kullanici_id=None):
    db.calistir("UPDATE servisler SET hatirlatma_tarihi=?, "
                "hatirlatma_sayisi=hatirlatma_sayisi+1 WHERE id=?",
                (db.bugun(), servis_id))
    db.log(kullanici_id, "hatirlatma", f"#{servis_id}")


# ==========================================================================
# ÜRÜN / STOK (urunler modülüne köprü)
# ==========================================================================
def urun_listele(arama="", sadece_kritik=False):
    return urn.listele(arama, sadece_kritik)


def urun_bul(kod):
    return urn.bul(kod)


def urun_ekle(kod, ad, stok=0, kritik=5, gelis="0", satis="0",
              garanti="2 yıl üretici garantisi", kategori="Yedek Parça",
              kullanici_id=None):
    kod = (kod or "").strip() or db.urun_kodu_uret()
    if not (ad or "").strip():
        raise ServisHata("Ürün adı zorunludur.")
    if urn.bul(kod):
        raise ServisHata("Bu ürün kodu zaten kayıtlı.")
    db.calistir(
        "INSERT INTO urunler (kod,ad,kategori,stok,kritik_stok,gelis_fiyat,"
        "satis_fiyat,garanti_suresi,guncelleme) VALUES (?,?,?,?,?,?,?,?,?)",
        (kod, ad.strip(), kategori, int(db.sayi(stok)), int(db.sayi(kritik, 5)),
         db.kurus(gelis), db.kurus(satis), garanti, db.iso_simdi()))
    urn.md_yaz()
    db.log(kullanici_id, "urun_ekle", f"{kod} {ad}")
    return kod


def urun_guncelle(kod, kullanici_id=None, **alanlar):
    izinli = {"ad", "kategori", "stok", "kritik_stok", "gelis_fiyat",
              "satis_fiyat", "garanti_suresi"}
    temiz = {}
    for k, v in alanlar.items():
        if k not in izinli:
            continue
        if k in ("gelis_fiyat", "satis_fiyat"):
            v = db.kurus(v)
        elif k in ("stok", "kritik_stok"):
            v = int(db.sayi(v))
        temiz[k] = v
    if not temiz:
        return
    temiz["guncelleme"] = db.iso_simdi()
    set_ = ", ".join(f"{k}=?" for k in temiz)
    db.calistir(f"UPDATE urunler SET {set_} WHERE kod=?",
                tuple(temiz.values()) + (str(kod),))
    urn.md_yaz()
    db.log(kullanici_id, "urun_guncelle", f"{kod}")


def urun_sil(kod, kullanici_id=None):
    if db.tek("SELECT 1 FROM servis_parcalari WHERE urun_kod=?", (str(kod),)):
        raise ServisHata("Bu ürün servis kayıtlarında kullanılmış; silinemez.")
    db.calistir("DELETE FROM urunler WHERE kod=?", (str(kod),))
    urn.md_yaz()
    db.log(kullanici_id, "urun_sil", str(kod))


def servis_stok_ata(kod, yeni_stok, kullanici_id=None):
    return urn.stok_ata(kod, yeni_stok, kullanici_id)


def servis_kritik_stoklar():
    return urn.kritik_stoklar()


# ==========================================================================
# FATURA
# ==========================================================================
def fatura_listele(durum=None):
    sql = ("SELECT f.*, s.kod AS servis_kod, m.ad_soyad, m.telefon "
           "FROM faturalar f LEFT JOIN servisler s ON s.id=f.servis_id "
           "LEFT JOIN musteriler m ON m.id=s.musteri_id")
    if durum:
        return db.sorgu(sql + " WHERE f.durum=? ORDER BY f.id DESC", (durum,))
    return db.sorgu(sql + " ORDER BY f.id DESC")


def fatura_bul(fatura_id):
    return db.tek("SELECT f.*, s.kod AS servis_kod, m.ad_soyad, m.telefon "
                  "FROM faturalar f LEFT JOIN servisler s ON s.id=f.servis_id "
                  "LEFT JOIN musteriler m ON m.id=s.musteri_id WHERE f.id=?",
                  (fatura_id,))


def fatura_kes(servis_id, aciklama="", kullanici_id=None):
    s = servis_bul(servis_id)
    if not s:
        raise ServisHata("Servis kaydı bulunamadı.")
    if db.tek("SELECT 1 FROM faturalar WHERE servis_id=? AND durum<>'İptal'",
              (servis_id,)):
        raise ServisHata("Bu kayıt için zaten fatura kesilmiş.")
    m = maliyet(servis_id)
    if m["toplam"] <= 0:
        raise ServisHata("Tutar sıfır; işçilik veya parça girilmeli.")
    no = db.fatura_no_uret()
    try:
        fid = db.calistir(
            "INSERT INTO faturalar (fatura_no,servis_id,ara_toplam,kdv,toplam,"
            "aciklama,tarih,olusturan_id) VALUES (?,?,?,?,?,?,?,?)",
            (no, servis_id, m["ara_toplam"], m["kdv"], m["toplam"], aciklama,
             db.iso_simdi(), kullanici_id))
    except sqlite3.IntegrityError:
        raise ServisHata("Fatura numarası çakıştı, tekrar deneyin.")
    servis_guncelle(servis_id, kullanici_id, fatura_durumu="Fatura var")
    db.log(kullanici_id, "fatura_kes", f"{no} {db.para(m['toplam'])}")
    return fid


def fatura_revize(fatura_id, yeni_toplam, aciklama="", kullanici_id=None):
    f = fatura_bul(fatura_id)
    if not f:
        raise ServisHata("Fatura bulunamadı.")
    if f["durum"] == "İptal":
        raise ServisHata("İptal edilmiş fatura revize edilemez.")
    toplam = db.kurus(yeni_toplam)
    if toplam <= 0:
        raise ServisHata("Tutar sıfırdan büyük olmalı.")
    ara = int(round(toplam / (1 + ayar.KDV_ORANI)))
    db.calistir("UPDATE faturalar SET ara_toplam=?,kdv=?,toplam=?,"
                "revizyon=revizyon+1,aciklama=?,tarih=? WHERE id=?",
                (ara, toplam - ara, toplam,
                 aciklama or f["aciklama"], db.iso_simdi(), fatura_id))
    db.log(kullanici_id, "fatura_revize", f"{f['fatura_no']} -> {db.para(toplam)}")


def fatura_durum(fatura_id, durum, kullanici_id=None):
    if durum not in ayar.FATURA_DURUMLARI:
        raise ServisHata("Geçersiz fatura durumu.")
    f = fatura_bul(fatura_id)
    if not f:
        raise ServisHata("Fatura bulunamadı.")
    db.calistir("UPDATE faturalar SET durum=? WHERE id=?", (durum, fatura_id))
    db.log(kullanici_id, "fatura_durum", f"{f['fatura_no']}={durum}")


# ==========================================================================
# SİPARİŞ (ürün satışı + WhatsApp bildirimi)
# ==========================================================================
def siparis_olustur(satirlar, musteri_adi="", telefon="", musteri_id=None,
                    kullanici_id=None, stok_dus=True):
    """satirlar: [{'urun_kod':…, 'ad':…, 'adet':n, 'birim_fiyat':kuruş}]"""
    if not satirlar:
        raise ServisHata("Sipariş satırı yok.")
    toplam = 0
    for s in satirlar:
        adet = max(1, int(s.get("adet", 1)))
        fiyat = int(s.get("birim_fiyat", 0))
        toplam += adet * fiyat
        if stok_dus and s.get("urun_kod"):
            u = urn.bul(s["urun_kod"])
            if u and int(u["stok"]) < adet:
                raise ServisHata(f"{u['ad']} için yetersiz stok "
                                 f"(mevcut {u['stok']}).")
    no = db.fatura_no_uret()
    sid = db.calistir(
        "INSERT INTO siparisler (fatura_no,musteri_id,musteri_adi,telefon,"
        "toplam,tarih,olusturan_id) VALUES (?,?,?,?,?,?,?)",
        (no, musteri_id, musteri_adi, telefon, toplam, db.iso_simdi(),
         kullanici_id))
    for s in satirlar:
        db.calistir("INSERT INTO siparis_satirlari (siparis_id,urun_kod,ad,"
                    "adet,birim_fiyat) VALUES (?,?,?,?,?)",
                    (sid, s.get("urun_kod", ""), s.get("ad", ""),
                     max(1, int(s.get("adet", 1))),
                     int(s.get("birim_fiyat", 0))))
        if stok_dus and s.get("urun_kod"):
            urn.stok_dus(s["urun_kod"], int(s.get("adet", 1)), kullanici_id,
                         f"sipariş {no}")
    db.log(kullanici_id, "siparis", f"{no} {db.para(toplam)}")
    return {"id": sid, "fatura_no": no, "toplam": toplam,
            "satirlar": satirlar, "musteri_adi": musteri_adi,
            "telefon": telefon}


def siparis_listele(limit=200):
    return db.sorgu("SELECT * FROM siparisler ORDER BY id DESC LIMIT ?",
                    (limit,))


def siparis_satirlari(siparis_id):
    return db.sorgu("SELECT * FROM siparis_satirlari WHERE siparis_id=? "
                    "ORDER BY id", (siparis_id,))


# ==========================================================================
# RAPOR
# ==========================================================================
def ozet_rapor():
    t = {}
    t["servis_toplam"] = db.tek("SELECT COUNT(*) c FROM servisler")["c"]
    t["servis_acik"] = db.tek(
        "SELECT COUNT(*) c FROM servisler WHERE durum<>'Teslim Edildi' "
        "AND arsiv=0")["c"]
    t["teslim_hazir"] = db.tek(
        "SELECT COUNT(*) c FROM servisler WHERE durum='Teslime Hazır'")["c"]
    t["musteri"] = db.tek("SELECT COUNT(*) c FROM musteriler")["c"]
    t["urun"] = db.tek("SELECT COUNT(*) c FROM urunler")["c"]
    t["kritik_stok"] = db.tek(
        "SELECT COUNT(*) c FROM urunler WHERE stok<=kritik_stok")["c"]
    t["stok_degeri"] = db.tek(
        "SELECT COALESCE(SUM(stok*gelis_fiyat),0) s FROM urunler")["s"]
    t["fatura_adet"] = db.tek("SELECT COUNT(*) c FROM faturalar")["c"]
    t["ciro"] = db.tek("SELECT COALESCE(SUM(toplam),0) s FROM faturalar "
                       "WHERE durum<>'İptal'")["s"]
    t["tahsil"] = db.tek("SELECT COALESCE(SUM(toplam),0) s FROM faturalar "
                         "WHERE durum='Ödendi'")["s"]
    t["siparis_ciro"] = db.tek("SELECT COALESCE(SUM(toplam),0) s "
                               "FROM siparisler")["s"]
    t["hatirlatma"] = len(hatirlatma_gerekenler())
    return t


def durum_dagilimi():
    satir = db.sorgu("SELECT durum, COUNT(*) c FROM servisler WHERE arsiv=0 "
                     "GROUP BY durum")
    d = {k: 0 for k in ayar.DURUMLAR}
    for s in satir:
        d[s["durum"]] = s["c"]
    return d


def marka_dagilimi():
    return db.sorgu("SELECT marka, COUNT(*) c FROM servisler GROUP BY marka "
                    "ORDER BY c DESC")


def aylik_ciro(ay_sayisi=12):
    return db.sorgu(
        "SELECT substr(tarih,1,7) ay, COUNT(*) adet, SUM(toplam) toplam "
        "FROM faturalar WHERE durum<>'İptal' GROUP BY ay "
        "ORDER BY ay DESC LIMIT ?", (ay_sayisi,))


def en_cok_kullanilan_parcalar(limit=10):
    return db.sorgu(
        "SELECT urun_kod, ad, SUM(adet) adet, SUM(adet*birim_fiyat) tutar "
        "FROM servis_parcalari GROUP BY urun_kod ORDER BY adet DESC LIMIT ?",
        (limit,))


def son_loglar(limit=200):
    return db.sorgu(
        "SELECT l.*, k.ad_soyad, k.kullanici_adi FROM loglar l "
        "LEFT JOIN kullanicilar k ON k.id=l.kullanici_id "
        "ORDER BY l.id DESC LIMIT ?", (limit,))

# ==========================================================================
# core/goc.py
# ==========================================================================

# Eski kayıt alanları (main.py / DENEME sürümü)
ESKI_ALANLAR = ["kod", "ad", "tel", "marka", "urun", "ariza", "cozum",
                "fatura", "garanti", "kayit_onay", "masraf_onay",
                "masraf_tutar", "durum", "not_servis", "onay_kodu", "tarih"]

# Eski durum isimleri -> yeni durum listesi
DURUM_ESLESTIR = {
    "Yeni Kayıt": "Kayıt Alındı",
    "Kayıt Alındı": "Kayıt Alındı",
    "İnceleniyor": "İnceleniyor",
    "Parça Bekliyor": "Parça Bekleniyor",
    "Parça Bekleniyor": "Parça Bekleniyor",
    "Tamir Edildi": "Test Ediliyor",
    "Tamir Ediliyor": "Tamir Ediliyor",
    "Test Ediliyor": "Test Ediliyor",
    "Teslime Hazır": "Teslime Hazır",
    "Teslim Edildi": "Teslim Edildi",
}


def _durum(eski):
    return DURUM_ESLESTIR.get((eski or "").strip(), "Kayıt Alındı")


def _garanti(eski):
    e = (eski or "").strip().lower()
    if e in ("var", "evet", "garanti kapsamında"):
        return "Garanti kapsamında"
    if e in ("yok", "hayır", "garanti süresi doldu"):
        return "Garanti süresi doldu"
    return eski if eski in ayar.GARANTI_SECENEKLERI else "Bilinmiyor"


def _onay(eski):
    e = (eski or "").strip().lower()
    if e.startswith("onay"):
        return "Onaylandı"
    if e.startswith("red"):
        return "Reddedildi"
    return "Bekliyor"


def _isaretle(yol):
    try:
        os.replace(yol, yol + ".eski")
    except OSError:
        pass


def _eski_kayit_aktar(k, olusturan_id=None):
    """Tek bir eski kaydı (dict) yeni şemaya yazar."""
    kod = str(k.get("kod") or "").strip()
    if not kod:
        return False
    if db.tek("SELECT 1 FROM servisler WHERE kod=?", (kod,)):
        return False
    mid = srv.musteri_bul_veya_ekle(k.get("ad") or "Bilinmeyen Müşteri",
                                    k.get("tel") or "")
    tarih = str(k.get("tarih") or "")[:10] or db.bugun()
    db.calistir(
        "INSERT INTO servisler (kod,musteri_id,marka,urun,ariza,cozum,durum,"
        "garanti,fatura_durumu,kayit_onay,masraf_onay,masraf_tutar,iscilik,"
        "onay_kodu,not_servis,giris_tarihi,teslim_tarihi,olusturan_id,"
        "guncelleme) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (kod, mid, k.get("marka") or "Diğer marka", k.get("urun") or "",
         k.get("ariza") or "", k.get("cozum") or "", _durum(k.get("durum")),
         _garanti(k.get("garanti")),
         "Fatura var" if str(k.get("fatura") or "").strip().lower() in
         ("var", "fatura var", "evet") else "Fatura yok",
         _onay(k.get("kayit_onay")), _onay(k.get("masraf_onay")),
         db.kurus(k.get("masraf_tutar")), db.kurus(k.get("masraf_tutar")),
         str(k.get("onay_kodu") or ""), k.get("not_servis") or "",
         tarih, db.gun_ekle(tarih, ayar.TESLIM_GUN), olusturan_id,
         db.iso_simdi()))
    return True


def kayitlar_json_aktar(yol=None):
    yol = yol or ayar.ESKI_DOSYALAR["kayitlar_json"]
    if not os.path.exists(yol):
        return 0
    try:
        with open(yol, "r", encoding="utf-8") as f:
            veri = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0
    kayitlar = veri.values() if isinstance(veri, dict) else veri
    sayac = sum(1 for k in kayitlar if isinstance(k, dict)
                and _eski_kayit_aktar(k))
    _isaretle(yol)
    return sayac


def kullanicilar_json_aktar(yol=None):
    """kullanicilar.json -> kullanicilar tablosu (hash + tuz korunur)."""
    yol = yol or ayar.ESKI_DOSYALAR["kullanicilar_json"]
    if not os.path.exists(yol):
        return 0
    try:
        with open(yol, "r", encoding="utf-8") as f:
            veri = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0
    sayac = 0
    for kadi, k in (veri or {}).items():
        if not isinstance(k, dict):
            continue
        if db.tek("SELECT 1 FROM kullanicilar WHERE kullanici_adi=? "
                  "COLLATE NOCASE", (kadi,)):
            continue
        rol = ayar.ROL_ESKI.get((k.get("rol") or "").lower(), ayar.ROL_PERSONEL)
        db.calistir(
            "INSERT INTO kullanicilar (kullanici_adi,ad_soyad,rol,sifre,tuz,"
            "olusturma) VALUES (?,?,?,?,?,?)",
            (kadi, k.get("ad") or kadi.capitalize(), rol,
             k.get("hash") or k.get("sifre") or "", k.get("salt") or
             k.get("tuz") or "", db.iso_simdi()))
        sayac += 1
    _isaretle(yol)
    return sayac


def eski_db_aktar(yol=None):
    """Kök klasördeki eski servis.db dosyasını içe aktarır."""
    yol = yol or ayar.ESKI_DOSYALAR["eski_db"]
    if not os.path.exists(yol) or os.path.abspath(yol) == os.path.abspath(
            ayar.DB_YOL):
        return 0
    try:
        con = sqlite3.connect(yol)
        con.row_factory = sqlite3.Row
    except sqlite3.Error:
        return 0
    sayac = 0
    try:
        tablolar = {r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "kayitlar" in tablolar:
            for satir in con.execute("SELECT * FROM kayitlar").fetchall():
                k = {a: (satir[a] if a in satir.keys() and satir[a] is not None
                         else "") for a in ESKI_ALANLAR}
                if _eski_kayit_aktar(k):
                    sayac += 1
        if "personel" in tablolar:
            for p in con.execute("SELECT * FROM personel").fetchall():
                kadi = p["kadi"]
                if not kadi or db.tek("SELECT 1 FROM kullanicilar WHERE "
                                      "kullanici_adi=? COLLATE NOCASE",
                                      (kadi,)):
                    continue
                kolon = p.keys()
                rol = ayar.ROL_ESKI.get(
                    (p["rol"] if "rol" in kolon else "") or "", ayar.ROL_PERSONEL)
                db.calistir(
                    "INSERT INTO kullanicilar (kullanici_adi,ad_soyad,telefon,"
                    "rol,sifre,tuz,olusturma) VALUES (?,?,?,?,?,?,?)",
                    (kadi, (p["ad"] if "ad" in kolon else kadi) or kadi,
                     (p["tel"] if "tel" in kolon else "") or "", rol,
                     (p["sifre"] if "sifre" in kolon else "") or "",
                     (p["salt"] if "salt" in kolon else "") or "",
                     db.iso_simdi()))
    except sqlite3.Error:
        pass
    finally:
        con.close()
    _isaretle(yol)
    return sayac


def fatura_sayac_aktar(yol=None):
    """fatura_sayac.txt -> ayarlar tablosu."""
    yol = yol or ayar.ESKI_DOSYALAR["fatura_sayac"]
    if not os.path.exists(yol):
        return 0
    try:
        with open(yol, "r", encoding="utf-8") as f:
            son = int((f.read().strip() or "0"))
    except (ValueError, OSError):
        son = 0
    mevcut = db.ayar_oku("fatura_sayac", "0")
    mevcut = int(mevcut) if str(mevcut).isdigit() else 0
    db.ayar_yaz("fatura_sayac", max(son, mevcut))
    _isaretle(yol)
    return son


def goc_tumunu_aktar():
    """Tüm eski dosyaları sırayla aktarır, özet döndürür."""
    ozet = {}
    try:
        ozet["kullanicilar.json"] = kullanicilar_json_aktar()
        ozet["eski servis.db"] = eski_db_aktar()
        ozet["kayitlar.json"] = kayitlar_json_aktar()
        ozet["fatura_sayac.txt"] = fatura_sayac_aktar()
    except sqlite3.Error:
        pass
    return {k: v for k, v in ozet.items() if v}

# ==========================================================================
# core/mesajlar.py
# ==========================================================================

def wa_url(telefon, metin):
    tel = db.tel_temizle(telefon)
    if not tel:
        return None
    return ("https://web.whatsapp.com/send?phone=" + tel + "&text="
            + urllib.parse.quote(metin))


def wa_ac(telefon, metin):
    """WhatsApp Web'i hazır mesajla açar. (url, hata) döndürür."""
    url = wa_url(telefon, metin)
    if not url:
        return None, ("Geçerli telefon yok. 0'sız 10 hane olmalı "
                      "(örn: 5321112233).")
    try:
        webbrowser.open(url, new=0, autoraise=True)
        return url, None
    except Exception as e:                                  # noqa: BLE001
        return url, f"Tarayıcı açılamadı: {e}"


# --------------------------------------------------------------------------
# SERVİS MESAJLARI
# --------------------------------------------------------------------------
def kayit_acildi(s):
    return (f"Merhaba {s['ad_soyad']},\n"
            f"{s['marka']} {s['urun']} ürününüz servise alınmıştır.\n"
            f"----------------------\n"
            f"Servis/Takip Kodunuz : {s['kod']}\n"
            f"Onay Kodunuz         : {s['onay_kodu']}\n"
            f"Bildirilen sorun     : {s['ariza']}\n"
            f"----------------------\n"
            f"Durumunuzu bu kodlarla sorgulayabilirsiniz.\n"
            f"{ayar.FIRMA}")


def kayit_karari(s, karar):
    if karar == "Onaylandı":
        govde = (f"Servise bıraktığınız ürün KABUL EDİLMİŞTİR.\n"
                 f"İnceleme sonrası tarafınıza bilgi verilecektir.")
    else:
        govde = (f"Servis kaydınız REDDEDİLMİŞTİR.\n"
                 f"Detay için servisimizle iletişime geçebilirsiniz.")
    return (f"Merhaba {s['ad_soyad']},\n{govde}\n"
            f"----------------------\n"
            f"Marka / Ürün : {s['marka']} {s['urun']}\n"
            f"Bildirilen sorun : {s['ariza']}\n"
            f"Servis Kodu : {s['kod']}\n"
            f"----------------------\n{ayar.FIRMA}")


def durum_bilgisi(s):
    satir = [f"Merhaba {s['ad_soyad']},",
             f"Servis Kodu : {s['kod']}",
             f"Ürün        : {s['marka']} {s['urun']}",
             f"Sorun       : {s['ariza']}",
             f"Durum       : {s['durum']}"]
    if s.get("masraf_tutar"):
        satir.append(f"Tamir Ücreti: {db.para(s['masraf_tutar'])}")
    if s.get("not_servis"):
        satir.append(f"Not         : {s['not_servis']}")
    satir.append(ayar.FIRMA)
    return "\n".join(satir)


def masraf_onayi(s, toplam=None):
    tutar = toplam if toplam is not None else s.get("masraf_tutar", 0)
    return (f"Merhaba {s['ad_soyad']},\n"
            f"{s['marka']} {s['urun']} ürününüzün onarım bedeli "
            f"{db.para(tutar)} olarak belirlenmiştir.\n"
            f"----------------------\n"
            f"Servis Kodu : {s['kod']}\n"
            f"Tespit      : {s.get('cozum') or s['ariza']}\n"
            f"----------------------\n"
            f"Onarımın yapılmasını onaylıyor musunuz? Lütfen bu mesaja "
            f"'ONAY' veya 'RED' yazarak dönüş yapınız.\n{ayar.FIRMA}")


def hazir_bildirimi(s, toplam=None):
    satir = [f"Merhaba {s['ad_soyad']},",
             "Ürününüzün SORUNU ÇÖZÜLMÜŞTÜR ve teslime hazırdır. ✅",
             "----------------------",
             f"Marka / Ürün    : {s['marka']} {s['urun']}",
             f"Giderilen sorun : {s['ariza']}"]
    if s.get("cozum"):
        satir.append(f"Yapılan işlem   : {s['cozum']}")
    satir.append(f"Servis Kodu     : {s['kod']}")
    tutar = toplam if toplam is not None else s.get("masraf_tutar", 0)
    if tutar:
        satir.append(f"Tutar           : {db.para(tutar)}")
    satir += ["----------------------",
              "Ürününüzü servisimizden teslim alabilirsiniz. İyi günler.",
              ayar.FIRMA]
    return "\n".join(satir)


def hatirlatma(s):
    gun = s.get("gecikme_gun")
    gun_str = f" ({gun} gündür bekliyor)" if gun else ""
    return (f"Merhaba {s['ad_soyad']},\n"
            f"{s['marka']} {s['urun']} ürününüz {s['kod']} numaralı servis "
            f"kaydıyla teslime hazır{gun_str}.\n"
            f"Uygun olduğunuzda servisimizden teslim alabilirsiniz.\n"
            f"{ayar.FIRMA}")


# --------------------------------------------------------------------------
# SİPARİŞ / SATIŞ MESAJI
# --------------------------------------------------------------------------
def siparis(alici_ad, satirlar, fatura_no=None, gonderen=None):
    """satirlar: [{'ad':…, 'adet':n, 'birim_fiyat':kuruş}]"""
    gonderen = gonderen or ayar.FIRMA
    govde, toplam = [], 0
    for s in satirlar:
        adet = max(1, int(s.get("adet", 1)))
        tutar = adet * int(s.get("birim_fiyat", 0))
        toplam += tutar
        govde.append(f"• {s.get('ad', '')} x{adet} — {db.para(tutar)}")
    fatura_satiri = f"\nFatura No: {fatura_no}\n" if fatura_no else ""
    return (f"Sayın {alici_ad},\n\n"
            f"Siparişiniz hazırlanmıştır, gelip teslim alabilirsiniz.\n\n"
            f"SİPARİŞ İÇERİĞİ\n" + "\n".join(govde)
            + f"\n\nToplam: {db.para(toplam)}\n" + fatura_satiri
            + f"\nGönderen: {gonderen}")


def fatura_bilgisi(f):
    return (f"Sayın {f.get('ad_soyad') or ''},\n"
            f"{f['fatura_no']} numaralı faturanız hazırlanmıştır.\n"
            f"----------------------\n"
            f"Ara Toplam : {db.para(f['ara_toplam'])}\n"
            f"KDV        : {db.para(f['kdv'])}\n"
            f"TOPLAM     : {db.para(f['toplam'])}\n"
            f"Durum      : {f['durum']}\n"
            f"----------------------\n{ayar.FIRMA}")

# ==========================================================================
# core/fis.py
# ==========================================================================

def kacir(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


STIL = """
  *{box-sizing:border-box;}
  body{font-family:Arial,Helvetica,sans-serif;color:#111;background:#eee;
       margin:0;padding:14px;}
  .kart{background:#fff;max-width:620px;margin:0 auto 14px;border:2px solid #111;
        border-radius:6px;padding:14px 16px;}
  .ust{display:flex;justify-content:space-between;align-items:center;
       border-bottom:2px solid #111;padding-bottom:8px;}
  .logo{font-size:19px;font-weight:bold;letter-spacing:.5px;}
  .logo small{display:block;font-size:10px;font-weight:normal;color:#666;
              letter-spacing:0;}
  .nod{text-align:center;border:2px solid #111;border-radius:6px;padding:2px 12px;}
  .nolbl{font-size:9px;color:#555;letter-spacing:1px;}
  .noval{font-size:22px;font-weight:bold;letter-spacing:1px;}
  .baslik{text-align:center;font-weight:bold;font-size:13px;letter-spacing:1px;
          background:#111;color:#fff;padding:5px;margin:10px 0;border-radius:4px;}
  .baslik span{font-weight:normal;font-size:11px;}
  .bolum{border:1px solid #999;border-radius:5px;margin-bottom:8px;overflow:hidden;}
  .bh{background:#f0f0f0;font-size:11px;font-weight:bold;letter-spacing:.5px;
      padding:5px 8px;border-bottom:1px solid #999;color:#333;}
  .grid2{display:grid;grid-template-columns:1fr 1fr;}
  .grid2>div{padding:7px 8px;font-size:13px;border-right:1px solid #eee;
             border-bottom:1px solid #eee;}
  .et{display:block;font-size:10px;color:#777;margin-bottom:1px;}
  .uzun{padding:8px;font-size:13px;min-height:34px;}
  table{width:100%;border-collapse:collapse;font-size:12px;}
  th,td{padding:6px 8px;border-bottom:1px solid #e2e2e2;text-align:left;}
  th{background:#f5f5f5;font-size:10px;letter-spacing:.5px;color:#444;}
  td.sag,th.sag{text-align:right;}
  .ucret{display:flex;justify-content:space-between;align-items:center;
         border:2px solid #111;border-radius:5px;padding:7px 12px;margin:8px 0;}
  .ucret span{font-size:12px;letter-spacing:1px;color:#333;}
  .ucret b{font-size:19px;}
  .uyari{background:#ffe8e0;border:1px solid #d33;color:#b23;padding:6px 8px;
         border-radius:5px;font-size:12px;margin:8px 0;text-align:center;
         font-weight:bold;}
  .imza{display:flex;justify-content:space-between;margin-top:24px;gap:20px;}
  .imza div{border-top:1px solid #333;padding-top:5px;width:46%;text-align:center;
            font-size:12px;color:#333;}
  .imza small{color:#777;}
  .kes{text-align:center;color:#999;font-size:11px;border-top:1px dashed #aaa;
       max-width:620px;margin:0 auto 14px;padding-top:4px;}
  .yazbtn{display:block;width:200px;margin:6px auto 20px;padding:12px;
          background:#00b4a6;color:#fff;border:none;border-radius:8px;
          font-size:15px;font-weight:bold;cursor:pointer;}
  @media print{
    body{background:#fff;padding:0;}
    .yazbtn,.kes{display:none;}
    .kart{margin:0 auto;page-break-inside:avoid;}
  }
"""


def _sayfa(baslik, govde):
    return (f"<!DOCTYPE html><html lang='tr'><head><meta charset='UTF-8'>"
            f"<title>{kacir(baslik)}</title><style>{STIL}</style></head><body>"
            f"<button class='yazbtn' onclick='window.print()'>🖨 Yazdır</button>"
            f"{govde}</body></html>")


def _yaz_ve_ac(dosya_adi, html, ac=True):
    yol = os.path.join(tempfile.gettempdir(), dosya_adi)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(html)
    if ac:
        try:
            webbrowser.open("file://" + yol)
        except Exception:                                   # noqa: BLE001
            pass
    return yol


# --------------------------------------------------------------------------
# SERVİS KARTI
# --------------------------------------------------------------------------
def servis_karti(s, parcalar=None, maliyet=None, ac=True):
    parcalar = parcalar or []
    uyari = ("<div class='uyari'>⚠ Bu markada TÜM PARÇALAR gereklidir.</div>"
             if s.get("marka") in ayar.PARCA_GEREKEN else "")
    toplam = (maliyet or {}).get("toplam") or s.get("masraf_tutar") or 0

    parca_tablo = ""
    if parcalar:
        satir = "".join(
            f"<tr><td>{kacir(p['ad'] or p['urun_kod'])}</td>"
            f"<td class='sag'>{p['adet']}</td>"
            f"<td class='sag'>{db.para(p['birim_fiyat'])}</td>"
            f"<td class='sag'>{db.para(p['adet'] * p['birim_fiyat'])}</td></tr>"
            for p in parcalar)
        parca_tablo = (
            "<div class='bolum'><div class='bh'>KULLANILAN PARÇALAR</div>"
            "<table><tr><th>Parça</th><th class='sag'>Adet</th>"
            "<th class='sag'>Birim</th><th class='sag'>Tutar</th></tr>"
            f"{satir}</table></div>")

    def kart(nusha):
        return f"""
  <div class="kart">
    <div class="ust">
      <div class="logo">{kacir(ayar.FIRMA.upper())}
        <small>{kacir(ayar.ALT_BASLIK)}</small></div>
      <div class="nod"><div class="nolbl">SERVİS NO</div>
        <div class="noval">{kacir(s['kod'])}</div></div>
    </div>
    <div class="baslik">SERVİS / REVİZYON KARTI <span>({nusha})</span></div>
    <div class="bolum"><div class="bh">MÜŞTERİ BİLGİLERİ</div>
      <div class="grid2">
        <div><span class="et">Ad Soyad</span>{kacir(s.get('ad_soyad'))}</div>
        <div><span class="et">Telefon</span>{kacir(s.get('telefon') or '-')}</div>
        <div><span class="et">Giriş Tarihi</span>{kacir(s.get('giris_tarihi'))}</div>
        <div><span class="et">Durum</span>{kacir(s.get('durum'))}</div>
      </div></div>
    <div class="bolum"><div class="bh">CİHAZ BİLGİLERİ</div>
      <div class="grid2">
        <div><span class="et">Marka</span>{kacir(s.get('marka'))}</div>
        <div><span class="et">Ürün</span>{kacir(s.get('urun'))}</div>
        <div><span class="et">Model</span>{kacir(s.get('model') or '-')}</div>
        <div><span class="et">Seri No</span>{kacir(s.get('seri_no') or '-')}</div>
        <div><span class="et">Fatura</span>{kacir(s.get('fatura_durumu'))}</div>
        <div><span class="et">Garanti</span>{kacir(s.get('garanti'))}</div>
      </div></div>
    <div class="bolum"><div class="bh">ARIZA / ŞİKAYET</div>
      <div class="uzun">{kacir(s.get('ariza'))}</div></div>
    <div class="bolum"><div class="bh">YAPILAN İŞLEM / ÇÖZÜM</div>
      <div class="uzun">{kacir(s.get('cozum') or '—')}</div></div>
    {parca_tablo}
    <div class="ucret"><span>ÜCRET (KDV DAHİL)</span>
      <b>{db.para(toplam)}</b></div>
    {uyari}
    <div class="imza">
      <div>Teslim Eden<br><small>(Müşteri)</small></div>
      <div>Teslim Alan<br><small>(Servis)</small></div>
    </div>
  </div>"""

    html = _sayfa(f"Servis Kartı {s['kod']}",
                  kart("SERVİS NÜSHASI")
                  + "<div class='kes'>— — — — — kesme çizgisi — — — — —</div>"
                  + kart("MÜŞTERİ NÜSHASI"))
    return _yaz_ve_ac(f"servis_kart_{s['kod']}.html", html, ac)


# --------------------------------------------------------------------------
# FATURA FİŞİ
# --------------------------------------------------------------------------
def fatura_fisi(f, servis=None, parcalar=None, ac=True):
    parcalar = parcalar or []
    satirlar = "".join(
        f"<tr><td>{kacir(p['ad'] or p['urun_kod'])}</td>"
        f"<td class='sag'>{p['adet']}</td>"
        f"<td class='sag'>{db.para(p['birim_fiyat'])}</td>"
        f"<td class='sag'>{db.para(p['adet'] * p['birim_fiyat'])}</td></tr>"
        for p in parcalar)
    iscilik = 0
    if servis:
        iscilik = int(servis.get("iscilik") or servis.get("masraf_tutar") or 0)
    if iscilik:
        satirlar += (f"<tr><td>İşçilik / Servis Bedeli</td><td class='sag'>1</td>"
                     f"<td class='sag'>{db.para(iscilik)}</td>"
                     f"<td class='sag'>{db.para(iscilik)}</td></tr>")

    govde = f"""
  <div class="kart">
    <div class="ust">
      <div class="logo">{kacir(ayar.FIRMA.upper())}
        <small>{kacir(ayar.ALT_BASLIK)}</small></div>
      <div class="nod"><div class="nolbl">FATURA NO</div>
        <div class="noval" style="font-size:15px">{kacir(f['fatura_no'])}</div></div>
    </div>
    <div class="baslik">SERVİS FATURASI
      <span>({kacir(f.get('tarih', '')[:16].replace('T', ' '))})</span></div>
    <div class="bolum"><div class="bh">MÜŞTERİ / SERVİS</div>
      <div class="grid2">
        <div><span class="et">Müşteri</span>{kacir(f.get('ad_soyad') or '-')}</div>
        <div><span class="et">Telefon</span>{kacir(f.get('telefon') or '-')}</div>
        <div><span class="et">Servis Kodu</span>{kacir(f.get('servis_kod') or '-')}</div>
        <div><span class="et">Durum</span>{kacir(f.get('durum'))}</div>
      </div></div>
    <div class="bolum"><div class="bh">KALEMLER</div>
      <table><tr><th>Açıklama</th><th class='sag'>Adet</th>
        <th class='sag'>Birim</th><th class='sag'>Tutar</th></tr>
        {satirlar or "<tr><td colspan='4'>Kalem yok</td></tr>"}
        <tr><th colspan='3' class='sag'>ARA TOPLAM</th>
            <th class='sag'>{db.para(f['ara_toplam'])}</th></tr>
        <tr><th colspan='3' class='sag'>KDV (%{int(ayar.KDV_ORANI * 100)})</th>
            <th class='sag'>{db.para(f['kdv'])}</th></tr>
      </table></div>
    <div class="ucret"><span>GENEL TOPLAM</span><b>{db.para(f['toplam'])}</b></div>
    {"<div class='bolum'><div class='bh'>AÇIKLAMA</div><div class='uzun'>"
     + kacir(f.get('aciklama')) + "</div></div>" if f.get('aciklama') else ""}
    <div class="imza"><div>Düzenleyen</div><div>Teslim Alan</div></div>
  </div>"""
    html = _sayfa(f"Fatura {f['fatura_no']}", govde)
    return _yaz_ve_ac(f"fatura_{f['fatura_no']}.html", html, ac)


# --------------------------------------------------------------------------
# RAPOR ÇIKTISI
# --------------------------------------------------------------------------
def rapor_sayfasi(ozet, durumlar, markalar, kritik, parcalar, ac=True):
    def tablo(baslik, sutunlar, satirlar):
        sut = "".join(f"<th class='{'sag' if i else ''}'>{kacir(s)}</th>"
                      for i, s in enumerate(sutunlar))
        gov = "".join("<tr>" + "".join(
            f"<td class='{'sag' if i else ''}'>{kacir(h)}</td>"
            for i, h in enumerate(satir)) + "</tr>" for satir in satirlar)
        return (f"<div class='bolum'><div class='bh'>{kacir(baslik)}</div>"
                f"<table><tr>{sut}</tr>{gov}</table></div>")

    kutular = [
        ("Toplam Servis", ozet["servis_toplam"]),
        ("Açık İş", ozet["servis_acik"]),
        ("Teslime Hazır", ozet["teslim_hazir"]),
        ("Müşteri", ozet["musteri"]),
        ("Ürün Çeşidi", ozet["urun"]),
        ("Kritik Stok", ozet["kritik_stok"]),
        ("Stok Değeri", db.para(ozet["stok_degeri"])),
        ("Fatura Adedi", ozet["fatura_adet"]),
        ("Ciro", db.para(ozet["ciro"])),
        ("Tahsil Edilen", db.para(ozet["tahsil"])),
        ("Satış/Sipariş", db.para(ozet["siparis_ciro"])),
        ("Hatırlatma", ozet["hatirlatma"]),
    ]
    govde = f"""
  <div class="kart">
    <div class="ust"><div class="logo">{kacir(ayar.FIRMA.upper())}
      <small>{kacir(ayar.ALT_BASLIK)}</small></div>
      <div class="nod"><div class="nolbl">RAPOR</div>
        <div class="noval" style="font-size:14px">{db.simdi()}</div></div></div>
    <div class="baslik">YÖNETİM ÖZET RAPORU</div>
    {tablo("GENEL DURUM", ["Başlık", "Değer"], kutular)}
    {tablo("SERVİS DURUM DAĞILIMI", ["Durum", "Adet"], list(durumlar.items()))}
    {tablo("MARKA DAĞILIMI", ["Marka", "Adet"],
           [(m["marka"], m["c"]) for m in markalar])}
    {tablo("KRİTİK STOK", ["Ürün", "Stok", "Kritik"],
           [(u["ad"], u["stok"], u["kritik_stok"]) for u in kritik])}
    {tablo("EN ÇOK KULLANILAN PARÇALAR", ["Parça", "Adet", "Tutar"],
           [(p["ad"] or p["urun_kod"], p["adet"], db.para(p["tutar"]))
            for p in parcalar])}
  </div>"""
    return _yaz_ve_ac("servis_rapor.html", _sayfa("Yönetim Raporu", govde), ac)

# ==========================================================================
# core/aktarim.py
# ==========================================================================

AYRAC = ";"
KODLAMA = "utf-8-sig"


def _yaz(yol, basliklar, satirlar):
    os.makedirs(os.path.dirname(os.path.abspath(yol)), exist_ok=True)
    with open(yol, "w", newline="", encoding=KODLAMA) as f:
        y = csv.writer(f, delimiter=AYRAC)
        y.writerow(basliklar)
        y.writerows(satirlar)
    return yol


def _varsayilan_yol(ad):
    klasor = os.path.join(ayar.VERI_KLASOR, "aktarim")
    damga = db.simdi().replace(".", "").replace(":", "").replace(" ", "_")
    return os.path.join(klasor, f"{ad}_{damga}.csv")


def servisleri_aktar(yol=None, arsiv=None):
    yol = yol or _varsayilan_yol("servisler")
    basliklar = ["Servis Kodu", "Müşteri", "Telefon", "Marka", "Ürün", "Model",
                 "Seri No", "Arıza", "Çözüm", "Durum", "Garanti", "Fatura",
                 "Kayıt Onayı", "Masraf Onayı", "İşçilik", "Parça Tutarı",
                 "KDV", "Genel Toplam", "Giriş", "Teslim Tarihi", "Çıkış",
                 "Servis Notu"]
    satirlar = []
    for s in srv.servis_listele(arsiv=arsiv):
        m = srv.maliyet(s["id"])
        satirlar.append([
            s["kod"], s["ad_soyad"], s["telefon"], s["marka"], s["urun"],
            s["model"], s["seri_no"], s["ariza"], s["cozum"], s["durum"],
            s["garanti"], s["fatura_durumu"], s["kayit_onay"], s["masraf_onay"],
            db.para(m["iscilik"], False), db.para(m["parca"], False),
            db.para(m["kdv"], False), db.para(m["toplam"], False),
            s["giris_tarihi"], s["teslim_tarihi"] or "", s["cikis_tarihi"] or "",
            s["not_servis"]])
    return _yaz(yol, basliklar, satirlar)


def urunleri_aktar(yol=None):
    yol = yol or _varsayilan_yol("urunler")
    basliklar = ["Ürün Kodu", "Ürün Adı", "Kategori", "Stok", "Kritik Stok",
                 "Geliş Fiyatı", "Satış Fiyatı", "Kâr Marjı %",
                 "Garanti Süresi", "Son Güncelleme"]
    satirlar = [[u["kod"], u["ad"], u["kategori"], u["stok"], u["kritik_stok"],
                 db.para(u["gelis_fiyat"], False),
                 db.para(u["satis_fiyat"], False),
                 f"{urn.kar_marji(u):.1f}", u["garanti_suresi"],
                 (u["guncelleme"] or "")[:16].replace("T", " ")]
                for u in urn.listele()]
    return _yaz(yol, basliklar, satirlar)


def faturalari_aktar(yol=None):
    yol = yol or _varsayilan_yol("faturalar")
    basliklar = ["Fatura No", "Servis Kodu", "Müşteri", "Ara Toplam", "KDV",
                 "Toplam", "Durum", "Revizyon", "Açıklama", "Tarih"]
    satirlar = [[f["fatura_no"], f["servis_kod"] or "", f["ad_soyad"] or "",
                 db.para(f["ara_toplam"], False), db.para(f["kdv"], False),
                 db.para(f["toplam"], False), f["durum"], f["revizyon"],
                 f["aciklama"], (f["tarih"] or "")[:16].replace("T", " ")]
                for f in srv.fatura_listele()]
    return _yaz(yol, basliklar, satirlar)


def musterileri_aktar(yol=None):
    yol = yol or _varsayilan_yol("musteriler")
    basliklar = ["Ad Soyad", "Telefon", "Adres", "E-posta", "Servis Sayısı"]
    satirlar = []
    for m in srv.musteri_listele():
        adet = db.tek("SELECT COUNT(*) c FROM servisler WHERE musteri_id=?",
                      (m["id"],))["c"]
        satirlar.append([m["ad_soyad"], m["telefon"], m["adres"], m["eposta"],
                         adet])
    return _yaz(yol, basliklar, satirlar)


def tumunu_aktar(klasor=None):
    """Dört dosyayı birden üretir; {ad: yol} döndürür."""
    klasor = klasor or os.path.join(ayar.VERI_KLASOR, "aktarim")
    os.makedirs(klasor, exist_ok=True)
    damga = db.simdi().replace(".", "").replace(":", "").replace(" ", "_")
    return {
        "servisler": servisleri_aktar(
            os.path.join(klasor, f"servisler_{damga}.csv")),
        "urunler": urunleri_aktar(os.path.join(klasor, f"urunler_{damga}.csv")),
        "faturalar": faturalari_aktar(
            os.path.join(klasor, f"faturalar_{damga}.csv")),
        "musteriler": musterileri_aktar(
            os.path.join(klasor, f"musteriler_{damga}.csv")),
    }

# ==========================================================================
# ÇEKİRDEK BAŞLATMA
# ==========================================================================

def baslat(ornek_veri=True):
    """Veritabanını hazırlar; arayüz açılışta çağırır."""
    firma_yukle()
    kur(ornek_veri=ornek_veri)

# ==========================================================================
# app_tk.py · TKINTER ARAYÜZÜ
# ==========================================================================

# --------------------------------------------------------------------------
# RENKLER
# --------------------------------------------------------------------------
BG, PANEL, PANEL2 = ayar.BG, ayar.PANEL, ayar.PANEL2
LINE, INK, MUTED = ayar.LINE, ayar.INK, ayar.MUTED
ACCENT, ACCENT2 = ayar.ACCENT, ayar.ACCENT2
OK, NO, WAIT, WA = ayar.OK, ayar.NO, ayar.WAIT, ayar.WA


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.kullanici = None
        self.secili_servis = None
        self.sepet = []
        self.arsiv_modu = False
        self.title(f"{ayar.FIRMA} · Servis Takip PRO {ayar.SURUM}")
        self.geometry("1280x780")
        self.minsize(1060, 660)
        self.configure(bg=BG)
        self._stil()
        self.giris_ekrani()

    # ==================================================== TEMA / YARDIMCI
    def _stil(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background=BG, foreground=INK,
                    fieldbackground=PANEL2, font=("Segoe UI", 10))
        s.configure("TFrame", background=BG)
        s.configure("Kart.TFrame", background=PANEL, relief="flat")
        s.configure("TLabel", background=BG, foreground=INK)
        s.configure("Kart.TLabel", background=PANEL, foreground=INK)
        s.configure("Soluk.TLabel", background=PANEL, foreground=MUTED,
                    font=("Segoe UI", 9))
        s.configure("H1.TLabel", background=BG, foreground=INK,
                    font=("Segoe UI", 18, "bold"))
        s.configure("H2.TLabel", background=PANEL, foreground=INK,
                    font=("Segoe UI", 12, "bold"))
        s.configure("Deger.TLabel", background=PANEL, foreground=ACCENT,
                    font=("Segoe UI", 20, "bold"))
        s.configure("TEntry", fieldbackground=PANEL2, foreground=INK,
                    insertcolor=INK, bordercolor=LINE, padding=5)
        s.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2,
                    foreground=INK, arrowcolor=INK, bordercolor=LINE)
        self.option_add("*TCombobox*Listbox.background", PANEL2)
        self.option_add("*TCombobox*Listbox.foreground", INK)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        s.configure("TButton", background=ACCENT2, foreground="white",
                    borderwidth=0, focusthickness=0, padding=(12, 7),
                    font=("Segoe UI", 10, "bold"))
        s.map("TButton", background=[("active", "#2196f3")])
        s.configure("Aksiyon.TButton", background=ACCENT)
        s.map("Aksiyon.TButton", background=[("active", "#00d3c2")])
        s.configure("Sil.TButton", background=NO)
        s.map("Sil.TButton", background=[("active", "#ff7a90")])
        s.configure("Wa.TButton", background=WA, foreground="#062d17")
        s.map("Wa.TButton", background=[("active", "#3ae57c")])
        s.configure("Hayalet.TButton", background=PANEL2, foreground=INK)
        s.map("Hayalet.TButton", background=[("active", LINE)])
        s.configure("Nav.TButton", background=PANEL, foreground="#c4d3ea",
                    anchor="w", padding=(14, 10), font=("Segoe UI", 10, "bold"))
        s.map("Nav.TButton", background=[("active", PANEL2)])
        s.configure("NavAktif.TButton", background=ACCENT2, foreground="white",
                    anchor="w", padding=(14, 10), font=("Segoe UI", 10, "bold"))
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                    foreground=INK, borderwidth=0, rowheight=26)
        s.configure("Treeview.Heading", background=PANEL2, foreground=MUTED,
                    relief="flat", font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", ACCENT2)],
              foreground=[("selected", "white")])
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                    padding=(14, 8))
        s.map("TNotebook.Tab", background=[("selected", PANEL2)],
              foreground=[("selected", INK)])
        s.configure("TCheckbutton", background=BG, foreground=INK)
        s.configure("Yatay.TScrollbar", background=PANEL2)

    def _temizle(self):
        for w in self.winfo_children():
            w.destroy()

    def kart(self, ana, **kw):
        f = ttk.Frame(ana, style="Kart.TFrame", padding=kw.pop("padding", 14))
        return f

    def bilgi(self, metin):
        messagebox.showinfo(ayar.FIRMA, metin, parent=self)

    def hata(self, metin):
        messagebox.showerror("Hata", metin, parent=self)

    def uyari(self, metin):
        messagebox.showwarning("Dikkat", metin, parent=self)

    def onay(self, metin):
        return messagebox.askyesno(ayar.FIRMA, metin, parent=self)

    def rol(self):
        return (self.kullanici or {}).get("rol", "")

    def yetkili(self, izin):
        return srv.yetki(self.kullanici, izin)

    def kid(self):
        return (self.kullanici or {}).get("id")

    def wa_gonder(self, telefon, metin):
        url, hata = msj.wa_ac(telefon, metin)
        if hata and not url:
            self.uyari(hata)
            return False
        if hata:
            self.uyari(hata + f"\n\nBağlantı:\n{url}")
        return True

    # ==================================================== GİRİŞ
    def giris_ekrani(self):
        self._temizle()
        self.kullanici = None
        sarmal = ttk.Frame(self)
        sarmal.place(relx=0.5, rely=0.5, anchor="center")
        k = self.kart(sarmal, padding=30)
        k.pack()
        ttk.Label(k, text=ayar.FIRMA, style="H2.TLabel",
                  font=("Segoe UI", 20, "bold")).pack()
        ttk.Label(k, text=ayar.ALT_BASLIK, style="Soluk.TLabel").pack(pady=(2, 2))
        ttk.Label(k, text=f"Servis Takip PRO v{ayar.SURUM}",
                  style="Soluk.TLabel").pack(pady=(0, 18))

        ttk.Label(k, text="Kullanıcı Adı", style="Kart.TLabel").pack(anchor="w")
        self.g_kadi = ttk.Entry(k, width=30)
        self.g_kadi.pack(pady=(2, 10))
        ttk.Label(k, text="Şifre", style="Kart.TLabel").pack(anchor="w")
        self.g_sifre = ttk.Entry(k, width=30, show="•")
        self.g_sifre.pack(pady=(2, 6))
        self.g_goster = tk.BooleanVar(value=False)
        ttk.Checkbutton(k, text="Şifreyi göster", variable=self.g_goster,
                        command=lambda: self.g_sifre.configure(
                            show="" if self.g_goster.get() else "•"),
                        style="TCheckbutton").pack(anchor="w", pady=(0, 12))
        ttk.Button(k, text="Giriş Yap", style="Aksiyon.TButton",
                   command=self.giris_yap).pack(fill="x")
        self.g_durum = ttk.Label(k, text="", style="Soluk.TLabel")
        self.g_durum.pack(pady=(10, 0))
        ttk.Label(k, text="İlk kurulum: admin / 1234", style="Soluk.TLabel"
                  ).pack(pady=(14, 0))
        self.g_sifre.bind("<Return>", lambda e: self.giris_yap())
        self.g_kadi.bind("<Return>", lambda e: self.g_sifre.focus_set())
        self.g_kadi.focus_set()
        self.deneme = 0

    def giris_yap(self):
        try:
            self.kullanici = srv.giris(self.g_kadi.get(), self.g_sifre.get())
        except ServisHata as e:
            self.deneme = getattr(self, "deneme", 0) + 1
            kalan = ayar.MAX_DENEME - self.deneme
            if ayar.MAX_DENEME > 0 and kalan <= 0:
                self.hata("Deneme hakkınız doldu, program kapatılıyor.")
                self.destroy()
                return
            ek = f"  (kalan deneme: {kalan})" if ayar.MAX_DENEME > 0 else ""
            self.g_durum.configure(text=str(e) + ek, foreground=NO)
            self.g_sifre.delete(0, "end")
            return
        self.ana_ekran()

    # ==================================================== ANA ÇERÇEVE
    def menuler(self):
        if self.rol() == ayar.ROL_MUSTERI:
            return [("🔧  Kayıtlarım", self.sayfa_kayitlarim),
                    ("💰  Masraf Onayı", self.sayfa_masraf_onay),
                    ("🔎  Kod Sorgula", self.sayfa_kod_sorgu)]
        m = [("🏠  Panel", self.sayfa_panel),
             ("🔧  Servis Kayıtları", self.sayfa_servisler),
             ("➕  Yeni Kayıt", self.sayfa_yeni_kayit),
             ("📦  Ürün / Stok", self.sayfa_urunler),
             ("👥  Müşteriler", self.sayfa_musteriler),
             ("🚚  Teslim Takibi", self.sayfa_teslim),
             ("🧾  Faturalar", self.sayfa_faturalar),
             ("🛒  Sipariş / Satış", self.sayfa_siparis)]
        if self.yetkili("rapor_gor"):
            m.append(("📊  Raporlar", self.sayfa_rapor))
        if self.yetkili("kullanici_yonet"):
            m.append(("🔐  Kullanıcılar", self.sayfa_kullanicilar))
        return m

    def ana_ekran(self):
        self._temizle()
        govde = ttk.Frame(self)
        govde.pack(fill="both", expand=True)

        yan = tk.Frame(govde, bg=PANEL, width=232)
        yan.pack(side="left", fill="y")
        yan.pack_propagate(False)
        tk.Label(yan, text=ayar.FIRMA, bg=PANEL, fg=INK,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16,
                                                     pady=(20, 0))
        tk.Label(yan, text=f"Servis Takip PRO {ayar.SURUM}", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=16)
        tk.Frame(yan, bg=LINE, height=1).pack(fill="x", padx=14, pady=12)
        tk.Label(yan, text=self.kullanici["ad_soyad"], bg=PANEL, fg=INK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16)
        tk.Label(yan, text=ayar.ROL_ADI.get(self.rol(), self.rol()).upper(),
                 bg=PANEL, fg=ACCENT, font=("Segoe UI", 8, "bold")).pack(
            anchor="w", padx=16, pady=(0, 12))

        self.nav_btn = {}
        for ad, komut in self.menuler():
            b = ttk.Button(yan, text=ad, style="Nav.TButton",
                           command=lambda k=komut, a=ad: self._sayfa_ac(a, k))
            b.pack(fill="x", padx=10, pady=2)
            self.nav_btn[ad] = b
        alt = tk.Frame(yan, bg=PANEL)
        alt.pack(side="bottom", fill="x", pady=14, padx=10)
        ttk.Button(alt, text="🔑  Şifre Değiştir", style="Hayalet.TButton",
                   command=self.sifre_penceresi).pack(fill="x", pady=2)
        ttk.Button(alt, text="⎋  Çıkış", style="Sil.TButton",
                   command=self.giris_ekrani).pack(fill="x", pady=2)

        self.icerik = ttk.Frame(govde, padding=18)
        self.icerik.pack(side="left", fill="both", expand=True)
        ilk_ad, ilk_komut = self.menuler()[0]
        self._sayfa_ac(ilk_ad, ilk_komut)

    def _sayfa_ac(self, ad, komut):
        for a, b in self.nav_btn.items():
            b.configure(style="NavAktif.TButton" if a == ad else "Nav.TButton")
        for w in self.icerik.winfo_children():
            w.destroy()
        self.secili_servis = None
        try:
            komut()
        except ServisHata as e:
            self.hata(str(e))
        except Exception as e:                              # noqa: BLE001
            self.hata(f"Beklenmeyen hata:\n{e}")

    def baslik(self, metin, aciklama=""):
        ttk.Label(self.icerik, text=metin, style="H1.TLabel").pack(anchor="w")
        if aciklama:
            ttk.Label(self.icerik, text=aciklama, foreground=MUTED).pack(
                anchor="w", pady=(2, 12))
        else:
            ttk.Frame(self.icerik, height=12).pack()

    def tablo(self, ana, sutunlar, genislikler, yukseklik=14):
        sarmal = ttk.Frame(ana)
        sarmal.pack(fill="both", expand=True)
        t = ttk.Treeview(sarmal, columns=sutunlar, show="headings",
                         height=yukseklik)
        for s, g in zip(sutunlar, genislikler):
            t.heading(s, text=s)
            t.column(s, width=g, anchor="w" if g > 90 else "center")
        kaydir = ttk.Scrollbar(sarmal, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=kaydir.set)
        t.pack(side="left", fill="both", expand=True)
        kaydir.pack(side="right", fill="y")
        t.tag_configure("kritik", foreground=NO)
        t.tag_configure("iyi", foreground=OK)
        t.tag_configure("bekle", foreground=WAIT)
        return t

    # ==================================================== PANEL
    def sayfa_panel(self):
        self.baslik("Panel", "Günlük iş listesi ve genel durum")
        o = srv.ozet_rapor()
        ust = ttk.Frame(self.icerik)
        ust.pack(fill="x", pady=(0, 14))
        kutular = [("Açık İş", o["servis_acik"], ACCENT),
                   ("Teslime Hazır", o["teslim_hazir"], OK),
                   ("Kritik Stok", o["kritik_stok"], NO),
                   ("Hatırlatma", o["hatirlatma"], WAIT),
                   ("Toplam Ciro", db.para(o["ciro"]), ACCENT2)]
        for ad, deger, renk in kutular:
            k = self.kart(ust)
            k.pack(side="left", padx=(0, 12), fill="both", expand=True)
            ttk.Label(k, text=ad.upper(), style="Soluk.TLabel").pack(anchor="w")
            tk.Label(k, text=str(deger), bg=PANEL, fg=renk,
                     font=("Segoe UI", 17, "bold")).pack(anchor="w")

        orta = ttk.Frame(self.icerik)
        orta.pack(fill="both", expand=True)

        sol = self.kart(orta)
        sol.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ttk.Label(sol, text="Durum Dağılımı", style="H2.TLabel").pack(anchor="w",
                                                                     pady=(0, 8))
        dagilim = srv.durum_dagilimi()
        en_yuksek = max(list(dagilim.values()) + [1])
        for durum, adet in dagilim.items():
            satir = tk.Frame(sol, bg=PANEL)
            satir.pack(fill="x", pady=2)
            tk.Label(satir, text=durum, bg=PANEL, fg=INK, width=18,
                     anchor="w", font=("Segoe UI", 9)).pack(side="left")
            cubuk = tk.Frame(satir, bg=ayar.DURUM_RENK.get(durum, ACCENT),
                             height=14, width=max(3, int(150 * adet / en_yuksek)))
            cubuk.pack(side="left")
            tk.Label(satir, text=f" {adet}", bg=PANEL, fg=MUTED).pack(side="left")

        sag = self.kart(orta)
        sag.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ttk.Label(sag, text="Kritik Stok Uyarısı", style="H2.TLabel").pack(
            anchor="w", pady=(0, 8))
        kritik = srv.kritik_stoklar()
        if not kritik:
            ttk.Label(sag, text="Kritik seviyede ürün yok.",
                      style="Soluk.TLabel").pack(anchor="w")
        for u in kritik[:10]:
            tk.Label(sag, text=f"• {u['ad']}  —  stok {u['stok']} / kritik "
                               f"{u['kritik_stok']}", bg=PANEL, fg=NO,
                     anchor="w").pack(fill="x")
        gecikme = srv.hatirlatma_gerekenler()
        if gecikme:
            ttk.Label(sag, text="\nTeslim Alınmayanlar", style="H2.TLabel").pack(
                anchor="w", pady=(10, 4))
            for s in gecikme[:6]:
                tk.Label(sag, text=f"• {s['kod']} · {s['ad_soyad']} "
                                   f"({s['gecikme_gun']} gün)", bg=PANEL,
                         fg=WAIT, anchor="w").pack(fill="x")

    # ==================================================== SERVİS KAYITLARI
    def sayfa_servisler(self):
        self.baslik("Servis Kayıtları",
                    "Kaydı seçip sağdaki panelden işlem yapabilirsiniz")
        ust = ttk.Frame(self.icerik)
        ust.pack(fill="x", pady=(0, 10))
        self.s_arama = ttk.Entry(ust, width=32)
        self.s_arama.pack(side="left")
        self.s_arama.bind("<KeyRelease>", lambda e: self.servis_doldur())
        self.s_durum = ttk.Combobox(ust, values=["Tümü"] + ayar.DURUMLAR,
                                    state="readonly", width=18)
        self.s_durum.current(0)
        self.s_durum.pack(side="left", padx=8)
        self.s_durum.bind("<<ComboboxSelected>>", lambda e: self.servis_doldur())
        self.s_arsiv = tk.BooleanVar(value=False)
        ttk.Checkbutton(ust, text="Arşiv", variable=self.s_arsiv,
                        command=self.servis_doldur).pack(side="left", padx=6)
        ttk.Button(ust, text="Yenile", style="Hayalet.TButton",
                   command=self.servis_doldur).pack(side="left", padx=6)

        govde = ttk.Frame(self.icerik)
        govde.pack(fill="both", expand=True)
        sol = ttk.Frame(govde)
        sol.pack(side="left", fill="both", expand=True)
        self.s_tablo = self.tablo(
            sol, ("Kod", "Müşteri", "Marka / Ürün", "Durum", "Tutar", "Giriş"),
            (80, 150, 210, 130, 100, 90), yukseklik=18)
        self.s_tablo.bind("<<TreeviewSelect>>", self.servis_secildi)

        self.s_detay = ttk.Frame(govde, width=400)
        self.s_detay.pack(side="left", fill="both", padx=(14, 0))
        self.s_detay.pack_propagate(False)
        self.servis_doldur()
        self._detay_bos()

    def servis_doldur(self, sec=None):
        durum = self.s_durum.get()
        kayitlar = srv.servis_listele(
            arama=self.s_arama.get().strip(),
            durum=None if durum == "Tümü" else durum,
            arsiv=1 if self.s_arsiv.get() else 0)
        self.s_tablo.delete(*self.s_tablo.get_children())
        for s in kayitlar:
            m = srv.maliyet(s["id"])
            etiket = ("iyi" if s["durum"] == "Teslime Hazır"
                      else "bekle" if s["durum"] == "Parça Bekleniyor" else "")
            self.s_tablo.insert("", "end", iid=str(s["id"]), tags=(etiket,),
                                values=(s["kod"], s["ad_soyad"],
                                        f"{s['marka']} {s['urun']}",
                                        s["durum"], db.para(m["toplam"]),
                                        s["giris_tarihi"]))
        if sec and self.s_tablo.exists(str(sec)):
            self.s_tablo.selection_set(str(sec))

    def servis_secildi(self, _e=None):
        sec = self.s_tablo.selection()
        if not sec:
            return
        self.secili_servis = int(sec[0])
        self.detay_goster()

    def _detay_bos(self):
        for w in self.s_detay.winfo_children():
            w.destroy()
        k = self.kart(self.s_detay)
        k.pack(fill="both", expand=True)
        ttk.Label(k, text="Kayıt Detayı", style="H2.TLabel").pack(anchor="w")
        ttk.Label(k, text="Soldan bir servis kaydı seçin.",
                  style="Soluk.TLabel").pack(anchor="w", pady=8)

    def detay_goster(self):
        s = srv.servis_bul(self.secili_servis)
        if not s:
            return self._detay_bos()
        for w in self.s_detay.winfo_children():
            w.destroy()
        m = srv.maliyet(s["id"])
        tuval = tk.Canvas(self.s_detay, bg=BG, highlightthickness=0)
        kaydir = ttk.Scrollbar(self.s_detay, orient="vertical",
                               command=tuval.yview)
        ic = tk.Frame(tuval, bg=BG)
        tuval.create_window((0, 0), window=ic, anchor="nw", width=352)
        tuval.configure(yscrollcommand=kaydir.set)
        tuval.pack(side="left", fill="both", expand=True)
        kaydir.pack(side="right", fill="y")
        ic.bind("<Configure>",
                lambda e: tuval.configure(scrollregion=tuval.bbox("all")))
        tuval.bind_all("<MouseWheel>",
                       lambda e: tuval.yview_scroll(int(-e.delta / 120), "units"))

        k = self.kart(ic)
        k.pack(fill="x")
        tk.Label(k, text=s["kod"], bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(k, text=s["durum"], bg=PANEL,
                 fg=ayar.DURUM_RENK.get(s["durum"], INK),
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        for etiket, deger in [
                ("Müşteri", s["ad_soyad"]), ("Telefon", s["telefon"] or "-"),
                ("Cihaz", f"{s['marka']} {s['urun']} {s['model'] or ''}"),
                ("Seri No", s["seri_no"] or "-"), ("Arıza", s["ariza"]),
                ("Çözüm", s["cozum"] or "-"), ("Garanti", s["garanti"]),
                ("Fatura", s["fatura_durumu"]),
                ("Kayıt Onayı", s["kayit_onay"]),
                ("Masraf Onayı", s["masraf_onay"]),
                ("Onay Kodu", s["onay_kodu"]),
                ("Giriş / Teslim", f"{s['giris_tarihi']} → "
                                   f"{s['teslim_tarihi'] or '-'}"),
                ("İşçilik", db.para(m["iscilik"])),
                ("Parça", db.para(m["parca"])),
                ("KDV", db.para(m["kdv"])),
                ("GENEL TOPLAM", db.para(m["toplam"]))]:
            satir = tk.Frame(k, bg=PANEL)
            satir.pack(fill="x", pady=1)
            tk.Label(satir, text=etiket, bg=PANEL, fg=MUTED, width=14,
                     anchor="w", font=("Segoe UI", 8)).pack(side="left")
            tk.Label(satir, text=str(deger), bg=PANEL, fg=INK, anchor="w",
                     wraplength=196, justify="left").pack(side="left", fill="x")

        parcalar = srv.parca_listele(s["id"])
        if parcalar:
            pk = self.kart(ic)
            pk.pack(fill="x", pady=(10, 0))
            ttk.Label(pk, text="Kullanılan Parçalar", style="H2.TLabel").pack(
                anchor="w")
            for p in parcalar:
                satir = tk.Frame(pk, bg=PANEL)
                satir.pack(fill="x", pady=1)
                tk.Label(satir, text=f"{p['ad']} x{p['adet']}", bg=PANEL,
                         fg=INK, anchor="w").pack(side="left")
                tk.Label(satir, text=db.para(p["adet"] * p["birim_fiyat"]),
                         bg=PANEL, fg=MUTED).pack(side="right")
                if self.yetkili("servis_duzenle"):
                    tk.Button(satir, text="sil", bg=PANEL, fg=NO, bd=0,
                              activebackground=PANEL, font=("Segoe UI", 8),
                              command=lambda pid=p["id"]: self._parca_sil(pid)
                              ).pack(side="right", padx=6)

        d = self.kart(ic)
        d.pack(fill="x", pady=(10, 20))
        ttk.Label(d, text="İşlemler", style="H2.TLabel").pack(anchor="w",
                                                              pady=(0, 6))
        duz = self.yetkili("servis_duzenle")
        butonlar = [
            ("▶  Durumu İlerlet", "Aksiyon.TButton", self._durum_ilerlet, duz),
            ("✎  Çözüm / Not Gir", "Hayalet.TButton", self._cozum_gir, duz),
            ("₺  İşçilik / Masraf Gir", "Hayalet.TButton", self._masraf_gir, duz),
            ("＋  Parça Ekle", "Hayalet.TButton", self._parca_ekle_pencere, duz),
            ("✔  Kayıt Kabul / Red", "Hayalet.TButton", self._kayit_karar, duz),
            ("🖨  Servis Kartı Yazdır", "Hayalet.TButton", self._fis_yazdir, True),
            ("💬  Durum Bilgisi Gönder", "Wa.TButton", self._wa_durum, True),
            ("💬  Masraf Onayı İste", "Wa.TButton", self._wa_masraf, duz),
            ("✅  Hazır + WhatsApp", "Wa.TButton", self._hazir_bildir, duz),
            ("🧾  Fatura Kes", "Hayalet.TButton", self._fatura_kes,
             self.yetkili("fatura_kes")),
            ("🗄  Arşivle / Geri Al", "Hayalet.TButton", self._arsivle, duz),
            ("🗑  Kaydı Sil", "Sil.TButton", self._servis_sil,
             self.yetkili("servis_sil")),
        ]
        for metin, stil, komut, izin in butonlar:
            if izin:
                ttk.Button(d, text=metin, style=stil, command=komut).pack(
                    fill="x", pady=2)

    # ---- detay işlemleri
    def _gerekli(self):
        if not self.secili_servis:
            self.uyari("Önce bir kayıt seçin.")
            return None
        return srv.servis_bul(self.secili_servis)

    def _yenile(self):
        self.servis_doldur(sec=self.secili_servis)
        self.detay_goster()

    def _durum_ilerlet(self):
        s = self._gerekli()
        if not s:
            return
        try:
            yeni = srv.durum_ilerlet(s["id"], self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        self._yenile()
        if yeni == "Teslime Hazır" and s["telefon"] and self.onay(
                "Durum 'Teslime Hazır' oldu. Müşteriye WhatsApp bildirimi "
                "gönderilsin mi?"):
            g = srv.servis_bul(s["id"])
            self.wa_gonder(g["telefon"],
                           msj.hazir_bildirimi(g, srv.maliyet(g["id"])["toplam"]))

    def _metin_sor(self, baslik, mevcut="", cok_satir=True):
        pen = tk.Toplevel(self)
        pen.title(baslik)
        pen.configure(bg=BG)
        pen.transient(self)
        pen.grab_set()
        ttk.Label(pen, text=baslik, style="H1.TLabel").pack(anchor="w",
                                                            padx=16, pady=12)
        kutu = tk.Text(pen, width=52, height=7 if cok_satir else 2, bg=PANEL2,
                       fg=INK, insertbackground=INK, relief="flat", wrap="word")
        kutu.insert("1.0", mevcut or "")
        kutu.pack(padx=16)
        sonuc = {}

        def kaydet():
            sonuc["metin"] = kutu.get("1.0", "end").strip()
            pen.destroy()
        alt = ttk.Frame(pen, padding=12)
        alt.pack(fill="x")
        ttk.Button(alt, text="Kaydet", style="Aksiyon.TButton",
                   command=kaydet).pack(side="right")
        ttk.Button(alt, text="Vazgeç", style="Hayalet.TButton",
                   command=pen.destroy).pack(side="right", padx=8)
        kutu.focus_set()
        self.wait_window(pen)
        return sonuc.get("metin")

    def _cozum_gir(self):
        s = self._gerekli()
        if not s:
            return
        cozum = self._metin_sor("Yapılan İşlem / Çözüm", s["cozum"])
        if cozum is None:
            return
        notu = self._metin_sor("Servis Notu (müşteriye gösterilir)",
                               s["not_servis"])
        srv.servis_guncelle(s["id"], self.kid(), cozum=cozum,
                            not_servis=notu or "")
        self._yenile()

    def _masraf_gir(self):
        s = self._gerekli()
        if not s:
            return
        pen = tk.Toplevel(self)
        pen.title("İşçilik / Masraf")
        pen.configure(bg=BG)
        pen.transient(self)
        pen.grab_set()
        k = self.kart(pen, padding=18)
        k.pack(padx=14, pady=14)
        ttk.Label(k, text="İşçilik / Tamir Ücreti (₺)",
                  style="Kart.TLabel").pack(anchor="w")
        giris = ttk.Entry(k, width=22)
        giris.insert(0, db.para(s["iscilik"] or s["masraf_tutar"], False))
        giris.pack(pady=(4, 10))
        ttk.Label(k, text="Parça tutarı otomatik eklenir, KDV %"
                          f"{int(ayar.KDV_ORANI * 100)} hesaplanır.",
                  style="Soluk.TLabel").pack(anchor="w")

        def kaydet():
            srv.servis_guncelle(s["id"], self.kid(), iscilik=giris.get(),
                                masraf_tutar=giris.get(), masraf_onay="Bekliyor")
            pen.destroy()
            self._yenile()
        ttk.Button(k, text="Kaydet", style="Aksiyon.TButton",
                   command=kaydet).pack(fill="x", pady=(12, 0))
        giris.focus_set()
        giris.bind("<Return>", lambda e: kaydet())

    def _parca_ekle_pencere(self):
        s = self._gerekli()
        if not s:
            return
        pen = tk.Toplevel(self)
        pen.title("Servise Parça Ekle")
        pen.configure(bg=BG)
        pen.transient(self)
        pen.grab_set()
        k = self.kart(pen, padding=18)
        k.pack(padx=14, pady=14)
        urunler = urn.listele()
        etiketler = [f"{u['kod']} · {u['ad']} (stok {u['stok']}) "
                     f"{db.para(u['satis_fiyat'])}" for u in urunler]
        ttk.Label(k, text="Parça / Ürün", style="Kart.TLabel").pack(anchor="w")
        kutu = ttk.Combobox(k, values=etiketler, state="readonly", width=50)
        kutu.pack(pady=(4, 10))
        ttk.Label(k, text="Adet", style="Kart.TLabel").pack(anchor="w")
        adet = ttk.Entry(k, width=10)
        adet.insert(0, "1")
        adet.pack(pady=(4, 10))

        def ekle():
            if not kutu.get():
                return self.uyari("Parça seçin.")
            kod = urunler[etiketler.index(kutu.get())]["kod"]
            try:
                srv.parca_ekle(s["id"], kod, int(db.sayi(adet.get(), 1)),
                               self.kid())
            except ServisHata as e:
                return self.hata(str(e))
            pen.destroy()
            self._yenile()
        ttk.Button(k, text="Parçayı Ekle", style="Aksiyon.TButton",
                   command=ekle).pack(fill="x")

    def _parca_sil(self, parca_id):
        if not self.onay("Parça kaydı silinsin mi? (stok geri eklenir)"):
            return
        try:
            srv.parca_sil(parca_id, self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        self._yenile()

    def _kayit_karar(self):
        s = self._gerekli()
        if not s:
            return
        karar = "Onaylandı" if self.onay(
            f"{s['kod']} kaydı KABUL edilsin mi?\n(Hayır = reddet)") \
            else "Reddedildi"
        srv.kayit_onay_ver(s["id"], karar, self.kid())
        self._yenile()
        if s["telefon"] and self.onay(f"Karar ({karar}) müşteriye WhatsApp'tan "
                                      "bildirilsin mi?"):
            self.wa_gonder(s["telefon"], msj.kayit_karari(s, karar))

    def _fis_yazdir(self):
        s = self._gerekli()
        if not s:
            return
        yol = fis.servis_karti(s, srv.parca_listele(s["id"]),
                              srv.maliyet(s["id"]))
        self.bilgi(f"Servis kartı oluşturuldu:\n{yol}")

    def _wa_durum(self):
        s = self._gerekli()
        if not s:
            return
        self.wa_gonder(s["telefon"], msj.durum_bilgisi(s))

    def _wa_masraf(self):
        s = self._gerekli()
        if not s:
            return
        m = srv.maliyet(s["id"])
        if not m["toplam"]:
            return self.uyari("Önce işçilik/parça girin.")
        self.wa_gonder(s["telefon"], msj.masraf_onayi(s, m["toplam"]))

    def _hazir_bildir(self):
        s = self._gerekli()
        if not s:
            return
        srv.durum_guncelle(s["id"], "Teslime Hazır", self.kid())
        self._yenile()
        g = srv.servis_bul(s["id"])
        self.wa_gonder(g["telefon"],
                       msj.hazir_bildirimi(g, srv.maliyet(g["id"])["toplam"]))

    def _fatura_kes(self):
        s = self._gerekli()
        if not s:
            return
        try:
            fid = srv.fatura_kes(s["id"], "Servis işlemi", self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        f = srv.fatura_bul(fid)
        self._yenile()
        if self.onay(f"{f['fatura_no']} kesildi ({db.para(f['toplam'])}).\n"
                     "Fatura fişi yazdırılsın mı?"):
            fis.fatura_fisi(f, s, srv.parca_listele(s["id"]))

    def _arsivle(self):
        s = self._gerekli()
        if not s:
            return
        srv.arsivle(s["id"], not s["arsiv"], self.kid())
        self.servis_doldur()
        self._detay_bos()

    def _servis_sil(self):
        s = self._gerekli()
        if not s or not self.onay(f"{s['kod']} kaydı kalıcı olarak silinsin mi?"):
            return
        try:
            srv.servis_sil(s["id"], self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        self.secili_servis = None
        self.servis_doldur()
        self._detay_bos()

    # ==================================================== YENİ KAYIT
    def sayfa_yeni_kayit(self):
        self.baslik("Yeni Servis Kaydı",
                    "Müşteri seçin ya da yeni müşteri olarak girin")
        sarmal = ttk.Frame(self.icerik)
        sarmal.pack(fill="both", expand=True)
        sol = self.kart(sarmal, padding=18)
        sol.pack(side="left", fill="both", expand=True, padx=(0, 8))
        sag = self.kart(sarmal, padding=18)
        sag.pack(side="left", fill="both", expand=True, padx=(8, 0))

        ttk.Label(sol, text="Müşteri", style="H2.TLabel").pack(anchor="w",
                                                               pady=(0, 8))
        self.yk_musteriler = srv.musteri_listele()
        self.yk_etiket = ["+ Yeni müşteri gir"] + [
            f"{m['ad_soyad']} · {m['telefon']}" for m in self.yk_musteriler]
        self.yk_secim = ttk.Combobox(sol, values=self.yk_etiket,
                                     state="readonly", width=38)
        self.yk_secim.current(0)
        self.yk_secim.pack(anchor="w", pady=(0, 10))

        self.yk_ad = self._alan(sol, "Ad Soyad")
        self.yk_tel = self._alan(sol, "Telefon (5321112233)")
        self.yk_adres = self._alan(sol, "Adres")

        ttk.Label(sag, text="Cihaz ve Arıza", style="H2.TLabel").pack(
            anchor="w", pady=(0, 8))
        ttk.Label(sag, text="Marka", style="Kart.TLabel").pack(anchor="w")
        self.yk_marka = ttk.Combobox(sag, values=ayar.MARKALAR,
                                     state="readonly", width=36)
        self.yk_marka.current(0)
        self.yk_marka.pack(anchor="w", pady=(2, 8))
        ttk.Label(sag, text="Ürün / Cihaz", style="Kart.TLabel").pack(anchor="w")
        self.yk_urun = ttk.Combobox(sag, values=ayar.modeller(ayar.MARKALAR[0]),
                                    width=36)
        self.yk_urun.pack(anchor="w", pady=(2, 8))
        self.yk_marka.bind("<<ComboboxSelected>>", lambda e: self.yk_urun.
                           configure(values=ayar.modeller(self.yk_marka.get())))
        self.yk_model = self._alan(sag, "Model / Seri No", genislik=36)
        ttk.Label(sag, text="Garanti", style="Kart.TLabel").pack(anchor="w")
        self.yk_garanti = ttk.Combobox(sag, values=ayar.GARANTI_SECENEKLERI,
                                       state="readonly", width=36)
        self.yk_garanti.current(len(ayar.GARANTI_SECENEKLERI) - 1)
        self.yk_garanti.pack(anchor="w", pady=(2, 8))
        ttk.Label(sag, text="Fatura Durumu", style="Kart.TLabel").pack(anchor="w")
        self.yk_fatura = ttk.Combobox(sag, values=ayar.FATURA_SECENEKLERI,
                                      state="readonly", width=36)
        self.yk_fatura.current(1)
        self.yk_fatura.pack(anchor="w", pady=(2, 8))
        self.yk_iscilik = self._alan(sag, "Tahmini İşçilik (₺)", genislik=36)
        ttk.Label(sag, text="Arıza / Şikayet", style="Kart.TLabel").pack(
            anchor="w")
        self.yk_ariza = tk.Text(sag, height=4, width=38, bg=PANEL2, fg=INK,
                                insertbackground=INK, relief="flat", wrap="word")
        self.yk_ariza.pack(anchor="w", pady=(2, 10))

        alt = ttk.Frame(self.icerik)
        alt.pack(fill="x", pady=(12, 0))
        self.yk_wa = tk.BooleanVar(value=True)
        ttk.Checkbutton(alt, text="Kayıt sonrası WhatsApp ile takip kodu gönder",
                        variable=self.yk_wa).pack(side="left")
        self.yk_fis = tk.BooleanVar(value=False)
        ttk.Checkbutton(alt, text="Servis kartını yazdır",
                        variable=self.yk_fis).pack(side="left", padx=12)
        ttk.Button(alt, text="Kaydı Oluştur", style="Aksiyon.TButton",
                   command=self._yeni_kayit_olustur).pack(side="right")

    def _alan(self, ana, etiket, genislik=38, gizli=False):
        ttk.Label(ana, text=etiket, style="Kart.TLabel").pack(anchor="w")
        e = ttk.Entry(ana, width=genislik, show="•" if gizli else "")
        e.pack(anchor="w", pady=(2, 8))
        return e

    def _yeni_kayit_olustur(self):
        try:
            i = self.yk_etiket.index(self.yk_secim.get())
            if i == 0:
                if not self.yk_ad.get().strip():
                    return self.uyari("Müşteri adı girin ya da listeden seçin.")
                mid = srv.musteri_bul_veya_ekle(
                    self.yk_ad.get(), self.yk_tel.get(), self.yk_adres.get(),
                    self.kid())
            else:
                mid = self.yk_musteriler[i - 1]["id"]
                if self.yk_tel.get().strip():
                    srv.musteri_guncelle(mid, telefon=self.yk_tel.get().strip())
            model = self.yk_model.get().strip()
            sid = srv.servis_ekle(
                mid, self.yk_marka.get(), self.yk_urun.get(), model, model,
                self.yk_ariza.get("1.0", "end").strip(),
                self.yk_garanti.get(), self.yk_fatura.get(),
                self.yk_iscilik.get() or 0, olusturan_id=self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        s = srv.servis_bul(sid)
        self.bilgi(f"Kayıt oluşturuldu.\n\nServis Kodu : {s['kod']}\n"
                   f"Onay Kodu   : {s['onay_kodu']}")
        if self.yk_wa.get() and s["telefon"]:
            self.wa_gonder(s["telefon"], msj.kayit_acildi(s))
        if self.yk_fis.get():
            fis.servis_karti(s, [], srv.maliyet(sid))
        self._sayfa_ac("🔧  Servis Kayıtları", self.sayfa_servisler)

    # ==================================================== ÜRÜN / STOK
    def sayfa_urunler(self):
        self.baslik("Ürün / Stok Yönetimi",
                    "Liste data/urunler.md dosyasıyla otomatik eşitlenir")
        ust = ttk.Frame(self.icerik)
        ust.pack(fill="x", pady=(0, 10))
        self.u_arama = ttk.Entry(ust, width=30)
        self.u_arama.pack(side="left")
        self.u_arama.bind("<KeyRelease>", lambda e: self.urun_doldur())
        self.u_kritik = tk.BooleanVar(value=False)
        ttk.Checkbutton(ust, text="Sadece kritik stok", variable=self.u_kritik,
                        command=self.urun_doldur).pack(side="left", padx=10)
        if self.yetkili("urun_yonet"):
            ttk.Button(ust, text="＋ Yeni Ürün", style="Aksiyon.TButton",
                       command=self._urun_ekle_pencere).pack(side="right")
            ttk.Button(ust, text="Stok Güncelle", style="Hayalet.TButton",
                       command=self._stok_guncelle).pack(side="right", padx=8)
            ttk.Button(ust, text="md'den İçe Aktar", style="Hayalet.TButton",
                       command=self._md_aktar).pack(side="right", padx=8)
        sutun = ["Kod", "Ürün", "Kategori", "Stok", "Kritik", "Satış", "Marj %",
                 "Garanti"]
        genislik = [110, 200, 110, 60, 60, 100, 70, 170]
        if self.yetkili("gelis_fiyat_gor"):
            sutun.insert(5, "Geliş")
            genislik.insert(5, 100)
        self.u_tablo = self.tablo(self.icerik, tuple(sutun), genislik,
                                  yukseklik=18)
        self.urun_doldur()

    def urun_doldur(self):
        self.u_tablo.delete(*self.u_tablo.get_children())
        for u in urn.listele(self.u_arama.get().strip(), self.u_kritik.get()):
            deger = [u["kod"], u["ad"], u["kategori"], u["stok"],
                     u["kritik_stok"]]
            if self.yetkili("gelis_fiyat_gor"):
                deger.append(db.para(u["gelis_fiyat"]))
            deger += [db.para(u["satis_fiyat"]), f"{urn.kar_marji(u):.0f}",
                      u["garanti_suresi"] or ""]
            etiket = "kritik" if u["stok"] <= u["kritik_stok"] else ""
            self.u_tablo.insert("", "end", iid=u["kod"], values=deger,
                                tags=(etiket,))

    def _secili_urun(self):
        sec = self.u_tablo.selection()
        if not sec:
            self.uyari("Listeden bir ürün seçin.")
            return None
        return urn.bul(sec[0])

    def _urun_ekle_pencere(self):
        pen = tk.Toplevel(self)
        pen.title("Yeni Ürün / Parça")
        pen.configure(bg=BG)
        pen.transient(self)
        pen.grab_set()
        k = self.kart(pen, padding=18)
        k.pack(padx=14, pady=14)
        kod = self._alan(k, "Ürün Kodu (boş = otomatik)", 34)
        ad = self._alan(k, "Ürün Adı", 34)
        ttk.Label(k, text="Kategori", style="Kart.TLabel").pack(anchor="w")
        kategori = ttk.Combobox(k, values=["Yedek Parça", "Satış Ürünü",
                                           "Sarf Malzeme"], state="readonly",
                                width=32)
        kategori.current(0)
        kategori.pack(anchor="w", pady=(2, 8))
        stok = self._alan(k, "Stok Adedi", 34)
        kritik = self._alan(k, "Kritik Stok Seviyesi", 34)
        gelis = self._alan(k, "Geliş Fiyatı (₺)", 34)
        satis = self._alan(k, "Satış Fiyatı (₺)", 34)
        garanti = self._alan(k, "Garanti Süresi", 34)
        garanti.insert(0, "2 yıl üretici garantisi")
        kritik.insert(0, "5")
        stok.insert(0, "0")

        def kaydet():
            try:
                srv.urun_ekle(kod.get(), ad.get(), stok.get(), kritik.get(),
                              gelis.get(), satis.get(), garanti.get(),
                              kategori.get(), self.kid())
            except ServisHata as e:
                return self.hata(str(e))
            pen.destroy()
            self.urun_doldur()
        ttk.Button(k, text="Kaydet", style="Aksiyon.TButton",
                   command=kaydet).pack(fill="x", pady=(8, 0))

    def _stok_guncelle(self):
        u = self._secili_urun()
        if not u:
            return
        pen = tk.Toplevel(self)
        pen.title("Stok Güncelle")
        pen.configure(bg=BG)
        pen.transient(self)
        pen.grab_set()
        k = self.kart(pen, padding=18)
        k.pack(padx=14, pady=14)
        ttk.Label(k, text=f"{u['ad']}  (mevcut stok: {u['stok']})",
                  style="H2.TLabel").pack(anchor="w", pady=(0, 10))
        yeni = self._alan(k, "Yeni Stok Adedi", 20)
        yeni.insert(0, str(u["stok"]))
        satis = self._alan(k, "Satış Fiyatı (₺)", 20)
        satis.insert(0, db.para(u["satis_fiyat"], False))

        def kaydet():
            srv.urun_guncelle(u["kod"], self.kid(), stok=yeni.get(),
                              satis_fiyat=satis.get())
            pen.destroy()
            self.urun_doldur()
        ttk.Button(k, text="Kaydet", style="Aksiyon.TButton",
                   command=kaydet).pack(fill="x")
        yeni.focus_set()
        yeni.bind("<Return>", lambda e: kaydet())

    def _md_aktar(self):
        sayac = urn.md_ice_aktar()
        urn.md_yaz()
        self.urun_doldur()
        self.bilgi(f"{sayac} satır urunler.md dosyasından içe aktarıldı.")

    # ==================================================== MÜŞTERİLER
    def sayfa_musteriler(self):
        self.baslik("Müşteriler", "Müşteri kartları ve servis geçmişi")
        ust = ttk.Frame(self.icerik)
        ust.pack(fill="x", pady=(0, 10))
        self.m_arama = ttk.Entry(ust, width=30)
        self.m_arama.pack(side="left")
        self.m_arama.bind("<KeyRelease>", lambda e: self.musteri_doldur())
        ttk.Button(ust, text="＋ Yeni Müşteri", style="Aksiyon.TButton",
                   command=self._musteri_ekle_pencere).pack(side="right")
        ttk.Button(ust, text="💬 WhatsApp", style="Wa.TButton",
                   command=self._musteri_wa).pack(side="right", padx=8)
        self.m_tablo = self.tablo(
            self.icerik, ("Ad Soyad", "Telefon", "Adres", "Servis", "Toplam"),
            (200, 130, 260, 70, 110), yukseklik=18)
        self.musteri_doldur()

    def musteri_doldur(self):
        self.m_tablo.delete(*self.m_tablo.get_children())
        for m in srv.musteri_listele(self.m_arama.get().strip()):
            kayitlar = srv.servis_listele(arsiv=None, musteri_id=m["id"])
            toplam = sum(srv.maliyet(s["id"])["toplam"] for s in kayitlar)
            self.m_tablo.insert("", "end", iid=str(m["id"]),
                                values=(m["ad_soyad"], m["telefon"],
                                        m["adres"], len(kayitlar),
                                        db.para(toplam)))

    def _musteri_ekle_pencere(self):
        pen = tk.Toplevel(self)
        pen.title("Yeni Müşteri")
        pen.configure(bg=BG)
        pen.transient(self)
        pen.grab_set()
        k = self.kart(pen, padding=18)
        k.pack(padx=14, pady=14)
        ad = self._alan(k, "Ad Soyad", 34)
        tel = self._alan(k, "Telefon", 34)
        adres = self._alan(k, "Adres", 34)
        eposta = self._alan(k, "E-posta", 34)

        def kaydet():
            try:
                srv.musteri_ekle(ad.get(), tel.get(), adres.get(), eposta.get(),
                                 olusturan_id=self.kid())
            except ServisHata as e:
                return self.hata(str(e))
            pen.destroy()
            self.musteri_doldur()
        ttk.Button(k, text="Kaydet", style="Aksiyon.TButton",
                   command=kaydet).pack(fill="x")

    def _musteri_wa(self):
        sec = self.m_tablo.selection()
        if not sec:
            return self.uyari("Müşteri seçin.")
        m = srv.musteri_bul(int(sec[0]))
        metin = self._metin_sor(f"{m['ad_soyad']} için mesaj",
                                f"Merhaba {m['ad_soyad']},\n\n{ayar.FIRMA}")
        if metin:
            self.wa_gonder(m["telefon"], metin)

    # ==================================================== TESLİM TAKİBİ
    def sayfa_teslim(self):
        self.baslik("Teslim Takibi",
                    f"{ayar.TESLIM_GUN} gün içinde alınmayanlar hatırlatılır")
        ust = ttk.Frame(self.icerik)
        ust.pack(fill="x", pady=(0, 10))
        ttk.Button(ust, text="💬 Hatırlatma Gönder", style="Wa.TButton",
                   command=self._hatirlatma_gonder).pack(side="left")
        ttk.Button(ust, text="✔ Teslim Edildi", style="Aksiyon.TButton",
                   command=self._teslim_et).pack(side="left", padx=8)
        ttk.Button(ust, text="Yenile", style="Hayalet.TButton",
                   command=self.teslim_doldur).pack(side="left", padx=8)
        self.t_tablo = self.tablo(
            self.icerik, ("Kod", "Müşteri", "Telefon", "Cihaz", "Teslim Tarihi",
                          "Gecikme", "Tutar"),
            (80, 160, 120, 200, 110, 80, 100), yukseklik=16)
        self.teslim_doldur()

    def teslim_doldur(self):
        self.t_tablo.delete(*self.t_tablo.get_children())
        gecikenler = {s["id"]: s.get("gecikme_gun")
                      for s in srv.hatirlatma_gerekenler()}
        for s in srv.teslim_bekleyenler():
            gun = db.gun_farki(s["teslim_tarihi"] or s["giris_tarihi"]) or 0
            etiket = "kritik" if s["id"] in gecikenler else (
                "bekle" if gun > 0 else "iyi")
            self.t_tablo.insert(
                "", "end", iid=str(s["id"]), tags=(etiket,),
                values=(s["kod"], s["ad_soyad"], s["telefon"],
                        f"{s['marka']} {s['urun']}", s["teslim_tarihi"] or "-",
                        f"{gun} gün" if gun > 0 else "-",
                        db.para(srv.maliyet(s["id"])["toplam"])))

    def _teslim_secili(self):
        sec = self.t_tablo.selection()
        if not sec:
            self.uyari("Listeden kayıt seçin.")
            return None
        return srv.servis_bul(int(sec[0]))

    def _hatirlatma_gonder(self):
        s = self._teslim_secili()
        if not s:
            return
        s["gecikme_gun"] = db.gun_farki(s["teslim_tarihi"] or s["giris_tarihi"])
        if self.wa_gonder(s["telefon"], msj.hatirlatma(s)):
            srv.hatirlatma_isaretle(s["id"], self.kid())
            self.teslim_doldur()

    def _teslim_et(self):
        s = self._teslim_secili()
        if not s:
            return
        srv.durum_guncelle(s["id"], "Teslim Edildi", self.kid())
        self.teslim_doldur()
        self.bilgi(f"{s['kod']} teslim edildi olarak işaretlendi.")

    # ==================================================== FATURALAR
    def sayfa_faturalar(self):
        self.baslik("Faturalar", f"KDV %{int(ayar.KDV_ORANI * 100)} dahil")
        ust = ttk.Frame(self.icerik)
        ust.pack(fill="x", pady=(0, 10))
        ttk.Button(ust, text="🖨 Fiş Yazdır", style="Hayalet.TButton",
                   command=self._fatura_fis).pack(side="left")
        ttk.Button(ust, text="✔ Ödendi", style="Aksiyon.TButton",
                   command=lambda: self._fatura_durum("Ödendi")).pack(
            side="left", padx=8)
        ttk.Button(ust, text="⨯ İptal", style="Sil.TButton",
                   command=lambda: self._fatura_durum("İptal")).pack(side="left")
        if self.yetkili("fatura_revize"):
            ttk.Button(ust, text="✎ Revize Et", style="Hayalet.TButton",
                       command=self._fatura_revize).pack(side="left", padx=8)
        ttk.Button(ust, text="💬 Müşteriye Gönder", style="Wa.TButton",
                   command=self._fatura_wa).pack(side="right")
        self.f_tablo = self.tablo(
            self.icerik, ("Fatura No", "Servis", "Müşteri", "Ara Toplam", "KDV",
                          "Toplam", "Durum", "Rev.", "Tarih"),
            (130, 80, 160, 110, 90, 110, 90, 50, 130), yukseklik=18)
        self.fatura_doldur()

    def fatura_doldur(self):
        self.f_tablo.delete(*self.f_tablo.get_children())
        for f in srv.fatura_listele():
            etiket = ("iyi" if f["durum"] == "Ödendi"
                      else "kritik" if f["durum"] == "İptal" else "bekle")
            self.f_tablo.insert(
                "", "end", iid=str(f["id"]), tags=(etiket,),
                values=(f["fatura_no"], f["servis_kod"] or "-",
                        f["ad_soyad"] or "-", db.para(f["ara_toplam"]),
                        db.para(f["kdv"]), db.para(f["toplam"]), f["durum"],
                        f["revizyon"], (f["tarih"] or "")[:16].replace("T", " ")))

    def _fatura_secili(self):
        sec = self.f_tablo.selection()
        if not sec:
            self.uyari("Fatura seçin.")
            return None
        return srv.fatura_bul(int(sec[0]))

    def _fatura_durum(self, durum):
        f = self._fatura_secili()
        if not f:
            return
        try:
            srv.fatura_durum(f["id"], durum, self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        self.fatura_doldur()

    def _fatura_revize(self):
        f = self._fatura_secili()
        if not f:
            return
        yeni = self._metin_sor(f"{f['fatura_no']} yeni toplam (KDV dahil ₺)",
                               db.para(f["toplam"], False), cok_satir=False)
        if not yeni:
            return
        try:
            srv.fatura_revize(f["id"], yeni, "Revize edildi", self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        self.fatura_doldur()

    def _fatura_fis(self):
        f = self._fatura_secili()
        if not f:
            return
        s = srv.servis_bul(f["servis_id"]) if f["servis_id"] else None
        parcalar = srv.parca_listele(f["servis_id"]) if f["servis_id"] else []
        yol = fis.fatura_fisi(f, s, parcalar)
        self.bilgi(f"Fatura fişi oluşturuldu:\n{yol}")

    def _fatura_wa(self):
        f = self._fatura_secili()
        if not f:
            return
        self.wa_gonder(f["telefon"], msj.fatura_bilgisi(f))

    # ==================================================== SİPARİŞ / SATIŞ
    def sayfa_siparis(self):
        self.baslik("Sipariş / Satış", "Sepete ürün ekleyip WhatsApp ile bildir")
        sarmal = ttk.Frame(self.icerik)
        sarmal.pack(fill="both", expand=True)
        sol = self.kart(sarmal, padding=16)
        sol.pack(side="left", fill="both", expand=True, padx=(0, 8))
        sag = self.kart(sarmal, padding=16)
        sag.pack(side="left", fill="both", expand=True, padx=(8, 0))

        ttk.Label(sol, text="Ürün Kataloğu", style="H2.TLabel").pack(anchor="w")
        self.sp_urunler = urn.listele()
        self.sp_etiket = [f"{u['ad']} · {db.para(u['satis_fiyat'])} "
                          f"(stok {u['stok']})" for u in self.sp_urunler]
        self.sp_secim = ttk.Combobox(sol, values=self.sp_etiket,
                                     state="readonly", width=42)
        self.sp_secim.pack(anchor="w", pady=8)
        satir = ttk.Frame(sol, style="Kart.TFrame")
        satir.pack(anchor="w", pady=4)
        ttk.Label(satir, text="Adet", style="Kart.TLabel").pack(side="left")
        self.sp_adet = ttk.Entry(satir, width=6)
        self.sp_adet.insert(0, "1")
        self.sp_adet.pack(side="left", padx=8)
        ttk.Button(satir, text="Sepete Ekle", style="Aksiyon.TButton",
                   command=self._sepete_ekle).pack(side="left")
        ttk.Label(sol, text="Katalogda olmayan ürün", style="Soluk.TLabel").pack(
            anchor="w", pady=(14, 2))
        self.sp_ad = self._alan(sol, "Ürün Adı", 34)
        self.sp_fiyat = self._alan(sol, "Birim Fiyat (₺)", 34)
        ttk.Button(sol, text="Elle Ekle", style="Hayalet.TButton",
                   command=self._elle_ekle).pack(anchor="w")

        ttk.Label(sag, text="Sepet", style="H2.TLabel").pack(anchor="w")
        self.sp_liste = tk.Listbox(sag, height=10, bg=PANEL2, fg=INK,
                                   relief="flat", highlightthickness=0,
                                   selectbackground=ACCENT2)
        self.sp_liste.pack(fill="x", pady=8)
        self.sp_toplam = ttk.Label(sag, text="Toplam: 0,00 ₺",
                                   style="Deger.TLabel")
        self.sp_toplam.pack(anchor="w")
        ttk.Button(sag, text="Seçili Satırı Çıkar", style="Hayalet.TButton",
                   command=self._sepetten_cikar).pack(anchor="w", pady=6)
        self.sp_musteri = self._alan(sag, "Müşteri Adı", 34)
        self.sp_tel = self._alan(sag, "Telefon", 34)
        self.sp_stok = tk.BooleanVar(value=True)
        ttk.Checkbutton(sag, text="Stoktan düş", variable=self.sp_stok).pack(
            anchor="w")
        ttk.Button(sag, text="Siparişi Oluştur + WhatsApp", style="Wa.TButton",
                   command=self._siparis_olustur).pack(fill="x", pady=(10, 0))
        self.sepet = []
        self._sepet_yenile()

    def _sepete_ekle(self):
        if not self.sp_secim.get():
            return self.uyari("Ürün seçin.")
        u = self.sp_urunler[self.sp_etiket.index(self.sp_secim.get())]
        self.sepet.append({"urun_kod": u["kod"], "ad": u["ad"],
                           "adet": max(1, int(db.sayi(self.sp_adet.get(), 1))),
                           "birim_fiyat": u["satis_fiyat"]})
        self._sepet_yenile()

    def _elle_ekle(self):
        if not self.sp_ad.get().strip():
            return self.uyari("Ürün adı girin.")
        self.sepet.append({"urun_kod": "", "ad": self.sp_ad.get().strip(),
                           "adet": max(1, int(db.sayi(self.sp_adet.get(), 1))),
                           "birim_fiyat": db.kurus(self.sp_fiyat.get())})
        self.sp_ad.delete(0, "end")
        self.sp_fiyat.delete(0, "end")
        self._sepet_yenile()

    def _sepetten_cikar(self):
        sec = self.sp_liste.curselection()
        if sec:
            self.sepet.pop(sec[0])
            self._sepet_yenile()

    def _sepet_yenile(self):
        self.sp_liste.delete(0, "end")
        toplam = 0
        for s in self.sepet:
            tutar = s["adet"] * s["birim_fiyat"]
            toplam += tutar
            self.sp_liste.insert("end", f"{s['ad']} x{s['adet']} — "
                                        f"{db.para(tutar)}")
        self.sp_toplam.configure(text=f"Toplam: {db.para(toplam)}")

    def _siparis_olustur(self):
        if not self.sepet:
            return self.uyari("Sepet boş.")
        if not self.sp_musteri.get().strip():
            return self.uyari("Müşteri adı girin.")
        try:
            sip = srv.siparis_olustur(
                self.sepet, self.sp_musteri.get().strip(), self.sp_tel.get(),
                kullanici_id=self.kid(), stok_dus=self.sp_stok.get())
        except ServisHata as e:
            return self.hata(str(e))
        self.bilgi(f"Sipariş kaydedildi.\nFatura No: {sip['fatura_no']}\n"
                   f"Toplam: {db.para(sip['toplam'])}")
        self.wa_gonder(self.sp_tel.get(),
                       msj.siparis(self.sp_musteri.get().strip(), self.sepet,
                                   sip["fatura_no"]))
        self.sepet = []
        self._sepet_yenile()

    # ==================================================== RAPOR
    def sayfa_rapor(self):
        self.baslik("Yönetim Raporu", "Özet göstergeler, aktarma ve yedekleme")
        o = srv.ozet_rapor()
        izgara = ttk.Frame(self.icerik)
        izgara.pack(fill="x", pady=(0, 14))
        kutular = [("Toplam Servis", o["servis_toplam"]),
                   ("Açık İş", o["servis_acik"]),
                   ("Müşteri", o["musteri"]),
                   ("Ürün Çeşidi", o["urun"]),
                   ("Stok Değeri", db.para(o["stok_degeri"])),
                   ("Fatura Adedi", o["fatura_adet"]),
                   ("Ciro", db.para(o["ciro"])),
                   ("Tahsil Edilen", db.para(o["tahsil"])),
                   ("Satış / Sipariş", db.para(o["siparis_ciro"]))]
        for i, (ad, deger) in enumerate(kutular):
            k = self.kart(izgara)
            k.grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)
            izgara.columnconfigure(i % 3, weight=1)
            ttk.Label(k, text=ad.upper(), style="Soluk.TLabel").pack(anchor="w")
            ttk.Label(k, text=str(deger), style="Deger.TLabel").pack(anchor="w")

        alt = ttk.Frame(self.icerik)
        alt.pack(fill="x", pady=10)
        ttk.Button(alt, text="🖨 HTML Rapor", style="Aksiyon.TButton",
                   command=self._rapor_html).pack(side="left")
        ttk.Button(alt, text="📤 CSV Aktar (tümü)", style="Hayalet.TButton",
                   command=self._csv_aktar).pack(side="left", padx=8)
        ttk.Button(alt, text="💾 Yedek Al", style="Hayalet.TButton",
                   command=self._yedek).pack(side="left")

        k = self.kart(self.icerik)
        k.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(k, text="Son İşlem Kayıtları", style="H2.TLabel").pack(
            anchor="w", pady=(0, 6))
        tablo = self.tablo(k, ("Tarih", "Kullanıcı", "Eylem", "Detay"),
                           (140, 140, 130, 400), yukseklik=9)
        for l in srv.son_loglar(120):
            tablo.insert("", "end", values=(
                (l["tarih"] or "")[:16].replace("T", " "),
                l["ad_soyad"] or "-", l["eylem"], l["detay"]))

    def _rapor_html(self):
        yol = fis.rapor_sayfasi(srv.ozet_rapor(), srv.durum_dagilimi(),
                                srv.marka_dagilimi(), srv.kritik_stoklar(),
                                srv.en_cok_kullanilan_parcalar())
        self.bilgi(f"Rapor oluşturuldu:\n{yol}")

    def _csv_aktar(self):
        try:
            sonuc = aktarim.tumunu_aktar()
        except OSError as e:
            return self.hata(f"Aktarma başarısız: {e}")
        self.bilgi("CSV dosyaları oluşturuldu:\n\n" +
                   "\n".join(f"• {os.path.basename(v)}" for v in sonuc.values())
                   + f"\n\nKlasör: {os.path.dirname(list(sonuc.values())[0])}")

    def _yedek(self):
        try:
            yol = db.yedek_al()
        except OSError as e:
            return self.hata(f"Yedek alınamadı: {e}")
        self.bilgi(f"Yedek alındı:\n{yol}")

    # ==================================================== KULLANICILAR
    def sayfa_kullanicilar(self):
        self.baslik("Kullanıcı Yönetimi", "Yönetici · Personel · Müşteri")
        ust = ttk.Frame(self.icerik)
        ust.pack(fill="x", pady=(0, 10))
        ttk.Button(ust, text="＋ Yeni Kullanıcı", style="Aksiyon.TButton",
                   command=self._kullanici_ekle_pencere).pack(side="left")
        ttk.Button(ust, text="⏸ Aktif / Pasif", style="Hayalet.TButton",
                   command=self._kullanici_durum).pack(side="left", padx=8)
        ttk.Button(ust, text="🔑 Şifre Sıfırla", style="Hayalet.TButton",
                   command=self._kullanici_sifre).pack(side="left")
        ttk.Button(ust, text="🗑 Sil", style="Sil.TButton",
                   command=self._kullanici_sil).pack(side="right")
        self.k_tablo = self.tablo(
            self.icerik, ("Kullanıcı Adı", "Ad Soyad", "Rol", "Telefon",
                          "Durum", "Kayıt"),
            (140, 200, 110, 130, 90, 140), yukseklik=16)
        self.kullanici_doldur()

    def kullanici_doldur(self):
        self.k_tablo.delete(*self.k_tablo.get_children())
        for k in srv.kullanici_listele():
            self.k_tablo.insert(
                "", "end", iid=str(k["id"]),
                tags=("iyi" if k["aktif"] else "kritik",),
                values=(k["kullanici_adi"], k["ad_soyad"],
                        ayar.ROL_ADI.get(k["rol"], k["rol"]), k["telefon"] or "",
                        "Aktif" if k["aktif"] else "Kapalı",
                        (k["olusturma"] or "")[:16].replace("T", " ")))

    def _kullanici_secili(self):
        sec = self.k_tablo.selection()
        if not sec:
            self.uyari("Kullanıcı seçin.")
            return None
        return db.tek("SELECT * FROM kullanicilar WHERE id=?", (int(sec[0]),))

    def _kullanici_ekle_pencere(self):
        pen = tk.Toplevel(self)
        pen.title("Yeni Kullanıcı")
        pen.configure(bg=BG)
        pen.transient(self)
        pen.grab_set()
        k = self.kart(pen, padding=18)
        k.pack(padx=14, pady=14)
        kadi = self._alan(k, "Kullanıcı Adı", 32)
        ad = self._alan(k, "Ad Soyad", 32)
        tel = self._alan(k, "Telefon", 32)
        sifre = self._alan(k, "Şifre", 32, gizli=True)
        ttk.Label(k, text="Rol", style="Kart.TLabel").pack(anchor="w")
        rol = ttk.Combobox(k, values=[ayar.ROL_ADI[r] for r in ayar.ROLLER],
                           state="readonly", width=30)
        rol.current(1)
        rol.pack(anchor="w", pady=(2, 10))
        musteri_bagla = tk.BooleanVar(value=True)
        ttk.Checkbutton(k, text="Müşteri rolündeyse müşteri kartı da oluştur",
                        variable=musteri_bagla).pack(anchor="w")

        def kaydet():
            kod = ayar.ROLLER[[ayar.ROL_ADI[r] for r in ayar.ROLLER].index(
                rol.get())]
            try:
                uid = srv.kullanici_ekle(kadi.get(), ad.get(), sifre.get(), kod,
                                         tel.get(), olusturan_id=self.kid())
                if kod == ayar.ROL_MUSTERI and musteri_bagla.get():
                    srv.musteri_ekle(ad.get(), tel.get(), kullanici_id=uid,
                                     olusturan_id=self.kid())
            except ServisHata as e:
                return self.hata(str(e))
            pen.destroy()
            self.kullanici_doldur()
        ttk.Button(k, text="Kaydet", style="Aksiyon.TButton",
                   command=kaydet).pack(fill="x", pady=(10, 0))

    def _kullanici_durum(self):
        k = self._kullanici_secili()
        if not k:
            return
        try:
            srv.kullanici_durum(k["id"], not k["aktif"], self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        self.kullanici_doldur()

    def _kullanici_sil(self):
        k = self._kullanici_secili()
        if not k or not self.onay(f"{k['kullanici_adi']} silinsin mi?"):
            return
        try:
            srv.kullanici_sil(k["id"], self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        self.kullanici_doldur()

    def _kullanici_sifre(self):
        k = self._kullanici_secili()
        if not k:
            return
        yeni = self._metin_sor(f"{k['kullanici_adi']} için yeni şifre",
                               cok_satir=False)
        if not yeni:
            return
        try:
            srv.sifre_degistir(k["id"], yeni)
        except ServisHata as e:
            return self.hata(str(e))
        self.bilgi("Şifre güncellendi.")

    def sifre_penceresi(self):
        pen = tk.Toplevel(self)
        pen.title("Şifre Değiştir")
        pen.configure(bg=BG)
        pen.transient(self)
        pen.grab_set()
        k = self.kart(pen, padding=18)
        k.pack(padx=14, pady=14)
        eski = self._alan(k, "Mevcut Şifre", 28, gizli=True)
        yeni = self._alan(k, "Yeni Şifre", 28, gizli=True)
        yeni2 = self._alan(k, "Yeni Şifre (tekrar)", 28, gizli=True)

        def kaydet():
            if yeni.get() != yeni2.get():
                return self.uyari("Yeni şifreler aynı değil.")
            try:
                srv.sifre_degistir(self.kid(), yeni.get(), eski.get())
            except ServisHata as e:
                return self.hata(str(e))
            pen.destroy()
            self.bilgi("Şifreniz güncellendi.")
        ttk.Button(k, text="Kaydet", style="Aksiyon.TButton",
                   command=kaydet).pack(fill="x")

    # ==================================================== MÜŞTERİ PANELİ
    def _musteri_kayitlari(self):
        m = srv.musteri_kullanicidan(self.kid())
        if not m:
            return []
        return srv.servis_listele(arsiv=None, musteri_id=m["id"])

    def sayfa_kayitlarim(self):
        self.baslik("Kayıtlarım", "Servise bıraktığınız ürünlerin durumu")
        kayitlar = self._musteri_kayitlari()
        if not kayitlar:
            k = self.kart(self.icerik)
            k.pack(fill="x")
            ttk.Label(k, text="Adınıza kayıtlı servis kaydı bulunamadı.",
                      style="Kart.TLabel").pack(anchor="w")
            ttk.Label(k, text="Servis kodunuz varsa 'Kod Sorgula' "
                              "sayfasından bakabilirsiniz.",
                      style="Soluk.TLabel").pack(anchor="w", pady=4)
            return
        tuval = tk.Canvas(self.icerik, bg=BG, highlightthickness=0)
        kaydir = ttk.Scrollbar(self.icerik, orient="vertical",
                               command=tuval.yview)
        ic = tk.Frame(tuval, bg=BG)
        tuval.create_window((0, 0), window=ic, anchor="nw", width=900)
        tuval.configure(yscrollcommand=kaydir.set)
        tuval.pack(side="left", fill="both", expand=True)
        kaydir.pack(side="right", fill="y")
        ic.bind("<Configure>",
                lambda e: tuval.configure(scrollregion=tuval.bbox("all")))
        for s in kayitlar:
            self._musteri_kart(ic, s)

    def _musteri_kart(self, ana, s):
        m = srv.maliyet(s["id"])
        k = self.kart(ana, padding=16)
        k.pack(fill="x", pady=6)
        ust = tk.Frame(k, bg=PANEL)
        ust.pack(fill="x")
        tk.Label(ust, text=f"{s['marka']} {s['urun']}", bg=PANEL, fg=INK,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Label(ust, text=s["durum"], bg=PANEL,
                 fg=ayar.DURUM_RENK.get(s["durum"], INK),
                 font=("Segoe UI", 10, "bold")).pack(side="right")
        tk.Label(k, text=f"Servis Kodu: {s['kod']}   ·   Giriş: "
                         f"{s['giris_tarihi']}   ·   Tahmini Teslim: "
                         f"{s['teslim_tarihi'] or '-'}",
                 bg=PANEL, fg=MUTED, anchor="w").pack(fill="x", pady=(2, 6))
        tk.Label(k, text=f"Arıza: {s['ariza']}", bg=PANEL, fg=INK, anchor="w",
                 wraplength=820, justify="left").pack(fill="x")
        if s["cozum"]:
            tk.Label(k, text=f"Yapılan işlem: {s['cozum']}", bg=PANEL, fg=OK,
                     anchor="w", wraplength=820, justify="left").pack(fill="x")
        if s["not_servis"]:
            tk.Label(k, text=f"Servis notu: {s['not_servis']}", bg=PANEL,
                     fg=MUTED, anchor="w", wraplength=820,
                     justify="left").pack(fill="x")
        tk.Label(k, text=f"Tutar: {db.para(m['toplam'])} (KDV dahil)   ·   "
                         f"Masraf onayı: {s['masraf_onay']}", bg=PANEL,
                 fg=ACCENT, anchor="w").pack(fill="x", pady=(6, 4))
        self._ilerleme(k, s["durum"])

    def _ilerleme(self, ana, aktif):
        satir = tk.Frame(ana, bg=PANEL)
        satir.pack(fill="x", pady=(6, 0))
        try:
            aktif_i = ayar.DURUMLAR.index(aktif)
        except ValueError:
            aktif_i = 0
        for i, d in enumerate(ayar.DURUMLAR):
            renk = ayar.DURUM_RENK[d] if i <= aktif_i else LINE
            hucre = tk.Frame(satir, bg=PANEL)
            hucre.pack(side="left", expand=True, fill="x")
            tk.Frame(hucre, bg=renk, height=6).pack(fill="x")
            tk.Label(hucre, text=d, bg=PANEL,
                     fg=INK if i <= aktif_i else MUTED,
                     font=("Segoe UI", 7)).pack()

    def sayfa_masraf_onay(self):
        self.baslik("Masraf Onayı", "Onarım bedelini onaylayın ya da reddedin")
        bekleyen = [s for s in self._musteri_kayitlari()
                    if s["masraf_onay"] == "Bekliyor" and
                    (s["masraf_tutar"] or s["iscilik"])]
        if not bekleyen:
            k = self.kart(self.icerik)
            k.pack(fill="x")
            ttk.Label(k, text="Onayınızı bekleyen masraf yok.",
                      style="Kart.TLabel").pack(anchor="w")
            return
        for s in bekleyen:
            m = srv.maliyet(s["id"])
            k = self.kart(self.icerik, padding=16)
            k.pack(fill="x", pady=6)
            tk.Label(k, text=f"{s['marka']} {s['urun']} · {s['kod']}", bg=PANEL,
                     fg=INK, font=("Segoe UI", 12, "bold")).pack(anchor="w")
            tk.Label(k, text=f"Tespit: {s['cozum'] or s['ariza']}", bg=PANEL,
                     fg=MUTED, anchor="w", wraplength=760,
                     justify="left").pack(fill="x", pady=4)
            tk.Label(k, text=f"İşçilik {db.para(m['iscilik'])} + Parça "
                             f"{db.para(m['parca'])} + KDV {db.para(m['kdv'])}"
                             f"  =  {db.para(m['toplam'])}", bg=PANEL,
                     fg=ACCENT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
            dugme = tk.Frame(k, bg=PANEL)
            dugme.pack(anchor="w", pady=(10, 0))
            ttk.Button(dugme, text="✔ Onaylıyorum", style="Aksiyon.TButton",
                       command=lambda sid=s["id"]: self._masraf_karar(
                           sid, "Onaylandı")).pack(side="left")
            ttk.Button(dugme, text="✗ Reddediyorum", style="Sil.TButton",
                       command=lambda sid=s["id"]: self._masraf_karar(
                           sid, "Reddedildi")).pack(side="left", padx=8)

    def _masraf_karar(self, servis_id, karar):
        try:
            srv.masraf_onayla(servis_id, karar, self.kid())
        except ServisHata as e:
            return self.hata(str(e))
        self.bilgi(f"Kararınız kaydedildi: {karar}")
        self._sayfa_ac("💰  Masraf Onayı", self.sayfa_masraf_onay)

    def sayfa_kod_sorgu(self):
        self.baslik("Kod Sorgula", "Servis kodu + onay kodu ile durum sorgusu")
        k = self.kart(self.icerik, padding=18)
        k.pack(fill="x")
        kod = self._alan(k, "Servis Kodu (örn: 2609-4471)", 28)
        onay = self._alan(k, "Onay Kodu (6 hane)", 28)
        sonuc = ttk.Frame(self.icerik)
        sonuc.pack(fill="both", expand=True, pady=10)

        def sorgula():
            for w in sonuc.winfo_children():
                w.destroy()
            try:
                s = srv.kod_dogrula(kod.get(), onay.get())
            except ServisHata as e:
                return self.hata(str(e))
            self._musteri_kart(sonuc, s)
        ttk.Button(k, text="Sorgula", style="Aksiyon.TButton",
                   command=sorgula).pack(fill="x")
        onay.bind("<Return>", lambda e: sorgula())


def firma_sihirbazi():
    """İlk açılışta bir kez çalışır.

    Döndürdüğü değer:
        None  -> kullanıcı pencereyi kapattı, uygulama açılmamalı
        True  -> bilgiler kaydedildi, örnek kayıtlarla başlanacak
        False -> bilgiler kaydedildi, boş veritabanıyla başlanacak
    """
    kok = tk.Tk()
    kok.title("Servis Takip PRO · İlk Kurulum")
    kok.configure(bg=BG)
    kok.resizable(False, False)

    s = ttk.Style(kok)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure("S.TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
    s.configure("SB.TLabel", background=BG, foreground=INK,
                font=("Segoe UI", 16, "bold"))
    s.configure("SM.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
    s.configure("S.TEntry", fieldbackground=PANEL2, foreground=INK)

    cer = tk.Frame(kok, bg=BG, padx=28, pady=22)
    cer.pack(fill="both", expand=True)

    ttk.Label(cer, text="Hoş geldiniz", style="SB.TLabel").pack(anchor="w")
    ttk.Label(cer, style="SM.TLabel", justify="left",
              text="Fişlerde, raporlarda ve WhatsApp mesajlarında görünecek\n"
                   "işletme bilgilerinizi girin. Daha sonra data/firma.json\n"
                   "dosyasından değiştirebilirsiniz."
              ).pack(anchor="w", pady=(4, 12))

    girisler = {}
    for anahtar, etiket, ipucu in (
            ("firma", "İşletme adı *", "Örn: Yıldız Teknik Servis"),
            ("alt_baslik", "Alt başlık", "Örn: Beyaz Eşya Yetkili Servisi"),
            ("telefon", "Telefon", "Örn: 0264 000 00 00"),
            ("adres", "Adres", "Örn: Cumhuriyet Mah. Akyazı / Sakarya"),
            ("fatura_onek", "Fatura ön eki", "Örn: YTS  ->  YTS-2026-00001")):
        ttk.Label(cer, text=etiket, style="S.TLabel").pack(anchor="w", pady=(6, 1))
        e = ttk.Entry(cer, style="S.TEntry", width=46)
        e.pack(anchor="w", ipady=3)
        ttk.Label(cer, text=ipucu, style="SM.TLabel").pack(anchor="w")
        girisler[anahtar] = e
    girisler["fatura_onek"].insert(0, "SRV")

    ornek = tk.BooleanVar(value=False)
    tk.Checkbutton(cer, variable=ornek,
                   text="  Örnek kayıtlarla başlat (tanıtım / demo için)",
                   bg=BG, fg=INK, selectcolor=PANEL2, activebackground=BG,
                   activeforeground=INK, bd=0, highlightthickness=0,
                   font=("Segoe UI", 10), cursor="hand2").pack(anchor="w",
                                                               pady=(14, 0))
    ttk.Label(cer, style="SM.TLabel", justify="left",
              text="İşaretlemezseniz sistem bomboş açılır — gerçek kullanım "
                   "için bunu seçin.").pack(anchor="w", pady=(1, 0))

    uyari = ttk.Label(cer, text="", style="SM.TLabel", foreground=NO)
    uyari.pack(anchor="w", pady=(8, 0))

    sonuc = {"deger": None}

    def kaydet(_=None):
        ad = girisler["firma"].get().strip()
        if len(ad) < 2:
            uyari.config(text="İşletme adı boş bırakılamaz.")
            girisler["firma"].focus_set()
            return
        firma_kaydet(ad, girisler["alt_baslik"].get(), girisler["telefon"].get(),
                     girisler["adres"].get(), girisler["fatura_onek"].get())
        sonuc["deger"] = bool(ornek.get())
        kok.destroy()

    tk.Button(cer, text="Kaydet ve Başla", command=kaydet,
              bg=ACCENT, fg="#ffffff", relief="flat", cursor="hand2",
              font=("Segoe UI", 10, "bold"), padx=18, pady=7,
              activebackground=ACCENT).pack(anchor="w", pady=(12, 0))

    kok.bind("<Return>", kaydet)
    girisler["firma"].focus_set()
    kok.update_idletasks()
    x = max(0, (kok.winfo_screenwidth() - kok.winfo_width()) // 2)
    y = max(0, (kok.winfo_screenheight() - kok.winfo_height()) // 3)
    kok.geometry(f"+{x}+{y}")
    kok.mainloop()
    return sonuc["deger"]


def main():
    firma_yukle()
    if firma_tanimli():
        baslat(ornek_veri=False)
    else:
        secim = firma_sihirbazi()
        if secim is None:
            return
        baslat(ornek_veri=secim)
    App().mainloop()


# ==========================================================================
# app_qt.py · PYQT5 ARAYÜZÜ
# ==========================================================================

def qt_arayuzu():
    """PyQt5 arayüzünü kurar ve çalıştırır (pip install pyqt5).

    Arayüz sınıfları bu fonksiyonun içinde tanımlıdır;
    böylece PyQt5 kurulu olmayan bilgisayarda dosyanın
    tkinter sürümü sorunsuz açılır.
    """
    import os
    import sys

    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox,
                                 QDialog, QFormLayout, QFrame, QHBoxLayout,
                                 QHeaderView, QLabel, QLineEdit, QMainWindow,
                                 QMessageBox, QPushButton, QScrollArea,
                                 QSpinBox, QStackedWidget, QTableWidget,
                                 QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)



    TEMA = f"""
    * {{ font-family: 'Segoe UI','DejaVu Sans'; color: {ayar.INK}; font-size: 13px; }}
    QMainWindow, QDialog, QWidget#kok {{ background: {ayar.BG}; }}
    QFrame#kart {{ background: {ayar.PANEL}; border-radius: 12px; }}
    QFrame#yan {{ background: {ayar.LACIVERT}; border: none; }}
    QLabel#h1 {{ font-size: 20px; font-weight: 700; }}
    QLabel#h2 {{ font-size: 14px; font-weight: 600; }}
    QLabel#soluk {{ color: {ayar.MUTED}; font-size: 11px; }}
    QLabel#deger {{ font-size: 22px; font-weight: 800; color: {ayar.ACCENT}; }}
    QLineEdit, QComboBox, QSpinBox, QTextEdit {{
        background: #0d1626; border: 1px solid {ayar.LINE}; border-radius: 8px;
        padding: 7px 10px; selection-background-color: {ayar.ACCENT2};
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ayar.ACCENT2}; }}
    QComboBox QAbstractItemView {{ background: {ayar.PANEL2};
        selection-background-color: {ayar.ACCENT2}; }}
    QPushButton {{ background: {ayar.ACCENT2}; border: none; border-radius: 8px;
        padding: 9px 14px; font-weight: 600; color: white; }}
    QPushButton:hover {{ background: #2196f3; }}
    QPushButton#aksiyon {{ background: {ayar.ACCENT}; color: #04231f; }}
    QPushButton#wa {{ background: {ayar.WA}; color: #062d17; }}
    QPushButton#sil {{ background: {ayar.NO}; }}
    QPushButton#hayalet {{ background: transparent; border: 1px solid {ayar.LINE};
        color: {ayar.INK}; }}
    QPushButton#hayalet:hover {{ background: {ayar.PANEL2}; }}
    QPushButton#nav {{ background: transparent; text-align: left; padding: 11px 16px;
        border-radius: 8px; color: #c4d3ea; font-weight: 600; }}
    QPushButton#nav:hover {{ background: rgba(255,255,255,0.06); }}
    QPushButton#nav:checked {{ background: {ayar.ACCENT2}; color: white; }}
    QTableWidget {{ background: {ayar.PANEL}; gridline-color: {ayar.LINE};
        border: none; border-radius: 10px; selection-background-color: {ayar.ACCENT2};
    }}
    QHeaderView::section {{ background: {ayar.PANEL2}; color: {ayar.MUTED};
        padding: 7px; border: none; font-weight: 600; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; }}
    QScrollBar::handle:vertical {{ background: {ayar.LINE}; border-radius: 5px; }}
    QCheckBox {{ spacing: 6px; }}
    """


    def kart(pencere=None):
        f = QFrame()
        f.setObjectName("kart")
        return f


    def hata_goster(ana, metin):
        QMessageBox.warning(ana, "Hata", metin)


    def bilgi_goster(ana, metin):
        QMessageBox.information(ana, ayar.FIRMA, metin)


    def soru(ana, metin):
        return QMessageBox.question(ana, ayar.FIRMA, metin,
                                    QMessageBox.Yes | QMessageBox.No) == \
            QMessageBox.Yes


    # ==========================================================================
    # GİRİŞ
    # ==========================================================================
    class GirisPenceresi(QWidget):
        def __init__(self, basarili):
            super().__init__()
            self.basarili = basarili
            self.deneme = 0
            self.setObjectName("kok")
            self.setWindowTitle(f"{ayar.FIRMA} · Giriş")
            self.resize(420, 520)
            dis = QVBoxLayout(self)
            dis.setAlignment(Qt.AlignCenter)
            k = kart()
            k.setFixedWidth(340)
            v = QVBoxLayout(k)
            v.setContentsMargins(28, 30, 28, 30)
            v.setSpacing(12)
            logo = QLabel(ayar.FIRMA)
            logo.setObjectName("h1")
            logo.setAlignment(Qt.AlignCenter)
            alt = QLabel(f"Servis Takip PRO {ayar.SURUM}")
            alt.setObjectName("soluk")
            alt.setAlignment(Qt.AlignCenter)
            self.kadi = QLineEdit()
            self.kadi.setPlaceholderText("Kullanıcı adı")
            self.sifre = QLineEdit()
            self.sifre.setPlaceholderText("Şifre")
            self.sifre.setEchoMode(QLineEdit.Password)
            self.sifre.returnPressed.connect(self._giris)
            dugme = QPushButton("Giriş Yap")
            dugme.setObjectName("aksiyon")
            dugme.clicked.connect(self._giris)
            self.durum = QLabel("")
            self.durum.setObjectName("soluk")
            self.durum.setAlignment(Qt.AlignCenter)
            self.durum.setWordWrap(True)
            ipucu = QLabel("İlk kurulum: admin / 1234")
            ipucu.setObjectName("soluk")
            ipucu.setAlignment(Qt.AlignCenter)
            for w in (logo, alt, self.kadi, self.sifre, dugme, self.durum, ipucu):
                v.addWidget(w)
            dis.addWidget(k)

        def _giris(self, sessiz=False):
            try:
                kullanici = srv.giris(self.kadi.text(), self.sifre.text())
            except ServisHata as e:
                self.deneme += 1
                kalan = ayar.MAX_DENEME - self.deneme
                if ayar.MAX_DENEME > 0 and kalan <= 0 and not sessiz:
                    hata_goster(self, "Deneme hakkınız doldu.")
                    self.close()
                    return
                ek = f" (kalan deneme: {kalan})" if ayar.MAX_DENEME > 0 else ""
                self.durum.setText(str(e) + ek)
                self.sifre.clear()
                return
            self.basarili(kullanici)
            self.close()


    # ==========================================================================
    # ANA PENCERE
    # ==========================================================================
    class AnaPencere(QMainWindow):
        def __init__(self, kullanici):
            super().__init__()
            self.kullanici = kullanici
            self.sepet = []
            self.setWindowTitle(f"{ayar.FIRMA} · Servis Takip PRO "
                                f"({kullanici['ad_soyad']})")
            self.resize(1280, 780)
            kok = QWidget()
            kok.setObjectName("kok")
            self.setCentralWidget(kok)
            duzen = QHBoxLayout(kok)
            duzen.setContentsMargins(0, 0, 0, 0)
            duzen.setSpacing(0)
            self.yigin = QStackedWidget()
            duzen.addWidget(self._yan_menu())
            duzen.addWidget(self.yigin, 1)
            self.yenile()

        # ---------------------------------------------------------------- menü
        def rol(self):
            return self.kullanici["rol"]

        def yetkili(self, izin):
            return srv.yetki(self.kullanici, izin)

        def kid(self):
            return self.kullanici["id"]

        def _sayfalar(self):
            if self.rol() == ayar.ROL_MUSTERI:
                return [("🔧  Kayıtlarım", self._sayfa_kayitlarim),
                        ("💰  Masraf Onayı", self._sayfa_masraf),
                        ("🔎  Kod Sorgula", self._sayfa_kod)]
            s = [("🏠  Panel", self._sayfa_panel),
                 ("🔧  Servis Kayıtları", self._sayfa_servisler),
                 ("➕  Yeni Kayıt", self._sayfa_yeni),
                 ("📦  Ürün / Stok", self._sayfa_urunler),
                 ("👥  Müşteriler", self._sayfa_musteriler),
                 ("🚚  Teslim Takibi", self._sayfa_teslim),
                 ("🧾  Faturalar", self._sayfa_faturalar),
                 ("🛒  Sipariş / Satış", self._sayfa_siparis)]
            if self.yetkili("rapor_gor"):
                s.append(("📊  Raporlar", self._sayfa_rapor))
            if self.yetkili("kullanici_yonet"):
                s.append(("🔐  Kullanıcılar", self._sayfa_kullanicilar))
            return s

        def _yan_menu(self):
            yan = QFrame()
            yan.setObjectName("yan")
            yan.setFixedWidth(236)
            v = QVBoxLayout(yan)
            v.setContentsMargins(12, 20, 12, 18)
            v.setSpacing(4)
            baslik = QLabel(ayar.FIRMA)
            baslik.setObjectName("h2")
            alt = QLabel(f"Servis Takip PRO {ayar.SURUM}")
            alt.setObjectName("soluk")
            ad = QLabel(self.kullanici["ad_soyad"])
            ad.setObjectName("h2")
            rol = QLabel(ayar.ROL_ADI.get(self.rol(), self.rol()).upper())
            rol.setObjectName("soluk")
            for w in (baslik, alt):
                v.addWidget(w)
            v.addSpacing(14)
            for w in (ad, rol):
                v.addWidget(w)
            v.addSpacing(12)

            self.gruplar = QButtonGroup(self)
            for i, (metin, olustur) in enumerate(self._sayfalar()):
                b = QPushButton(metin)
                b.setObjectName("nav")
                b.setCheckable(True)
                b.clicked.connect(lambda _, x=i: self.yigin.setCurrentIndex(x))
                self.gruplar.addButton(b, i)
                v.addWidget(b)
                sarmal = QWidget()
                sarmal.setObjectName("kok")
                QVBoxLayout(sarmal).setContentsMargins(18, 16, 18, 16)
                self.yigin.addWidget(sarmal)
            self.gruplar.button(0).setChecked(True)
            self.yigin.currentChanged.connect(self._sayfa_degisti)
            v.addStretch()
            sifre = QPushButton("🔑  Şifre Değiştir")
            sifre.setObjectName("hayalet")
            sifre.clicked.connect(self._sifre_degistir)
            cikis = QPushButton("⎋  Çıkış")
            cikis.setObjectName("sil")
            cikis.clicked.connect(self.close)
            v.addWidget(sifre)
            v.addWidget(cikis)
            return yan

        def _sayfa_degisti(self, i):
            if self.gruplar.button(i):
                self.gruplar.button(i).setChecked(True)
            self._doldur(i)

        def yenile(self):
            self._doldur(self.yigin.currentIndex())

        def _doldur(self, i):
            sayfalar = self._sayfalar()
            if not 0 <= i < len(sayfalar):
                return
            sarmal = self.yigin.widget(i)
            duzen = sarmal.layout()
            while duzen.count():
                oge = duzen.takeAt(0)
                if oge.widget():
                    oge.widget().deleteLater()
            try:
                sayfalar[i][1](duzen)
            except ServisHata as e:
                hata_goster(self, str(e))

        # ------------------------------------------------------------ yardımcı
        def _baslik(self, duzen, metin, aciklama=""):
            b = QLabel(metin)
            b.setObjectName("h1")
            duzen.addWidget(b)
            if aciklama:
                a = QLabel(aciklama)
                a.setObjectName("soluk")
                duzen.addWidget(a)

        def _tablo(self, sutunlar, genislikler=None):
            t = QTableWidget(0, len(sutunlar))
            t.setHorizontalHeaderLabels(sutunlar)
            t.verticalHeader().setVisible(False)
            t.setSelectionBehavior(QTableWidget.SelectRows)
            t.setEditTriggers(QTableWidget.NoEditTriggers)
            t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            return t

        @staticmethod
        def _satir(tablo, i, degerler, veri=None):
            for j, d in enumerate(degerler):
                oge = QTableWidgetItem(str(d))
                if j == 0 and veri is not None:
                    oge.setData(Qt.UserRole, veri)
                tablo.setItem(i, j, oge)

        def _secili_veri(self, tablo):
            satir = tablo.currentRow()
            if satir < 0:
                hata_goster(self, "Listeden bir satır seçin.")
                return None
            oge = tablo.item(satir, 0)
            return oge.data(Qt.UserRole) if oge else None

        def _wa(self, telefon, metin):
            url, hata = msj.wa_ac(telefon, metin)
            if hata and not url:
                hata_goster(self, hata)
                return False
            return True

        # ================================================================ PANEL
        def _sayfa_panel(self, duzen):
            self._baslik(duzen, "Panel", "Günlük iş listesi ve genel durum")
            o = srv.ozet_rapor()
            satir = QHBoxLayout()
            for ad, deger in [("Açık İş", o["servis_acik"]),
                              ("Teslime Hazır", o["teslim_hazir"]),
                              ("Kritik Stok", o["kritik_stok"]),
                              ("Hatırlatma", o["hatirlatma"]),
                              ("Ciro", db.para(o["ciro"]))]:
                k = kart()
                kv = QVBoxLayout(k)
                kv.setContentsMargins(16, 12, 16, 12)
                e = QLabel(ad.upper())
                e.setObjectName("soluk")
                d = QLabel(str(deger))
                d.setObjectName("deger")
                kv.addWidget(e)
                kv.addWidget(d)
                satir.addWidget(k)
            duzen.addLayout(satir)

            alt = QHBoxLayout()
            sol = kart()
            sv = QVBoxLayout(sol)
            sv.setContentsMargins(16, 14, 16, 14)
            b = QLabel("Durum Dağılımı")
            b.setObjectName("h2")
            sv.addWidget(b)
            for durum, adet in srv.durum_dagilimi().items():
                e = QLabel(f"{durum}  ·  {adet}")
                e.setStyleSheet(f"color: {ayar.DURUM_RENK.get(durum, ayar.INK)}")
                sv.addWidget(e)
            sv.addStretch()
            sag = kart()
            gv = QVBoxLayout(sag)
            gv.setContentsMargins(16, 14, 16, 14)
            b2 = QLabel("Kritik Stok")
            b2.setObjectName("h2")
            gv.addWidget(b2)
            kritik = srv.kritik_stoklar()
            if not kritik:
                gv.addWidget(QLabel("Kritik seviyede ürün yok."))
            for u in kritik[:12]:
                e = QLabel(f"• {u['ad']} — stok {u['stok']} / kritik "
                           f"{u['kritik_stok']}")
                e.setStyleSheet(f"color: {ayar.NO}")
                gv.addWidget(e)
            gv.addStretch()
            alt.addWidget(sol)
            alt.addWidget(sag)
            duzen.addLayout(alt, 1)

        # ====================================================== SERVİS KAYITLARI
        def _sayfa_servisler(self, duzen):
            self._baslik(duzen, "Servis Kayıtları", "Satır seçip işlem yapın")
            ust = QHBoxLayout()
            self.s_arama = QLineEdit()
            self.s_arama.setPlaceholderText("Kod, müşteri, marka, arıza ara…")
            self.s_arama.textChanged.connect(self._servis_doldur)
            self.s_durum = QComboBox()
            self.s_durum.addItems(["Tümü"] + ayar.DURUMLAR)
            self.s_durum.currentIndexChanged.connect(self._servis_doldur)
            self.s_arsiv = QCheckBox("Arşiv")
            self.s_arsiv.stateChanged.connect(self._servis_doldur)
            ust.addWidget(self.s_arama, 2)
            ust.addWidget(self.s_durum)
            ust.addWidget(self.s_arsiv)
            duzen.addLayout(ust)

            self.s_tablo = self._tablo(["Kod", "Müşteri", "Marka / Ürün", "Durum",
                                        "Tutar", "Giriş"])
            duzen.addWidget(self.s_tablo, 1)

            dugmeler = QHBoxLayout()
            tanim = [("▶ Durumu İlerlet", "aksiyon", self._durum_ilerlet,
                      self.yetkili("servis_duzenle")),
                     ("₺ İşçilik Gir", "hayalet", self._iscilik_gir,
                      self.yetkili("servis_duzenle")),
                     ("＋ Parça Ekle", "hayalet", self._parca_ekle,
                      self.yetkili("servis_duzenle")),
                     ("🖨 Servis Kartı", "hayalet", self._servis_karti, True),
                     ("🧾 Fatura Kes", "hayalet", self._fatura_kes,
                      self.yetkili("fatura_kes")),
                     ("💬 Durum Gönder", "wa", self._wa_durum, True),
                     ("✅ Hazır + WhatsApp", "wa", self._hazir,
                      self.yetkili("servis_duzenle")),
                     ("🗑 Sil", "sil", self._servis_sil, self.yetkili("servis_sil"))]
            for metin, stil, komut, izin in tanim:
                if not izin:
                    continue
                b = QPushButton(metin)
                b.setObjectName(stil)
                b.clicked.connect(komut)
                dugmeler.addWidget(b)
            duzen.addLayout(dugmeler)
            self._servis_doldur()

        def _servis_doldur(self):
            durum = self.s_durum.currentText()
            kayitlar = srv.servis_listele(
                arama=self.s_arama.text().strip(),
                durum=None if durum == "Tümü" else durum,
                arsiv=1 if self.s_arsiv.isChecked() else 0)
            self.s_tablo.setRowCount(len(kayitlar))
            for i, s in enumerate(kayitlar):
                m = srv.maliyet(s["id"])
                self._satir(self.s_tablo, i,
                            [s["kod"], s["ad_soyad"], f"{s['marka']} {s['urun']}",
                             s["durum"], db.para(m["toplam"]), s["giris_tarihi"]],
                            veri=s["id"])

        def _servis_secili(self):
            sid = self._secili_veri(self.s_tablo)
            return srv.servis_bul(sid) if sid else None

        def _durum_ilerlet(self):
            s = self._servis_secili()
            if not s:
                return
            try:
                yeni = srv.durum_ilerlet(s["id"], self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            self._servis_doldur()
            if yeni == "Teslime Hazır" and soru(self, "Müşteriye WhatsApp "
                                                      "bildirimi gönderilsin mi?"):
                g = srv.servis_bul(s["id"])
                self._wa(g["telefon"],
                         msj.hazir_bildirimi(g, srv.maliyet(g["id"])["toplam"]))

        def _iscilik_gir(self):
            s = self._servis_secili()
            if not s:
                return
            d = MetinDialog(self, "İşçilik / Tamir Ücreti (₺)",
                            db.para(s["iscilik"] or s["masraf_tutar"], False),
                            tek_satir=True)
            if d.exec_() == QDialog.Accepted and d.metin():
                srv.servis_guncelle(s["id"], self.kid(), iscilik=d.metin(),
                                    masraf_tutar=d.metin(), masraf_onay="Bekliyor")
                self._servis_doldur()

        def _parca_ekle(self):
            s = self._servis_secili()
            if not s:
                return
            d = ParcaDialog(self, s["id"], self.kid())
            if d.exec_() == QDialog.Accepted:
                self._servis_doldur()

        def _servis_karti(self):
            s = self._servis_secili()
            if not s:
                return
            yol = fis.servis_karti(s, srv.parca_listele(s["id"]),
                                   srv.maliyet(s["id"]))
            bilgi_goster(self, f"Servis kartı oluşturuldu:\n{yol}")

        def _fatura_kes(self):
            s = self._servis_secili()
            if not s:
                return
            try:
                fid = srv.fatura_kes(s["id"], "Servis işlemi", self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            f = srv.fatura_bul(fid)
            self._servis_doldur()
            if soru(self, f"{f['fatura_no']} kesildi ({db.para(f['toplam'])}).\n"
                          "Fiş yazdırılsın mı?"):
                fis.fatura_fisi(f, s, srv.parca_listele(s["id"]))

        def _wa_durum(self):
            s = self._servis_secili()
            if s:
                self._wa(s["telefon"], msj.durum_bilgisi(s))

        def _hazir(self):
            s = self._servis_secili()
            if not s:
                return
            srv.durum_guncelle(s["id"], "Teslime Hazır", self.kid())
            g = srv.servis_bul(s["id"])
            self._servis_doldur()
            self._wa(g["telefon"],
                     msj.hazir_bildirimi(g, srv.maliyet(g["id"])["toplam"]))

        def _servis_sil(self):
            s = self._servis_secili()
            if not s or not soru(self, f"{s['kod']} silinsin mi?"):
                return
            try:
                srv.servis_sil(s["id"], self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            self._servis_doldur()

        # ============================================================ YENİ KAYIT
        def _sayfa_yeni(self, duzen):
            self._baslik(duzen, "Yeni Servis Kaydı", "Müşteri ve cihaz bilgileri")
            k = kart()
            form = QFormLayout(k)
            form.setContentsMargins(18, 16, 18, 16)
            self.y_musteriler = srv.musteri_listele()
            self.y_musteri = QComboBox()
            self.y_musteri.addItems(["+ Yeni müşteri"] +
                                    [f"{m['ad_soyad']} · {m['telefon']}"
                                     for m in self.y_musteriler])
            self.y_ad = QLineEdit()
            self.y_tel = QLineEdit()
            self.y_marka = QComboBox()
            self.y_marka.addItems(ayar.MARKALAR)
            self.y_urun = QComboBox()
            self.y_urun.setEditable(True)
            self.y_urun.addItems(ayar.modeller(ayar.MARKALAR[0]))
            self.y_marka.currentTextChanged.connect(self._marka_degisti)
            self.y_model = QLineEdit()
            self.y_garanti = QComboBox()
            self.y_garanti.addItems(ayar.GARANTI_SECENEKLERI)
            self.y_fatura = QComboBox()
            self.y_fatura.addItems(ayar.FATURA_SECENEKLERI)
            self.y_iscilik = QLineEdit()
            self.y_ariza = QTextEdit()
            self.y_ariza.setFixedHeight(80)
            self.y_wa = QCheckBox("Kayıt sonrası WhatsApp ile takip kodu gönder")
            self.y_wa.setChecked(True)
            form.addRow("Müşteri", self.y_musteri)
            form.addRow("Ad Soyad", self.y_ad)
            form.addRow("Telefon", self.y_tel)
            form.addRow("Marka", self.y_marka)
            form.addRow("Ürün", self.y_urun)
            form.addRow("Model / Seri", self.y_model)
            form.addRow("Garanti", self.y_garanti)
            form.addRow("Fatura", self.y_fatura)
            form.addRow("İşçilik (₺)", self.y_iscilik)
            form.addRow("Arıza", self.y_ariza)
            form.addRow("", self.y_wa)
            kaydet = QPushButton("Kaydı Oluştur")
            kaydet.setObjectName("aksiyon")
            kaydet.clicked.connect(self._kayit_olustur)
            form.addRow("", kaydet)
            duzen.addWidget(k)
            duzen.addStretch()

        def _marka_degisti(self, marka):
            self.y_urun.clear()
            self.y_urun.addItems(ayar.modeller(marka))

        def _kayit_olustur(self):
            try:
                i = self.y_musteri.currentIndex()
                if i == 0:
                    mid = srv.musteri_bul_veya_ekle(self.y_ad.text(),
                                                    self.y_tel.text(),
                                                    olusturan_id=self.kid())
                else:
                    mid = self.y_musteriler[i - 1]["id"]
                sid = srv.servis_ekle(
                    mid, self.y_marka.currentText(), self.y_urun.currentText(),
                    self.y_model.text(), self.y_model.text(),
                    self.y_ariza.toPlainText(), self.y_garanti.currentText(),
                    self.y_fatura.currentText(), self.y_iscilik.text() or 0,
                    olusturan_id=self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            s = srv.servis_bul(sid)
            bilgi_goster(self, f"Kayıt oluşturuldu.\nServis Kodu: {s['kod']}\n"
                               f"Onay Kodu: {s['onay_kodu']}")
            if self.y_wa.isChecked() and s["telefon"]:
                self._wa(s["telefon"], msj.kayit_acildi(s))
            self.yigin.setCurrentIndex(1)

        # ============================================================= ÜRÜNLER
        def _sayfa_urunler(self, duzen):
            self._baslik(duzen, "Ürün / Stok", "urunler.md ile eşitlenir")
            ust = QHBoxLayout()
            self.u_arama = QLineEdit()
            self.u_arama.setPlaceholderText("Ürün ara…")
            self.u_arama.textChanged.connect(self._urun_doldur)
            self.u_kritik = QCheckBox("Sadece kritik stok")
            self.u_kritik.stateChanged.connect(self._urun_doldur)
            ust.addWidget(self.u_arama, 2)
            ust.addWidget(self.u_kritik)
            if self.yetkili("urun_yonet"):
                ekle = QPushButton("＋ Yeni Ürün")
                ekle.setObjectName("aksiyon")
                ekle.clicked.connect(self._urun_ekle)
                stok = QPushButton("Stok Güncelle")
                stok.setObjectName("hayalet")
                stok.clicked.connect(self._stok_guncelle)
                ust.addWidget(stok)
                ust.addWidget(ekle)
            duzen.addLayout(ust)
            sutun = ["Kod", "Ürün", "Kategori", "Stok", "Kritik", "Satış", "Marj %"]
            if self.yetkili("gelis_fiyat_gor"):
                sutun.insert(5, "Geliş")
            self.u_tablo = self._tablo(sutun)
            duzen.addWidget(self.u_tablo, 1)
            self._urun_doldur()

        def _urun_doldur(self):
            kayitlar = urn.listele(self.u_arama.text().strip(),
                                   self.u_kritik.isChecked())
            self.u_tablo.setRowCount(len(kayitlar))
            for i, u in enumerate(kayitlar):
                deger = [u["kod"], u["ad"], u["kategori"], u["stok"],
                         u["kritik_stok"]]
                if self.yetkili("gelis_fiyat_gor"):
                    deger.append(db.para(u["gelis_fiyat"]))
                deger += [db.para(u["satis_fiyat"]), f"{urn.kar_marji(u):.0f}"]
                self._satir(self.u_tablo, i, deger, veri=u["kod"])

        def _urun_ekle(self):
            d = UrunDialog(self, self.kid())
            if d.exec_() == QDialog.Accepted:
                self._urun_doldur()

        def _stok_guncelle(self):
            kod = self._secili_veri(self.u_tablo)
            if not kod:
                return
            u = urn.bul(kod)
            d = MetinDialog(self, f"{u['ad']} yeni stok adedi", str(u["stok"]),
                            tek_satir=True)
            if d.exec_() == QDialog.Accepted and d.metin():
                srv.urun_guncelle(kod, self.kid(), stok=d.metin())
                self._urun_doldur()

        # =========================================================== MÜŞTERİLER
        def _sayfa_musteriler(self, duzen):
            self._baslik(duzen, "Müşteriler", "Kayıtlı müşteriler ve servis sayısı")
            ust = QHBoxLayout()
            self.m_arama = QLineEdit()
            self.m_arama.setPlaceholderText("Müşteri ara…")
            self.m_arama.textChanged.connect(self._musteri_doldur)
            ekle = QPushButton("＋ Yeni Müşteri")
            ekle.setObjectName("aksiyon")
            ekle.clicked.connect(self._musteri_ekle)
            ust.addWidget(self.m_arama, 2)
            ust.addWidget(ekle)
            duzen.addLayout(ust)
            self.m_tablo = self._tablo(["Ad Soyad", "Telefon", "Adres", "Servis"])
            duzen.addWidget(self.m_tablo, 1)
            self._musteri_doldur()

        def _musteri_doldur(self):
            kayitlar = srv.musteri_listele(self.m_arama.text().strip())
            self.m_tablo.setRowCount(len(kayitlar))
            for i, m in enumerate(kayitlar):
                adet = len(srv.servis_listele(arsiv=None, musteri_id=m["id"]))
                self._satir(self.m_tablo, i, [m["ad_soyad"], m["telefon"],
                                              m["adres"], adet], veri=m["id"])

        def _musteri_ekle(self):
            d = MusteriDialog(self, self.kid())
            if d.exec_() == QDialog.Accepted:
                self._musteri_doldur()

        # ========================================================= TESLİM TAKİBİ
        def _sayfa_teslim(self, duzen):
            self._baslik(duzen, "Teslim Takibi", "Teslime hazır ve gecikenler")
            self.t_tablo = self._tablo(["Kod", "Müşteri", "Telefon", "Cihaz",
                                        "Teslim Tarihi", "Gecikme"])
            duzen.addWidget(self.t_tablo, 1)
            satir = QHBoxLayout()
            h = QPushButton("💬 Hatırlatma Gönder")
            h.setObjectName("wa")
            h.clicked.connect(self._hatirlat)
            t = QPushButton("✔ Teslim Edildi")
            t.setObjectName("aksiyon")
            t.clicked.connect(self._teslim_et)
            satir.addWidget(h)
            satir.addWidget(t)
            satir.addStretch()
            duzen.addLayout(satir)
            self._teslim_doldur()

        def _teslim_doldur(self):
            kayitlar = srv.teslim_bekleyenler()
            self.t_tablo.setRowCount(len(kayitlar))
            for i, s in enumerate(kayitlar):
                gun = db.gun_farki(s["teslim_tarihi"] or s["giris_tarihi"]) or 0
                self._satir(self.t_tablo, i,
                            [s["kod"], s["ad_soyad"], s["telefon"],
                             f"{s['marka']} {s['urun']}", s["teslim_tarihi"] or "-",
                             f"{gun} gün" if gun > 0 else "-"], veri=s["id"])

        def _hatirlat(self):
            sid = self._secili_veri(self.t_tablo)
            if not sid:
                return
            s = srv.servis_bul(sid)
            s["gecikme_gun"] = db.gun_farki(s["teslim_tarihi"] or s["giris_tarihi"])
            if self._wa(s["telefon"], msj.hatirlatma(s)):
                srv.hatirlatma_isaretle(sid, self.kid())
                self._teslim_doldur()

        def _teslim_et(self):
            sid = self._secili_veri(self.t_tablo)
            if not sid:
                return
            srv.durum_guncelle(sid, "Teslim Edildi", self.kid())
            self._teslim_doldur()

        # ============================================================ FATURALAR
        def _sayfa_faturalar(self, duzen):
            self._baslik(duzen, "Faturalar",
                         f"KDV %{int(ayar.KDV_ORANI * 100)} dahil")
            self.f_tablo = self._tablo(["Fatura No", "Servis", "Müşteri",
                                        "Ara Toplam", "KDV", "Toplam", "Durum",
                                        "Tarih"])
            duzen.addWidget(self.f_tablo, 1)
            satir = QHBoxLayout()
            for metin, stil, komut, izin in [
                    ("🖨 Fiş Yazdır", "hayalet", self._fatura_fis, True),
                    ("✔ Ödendi", "aksiyon",
                     lambda: self._fatura_durum("Ödendi"), True),
                    ("⨯ İptal", "sil", lambda: self._fatura_durum("İptal"), True),
                    ("✎ Revize", "hayalet", self._fatura_revize,
                     self.yetkili("fatura_revize")),
                    ("💬 Müşteriye Gönder", "wa", self._fatura_wa, True)]:
                if not izin:
                    continue
                b = QPushButton(metin)
                b.setObjectName(stil)
                b.clicked.connect(komut)
                satir.addWidget(b)
            duzen.addLayout(satir)
            self._fatura_doldur()

        def _fatura_doldur(self):
            kayitlar = srv.fatura_listele()
            self.f_tablo.setRowCount(len(kayitlar))
            for i, f in enumerate(kayitlar):
                self._satir(self.f_tablo, i,
                            [f["fatura_no"], f["servis_kod"] or "-",
                             f["ad_soyad"] or "-", db.para(f["ara_toplam"]),
                             db.para(f["kdv"]), db.para(f["toplam"]), f["durum"],
                             (f["tarih"] or "")[:16].replace("T", " ")],
                            veri=f["id"])

        def _fatura_secili(self):
            fid = self._secili_veri(self.f_tablo)
            return srv.fatura_bul(fid) if fid else None

        def _fatura_durum(self, durum):
            f = self._fatura_secili()
            if not f:
                return
            try:
                srv.fatura_durum(f["id"], durum, self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            self._fatura_doldur()

        def _fatura_revize(self):
            f = self._fatura_secili()
            if not f:
                return
            d = MetinDialog(self, f"{f['fatura_no']} yeni toplam (KDV dahil)",
                            db.para(f["toplam"], False), tek_satir=True)
            if d.exec_() == QDialog.Accepted and d.metin():
                try:
                    srv.fatura_revize(f["id"], d.metin(), "Revize", self.kid())
                except ServisHata as e:
                    return hata_goster(self, str(e))
                self._fatura_doldur()

        def _fatura_fis(self):
            f = self._fatura_secili()
            if not f:
                return
            s = srv.servis_bul(f["servis_id"]) if f["servis_id"] else None
            yol = fis.fatura_fisi(f, s, srv.parca_listele(f["servis_id"])
                                  if f["servis_id"] else [])
            bilgi_goster(self, f"Fatura fişi:\n{yol}")

        def _fatura_wa(self):
            f = self._fatura_secili()
            if f:
                self._wa(f["telefon"], msj.fatura_bilgisi(f))

        # ============================================================== SİPARİŞ
        def _sayfa_siparis(self, duzen):
            self._baslik(duzen, "Sipariş / Satış", "Sepet oluştur, WhatsApp'tan bildir")
            ust = QHBoxLayout()
            self.sp_urunler = urn.listele()
            self.sp_secim = QComboBox()
            self.sp_secim.addItems([f"{u['ad']} · {db.para(u['satis_fiyat'])} "
                                    f"(stok {u['stok']})" for u in self.sp_urunler])
            self.sp_adet = QSpinBox()
            self.sp_adet.setRange(1, 999)
            ekle = QPushButton("Sepete Ekle")
            ekle.setObjectName("aksiyon")
            ekle.clicked.connect(self._sepete_ekle)
            ust.addWidget(self.sp_secim, 2)
            ust.addWidget(self.sp_adet)
            ust.addWidget(ekle)
            duzen.addLayout(ust)

            self.sp_tablo = self._tablo(["Ürün", "Adet", "Birim", "Tutar"])
            duzen.addWidget(self.sp_tablo, 1)
            alt = QHBoxLayout()
            self.sp_musteri = QLineEdit()
            self.sp_musteri.setPlaceholderText("Müşteri adı")
            self.sp_tel = QLineEdit()
            self.sp_tel.setPlaceholderText("Telefon")
            self.sp_toplam = QLabel("Toplam: 0,00 ₺")
            self.sp_toplam.setObjectName("deger")
            olustur = QPushButton("Siparişi Oluştur + WhatsApp")
            olustur.setObjectName("wa")
            olustur.clicked.connect(self._siparis_olustur)
            cikar = QPushButton("Satırı Çıkar")
            cikar.setObjectName("hayalet")
            cikar.clicked.connect(self._sepetten_cikar)
            alt.addWidget(self.sp_musteri)
            alt.addWidget(self.sp_tel)
            alt.addWidget(self.sp_toplam)
            alt.addWidget(cikar)
            alt.addWidget(olustur)
            duzen.addLayout(alt)
            self.sepet = []
            self._sepet_yenile()

        def _sepete_ekle(self):
            if not self.sp_urunler:
                return
            u = self.sp_urunler[self.sp_secim.currentIndex()]
            self.sepet.append({"urun_kod": u["kod"], "ad": u["ad"],
                               "adet": self.sp_adet.value(),
                               "birim_fiyat": u["satis_fiyat"]})
            self._sepet_yenile()

        def _sepetten_cikar(self):
            satir = self.sp_tablo.currentRow()
            if satir >= 0:
                self.sepet.pop(satir)
                self._sepet_yenile()

        def _sepet_yenile(self):
            self.sp_tablo.setRowCount(len(self.sepet))
            toplam = 0
            for i, s in enumerate(self.sepet):
                tutar = s["adet"] * s["birim_fiyat"]
                toplam += tutar
                self._satir(self.sp_tablo, i, [s["ad"], s["adet"],
                                               db.para(s["birim_fiyat"]),
                                               db.para(tutar)])
            self.sp_toplam.setText(f"Toplam: {db.para(toplam)}")

        def _siparis_olustur(self):
            if not self.sepet:
                return hata_goster(self, "Sepet boş.")
            try:
                sip = srv.siparis_olustur(self.sepet, self.sp_musteri.text().strip(),
                                          self.sp_tel.text(),
                                          kullanici_id=self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            bilgi_goster(self, f"Sipariş kaydedildi.\nFatura No: {sip['fatura_no']}")
            self._wa(self.sp_tel.text(),
                     msj.siparis(self.sp_musteri.text().strip(), self.sepet,
                                 sip["fatura_no"]))
            self.sepet = []
            self._sepet_yenile()

        # =============================================================== RAPOR
        def _sayfa_rapor(self, duzen):
            self._baslik(duzen, "Yönetim Raporu", "Özet, aktarma ve yedekleme")
            o = srv.ozet_rapor()
            k = kart()
            form = QFormLayout(k)
            form.setContentsMargins(18, 16, 18, 16)
            for ad, deger in [("Toplam Servis", o["servis_toplam"]),
                              ("Açık İş", o["servis_acik"]),
                              ("Müşteri", o["musteri"]),
                              ("Ürün Çeşidi", o["urun"]),
                              ("Stok Değeri", db.para(o["stok_degeri"])),
                              ("Fatura Adedi", o["fatura_adet"]),
                              ("Ciro", db.para(o["ciro"])),
                              ("Tahsil Edilen", db.para(o["tahsil"])),
                              ("Satış / Sipariş", db.para(o["siparis_ciro"]))]:
                form.addRow(ad, QLabel(str(deger)))
            duzen.addWidget(k)
            satir = QHBoxLayout()
            for metin, komut in [("🖨 HTML Rapor", self._rapor_html),
                                 ("📤 CSV Aktar", self._csv),
                                 ("💾 Yedek Al", self._yedek)]:
                b = QPushButton(metin)
                b.setObjectName("hayalet")
                b.clicked.connect(komut)
                satir.addWidget(b)
            satir.addStretch()
            duzen.addLayout(satir)
            log_tablo = self._tablo(["Tarih", "Kullanıcı", "Eylem", "Detay"])
            kayitlar = srv.son_loglar(80)
            log_tablo.setRowCount(len(kayitlar))
            for i, l in enumerate(kayitlar):
                self._satir(log_tablo, i,
                            [(l["tarih"] or "")[:16].replace("T", " "),
                             l["ad_soyad"] or "-", l["eylem"], l["detay"]])
            duzen.addWidget(log_tablo, 1)

        def _rapor_html(self):
            yol = fis.rapor_sayfasi(srv.ozet_rapor(), srv.durum_dagilimi(),
                                    srv.marka_dagilimi(), srv.kritik_stoklar(),
                                    srv.en_cok_kullanilan_parcalar())
            bilgi_goster(self, f"Rapor: {yol}")

        def _csv(self):
            sonuc = aktarim.tumunu_aktar()
            bilgi_goster(self, "CSV dosyaları:\n" +
                         "\n".join(os.path.basename(v) for v in sonuc.values()))

        def _yedek(self):
            bilgi_goster(self, f"Yedek alındı:\n{db.yedek_al()}")

        # ========================================================= KULLANICILAR
        def _sayfa_kullanicilar(self, duzen):
            self._baslik(duzen, "Kullanıcılar", "Yönetici · Personel · Müşteri")
            self.k_tablo = self._tablo(["Kullanıcı Adı", "Ad Soyad", "Rol",
                                        "Telefon", "Durum"])
            duzen.addWidget(self.k_tablo, 1)
            satir = QHBoxLayout()
            for metin, stil, komut in [("＋ Yeni Kullanıcı", "aksiyon",
                                        self._kullanici_ekle),
                                       ("⏸ Aktif / Pasif", "hayalet",
                                        self._kullanici_durum),
                                       ("🗑 Sil", "sil", self._kullanici_sil)]:
                b = QPushButton(metin)
                b.setObjectName(stil)
                b.clicked.connect(komut)
                satir.addWidget(b)
            satir.addStretch()
            duzen.addLayout(satir)
            self._kullanici_doldur()

        def _kullanici_doldur(self):
            kayitlar = srv.kullanici_listele()
            self.k_tablo.setRowCount(len(kayitlar))
            for i, k in enumerate(kayitlar):
                self._satir(self.k_tablo, i,
                            [k["kullanici_adi"], k["ad_soyad"],
                             ayar.ROL_ADI.get(k["rol"], k["rol"]),
                             k["telefon"] or "",
                             "Aktif" if k["aktif"] else "Kapalı"], veri=k["id"])

        def _kullanici_ekle(self):
            d = KullaniciDialog(self, self.kid())
            if d.exec_() == QDialog.Accepted:
                self._kullanici_doldur()

        def _kullanici_durum(self):
            uid = self._secili_veri(self.k_tablo)
            if not uid:
                return
            k = db.tek("SELECT * FROM kullanicilar WHERE id=?", (uid,))
            try:
                srv.kullanici_durum(uid, not k["aktif"], self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            self._kullanici_doldur()

        def _kullanici_sil(self):
            uid = self._secili_veri(self.k_tablo)
            if not uid or not soru(self, "Kullanıcı silinsin mi?"):
                return
            try:
                srv.kullanici_sil(uid, self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            self._kullanici_doldur()

        def _sifre_degistir(self):
            d = SifreDialog(self, self.kid())
            d.exec_()

        # ======================================================= MÜŞTERİ PANELİ
        def _musteri_kayitlari(self):
            m = srv.musteri_kullanicidan(self.kid())
            return srv.servis_listele(arsiv=None, musteri_id=m["id"]) if m else []

        def _kayit_karti(self, s):
            m = srv.maliyet(s["id"])
            k = kart()
            v = QVBoxLayout(k)
            v.setContentsMargins(16, 14, 16, 14)
            ust = QLabel(f"{s['marka']} {s['urun']}  ·  {s['kod']}")
            ust.setObjectName("h2")
            durum = QLabel(s["durum"])
            durum.setStyleSheet(f"color: {ayar.DURUM_RENK.get(s['durum'], ayar.INK)};"
                                "font-weight: 700")
            bilgi = QLabel(f"Giriş: {s['giris_tarihi']}   ·   Tahmini teslim: "
                           f"{s['teslim_tarihi'] or '-'}")
            bilgi.setObjectName("soluk")
            ariza = QLabel(f"Arıza: {s['ariza']}")
            ariza.setWordWrap(True)
            tutar = QLabel(f"Tutar: {db.para(m['toplam'])} (KDV dahil)   ·   "
                           f"Masraf onayı: {s['masraf_onay']}")
            tutar.setStyleSheet(f"color: {ayar.ACCENT}")
            for w in (ust, durum, bilgi, ariza):
                v.addWidget(w)
            if s["cozum"]:
                c = QLabel(f"Yapılan işlem: {s['cozum']}")
                c.setWordWrap(True)
                c.setStyleSheet(f"color: {ayar.OK}")
                v.addWidget(c)
            v.addWidget(tutar)
            return k

        def _sayfa_kayitlarim(self, duzen):
            self._baslik(duzen, "Kayıtlarım", "Servisteki ürünlerinizin durumu")
            kayitlar = self._musteri_kayitlari()
            if not kayitlar:
                duzen.addWidget(QLabel("Adınıza kayıtlı servis kaydı yok."))
                duzen.addStretch()
                return
            alan = QScrollArea()
            alan.setWidgetResizable(True)
            alan.setStyleSheet("border: none;")
            ic = QWidget()
            ic.setObjectName("kok")
            iv = QVBoxLayout(ic)
            for s in kayitlar:
                iv.addWidget(self._kayit_karti(s))
            iv.addStretch()
            alan.setWidget(ic)
            duzen.addWidget(alan, 1)

        def _sayfa_masraf(self, duzen):
            self._baslik(duzen, "Masraf Onayı", "Onarım bedelini onaylayın")
            bekleyen = [s for s in self._musteri_kayitlari()
                        if s["masraf_onay"] == "Bekliyor" and
                        (s["masraf_tutar"] or s["iscilik"])]
            if not bekleyen:
                duzen.addWidget(QLabel("Onayınızı bekleyen masraf yok."))
                duzen.addStretch()
                return
            for s in bekleyen:
                m = srv.maliyet(s["id"])
                k = kart()
                v = QVBoxLayout(k)
                v.setContentsMargins(16, 14, 16, 14)
                baslik = QLabel(f"{s['marka']} {s['urun']} · {s['kod']}")
                baslik.setObjectName("h2")
                tutar = QLabel(f"İşçilik {db.para(m['iscilik'])} + Parça "
                               f"{db.para(m['parca'])} + KDV {db.para(m['kdv'])} = "
                               f"{db.para(m['toplam'])}")
                tutar.setStyleSheet(f"color: {ayar.ACCENT}; font-weight: 700")
                v.addWidget(baslik)
                v.addWidget(tutar)
                satir = QHBoxLayout()
                onay = QPushButton("✔ Onaylıyorum")
                onay.setObjectName("aksiyon")
                onay.clicked.connect(
                    lambda _, sid=s["id"]: self._masraf_karar(sid, "Onaylandı"))
                red = QPushButton("✗ Reddediyorum")
                red.setObjectName("sil")
                red.clicked.connect(
                    lambda _, sid=s["id"]: self._masraf_karar(sid, "Reddedildi"))
                satir.addWidget(onay)
                satir.addWidget(red)
                satir.addStretch()
                v.addLayout(satir)
                duzen.addWidget(k)
            duzen.addStretch()

        def _masraf_karar(self, servis_id, karar):
            try:
                srv.masraf_onayla(servis_id, karar, self.kid())
            except ServisHata as e:
                return hata_goster(self, str(e))
            bilgi_goster(self, f"Kararınız kaydedildi: {karar}")
            self.yenile()

        def _sayfa_kod(self, duzen):
            self._baslik(duzen, "Kod Sorgula", "Servis kodu + onay kodu")
            k = kart()
            form = QFormLayout(k)
            form.setContentsMargins(18, 16, 18, 16)
            self.kd_kod = QLineEdit()
            self.kd_onay = QLineEdit()
            form.addRow("Servis Kodu", self.kd_kod)
            form.addRow("Onay Kodu", self.kd_onay)
            b = QPushButton("Sorgula")
            b.setObjectName("aksiyon")
            form.addRow("", b)
            duzen.addWidget(k)
            self.kd_sonuc = QVBoxLayout()
            duzen.addLayout(self.kd_sonuc)
            duzen.addStretch()

            def sorgula():
                while self.kd_sonuc.count():
                    oge = self.kd_sonuc.takeAt(0)
                    if oge.widget():
                        oge.widget().deleteLater()
                try:
                    s = srv.kod_dogrula(self.kd_kod.text(), self.kd_onay.text())
                except ServisHata as e:
                    return hata_goster(self, str(e))
                self.kd_sonuc.addWidget(self._kayit_karti(s))
            b.clicked.connect(sorgula)
            self.kd_onay.returnPressed.connect(sorgula)


    # ==========================================================================
    # DİYALOGLAR
    # ==========================================================================
    class TemelDialog(QDialog):
        def __init__(self, ana, baslik):
            super().__init__(ana)
            self.setWindowTitle(baslik)
            self.setObjectName("kok")
            self.setMinimumWidth(360)
            self.form = QFormLayout(self)

        def dugmeler(self, komut):
            satir = QHBoxLayout()
            vazgec = QPushButton("Vazgeç")
            vazgec.setObjectName("hayalet")
            vazgec.clicked.connect(self.reject)
            kaydet = QPushButton("Kaydet")
            kaydet.setObjectName("aksiyon")
            kaydet.clicked.connect(komut)
            satir.addWidget(vazgec)
            satir.addWidget(kaydet)
            self.form.addRow("", self._sar(satir))

        @staticmethod
        def _sar(duzen):
            w = QWidget()
            w.setLayout(duzen)
            return w


    class MetinDialog(TemelDialog):
        def __init__(self, ana, baslik, mevcut="", tek_satir=False):
            super().__init__(ana, baslik)
            self.giris = QLineEdit(mevcut) if tek_satir else QTextEdit(mevcut)
            self.form.addRow(baslik, self.giris)
            self.dugmeler(self.accept)

        def metin(self):
            if isinstance(self.giris, QLineEdit):
                return self.giris.text().strip()
            return self.giris.toPlainText().strip()


    class ParcaDialog(TemelDialog):
        def __init__(self, ana, servis_id, kullanici_id):
            super().__init__(ana, "Servise Parça Ekle")
            self.servis_id, self.kullanici_id = servis_id, kullanici_id
            self.urunler = urn.listele()
            self.secim = QComboBox()
            self.secim.addItems([f"{u['kod']} · {u['ad']} (stok {u['stok']}) "
                                 f"{db.para(u['satis_fiyat'])}"
                                 for u in self.urunler])
            self.adet = QSpinBox()
            self.adet.setRange(1, 999)
            self.form.addRow("Parça", self.secim)
            self.form.addRow("Adet", self.adet)
            self.dugmeler(self._kaydet)

        def _kaydet(self):
            if not self.urunler:
                return self.reject()
            kod = self.urunler[self.secim.currentIndex()]["kod"]
            try:
                srv.parca_ekle(self.servis_id, kod, self.adet.value(),
                               self.kullanici_id)
            except ServisHata as e:
                return hata_goster(self, str(e))
            self.accept()


    class UrunDialog(TemelDialog):
        def __init__(self, ana, kullanici_id):
            super().__init__(ana, "Yeni Ürün / Parça")
            self.kullanici_id = kullanici_id
            self.kod = QLineEdit()
            self.kod.setPlaceholderText("boş = otomatik")
            self.ad = QLineEdit()
            self.kategori = QComboBox()
            self.kategori.addItems(["Yedek Parça", "Satış Ürünü", "Sarf Malzeme"])
            self.stok = QSpinBox()
            self.stok.setRange(0, 99999)
            self.kritik = QSpinBox()
            self.kritik.setRange(0, 9999)
            self.kritik.setValue(5)
            self.gelis = QLineEdit("0")
            self.satis = QLineEdit("0")
            self.garanti = QLineEdit("2 yıl üretici garantisi")
            for etiket, alan in [("Kod", self.kod), ("Ad", self.ad),
                                 ("Kategori", self.kategori), ("Stok", self.stok),
                                 ("Kritik Stok", self.kritik),
                                 ("Geliş (₺)", self.gelis),
                                 ("Satış (₺)", self.satis),
                                 ("Garanti", self.garanti)]:
                self.form.addRow(etiket, alan)
            self.dugmeler(self._kaydet)

        def _kaydet(self):
            try:
                srv.urun_ekle(self.kod.text(), self.ad.text(), self.stok.value(),
                              self.kritik.value(), self.gelis.text(),
                              self.satis.text(), self.garanti.text(),
                              self.kategori.currentText(), self.kullanici_id)
            except ServisHata as e:
                return hata_goster(self, str(e))
            self.accept()


    class MusteriDialog(TemelDialog):
        def __init__(self, ana, kullanici_id):
            super().__init__(ana, "Yeni Müşteri")
            self.kullanici_id = kullanici_id
            self.ad = QLineEdit()
            self.tel = QLineEdit()
            self.adres = QLineEdit()
            self.eposta = QLineEdit()
            for etiket, alan in [("Ad Soyad", self.ad), ("Telefon", self.tel),
                                 ("Adres", self.adres), ("E-posta", self.eposta)]:
                self.form.addRow(etiket, alan)
            self.dugmeler(self._kaydet)

        def _kaydet(self):
            try:
                srv.musteri_ekle(self.ad.text(), self.tel.text(), self.adres.text(),
                                 self.eposta.text(), olusturan_id=self.kullanici_id)
            except ServisHata as e:
                return hata_goster(self, str(e))
            self.accept()


    class KullaniciDialog(TemelDialog):
        def __init__(self, ana, kullanici_id):
            super().__init__(ana, "Yeni Kullanıcı")
            self.kullanici_id = kullanici_id
            self.kadi = QLineEdit()
            self.ad = QLineEdit()
            self.tel = QLineEdit()
            self.sifre = QLineEdit()
            self.sifre.setEchoMode(QLineEdit.Password)
            self.rol = QComboBox()
            self.rol.addItems([ayar.ROL_ADI[r] for r in ayar.ROLLER])
            self.rol.setCurrentIndex(1)
            for etiket, alan in [("Kullanıcı Adı", self.kadi), ("Ad Soyad", self.ad),
                                 ("Telefon", self.tel), ("Şifre", self.sifre),
                                 ("Rol", self.rol)]:
                self.form.addRow(etiket, alan)
            self.dugmeler(self._kaydet)

        def _kaydet(self):
            kod = ayar.ROLLER[self.rol.currentIndex()]
            try:
                uid = srv.kullanici_ekle(self.kadi.text(), self.ad.text(),
                                         self.sifre.text(), kod, self.tel.text(),
                                         olusturan_id=self.kullanici_id)
                if kod == ayar.ROL_MUSTERI:
                    srv.musteri_ekle(self.ad.text(), self.tel.text(),
                                     kullanici_id=uid,
                                     olusturan_id=self.kullanici_id)
            except ServisHata as e:
                return hata_goster(self, str(e))
            self.accept()


    class SifreDialog(TemelDialog):
        def __init__(self, ana, kullanici_id):
            super().__init__(ana, "Şifre Değiştir")
            self.kullanici_id = kullanici_id
            self.eski = QLineEdit()
            self.yeni = QLineEdit()
            self.yeni2 = QLineEdit()
            for alan in (self.eski, self.yeni, self.yeni2):
                alan.setEchoMode(QLineEdit.Password)
            self.form.addRow("Mevcut Şifre", self.eski)
            self.form.addRow("Yeni Şifre", self.yeni)
            self.form.addRow("Yeni Şifre (tekrar)", self.yeni2)
            self.dugmeler(self._kaydet)

        def _kaydet(self):
            if self.yeni.text() != self.yeni2.text():
                return hata_goster(self, "Yeni şifreler aynı değil.")
            try:
                srv.sifre_degistir(self.kullanici_id, self.yeni.text(),
                                   self.eski.text())
            except ServisHata as e:
                return hata_goster(self, str(e))
            bilgi_goster(self, "Şifreniz güncellendi.")
            self.accept()


    # ==========================================================================
    def _qt_calistir():
        baslat()
        uygulama = QApplication(sys.argv)
        uygulama.setStyleSheet(TEMA)
        tutucu = {}

        def basarili(kullanici):
            tutucu["p"] = AnaPencere(kullanici)
            tutucu["p"].show()

        giris = GirisPenceresi(basarili)
        giris.show()
        sys.exit(uygulama.exec_())

    _qt_calistir()


if __name__ == "__main__":
    if "--qt" in sys.argv:
        qt_arayuzu()
    else:
        main()
