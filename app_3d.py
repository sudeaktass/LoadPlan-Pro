# -*- coding: utf-8 -*-
"""
LoadPlan Pro — Kurumsal 3D Araç Yükleme Optimizasyonu (v8)
===========================================================
Yeni:  Kullanıcı/Şirket oturumu · STEP/STL import · L/T/I profil
       NFP Nested Packing · Proje DB · PDF/Excel rapor
"""
import sys, io
# Windows cp1254 terminali emoji içeren print() çağrılarını çöküşten korur.
# Üç durum vardır:
#   1) Normal terminal      -> stdout'ta reconfigure() vardır
#   2) Ham bayt akışı       -> reconfigure yok ama .buffer var
#   3) Yakalanmış çıktı     -> ikisi de yok (ör. Streamlit stdout'u StringIO ile
#                              değiştirir). Bu durumda akış zaten metindir;
#                              dokunulmazsa sorun çıkmaz.
# 3. durum gözden kaçtığı için Streamlit altında AttributeError alınıyordu.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
elif hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# matplotlib backend'i pyplot import edilmeden ÖNCE ayarla
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as _plt_module  # noqa — erken import, backend kilitlenir

import streamlit as st
import time, tempfile, os
from pathlib import Path
import pandas as pd
from typing import Dict

# ── DB init ───────────────────────────────────────────────────────────────────
from database import init_db; init_db()

# ── Auth ──────────────────────────────────────────────────────────────────────
from auth import (is_logged_in, render_login_page, render_user_sidebar,
                  current_user, current_company, has_role, get_allowed_pages,
                  require_role)

# ── Mevcut modüller ───────────────────────────────────────────────────────────
from core_3d    import Piece3D, Truck3D, CuttingPlan3D, Placement3D
from plotly_3d  import (visualize_3d_plan, visualize_nfp_layout)

# ── Yeni modüller ─────────────────────────────────────────────────────────────
HAS_SHAPE    = False
HAS_TRIMESH  = False
HAS_SHAPELY  = False
_shape_import_error = None

def _check_pkg(name: str) -> bool:
    """importlib ile paket algılama — __import__'tan daha güvenilir."""
    import importlib.util
    return importlib.util.find_spec(name) is not None

try:
    from shape_engine import (load_from_file, load_all_stl_orientations,
                               l_profile, t_profile, i_profile,
                               hollow_cylinder, polygon_profile, shape_summary)
    from nfp_engine   import (pack_3d_with_nesting,)
    HAS_SHAPE = True
except Exception as _e:
    _shape_import_error = str(_e)

# trimesh ve shapely: shape_engine bağımsız kontrol
# importlib.util.find_spec daha güvenilir — farklı Python env'larda da çalışır
HAS_TRIMESH = _check_pkg("trimesh")
HAS_SHAPELY = _check_pkg("shapely")

_REPORTS_ERR = ""
try:
    from reports import generate_pdf_report, generate_excel_report
    HAS_REPORTS = True
except Exception as _e:
    HAS_REPORTS = False
    _REPORTS_ERR = str(_e)

import database as db_mod

# ── Otomatik Optimizer ────────────────────────────────────────────────────────
HAS_AUTO_OPT = False
_AUTO_OPT_ERROR = ""
try:
    from iterative_optimizer_3d import IterativeSearch, HybridPipeline, AdaptiveSearch
    HAS_AUTO_OPT = True
except Exception as _e:
    _AUTO_OPT_ERROR = str(_e)

# ── İleri Düzey Algoritmalar ──────────────────────────────────────────────────
HAS_BAYESIAN   = False
HAS_ISLAND_GA  = False
HAS_MULTISTART = False
HAS_FLEET_OPT  = False
# Hata sebepleri saklanır — "özellik yok" ile "modül bozuk" ayırt edilebilsin
# (eski `except: pass` syntax hatasını bile sessizce yutuyordu).
_ADV_IMPORT_ERRORS: dict = {}

try:
    from bayesian_optimizer_3d import bayesian_optimization_3d
    HAS_BAYESIAN = True
except Exception as _e:
    _ADV_IMPORT_ERRORS["bayesian"] = str(_e)

try:
    from island_genetic_3d import island_model_ga_3d
    HAS_ISLAND_GA = True
except Exception as _e:
    _ADV_IMPORT_ERRORS["island_ga"] = str(_e)

try:
    from multistart_sa_3d import multistart_sa_3d
    HAS_MULTISTART = True
except Exception as _e:
    _ADV_IMPORT_ERRORS["multistart_sa"] = str(_e)

try:
    from fleet_optimizer_3d import fleet_optimizer_3d
    HAS_FLEET_OPT = True
except Exception as _e:
    _ADV_IMPORT_ERRORS["fleet_opt"] = str(_e)

# ─────────────────────────────────────────────────────────────────────────────
# SAYFA YAPISI
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="LoadPlan Pro", page_icon="🚛",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.kpi-card{background:#161b22;border:1px solid rgba(56,139,253,.25);
  border-radius:12px;padding:1rem;text-align:center}
.kpi-label{color:#8b949e;font-size:.78rem;margin-bottom:4px}
.kpi-value{color:#e6edf3;font-size:1.55rem;font-weight:700}
.sec{font-size:1rem;font-weight:700;color:#e6edf3;
  border-left:3px solid #2196F3;padding-left:9px;margin:1rem 0 .4rem}
.badge-g{background:#1b5e20;color:#a5d6a7;padding:2px 8px;border-radius:10px;font-size:.8rem}
.badge-b{background:#0d47a1;color:#90caf9;padding:2px 8px;border-radius:10px;font-size:.8rem}
.badge-o{background:#e65100;color:#ffcc80;padding:2px 8px;border-radius:10px;font-size:.8rem}
</style>""", unsafe_allow_html=True)

# ── Giriş kontrolü ────────────────────────────────────────────────────────────
# LOADPLAN_GUEST_MODE=1 (varsayılan): giriş ekranı atlanır, gerçek bir
#   "Misafir" DB hesabıyla çalışılır (FK bütünlüğü korunur, proje kaydı çalışır).
# LOADPLAN_GUEST_MODE=0: normal giriş zorunlu — ÜRETİM DAĞITIMINDA BU KULLANILMALI.
_GUEST_MODE = os.getenv("LOADPLAN_GUEST_MODE", "1") == "1"

if not _GUEST_MODE:
    if not is_logged_in():
        render_login_page()
elif not st.session_state.get("user_id"):
    try:
        _g_co, _g_user = db_mod.get_or_create_guest()
        st.session_state["user_id"]    = _g_user.id
        st.session_state["company_id"] = _g_co.id
        st.session_state["current_user"] = {
            "id": _g_user.id, "email": _g_user.email,
            "full_name": _g_user.full_name, "role": _g_user.role,
            "company_id": _g_co.id,
        }
        st.session_state["current_company"] = {
            "id": _g_co.id, "name": _g_co.name, "slug": _g_co.slug,
            "plan": _g_co.plan, "logo_url": _g_co.logo_url,
        }
    except Exception as _ge:
        st.error(f"⚠️ Misafir hesabı oluşturulamadı: {_ge}")
        st.stop()

user = current_user()
co   = current_company()

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
render_user_sidebar()

ALGORITHMS = {
    "greedy_ep": {
        "name": "⚡ Greedy", "time": "< 1 sn", "advanced": False,
        "desc": "Online Best-Fit: parçaları GELİŞ SIRASINDA işler (boyuta göre ön-sıralama YOK) ve her parçayı, en az boş hacim bırakan (en dolu) uygun araca koyar — her adımda yerel-optimal seçim. FFD'den (=BFD) yalnızca azalan-sıralamada ayrışır; fark, sıralamanın katkısını ölçen kontrollü ablasyondur.",
        "pros": "Çok hızlı · Deterministik · Katı açgözlü (yerel-optimal) baseline",
        "cons": "Ön-sıralama yok → FFD'den düşük doluluk (sıralamanın katkısı)",
    },
    "ffd_ep": {
        "name": "📦 FFD", "time": "< 1 sn", "advanced": False,
        "desc": "Best-Fit Decreasing: büyükten küçüğe sıralar ve her parçayı yerleştirildikten sonra EN YÜKSEK doluluğu veren araca koyar (Greedy'den farkı budur). Hız/doluluk dengesi için önerilen başlangıç.",
        "pros": "Hızlı · Best-fit → Greedy'den iyi doluluk · Stabil",
        "cons": "Kompleks geometride sınırlı",
    },
    "layer_building": {
        "name": "🧱 Layer Building", "time": "< 5 sn", "advanced": False,
        "desc": "Yatay katmanlar oluşturarak istifler. Homojen boyutlu yüklerde çok etkili, düzenli ve öngörülebilir yerleşim sağlar.",
        "pros": "Düzenli istif · Hızlı",
        "cons": "Karışık boyutlarda orta",
    },
    "tabu_search": {
        "name": "🔍 Tabu Search", "time": "5–120 sn", "advanced": False,
        "desc": "Yerel arama + tabu listesi kombinasyonu. Daha önce denenen kötü hamleler yasaklanır, döngüden kaçınarak daha iyi çözüme ulaşır.",
        "pros": "Döngü yasaklar · İyi optimizasyon",
        "cons": "Parametre hassas · Orta süre",
    },
    "sa_hybrid": {
        "name": "🌡️ Sim. Annealing", "time": "5–120 sn", "advanced": False,
        "desc": "Isı-soğuma benzetmesi. Başta kötü hamleler de kabul edilerek yerel minimumdan kaçılır, süreç ilerledikçe hassaslaşır.",
        "pros": "Yerel minimumdan kaçar · Genel çözüm",
        "cons": "Soğuma hızı kritik",
    },
    "monte_carlo": {
        "name": "🎲 Monte Carlo", "time": "10–60 sn", "advanced": False,
        "desc": "Rastgele denemelerle istatistiksel optimizasyon. Geniş arama uzayını keşfeder; sonuç her çalıştırmada farklı olabilir.",
        "pros": "Geniş keşif · Paralel çalışabilir",
        "cons": "Tekrarlanabilirlik düşük",
    },
    "genetic": {
        "name": "🧬 Genetic Algorithm", "time": "30–120 sn", "advanced": False,
        "desc": "Evrimsel algoritma — popülasyon içindeki çözümler çaprazlama ve mutasyonla nesiller boyunca geliştirilir. Karmaşık problemlerde güçlü.",
        "pros": "Karmaşık problemler · Yüksek kalite",
        "cons": "Yavaş · Parametre hassas",
    },
    "bayesian": {
        "name": "🔬 Bayesian Optim.", "time": "60–300 sn", "advanced": True,
        "desc": "Optuna TPE (Tree-structured Parzen Estimator) ile hiperparametre optimizasyonu: seçilen algoritmanın (GA/SA/Tabu/MC) parametrelerini geçmiş denemelerden öğrenerek akıllıca arar.",
        "pros": "Akıllı parametre araması · Az deneme yeter",
        "cons": "Uzun süre · İç algoritmayı defalarca çalıştırır",
    },
    "island_ga": {
        "name": "🏝️ Island GA", "time": "60–300 sn", "advanced": True,
        "desc": "Birden fazla GA popülasyonu paralel çalışır ve belirli aralıklarla göç ile bilgi paylaşır. En kapsamlı evrimsel yaklaşım.",
        "pros": "Çok popülasyon · Göç ile bilgi paylaşımı",
        "cons": "En yavaş · Çok kaynak",
    },
    "multistart_sa": {
        "name": "🔁 Multi-Start SA", "time": "30–180 sn", "advanced": True,
        "desc": "Simüle tavlamayı birden fazla farklı başlangıç noktasından çalıştırır ve en iyi sonucu seçer. Güvenilir ve tekrarlanabilir.",
        "pros": "Güvenilir · Başlangıç bağımsız",
        "cons": "Uzun süre",
    },
}

# ── Şekil tipi → tablo SelectboxColumn seçenek eşlemesi ─────────────────────
# shape_engine.display_name "L Profil" (boşluklu) döndürür;
# SelectboxColumn ise "L-Profil" (tireli) bekler → uyuşmazlıkta Streamlit
# değeri "Dikdörtgen"e düşürür.  Bu dict tek yetkili dönüşüm tablosudur.
_SHAPE_TYPE_TO_LABEL: dict = {
    "box":             "Dikdörtgen",
    "cylinder":        "Silindir",
    "hollow_cylinder": "Boru",
    "l_profile":       "L-Profil",
    "t_profile":       "T-Profil",
    "i_profile":       "I-Profil",
    "polygon":         "Poligon",
    "custom":          "Dikdörtgen",
}
# Ters yön: tablo etiketi → shape_type (build_pieces_from_load_rules için)
_LABEL_TO_SHAPE_TYPE: dict = {v: k for k, v in _SHAPE_TYPE_TO_LABEL.items()}


def _shape_label(info) -> str:
    """ShapeInfo nesnesinden doğru tablo etiketini döndürür."""
    return _SHAPE_TYPE_TO_LABEL.get(
        getattr(info, "shape_type", "box"), "Dikdörtgen"
    )


with st.sidebar:
    st.markdown("""
<style>
div[data-testid="stSidebarNav"] {display:none}
.nav-btn {
    display:block; width:100%; padding:10px 16px; margin:4px 0;
    border-radius:10px; border:none; cursor:pointer; text-align:left;
    font-size:15px; font-weight:500; transition:all .2s;
    background:rgba(255,255,255,0.05); color:#cdd6f4;
}
.nav-btn:hover {background:rgba(255,255,255,0.12); color:#fff;}
.nav-btn.active {background:linear-gradient(90deg,#1e90ff22,#1e90ff44);
    color:#89b4fa; border-left:3px solid #89b4fa;}
</style>""", unsafe_allow_html=True)
    st.markdown("#### 📌 Navigasyon")
    # R4 fix — rol bazlı sayfa filtresi (operator → 3 sayfa, admin/manager → 4 sayfa)
    _pages = get_allowed_pages(user["role"])
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "🚀 Optimizasyon"
    # R4: Eğer kaydedilmiş sayfa kullanıcının yetkisi dışındaysa, varsayılana dön
    if st.session_state.nav_page not in _pages:
        st.session_state.nav_page = "🚀 Optimizasyon"
    for _p in _pages:
        _active = "active" if st.session_state.nav_page == _p else ""
        if st.button(_p, key=f"nav_{_p}", width="stretch"):
            st.session_state.nav_page = _p
            st.rerun()
    page = st.session_state.nav_page
    st.markdown("---")

    # Optimizasyon sayfasına özel sidebar araçları
    if page == "🚀 Optimizasyon":

        st.header("🚚 Araç Filosu")

        # ── Filo sayfasından çekici+dorse seçildiyse ONU göster ──────────
        # Aksi hâlde kenar çubuğu eski tabloyu gösterip "4 araç / 28.000 kg"
        # derken optimizasyon başka bir filoyla çalışıyordu.
        from filo_secimi import aktif_filo, eski_tablo_ayarla
        _sb_ck, _sb_dr = aktif_filo()
        if _sb_ck and _sb_dr:
            from filo_havuzu import havuz_olustur_cekici_dorse
            _sb_havuz = havuz_olustur_cekici_dorse(_sb_ck, _sb_dr)
            _sb_trucks = list(_sb_havuz.trucks)

            st.success(f"✅ **Çekici + dorse filosu** — {len(_sb_ck)} çekici, "
                       f"{len(_sb_dr)} dorse")
            st.caption("🚚 Filo sayfasında seçildi. Bu liste bir **tavandır**; "
                       "hangi araçların açılacağına algoritma karar verir.")

            _sb_satir = []
            for _t in _sb_trucks:
                _es = _t.eslesme
                _sb_satir.append({
                    "Çekici": _es.cekici.plaka,
                    "Dorse": _es.dorse.plaka,
                    "Hacim (m³)": round(_es.dorse.ic_hacim_m3, 1),
                    "Faydalı yük (kg)": int(_es.faydali_yuk_kg),
                    "Dingil": "✅" if _es.dingil_kontrol_edilebilir else "⚠️",
                })
            st.dataframe(pd.DataFrame(_sb_satir), hide_index=True,
                         width="stretch")

            _c1, _c2 = st.columns(2)
            _c1.metric("Toplam Araç", len(_sb_trucks))
            _c2.metric("Faydalı yük",
                       f'{sum(t.capacity for t in _sb_trucks):,.0f} kg')
            if any(not t.eslesme.dingil_kontrol_edilebilir for t in _sb_trucks):
                st.warning("⚠️ Bazı araçlarda dingil kontrolü yapılamıyor — "
                           "eksik veri. 🚚 Filo sayfasından tamamlayın.")
            if len(_sb_dr) > len(_sb_ck):
                st.warning(f"⚠️ {len(_sb_dr) - len(_sb_ck)} dorse için boş "
                           f"çekici yok → o dorseler açılamaz.")

            if st.button("↩️ Eski araç tablosuna dön", width="stretch",
                         key="sb_filo_birak"):
                eski_tablo_ayarla(True)
                st.rerun()

            df_trucks = st.session_state.get(
                "df_trucks_live", st.session_state.get("df_trucks",
                                                       pd.DataFrame()))
            st.markdown("---")
            st.header("🎯 Algoritma")
            _filo_sayfasindan = True
        else:
            _filo_sayfasindan = False

        # Çekici+dorse filosu seçilmediyse ESKİ araç tablosu kullanılır
        if not _filo_sayfasindan:
            if "df_trucks" not in st.session_state:
                st.session_state.df_trucks = pd.DataFrame({
                    "ID":            ["Küçük-1", "Orta-1", "Büyük-1"],
                    "Genişlik (cm)": [170, 180, 240],
                    "Uzunluk (cm)":  [260, 420, 600],
                    "Yükseklik (cm)":[180, 220, 270],
                    "Kapasite (kg)": [6000, 7000, 8000],
                    "Adet":          [1, 2, 1],
                })
            # KRİTİK: data_editor'a stabil bir 'key' verilir ve çıktısı ASLA
            # editörün veri kaynağına (st.session_state.df_trucks) geri yazılmaz.
            # Geri yazılırsa Streamlit edit-delta'larını edilmiş veriye TEKRAR
            # uygular → yazarken sıfırlanma/silinme olur. Düzenlenmiş hali ayrı
            # 'df_trucks_live' anahtarında tutulur (diğer sayfalar bunu okur).
            df_trucks = st.data_editor(st.session_state.df_trucks, num_rows="dynamic",
                width="stretch",
                key="df_trucks_editor",
                column_config={
                    "ID":             st.column_config.TextColumn("ID", required=True),
                    "Genişlik (cm)":  st.column_config.NumberColumn("G(cm)",  min_value=1),
                    "Uzunluk (cm)":   st.column_config.NumberColumn("U(cm)",  min_value=1),
                    "Yükseklik (cm)": st.column_config.NumberColumn("Y(cm)",  min_value=1),
                    "Kapasite (kg)":  st.column_config.NumberColumn("Kap(kg)",min_value=1),
                    "Adet":           st.column_config.NumberColumn("Adet",   min_value=1),
                })
            st.session_state.df_trucks_live = df_trucks
            c1,c2 = st.columns(2)
            # Düzenleme sırasında boş hücre (NaN) olabilir → fillna ile koru
            _adet_t = df_trucks["Adet"].fillna(0)
            _kap_t  = df_trucks["Kapasite (kg)"].fillna(0)
            c1.metric("Toplam Araç",    int(_adet_t.sum()))
            c2.metric("Kapasite", f'{float((_kap_t * _adet_t).sum()):,.0f} kg')
            st.markdown("---")

            st.header("🎯 Algoritma")

        pass  # tooltip motoru ana sayfada (aşağıda)

        mode = st.selectbox("Mod", ["🎯 Tek", "📊 Karşılaştırmalı"],
                            key="_algo_mode")

        st.info(
            "🚛 Girdiğiniz filo bir **tavandır**.\n"
            "Hangi araçların kullanılacağına algoritma karar verir."
        )
        sel_algo  = None
        sel_algos = []

        _std_keys = [k for k,v in ALGORITHMS.items() if not v["advanced"]]
        _adv_keys = [k for k,v in ALGORITHMS.items() if v["advanced"]]

        if mode == "🎯 Tek":
            st.caption("**Standart**")
            keys   = _std_keys
            labels = [ALGORITHMS[k]["name"] for k in keys]
            # Öneri kartından gelen seçimi session_state'e aktar (tek seferlik)
            _tek_sel = st.session_state.get("_tek_sel_key", None)
            if "_tek_sel_key" in st.session_state:
                del st.session_state["_tek_sel_key"]
            if _tek_sel in keys:
                st.session_state["_std_radio"] = keys.index(_tek_sel)
            _initial_radio = st.session_state.get("_std_radio", 1)
            idx = st.radio("std", range(len(keys)), format_func=lambda i: labels[i],
                           index=_initial_radio, label_visibility="collapsed",
                           key="_std_radio")
            sel_algo = keys[idx]
            st.caption(f"⏱️ {ALGORITHMS[sel_algo]['time']}")

            st.markdown("---")
            # KARAR A (21 Ekim 2026): Multi-Start SA, Island GA ve BO-HPO
            # DONDURULDU — ana karşılaştırmadan ve deneyden çıktılar.
            # Kodları duruyor, mantıklarına dokunulmadı; varyant analizi
            # için buradan çalıştırılabilirler.
            st.caption("**📦 Arşiv / varyantlar** — dondurulmuş, "
                       "ana karşılaştırmaya girmez")
            _adv_labels = []
            for k in _adv_keys:
                _disabled = (k == "bayesian" and not HAS_BAYESIAN) or \
                            (k == "island_ga" and not HAS_ISLAND_GA) or \
                            (k == "multistart_sa" and not HAS_MULTISTART)
                _lbl = ALGORITHMS[k]["name"] + (" ⏱️ " + ALGORITHMS[k]["time"])
                if not _disabled:
                    _adv_labels.append((k, _lbl))

            if _adv_labels:
                _adv_choice = st.radio(
                    "adv", ["(Seçme)"] + [l for _, l in _adv_labels],
                    label_visibility="collapsed"
                )
                for k, l in _adv_labels:
                    if _adv_choice == l:
                        sel_algo = k
                        st.caption(f"⏱️ {ALGORITHMS[k]['time']}")
                        break
            else:
                st.info("İleri düzey dosyalar klasörde bulunamadı.")
            # Yüklenemeyen modüllerin SEBEBİNİ göster (sessiz maskelenmesin)
            for _mk, _merr in _ADV_IMPORT_ERRORS.items():
                if _mk in ("bayesian", "island_ga", "multistart_sa"):
                    st.caption(f"⚠️ `{_mk}` yüklenemedi: {_merr[:120]}")

        else:
            _c1, _c2 = st.columns(2)
            if _c1.button("✅ Hepsini Seç", width="stretch"):
                # Dondurulmuş varyantlar (advanced) seçilmez — karar A
                for _k, _v in ALGORITHMS.items():
                    if not _v["advanced"]:
                        st.session_state[f"cmp_{_k}"] = True
            if _c2.button("❌ Hepsini Temizle", width="stretch"):
                for _k in ALGORITHMS:
                    st.session_state[f"cmp_{_k}"] = False

            st.caption("**Standart**")
            for k in _std_keys:
                v = ALGORITHMS[k]
                _def = k in ("ffd_ep", "layer_building")
                if f"cmp_{k}" not in st.session_state:
                    st.session_state[f"cmp_{k}"] = _def
                if st.checkbox(v["name"], key=f"cmp_{k}"):
                    sel_algos.append(k)

            st.markdown("---")
            st.caption("**🔬 İleri Düzey**")
            for k in _adv_keys:
                v = ALGORITHMS[k]
                _disabled = (k == "bayesian" and not HAS_BAYESIAN) or \
                            (k == "island_ga" and not HAS_ISLAND_GA) or \
                            (k == "multistart_sa" and not HAS_MULTISTART)
                if not _disabled:
                    if f"cmp_{k}" not in st.session_state:
                        st.session_state[f"cmp_{k}"] = False
                    if st.checkbox(v["name"], key=f"cmp_{k}"):
                        sel_algos.append(k)
                else:
                    st.caption(f"~~{v['name']}~~ (dosya bulunamadı)")

        st.markdown("---")
        st.header("⚙️ Parametreler")
        active = [sel_algo] if sel_algo else sel_algos
        ts_time=30; ts_tenure=7; sa_time=30; sa_temp=1000.0; sa_cool=0.995
        mc_iter=100; ga_pop=50; ga_gen=100; ga_time=60; ga_workers=0
        layer_strat="adaptive"
        nfp_res=2.0; nfp_margin=0.5

        # ── Tekrarlanabilirlik: sabit rastgelelik tohumu (seed) ───────────
        _use_seed = st.checkbox(
            "🎯 Sabit Seed (tekrarlanabilir sonuç)", value=False,
            help="İşaretlenirse tüm stokastik algoritmalar (Tabu, SA, GA, Island, "
                 "MC, Multi-Start) sabit rastgelelik tohumuyla çalışır → aynı girdi "
                 "her seferinde aynı sonucu verir. Adil/tekrarlanabilir karşılaştırma için.")
        rng_seed = int(st.number_input("Seed değeri", 0, 999999, 42, 1,
                                       disabled=not _use_seed)) if _use_seed else None

        with st.expander("🔍 Tabu Search", expanded="tabu_search" in active):
            ts_time   = st.slider("Süre (sn)",5,120,30,5)
            ts_tenure = st.slider("Tenure",3,20,7)
        with st.expander("🌡️ Simulated Annealing", expanded="sa_hybrid" in active):
            sa_time = st.slider("Süre",5,120,30,5,key="sa_t")
            sa_temp = float(st.slider("Başlangıç T",100,5000,1000,100))
            sa_cool = float(st.slider("Soğuma",0.990,0.999,0.995,0.001,format="%.3f"))
        with st.expander("🎲 Monte Carlo", expanded="monte_carlo" in active):
            mc_iter = st.slider("Deneme",10,500,100,10)
        with st.expander("🧬 Genetic Algorithm", expanded="genetic" in active):
            ga_pop = st.slider("Popülasyon",10,200,50,10)
            ga_gen = st.slider("Nesil",10,500,100,10)
            ga_time = st.slider("Maks. Süre (sn, 0=sınırsız)", 0, 300, 60, 15,
                help="Süre dolunca GA erken biter — en iyi bulunan çözüm döner.")
            ga_workers = st.slider("Paralel işçi (0=kapalı)", 0, 8, 0, 1,
                help="Birey değerlendirmelerini çok çekirdekte paralel koşar. "
                     "Sonuç sıralı koşuyla aynıdır; ilk açılışta süreç havuzu "
                     "kurulumu birkaç saniye sürer. Büyük problemlerde önerilir.")
        with st.expander("🧱 Layer Building", expanded="layer_building" in active):
            layer_strat = st.selectbox("Strateji",["max","adaptive","median"])

        # İleri düzey parametre bölümü
        bay_time=120; bay_trials=40; bay_target="auto"
        isl_islands=4; isl_pop=25; isl_gen=80; isl_mig=15
        isl_time=120; isl_workers=0
        ms_starts=5; ms_time=90

        st.markdown("**🔬 İleri Düzey Parametreler**")
        with st.expander("🔬 Bayesian Optimizasyon", expanded="bayesian" in active):
            bay_time   = st.slider("Bütçe (sn)", 30, 300, 120, 15, key="bay_t")
            bay_trials = st.slider("Maks. Deneme", 10, 100, 40, 5)
            bay_target = st.selectbox("Optimize Edilen", ["auto","Genetic","SA","Tabu","MonteCarlo"])
        with st.expander("🏝️ Island GA", expanded="island_ga" in active):
            isl_islands = st.slider("Ada Sayısı", 2, 8, 4, 1)
            isl_pop     = st.slider("Ada Popülasyonu", 10, 60, 25, 5)
            isl_gen     = st.slider("Nesil", 30, 200, 80, 10)
            isl_mig     = st.slider("Göç Aralığı", 5, 30, 15, 5)
            isl_time    = st.slider("Maks. Süre (sn, 0=sınırsız)", 0, 600, 120, 30,
                help="Süre dolunca en iyi bulunan çözümle erken biter.")
            isl_workers = st.slider("Paralel işçi (0=kapalı)", 0, 8, 0, 1,
                key="isl_wrk",
                help="Tüm adaların birey değerlendirmelerini çok çekirdekte "
                     "paralel koşar; sonuç sıralı koşuyla birebir aynıdır.")
        with st.expander("🔁 Multi-Start SA", expanded="multistart_sa" in active):
            ms_starts = st.slider("Başlangıç Noktası", 2, 10, 5, 1)
            ms_time   = st.slider("Toplam Süre (sn)", 30, 300, 90, 15, key="ms_t")

        st.markdown("---")
        st.header("🚛 Akıllı Araç Seçimi")
        if HAS_AUTO_OPT:
            auto_time_budget = st.slider("Araç arama süresi (sn)", 30, 600, 120, 30,
                help="Aşağıdaki 'Akıllı Araç Seçimi' açıkken, en iyi araç "
                     "kombinasyonunu aramak için ayrılan süre.")
        else:
            if _AUTO_OPT_ERROR:
                st.error(f"Yükleme hatası:\n`{_AUTO_OPT_ERROR}`")
            else:
                st.warning("iterative_optimizer_3d.py bulunamadı")

        st.markdown("---")
        st.header("🎨 Görsel")
        show_truck  = st.checkbox("Araç kutusu", value=True)
        show_grid   = st.checkbox("Grid", value=True)
        show_weight = False
        show_nfp2d  = st.checkbox("2D Kesit planı", value=True)

        st.markdown("---")
        st.header("⚖️ Yükleme Stratejisi")
        compact_fwd = st.checkbox(
            "🔧 Öne Sıkıştır (Compact Forward)",
            value=True,
            help="Optimizasyon sonrası parçaları araç önüne doğru kaydırır — "
                 "CoG öne taşınır, arka boşluklar doldurulabilir hale gelir."
        )
        st.caption(
            "💡 Ağır parçalar zaten önce yerleştirilir. "
            "Bu seçenek ek olarak tüm parçaları öne sıkıştırır."
        )

        # ── KARAR K (21 Ekim 2026): "Akıllı Araç Seçimi" GİZLENDİ ────────
        # fleet_optimizer_3d K4 ile çelişiyor: K4'e göre kullanıcının
        # girdiği filo bir TAVANDIR ve araç seçimini algoritma kendi yapar
        # (filo_havuzu). Bu düğme ise algoritmadan önce bir araç
        # kombinasyonu sabitliyordu — yani sorun #1'in başka bir biçimi.
        # Kod SİLİNMEDİ: ileride "filo büyüklüğü ve bileşimi" senaryosu
        # için kullanılabilir (Koç ve ark. 2016, FSM ↔ HF ayrımı).
        use_fleet_opt = False
        if False:
            st.caption(
                "⚠️ Her çalıştırmaya toplam bütçenin **~%35'i** ek süre ekler. "
                "Örn: 120sn bütçede ilk 42sn araç seçimine gider."
            )
            if not HAS_FLEET_OPT:
                _fo_err = _ADV_IMPORT_ERRORS.get("fleet_opt", "dosya bulunamadı")
                st.error(f"fleet_optimizer_3d yüklenemedi ({_fo_err[:120]}) — toggle devre dışı.")
                use_fleet_opt = False

    else:  # Diğer sayfalar için varsayılanlar
        # Düzenlenmiş araç tablosu df_trucks_live'da; yoksa base'e düş
        df_trucks = st.session_state.get("df_trucks_live",
                        st.session_state.get("df_trucks", pd.DataFrame()))
        mode="🎯 Tek"; sel_algo="ffd_ep"; sel_algos=[]
        active=["ffd_ep"]; ts_time=30; ts_tenure=7; sa_time=30; rng_seed=None
        sa_temp=1000.0; sa_cool=0.995; mc_iter=100; ga_pop=50; ga_gen=100
        ga_time=60; ga_workers=0
        layer_strat="adaptive"; nfp_res=2.0; nfp_margin=0.5
        show_truck=show_grid=show_nfp2d=True; show_weight=False; compact_fwd=True; use_fleet_opt=False

# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCI FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# EXCEL IMPORT / EXPORT YARDIMCILARI
# ─────────────────────────────────────────────────────────────────────────────

# Kolon eşleştirme — Excel'den gelen başlıkları uygulama sütunlarına çevirir
_TRUCK_COL_MAP = {
    "id": "ID", "araç id": "ID", "arac id": "ID",
    "genişlik (cm)": "Genişlik (cm)", "genislik (cm)": "Genişlik (cm)",
    "genişlik": "Genişlik (cm)", "genislik": "Genişlik (cm)", "g(cm)": "Genişlik (cm)",
    "uzunluk (cm)": "Uzunluk (cm)", "uzunluk": "Uzunluk (cm)", "u(cm)": "Uzunluk (cm)",
    "yükseklik (cm)": "Yükseklik (cm)", "yukseklik (cm)": "Yükseklik (cm)",
    "yükseklik": "Yükseklik (cm)", "yukseklik": "Yükseklik (cm)", "y(cm)": "Yükseklik (cm)",
    "kapasite (kg)": "Kapasite (kg)", "kapasite": "Kapasite (kg)", "kap(kg)": "Kapasite (kg)",
    "adet": "Adet",
}

_LOAD_COL_MAP = {
    "id": "ID", "yük id": "ID", "yuk id": "ID",
    "şekil": "Şekil", "sekil": "Şekil",
    "genişlik (cm)": "Genişlik (cm)", "genislik (cm)": "Genişlik (cm)",
    "genişlik": "Genişlik (cm)", "genislik": "Genişlik (cm)", "g(cm)": "Genişlik (cm)",
    "uzunluk (cm)": "Uzunluk (cm)", "uzunluk": "Uzunluk (cm)", "u(cm)": "Uzunluk (cm)",
    "yükseklik (cm)": "Yükseklik (cm)", "yukseklik (cm)": "Yükseklik (cm)",
    "yükseklik": "Yükseklik (cm)", "yukseklik": "Yükseklik (cm)", "y(cm)": "Yükseklik (cm)",
    "ağırlık (kg)": "Ağırlık (kg)", "agirlik (kg)": "Ağırlık (kg)",
    "ağırlık": "Ağırlık (kg)", "agirlik": "Ağırlık (kg)", "ağırlık(kg)": "Ağırlık (kg)",
    "adet": "Adet",
    "müşteri": "Müşteri", "musteri": "Müşteri", "customer": "Müşteri",
    "altına yerleştirilemez": "Altına yerleştirilemez",
    "altina yerlestirilmez": "Altına yerleştirilemez",
    "altına yük konmasın": "Altına yerleştirilemez",
    "üstüne yerleştirilemez": "Üstüne yerleştirilemez",
    "ustune yerlestirilmez": "Üstüne yerleştirilemez",
    "üstüne yük konmasın": "Üstüne yerleştirilemez",
    "kırılgan": "Üstüne yerleştirilemez",
    "rotasyon": "Rotasyon", "rotation": "Rotasyon",
    "min. aralık (cm)": "Min. Aralık (cm)", "min aralık": "Min. Aralık (cm)",
    "min. aralik (cm)": "Min. Aralık (cm)", "aralik": "Min. Aralık (cm)",
    "öncelik": "Öncelik", "oncelik": "Öncelik", "priority": "Öncelik",
}


def _normalize_col(name: str) -> str:
    """Sütun adını normalleştirir: küçük harf, boşluk temizle."""
    return str(name).strip().lower()


def _map_df_columns(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """Excel'den okunan sütun isimlerini uygulama sütunlarına çevirir."""
    rename = {}
    for col in df.columns:
        normalized = _normalize_col(col)
        if normalized in col_map:
            rename[col] = col_map[normalized]
    return df.rename(columns=rename)


def _parse_bool_col(series: pd.Series) -> pd.Series:
    """EVET/HAYIR, True/False, 1/0 → bool dönüşümü."""
    def _to_bool(v):
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return s in ("evet", "true", "1", "yes", "e", "t")
    return series.map(_to_bool)


def import_excel(file_bytes) -> tuple:
    """
    Excel dosyasını okur, (df_trucks, df_pallets, errors) döndürür.
    Banner satırı (1. satır başlık) veya açıklama satırlarını otomatik atlar.
    """
    errors = []
    df_trucks_out  = None
    df_pallets_out = None

    try:
        xls = pd.ExcelFile(file_bytes)
    except Exception as e:
        return None, None, [f"Excel okunamadı: {e}"]

    def _read_smart(sheet_name, col_map, required_cols):
        """
        Sayfayı okur; önce header=0, olmadıysa header=1 dener.
        Açıklama satırlarını (sayısal değer içermeyen ID) otomatik atar.
        """
        for hdr in [0, 1, 2]:
            try:
                df = pd.read_excel(file_bytes, sheet_name=sheet_name,
                                   header=hdr, dtype=str)
                df = df.dropna(how="all")
                df = _map_df_columns(df, col_map)
                if all(c in df.columns for c in required_cols):
                    return df, None
            except Exception:
                continue
        return None, f"'{sheet_name}' sayfasında sütunlar bulunamadı. Beklenen: {required_cols}"

    def _clean_id_col(df):
        """
        ID sütununu temizler: banner, açıklama ve boş satırları düşürür.
        Geçerli satır = ID'si olan ve sayısal boyut içeren satır.
        """
        df["ID"] = df["ID"].astype(str).str.strip()
        # Geçersiz ID'leri filtrele
        _bad = ["nan", "", "none", "benzersiz id", "araç id", "yük id",
                "id", "açıklama", "aciklama"]
        df = df[~df["ID"].str.lower().isin(_bad)]
        df = df[~df["ID"].str.startswith("ℹ")]
        df = df[~df["ID"].str.startswith("─")]
        df = df[~df["ID"].str.startswith("🚛")]
        df = df[~df["ID"].str.startswith("📦")]
        return df.reset_index(drop=True)

    # ── Araçlar sayfası ──────────────────────────────────────────────────────
    truck_sheet = None
    for name in xls.sheet_names:
        if any(k in name.lower() for k in ("araç", "arac", "truck", "vehicle", "fleet")):
            truck_sheet = name
            break
    if truck_sheet is None:
        truck_sheet = xls.sheet_names[0]

    required_t = ["ID", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
                  "Kapasite (kg)", "Adet"]
    try:
        df_t, err_t = _read_smart(truck_sheet, _TRUCK_COL_MAP, required_t)
        if err_t:
            errors.append(f"Araçlar sayfası: {err_t}")
        else:
            df_t = _clean_id_col(df_t)
            for num_col in ["Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
                            "Kapasite (kg)", "Adet"]:
                df_t[num_col] = pd.to_numeric(df_t[num_col], errors="coerce")
            df_t = df_t.dropna(subset=["Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)"])
            df_t = df_t[df_t["ID"] != ""]
            for c in ["Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)", "Kapasite (kg)", "Adet"]:
                df_t[c] = df_t[c].fillna(1).astype(int)
            df_trucks_out = df_t[required_t].reset_index(drop=True)
    except Exception as e:
        errors.append(f"Araçlar sayfası işlenirken hata: {e}")

    # ── Yükler sayfası ───────────────────────────────────────────────────────
    load_sheet = None
    for name in xls.sheet_names:
        if any(k in name.lower() for k in ("yük", "yuk", "load", "palet", "kargo", "cargo")):
            load_sheet = name
            break
    if load_sheet is None and len(xls.sheet_names) >= 2:
        load_sheet = xls.sheet_names[1]
    elif load_sheet is None:
        load_sheet = xls.sheet_names[0]

    required_l = ["ID", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
                  "Ağırlık (kg)", "Adet"]
    try:
        df_l, err_l = _read_smart(load_sheet, _LOAD_COL_MAP, required_l)
        if err_l:
            errors.append(f"Yükler sayfası: {err_l}")
        else:
            df_l = _clean_id_col(df_l)

            # Şekil
            if "Şekil" not in df_l.columns:
                df_l["Şekil"] = "Dikdörtgen"
            else:
                df_l["Şekil"] = df_l["Şekil"].fillna("Dikdörtgen").astype(str).str.strip()
                df_l["Şekil"] = df_l["Şekil"].apply(
                    lambda v: "Silindir" if "silind" in str(v).lower() else "Dikdörtgen")

            # Sayısal
            for num_col in ["Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
                            "Ağırlık (kg)", "Adet"]:
                df_l[num_col] = pd.to_numeric(df_l[num_col], errors="coerce")
            df_l = df_l.dropna(subset=["Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)"])
            for c in ["Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)", "Adet"]:
                df_l[c] = df_l[c].fillna(1).astype(int)
            df_l["Ağırlık (kg)"] = df_l["Ağırlık (kg)"].fillna(0).astype(float)

            # Müşteri
            if "Müşteri" not in df_l.columns:
                df_l["Müşteri"] = ""
            else:
                df_l["Müşteri"] = df_l["Müşteri"].fillna("").astype(str).str.strip()
                df_l["Müşteri"] = df_l["Müşteri"].replace("nan", "")

            # Bool kolonlar
            for bool_col, default in [
                ("Altına yerleştirilemez", False),
                ("Üstüne yerleştirilemez", False),
                ("Rotasyon", True),
            ]:
                if bool_col not in df_l.columns:
                    df_l[bool_col] = default
                else:
                    df_l[bool_col] = _parse_bool_col(df_l[bool_col])

            # Min. Aralık
            if "Min. Aralık (cm)" not in df_l.columns:
                df_l["Min. Aralık (cm)"] = 0
            else:
                df_l["Min. Aralık (cm)"] = pd.to_numeric(
                    df_l["Min. Aralık (cm)"], errors="coerce").fillna(0).astype(int)

            # Öncelik (M kolonu — opsiyonel)
            if "Öncelik" not in df_l.columns:
                df_l["Öncelik"] = None
            else:
                df_l["Öncelik"] = df_l["Öncelik"].apply(
                    lambda v: int(float(v))
                    if v is not None and str(v).strip() not in ("", "nan", "None")
                    else None
                )

            final_cols = ["ID", "Şekil", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
                          "Ağırlık (kg)", "Adet", "Müşteri",
                          "Altına yerleştirilemez", "Üstüne yerleştirilemez",
                          "Rotasyon", "Min. Aralık (cm)", "Öncelik"]
            df_pallets_out = df_l[final_cols].reset_index(drop=True)

    except Exception as e:
        errors.append(f"Yükler sayfası işlenirken hata: {e}")

    return df_trucks_out, df_pallets_out, errors


def compact_forward(plan, pieces, trucks):
    """
    Parçaları Y (araç önüne) ve X (sol duvara) yönünde sıkıştırır.
    Öncelik bölgeleri korunur.

    Arama yönü: floor'dan mevcut pozisyona YUKARI tarar ve ilk geçerli
    pozisyonu seçer — bu, mümkün olan minimum değeri garantiler.
    (Yukarıdan aşağı arama, çakışma alanının ötesindeki boş bölgeleri
    atlayabildiğinden hatalıydı.)
    """
    from core_3d import (check_collision_with_list, is_within_bounds_3d,
                         check_support_3d, check_stacking_rules,
                         calculate_xy_overlap_area, Placement3D)
    from priority_utils import get_priority_zone

    piece_info = {p.id: p for p in pieces}

    def _ok(pl, nx, ny, others, truck):
        """(nx, ny) konumunun geçerli olup olmadığını döner.

        DÜZELTME: Eski kod yalnızca taşınan parçanın kendi desteğini kontrol
        ediyordu — parça, üstünde duran yığının altından çekilebiliyor ve
        üstteki parçalar havada kalıyordu. Artık (1) taşınan parça için
        istif kuralları (kırılgan/istif ağırlığı) yeniden doğrulanır,
        (2) taşınan parçanın ÜSTÜNDE duran her parçanın desteği, taşıma
        sonrası konfigürasyonda yeniden kontrol edilir.
        """
        tmp = Placement3D(nx, ny, pl.z, pl.width, pl.length, pl.height,
                          pl.piece_id, pl.rotation, pl.bin_id)
        if not is_within_bounds_3d(tmp, truck):
            return False
        if check_collision_with_list(tmp, others, piece_info=piece_info):
            return False
        if pl.z > 0 and not check_support_3d(tmp, others,
                                              min_support_ratio=0.80,
                                              piece_info=piece_info):
            return False
        # (1) Taşınan parça yeni konumda istif kurallarına uymalı
        piece = piece_info.get(pl.piece_id)
        if piece is not None:
            valid, _ = check_stacking_rules(tmp, piece, others, piece_info)
            if not valid:
                return False
        # (2) Eski konumda bu parçanın üstünde duranlar desteksiz kalmamalı
        moved_top = pl.z + pl.height
        for o in others:
            if abs(o.z - moved_top) >= 1:
                continue
            if calculate_xy_overlap_area(
                    o.x, o.y, o.width, o.length,
                    pl.x, pl.y, pl.width, pl.length) <= 0:
                continue   # bu parça taşınanın üstünde durmuyordu
            new_env = [x for x in others if x is not o] + [tmp]
            if not check_support_3d(o, new_env,
                                    min_support_ratio=0.80,
                                    piece_info=piece_info):
                return False
        return True

    def _slide_y(pl, others, truck):
        """Parçayı Y=floor'dan başlayarak yukarı tarayarak minimum Y'ye taşı."""
        piece = piece_info.get(pl.piece_id)
        prio  = getattr(piece, 'priority', None) if piece else None
        y_min_zone, _ = get_priority_zone(truck.length, prio)
        floor = max(0, y_min_zone)
        if pl.y <= floor:
            return
        # floor'dan pl.y'ye kadar tara — ilk geçerli pozisyon = minimum
        step = max(1, pl.length // 20)   # kaba adım (hız için)
        best = pl.y
        for v in range(floor, pl.y, step):
            if _ok(pl, pl.x, v, others, truck):
                # İnce ayar: v'den biraz geriye bak
                best = v
                for fv in range(v - 1, floor - 1, -1):
                    if _ok(pl, pl.x, fv, others, truck):
                        best = fv
                    else:
                        break
                break
        pl.y = best

    def _slide_x(pl, others, truck):
        """Parçayı X=0'dan başlayarak yukarı tarayarak minimum X'e taşı."""
        if pl.x <= 0:
            return
        step = max(1, pl.width // 20)
        best = pl.x
        for v in range(0, pl.x, step):
            if _ok(pl, v, pl.y, others, truck):
                best = v
                for fv in range(v - 1, -1, -1):
                    if _ok(pl, fv, pl.y, others, truck):
                        best = fv
                    else:
                        break
                break
        pl.x = best

    def _pass_y(placements, truck):
        placements.sort(key=lambda p: (p.z, p.y))
        for i, pl in enumerate(placements):
            _slide_y(pl, [p for j, p in enumerate(placements) if j != i], truck)

    def _pass_x(placements, truck):
        placements.sort(key=lambda p: (p.z, p.x))
        for i, pl in enumerate(placements):
            _slide_x(pl, [p for j, p in enumerate(placements) if j != i], truck)

    for bin_id, placements in enumerate(plan.bins):
        if not placements:
            continue
        truck_id = plan.truck_assignments.get(bin_id)
        truck = next((t for t in trucks if t.id == truck_id),
                     trucks[0] if trucks else None)
        if not truck:
            continue
        _pass_y(placements, truck)
        _pass_y(placements, truck)
        _pass_y(placements, truck)
        _pass_x(placements, truck)

    return plan


# NOT: Eski build_pieces() fonksiyonu kaldırıldı — hiçbir yerden çağrılmıyordu
# (ölü kod) ve clearance/öncelik/geom-fallback içermediği için yanlışlıkla
# canlandırılması sessiz kural kaybına yol açacaktı. Tek yetkili üretici:
# build_pieces_from_load_rules().


def build_pieces_from_load_rules(load_rules_df: "pd.DataFrame", geom_store: dict):
    """
    Algoritmaya gönderilecek Piece3D listesini YALNIZCA load_rules tablosundan oluşturur.
    Kullanıcının sildiği parçalar buraya gelmez.
    geom_store: STL/STEP ve profillerin mesh/geometri verisi {piece_id: {...}}
    """
    if load_rules_df is None or load_rules_df.empty:
        return []

    # Duplicate ID'leri birleştir: aynı ID'den birden fazla satır varsa TOPLAMA — son satırı kullan
    # (sum kullanmak Adet'i kat kat artırır; en son eklenen/güncellenen satır doğrudur)
    if "ID" in load_rules_df.columns and load_rules_df["ID"].duplicated().any():
        load_rules_df = load_rules_df.drop_duplicates(subset=["ID"], keep="last").reset_index(drop=True)

    pieces = []
    for _, row in load_rules_df.iterrows():
        try:
            pid   = str(row["ID"])
            adet  = int(row.get("Adet", 1))
            if adet <= 0:
                continue

            # Şekil
            sekil = str(row.get("Şekil", "Dikdörtgen"))
            shape = "cylinder" if "Silindir" in sekil or sekil == "cylinder" else "box"

            w = max(1, round(float(row.get("G(cm)", 10))))
            l = max(1, round(float(row.get("U(cm)", 10))))
            h = max(1, round(float(row.get("Y(cm)", 10))))
            if shape == "cylinder":
                l = w  # silindir: G=L=çap

            wgt = float(row.get("Ağırlık(kg)", 0))
            cst = str(row.get("Müşteri", "")).strip() or None

            stackable = not bool(row.get("Altına yerleştirilemez", False))
            fragile   = bool(row.get("Üstüne yerleştirilemez", False))
            rotation  = bool(row.get("Rotasyon", True))

            clearance = int(row.get("Min. Aralık (cm)", 0) or 0)
            # Algoritma clearance dahil boyutlarla çalışır → parçalar arası boşluk garantilenir
            # Görsel için gerçek boyutlar ve clearance ayrıca saklanır
            eff_w = w + 2 * clearance   # Etkin yerleştirme genişliği (clearance dahil)
            eff_l = l + 2 * clearance   # Etkin yerleştirme uzunluğu (clearance dahil)
            p = Piece3D(
                id=pid, shape=shape,
                width=max(1, eff_w),
                length=max(1, eff_l),
                height=h,
                quantity=adet, weight=wgt,
                allow_rotation_xy=rotation,
                is_stackable=stackable,
                is_fragile=fragile,
                customer_id=cst,
            )
            # Öncelik: 1 = kapıya en yakın bölge (y >= 0.70·L, EN SON yüklenir),
            # None = önceliksiz, her yere gidebilir (bkz. priority_utils)
            _prio_raw = row.get("Öncelik", None)
            p.priority = int(_prio_raw) if _prio_raw is not None and str(_prio_raw).strip() not in ("", "nan", "None") else None

            p._real_width   = w          # Gerçek fiziksel genişlik (görsel için)
            p._real_length  = l          # Gerçek fiziksel uzunluk (görsel için)
            p._clearance_cm = clearance  # Bırakılacak boşluk (görsel için)

            # Geometri verisi — STL/Profil için
            geom = geom_store.get(pid)
            if geom:
                p._shape_type     = geom.get("shape_type", "box")
                p._cross_section  = geom.get("cross_section")
                p._fill_ratio     = geom.get("fill_ratio", 1.0)
                p._mesh_vertices  = geom.get("mesh_vertices")
                p._mesh_faces     = geom.get("mesh_faces")
                try: p._inner_diameter = float(geom.get("inner_diameter", 0) or 0)
                except: p._inner_diameter = 0.0
            else:
                # geom_store boş (örn. Excel import, session yenileme):
                # Şekil sütunundan shape_type türet (yalnız Dikdörtgen/Silindir)
                p._shape_type     = _LABEL_TO_SHAPE_TYPE.get(sekil, "box")
                p._fill_ratio     = 1.0
                p._mesh_vertices  = None
                p._mesh_faces     = None
                p._cross_section  = None
                p._inner_diameter = 0.0

            pieces.append(p)
        except Exception:
            continue
    return pieces


def build_trucks(df):
    """Optimizasyonda kullanılacak araç listesi.

    Filo sayfasında (🚚 Filo) bir çekici+dorse filosu seçildiyse O kullanılır;
    seçilmediyse kenar çubuğundaki eski araç tablosu kullanılır. Böylece iki
    yol da çalışmaya devam eder (göç kararı H).
    """
    from filo_secimi import aktif_filo
    _ck, _dr = aktif_filo()
    if _ck and _dr:
        from filo_havuzu import havuz_olustur_cekici_dorse
        return list(havuz_olustur_cekici_dorse(_ck, _dr).trucks)

    trucks = []
    sizes = {260:"Küçük", 420:"Orta", 600:"Büyük"}
    for i, (_, row) in enumerate(df.iterrows(), 1):
        try:
            ulen = int(row["Uzunluk (cm)"])
            # ID kolonu varsa kullan, yoksa uzunluktan otomatik üret
            if "ID" in row and str(row["ID"]).strip():
                tid = str(row["ID"]).strip()
            else:
                tid = f"{sizes.get(ulen, 'Araç')}-{i}"
            trucks.append(Truck3D(
                id=tid,
                width=int(row.get("Genişlik (cm)", 240)),
                length=ulen,
                height=int(row["Yükseklik (cm)"]),
                capacity=float(row["Kapasite (kg)"]),
                available=int(row["Adet"]),
            ))
        except Exception:
            continue
    return trucks


def run_algo(key, pieces, trucks, _bypass_phase1=False, **kw):
    """
    Her algoritma için 4 fazlı çalışma:
      Faz 1: Minimum araç seçimi (tüm ürünleri kapsayan)
      Faz 2: Kapasite yeterlilik kontrolü
      Faz 3: Asıl algoritma çalışır
      Faz 4: Zorunlu kısıt doğrulaması (run_algo_with_validation'da)

    KESİN KURAL: Hiçbir algoritma yerleştirilemeyen ürünle dönemez.
    Her return öncesi _ensure_all_placed() çağrılır.

    Args:
        _bypass_phase1: True → Faz 1'i atla, trucks olduğu gibi kullan
                        (fallback retry için tam filo geçildiğinde kullanılır)
    """
    # ── Orijinal tam filo — kurtarma adımları için sakla ──────────────────
    # NOT: Faz 1 artık filoyu DARALTMIYOR (karar K4/B.4), bu yüzden
    # _full_fleet ile trucks aynı listedir. Değişken korunuyor: kurtarma
    # adımlarının her zaman tam filoyu gördüğü açık kalsın.
    _full_fleet = list(trucks)

    if not _bypass_phase1:
        # ── FAZ 1: YALNIZCA yeterlilik ön kontrolü (karar K4 / B.4) ──────
        # DEĞİŞTİ: Eskiden minimum_vehicle_selector FFD simülasyonuyla
        # birkaç araç seçiyor ve algoritmalara `trucks = _selected_trucks`
        # ile YALNIZCA onları veriyordu → algoritmalar başka bir araç
        # bileşimi deneyemiyordu (sorun #1). Artık filo bir TAVANDIR ve
        # hangi araçların açılacağına algoritma karar verir (filo_havuzu).
        from minimum_vehicle_selector import filo_on_kontrol
        _phase1_log = filo_on_kontrol(pieces, trucks)
        try:
            import streamlit as st
            st.session_state["_phase1_log"] = _phase1_log
        except Exception:
            pass
        print("[1/4] 🚛 Filo yeterlilik ön kontrolü...")
        for _line in _phase1_log:
            print(f"    {_line}")
        print(f"[2/4] 🔒 Araç seçimi algoritmaya bırakıldı (tavan: tüm filo)")
        print(f"[3/4] 🧬 {key} çalışıyor...")
    else:
        print(f"[3/4] 🧬 {key} çalışıyor (fallback retry, tam filo)...")
    # ────────────────────────────────────────────────────────────────────

    def _ensure_all_placed(plan):
        """Kurtarma + küçültme — her algoritmanın ortak çıkışı."""
        return _kucultme_uygula(_kurtarma_uygula(plan))

    def _kucultme_uygula(plan):
        """S18 — Kang & Park (2003) IFFD 2. adımı.

        "Gerektikçe aç" kuralı araç SAYISINI iyi tutuyor, ama son araç tek
        bir parça için açıldığında en büyüğü seçiliyor; K1'in 2. ölçütü
        (toplam araç hacmi) ve doluluk gereksiz kötüleşiyor. Küçültme
        yalnız araç TİPİNİ değiştirir, parçalar yerinde kalır → araç sayısı
        ve geçerlilik korunur.
        """
        if plan is None:
            return plan
        try:
            from filo_havuzu import kucult
            _pi = {p.id: p for p in pieces}
            _n = kucult(plan, _full_fleet, _pi)
            if _n:
                print(f"    [KUCULTME] {_n} arac daha kucuk tipe indirildi")
        except Exception as _e:                      # noqa: BLE001
            print(f"    [KUCULTME] atlandi: {_e}")
        return plan

    def _kurtarma_uygula(plan):
        """
        Algoritma döndürdükten hemen sonra çağrılır — 3 kademeli garanti:
          A) rescue_placement (TAM filo ile — Phase 1'in kısıtladığı filo değil)
          B) guarantee_all_placed (boyut-garantili overflow aracı)
          C) force_place_remaining (EP bypass — mutlak son şans)
        Bu fonksiyon ASLA None veya eksik plan döndürmez.
        """
        if plan is None:
            return plan
        from fallback_strategy import get_unplaced_pieces, rescue_placement, cleanup_empty_bins
        from placement_guarantee import guarantee_all_placed, force_place_remaining

        unplaced = get_unplaced_pieces(pieces, plan)
        if not unplaced:
            return plan   # zaten tam — hızlı çıkış

        total_pieces = sum(p.quantity for p in pieces)
        print(f"    [!] {key}: {len(unplaced)}/{total_pieces} urun yerlestirilmedi "
              "-- 3 kademeli kurtarma basliyor")

        # ── Kademe A: rescue_placement — TAM filo (_full_fleet) kullan ──────
        # NOT: Faz 1 artık daraltma yapmadığı için ikisi aynı; yine de
        # kurtarmanın tam filoyu kullandığı açıkça belli olsun diye durur.
        try:
            plan = rescue_placement(pieces, plan, _full_fleet)
            unplaced = get_unplaced_pieces(pieces, plan)
            if not unplaced:
                print(f"    [A] rescue_placement basarili (tam filo ile)")
                return cleanup_empty_bins(plan)
        except Exception as _e:
            print(f"    [A] rescue hatasi: {_e}")
            unplaced = get_unplaced_pieces(pieces, plan)

        # ── Kademe B: Boyut-garantili overflow aracı ─────────────────────────
        if unplaced:
            plan, ov_used, ov_log = guarantee_all_placed(
                pieces, plan, _full_fleet)
            for _l in ov_log:
                print(f"    [B] {_l}")
            if ov_used:
                try:
                    import streamlit as st
                    st.session_state["_overflow_used"] = True
                except Exception:
                    pass
            unplaced = get_unplaced_pieces(pieces, plan)

        # ── Kademe C: Force-placement — EP bypass, kesinlikle yerleştirir ────
        if unplaced:
            print(f"    [C] {len(unplaced)} urun hala eksik — force_place devreye giriyor")
            plan = force_place_remaining(pieces, plan, _full_fleet)
            unplaced = get_unplaced_pieces(pieces, plan)
            if ov_used or True:
                try:
                    import streamlit as st
                    st.session_state["_overflow_used"] = True
                except Exception:
                    pass

        if unplaced:
            print(f"    [KRITIK] {len(unplaced)} urun hala yerlestirilemedi — veri sorunu!")
        else:
            print(f"    [OK] Tum urunler yerlestirildi.")

        return cleanup_empty_bins(plan)

    eng = "EP"
    if key == "greedy_ep":
        from greedy_3d import greedy_3d_optimization
        return _ensure_all_placed(
            greedy_3d_optimization(pieces, trucks, heuristic="CP", engine=eng))
    elif key == "ffd_ep":
        from ffd_3d import ffd_3d_optimization
        return _ensure_all_placed(
            ffd_3d_optimization(pieces, trucks, heuristic="CP", engine=eng))
    elif key == "layer_building":
        from layer_building_3d import layer_building_3d_optimization
        # DÜZELTME: layer_strat UI'da seçiliyordu ama buraya hiç geçmiyordu
        # (kozmetik parametre) — artık katman derinliği stratejisine bağlı.
        return _ensure_all_placed(
            layer_building_3d_optimization(
                pieces, trucks,
                depth_strategy=kw.get("layer_strat", "adaptive")))
    elif key == "tabu_search":
        from ffd_3d import ffd_3d_optimization
        from tabu_search_3d import tabu_search_3d_optimization
        init = ffd_3d_optimization(pieces, trucks, heuristic="CP", engine=eng)
        return _ensure_all_placed(
            tabu_search_3d_optimization(pieces, trucks, initial_solution=init,
                max_time=kw.get("ts_time",30),
                tabu_tenure=kw.get("ts_tenure",7), engine=eng,
                seed=kw.get("seed"),
                progress_callback=kw.get("progress_cb")))
    elif key == "sa_hybrid":
        from ffd_3d import ffd_3d_optimization
        from simulated_annealing_3d import simulated_annealing_3d_optimization
        init = ffd_3d_optimization(pieces, trucks, heuristic="CP", engine=eng)
        return _ensure_all_placed(
            simulated_annealing_3d_optimization(pieces, trucks, initial_solution=init,
                max_time=kw.get("sa_time",30),
                initial_temp=kw.get("sa_temp",1000.0),
                cooling_rate=kw.get("sa_cool",0.995), engine=eng,
                seed=kw.get("seed"),
                progress_callback=kw.get("progress_cb")))
    elif key == "monte_carlo":
        from monte_carlo_3d import monte_carlo_3d_optimization
        from ffd_3d import ffd_3d_optimization as _ffd_mc
        _init_mc = _ffd_mc(pieces, trucks, heuristic="CP", engine=eng)
        return _ensure_all_placed(
            monte_carlo_3d_optimization(pieces, trucks,
                iterations=kw.get("mc_iter",100), initial_solution=_init_mc,
                seed=kw.get("seed"),
                progress_callback=kw.get("progress_cb")))
    elif key == "genetic":
        from genetic_3d import genetic_3d_optimization
        from ffd_3d import ffd_3d_optimization as _ffd_ga
        _init_ga = _ffd_ga(pieces, trucks, heuristic="CP", engine=eng)
        return _ensure_all_placed(
            genetic_3d_optimization(pieces, trucks,
                population_size=kw.get("ga_pop",50),
                generations=kw.get("ga_gen",100),
                initial_solution=_init_ga,
                max_time=kw.get("ga_time", 0) or 0,
                n_workers=kw.get("ga_workers", 0),
                seed=kw.get("seed"),
                progress_callback=kw.get("progress_cb")))
    elif key == "nfp_nested":
        return _ensure_all_placed(
            run_nfp(pieces, trucks, kw.get("nfp_res",2.0), kw.get("nfp_margin",0.5)))
    elif key == "bayesian":
        from bayesian_optimizer_3d import bayesian_optimization_3d
        return _ensure_all_placed(
            bayesian_optimization_3d(
                pieces, trucks,
                target_algorithm=kw.get("bay_target", "auto"),
                n_trials=kw.get("bay_trials", 40),
                time_budget=kw.get("bay_time", 120.0),
                seed_with_ffd=True,
                progress_callback=kw.get("progress_cb"),
            ))
    elif key == "island_ga":
        from island_genetic_3d import island_model_ga_3d
        from ffd_3d import ffd_3d_optimization as _ffd_isl
        _init_isl = _ffd_isl(pieces, trucks, heuristic="CP", engine=eng)
        return _ensure_all_placed(
            island_model_ga_3d(
                pieces, trucks,
                n_islands=kw.get("isl_islands", 4),
                island_population=kw.get("isl_pop", 25),
                generations=kw.get("isl_gen", 80),
                migration_interval=kw.get("isl_mig", 15),
                initial_solution=_init_isl,
                max_time=kw.get("isl_time", 0) or 0,
                n_workers=kw.get("isl_workers", 0),
                seed=kw.get("seed"),
                progress_callback=kw.get("progress_cb"),
            ))
    elif key == "multistart_sa":
        from multistart_sa_3d import multistart_sa_3d
        from ffd_3d import ffd_3d_optimization as _ffd_ms
        _init_ms = _ffd_ms(pieces, trucks, heuristic="CP", engine=eng)
        return _ensure_all_placed(
            multistart_sa_3d(
                pieces, trucks,
                n_starts=kw.get("ms_starts", 5),
                time_budget=kw.get("ms_time", 90.0),
                initial_solution=_init_ms,
                seed=kw.get("seed"),
                progress_callback=kw.get("progress_cb"),
            ))
    return None


def run_algo_with_validation(key, pieces, trucks, **kw):
    """
    run_algo'yu çağırır + Faz 4 kısıt doğrulaması yapar.
    Eksik ürün varsa FALLBACK ZİNCİRİNİ tetikler:
      Adım 1 — Silindir bbox (motor zaten kullanıyor, log)
      Adım 2 — Öncelik swap (motor desteklemiyorsa skip + log)
      Adım 3 — Tam filo ile algoritmayı yeniden çalıştır (yeni araç ekle)
      Adım 4 — Hâlâ eksikse ConstraintViolation
    """
    from minimum_vehicle_selector import (
        validate_all_placed, format_validation_summary, ConstraintViolation,
    )
    from fallback_strategy import apply_fallback_chain, get_unplaced_pieces

    plan = run_algo(key, pieces, trucks, **kw)
    if plan is None:
        return None

    # Faz 4: İlk doğrulama
    summary = format_validation_summary(pieces, plan)
    print(f"[4/4] ✅ Kısıt doğrulama → {summary}")
    try:
        validate_all_placed(pieces, plan)
        # Sonuç temizliği: boş bin'leri kaldır
        from fallback_strategy import cleanup_empty_bins
        return cleanup_empty_bins(plan)
    except ConstraintViolation as cv:
        print(f"[4/4] ⚠️ {cv}")
        print("[4/4] 🔄 Fallback zinciri başlatılıyor...")
        # Fallback: tam filo (kullanıcının tanımladığı orijinal filo) ile dene
        try:
            report = apply_fallback_chain(
                key, pieces, trucks, plan, run_algo, **kw
            )
            # UI için log'u session_state'e ekle
            try:
                import streamlit as st
                st.session_state["_fallback_log"] = report.log_lines
                st.session_state["_fallback_added_vehicles"] = report.added_vehicles
            except Exception:
                pass
            for _l in report.log_lines:
                print(f"    {_l}")
            if report.success:
                print(f"[4/4] ✅ Fallback başarılı")
                from fallback_strategy import cleanup_empty_bins
                return cleanup_empty_bins(report.plan)
            return report.plan
        except ConstraintViolation:
            # Son şans: parça-bazlı rescue
            print("[4/4] 🚨 Fallback başarısız → rescue_placement deneniyor")
            from fallback_strategy import rescue_placement
            try:
                rescued_plan = rescue_placement(pieces, plan, trucks)
            except Exception:
                rescued_plan = plan   # rescue da başarısız → overflow'a bırak
            try:
                import streamlit as st
                _fblog = st.session_state.get("_fallback_log", [])
                _fblog.append("🚨 rescue_placement çalıştırıldı (parça-bazlı kurtarma)")
                st.session_state["_fallback_log"] = _fblog
            except Exception:
                pass

            # ── ADIM 4 (Son): Overflow aracı garantisi ─────────────────────
            from placement_guarantee import guarantee_all_placed
            rescued_plan, overflow_used, ov_log = guarantee_all_placed(
                pieces, rescued_plan, trucks
            )
            for _l in ov_log:
                print(f"    {_l}")
            if overflow_used:
                try:
                    import streamlit as st
                    _fblog = st.session_state.get("_fallback_log", [])
                    _fblog.extend(ov_log)
                    st.session_state["_fallback_log"]      = _fblog
                    st.session_state["_overflow_used"]     = True
                except Exception:
                    pass
                print("[4/4] ✅ Overflow aracı devreye girdi — tüm ürünler yerleştirildi")
            else:
                print("[4/4] ✅ Rescue başarılı")

            from fallback_strategy import cleanup_empty_bins
            return cleanup_empty_bins(rescued_plan)


def run_nfp(pieces, trucks, resolution=2.0, margin=0.5):
    from shapely.geometry import box as sbox
    t0 = time.time()
    all_bins, assignments, tidx = [], {}, 0
    for truck in trucks:
        for _ in range(truck.available):
            pieces_data = [{
                "id": p.id,
                "polygon": getattr(p,"_cross_section",None) or sbox(0,0,p.width,p.length),
                "width":p.width, "length":p.length, "height":p.height,
                "quantity":p.quantity,
                "priority": getattr(p,"priority",0) or 0,
                "allow_rotation": p.allow_rotation_xy,
            } for p in pieces]
            layer_groups, _ = pack_3d_with_nesting(
                pieces_data, truck.width, truck.length, truck.height,
                resolution=resolution, margin=margin)
            pmap = {p.id: p for p in pieces}
            bin_placements = []
            for lg in layer_groups:
                for pl in lg.placements:
                    pobj = pmap.get(pl.piece_id)
                    if not pobj: continue
                    bin_placements.append(Placement3D(
                        x=int(pl.x), y=int(pl.y), z=int(lg.z_start),
                        width=pobj.width, length=pobj.length, height=pobj.height,
                        piece_id=pl.piece_id, rotation=(0,int(pl.rotation_deg),0),
                        bin_id=tidx))
            all_bins.append(bin_placements)
            assignments[tidx] = truck.id
            tidx += 1

    truck_vol = sum(t.width*t.length*t.height*t.available for t in trucks)
    piece_vol = sum(getattr(p,"_fill_ratio",1.0)*p.width*p.length*p.height*p.quantity for p in pieces)
    util = min(100.0, piece_vol/truck_vol*100) if truck_vol else 0

    plan = CuttingPlan3D(bins=all_bins, total_waste=truck_vol-piece_vol,
                          utilization=util, execution_time=time.time()-t0,
                          algorithm="NFP Nested", truck_assignments=assignments)

    # 2D çizim verisi
    nfp_plot = []
    COLORS = ['#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD',
              '#F8C471','#82E0AA','#85C1E9','#BB8FCE']
    cmap = {}; cidx = 0
    for b in all_bins:
        for pl3d in b:
            cs = getattr(pmap.get(pl3d.piece_id), "_cross_section", None) if (pmap := {p.id:p for p in pieces}) else None
            if not cs: continue
            from shapely import affinity as saff
            poly = saff.translate(cs, pl3d.x, pl3d.y)
            pid = pl3d.piece_id
            if pid not in cmap: cmap[pid]=COLORS[cidx%len(COLORS)]; cidx+=1
            nfp_plot.append({"piece_id":pid,"x":pl3d.x,"y":pl3d.y,
                "z_start":pl3d.z,"z_end":pl3d.z+pl3d.height,
                "polygon_coords":list(poly.exterior.coords),
                "color":cmap[pid],"rotation":pl3d.rotation[1]})
    st.session_state["nfp_plot"]  = nfp_plot
    st.session_state["nfp_truck"] = (trucks[0].width, trucks[0].length) if trucks else (300,600)
    return plan


def _show_fleet_report(plan, pieces, trucks):
    """Araç başına doluluk (R-a) ve dingil yükleri (D-b).

    U_V tanımı DEĞİŞMİYOR: gerçek hacim (silindirde πr²h) ÷ aracın hacmi —
    yani mevcut U_G tanımı. Yanına ağırlık kullanımı U_W eklenir.
    "Bağlayıcı ölçü" seçimi S11 kararını beklediği için burada YAPILMIYOR;
    ikisi de ayrı ayrı gösteriliyor.
    """
    if not trucks or not plan or not plan.bins:
        return
    from core_3d import piece_used_volume
    from doluluk import AracDoluluk, PlanDoluluk

    piece_info = {p.id: p for p in pieces}
    tid = {t.id: t for t in trucks}
    atama = plan.truck_assignments or {}

    satirlar, dingil_satirlari, uyarilar = [], [], []
    rapor = PlanDoluluk()

    for bid, bps in enumerate(plan.bins):
        if not bps:
            continue
        t = tid.get(atama.get(bid))
        if t is None:
            continue
        gercek = sum(piece_used_volume(p, piece_info) for p in bps)
        yuk_kg = sum(getattr(piece_info.get(p.piece_id), "weight", 0) or 0
                     for p in bps)
        es = getattr(t, "eslesme", None)
        ad = (f"{es.cekici.plaka} + {es.dorse.plaka}") if es else t.id

        a = AracDoluluk(
            etiket=ad, gercek_hacim=gercek,
            dis_kutu_hacim=sum(p.get_volume() for p in bps),
            arac_hacim=t.get_volume(), yuk_kg=yuk_kg,
            faydali_yuk_kg=t.capacity,
            bos_agirlik_kg=((es.cekici.bos_agirlik_kg + es.dorse.bos_agirlik_kg)
                            if es else 0.0),
        )
        rapor.araclar.append(a)
        satirlar.append({
            "Araç": ad,
            "Parça": len(bps),
            "U_V (hacim)": f"%{(a.u_v or 0) * 100:.1f}",
            "U_W (ağırlık)": f"%{(a.u_w or 0) * 100:.1f}",
            "Yük (kg)": f"{yuk_kg:,.0f}".replace(",", "."),
            "Faydalı yük (kg)": f"{t.capacity:,.0f}".replace(",", "."),
        })

        # ── Dingil yükleri ──
        if es is None:
            continue
        from dingil_yuku import arac_dingil_raporu, cm_to_mm_cg
        yukler = [((getattr(piece_info.get(p.piece_id), "weight", 0) or 0),
                   cm_to_mm_cg(p.y, p.length)) for p in bps]
        sonuc = arac_dingil_raporu(es, yukler)
        if not sonuc.kontrol_edildi:
            uyarilar.append(f"**{ad}** — " + (sonuc.uyarilar[-1]
                                              if sonuc.uyarilar else
                                              "dingil kontrolü yapılamadı"))
            continue
        s = es.dingil_sinirlari
        for etiket, yuk, sinir in (
                ("ön dingil", sonuc.yukler.on_dingil_kg, s.on_dingil_kg),
                ("tahrik dingili", sonuc.yukler.tahrik_dingil_kg,
                 s.tahrik_dingil_kg),
                ("kingpin", sonuc.yukler.kingpin_kg, s.kingpin_kg),
                ("dingil grubu", sonuc.yukler.dingil_grubu_kg,
                 s.dingil_grubu_kg),
                ("toplam", sonuc.yukler.toplam_kg, s.toplam_kg)):
            if sinir is None:
                continue
            asim = yuk > sinir
            dingil_satirlari.append({
                "Araç": ad, "Sınır": etiket,
                "Yük (kg)": f"{yuk:,.0f}".replace(",", "."),
                "Limit (kg)": f"{sinir:,.0f}".replace(",", "."),
                "Oran": f"%{yuk / sinir * 100:.0f}" if sinir else "—",
                "Durum": "🔴 AŞIM" if asim else "✅",
            })
        uyarilar.extend(f"**{ad}** — {u}" for u in sonuc.uyarilar
                        if "VARSAYIM" in u or "yapılamadı" in u)

    if not satirlar:
        return

    _etiket = (f"📊 Araç başına doluluk ve dingil yükleri — "
               f"{len(satirlar)} araç")
    with st.expander(_etiket, expanded=False):
        st.markdown("**Doluluk (R-a)**")
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("U_V (toplam)", f"%{(rapor.u_v or 0) * 100:.1f}",
                  help="Gerçek hacim ÷ kullanılan araçların hacmi — "
                       "mevcut U_G tanımı, değişmedi.")
        c2.metric("U_W (toplam)", f"%{(rapor.u_w or 0) * 100:.1f}",
                  help="Yük kütlesi ÷ toplam faydalı yük.")
        c3.metric("U_V en düşük", f"%{(rapor.u_v_en_dusuk or 0) * 100:.1f}")
        c4.metric("Toplam boş ağırlık",
                  f"{rapor.toplam_bos_agirlik_kg:,.0f} kg".replace(",", "."),
                  help="Taşınan ölü ağırlık. YALNIZCA raporlanır; "
                       "sıralamada kullanılmaz (K1'in 2. ölçütü açık).")
        st.caption(
            f"Araç başına U_V ortalaması: "
            f"%{(rapor.u_v_ortalama or 0) * 100:.1f} — heterojen filoda "
            f"toplam oranla ayrışır, bu yüzden ikisi birlikte veriliyor.")

        if dingil_satirlari:
            st.markdown("**Dingil yükleri (D-b)** — "
                        "Yükleme Yönetmeliği md. 6(1)(b)")
            st.dataframe(pd.DataFrame(dingil_satirlari), hide_index=True,
                         width="stretch")
        for u in dict.fromkeys(uyarilar):
            st.warning(f"⚠️ {u}")


def show_kpis(plan, pieces, trucks=None):
    placed       = sum(len(b) for b in plan.bins)
    total        = sum(p.quantity for p in pieces)
    n_tr         = len([b for b in plan.bins if b])
    total_weight = sum(p.weight * p.quantity for p in pieces)
    piece_info   = {p.id: p for p in pieces}

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.markdown(f'<div class="kpi-card"><div class="kpi-label">Araç</div>'
                f'<div class="kpi-value">{n_tr}</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="kpi-card"><div class="kpi-label">Doluluk</div>'
                f'<div class="kpi-value">%{plan.utilization:.1f}</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="kpi-card"><div class="kpi-label">Yerleşen</div>'
                f'<div class="kpi-value">{placed}/{total}</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="kpi-card"><div class="kpi-label">Toplam Ağırlık</div>'
                f'<div class="kpi-value">{total_weight:,.0f} kg</div></div>', unsafe_allow_html=True)
    c5.markdown(f'<div class="kpi-card"><div class="kpi-label">Süre</div>'
                f'<div class="kpi-value">{plan.execution_time:.2f}s</div></div>', unsafe_allow_html=True)

    # ── Overflow araç uyarısı ─────────────────────────────────────────────────
    if st.session_state.get("_overflow_used"):
        st.warning(
            "⚠️ **Overflow aracı kullanıldı:** Tüm ürünler yerleştirildi, "
            "ancak filo kapasitesi yetersiz kaldı. Yeni bir araç eklemeyi düşünün."
        )
        st.session_state["_overflow_used"] = False   # tek seferlik göster

    # ── Öncelik bölgesi ihlalleri (artık yalnız konsola değil UI'a da) ────────
    try:
        from priority_utils import collect_priority_violations
        _pv = collect_priority_violations(
            plan.bins, piece_info, trucks or [], plan.truck_assignments or {})
        if _pv:
            with st.expander(f"🚚 {len(_pv)} öncelik bölgesi ihlali", expanded=True):
                st.warning(
                    "Aşağıdaki öncelikli parçalar hedef bölgelerinin dışına "
                    "yerleşti (bölge kısıtı soft'tur — algoritma ceza puanına "
                    "rağmen daha iyi yer bulamadı). Araç/parça düzenini gözden "
                    "geçirin veya farklı bir algoritma deneyin."
                )
                st.dataframe(pd.DataFrame([
                    {"Araç": v["bin"] + 1, "Parça": v["piece_id"],
                     "Öncelik": v["priority"],
                     "Y merkezi (cm)": round(v["y_center"]),
                     "Beklenen bölge (cm)": f"{v['expected'][0]}–{v['expected'][1]}"}
                    for v in _pv
                ]), hide_index=True, width="stretch")
    except Exception:
        pass

    # ── P1-P5 Yerleştirme Öncelik Özeti (kapalı expander) ────────────────────
    try:
        from placement_guarantee import classify_pieces_p1_p5, build_priority_summary
        _classified = classify_pieces_p1_p5(pieces, trucks or [])
        _prio_rows  = build_priority_summary(_classified, plan)
        _has_pieces  = any(r["total"] > 0 for r in _prio_rows)
        _has_pending = any(r["pending"] > 0 for r in _prio_rows)
        if _has_pieces:
            _exp_icon = "⚠️" if _has_pending else "✅"
            with st.expander(
                f"{_exp_icon} Yerleştirme Öncelik Özeti (P1–P5)",
                expanded=False,
            ):
                _tbl = [
                    "| Seviye | Açıklama | Ürün | Yerleşen | Bekleyen |",
                    "|--------|----------|:----:|:--------:|:--------:|",
                ]
                for r in _prio_rows:
                    if r["total"] == 0:
                        continue
                    pend_str = f"**{r['pending']}** ⚠️" if r["pending"] > 0 else "0 ✅"
                    _tbl.append(
                        f"| P{r['level']} | {r['label']} "
                        f"| {r['total']} | {r['placed']} | {pend_str} |"
                    )
                st.markdown("\n".join(_tbl))
                st.caption(
                    "P1: Boyut kısıtlı · P2: Ağır · P3: Hacimli · "
                    "P4: Standart · P5: Küçük/Tamamlayıcı"
                )
                if _has_pending:
                    st.error(
                        f"❌ Yerleştirilemeyen ürün — bu satır **0** değil. "
                        "Araç sayısını artırın veya filo boyutunu gözden geçirin."
                    )
    except Exception:
        pass   # placement_guarantee yoksa sessizce geç

    if placed < total:
        st.error(f"⚠️ {total-placed} yük yerleştirilemedi!")

        # ── Yerleştirilemeyen parçaları hesapla ──────────────────────────────
        # Placements'taki piece_id sayısını say → required - placed = unfitted
        placed_counts: Dict[str, int] = {}
        for b in plan.bins:
            for pl in b:
                placed_counts[pl.piece_id] = placed_counts.get(pl.piece_id, 0) + 1

        unfitted_rows = []
        for p in pieces:
            req  = p.quantity
            done = placed_counts.get(p.id, 0)
            miss = req - done
            if miss > 0:
                unfitted_rows.append({
                    "🏷️ ID":          p.id,
                    "📐 Boyut (cm)":  f"{p.width}×{p.length}×{p.height}",
                    "⚖️ Ağırlık(kg)": f"{p.weight:,.1f}",
                    "İstenen":        req,
                    "Yerleşen":       done,
                    "❌ Eksik":       miss,
                    "Neden (tahmin)": (
                        "Araç kapasitesi aşıldı" if p.weight * miss > 500
                        else "Araçlarda yer kalmadı" if sum(
                            t.width * t.length * t.height * t.available
                            for t in (trucks or [])
                        ) < p.width * p.length * p.height
                        else "Boyut / ağırlık uyumsuzluğu"
                    ),
                })

        if unfitted_rows:
            with st.expander("📋 Yerleştirilemeyen parçalar — detay", expanded=True):
                _uf_df = pd.DataFrame(unfitted_rows)
                st.dataframe(_uf_df, hide_index=True, width="stretch",
                    column_config={
                        "❌ Eksik": st.column_config.NumberColumn("❌ Eksik", format="%d"),
                        "İstenen":  st.column_config.NumberColumn("İstenen",  format="%d"),
                        "Yerleşen": st.column_config.NumberColumn("Yerleşen", format="%d"),
                    })
                total_miss_kg = sum(
                    p.weight * (p.quantity - placed_counts.get(p.id, 0))
                    for p in pieces if p.quantity - placed_counts.get(p.id, 0) > 0
                )
                st.caption(
                    f"Toplam yerleştirilemeyen: **{sum(r['❌ Eksik'] for r in unfitted_rows)} adet** "
                    f"/ **{total_miss_kg:,.0f} kg** "
                    f"→ Araç sayısını artırın veya araç boyutunu büyütün."
                )

    # ── Araç başına ağırlık merkezi kontrolü (literatür tabanlı, 3 eksen) ──
    # Kaynak: Synák & Nedeliaková (2024) Appl. Sci.; Erbayrak et al. (2021)
    from core_3d import (check_weight_balance as _cwb, COG_LATERAL_TOL,
                          COG_LONG_TOL, COG_VERTICAL_MAX, COG_FRONT_BIAS)
    truck_list = trucks or []

    # ── 1. Tüm araçları tara, veriyi topla ───────────────────────────────────
    _balance_rows   = []   # (truck_id, status_icon, sorun_str, detail_dict, truck_obj, cap_exceeded)
    _fix_rows       = []   # Sadece sorunlu araçlar → düzeltme önerileri için

    for bid, bin_placements in enumerate(plan.bins):
        if not bin_placements:
            continue
        truck_id = plan.truck_assignments.get(bid, "—") if plan.truck_assignments else "—"
        truck = next((t for t in truck_list if t.id == truck_id), truck_list[0] if truck_list else None)
        if not truck:
            continue

        bin_weight = sum(
            piece_info[pl.piece_id].weight
            for pl in bin_placements if pl.piece_id in piece_info
        )
        cap_exceeded = bin_weight > truck.capacity

        lat_ok, lon_ok, vert_ok, det = _cwb(bin_placements, piece_info, truck)

        sorun_parts = []
        if cap_exceeded:
            sorun_parts.append(f"Kapasite aşıldı ({bin_weight:,.0f}/{truck.capacity:,.0f} kg)")
        if not lat_ok:
            sorun_parts.append(f"Yanal %{det.get('x_dev',0)*100:.0f}")
        if not lon_ok:
            sorun_parts.append(f"Boylamsal %{det.get('y_dev',0)*100:.0f}")
        if not vert_ok:
            sorun_parts.append(f"Dikey %{det.get('z_frac',0)*100:.0f}")

        has_issue = bool(sorun_parts)
        status_icon = "⚠️" if has_issue else "✅"
        sorun_str   = ", ".join(sorun_parts) if sorun_parts else "—"

        _balance_rows.append((truck_id, status_icon, sorun_str, det, truck, cap_exceeded,
                               lat_ok, lon_ok, vert_ok))
        if has_issue:
            _fix_rows.append((truck_id, det, truck, cap_exceeded, lat_ok, lon_ok, vert_ok, bin_weight))

    # ── 1b. Araç başına doluluk ve dingil yükleri (R-a + D-b) ───────────────
    _show_fleet_report(plan, pieces, trucks)

    # ── 2. Özet tablo + düzeltme önerileri → tek kapalı expander ─────────────
    _ok_count  = sum(1 for r in _balance_rows if r[1] == "✅")
    _warn_count = sum(1 for r in _balance_rows if r[1] == "⚠️")
    _total     = len(_balance_rows)

    _exp_label = (
        f"🏋️ Denge Analizi — {_total} araç  |  ✅ {_ok_count}  ⚠️ {_warn_count}"
    )
    with st.expander(_exp_label, expanded=False):
        # Özet tablo
        _tbl_lines = ["| Araç | Durum | Sorun |", "|------|-------|-------|"]
        for truck_id, icon, sorun, *_ in _balance_rows:
            _tbl_lines.append(f"| {truck_id} | {icon} | {sorun} |")
        st.markdown("\n".join(_tbl_lines))

        # İstatistik
        st.caption(
            f"**Toplam:** {_total} araç  —  **✅ Sorunsuz:** {_ok_count}  —  **⚠️ Sorunlu:** {_warn_count}"
        )

        # Düzeltme önerileri (sadece sorunlu araçlar, toplu)
        if _fix_rows:
            st.markdown("---")
            st.markdown("### 🔧 Düzeltme Önerileri")
            for (truck_id, det, truck, cap_exceeded,
                 lat_ok, lon_ok, vert_ok, bin_weight) in _fix_rows:
                cog_x   = det.get('cog_x', 0)
                cog_y   = det.get('cog_y', 0)
                cog_z   = det.get('cog_z', 0)
                ideal_x = det.get('ideal_x', truck.width / 2)
                ideal_y = det.get('ideal_y', truck.length * 0.55)

                st.markdown(f"**{truck_id}**")
                if cap_exceeded:
                    st.markdown(
                        f"- 🔴 **Kapasite:** {bin_weight:,.0f} kg yüklendi, "
                        f"limit {truck.capacity:,.0f} kg. Bir kısmını başka araca taşıyın."
                    )
                if not lat_ok:
                    direction = "sola" if cog_x > ideal_x else "sağa"
                    shift_cm  = abs(cog_x - ideal_x)
                    st.markdown(
                        f"- 🔴 **Yanal:** Ağır yükleri ~{shift_cm:.0f} cm **{direction}** kaydırın. "
                        f"(Mevcut CoG X={cog_x:.0f} cm, hedef {ideal_x:.0f} cm ±{truck.width*0.10:.0f} cm)"
                    )
                if not lon_ok:
                    direction = "öne" if cog_y > ideal_y else "arkaya"
                    shift_cm  = abs(cog_y - ideal_y)
                    st.markdown(
                        f"- 🟡 **Boylamsal:** Ağır yükleri ~{shift_cm:.0f} cm **{direction}** taşıyın. "
                        f"(Mevcut CoG Y={cog_y:.0f} cm, hedef {ideal_y:.0f} cm ±{truck.length*0.15:.0f} cm)"
                    )
                if not vert_ok:
                    st.markdown(
                        f"- 🟡 **Dikey:** Ağır parçaları zemine alın. "
                        f"(Mevcut CoG Z={cog_z:.0f} cm → hedef ≤{truck.height*0.60:.0f} cm)"
                    )


def show_3d(plan, pieces, trucks, show_truck, show_grid, show_weight, chart_key="main"):
    import hashlib
    dolu = [(i,b) for i,b in enumerate(plan.bins) if b]
    if not dolu:
        st.info("Görüntülenecek yerleşim yok."); return

    def _safe_key(base):
        # Streamlit key: sadece alfanumerik + _ + - izin verilir
        # Tüm özel karakterleri temizle, uzun keyleri hash ile kısalt
        clean = "".join(c if c.isalnum() or c in "_-" else "_" for c in base)
        if len(clean) > 80:
            clean = clean[:40] + "_" + hashlib.md5(base.encode()).hexdigest()[:8]
        return clean

    if len(dolu) == 1:
        bid = dolu[0][0]
        fig = visualize_3d_plan(plan, trucks, pieces, bid, show_truck, show_grid)
        _k = _safe_key(f"chart_{chart_key}_b{bid}")
        st.plotly_chart(fig, width="stretch", key=_k)
    else:
        tab_labels = [f"🚛 Araç {i+1} ({len(b)} palet)" for i,b in dolu]
        tabs = st.tabs(tab_labels)
        for tidx, (tab,(bid,_)) in enumerate(zip(tabs, dolu)):
            with tab:
                fig = visualize_3d_plan(plan, trucks, pieces, bid, show_truck, show_grid)
                _k = _safe_key(f"chart_{chart_key}_t{tidx}_b{bid}")
                st.plotly_chart(fig, width="stretch", key=_k)


def results_dict_from(all_results, pieces):
    total = sum(p.quantity for p in pieces)
    return {
        name: {
            "utilization":    plan.utilization,
            "truck_count":    len([b for b in plan.bins if b]),
            "placed":         sum(len(b) for b in plan.bins),
            "total_req":      total,
            "total_weight":   sum(p.weight*p.quantity for p in pieces),
            "waste_cm3":      plan.total_waste,
            "execution_time": plan.execution_time,
        } for name, plan in all_results.items()
    }


def plan_rank(plan) -> tuple:
    """
    "En iyi algoritma" karşılaştırma anahtarı.

    Salt utilization, daha az parça yerleştirip daha yüksek doluluk gösteren
    planın kazanmasına izin veriyordu. Sıralama önceliği:
      1) En çok yerleştirilen parça
      2) En az kullanılan araç
      3) En yüksek doluluk
    """
    placed = sum(len(b) for b in plan.bins)
    bins_used = len([b for b in plan.bins if b])
    return (placed, -bins_used, plan.utilization)


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA: OPTİMİZASYON
# ─────────────────────────────────────────────────────────────────────────────
if page == "🚀 Optimizasyon":
    # ── Algoritma hover tooltip motoru ───────────────────────────────────────
    # components.html() SIDEBAR DIŞINDA çağrılmalı — içinde iframe render edilmez.
    # height=0 → görünmez; JS window.parent.document ile sidebar'a erişir.
    import json as _json
    import streamlit.components.v1 as _cmp
    _tip_data = _json.dumps({
        v["name"].split(" ", 1)[-1].strip(): {
            "full": v["name"],
            "desc": v.get("desc", ""),
            "time": v["time"],
            "pros": v.get("pros", ""),
            "cons": v.get("cons", ""),
        }
        for v in ALGORITHMS.values()
    }, ensure_ascii=False)
    _cmp.html(
        "<script>\n"
        "(function(){\n"
        "try{\n"
        "var pd=window.parent.document,p=window.parent;\n"
        "if(!pd.getElementById('lp-tip-css')){\n"
        " var s=pd.createElement('style');s.id='lp-tip-css';\n"
        " s.textContent='#lp-algo-tip{position:fixed;z-index:99999;'"
        "+'background:linear-gradient(135deg,#1a1f35,#0d1117);'"
        "+'border:1px solid rgba(33,150,243,.4);border-radius:10px;'"
        "+'padding:17px 21px;max-width:340px;min-width:260px;'"
        "+'box-shadow:0 8px 32px rgba(0,0,0,.7);pointer-events:none;display:none;'"
        "+'font-family:sans-serif;}'"
        "+'#lp-t{font-size:17px;font-weight:700;color:#89b4fa;margin-bottom:8px;}'"
        "+'#lp-d{font-size:15px;color:#cdd6f4;line-height:1.6;margin-bottom:11px;}'"
        "+'#lp-row{display:flex;flex-wrap:wrap;gap:6px;}'"
        "+'.lp-b{font-size:14px;padding:4px 11px;border-radius:12px;display:inline-block;}'"
        "+'.lp-tm{background:#2196F322;border:1px solid #2196F355;color:#64B5F6;}'"
        "+'.lp-pr{background:#4CAF5022;border:1px solid #4CAF5055;color:#81C784;}'"
        "+'.lp-cn{background:#FF572222;border:1px solid #FF572255;color:#EF9A9A;}';\n"
        " pd.head.appendChild(s);\n"
        "}\n"
        "if(!pd.getElementById('lp-algo-tip')){\n"
        " var dv=pd.createElement('div');dv.id='lp-algo-tip';\n"
        " dv.innerHTML='<div id=\"lp-t\"></div><div id=\"lp-d\"></div>'"
        "+'<div id=\"lp-row\">'"
        "+'<span class=\"lp-b lp-tm\" id=\"lp-tm\"></span>'"
        "+'<span class=\"lp-b lp-pr\" id=\"lp-pr\"></span>'"
        "+'<span class=\"lp-b lp-cn\" id=\"lp-cn\"></span>'"
        "+'</div>';\n"
        " pd.body.appendChild(dv);\n"
        "}\n"
        "var tip=pd.getElementById('lp-algo-tip');\n"
        f"var TIPS={_tip_data};\n"
        "function fk(t){for(var k in TIPS)if(t.indexOf(k)!==-1)return k;return null;}\n"
        "function show(lbl){\n"
        " var t=lbl._lp;\n"
        " pd.getElementById('lp-t').textContent=t.full;\n"
        " pd.getElementById('lp-d').textContent=t.desc;\n"
        " pd.getElementById('lp-tm').textContent='⏱ '+t.time;\n"
        " var pr=pd.getElementById('lp-pr'),cn=pd.getElementById('lp-cn');\n"
        " pr.textContent=t.pros?'✓ '+t.pros:'';pr.style.display=t.pros?'':'none';\n"
        " cn.textContent=t.cons?'✗ '+t.cons:'';cn.style.display=t.cons?'':'none';\n"
        " var r=lbl.getBoundingClientRect();\n"
        " var sbr=pd.querySelector('[data-testid=\"stSidebar\"]').getBoundingClientRect();\n"
        " tip.style.left=(sbr.right+12)+'px';\n"
        " tip.style.top=Math.max(8,r.top)+'px';\n"
        " tip.style.display='block';\n"
        "}\n"
        "function attach(){\n"
        " var sb=pd.querySelector('[data-testid=\"stSidebar\"]');if(!sb)return;\n"
        " var sel='[data-testid=\"stRadio\"] label,[data-baseweb=\"radiogroup\"] label,label:has([data-baseweb=\"radio\"]),"
        "[data-testid=\"stCheckbox\"] label,label:has([data-baseweb=\"checkbox\"])';\n"
        " var els=[];\n"
        " try{els=Array.from(sb.querySelectorAll(sel));}catch(e){\n"
        "  els=Array.from(sb.querySelectorAll('[data-testid=\"stRadio\"] label,[data-baseweb=\"radiogroup\"] label,[data-testid=\"stCheckbox\"] label'));\n"
        " }\n"
        " els.forEach(function(lb){\n"
        "  if(lb._lp)return;\n"
        "  var sp=lb.querySelector('span,p,div>span');\n"
        "  var _st=(sp?sp.textContent:'').trim();\n"
        "  var t=(_st.length>2?_st:lb.textContent||'').trim();\n"
        "  var k=fk(t);if(!k)return;\n"
        "  lb._lp=TIPS[k];lb.style.cursor='help';\n"
        "  lb.addEventListener('mouseenter',function(){show(lb);});\n"
        "  lb.addEventListener('mouseleave',function(){tip.style.display='none';});\n"
        " });\n"
        "}\n"
        "if(!p._lpObs){\n"
        " p._lpObs=new MutationObserver(function(){attach();});\n"
        " p._lpObs.observe(pd.body,{childList:true,subtree:true});\n"
        "}\n"
        "attach();\n"
        "setTimeout(attach,800);\n"
        "setTimeout(attach,2000);\n"
        "}catch(e){console.warn('[LP-tip]',e);}\n"
        "})();\n"
        "</script>",
        height=0, scrolling=False,
    )

    st.title("🧊 3D Araç Yükleme Optimizasyonu")
    st.caption("EP · Layer Building · Tabu/SA · NFP Nested Packing · STEP/STL import")

    # Proje adı
    col_pn, col_pd = st.columns([2,3])
    project_name = col_pn.text_input("📋 Proje Adı", value="Yeni Proje")
    project_desc = col_pd.text_input("Açıklama", value="")
    st.markdown("---")

    # ── Yük Tanımı sekmeler ──────────────────────────────────────────────────
    t_std, t_sw, t_xl = st.tabs([
        "📦 Standart Yükler",
        "📐 SolidWorks (STEP/STL)",
        "📊 Excel'den İçe Aktar",
    ])

    # — Standart
    with t_std:
        if "df_pallets" not in st.session_state:
            st.session_state.df_pallets = pd.DataFrame({
                "ID":          ["Euro-1","Euro-2","Silindir-1"],
                "Şekil":       ["Dikdörtgen","Dikdörtgen","Silindir"],
                "Genişlik (cm)":[80,80,80],
                "Uzunluk (cm)":[120,120,80],
                "Yükseklik (cm)":[140,140,120],
                "Ağırlık (kg)":[250,180,300],
                "Adet":        [6,6,4],
                "Müşteri":     ["","",""],
                "Öncelik":     [None,None,None],
            })

        df_pallets = st.session_state.df_pallets

    # — SolidWorks
    with t_sw:
        st.markdown("""
#### 📐 STEP / STL Dosyası İçe Aktarım
**SolidWorks'ten dışa aktarım:**
- STL: *Dosya → Farklı Kaydet → STL* — **Birim: Santimetre**
- STEP: *Dosya → Farklı Kaydet → STEP AP214*
        """)

        if not HAS_TRIMESH and not HAS_SHAPE:
            st.error("⚠️ **trimesh kurulu değil.** Terminalde: `pip install trimesh`")
        if not HAS_SHAPELY and not HAS_SHAPE:
            st.warning("⚠️ **shapely kurulu değil.** Terminalde: `pip install shapely`")

        col_unit, col_up = st.columns([1, 2])
        with col_unit:
            stl_unit = st.selectbox(
                "📏 STL Birimi",
                ["cm (SolidWorks varsayılanı)", "mm", "m", "inch"],
                index=0,
                help="SolidWorks → Farklı Kaydet → STL → Seçenekler → Birim"
            )
        _unit_map = {"cm (SolidWorks varsayılanı)":"cm","mm":"mm","m":"m","inch":"inch"}
        _stl_unit_code = _unit_map[stl_unit]

        with col_up:
            up_files = st.file_uploader("Dosyaları sürükleyin", type=["stl","step","stp"],
                                        accept_multiple_files=True,
                                        disabled=not HAS_TRIMESH)

        # ── Session state başlatma ─────────────────────────────────────────
        if "sw_shapes" not in st.session_state:
            st.session_state.sw_shapes = []
        if "sw_staging" not in st.session_state:
            st.session_state.sw_staging = []

        # ── Yeni yüklenen dosyaları staging'e al ────────────────────────────
        # Aynı dosya birden fazla kez eklenebilir — her seferinde yeni staging girdisi
        if up_files and HAS_TRIMESH:
            processed_this_run = set(st.session_state.get("_sw_processed_run", set()))
            _MAX_MESH_MB = 80   # tek dosya sınırı — devasa mesh parse-DoS önlemi
            for uf in up_files:
                if uf.file_id in processed_this_run:
                    continue
                processed_this_run.add(uf.file_id)
                if getattr(uf, "size", 0) and uf.size > _MAX_MESH_MB * 1024 * 1024:
                    st.error(f"⛔ **{uf.name}**: {uf.size/1e6:.0f} MB — "
                             f"tek dosya sınırı {_MAX_MESH_MB} MB. Mesh'i "
                             f"sadeleştirip tekrar deneyin.")
                    continue
                _file_bytes = uf.read()
                with tempfile.NamedTemporaryFile(suffix=Path(uf.name).suffix, delete=False) as tmp:
                    tmp.write(_file_bytes); tmp_path = tmp.name
                try:
                    _ext = Path(uf.name).suffix.lower()
                    with st.spinner(f"📐 {uf.name} analiz ediliyor..."):
                        if _ext == ".stl":
                            try:
                                from shape_engine import load_all_stl_orientations as _lao
                                _all_infos = _lao(tmp_path, unit=_stl_unit_code)
                                # Otomatik en iyi yönelimi seç (en büyük taban)
                                _auto_idx = max(range(len(_all_infos)),
                                    key=lambda i: _all_infos[i].bbox_width * _all_infos[i].bbox_length)
                                info_orig = _all_infos[_auto_idx]
                            except Exception as _stl_e:
                                from shape_engine import load_from_file as _lff
                                _all_infos = None
                                _auto_idx = 0
                                info_orig = _lff(tmp_path, unit=_stl_unit_code)
                        else:
                            from shape_engine import load_from_file as _lff2
                            _all_infos = None
                            _auto_idx = 0
                            info_orig = _lff2(tmp_path, unit=_stl_unit_code)
                    import copy as _copy
                    info = _copy.deepcopy(info_orig)
                    # ID numaralandırma: display_id'yi weight kontrolünden ÖNCE hesapla
                    base_name = Path(uf.name).stem
                    existing_count = sum(
                        1 for s in (st.session_state.sw_staging + st.session_state.sw_shapes)
                        if s.get("base_name", "") == base_name
                    )
                    display_id = f"{base_name}-{existing_count + 1}"
                    raw_wgt = float(info.actual_volume_cm3 * 0.002)
                    # Birim hatası veya aşırı büyük geometriler için clamp
                    if raw_wgt > 99990.0:
                        st.warning(
                            f"⚠️ **{display_id}**: Hesaplanan hacimden gelen tahmini ağırlık "
                            f"çok büyük ({raw_wgt:,.0f} kg). "
                            f"Muhtemelen **birim seçimi yanlış** — "
                            f"STL birimi olarak **mm** seçtiğinizden emin olun. "
                            f"Ağırlık 1 kg olarak ayarlandı, lütfen manuel girin."
                        )
                        default_wgt = 1.0
                    else:
                        default_wgt = max(0.1, raw_wgt)
                    info.name = display_id
                    # all_infos listesi varsa her elemanın adını güncelle
                    if _all_infos:
                        for _oi in _all_infos:
                            _oi.name = display_id
                    st.session_state.sw_staging.append({
                        "name":            display_id,
                        "base_name":       base_name,
                        "file_name":       uf.name,
                        "info":            info,
                        "all_infos":       _all_infos,       # 3 yönelim (STL) veya None
                        "orientation_idx": _auto_idx,        # seçili yönelim indeksi
                        "quantity":        1,
                        "weight":          default_wgt,
                        "customer":        "",
                        "unit":            _stl_unit_code,
                    })
                    st.success(f"✅ **{display_id}** analiz edildi — aşağıdan düzenleyip ekleyin.")
                except Exception as e:
                    st.error(f"❌ {uf.name}: {e}")
                finally:
                    try: os.unlink(tmp_path)
                    except: pass
            st.session_state["_sw_processed_run"] = processed_this_run

        # ── Staging alanı: düzenle ve ekle ─────────────────────────────────
        if st.session_state.sw_staging:
            st.markdown("---")
            st.markdown("### ✏️ Bekleyen Dosyalar — Düzenle & Ekle")
            to_remove = []
            for idx_s, s in enumerate(st.session_state.sw_staging):
                info = s["info"]
                with st.container(border=True):
                    c_hdr, c_del = st.columns([10, 1])
                    is_added = s["name"] in [_sw["name"] for _sw in st.session_state.sw_shapes]
                    _badge = " &nbsp;<span style='background:#1b5e20;color:#a5d6a7;padding:2px 8px;border-radius:10px;font-size:.8rem'>✅ Eklendi</span>" if is_added else ""
                    c_hdr.markdown(
                        f"**📦 {s['name']}**{_badge} — "
                        f"{info.bbox_width:.1f}×{info.bbox_length:.1f}×{info.bbox_height:.1f} cm  "
                        f"|  %{info.fill_ratio*100:.0f} doluluk",
                        unsafe_allow_html=True
                    )
                    if c_del.button("✖", key=f"stage_del_{idx_s}_{s['name']}",
                                    help="İptal et"):
                        # Direkt pop et — rerun'dan önce, yoksa to_remove reset'lenir
                        st.session_state.sw_staging.pop(idx_s)
                        st.rerun()

                    # ── 3D Önizleme + Yönelim Seçici ─────────────────────────
                    if s.get("all_infos"):
                        def _render_stl_preview(si):
                            """STL mesh'ini matplotlib ile CPU tabanlı PNG olarak render et."""
                            import io as _io
                            import numpy as _np
                            import matplotlib.pyplot as _plt
                            from mpl_toolkits.mplot3d.art3d import Poly3DCollection as _P3C
                            if si.mesh_vertices is None or si.mesh_faces is None:
                                return None
                            verts = si.mesh_vertices
                            faces = si.mesh_faces
                            # Çok fazla üçgeni sınırla
                            if len(faces) > 3000:
                                rng = _np.random.default_rng(42)
                                idx = rng.choice(len(faces), 3000, replace=False)
                                faces = faces[idx]
                            triangles = verts[faces]
                            fig = _plt.figure(figsize=(4, 3), facecolor="#0D1117")
                            ax = fig.add_subplot(111, projection="3d")
                            ax.set_facecolor("#161b22")
                            poly = _P3C(triangles, alpha=0.85,
                                        facecolor="#1565C0", edgecolor="none")
                            ax.add_collection3d(poly)
                            W, L, H = si.bbox_width, si.bbox_length, si.bbox_height
                            ax.set_xlim(0, W); ax.set_ylim(0, L); ax.set_zlim(0, H)
                            ax.set_xlabel("G", color="#aaa", fontsize=7)
                            ax.set_ylabel("U", color="#aaa", fontsize=7)
                            ax.set_zlabel("Y", color="#aaa", fontsize=7)
                            ax.tick_params(colors="#666", labelsize=6)
                            for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
                                pane.set_facecolor("#1a1f2e")
                                pane.set_edgecolor("#333")
                            ax.set_title(
                                f"{W:.0f} × {L:.0f} × {H:.0f} cm",
                                color="white", fontsize=9, pad=4)
                            buf = _io.BytesIO()
                            _plt.savefig(buf, format="png", dpi=90,
                                         bbox_inches="tight", facecolor="#0D1117")
                            buf.seek(0)
                            _plt.close(fig)
                            return buf.read()

                        _prev_key = f"_stlprev_{s['name']}_{s['orientation_idx']}"
                        if _prev_key not in st.session_state:
                            with st.spinner("3D önizleme oluşturuluyor..."):
                                st.session_state[_prev_key] = _render_stl_preview(s["info"])

                        _col_prev, _col_orient = st.columns([1, 1])
                        with _col_prev:
                            _png = st.session_state.get(_prev_key)
                            if _png:
                                st.image(_png, width="stretch",
                                         caption="Seçili yönelim önizlemesi")
                            else:
                                st.info("Önizleme üretilemedi.")

                        with _col_orient:
                            st.markdown("**Taban yüzeyini seç:**")
                            _orient_labels = [o[3] for o in s["all_infos"][0].available_orientations]
                            _cur_label = _orient_labels[s["orientation_idx"]]
                            _sel_orient = st.radio(
                                "Yönelim:",
                                _orient_labels,
                                index=s["orientation_idx"],
                                key=f"stl_orient_{idx_s}_{s['name']}",
                                label_visibility="collapsed",
                            )
                            _new_idx = _orient_labels.index(_sel_orient)
                            if _new_idx != s["orientation_idx"]:
                                s["orientation_idx"] = _new_idx
                                s["info"] = s["all_infos"][_new_idx]
                                s["info"].name = s["name"]
                                # Ağırlık tahmini de güncelle
                                _nw = float(s["info"].actual_volume_cm3 * 0.002)
                                if _nw < 99990.0:
                                    s["weight"] = max(0.1, _nw)
                                st.rerun()

                    if HAS_SHAPE and hasattr(shape_summary, '__call__'):
                        with st.expander("📊 Geometri detayları"):
                            st.code(shape_summary(info))
                    if max(info.bbox_width, info.bbox_length, info.bbox_height) < 5.0:
                        st.warning("⚠️ Parça çok küçük — birim seçicisini kontrol edin.")

                    c1, c2, c3 = st.columns(3)
                    qty = c1.number_input("Adet", 1, 9999, value=s["quantity"],
                                          key=f"stage_qty_{idx_s}_{s['name']}")
                    wgt = c2.number_input("Ağırlık (kg)", 0.0, 9_999_999.0,
                                          value=min(float(s["weight"]), 9_999_990.0), step=0.1,
                                          key=f"stage_wgt_{idx_s}_{s['name']}")
                    cst = c3.text_input("Müşteri", value=s["customer"],
                                        key=f"stage_cst_{idx_s}_{s['name']}")

                    is_added = s["name"] in [_sw["name"] for _sw in st.session_state.sw_shapes]

                    if st.button(
                        "🔄 Güncelle" if is_added else "➕ Parça Listesine Ekle",
                        key=f"stage_add_{idx_s}_{s['name']}",
                        type="primary", width="stretch"
                    ):
                        final_name = s["name"]
                        # Staging'deki güncel değerleri kaydet
                        s["quantity"] = qty
                        s["weight"]   = wgt
                        s["customer"] = cst

                        existing_ids = [_sw["name"] for _sw in st.session_state.sw_shapes]
                        if final_name in existing_ids:
                            for _sw in st.session_state.sw_shapes:
                                if _sw["name"] == final_name:
                                    _sw["quantity"] = qty
                                    _sw["weight"]   = wgt
                                    _sw["customer"] = cst
                            # load_rules güncelle
                            if "load_rules" in st.session_state and not st.session_state.load_rules.empty:
                                _mask = st.session_state.load_rules["ID"] == final_name
                                if _mask.any():
                                    st.session_state.load_rules.loc[_mask, "Adet"]        = qty
                                    st.session_state.load_rules.loc[_mask, "Ağırlık(kg)"] = wgt
                                    st.session_state.load_rules.loc[_mask, "Müşteri"]     = cst
                        else:
                            st.session_state.sw_shapes.append({
                                "name":      final_name,
                                "base_name": s.get("base_name", final_name),
                                "info":      info,
                                "quantity":  qty,
                                "weight":    min(float(wgt), 9_999_990.0),
                                "customer":  cst,
                                "unit":      s["unit"],
                            })
                        st.session_state[f"swq_{final_name}"] = qty
                        st.session_state[f"sww_{final_name}"] = wgt
                        st.session_state[f"swc_{final_name}"] = cst
                        # Staging'den SİLME — kullanıcı ✖ ile siler
                        st.rerun()

        # ── Eklenmiş SW parçaları — canlı düzenleme tablosu ────────────────
        if st.session_state.sw_shapes:
            st.markdown("---")
            st.markdown(f"### ✅ Parça Listesine Eklenmiş ({len(st.session_state.sw_shapes)} dosya)")
            st.caption("Aşağıdaki değişiklikler Yük Listesi & Yerleştirme Kuralları ile senkronize edilir.")

            # data_editor ile canlı düzenleme
            sw_rows = []
            for s in st.session_state.sw_shapes:
                info = s["info"]
                sw_rows.append({
                    "ID":           s["name"],
                    "Dosya":        s.get("file_name", s["name"]),
                    "G(cm)":        round(info.bbox_width, 1),
                    "U(cm)":        round(info.bbox_length, 1),
                    "Y(cm)":        round(info.bbox_height, 1),
                    "Adet":         int(st.session_state.get(f"swq_{s['name']}", s["quantity"])),
                    "Ağırlık(kg)":  float(st.session_state.get(f"sww_{s['name']}", s["weight"])),
                    "Müşteri":      str(st.session_state.get(f"swc_{s['name']}", s["customer"])),
                })

            sw_df = pd.DataFrame(sw_rows)
            sw_edited = st.data_editor(
                sw_df,
                width="stretch",
                hide_index=True,
                num_rows="dynamic",
                disabled=["ID","Dosya","G(cm)","U(cm)","Y(cm)"],
                column_config={
                    "ID":          st.column_config.TextColumn("🏷️ ID"),
                    "Dosya":       st.column_config.TextColumn("📂 Dosya"),
                    "G(cm)":       st.column_config.NumberColumn("G(cm)", format="%.1f"),
                    "U(cm)":       st.column_config.NumberColumn("U(cm)", format="%.1f"),
                    "Y(cm)":       st.column_config.NumberColumn("Y(cm)", format="%.1f"),
                    "Adet":        st.column_config.NumberColumn("Adet", min_value=0),
                    "Ağırlık(kg)": st.column_config.NumberColumn("⚖️ Ağırlık(kg)", format="%.2f"),
                    "Müşteri":     st.column_config.TextColumn("👤 Müşteri"),
                },
                key="sw_shapes_editor",
            )

            # ── Duplicate ID kontrolü (eski girdileri otomatik temizle) ────────
            if "ID" in sw_edited.columns:
                dup_mask = sw_edited["ID"].duplicated(keep="first")
                if dup_mask.any():
                    sw_edited = sw_edited[~dup_mask].reset_index(drop=True)
                    st.session_state.sw_shapes = [
                        s for s in st.session_state.sw_shapes
                        if s["name"] in set(sw_edited["ID"].tolist())
                    ]
                    st.warning("⚠️ Duplicate ID'ler temizlendi. Lütfen aynı dosyayı tekrar ekleyin.")

            # Değişiklikleri sw_shapes ve load_rules'a yansıt
            curr_sw_ids = set(sw_edited["ID"].tolist()) if not sw_edited.empty else set()
            prev_sw_ids = {s["name"] for s in st.session_state.sw_shapes}
            deleted_sw  = prev_sw_ids - curr_sw_ids
            if deleted_sw:
                st.session_state.sw_shapes = [
                    s for s in st.session_state.sw_shapes
                    if s["name"] not in deleted_sw
                ]
                st.session_state.deleted_ids |= deleted_sw
                if "load_rules" in st.session_state and not st.session_state.load_rules.empty:
                    st.session_state.load_rules = st.session_state.load_rules[
                        ~st.session_state.load_rules["ID"].isin(deleted_sw)
                    ].reset_index(drop=True)
                st.rerun()

            if not sw_edited.empty:
                for _, row in sw_edited.iterrows():
                    pid = str(row["ID"])
                    new_qty = int(row.get("Adet", 1))
                    new_wgt = float(row.get("Ağırlık(kg)", 0))
                    new_cst = str(row.get("Müşteri", ""))
                    # Session state key güncelle
                    st.session_state[f"swq_{pid}"] = new_qty
                    st.session_state[f"sww_{pid}"] = new_wgt
                    st.session_state[f"swc_{pid}"] = new_cst
                    # sw_shapes güncelle
                    for _sw in st.session_state.get("sw_shapes", []):
                        if _sw["name"] == pid:
                            _sw["quantity"] = new_qty
                            _sw["weight"]   = new_wgt
                            _sw["customer"] = new_cst
                    # load_rules senkronizasyonu
                    if "load_rules" in st.session_state and not st.session_state.load_rules.empty:
                        mask = st.session_state.load_rules["ID"] == pid
                        if mask.any():
                            st.session_state.load_rules.loc[mask, "Adet"]        = new_qty
                            st.session_state.load_rules.loc[mask, "Ağırlık(kg)"] = new_wgt
                            st.session_state.load_rules.loc[mask, "Müşteri"]     = new_cst
                    # staging'de bekleyen varsa güncelle
                    for _s in st.session_state.get("sw_staging", []):
                        if _s["name"] == pid:
                            _s["quantity"] = new_qty
                            _s["weight"]   = new_wgt
                            _s["customer"] = new_cst

            if st.button("🗑️ Tüm SW Parçalarını Temizle"):
                st.session_state.sw_shapes  = []
                st.session_state.sw_staging = []
                st.session_state.pop("_sw_processed_run", None)
                st.rerun()

    # ── Excel İçe Aktarım ────────────────────────────────────────────────────
    with t_xl:
        st.markdown("#### 📊 Excel'den Araç ve Yük Verisi İçe Aktar")

        col_dl, col_up = st.columns([1, 2])
        with col_dl:
            st.markdown("**Excel Şablonu**")
            st.caption("Uygun kolon başlıklarına sahip hazır şablon:")
            import os as _os
            _tpl_search = [
                "loadplan_template.xlsx",
                _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                              "loadplan_template.xlsx"),
                _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                              "..", "loadplan_template.xlsx"),
            ]
            _tpl_bytes = None
            for _p in _tpl_search:
                try:
                    with open(_p, "rb") as _tf:
                        _tpl_bytes = _tf.read()
                    break
                except FileNotFoundError:
                    continue
            if _tpl_bytes:
                st.download_button(
                    "⬇ Boş Şablonu İndir",
                    data=_tpl_bytes,
                    file_name="loadplan_template.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch",
                    type="primary",
                )
            else:
                st.caption("loadplan_template.xlsx bulunamadı.")

        with col_up:
            st.markdown("**2. Doldurulmuş Dosyayı Yükle**")
            st.caption("Şablonu doldurup yükleyin — Araçlar ve Yükler sayfaları otomatik okunur:")
            xl_file = st.file_uploader(
                "Excel dosyası seç",
                type=["xlsx", "xls"],
                key="xl_import_uploader",
                label_visibility="collapsed",
            )

        if xl_file is not None:
            xl_bytes = xl_file.read()
            with st.spinner("Excel okunuyor…"):
                df_t_xl, df_p_xl, xl_errors = import_excel(xl_bytes)

            if xl_errors:
                for err in xl_errors:
                    st.error(f"❌ {err}")

            # Araçlar önizleme
            if df_t_xl is not None and not df_t_xl.empty:
                st.markdown(f"**🚛 Araçlar** — {len(df_t_xl)} satır okundu")
                st.dataframe(df_t_xl, hide_index=True, width="stretch")
            elif not xl_errors:
                st.warning("Araçlar sayfası bulunamadı veya veri yok.")

            # Yükler önizleme
            if df_p_xl is not None and not df_p_xl.empty:
                st.markdown(f"**📦 Yükler** — {len(df_p_xl)} satır okundu")
                st.dataframe(df_p_xl, hide_index=True, width="stretch",
                    column_config={
                        "Altına yerleştirilemez": st.column_config.CheckboxColumn("🚫 Altına"),
                        "Üstüne yerleştirilemez": st.column_config.CheckboxColumn("⛔ Üstüne"),
                        "Rotasyon":               st.column_config.CheckboxColumn("🔄 Rot."),
                        "Min. Aralık (cm)":       st.column_config.NumberColumn(
                            "↔️ Min. Aralık", width="small"),
                        "Öncelik":                st.column_config.NumberColumn(
                            "🚚 Öncelik", width="small",
                            help="0/boş = normal · 1 = kapıya en yakın"),
                    })
            elif not xl_errors:
                st.warning("Yükler sayfası bulunamadı veya veri yok.")

            # Uygula butonu
            if (df_t_xl is not None or df_p_xl is not None) and not xl_errors:
                _xl_mode = st.radio(
                    "Mevcut verilerle ne yapılsın?",
                    ["🔄 Üzerine yaz (mevcut verileri sil)", "➕ Mevcut veriye ekle"],
                    horizontal=True, key="xl_import_mode",
                )
                if st.button("✅ İçe Aktarımı Uygula", type="primary", width="stretch"):
                    _overwrite = "Üzerine yaz" in _xl_mode

                    # Araçlar
                    if df_t_xl is not None and not df_t_xl.empty:
                        if _overwrite:
                            st.session_state.df_trucks = df_t_xl.copy()
                        else:
                            existing_t = st.session_state.get("df_trucks", pd.DataFrame())
                            st.session_state.df_trucks = pd.concat(
                                [existing_t, df_t_xl], ignore_index=True
                            ).drop_duplicates(subset=["ID"], keep="last").reset_index(drop=True)
                        # Araç tablosu base'i değişti → editör delta'ları artık
                        # geçersiz; key'i ve live kopyayı temizle (yanlış hizalama önlenir)
                        st.session_state.pop("df_trucks_editor", None)
                        st.session_state.pop("df_trucks_live", None)
                        st.success(f"✅ {len(df_t_xl)} araç yüklendi.")

                    # Yükler
                    if df_p_xl is not None and not df_p_xl.empty:
                        # df_pallets güncelle
                        _pal_cols = ["ID", "Şekil", "Genişlik (cm)", "Uzunluk (cm)",
                                     "Yükseklik (cm)", "Ağırlık (kg)", "Adet", "Müşteri",
                                     "Öncelik"]
                        # Öncelik sütunu yoksa boş oluştur (geriye dönük uyumluluk)
                        for _c in _pal_cols:
                            if _c not in df_p_xl.columns:
                                df_p_xl[_c] = None
                        _df_pal_new = df_p_xl[_pal_cols].copy()
                        _df_pal_new = _df_pal_new.rename(columns={
                            "Ağırlık (kg)": "Ağırlık (kg)",
                        })
                        if _overwrite:
                            st.session_state.df_pallets = _df_pal_new
                            # Yük listesini de sıfırla
                            st.session_state.pop("load_rules", None)
                            st.session_state.pop("deleted_ids", None)
                        else:
                            existing_p = st.session_state.get("df_pallets", pd.DataFrame())
                            st.session_state.df_pallets = pd.concat(
                                [existing_p, _df_pal_new], ignore_index=True
                            ).drop_duplicates(subset=["ID"], keep="last").reset_index(drop=True)

                        # load_rules'a doğrudan ekle (kural sütunlarıyla)
                        _lr_rows = []
                        _existing_lr_ids = set(
                            st.session_state.get("load_rules", pd.DataFrame()).get("ID", [])
                            if "load_rules" in st.session_state else []
                        )
                        for _, _row in df_p_xl.iterrows():
                            _pid = str(_row["ID"])
                            if not _overwrite and _pid in _existing_lr_ids:
                                continue
                            _lr_rows.append({
                                "Kaynak": "Excel",
                                "ID": _pid,
                                "Şekil": _row.get("Şekil", "Dikdörtgen"),
                                "G(cm)": float(_row.get("Genişlik (cm)", 0)),
                                "U(cm)": float(_row.get("Uzunluk (cm)", 0)),
                                "Y(cm)": float(_row.get("Yükseklik (cm)", 0)),
                                "Adet": int(_row.get("Adet", 1)),
                                "Ağırlık(kg)": float(_row.get("Ağırlık (kg)", 0)),
                                "Müşteri": str(_row.get("Müşteri", "")),
                                "Altına yerleştirilemez": bool(_row.get("Altına yerleştirilemez", False)),
                                "Üstüne yerleştirilemez": bool(_row.get("Üstüne yerleştirilemez", False)),
                                "Rotasyon": bool(_row.get("Rotasyon", True)),
                                "Min. Aralık (cm)": int(_row.get("Min. Aralık (cm)", 0)),
                                "Öncelik": int(_row["Öncelik"]) if "Öncelik" in _row and str(_row.get("Öncelik","")).strip() not in ("","nan","None") else None,
                            })
                        if _lr_rows:
                            _new_lr = pd.DataFrame(_lr_rows)
                            if _overwrite or "load_rules" not in st.session_state \
                                    or st.session_state.load_rules.empty:
                                st.session_state.load_rules = _new_lr
                            else:
                                st.session_state.load_rules = pd.concat(
                                    [st.session_state.load_rules, _new_lr],
                                    ignore_index=True
                                ).drop_duplicates(subset=["ID"], keep="last").reset_index(drop=True)
                        st.success(f"✅ {len(df_p_xl)} yük yüklendi.")

                    st.rerun()

        st.markdown("---")
        st.markdown("**📋 Desteklenen Kolon Başlıkları**")
        _col_info = {
            "Araçlar sayfası": "ID · Genişlik (cm) · Uzunluk (cm) · Yükseklik (cm) · Kapasite (kg) · Adet",
            "Yükler sayfası (zorunlu)": "ID · Genişlik (cm) · Uzunluk (cm) · Yükseklik (cm) · Ağırlık (kg) · Adet",
            "Yükler sayfası (isteğe bağlı)": "Şekil · Müşteri · Altına yerleştirilemez · Üstüne yerleştirilemez · Rotasyon · Min. Aralık (cm) · Öncelik",
            "Türkçe/İngilizce eşdeğerleri": "genislik=Genişlik · agirlik=Ağırlık · musteri=Müşteri · rotation=Rotasyon",
        }
        for k, v in _col_info.items():
            st.caption(f"**{k}:** {v}")

    st.markdown("---")

    # ═══════════════════════════════════════════════════════════════════════════
    # YÜK LİSTESİ & YERLEŞTİRME KURALLARI — TEK KAYNAK
    # Silinen satır kalıcı olarak kaldırılır, yeni yük eklenince geri gelmez.
    # Algoritma yalnızca bu tablodaki parçaları kullanır.
    # ═══════════════════════════════════════════════════════════════════════════
    # ── Hangi filo kullanılıyor? (ana ekranda da görünsün) ───────────────
    from filo_secimi import aktif_filo as _aktif_filo
    _ana_ck, _ana_dr = _aktif_filo()
    if _ana_ck and _ana_dr:
        _ana_plakalar = ", ".join(d.plaka for d in _ana_dr[:4])
        if len(_ana_dr) > 4:
            _ana_plakalar += f" (+{len(_ana_dr) - 4})"
        st.info(
            f"🚚 **Çekici + dorse filosu kullanılıyor** — {len(_ana_ck)} çekici, "
            f"{len(_ana_dr)} dorse ({_ana_plakalar}). Kütle kapasitesi KTY "
            f"md.128'den hesaplanıyor; her yerleştirmede dingil yükü "
            f"kontrol ediliyor. Değiştirmek için → 🚚 Filo sayfası."
        )
    else:
        st.caption("🚛 Kenar çubuğundaki araç tablosu kullanılıyor. "
                   "Çekici/dorse ayrımı, mevzuat kapasitesi ve dingil "
                   "kontrolü için → 🚚 Filo sayfası.")

    st.subheader("📋 Yük Listesi & Yerleştirme Kuralları")
    st.caption("Bu tablo algoritmaya gönderilecek yük listesidir. "
               "Satır silin, adet/kural değiştirin — algoritma yalnızca bu tabloyu kullanır.")

    if "deleted_ids" not in st.session_state:
        st.session_state.deleted_ids = set()
    if "geom_store" not in st.session_state:
        st.session_state.geom_store = {}

    def _sync_new_items():
        """Kaynaklardaki yeni ID'leri load_rules'a ekle; silinmişleri atla."""
        existing = set(st.session_state.get("load_rules", pd.DataFrame()).get("ID", []))
        new_rows = []

        for _, r in st.session_state.get("df_pallets", pd.DataFrame()).iterrows():
            pid = str(r.get("ID", ""))
            if not pid or pid in existing or pid in st.session_state.deleted_ids:
                continue
            existing.add(pid)   # ← Bu render döngüsünde eklendi; tekrar ekleme
            new_rows.append({
                "Kaynak": "Manuel", "ID": pid,
                "Şekil": str(r.get("Şekil", "Dikdörtgen")),
                "G(cm)": float(r.get("Genişlik (cm)", 0)),
                "U(cm)": float(r.get("Uzunluk (cm)", 0)),
                "Y(cm)": float(r.get("Yükseklik (cm)", 0)),
                "Adet": int(r.get("Adet", 1)),
                "Ağırlık(kg)": float(r.get("Ağırlık (kg)", 0)),
                "Müşteri": str(r.get("Müşteri", "")),
                "Altına yerleştirilemez": False,
                "Üstüne yerleştirilemez": False,
                "Rotasyon": True,  # Yük Listesi'nden yönetilir
                "Min. Aralık (cm)": 0,
                "Öncelik": int(r.get("Öncelik")) if r.get("Öncelik") is not None and str(r.get("Öncelik","")).strip() not in ("","nan","None") else None,
            })

        _sw_seen_in_sync = set()  # Bu sync döngüsünde görülen ID'ler
        for sw in st.session_state.get("sw_shapes", []):
            info = sw["info"]
            pid  = info.name
            # Duplicate ID'leri atla (aynı run içinde veya daha önce eklendiyse)
            if pid in existing or pid in st.session_state.deleted_ids or pid in _sw_seen_in_sync:
                continue
            _sw_seen_in_sync.add(pid)
            existing.add(pid)   # ← Bu render döngüsünde eklendi; tekrar ekleme
            qty = int(st.session_state.get(f"swq_{sw['name']}", sw.get("quantity", 1)))
            wgt = float(st.session_state.get(f"sww_{sw['name']}", sw.get("weight", 0)))
            st.session_state.geom_store[pid] = {
                "shape_type": info.shape_type, "cross_section": info.cross_section,
                "fill_ratio": info.fill_ratio, "mesh_vertices": info.mesh_vertices,
                "mesh_faces": info.mesh_faces, "source": "stl",
            }
            new_rows.append({
                "Kaynak": "STL/STEP", "ID": pid, "Şekil": _shape_label(info),
                "G(cm)": round(info.bbox_width, 1), "U(cm)": round(info.bbox_length, 1),
                "Y(cm)": round(info.bbox_height, 1), "Adet": qty,
                "Ağırlık(kg)": round(wgt, 2),
                "Müşteri": str(st.session_state.get(f"swc_{sw['name']}", "")),
                "Altına yerleştirilemez": False, "Üstüne yerleştirilemez": False, "Rotasyon": True,
                "Min. Aralık (cm)": 0, "Öncelik": None,
            })

        for pf in st.session_state.get("custom_profiles", []):
            info = pf["info"]
            pid  = pf["id"]
            if pid in existing or pid in st.session_state.deleted_ids:
                continue
            existing.add(pid)   # ← Bu render döngüsünde eklendi; tekrar ekleme
            st.session_state.geom_store[pid] = {
                "shape_type": info.shape_type, "cross_section": info.cross_section,
                "fill_ratio": info.fill_ratio,
                "mesh_vertices": getattr(info, "mesh_vertices", None),
                "mesh_faces": getattr(info, "mesh_faces", None), "source": "profile",
                "inner_diameter": float(pf.get("t1", 0) or 0),
            }
            new_rows.append({
                "Kaynak": "Profil", "ID": pid, "Şekil": _shape_label(info),
                "G(cm)": round(info.bbox_width, 1), "U(cm)": round(info.bbox_length, 1),
                "Y(cm)": round(info.bbox_height, 1),
                "Adet": int(pf.get("quantity", 1)), "Ağırlık(kg)": float(pf.get("weight", 0)),
                "Müşteri": str(pf.get("customer", "")),
                "Altına yerleştirilemez": False, "Üstüne yerleştirilemez": False, "Rotasyon": True,
                "Min. Aralık (cm)": 0, "Öncelik": None,
            })

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            if "load_rules" not in st.session_state or st.session_state.load_rules.empty:
                st.session_state.load_rules = new_df
            else:
                st.session_state.load_rules = pd.concat(
                    [st.session_state.load_rules, new_df], ignore_index=True)

    _sync_new_items()

    # ── Eski oturumlardan kalan t1/t2 sütunlarını tablodan tamamen kaldır ────
    for _df_key in ("load_rules", "load_rules_live"):
        _df_ref = st.session_state.get(_df_key)
        if _df_ref is not None and not _df_ref.empty:
            _drop = [c for c in ("t1(cm)", "t2(cm)") if c in _df_ref.columns]
            if _drop:
                st.session_state[_df_key] = _df_ref.drop(columns=_drop)

    # ── _sync_new_items tarafından load_rules'a eklenen yeni satırları
    #    load_rules_live'a da ekle (algoritma her zaman live'ı kullanır)
    if "load_rules_live" in st.session_state and "load_rules" in st.session_state:
        if not st.session_state.load_rules.empty:
            _live_ids = (
                set(st.session_state.load_rules_live["ID"].dropna().astype(str).tolist())
                if not st.session_state.load_rules_live.empty else set()
            )
            _newly_in_base = st.session_state.load_rules[
                ~st.session_state.load_rules["ID"].astype(str).isin(_live_ids)
            ]
            if not _newly_in_base.empty:
                st.session_state.load_rules_live = pd.concat(
                    [st.session_state.load_rules_live, _newly_in_base],
                    ignore_index=True,
                )

    # ── Çift yönlü senkronizasyon: load_rules → sw_shapes + staging ─────────
    if "load_rules" in st.session_state and not st.session_state.load_rules.empty:
        lr = st.session_state.load_rules
        _lr_stl = lr[lr["Kaynak"] == "STL/STEP"] if "Kaynak" in lr.columns else pd.DataFrame()
        if not _lr_stl.empty:
            # sw_shapes güncelle
            for _sw in st.session_state.get("sw_shapes", []):
                _pid = _sw["info"].name
                _mask = _lr_stl["ID"] == _pid
                if _mask.any():
                    _lr_row = _lr_stl[_mask].iloc[0]
                    _new_qty = int(_lr_row.get("Adet", _sw["quantity"]))
                    _new_wgt = float(_lr_row.get("Ağırlık(kg)", _sw["weight"]))
                    _new_cst = str(_lr_row.get("Müşteri", _sw["customer"]))
                    st.session_state[f"swq_{_pid}"] = _new_qty
                    st.session_state[f"sww_{_pid}"] = _new_wgt
                    st.session_state[f"swc_{_pid}"] = _new_cst
                    _sw["quantity"] = _new_qty
                    _sw["weight"]   = _new_wgt
                    _sw["customer"] = _new_cst
            # Staging'deki parçaları da güncelle (henüz eklenmemiş bekleyenler)
            _lr_all = lr if not lr.empty else pd.DataFrame()
            for _s in st.session_state.get("sw_staging", []):
                _pid = _s["name"]
                _mask2 = _lr_all["ID"] == _pid if "ID" in _lr_all.columns else pd.Series(dtype=bool)
                if not _mask2.empty and _mask2.any():
                    _lr_row2 = _lr_all[_mask2].iloc[0]
                    _s["quantity"] = int(_lr_row2.get("Adet", _s["quantity"]))
                    _s["weight"]   = float(_lr_row2.get("Ağırlık(kg)", _s["weight"]))
                    _s["customer"] = str(_lr_row2.get("Müşteri", _s["customer"]))

    # load_rules_live yoksa base'den kopyala (ilk açılış / sıfırlama sonrası)
    if "load_rules_live" not in st.session_state and "load_rules" in st.session_state:
        st.session_state.load_rules_live = st.session_state.load_rules.copy()

    # ── Fragment: tablo düzenlenirken sadece bu bölüm yeniden çalışır ────────
    def _load_rules_editor_ui():
        if st.session_state.get("load_rules") is None or st.session_state.load_rules.empty:
            st.info("Henüz yük tanımlanmamış. Yukarıdaki sekmelerden yük ekleyin.")
            return

        prev_ids = set(st.session_state.load_rules["ID"].tolist())

        edited = st.data_editor(
            st.session_state.load_rules,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            disabled=["Kaynak"],
            column_config={
                "Kaynak":    st.column_config.TextColumn("📂 Kaynak", width="small"),
                "ID":        st.column_config.TextColumn("🏷️ ID", required=True),
                "Şekil":     st.column_config.SelectboxColumn("📐 Şekil",
                                 options=["Dikdörtgen","Silindir"],
                                 required=True),
                "G(cm)":     st.column_config.NumberColumn("G(cm)", format="%.1f", min_value=1),
                "U(cm)":     st.column_config.NumberColumn("U(cm)", format="%.1f", min_value=1),
                "Y(cm)":     st.column_config.NumberColumn("Y(cm)", format="%.1f", min_value=1),
                "Adet":      st.column_config.NumberColumn("Adet", width="small", min_value=0),
                "Ağırlık(kg)": st.column_config.NumberColumn("⚖️ Ağırlık(kg)", format="%.1f", min_value=0),
                "Müşteri":   st.column_config.TextColumn("👤 Müşteri"),
                "Altına yerleştirilemez": st.column_config.CheckboxColumn(
                    "🚫 Altına yük konmasın",
                    help="Bu yükün altına başka yük yerleştirilemez (zemine oturur)"),
                "Üstüne yerleştirilemez": st.column_config.CheckboxColumn(
                    "⛔ Üstüne yük konmasın",
                    help="Bu yük kırılgan/hassas — üstüne hiçbir yük yerleştirilemez"),
                "Rotasyon":  st.column_config.CheckboxColumn(
                    "🔄 Rotasyon", help="Yük XY düzleminde döndürülebilir"),
                "Min. Aralık (cm)": st.column_config.NumberColumn(
                    "↔️ Min. Aralık (cm)",
                    min_value=0, max_value=100, step=1, default=0,
                    help="Bu parçanın çevresinde bırakılacak minimum boşluk (cm)."),
                "Öncelik": st.column_config.NumberColumn(
                    "🚚 Öncelik", min_value=1, step=1,
                    help="Teslimat önceliği: 1 = kapıya en yakın. Boş = önceliksiz."),
            },
            key="load_rules_editor",
        )

        # Yeni satırlarda Kaynak boşsa "Manuel" yaz
        if not edited.empty and "Kaynak" in edited.columns:
            edited["Kaynak"] = edited["Kaynak"].fillna("Manuel").replace("", "Manuel")

        # ── Silinen satırları işle (sadece silinme varsa base güncellenir) ──
        curr_ids = set(edited["ID"].dropna().astype(str).tolist()) if not edited.empty else set()
        newly_deleted = prev_ids - curr_ids
        if newly_deleted:
            st.session_state.deleted_ids |= newly_deleted
            if "df_pallets" in st.session_state:
                st.session_state.df_pallets = st.session_state.df_pallets[
                    ~st.session_state.df_pallets["ID"].isin(newly_deleted)
                ].reset_index(drop=True)
            st.session_state.sw_shapes = [
                s for s in st.session_state.get("sw_shapes", [])
                if s["info"].name not in newly_deleted
            ]
            st.session_state.custom_profiles = [
                p for p in st.session_state.get("custom_profiles", [])
                if p["id"] not in newly_deleted
            ]
            for did in newly_deleted:
                st.session_state.geom_store.pop(did, None)
            # Silinen satırları base'den de çıkar — widget zaten silindi gösteriyor
            st.session_state.load_rules = st.session_state.load_rules[
                ~st.session_state.load_rules["ID"].isin(newly_deleted)
            ].reset_index(drop=True)

        # ── KRİTİK: load_rules_live = mevcut tablo durumu (base güncellenmez!) ──
        # load_rules (base) asla inline düzenlemeden güncellenmez;
        # aksi hâlde st.data_editor widget'ı sıfırlanır ve yazılan veri silinir.
        # Algoritma load_rules_live'dan okur.
        st.session_state.load_rules_live = edited

        # Metrikler
        if not edited.empty:
            _adet = edited["Adet"].fillna(0)
            _agir = edited["Ağırlık(kg)"].fillna(0)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Toplam Parça", int(_adet.sum()))
            m2.metric("Toplam Ağırlık", f"{float((_agir * _adet).sum()):,.0f} kg")
            m3.metric("Altına yük konmaz", int(edited["Altına yerleştirilemez"].fillna(False).sum()))
            m4.metric("Üstüne yük konmaz", int(edited["Üstüne yerleştirilemez"].fillna(False).sum()))

        if st.button("🔄 Yük Listesini Sıfırla",
                     help="Tüm yükler ve silme geçmişi temizlenir, sıfırdan başlanır"):
            for k in ["load_rules", "load_rules_live", "deleted_ids", "geom_store",
                      "df_pallets", "sw_shapes", "sw_staging", "custom_profiles"]:
                st.session_state.pop(k, None)
            st.rerun()

    # st.fragment: Streamlit ≥ 1.33 — tablo düzenlenirken tam sayfa yeniden çalışmaz
    try:
        _load_rules_editor_ui = st.fragment(_load_rules_editor_ui)
    except AttributeError:
        pass  # Eski Streamlit — normal fonksiyon olarak çalışır

    _load_rules_editor_ui()


    st.markdown("---")

    # ── BAŞLAT BUTONU ─────────────────────────────────────────────────────────
    _,btn_col,_ = st.columns([1,2,1])
    with btn_col:
        btn_label = (f"🚀 {ALGORITHMS.get(sel_algo,{}).get('name',sel_algo)} Çalıştır"
                     if mode=="🎯 Tek" else f"📊 {len(sel_algos)} Algoritma Karşılaştır")
        run_btn = st.button(btn_label, type="primary", width="stretch")

        # ⚡ Optimizasyon (iteratif otomatik motor) projeden kaldırıldı.
        # Yalnızca manuel algoritma çalıştırma/karşılaştırma kullanılır.
        tam_opt_btn = False
        auto_btn    = False
        fleet_btn   = False

    # ═══════════════════════════════════════════════════════════════════════
    # MANUEL ÇALIŞTIR — Tek / Karşılaştırmalı algoritma
    # ═══════════════════════════════════════════════════════════════════════
    if run_btn:
        # Algoritma YALNIZCA yük listesindeki (live) parçaları kullanır
        pieces_3d = build_pieces_from_load_rules(
            st.session_state.get("load_rules_live",
                st.session_state.get("load_rules", pd.DataFrame())),
            st.session_state.get("geom_store", {}),
        )
        trucks_3d = build_trucks(df_trucks)
        if not pieces_3d: st.error("❌ Yük tanımlanmamış!"); st.stop()
        if not trucks_3d: st.error("❌ Araç tanımlanmamış!"); st.stop()

        # ── Akıllı Araç Seçimi (toggle açıksa) ────────────────────────────
        if use_fleet_opt and HAS_FLEET_OPT:
            _fs_stat = st.info("🚛 Araç kombinasyonları taranıyor…")
            _fs_bar  = st.progress(0)
            def _fs_cb(trial, total, score):
                _fs_bar.progress(min(trial / max(total, 1), 1.0))
            try:
                _, _best_cfg, _fleet_results = fleet_optimizer_3d(
                    pieces_3d, trucks_3d,
                    time_budget=max(15, int(auto_time_budget * 0.35)) if HAS_AUTO_OPT else 30,
                    max_configs=200, packing_algo="auto", use_bayesian=True,
                    progress_callback=_fs_cb,
                )
                if _best_cfg and _best_cfg.trucks:
                    trucks_3d = sorted(_best_cfg.trucks,
                                       key=lambda t: t.get_volume(), reverse=True)
                    _fs_stat.success(
                        f"✅ En iyi araç kombinasyonu: **{_best_cfg.label()}**")
                else:
                    _fs_stat.warning("⚠️ Araç seçimi sonuç vermedi, orijinal filo kullanılıyor.")
            except Exception as _fe:
                _fs_stat.warning(f"⚠️ Araç seçimi hatası: {_fe} — orijinal filo kullanılıyor.")
            _fs_bar.progress(1.0)

        run_list = [sel_algo] if mode == "🎯 Tek" else sel_algos
        if not run_list:
            st.warning("⚠️ En az bir algoritma seçin."); st.stop()
        all_results = {}
        # ── ARTIMLI KALICILIK: sonuç sözlüğü koşu BAŞINDA session_state'e
        # bağlanır; her algoritma bittiğinde otomatik birikir. Böylece uzun
        # karşılaştırmalı koşu sırasında bir widget-rerun'u tamamlanan
        # algoritmaların sonuçlarını kaybettirmez.
        st.session_state["last_results"]      = all_results
        st.session_state["last_pieces_3d"]    = pieces_3d
        st.session_state["last_trucks_3d"]    = trucks_3d
        st.session_state["last_mode"]         = mode
        st.session_state["last_project_name"] = project_name or "rapor"

        prog = st.progress(0); stat = st.empty()
        algo_prog = st.progress(0.0)   # algoritma-İÇİ ilerleme (callback'li)

        _algo_kw = dict(
            ts_time=ts_time, ts_tenure=ts_tenure,
            sa_time=sa_time, sa_temp=sa_temp, sa_cool=sa_cool,
            mc_iter=mc_iter, ga_pop=ga_pop, ga_gen=ga_gen,
            ga_time=ga_time, ga_workers=ga_workers,
            layer_strat=layer_strat, nfp_res=nfp_res, nfp_margin=nfp_margin,
            bay_time=bay_time, bay_trials=bay_trials, bay_target=bay_target,
            isl_islands=isl_islands, isl_pop=isl_pop, isl_gen=isl_gen, isl_mig=isl_mig,
            isl_time=isl_time, isl_workers=isl_workers,
            ms_starts=ms_starts, ms_time=ms_time,
            seed=rng_seed,
        )

        for idx, akey in enumerate(run_list):
            stat.info(f"⏳ {ALGORITHMS[akey]['name']} çalışıyor… ({idx+1}/{len(run_list)})")
            prog.progress(idx / len(run_list))
            algo_prog.progress(0.0)

            def _algo_cb(cur, total, *rest):
                """Algoritma-içi ilerleme (GA/MC/Island/MS/Bayes/Tabu/SA)."""
                try:
                    algo_prog.progress(min(max(cur / max(total, 1), 0.0), 1.0))
                except Exception:
                    pass

            try:
                plan = run_algo_with_validation(
                    akey, pieces_3d, trucks_3d,
                    progress_cb=_algo_cb, **_algo_kw)
                if plan:
                    # Seçilen araçlara sığmayan parça varsa → tam filo ile tekrar dene
                    _total_req = sum(p.quantity for p in pieces_3d)
                    _placed    = sum(len(b) for b in plan.bins)
                    _orig_trucks = build_trucks(df_trucks)
                    if use_fleet_opt and _placed < _total_req and _orig_trucks != trucks_3d:
                        stat.warning(
                            f"⚠️ Seçilen araçlara {_total_req - _placed} parça sığmadı — "
                            f"tam filo ile tekrar deneniyor…")
                        try:
                            plan2 = run_algo_with_validation(
                                akey, pieces_3d, _orig_trucks, **_algo_kw)
                            if plan2 and sum(len(b) for b in plan2.bins) > _placed:
                                plan = plan2
                                trucks_3d = _orig_trucks
                        except Exception:
                            pass
                    if compact_fwd:
                        try:
                            plan = compact_forward(plan, pieces_3d, trucks_3d)
                        except Exception as _cfe:
                            st.warning(f"⚠️ Öne sıkıştırma atlandı "
                                       f"({ALGORITHMS[akey]['name']}): {_cfe}")
                    all_results[ALGORITHMS[akey]["name"]] = plan
            except Exception as e:
                st.warning(f"⚠️ {ALGORITHMS[akey]['name']}: {e}")

        prog.progress(1.0); stat.empty(); prog.empty(); algo_prog.empty()
        if not all_results:
            st.error("❌ Hiçbir algoritma tamamlanamadı!"); st.stop()

        # (Sonuçlar koşu başında session_state'e bağlandı — artımlı birikti.)
        try:
            _rdict_tmp  = results_dict_from(all_results, pieces_3d)
            _best_tmp   = max(all_results, key=lambda k: plan_rank(all_results[k]))
            st.session_state["last_rdict"]     = _rdict_tmp
            st.session_state["last_best_name"] = _best_tmp
        except Exception:
            pass

        # Görsel önbellek: EAGER üretim kaldırıldı — tüm algoritma × araç
        # figürlerini peşinen üretmek hem koşuyu uzatıyor hem yüzlerce MB
        # bellek tutuyordu. Figürler artık ilk görüntülemede üretilip
        # sınırlı boyutlu önbelleğe alınır (aşağıda _cached_fig).
        st.session_state["last_fig_cache"] = {}

        # Yerleştirilemeyen parça uyarısı
        total_req = sum(p.quantity for p in pieces_3d)
        best_placed = max(sum(len(b) for b in plan.bins) for plan in all_results.values())
        if best_placed < total_req:
            st.warning(
                f"⚠️ **{total_req - best_placed} parça yerleştirilemedi.** "
                "Araç kapasitesi yetersiz olabilir, parçalar araç boyutlarına sığmıyor "
                "olabilir veya Min. aralık çok büyük. Büyük araç ekleyin ya da araç "
                "adedini artırıp tekrar deneyin.")
        else:
            st.success(
                f"✅ {len(all_results)} algoritma tamamlandı — "
                f"tüm {total_req} parça yerleştirildi!")

        # Proje kaydet + rapor (ikincil — hata olsa da çalıştırma bozulmaz)
        try:
            rdict = results_dict_from(all_results, pieces_3d)
            best_name = max(all_results, key=lambda k: plan_rank(all_results[k]))
            if project_name:
                proj = db_mod.create_project(co["id"], user["id"], project_name, project_desc)
                db_mod.save_project_data(
                    proj.id,
                    trucks=df_trucks.to_dict("records"),
                    pieces=st.session_state.get("df_pallets", pd.DataFrame()).to_dict("records"),
                    params={"algorithms": run_list, "nfp_res": nfp_res},
                    results=rdict)
                st.info(f"💾 Proje kaydedildi: **{project_name}**")
        except Exception as _pe:
            # Sessiz yutma YOK: kullanıcı kaydın başarısız olduğunu görmeli
            st.warning(f"⚠️ Proje veritabanına kaydedilemedi: {_pe} — "
                       "sonuçlar bu oturumda kullanılabilir durumda.")

        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SONUÇ GÖSTERİMİ — session_state'ten oku (run_btn'den bağımsız, her rerun'da korunur)
# ─────────────────────────────────────────────────────────────────────────────
if page == "🚀 Optimizasyon" and "last_results" in st.session_state:
    import hashlib as _hs

    _all_results = st.session_state["last_results"]
    _pieces_3d   = st.session_state["last_pieces_3d"]
    _trucks_3d   = st.session_state["last_trucks_3d"]
    _last_mode   = st.session_state["last_mode"]
    _is_cmp      = (_last_mode == "📊 Karşılaştırmalı")
    _fig_cache   = st.session_state.setdefault("last_fig_cache", {})

    _FIG_CACHE_MAX = 24   # bellek sınırı: en fazla bu kadar figür tutulur

    def _cached_fig(aname, bid):
        """Tembel figür üretimi + sınırlı önbellek (LRU-vari basit tahliye)."""
        key = (aname, bid)
        if key in _fig_cache:
            return _fig_cache[key]
        fig = visualize_3d_plan(
            _all_results[aname], _trucks_3d, _pieces_3d, bid, show_truck, show_grid)
        if fig is not None:
            if len(_fig_cache) >= _FIG_CACHE_MAX:
                _fig_cache.pop(next(iter(_fig_cache)))   # en eskiyi at
            _fig_cache[key] = fig
        return fig

    def _show_3d_fast(aname, bid, plotly_key):
        fig = _cached_fig(aname, bid)
        if fig:
            st.plotly_chart(fig, width="stretch", key=plotly_key)
        else:
            st.info(f"⚠️ '{aname}' / Araç {bid+1} için görsel üretilemedi.")

    st.markdown("---")

    def _safe_k(base):
        clean = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(base))
        if len(clean) > 90:
            clean = clean[:45] + "_" + _hs.md5(base.encode()).hexdigest()[:8]
        return clean

    # ── 🏆 EN İYİ TEK SONUÇ KARTI ─────────────────────────────────────────
    _best_name = max(_all_results, key=lambda k: plan_rank(_all_results[k]))
    _best_plan = _all_results[_best_name]
    _best_placed = sum(len(b) for b in _best_plan.bins)
    _best_total  = sum(p.quantity for p in _pieces_3d)
    _best_trucks = len([b for b in _best_plan.bins if b])
    _best_weight = sum(p.weight * p.quantity for p in _pieces_3d)

    _is_advanced = any(w in _best_name for w in ("Bayesian","Island","Multi-Start","Otomatik"))
    _badge = "🔬 İleri Düzey" if _is_advanced else "📦 Standart"

    st.markdown(f"""
<div style="background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);
     border:2px solid #2196F3; border-radius:16px; padding:1.4rem 1.8rem; margin-bottom:1rem">
  <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:0.5rem">
    <div>
      <span style="color:#8b949e;font-size:.8rem">EN İYİ SONUÇ &nbsp;·&nbsp; {_badge}</span><br>
      <span style="color:#e6edf3;font-size:1.5rem;font-weight:700">{_best_name}</span>
    </div>
    <div style="text-align:right">
      <span style="color:#4CAF50;font-size:2.2rem;font-weight:800">%{_best_plan.utilization:.1f}</span>
      <span style="color:#8b949e;font-size:.9rem"> doluluk</span>
    </div>
  </div>
  <div style="display:flex;gap:2rem;margin-top:.8rem;flex-wrap:wrap">
    <div><span style="color:#8b949e;font-size:.75rem">ARAÇ</span><br>
         <span style="color:#e6edf3;font-weight:600">{_best_trucks}</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">YERLEŞTİRİLEN</span><br>
         <span style="color:#e6edf3;font-weight:600">{_best_placed}/{_best_total}</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">AĞIRLIK</span><br>
         <span style="color:#e6edf3;font-weight:600">{_best_weight:,.0f} kg</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">SÜRE</span><br>
         <span style="color:#e6edf3;font-weight:600">{_best_plan.execution_time:.1f}s</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

    if not _is_cmp or len(_all_results) == 1:
        # ── Tek algoritma ────────────────────────────────────────────────────
        _name, _plan = list(_all_results.items())[0]
        show_kpis(_plan, _pieces_3d, _trucks_3d)
        _dolu = [(i,b) for i,b in enumerate(_plan.bins) if b]
        if _dolu:
            if len(_dolu) == 1:
                _bid = _dolu[0][0]
                _show_3d_fast(_name, _bid, _safe_k(f"res_single_b{_bid}"))
            else:
                _tlabels = [f"🚛 Araç {i+1} ({len(b)} palet)" for i,b in _dolu]
                _sel_label = st.radio(
                    "Araç seç:", _tlabels, horizontal=True,
                    key=_safe_k(f"res_{_name}_radio"),
                    label_visibility="collapsed",
                )
                _sel_tidx = _tlabels.index(_sel_label)
                _sel_bid  = _dolu[_sel_tidx][0]
                _show_3d_fast(_name, _sel_bid,
                              _safe_k(f"res_single_r{_sel_tidx}_b{_sel_bid}"))
        else:
            st.info("Görüntülenecek yerleşim yok.")

    else:
        # ── Karşılaştırma modu ───────────────────────────────────────────────
        _rdict = results_dict_from(_all_results, _pieces_3d)
        _comp_rows = sorted(_rdict.items(), key=lambda x: -x[1]["utilization"])
        _best = _comp_rows[0][0]

        # Özet tablo
        st.subheader(f"📊 Tüm Algoritmalar Karşılaştırması ({len(_all_results)} algoritma)")
        _cdf = pd.DataFrame([{
            "Algoritma":   ("🏆 " if k == _best else "") + k,
            "Araç":        v["truck_count"],
            "Yerleşen":    f"{v['placed']}/{v['total_req']}",
            "Doluluk (%)": round(v["utilization"], 1),
            "Ağırlık (kg)":f"{v['total_weight']:,.0f}",
            "Süre (sn)":   round(v["execution_time"], 2),
        } for k,v in _comp_rows])
        st.dataframe(_cdf, hide_index=True, width="stretch",
            column_config={
                "Doluluk (%)": st.column_config.ProgressColumn(
                    "Doluluk (%)", min_value=0, max_value=100, format="%.1f%%"),
                "Süre (sn)": st.column_config.NumberColumn("⏱️ Süre (sn)", format="%.2f"),
            })
        st.markdown("---")

        # Her algoritma için radio seçici — st.tabs tüm içeriği aynı anda render eder
        # → WebGL birden fazla chart aynı anda → Chrome crash. Radio = sadece seçili render.
        _algo_names = [k for k,_ in _comp_rows]
        _tab_labels = [("🏆 " if n == _best else "") + n for n in _algo_names]

        _sel_algo_label = st.radio(
            "Algoritma:", _tab_labels, horizontal=True,
            key="cmp_algo_radio", label_visibility="collapsed",
        )
        _sel_algo_idx = _tab_labels.index(_sel_algo_label)
        _aname = _algo_names[_sel_algo_idx]

        _plan_a = _all_results[_aname]
        _placed = sum(len(b) for b in _plan_a.bins)
        _total  = sum(p.quantity for p in _pieces_3d)
        _c1,_c2,_c3 = st.columns(3)
        _c1.metric("Yerleşen",  f"{_placed}/{_total}")
        _c2.metric("Doluluk",   f"%{_plan_a.utilization:.1f}")
        _c3.metric("Süre",      f"{_plan_a.execution_time:.2f}s")

        _adolu = [(i,b) for i,b in enumerate(_plan_a.bins) if b]
        if not _adolu:
            st.info("Görüntülenecek yerleşim yok.")
        elif len(_adolu) == 1:
            _abid = _adolu[0][0]
            _ak = _safe_k(f"cmp_{_sel_algo_idx}_{_aname[:8]}_b{_abid}")
            _show_3d_fast(_aname, _abid, _ak)
        else:
            # Birden fazla araç: radio seçici
            _truck_labels = [f"🚛 Araç {_vi+1} ({len(_vb)} palet)" for _vi,_vb in _adolu]
            _sel_label = st.radio(
                "Araç seç:", _truck_labels, horizontal=True,
                key=_safe_k(f"cmp_{_sel_algo_idx}_{_aname[:8]}_radio"),
                label_visibility="collapsed",
            )
            _sel_vidx = _truck_labels.index(_sel_label)
            _abid = _adolu[_sel_vidx][0]
            _ak = _safe_k(f"cmp_{_sel_algo_idx}_{_aname[:8]}_v{_sel_vidx}_b{_abid}")
            _show_3d_fast(_aname, _abid, _ak)

        with st.expander(f"📊 {_aname} — Detaylı KPI", expanded=False):
            show_kpis(_plan_a, _pieces_3d, _trucks_3d)

    # ── Rapor İndir (session_state'ten — her rerun'da kalıcı) ────────────────
    if HAS_REPORTS and "last_rdict" in st.session_state:
        _rdict     = st.session_state["last_rdict"]
        _best_nm   = st.session_state["last_best_name"]
        _proj_nm   = st.session_state.get("last_project_name", "rapor")
        _co_nm     = co.get("name", "")
        _trucks_d  = df_trucks.to_dict("records")
        _pieces_d  = st.session_state.get("df_pallets", pd.DataFrame()).to_dict("records")

        st.markdown("---")
        st.subheader("📥 Rapor İndir")

        # ── Detay çıktılar için algoritma seçimi ─────────────────────────
        # Karşılaştırmalı analizde kullanıcı yalnız en iyinin değil,
        # İSTEDİĞİ algoritmanın plan detayını (Excel talimatı + sürücü PDF)
        # indirebilir. Yönetim PDF'i ve Genel Rapor her zaman tümünü içerir.
        _algo_opts = list(_all_results.keys())
        _def_idx   = _algo_opts.index(_best_nm) if _best_nm in _algo_opts else 0
        if len(_algo_opts) > 1:
            _report_algo = st.selectbox(
                "🧾 Detay çıktıların algoritması (Excel & Sürücü Talimatı)",
                _algo_opts, index=_def_idx, key="report_algo_sel",
                help="🏆 = koşunun en iyisi. Yönetim PDF'i ve Genel Rapor "
                     "her zaman TÜM algoritmaları içerir.",
                format_func=lambda a: ("🏆 " if a == _best_nm else "") + a)
        else:
            _report_algo = _algo_opts[_def_idx] if _algo_opts else _best_nm
        _report_plan = _all_results.get(_report_algo)
        _algo_slug   = "".join(c if c.isalnum() else "_"
                               for c in _report_algo)[:20]

        _xl_pinfo = {
            p.id: {
                "weight":     getattr(p, "weight",     0),
                "is_fragile": getattr(p, "is_fragile", False),
                "no_top_load":getattr(p, "no_top_load", False),
                "priority":   getattr(p, "priority",   None),
                "customer":   getattr(p, "customer",   ""),
            }
            for p in _pieces_3d
        }

        _r1, _r2, _r3, _r4 = st.columns(4)
        try:
            _pdf_b = generate_pdf_report(_proj_nm, _co_nm, _trucks_d, _pieces_d,
                                         _rdict, _best_nm, {}, user["full_name"])
            _r1.download_button("📄 Yönetim Raporu (PDF)", _pdf_b,
                file_name=f"{_proj_nm}_yonetim_{time.strftime('%Y%m%d')}.pdf",
                mime="application/pdf", width="stretch", key="dl_pdf_main",
                help="Tüm algoritmaların karşılaştırması + en iyi sonucun özeti")
        except Exception:
            _r1.button("📄 PDF (hata)", disabled=True, width="stretch")
        try:
            _xl_b = generate_excel_report(
                _proj_nm, _co_nm, _trucks_d, _pieces_d,
                _rdict, _report_algo,
                load_rules_df=st.session_state.get("load_rules_live",
                    st.session_state.get("load_rules")),
                best_plan=_report_plan,
                piece_info=_xl_pinfo,
            )
            _r2.download_button(f"📊 Excel — {_report_algo[:14]}", _xl_b,
                file_name=f"{_proj_nm}_{_algo_slug}_{time.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch", key="dl_xl_main",
                help=f"Seçilen algoritmanın ({_report_algo}) plan detayı ve "
                     "yükleme talimatı")
        except Exception:
            _r2.button("📊 Excel (hata)", disabled=True, width="stretch")
        try:
            from reports import generate_loading_sheet_pdf, build_bins_data_from_plan
            _best_plan_r = _report_plan
            _bins_r      = build_bins_data_from_plan(_best_plan_r, _trucks_3d)
            _pinfo_r     = {p.id: {"name": p.id, "weight": p.weight,
                                   "is_fragile": p.is_fragile, "priority": p.priority}
                            for p in _pieces_3d}
            # QR prefix: proje adı + tarih-saat → iki "Yeni Proje" çakışmaz
            _loading_pdf = generate_loading_sheet_pdf(
                _proj_nm, _co_nm, _bins_r, _pinfo_r,
                include_qr=True,
                qr_prefix=f"LP-{_proj_nm[:8]}-{time.strftime('%Y%m%d%H%M')}")
            _r3.download_button("🚛 Sürücü Talimatı (QR)", _loading_pdf,
                file_name=f"{_proj_nm}_{_algo_slug}_surucu_{time.strftime('%Y%m%d')}.pdf",
                mime="application/pdf", width="stretch", key="dl_surucu_main",
                help=f"Seçilen algoritmanın ({_report_algo}) sürücü talimatı")
        except ImportError:
            _r3.button("🚛 Sürücü Talimatı", disabled=True,
                       help="qrcode kütüphanesi gerekli: pip install qrcode[pil]",
                       width="stretch")
        except Exception as _re:
            _r3.button("🚛 Sürücü Talimatı (hata)", disabled=True,
                       help=f"Hata: {_re}", width="stretch")

        # ── GENEL RAPOR: koşulan TÜM algoritmalar tek dosyada ────────────
        if len(_all_results) > 1:
            try:
                from reports import generate_comparison_excel
                _cmp_b = generate_comparison_excel(
                    _proj_nm, _co_nm, _trucks_d, _pieces_d,
                    _rdict, _best_nm, _all_results, piece_info=_xl_pinfo)
                _r4.download_button(
                    f"🧾 Genel Rapor ({len(_all_results)} algoritma)", _cmp_b,
                    file_name=f"{_proj_nm}_genel_{time.strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    width="stretch", key="dl_genel_main",
                    help="Karşılaştırma özeti + her algoritma için ayrı "
                         "yükleme talimatı sayfası")
            except Exception as _ce:
                _r4.button("🧾 Genel Rapor (hata)", disabled=True,
                           help=f"Hata: {_ce}", width="stretch")
        else:
            _r4.caption("🧾 Genel Rapor: karşılaştırmalı modda "
                        "(≥2 algoritma) aktif olur.")


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA: FİLO (karar J) — çekici ve dorse kayıtları
# ─────────────────────────────────────────────────────────────────────────────
elif page == "🚚 Filo":
    import filo_sayfasi
    filo_sayfasi.render()


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA: PROJELERİM
# ─────────────────────────────────────────────────────────────────────────────
elif page == "📁 Projelerim":
    # R4 fix — Operator sadece kendi projelerini görür
    _is_operator_only = user["role"] == "operator"
    if _is_operator_only:
        st.caption("👤 Operatör modu — sadece sizin oluşturduğunuz projeler görüntülenir")
    st.title("📁 Projelerim")
    projects = db_mod.list_projects(co["id"])
    if not projects:
        st.info("Henüz kayıtlı proje yok.")
    else:
        search = st.text_input("🔍 Ara", placeholder="Proje adı...")
        filtered = [p for p in projects
                    if not search or search.lower() in (p.name or "").lower()]
        for p in filtered:
            with st.expander(f"**{p.name}** — %{p.best_utilization or 0:.1f} doluluk — "
                             f"{p.updated_at.strftime('%d.%m.%Y') if p.updated_at else '—'}"):
                c1,c2 = st.columns(2)
                c1.markdown(f"**Açıklama:** {p.description or '—'}")
                c1.markdown(f"**Algoritma:** {p.best_algorithm or '—'}")
                c2.markdown(f"**Araç:** {p.truck_count or '—'}  **Palet:** {p.piece_count or '—'}")
                c2.markdown(f"**Durum:** {p.status}")
                res = p.get_results()
                if res:
                    st.dataframe(pd.DataFrame([
                        {"Algoritma":k,"Doluluk":f'%{v.get("utilization",0):.1f}',
                         "Kamyon":v.get("truck_count","—"),
                         "Süre":f'{v.get("execution_time",0):.2f}s'} for k,v in res.items()
                    ]), hide_index=True, width="stretch")
                cd,ca = st.columns(2)
                # company_id ile kapsamlı — başka şirketin projesi hedeflenemez
                if cd.button("🗑️ Sil",    key=f"del_{p.id}"):
                    db_mod.delete_project(p.id, company_id=co["id"]); st.rerun()
                if ca.button("📦 Arşivle",key=f"arc_{p.id}"):
                    db_mod.archive_project(p.id, company_id=co["id"]); st.rerun()
                if HAS_REPORTS and res:
                    pdf_b = generate_pdf_report(p.name, co.get("name",""),
                                p.get_trucks(), p.get_pieces(), res,
                                p.best_algorithm or "—", p.get_params())
                    st.download_button(f"📄 PDF — {p.name}", pdf_b,
                        f"{p.name}.pdf", "application/pdf", key=f"pdf_{p.id}")


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA: ŞİRKET AYARLARI
# ─────────────────────────────────────────────────────────────────────────────
elif page == "⚙️ Şirket Ayarları":
    st.title("⚙️ Şirket Ayarları")
    if user["role"] not in ("admin","manager"):
        st.error("⛔ Admin veya Yönetici rolü gerekli."); st.stop()

    # R3 fix — Yedekleme tab'ı (sadece admin)
    if has_role("admin"):
        t_info, t_users, t_backup = st.tabs(
            ["🏢 Şirket", "👥 Kullanıcılar", "🗄️ Yedekleme"]
        )
    else:
        t_info, t_users = st.tabs(["🏢 Şirket", "👥 Kullanıcılar"])
        t_backup = None
    with t_info:
        st.metric("Şirket",  co.get("name",""))
        st.metric("Plan",    co.get("plan","standard").capitalize())
    with t_users:
        users_list = db_mod.list_company_users(co["id"])
        st.dataframe(pd.DataFrame([{
            "Ad Soyad":u.full_name,"E-posta":u.email,
            "Rol":u.role,"Aktif":"✅" if u.is_active else "❌",
            "Son Giriş":u.last_login.strftime("%d.%m.%Y") if u.last_login else "—"
        } for u in users_list]), hide_index=True, width="stretch")

        if user["role"] == "admin":
            st.markdown("---"); st.subheader("➕ Kullanıcı Ekle")
            from auth import add_user_to_company
            with st.form("add_user_form"):
                nm=st.text_input("Ad Soyad"); em=st.text_input("E-posta")
                rl=st.selectbox("Rol",["operator","manager","admin"])
                pw=st.text_input("Şifre",type="password")
                if st.form_submit_button("Ekle"):
                    ok,msg=add_user_to_company(co["id"],em,nm,pw,rl)
                    st.success(msg) if ok else st.error(msg)

    # ── R3 FIX: Yedekleme tab'ı (sadece admin görür) ────────────────────
    if t_backup is not None:
        with t_backup:
            st.subheader("🗄️ Veritabanı Yedekleme")
            from backup_manager import (
                run_backup_now, list_backups, get_latest_backup_age_hours,
                DEFAULT_BACKUP_DIR, DEFAULT_RETENTION_DAYS,
            )

            # Son yedek yaşı uyarısı
            age_h = get_latest_backup_age_hours()
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if age_h is None:
                    st.metric("Son Yedek", "Hiç yok", help="Henüz yedek alınmamış")
                elif age_h > 24:
                    st.metric("Son Yedek", f"{age_h:.0f} saat önce ⚠️")
                else:
                    st.metric("Son Yedek", f"{age_h:.1f} saat önce")
            with col_b:
                st.metric("Yedek Dizini", str(DEFAULT_BACKUP_DIR.name))
            with col_c:
                st.metric("Saklama", f"{DEFAULT_RETENTION_DAYS} gün")

            if age_h is not None and age_h > 24:
                st.warning(
                    f"⚠️ Son yedekten bu yana {age_h:.0f} saat geçmiş. "
                    f"Lütfen yeni yedek alın veya günlük cron kurun."
                )

            # Yedek al butonu
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("▶️ Yedek Al", type="primary",
                             width="stretch"):
                    with st.spinner("Yedek alınıyor..."):
                        result = run_backup_now()
                    if result["ok"]:
                        st.success(
                            f"✅ Yedek alındı: {Path(result['path']).name} "
                            f"({result['size_kb']} KB)"
                        )
                        if result["removed_old"]:
                            st.info(
                                f"🗑️ {result['removed_old']} eski yedek silindi "
                                f"(retention: {DEFAULT_RETENTION_DAYS} gün)"
                            )
                        st.rerun()
                    else:
                        st.error(f"❌ Yedekleme başarısız: {result['error']}")
            with col2:
                st.caption(
                    f"Veritabanı tipi: **{os.getenv('DATABASE_URL', 'sqlite:///data/app.db')[:20]}...**  "
                    f"Yedekler `{DEFAULT_BACKUP_DIR}` altına yazılır."
                )

            # Mevcut yedeklerin listesi
            st.markdown("#### 📋 Mevcut Yedekler")
            backups = list_backups()
            if not backups:
                st.info("Henüz yedek alınmamış. Yukarıdaki butonla ilk yedeği alın.")
            else:
                df_backup = pd.DataFrame([{
                    "Dosya Adı": b["name"],
                    "Tarih": b["created"].strftime("%d.%m.%Y %H:%M"),
                    "Boyut (KB)": b["size_kb"],
                } for b in backups[:20]])
                st.dataframe(df_backup, hide_index=True, width="stretch")
                if len(backups) > 20:
                    st.caption(f"…ve {len(backups) - 20} eski yedek daha")

            # Otomatik yedekleme önerisi
            with st.expander("⚙️ Otomatik Günlük Yedekleme Kurulumu"):
                st.markdown("**Linux/macOS (crontab):**")
                st.code(
                    "# Her gün gece 02:00'de yedek al\n"
                    "0 2 * * * cd /app && python backup_manager.py >> "
                    "/var/log/backup.log 2>&1",
                    language="bash"
                )
                st.markdown("**Windows (Görev Zamanlayıcı):**")
                st.code(
                    "schtasks /create /tn LoadPlanBackup "
                    "/tr \"python C:\\app\\backup_manager.py\" "
                    "/sc daily /st 02:00",
                    language="powershell"
                )
                st.caption(
                    "ENV değişkenleri: "
                    "`BACKUP_DIR`, `BACKUP_RETENTION_DAYS` (default 30), "
                    "`PG_DUMP_BIN` (PostgreSQL için)"
                )

# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("🚛 LoadPlan Pro · EP (Crainic 2008) · Layer Building (George 1980) "
           "· Tabu (Lodi 2004) · SA (Mack 2004) · NFP (Bennell & Oliveira 2008)")
