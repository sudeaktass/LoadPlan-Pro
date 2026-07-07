# -*- coding: utf-8 -*-
"""
LoadPlan Pro — Kurumsal 3D Araç Yükleme Optimizasyonu (v8)
===========================================================
Yeni:  Kullanıcı/Şirket oturumu · STEP/STL import · L/T/I profil
       NFP Nested Packing · Proje DB · PDF/Excel rapor
"""
import sys, io
# Windows cp1254 terminali emoji içeren print() çağrılarını çöküşten korur
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
else:
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
                  current_user, current_company)

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

try:
    from reports import generate_pdf_report, generate_excel_report
    HAS_REPORTS = True
except ImportError:
    HAS_REPORTS = False

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

try:
    from bayesian_optimizer_3d import bayesian_optimization_3d
    HAS_BAYESIAN = True
except Exception:
    pass

try:
    from island_genetic_3d import island_model_ga_3d
    HAS_ISLAND_GA = True
except Exception:
    pass

try:
    from multistart_sa_3d import multistart_sa_3d
    HAS_MULTISTART = True
except Exception:
    pass

try:
    from fleet_optimizer_3d import fleet_optimizer_3d
    HAS_FLEET_OPT = True
except Exception:
    pass

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
if not is_logged_in():
    render_login_page()

user = current_user()
co   = current_company()

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
render_user_sidebar()

ALGORITHMS = {
    "greedy_ep":      {"name": "⚡ Greedy",             "time": "< 1 sn",    "advanced": False},
    "ffd_ep":         {"name": "📦 FFD",                 "time": "< 1 sn",    "advanced": False},
    "layer_building": {"name": "🧱 Layer Building",      "time": "< 5 sn",    "advanced": False},
    "tabu_search":    {"name": "🔍 Tabu Search",         "time": "5–120 sn",  "advanced": False},
    "sa_hybrid":      {"name": "🌡️ Sim. Annealing",     "time": "5–120 sn",  "advanced": False},
    "monte_carlo":    {"name": "🎲 Monte Carlo",         "time": "10–60 sn",  "advanced": False},
    "genetic":        {"name": "🧬 Genetic Algorithm",   "time": "30–120 sn", "advanced": False},
    "bayesian":       {"name": "🔬 Bayesian Optim.",     "time": "60–300 sn", "advanced": True},
    "island_ga":      {"name": "🏝️ Island GA",          "time": "60–300 sn", "advanced": True},
    "multistart_sa":  {"name": "🔁 Multi-Start SA",      "time": "30–180 sn", "advanced": True},
}

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
    _pages = ["🏠 Dashboard","🚀 Optimizasyon","📁 Projelerim","⚙️ Şirket Ayarları"]
    if "nav_page" not in st.session_state:
        st.session_state.nav_page = "🚀 Optimizasyon"
    for _p in _pages:
        _active = "active" if st.session_state.nav_page == _p else ""
        if st.button(_p, key=f"nav_{_p}", use_container_width=True):
            st.session_state.nav_page = _p
            st.rerun()
    page = st.session_state.nav_page
    st.markdown("---")

    # Optimizasyon sayfasına özel sidebar araçları
    if page == "🚀 Optimizasyon":

        st.header("🚚 Araç Filosu")
        if "df_trucks" not in st.session_state:
            st.session_state.df_trucks = pd.DataFrame({
                "ID":            ["Küçük-1", "Orta-1", "Büyük-1"],
                "Genişlik (cm)": [170, 180, 240],
                "Uzunluk (cm)":  [260, 420, 600],
                "Yükseklik (cm)":[180, 220, 270],
                "Kapasite (kg)": [6000, 7000, 8000],
                "Adet":          [1, 2, 1],
            })
        df_trucks = st.data_editor(st.session_state.df_trucks, num_rows="dynamic",
            use_container_width=True,
            column_config={
                "ID":             st.column_config.TextColumn("ID", required=True),
                "Genişlik (cm)":  st.column_config.NumberColumn("G(cm)",  min_value=1),
                "Uzunluk (cm)":   st.column_config.NumberColumn("U(cm)",  min_value=1),
                "Yükseklik (cm)": st.column_config.NumberColumn("Y(cm)",  min_value=1),
                "Kapasite (kg)":  st.column_config.NumberColumn("Kap(kg)",min_value=1),
                "Adet":           st.column_config.NumberColumn("Adet",   min_value=1),
            })
        st.session_state.df_trucks = df_trucks
        c1,c2 = st.columns(2)
        c1.metric("Toplam Araç",    int(df_trucks["Adet"].sum()))
        c2.metric("Kapasite", f'{(df_trucks["Kapasite (kg)"]*df_trucks["Adet"]).sum():,.0f} kg')
        st.markdown("---")

        st.header("🎯 Algoritma")
        mode = st.selectbox("Mod", ["🎯 Tek","📊 Karşılaştırmalı"])
        sel_algo  = None
        sel_algos = []

        _std_keys = [k for k,v in ALGORITHMS.items() if not v["advanced"]]
        _adv_keys = [k for k,v in ALGORITHMS.items() if v["advanced"]]

        if mode == "🎯 Tek":
            st.caption("**Standart**")
            keys   = _std_keys
            labels = [ALGORITHMS[k]["name"] for k in keys]
            idx = st.radio("std", range(len(keys)), format_func=lambda i: labels[i],
                           index=1, label_visibility="collapsed")
            sel_algo = keys[idx]
            st.caption(f"⏱️ {ALGORITHMS[sel_algo]['time']}")

            st.markdown("---")
            st.caption("**🔬 İleri Düzey** — Daha uzun sürer, daha iyi sonuç verir")
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

        else:
            _c1, _c2 = st.columns(2)
            if _c1.button("✅ Hepsini Seç", use_container_width=True):
                for _k in ALGORITHMS:
                    st.session_state[f"cmp_{_k}"] = True
            if _c2.button("❌ Hepsini Temizle", use_container_width=True):
                for _k in ALGORITHMS:
                    st.session_state[f"cmp_{_k}"] = False

            st.caption("**Standart**")
            for k in _std_keys:
                v = ALGORITHMS[k]
                _def = k in ("ffd_ep", "layer_building")
                if st.checkbox(v["name"], value=st.session_state.get(f"cmp_{k}", _def), key=f"cmp_{k}"):
                    sel_algos.append(k)

            st.markdown("---")
            st.caption("**🔬 İleri Düzey**")
            for k in _adv_keys:
                v = ALGORITHMS[k]
                _disabled = (k == "bayesian" and not HAS_BAYESIAN) or \
                            (k == "island_ga" and not HAS_ISLAND_GA) or \
                            (k == "multistart_sa" and not HAS_MULTISTART)
                if not _disabled:
                    if st.checkbox(v["name"], value=st.session_state.get(f"cmp_{k}", False), key=f"cmp_{k}"):
                        sel_algos.append(k)
                else:
                    st.caption(f"~~{v['name']}~~ (dosya bulunamadı)")

        st.markdown("---")
        st.header("⚙️ Parametreler")
        active = [sel_algo] if sel_algo else sel_algos
        ts_time=30; ts_tenure=7; sa_time=30; sa_temp=1000.0; sa_cool=0.995
        mc_iter=100; ga_pop=50; ga_gen=100; layer_strat="adaptive"
        nfp_res=2.0; nfp_margin=0.5

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
        with st.expander("🧱 Layer Building", expanded="layer_building" in active):
            layer_strat = st.selectbox("Strateji",["max","adaptive","median"])

        # İleri düzey parametre bölümü
        bay_time=120; bay_trials=40; bay_target="auto"
        isl_islands=4; isl_pop=25; isl_gen=80; isl_mig=15
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
        with st.expander("🔁 Multi-Start SA", expanded="multistart_sa" in active):
            ms_starts = st.slider("Başlangıç Noktası", 2, 10, 5, 1)
            ms_time   = st.slider("Toplam Süre (sn)", 30, 300, 90, 15, key="ms_t")

        st.markdown("---")
        st.header("🤖 Otomatik Optimizasyon")
        if HAS_AUTO_OPT:
            auto_strategy = st.selectbox(
                "Strateji",
                ["⚡ Hızlı (Greedy → SA)", "⚖️ Dengeli (FFD → Genetic)", "🔗 Tam Zincir", "🔬 Parametre Taraması"],
                help="Hızlı: ~1-2 dk | Dengeli: ~3-5 dk | Tam Zincir: ~5-10 dk | Tarama: bütçe kadar"
            )
            auto_time_budget = st.slider("Maks. Süre (sn)", 30, 600, 120, 30)
            auto_target_util = st.slider("Hedef Doluluk %", 50, 100, 85, 5,
                                          help="Bu orana ulaşınca otomatik durur")
            # Önceki çalıştırmadan en iyi config önerisi
            _prev_best = st.session_state.get("auto_best_config")
            if _prev_best:
                st.caption(f"💡 Önceki en iyi: **{_prev_best['algorithm']}** → %{_prev_best['utilization']:.1f}")
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

        st.markdown("---")
        st.header("🚛 Akıllı Araç Seçimi")
        use_fleet_opt = st.checkbox(
            "Otomatik Araç Seçimi",
            value=False,
            help="Açıksa: Her çalıştırmadan önce filodaki en iyi araç kombinasyonunu bulur, "
                 "sonra seçilen algoritmayı o araçlarla çalıştırır.\n\n"
                 "Kapalıysa: Sidebar'daki araç tablosundaki tüm araçları kullanır.",
            key="use_fleet_opt_toggle",
        )
        if use_fleet_opt:
            st.caption(
                "⚠️ Her çalıştırmaya toplam bütçenin **~%35'i** ek süre ekler. "
                "Örn: 120sn bütçede ilk 42sn araç seçimine gider."
            )
            if not HAS_FLEET_OPT:
                st.error("fleet_optimizer_3d.py bulunamadı — toggle devre dışı.")
                use_fleet_opt = False

    else:  # Diğer sayfalar için varsayılanlar
        df_trucks = st.session_state.get("df_trucks", pd.DataFrame())
        mode="🎯 Tek"; sel_algo="ffd_ep"; sel_algos=[]
        active=["ffd_ep"]; ts_time=30; ts_tenure=7; sa_time=30
        sa_temp=1000.0; sa_cool=0.995; mc_iter=100; ga_pop=50; ga_gen=100
        layer_strat="max"; nfp_res=2.0; nfp_margin=0.5
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

            final_cols = ["ID", "Şekil", "Genişlik (cm)", "Uzunluk (cm)", "Yükseklik (cm)",
                          "Ağırlık (kg)", "Adet", "Müşteri",
                          "Altına yerleştirilemez", "Üstüne yerleştirilemez",
                          "Rotasyon", "Min. Aralık (cm)"]
            df_pallets_out = df_l[final_cols].reset_index(drop=True)

    except Exception as e:
        errors.append(f"Yükler sayfası işlenirken hata: {e}")

    return df_trucks_out, df_pallets_out, errors


def compact_forward(plan, pieces, trucks):
    """
    Yerleştirilen parçaları Y=0 (araç önü) yönüne doğru sıkıştırır.

    KRİTİK: Sadece yerden (z=0) başlayan veya altında tam destek olan
    parçalar öne kaydırılır. Havada asılı kalma riski yoktur.

    Kaydırma kuralları:
      1. Zemin parçaları (z=0): serbestçe öne kaydırılabilir
      2. Havadaki parçalar: yeni Y pozisyonunda %75 destek şartı aranır
      3. Destek yoksa → kaydırma iptal, parça yerinde kalır
    """
    from core_3d import check_collision_with_list, is_within_bounds_3d, check_support_3d, Placement3D

    piece_info = {p.id: p for p in pieces}

    for bin_id, placements in enumerate(plan.bins):
        if not placements:
            continue
        truck_id = plan.truck_assignments.get(bin_id)
        truck = next((t for t in trucks if t.id == truck_id), trucks[0] if trucks else None)
        if not truck:
            continue

        # Önden arkaya sırala — alttaki parçalar önce kaydırılmalı
        # (üstteki parçanın desteği korunabilsin)
        placements.sort(key=lambda p: (p.z, p.y))

        for i, pl in enumerate(placements):
            # Zemin parçası değilse ve desteği yoksa — atla
            if pl.z > 0:
                others_now = [p for j, p in enumerate(placements) if j != i]
                if not check_support_3d(pl, others_now, piece_info=piece_info):
                    continue  # Zaten desteği yok, kaydırma

            others = [p for j, p in enumerate(placements) if j != i]
            best_y = pl.y
            step = max(1, pl.length // 8)
            candidate_y = pl.y - step

            while candidate_y >= 0:
                # Sınır kontrolü
                if not is_within_bounds_3d(pl.x, candidate_y, pl.z,
                                           pl.width, pl.length, pl.height,
                                           truck.width, truck.length, truck.height):
                    break

                # Çakışma kontrolü
                if check_collision_with_list(
                        pl.x, candidate_y, pl.z,
                        pl.width, pl.length, pl.height, others):
                    break

                # Yerçekimi / destek kontrolü (havadaki parçalar için)
                if pl.z > 0:
                    # Geçici Placement3D oluştur, desteği kontrol et
                    tmp = Placement3D(
                        x=pl.x, y=candidate_y, z=pl.z,
                        width=pl.width, length=pl.length, height=pl.height,
                        piece_id=pl.piece_id, rotation=pl.rotation,
                        bin_id=pl.bin_id
                    )
                    if not check_support_3d(tmp, others, piece_info=piece_info):
                        break  # Destek yok — buraya kadar git, daha ileriye geçme

                best_y = candidate_y
                candidate_y -= step

            pl.y = best_y

    return plan


def build_pieces(df, sw_shapes, custom_profiles, rules_map=None):
    """
    rules_map: {piece_id: {"stackable": bool, "fragile": bool, "rotation": bool}}
    Yük tablosundaki kullanıcı kurallarını Piece3D alanlarına yansıtır.
    """
    if rules_map is None:
        rules_map = {}

    pieces = []
    for _, row in df.iterrows():
        try:
            pid   = str(row["ID"])
            sh    = str(row.get("Şekil","Dikdörtgen")).strip()
            shape = "cylinder" if sh == "Silindir" else "box"
            # Temel değerler — load_rules override ediyorsa onu kullan
            rule  = rules_map.get(pid, {})
            p = Piece3D(
                id=pid, shape=shape,
                width=int(row["Genişlik (cm)"]),
                length=int(row["Genişlik (cm)"]) if shape=="cylinder" else int(row["Uzunluk (cm)"]),
                height=int(row["Yükseklik (cm)"]),
                quantity=int(row["Adet"]), weight=float(row["Ağırlık (kg)"]),
                allow_rotation_xy=rule.get("rotation", bool(row.get("Rotasyon XY", True))),
                # Kırılgan/İstiflenebilir artık yalnızca yük listesi (rules_map) üzerinden gelir
                is_stackable=rule.get("stackable", True),
                is_fragile=rule.get("fragile", False),
                customer_id=str(row.get("Müşteri","")).strip() or None,
            )
            if sh in ("L-Profil","T-Profil","I-Profil","Boru","Poligon"):
                p._shape_type = sh.lower().replace("-","_").replace(" ","_")
            pieces.append(p)
        except Exception:
            continue
    for sw in sw_shapes:
        info = sw["info"]
        qty = int(st.session_state.get(f"swq_{sw['name']}", sw.get("quantity", 1)))
        wgt = float(st.session_state.get(f"sww_{sw['name']}", sw.get("weight", 0.0)))
        cst = str(st.session_state.get(f"swc_{sw['name']}", sw.get("customer", "")))
        rule = rules_map.get(info.name, {})
        p = Piece3D(id=info.name, shape="box",
                    width=max(1, round(info.bbox_width)),
                    length=max(1, round(info.bbox_length)),
                    height=max(1, round(info.bbox_height)),
                    quantity=qty, weight=wgt, customer_id=cst or None,
                    is_stackable=rule.get("stackable", True),
                    is_fragile=rule.get("fragile", False),
                    allow_rotation_xy=rule.get("rotation", True))
        p._shape_type     = info.shape_type
        p._cross_section  = info.cross_section
        p._fill_ratio     = info.fill_ratio
        p._mesh_vertices  = info.mesh_vertices
        p._mesh_faces     = info.mesh_faces
        pieces.append(p)
    for prof in custom_profiles:
        info = prof["info"]
        rule = rules_map.get(prof["id"], {})
        p = Piece3D(id=prof["id"], shape="box",
                    width=max(1, round(info.bbox_width)),
                    length=max(1, round(info.bbox_length)),
                    height=max(1, round(info.bbox_height)),
                    quantity=prof["quantity"],
                    weight=prof["weight"], customer_id=prof.get("customer") or None,
                    is_stackable=rule.get("stackable", True),
                    is_fragile=rule.get("fragile", False),
                    allow_rotation_xy=rule.get("rotation", True))
        p._shape_type=info.shape_type; p._cross_section=info.cross_section
        p._fill_ratio=info.fill_ratio; pieces.append(p)
    return pieces


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
            p._real_width   = w          # Gerçek fiziksel genişlik (görsel için)
            p._real_length  = l          # Gerçek fiziksel uzunluk (görsel için)
            p._clearance_cm = clearance  # Bırakılacak boşluk (görsel için)

            # Geometri verisi — STL/Profil için
            geom = geom_store.get(pid)
            if geom:
                p._shape_type    = geom.get("shape_type", "box")
                p._cross_section = geom.get("cross_section")
                p._fill_ratio    = geom.get("fill_ratio", 1.0)
                p._mesh_vertices = geom.get("mesh_vertices")
                p._mesh_faces    = geom.get("mesh_faces")
            else:
                p._shape_type    = "box"
                p._cross_section = None
                p._fill_ratio    = 1.0
                p._mesh_vertices = None
                p._mesh_faces    = None

            pieces.append(p)
        except Exception:
            continue
    return pieces


def build_trucks(df):
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


def run_algo(key, pieces, trucks, **kw):
    eng = "EP"
    if key == "greedy_ep":
        from greedy_3d import greedy_3d_optimization
        return greedy_3d_optimization(pieces, trucks, heuristic="CP", engine=eng)
    elif key == "ffd_ep":
        from ffd_3d import ffd_3d_optimization
        return ffd_3d_optimization(pieces, trucks, heuristic="CP", engine=eng)
    elif key == "layer_building":
        from layer_building_3d import layer_building_3d_optimization
        return layer_building_3d_optimization(pieces, trucks, layer_strategy=kw.get("layer_strat","adaptive"))
    elif key == "tabu_search":
        from ffd_3d import ffd_3d_optimization
        from tabu_search_3d import tabu_search_3d_optimization
        init = ffd_3d_optimization(pieces, trucks, heuristic="CP", engine=eng)
        return tabu_search_3d_optimization(pieces, trucks, initial_solution=init,
                   max_time=kw.get("ts_time",30), tabu_tenure=kw.get("ts_tenure",7), engine=eng)
    elif key == "sa_hybrid":
        from ffd_3d import ffd_3d_optimization
        from simulated_annealing_3d import simulated_annealing_3d_optimization
        init = ffd_3d_optimization(pieces, trucks, heuristic="CP", engine=eng)
        # FIX-K2: sa_temp varsayılanı 1000.0 → None (auto-kalibrasyon).
        # UI'den özel değer girilmemişse _calibrate_initial_temp() devreye girer.
        return simulated_annealing_3d_optimization(pieces, trucks, initial_solution=init,
                   max_time=kw.get("sa_time", 30),
                   initial_temp=kw.get("sa_temp", None),
                   cooling_rate=kw.get("sa_cool", 0.995), engine=eng)
    elif key == "monte_carlo":
        from monte_carlo_3d import monte_carlo_3d_optimization
        from ffd_3d import ffd_3d_optimization as _ffd_mc
        _init_mc = _ffd_mc(pieces, trucks, heuristic="CP", engine=eng)
        return monte_carlo_3d_optimization(pieces, trucks,
                                           iterations=kw.get("mc_iter",100),
                                           initial_solution=_init_mc)
    elif key == "genetic":
        from genetic_3d import genetic_3d_optimization
        from ffd_3d import ffd_3d_optimization as _ffd_ga
        _init_ga = _ffd_ga(pieces, trucks, heuristic="CP", engine=eng)
        return genetic_3d_optimization(pieces, trucks,
                                        population_size=kw.get("ga_pop",50),
                                        generations=kw.get("ga_gen",100),
                                        initial_solution=_init_ga)
    elif key == "nfp_nested":
        return run_nfp(pieces, trucks, kw.get("nfp_res",2.0), kw.get("nfp_margin",0.5))
    elif key == "bayesian":
        from bayesian_optimizer_3d import bayesian_optimization_3d
        return bayesian_optimization_3d(
            pieces, trucks,
            target_algorithm=kw.get("bay_target", "auto"),
            n_trials=kw.get("bay_trials", 40),
            time_budget=kw.get("bay_time", 120.0),
            seed_with_ffd=True,
        )
    elif key == "island_ga":
        from island_genetic_3d import island_model_ga_3d
        from ffd_3d import ffd_3d_optimization as _ffd_isl
        _init_isl = _ffd_isl(pieces, trucks, heuristic="CP", engine=eng)
        return island_model_ga_3d(
            pieces, trucks,
            n_islands=kw.get("isl_islands", 4),
            island_population=kw.get("isl_pop", 25),
            generations=kw.get("isl_gen", 80),
            migration_interval=kw.get("isl_mig", 15),
            initial_solution=_init_isl,
        )
    elif key == "multistart_sa":
        from multistart_sa_3d import multistart_sa_3d
        from ffd_3d import ffd_3d_optimization as _ffd_ms
        _init_ms = _ffd_ms(pieces, trucks, heuristic="CP", engine=eng)
        return multistart_sa_3d(
            pieces, trucks,
            n_starts=kw.get("ms_starts", 5),
            time_budget=kw.get("ms_time", 90.0),
            initial_solution=_init_ms,
        )
    return None


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
                st.dataframe(_uf_df, hide_index=True, use_container_width=True,
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
        # Kapasite kontrolü
        if bin_weight > truck.capacity:
            st.error(
                f"🔴 **Araç {truck_id}:** Kapasite aşıldı! "
                f"{bin_weight:,.0f} kg > {truck.capacity:,.0f} kg kapasitesi"
            )
        # 3-eksenli ağırlık merkezi kontrolü
        lat_ok, lon_ok, vert_ok, det = _cwb(bin_placements, piece_info, truck)
        msgs = []
        if not lat_ok:
            msgs.append(
                f"🔴 **Yanal denge (Sol/Sağ):** "
                f"Merkez %{det.get('x_dev',0)*100:.0f} saptı — "
                f"limit ±%{COG_LATERAL_TOL*100:.0f}. "
                "Yükleri araç genişliğine eşit dağıtın."
            )
        if not lon_ok:
            msgs.append(
                f"🟡 **Boylamsal denge (Ön/Arka):** "
                f"İdeal ön-%{COG_FRONT_BIAS*100:.0f}'den %{det.get('y_dev',0)*100:.0f} saptı — "
                f"limit ±%{COG_LONG_TOL*100:.0f}. "
                "Ağır yükleri öne (sürücü tarafına) yakın yerleştirin."
            )
        if not vert_ok:
            msgs.append(
                f"🟡 **Dikey denge (Yükseklik):** "
                f"CoG araç yüksekliğinin %{det.get('z_frac',0)*100:.0f}'inde — "
                f"limit %{COG_VERTICAL_MAX*100:.0f}. "
                "Ağır yükleri zemine yakın koyun, hafif yükleri üste alın."
            )
        if msgs:
            for msg in msgs:
                st.warning(f"⚠️ **Araç {truck_id}:** {msg}")
            # ── Somut düzeltme önerileri ──────────────────────────────────
            with st.expander(f"💡 Araç {truck_id} için önerilen düzeltmeler", expanded=False):
                cog_x  = det.get('cog_x', 0)
                cog_y  = det.get('cog_y', 0)
                cog_z  = det.get('cog_z', 0)
                ideal_x = det.get('ideal_x', truck.width / 2)
                ideal_y = det.get('ideal_y', truck.length * 0.55)

                st.markdown(f"""
**Mevcut ağırlık merkezi:** X={cog_x:.0f} cm · Y={cog_y:.0f} cm · Z={cog_z:.0f} cm

**Hedef bölge:**
- Yanal (X): {ideal_x - truck.width*0.10:.0f} – {ideal_x + truck.width*0.10:.0f} cm *(araç merkezinin ±%10'u)*
- Boylamsal (Y): {ideal_y - truck.length*0.15:.0f} – {ideal_y + truck.length*0.15:.0f} cm *(ön aksın ön-%55'i ±%15)*
- Dikey (Z): 0 – {truck.height*0.60:.0f} cm *(yüksekliğin maks. %60'ı)*

**Nasıl düzeltilir?**
""")
                action_items = []
                if not lat_ok:
                    direction = "sola" if cog_x > ideal_x else "sağa"
                    shift_cm  = abs(cog_x - ideal_x)
                    action_items.append(
                        f"🔴 **Yanal:** Ağır yükleri yaklaşık **{shift_cm:.0f} cm {direction}** kaydırın. "
                        f"Yük tablosunda X'i düşük olan parçaları sağa, yüksek olanları sola alın."
                    )
                if not lon_ok:
                    direction = "öne (küçük Y)" if cog_y > ideal_y else "arkaya (büyük Y)"
                    shift_cm  = abs(cog_y - ideal_y)
                    action_items.append(
                        f"🟡 **Boylamsal:** En ağır yükleri yaklaşık **{shift_cm:.0f} cm {direction}** taşıyın. "
                        f"İdeal: ağır yükler araç öne (%55 noktasına kadar) yakın olmalı."
                    )
                if not vert_ok:
                    action_items.append(
                        f"🟡 **Dikey:** En ağır parçaları zemine (alt kata) alın, "
                        f"hafif/kırılgan parçaları üste yerleştirin. "
                        f"CoG yüksekliği {cog_z:.0f} cm → hedef {truck.height*0.60:.0f} cm altı."
                    )
                for item in action_items:
                    st.markdown(f"- {item}")

                st.info(
                    "💡 **İpucu:** Yük tablosunda ağır parçaların sırasını değiştirin veya "
                    "araç parametrelerini (genişlik/boy) güncelleyerek algoritmayı yeniden çalıştırın. "
                    "CoG penalty algoritmanıza dahil edilmiştir — daha fazla iterasyon verin "
                    "(Tabu Search / Genetic Algorithm)."
                )
        else:
            cog_x = det.get('cog_x', 0)
            cog_y = det.get('cog_y', 0)
            cog_z = det.get('cog_z', 0)
            st.success(
                f"✅ **Araç {truck_id}:** Ağırlık dağılımı optimal — "
                f"CoG ({cog_x:.0f}, {cog_y:.0f}, {cog_z:.0f}) cm "
                f"[Yanal ✅  Boylamsal ✅  Dikey ✅]"
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
        st.plotly_chart(fig, use_container_width=True, key=_k)
    else:
        tab_labels = [f"🚛 Araç {i+1} ({len(b)} palet)" for i,b in dolu]
        tabs = st.tabs(tab_labels)
        for tidx, (tab,(bid,_)) in enumerate(zip(tabs, dolu)):
            with tab:
                fig = visualize_3d_plan(plan, trucks, pieces, bid, show_truck, show_grid)
                _k = _safe_key(f"chart_{chart_key}_t{tidx}_b{bid}")
                st.plotly_chart(fig, use_container_width=True, key=_k)


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


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA: DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
if page == "🏠 Dashboard":
    st.title(f"🏠 Hoş geldiniz, {user['full_name'].split()[0]}!")
    st.caption(f"**{co.get('name','')}** · {co.get('plan','standard').capitalize()} Plan")
    st.markdown("---")

    stats = db_mod.company_stats(co["id"])
    cols = st.columns(4)
    for col, (label, val) in zip(cols, [
        ("Toplam Proje", stats["total_projects"]),
        ("Tamamlanan",   stats["completed_projects"]),
        ("Ort. Doluluk", f'%{stats["avg_utilization"]}'),
        ("Kullanıcılar", stats["user_count"]),
    ]):
        col.markdown(f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
                     f'<div class="kpi-value">{val}</div></div>', unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("📂 Son Projeler")
    projects = db_mod.list_projects(co["id"], limit=10)
    if projects:
        rows = []
        for p in projects:
            badge = {"completed":'<span class="badge-g">✅ Tamam</span>',
                     "draft":    '<span class="badge-o">📝 Taslak</span>',
                     "running":  '<span class="badge-b">⏳ Çalışıyor</span>'
                    }.get(p.status, p.status)
            rows.append({
                "Proje": p.name,
                "Durum": badge,
                "Doluluk": f'%{p.best_utilization:.1f}' if p.best_utilization else '—',
                "Algoritma": p.best_algorithm or '—',
                "Tarih": p.updated_at.strftime("%d.%m.%Y") if p.updated_at else '—',
            })
        df_show = pd.DataFrame(rows)
        st.write(df_show.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.info("Henüz proje yok. **🚀 Optimizasyon** sayfasından başlayın.")


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA: OPTİMİZASYON
# ─────────────────────────────────────────────────────────────────────────────
elif page == "🚀 Optimizasyon":
    st.title("🧊 3D Araç Yükleme Optimizasyonu")
    st.caption("EP · Layer Building · Tabu/SA · NFP Nested Packing · STEP/STL import")

    # Proje adı
    col_pn, col_pd = st.columns([2,3])
    project_name = col_pn.text_input("📋 Proje Adı", value="Yeni Proje")
    project_desc = col_pd.text_input("Açıklama", value="")
    st.markdown("---")

    # ── Yük Tanımı sekmeler ──────────────────────────────────────────────────
    t_std, t_sw, t_prof, t_xl = st.tabs([
        "📦 Standart Yükler",
        "📐 SolidWorks (STEP/STL)",
        "🔷 Profil Tasarımcı",
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
            })

        # ── Çift yönlü senkronizasyon: load_rules → df_pallets ───────────────
        # Kullanıcı Yük Listesi'nde Adet/Müşteri değiştirdiyse buraya yansıt
        if "load_rules" in st.session_state and not st.session_state.load_rules.empty:
            lr = st.session_state.load_rules
            df_p = st.session_state.df_pallets.copy()
            changed = False
            for _, lr_row in lr[lr["Kaynak"] == "Manuel"].iterrows():
                pid = str(lr_row["ID"])
                mask = df_p["ID"] == pid
                if mask.any():
                    if int(df_p.loc[mask, "Adet"].iloc[0]) != int(lr_row.get("Adet", 0)):
                        df_p.loc[mask, "Adet"] = int(lr_row.get("Adet", 0))
                        changed = True
                    if str(df_p.loc[mask, "Müşteri"].iloc[0]) != str(lr_row.get("Müşteri", "")):
                        df_p.loc[mask, "Müşteri"] = str(lr_row.get("Müşteri", ""))
                        changed = True
            if changed:
                st.session_state.df_pallets = df_p

        df_pallets = st.data_editor(st.session_state.df_pallets, num_rows="dynamic",
            use_container_width=True,
            column_config={
                "ID":    st.column_config.TextColumn("ID", required=True),
                "Şekil": st.column_config.SelectboxColumn("Şekil", options=[
                    "Dikdörtgen","Silindir","L-Profil","T-Profil","I-Profil","Boru","Poligon"], required=True),
                "Genişlik (cm)":  st.column_config.NumberColumn("G/Çap", min_value=1),
                "Uzunluk (cm)":   st.column_config.NumberColumn("U(cm)", min_value=1),
                "Yükseklik (cm)": st.column_config.NumberColumn("Y(cm)", min_value=1),
                "Ağırlık (kg)":   st.column_config.NumberColumn("Ağırlık", min_value=0),
                "Adet":           st.column_config.NumberColumn("Adet", min_value=0),
                "Müşteri":        st.column_config.TextColumn("👤 Müşteri"),
            },
            key="df_pallets_editor",
        )

        # ── Standart tablodaki değişiklikleri load_rules'a yansıt ─────────────
        if not df_pallets.equals(st.session_state.df_pallets):
            if "load_rules" in st.session_state and not st.session_state.load_rules.empty:
                lr = st.session_state.load_rules.copy()
                for _, row in df_pallets.iterrows():
                    pid = str(row["ID"])
                    mask = lr["ID"] == pid
                    if mask.any():
                        lr.loc[mask, "G(cm)"]       = float(row.get("Genişlik (cm)", 0))
                        lr.loc[mask, "U(cm)"]       = float(row.get("Uzunluk (cm)", 0))
                        lr.loc[mask, "Y(cm)"]       = float(row.get("Yükseklik (cm)", 0))
                        lr.loc[mask, "Ağırlık(kg)"] = float(row.get("Ağırlık (kg)", 0))
                        lr.loc[mask, "Adet"]        = int(row.get("Adet", 1))
                        lr.loc[mask, "Müşteri"]     = str(row.get("Müşteri", ""))
                st.session_state.load_rules = lr

        st.session_state.df_pallets = df_pallets
        cc1,cc2 = st.columns(2)
        cc1.metric("Toplam Adet",   int(df_pallets["Adet"].sum()))
        cc2.metric("Toplam Ağırlık",f'{(df_pallets["Ağırlık (kg)"]*df_pallets["Adet"]).sum():,.0f} kg')

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
            for uf in up_files:
                if uf.file_id in processed_this_run:
                    continue
                processed_this_run.add(uf.file_id)
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
                                st.image(_png, use_container_width=True,
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
                        type="primary", use_container_width=True
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
                use_container_width=True,
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

    # — Profil Tasarımcı
    with t_prof:
        st.markdown("#### 🔷 L / T / I Profil & Boru Tasarımcı")
        if "custom_profiles" not in st.session_state:
            st.session_state.custom_profiles = []

        ptype = st.selectbox("Profil Tipi",
                             ["L Profil","T Profil","I Profil","Boru (İçi Boş)","Serbest Poligon"])
        with st.form("pf_form"):
            c1,c2 = st.columns(2)
            pid = c1.text_input("Profil ID", value=f"Prof-{len(st.session_state.custom_profiles)+1}")
            qty_p = c2.number_input("Adet",1,9999,1)
            wgt_p = c1.number_input("Ağırlık (kg)",0.0,99999.0,50.0)
            cst_p = c2.text_input("Müşteri","")
            info_obj = None

            if ptype == "L Profil":
                cc = st.columns(5)
                a=cc[0].number_input("a(cm)",1.,999.,10.); b=cc[1].number_input("b(cm)",1.,999.,8.)
                t1=cc[2].number_input("t1(cm)",.1,50.,1.5); t2=cc[3].number_input("t2(cm)",.1,50.,1.5)
                ln=cc[4].number_input("Boy(cm)",1.,2000.,600.)
            elif ptype == "T Profil":
                cc = st.columns(5)
                w_=cc[0].number_input("Flanş G",1.,999.,12.); h=cc[1].number_input("Y",1.,999.,15.)
                tf=cc[2].number_input("tf",.1,50.,1.5); tw=cc[3].number_input("tw",.1,50.,1.)
                ln=cc[4].number_input("Boy",1.,2000.,600.)
            elif ptype == "I Profil":
                cc = st.columns(5)
                w_=cc[0].number_input("Flanş G",1.,999.,15.); h=cc[1].number_input("Y",1.,999.,30.)
                tf=cc[2].number_input("tf",.1,50.,2.); tw=cc[3].number_input("tw",.1,50.,1.)
                ln=cc[4].number_input("Boy",1.,2000.,600.)
            elif ptype == "Boru (İçi Boş)":
                cc = st.columns(3)
                od=cc[0].number_input("Dış Çap",1.,999.,20.); id_=cc[1].number_input("İç Çap",.1,998.,16.)
                h_=cc[2].number_input("Yükseklik",1.,2000.,200.)
            elif ptype == "Serbest Poligon":
                coord_str = st.text_area("x,y koordinatları (her satır bir nokta)",
                                          value="0,0\n20,0\n20,5\n5,5\n5,20\n0,20", height=120)
                ln = st.number_input("Boy(cm)",1.,2000.,600.)

            if st.form_submit_button("➕ Profil Ekle", type="primary") and HAS_SHAPE:
                try:
                    if ptype=="L Profil":       info_obj=l_profile(a,b,t1,t2,ln)
                    elif ptype=="T Profil":     info_obj=t_profile(w_,h,tf,tw,ln)
                    elif ptype=="I Profil":     info_obj=i_profile(w_,h,tf,tw,ln)
                    elif ptype=="Boru (İçi Boş)": info_obj=hollow_cylinder(od,id_,h_)
                    elif ptype=="Serbest Poligon":
                        coords_raw=[(float(x),float(y)) for x,y in
                                    (l.strip().split(",") for l in coord_str.strip().split("\n"))]
                        info_obj=polygon_profile(coords_raw,ln,pid)
                    if info_obj:
                        info_obj.name=pid
                        st.session_state.custom_profiles.append(
                            {"id":pid,"info":info_obj,"quantity":qty_p,"weight":wgt_p,"customer":cst_p})
                        st.success(f"✅ {pid} eklendi — {shape_summary(info_obj)}")
                except Exception as e:
                    st.error(f"Hata: {e}")

        if st.session_state.custom_profiles:
            st.markdown(f"**{len(st.session_state.custom_profiles)} profil tanımlı**")
            for p in st.session_state.custom_profiles:
                i=p["info"]
                st.markdown(f"- **{p['id']}** [{i.display_name}] — "
                            f"{i.bbox_width:.0f}×{i.bbox_length:.0f}×{i.bbox_height:.0f} cm · {p['quantity']} adet")
            if st.button("🗑️ Profilleri Temizle"):
                st.session_state.custom_profiles=[]; st.rerun()

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
                    use_container_width=True,
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
                st.dataframe(df_t_xl, hide_index=True, use_container_width=True)
            elif not xl_errors:
                st.warning("Araçlar sayfası bulunamadı veya veri yok.")

            # Yükler önizleme
            if df_p_xl is not None and not df_p_xl.empty:
                st.markdown(f"**📦 Yükler** — {len(df_p_xl)} satır okundu")
                st.dataframe(df_p_xl, hide_index=True, use_container_width=True,
                    column_config={
                        "Altına yerleştirilemez": st.column_config.CheckboxColumn("🚫 Altına"),
                        "Üstüne yerleştirilemez": st.column_config.CheckboxColumn("⛔ Üstüne"),
                        "Rotasyon":               st.column_config.CheckboxColumn("🔄 Rot."),
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
                if st.button("✅ İçe Aktarımı Uygula", type="primary", use_container_width=True):
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
                        st.success(f"✅ {len(df_t_xl)} araç yüklendi.")

                    # Yükler
                    if df_p_xl is not None and not df_p_xl.empty:
                        # df_pallets güncelle
                        _pal_cols = ["ID", "Şekil", "Genişlik (cm)", "Uzunluk (cm)",
                                     "Yükseklik (cm)", "Ağırlık (kg)", "Adet", "Müşteri"]
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
            "Yükler sayfası (isteğe bağlı)": "Şekil · Müşteri · Altına yerleştirilemez · Üstüne yerleştirilemez · Rotasyon · Min. Aralık (cm)",
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
                "Kaynak": "STL/STEP", "ID": pid, "Şekil": info.display_name,
                "G(cm)": round(info.bbox_width, 1), "U(cm)": round(info.bbox_length, 1),
                "Y(cm)": round(info.bbox_height, 1), "Adet": qty,
                "Ağırlık(kg)": round(wgt, 2),
                "Müşteri": str(st.session_state.get(f"swc_{sw['name']}", "")),
                "Altına yerleştirilemez": False, "Üstüne yerleştirilemez": False, "Rotasyon": True,
                "Min. Aralık (cm)": 0,
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
            }
            new_rows.append({
                "Kaynak": "Profil", "ID": pid, "Şekil": info.display_name,
                "G(cm)": round(info.bbox_width, 1), "U(cm)": round(info.bbox_length, 1),
                "Y(cm)": round(info.bbox_height, 1),
                "Adet": int(pf.get("quantity", 1)), "Ağırlık(kg)": float(pf.get("weight", 0)),
                "Müşteri": str(pf.get("customer", "")),
                "Altına yerleştirilemez": False, "Üstüne yerleştirilemez": False, "Rotasyon": True,
                "Min. Aralık (cm)": 0,
            })

        if new_rows:
            new_df = pd.DataFrame(new_rows)
            if "load_rules" not in st.session_state or st.session_state.load_rules.empty:
                st.session_state.load_rules = new_df
            else:
                st.session_state.load_rules = pd.concat(
                    [st.session_state.load_rules, new_df], ignore_index=True)

    _sync_new_items()

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

    if "load_rules" not in st.session_state or st.session_state.load_rules.empty:
        st.info("Henüz yük tanımlanmamış. Yukarıdaki sekmelerden yük ekleyin.")
    else:
        prev_ids = set(st.session_state.load_rules["ID"].tolist())

        edited = st.data_editor(
            st.session_state.load_rules,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            disabled=["Kaynak", "ID", "Şekil", "G(cm)", "U(cm)", "Y(cm)", "Ağırlık(kg)"],
            column_config={
                "Kaynak":    st.column_config.TextColumn("📂 Kaynak", width="small"),
                "ID":        st.column_config.TextColumn("🏷️ ID"),
                "Şekil":     st.column_config.TextColumn("📐 Şekil"),
                "G(cm)":     st.column_config.NumberColumn("G(cm)", format="%.1f"),
                "U(cm)":     st.column_config.NumberColumn("U(cm)", format="%.1f"),
                "Y(cm)":     st.column_config.NumberColumn("Y(cm)", format="%.1f"),
                "Adet":      st.column_config.NumberColumn("Adet", width="small", min_value=0),
                "Ağırlık(kg)": st.column_config.NumberColumn("⚖️ Ağırlık(kg)", format="%.1f"),
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
                    help="Bu parçanın çevresinde bırakılacak minimum boşluk (cm). "
                         "Titreşimli, sıcak veya korozif yükler için kullanın."),
            },
            key="load_rules_editor",
        )

        # Silinen ID'leri kalıcı olarak kaydet + kaynaklardan temizle
        curr_ids = set(edited["ID"].tolist()) if not edited.empty else set()
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

        st.session_state.load_rules = edited

        # ── load_rules → staging + sw_shapes tam senkronizasyon ─────────────
        if not edited.empty:
            for _, _lr_row in edited.iterrows():
                _pid = str(_lr_row.get("ID",""))
                if not _pid: continue
                _qty = int(_lr_row.get("Adet", 1))
                _wgt = float(_lr_row.get("Ağırlık(kg)", 0))
                _cst = str(_lr_row.get("Müşteri", ""))
                # staging güncelle
                for _s in st.session_state.get("sw_staging", []):
                    if _s["name"] == _pid:
                        _s["quantity"] = _qty; _s["weight"] = _wgt; _s["customer"] = _cst
                # sw_shapes güncelle
                for _sw in st.session_state.get("sw_shapes", []):
                    if _sw["name"] == _pid:
                        _sw["quantity"] = _qty; _sw["weight"] = _wgt; _sw["customer"] = _cst
                        st.session_state[f"swq_{_pid}"] = _qty
                        st.session_state[f"sww_{_pid}"] = _wgt
                        st.session_state[f"swc_{_pid}"] = _cst

        if not edited.empty:
            total_pieces = int(edited["Adet"].sum())
            total_kg     = float((edited["Ağırlık(kg)"] * edited["Adet"]).sum())
            n_no_stack   = int(edited["Altına yerleştirilemez"].sum())
            n_fragile    = int(edited["Üstüne yerleştirilemez"].sum())
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Toplam Parça", total_pieces)
            m2.metric("Toplam Ağırlık", f"{total_kg:,.0f} kg")
            m3.metric("Altına yük konmaz", n_no_stack)
            m4.metric("Üstüne yük konmaz", n_fragile)

        if st.button("🔄 Yük Listesini Sıfırla",
                     help="Tüm yükler ve silme geçmişi temizlenir, sıfırdan başlanır"):
            for k in ["load_rules","deleted_ids","geom_store","df_pallets",
                      "sw_shapes","sw_staging","custom_profiles"]:
                st.session_state.pop(k, None)
            st.rerun()


    st.markdown("---")

    # ── BAŞLAT BUTONU ─────────────────────────────────────────────────────────
    _,btn_col,_ = st.columns([1,2,1])
    with btn_col:
        btn_label = (f"🚀 {ALGORITHMS.get(sel_algo,{}).get('name',sel_algo)} Çalıştır"
                     if mode=="🎯 Tek" else f"📊 {len(sel_algos)} Algoritma Karşılaştır")
        run_btn = st.button(btn_label, type="primary", use_container_width=True)

        st.markdown("---")
        st.caption("**🔬 İleri Düzey — otomatik her şeyi optimize eder:**")

        tam_opt_btn = st.button(
            "⚡ Tam Optimizasyon",
            use_container_width=True,
            type="primary",
            disabled=not (HAS_AUTO_OPT and HAS_FLEET_OPT),
            help="Araç seçimi + yerleşim parametrelerini birlikte optimize eder. "
                 "Aşama 1: En iyi araç kombinasyonunu bul. "
                 "Aşama 2: O kombinasyon için SA/GA ile en iyi yerleşimi bul."
                 if (HAS_AUTO_OPT and HAS_FLEET_OPT)
                 else "fleet_optimizer_3d.py veya iterative_optimizer_3d.py eksik",
        )

        _col_a, _col_b = st.columns(2)
        auto_btn = _col_a.button(
            "🤖 Sadece Parametreler",
            use_container_width=True,
            disabled=not HAS_AUTO_OPT,
            help="Mevcut araç filosunu kullanarak en iyi parametre kombinasyonunu bulur.",
        )
        fleet_btn = _col_b.button(
            "🚛 Sadece Araç Seçimi",
            use_container_width=True,
            disabled=not HAS_FLEET_OPT,
            help="Hangi araçların kullanılacağını optimize eder, FFD ile hızlı yerleşim yapar.",
        )

    # ═══════════════════════════════════════════════════════════════════════
    # TAM OPTİMİZASYON — Araç Seçimi + Yerleşim Birlikte
    # ═══════════════════════════════════════════════════════════════════════
    if tam_opt_btn and HAS_AUTO_OPT and HAS_FLEET_OPT:
        pieces_3d = build_pieces_from_load_rules(
            st.session_state.get("load_rules", pd.DataFrame()),
            st.session_state.get("geom_store", {}),
        )
        trucks_3d = build_trucks(df_trucks)
        if not pieces_3d: st.error("❌ Yük tanımlanmamış!"); st.stop()
        if not trucks_3d: st.error("❌ Araç tanımlanmamış!"); st.stop()

        st.markdown("---")
        st.subheader("⚡ Tam Optimizasyon")

        _phase1_time = max(30, int(auto_time_budget * 0.35))
        _phase2_time = auto_time_budget - _phase1_time
        st.caption(
            f"📦 {sum(p.quantity for p in pieces_3d)} parça  |  "
            f"🚛 {len(set(t.id for t in trucks_3d))} araç tipi  |  "
            f"Aşama 1 (araç seçimi): {_phase1_time}s  |  "
            f"Aşama 2 (yerleşim rafine): {_phase2_time}s"
        )

        _p1_bar  = st.progress(0)
        _p1_stat = st.empty()
        _p2_bar  = st.progress(0)
        _p2_stat = st.empty()
        _result_box = st.empty()
        _chart_box  = st.empty()

        # ── AŞAMA 1: En iyi araç kombinasyonlarını bul ──────────────────────
        _p1_stat.info("🔍 **Aşama 1/2:** Araç kombinasyonları taranıyor…")

        def _p1_cb(trial, total, score):
            _p1_bar.progress(min(trial / max(total, 1), 1.0))
            _p1_stat.info(f"🔍 **Aşama 1/2:** Deneme {trial}/{total} — En iyi skor: {score:.4f}")

        best_plan_p1, best_cfg_p1, all_results_p1 = fleet_optimizer_3d(
            pieces_3d, trucks_3d,
            time_budget=_phase1_time,
            max_configs=200,
            packing_algo="auto",
            use_bayesian=True,
            progress_callback=_p1_cb,
        )

        _p1_bar.progress(1.0)

        # En iyi 3 config'i al (bunlar Aşama 2'de rafine edilecek)
        _top_configs = []
        _seen_labels = set()
        for _r in sorted(all_results_p1, key=lambda r: -r.score):
            _lbl = _r.config.label()
            if _lbl not in _seen_labels:
                _top_configs.append(_r.config)
                _seen_labels.add(_lbl)
            if len(_top_configs) >= 3:
                break

        if not _top_configs and best_cfg_p1:
            _top_configs = [best_cfg_p1]

        _p1_stat.success(
            f"✅ **Aşama 1 tamamlandı** — En iyi araç kombinasyonu: "
            f"**{best_cfg_p1.label() if best_cfg_p1 else '?'}**  |  "
            f"Top {len(_top_configs)} konfigürasyon Aşama 2'ye taşınıyor"
        )

        # Tablo göster
        if all_results_p1:
            _p1_tbl = [{
                "Araç Kombinasyonu": r.config.label(),
                "Doluluk %": round(r.utilization, 1),
                "Araç Sayısı": r.num_trucks,
                "Yerleşen": f"{r.placed}/{r.total}",
            } for r in sorted(all_results_p1, key=lambda r: -r.score)[:8]]
            with st.expander("📋 Aşama 1 — Tüm kombinasyon sonuçları", expanded=False):
                st.dataframe(pd.DataFrame(_p1_tbl), hide_index=True, use_container_width=True,
                    column_config={"Doluluk %": st.column_config.ProgressColumn(
                        "Doluluk %", min_value=0, max_value=100, format="%.1f%%")})

        # ── AŞAMA 2: Top config'ler için SA/GA ile rafine et ────────────────
        _p2_stat.info(f"🧬 **Aşama 2/2:** {len(_top_configs)} kombinasyon için yerleşim rafine ediliyor…")

        from iterative_optimizer_3d import _run_algorithm
        _time_per_config = _phase2_time / max(len(_top_configs), 1)
        _best_final_plan  = best_plan_p1
        _best_final_util  = best_plan_p1.utilization if best_plan_p1 else 0
        _best_final_cfg   = best_cfg_p1
        _p2_results = []

        _p2_start = time.time()   # FIX-G: Aşama 2 başlangıç zamanı
        for _ci, _cfg in enumerate(_top_configs):
            _cfg_trucks = sorted(_cfg.trucks, key=lambda t: t.get_volume(), reverse=True)
            _p2_bar.progress(_ci / len(_top_configs))
            _p2_stat.info(
                f"🧬 **Aşama 2/2:** [{_ci+1}/{len(_top_configs)}] "
                f"**{_cfg.label()}** rafine ediliyor…"
            )

            # FFD seed al
            try:
                _seed, _ = _run_algorithm("FFD", {}, pieces_3d, _cfg_trucks)
            except Exception:
                _seed = None

            # SA ile rafine et
            # FIX-G: initial_temp=1200.0 kaldırıldı → auto-kalibrasyon.
            # max_time: kalan toplam bütçeyi aşmamak için _phase2_time
            # ile sınırlandırılıyor (_time_per_config * 0.6 yeterliydi
            # ama toplam bütçe taşabiliyordu).
            _sa_time = min(_time_per_config * 0.6, _phase2_time - (time.time() - _p2_start) if '_p2_start' in dir() else _time_per_config * 0.6)
            try:
                _refined, _t = _run_algorithm(
                    "SimulatedAnnealing",
                    {"max_time": max(_sa_time, 5.0), "cooling_rate": 0.997},
                    pieces_3d, _cfg_trucks, _seed
                )
                _p2_results.append((_refined.utilization, _refined, _cfg))
                _p2_stat.info(
                    f"🧬 SA [{_cfg.label()}] → %{_refined.utilization:.1f}  "
                    f"(+{_t:.0f}s)"
                )
                if _refined.utilization > _best_final_util:
                    _best_final_util = _refined.utilization
                    _best_final_plan = _refined
                    _best_final_cfg  = _cfg
            except Exception as _e:
                _p2_stat.warning(f"⚠️ SA [{_cfg.label()}]: {_e}")

            # Şu anki en iyi grafiği güncelle
            if _best_final_plan:
                try:
                    _bid0 = next(i for i, b in enumerate(_best_final_plan.bins) if b)
                    _fig0 = visualize_3d_plan(
                        _best_final_plan, _cfg_trucks, pieces_3d, _bid0, True, True)
                    _chart_box.plotly_chart(_fig0, use_container_width=True,
                                            key=f"tam_live_{_ci}")
                except Exception:
                    pass

        _p2_bar.progress(1.0)
        _p2_stat.success(
            f"✅ **Aşama 2 tamamlandı** — "
            f"En iyi: **{_best_final_cfg.label() if _best_final_cfg else '?'}** "
            f"→ %{_best_final_util:.2f} doluluk"
        )

        if _best_final_plan and _best_final_cfg:
            _placed_t = sum(len(b) for b in _best_final_plan.bins)
            _total_t  = sum(p.quantity for p in pieces_3d)
            _trucks_t = sum(1 for b in _best_final_plan.bins if b)

            st.markdown(f"""
<div style="background:linear-gradient(135deg,#0f2027,#1a3a1a,#2c5364);
     border:2px solid #4CAF50;border-radius:14px;padding:1.2rem 1.6rem;margin:.5rem 0">
  <div style="color:#8b949e;font-size:.8rem">⚡ TAM OPTİMİZASYON SONUCU</div>
  <div style="color:#e6edf3;font-size:1.4rem;font-weight:700;margin:.3rem 0">
    {_best_final_cfg.label()}
  </div>
  <div style="display:flex;gap:2rem;flex-wrap:wrap;margin-top:.5rem">
    <div><span style="color:#8b949e;font-size:.75rem">DOLULUK</span><br>
         <span style="color:#4CAF50;font-size:1.5rem;font-weight:800">%{_best_final_plan.utilization:.1f}</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">ARAÇ</span><br>
         <span style="color:#e6edf3;font-weight:600">{_trucks_t} adet</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">YERLEŞTİRİLEN</span><br>
         <span style="color:#e6edf3;font-weight:600">{_placed_t}/{_total_t}</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">TOPLAM SÜRE</span><br>
         <span style="color:#e6edf3;font-weight:600">{auto_time_budget}s</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

            if compact_fwd:
                try:
                    _best_final_plan = compact_forward(_best_final_plan, pieces_3d, _best_final_cfg.trucks if _best_final_cfg else trucks_3d)
                except Exception:
                    pass

            _vis_trucks_t = _best_final_cfg.trucks if _best_final_cfg else trucks_3d

            st.session_state["last_results"]   = {"⚡ Tam Optimizasyon": _best_final_plan}
            st.session_state["last_pieces_3d"] = pieces_3d
            st.session_state["last_trucks_3d"] = _vis_trucks_t
            st.session_state["last_mode"]      = "🎯 Tek"
            _fc_t = {}
            for _bid_t, _bpl_t in enumerate(_best_final_plan.bins):
                if _bpl_t:
                    try:
                        _fc_t[("⚡ Tam Optimizasyon", _bid_t)] = visualize_3d_plan(
                            _best_final_plan, _vis_trucks_t, pieces_3d,
                            _bid_t, show_truck, show_grid)
                    except Exception:
                        pass
            st.session_state["last_fig_cache"] = _fc_t
            st.rerun()
        else:
            st.error("❌ Tam optimizasyon başarısız oldu.")

    # ═══════════════════════════════════════════════════════════════════════
    # AKILLI ARAÇ SEÇİMİ — FİLO OPTİMİZASYONU
    # ═══════════════════════════════════════════════════════════════════════
    if fleet_btn and HAS_FLEET_OPT:
        pieces_3d = build_pieces_from_load_rules(
            st.session_state.get("load_rules", pd.DataFrame()),
            st.session_state.get("geom_store", {}),
        )
        trucks_3d = build_trucks(df_trucks)
        if not pieces_3d: st.error("❌ Yük tanımlanmamış!"); st.stop()
        if not trucks_3d: st.error("❌ Araç tanımlanmamış!"); st.stop()

        st.markdown("---")
        st.subheader("🚛 Akıllı Araç Seçimi")
        st.caption(
            f"📦 {sum(p.quantity for p in pieces_3d)} parça  |  "
            f"🚛 {len(trucks_3d)} araç tipi  |  "
            f"Bütçe: {auto_time_budget}s"
        )

        # Kaç konfigürasyon var?
        import itertools as _itr
        _unique_t = {t.id: t for t in trucks_3d}
        _total_cfgs = 1
        for _t in _unique_t.values():
            _total_cfgs *= (_t.available + 1)
        _total_cfgs -= 1  # boş konfigürasyon çıkar
        st.info(
            f"🔢 Toplam **{_total_cfgs}** olası araç kombinasyonu  |  "
            f"{'Tümü denenecek' if _total_cfgs <= 30 else 'Bayesian ile akıllı arama yapılacak'}"
        )

        _fleet_prog  = st.progress(0)
        _fleet_stat  = st.empty()
        _fleet_table = st.empty()
        _fleet_chart = st.empty()

        _fleet_rows  = []
        _fleet_best_score = [-1.0]

        def _fleet_cb(trial_no, total, best_score):
            _fleet_prog.progress(min(trial_no / max(total, 1), 0.99))
            _fleet_stat.info(
                f"⏳ Deneme {trial_no}/{total}  |  "
                f"En iyi skor: {best_score:.4f}"
            )

        with st.spinner("Araç kombinasyonları değerlendiriliyor…"):
            best_plan_f, best_cfg_f, all_results_f = fleet_optimizer_3d(
                pieces_3d, trucks_3d,
                time_budget=auto_time_budget,
                max_configs=min(_total_cfgs, 200),
                packing_algo="auto",
                use_bayesian=(_total_cfgs > 30),
                progress_callback=_fleet_cb,
            )

        _fleet_prog.progress(1.0)
        _fleet_stat.empty()

        if best_plan_f and best_cfg_f:
            _placed_f = sum(len(b) for b in best_plan_f.bins)
            _total_f  = sum(p.quantity for p in pieces_3d)
            _trucks_f = sum(1 for b in best_plan_f.bins if b)

            # Sonuç kartı
            st.markdown(f"""
<div style="background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);
     border:2px solid #4CAF50;border-radius:14px;padding:1.2rem 1.6rem;margin:.5rem 0">
  <div style="color:#8b949e;font-size:.8rem">🏆 EN İYİ ARAÇ KOMBİNASYONU</div>
  <div style="color:#e6edf3;font-size:1.4rem;font-weight:700;margin:.3rem 0">
    {best_cfg_f.label()}
  </div>
  <div style="display:flex;gap:2rem;flex-wrap:wrap;margin-top:.5rem">
    <div><span style="color:#8b949e;font-size:.75rem">DOLULUK</span><br>
         <span style="color:#4CAF50;font-size:1.4rem;font-weight:700">%{best_plan_f.utilization:.1f}</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">KULLANILAN ARAÇ</span><br>
         <span style="color:#e6edf3;font-weight:600">{_trucks_f} adet</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">YERLEŞTİRİLEN</span><br>
         <span style="color:#e6edf3;font-weight:600">{_placed_f}/{_total_f}</span></div>
    <div><span style="color:#8b949e;font-size:.75rem">TOPLAM HACİM</span><br>
         <span style="color:#e6edf3;font-weight:600">{best_cfg_f.total_volume():,} cm³</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

            # Tüm parçalar sığmadıysa açık uyarı
            if _placed_f < _total_f:
                st.warning(
                    f"⚠️ **{_total_f - _placed_f} parça yerleştirilemedi.** "
                    f"Mevcut araç filosunun toplam hacmi veya ağırlık kapasitesi yetmiyor. "
                    f"**Çözüm:** Sidebar'dan araç filosuna daha büyük araç ekleyin "
                    f"veya mevcut araçların 'Adet' değerini artırın, "
                    f"ardından Tam Optimizasyonu tekrar çalıştırın."
                )

            # Top 10 sonuç tablosu
            if all_results_f:
                st.markdown("**📋 Tüm Kombinasyon Sonuçları (en iyi 10):**")
                _tbl_rows = []
                for _r in all_results_f[:10]:
                    _tbl_rows.append({
                        "Araç Kombinasyonu": _r.config.label(),
                        "Doluluk %":         round(_r.utilization, 1),
                        "Araç Sayısı":       _r.num_trucks,
                        "Yerleşen":          f"{_r.placed}/{_r.total}",
                        "Skor":              round(_r.score, 4),
                    })
                st.dataframe(
                    pd.DataFrame(_tbl_rows), hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Doluluk %": st.column_config.ProgressColumn(
                            "Doluluk %", min_value=0, max_value=100, format="%.1f%%"),
                    }
                )

            # Compact forward uygula
            if compact_fwd:
                try:
                    best_plan_f = compact_forward(best_plan_f, pieces_3d, best_cfg_f.trucks)
                except Exception:
                    pass

            # Görsel için seçilen araçları kullan (tam filo değil!)
            _vis_trucks_f = best_cfg_f.trucks if best_cfg_f else trucks_3d

            # Session state'e kaydet
            st.session_state["last_results"]   = {"🚛 Akıllı Araç Seçimi": best_plan_f}
            st.session_state["last_pieces_3d"] = pieces_3d
            st.session_state["last_trucks_3d"] = _vis_trucks_f
            st.session_state["last_mode"]      = "🎯 Tek"
            _fc = {}
            for _bid_f, _bpl_f in enumerate(best_plan_f.bins):
                if _bpl_f:
                    try:
                        _fc[("🚛 Akıllı Araç Seçimi", _bid_f)] = visualize_3d_plan(
                            best_plan_f, _vis_trucks_f, pieces_3d, _bid_f, show_truck, show_grid)
                    except Exception:
                        pass
            st.session_state["last_fig_cache"] = _fc
            st.rerun()
        else:
            st.error("❌ Hiçbir araç kombinasyonu için geçerli sonuç üretilemedi.")

    # ═══════════════════════════════════════════════════════════════════════
    # OTOMATİK OPTİMİZASYON
    # ═══════════════════════════════════════════════════════════════════════
    if auto_btn and HAS_AUTO_OPT:
        pieces_3d = build_pieces_from_load_rules(
            st.session_state.get("load_rules", pd.DataFrame()),
            st.session_state.get("geom_store", {}),
        )
        trucks_3d = build_trucks(df_trucks)
        if not pieces_3d: st.error("❌ Yük tanımlanmamış!"); st.stop()
        if not trucks_3d: st.error("❌ Araç tanımlanmamış!"); st.stop()

        # ── Akıllı Araç Seçimi (toggle açıksa) ────────────────────────────────
        if use_fleet_opt and HAS_FLEET_OPT:
            _fs2_stat = st.info("🚛 Araç kombinasyonları taranıyor…")
            _fs2_bar  = st.progress(0)
            def _fs2_cb(trial, total, score):
                _fs2_bar.progress(min(trial / max(total, 1), 1.0))
            try:
                _, _best_cfg2, _ = fleet_optimizer_3d(
                    pieces_3d, trucks_3d,
                    time_budget=max(15, int(auto_time_budget * 0.35)),
                    max_configs=200, packing_algo="auto", use_bayesian=True,
                    progress_callback=_fs2_cb,
                )
                if _best_cfg2 and _best_cfg2.trucks:
                    trucks_3d = sorted(_best_cfg2.trucks, key=lambda t: t.get_volume(), reverse=True)
                    _fs2_stat.success(f"✅ En iyi araç: **{_best_cfg2.label()}**")
                else:
                    _fs2_stat.warning("⚠️ Araç seçimi sonuç vermedi, orijinal filo kullanılıyor.")
            except Exception as _fe2:
                _fs2_stat.warning(f"⚠️ Araç seçimi hatası: {_fe2}")
            _fs2_bar.progress(1.0)

        n_pieces = sum(p.quantity for p in pieces_3d)

        st.markdown("---")
        st.subheader("🤖 Otomatik Optimizasyon")

        # Strateji açıklaması
        _strat_info = {
            "⚡ Hızlı (Greedy → SA)":      ("Greedy ile hızlı başlangıç, SA ile rafine eder.", "greedy_sa"),
            "⚖️ Dengeli (FFD → Genetic)":  ("FFD seed + Genetic evrim — orta büyüklük için ideal.", "ffd_genetic"),
            "🔗 Tam Zincir":               ("FFD → Greedy → GA → SA → Tabu — tüm algoritmalar sırayla.", "full_chain"),
            "🔬 Parametre Taraması":       ("Tüm parametre kombinasyonlarını tarar, en iyiyi seçer.", "search"),
        }
        _strat_desc, _strat_key = _strat_info.get(auto_strategy, ("", "greedy_sa"))
        st.caption(f"📌 **{auto_strategy}** — {_strat_desc}  |  Hedef: **%{auto_target_util}**  |  Bütçe: **{auto_time_budget}s**")

        # Akıllı strateji tavsiyesi
        if n_pieces > 50 and _strat_key == "search":
            st.info(f"💡 {n_pieces} parça için Parametre Taraması uzun sürebilir. "
                     "Tam Zincir veya Dengeli strateji daha hızlı sonuç verir.")
        elif n_pieces <= 10 and _strat_key == "full_chain":
            st.info("💡 Az parça için Hızlı strateji genellikle yeterlidir.")

        # UI bileşenleri
        col_prog, col_stop = st.columns([5, 1])
        prog_bar   = col_prog.progress(0)
        stop_flag  = st.session_state.get("auto_stop_requested", False)
        stop_btn   = col_stop.button("⏹ Dur", key="auto_stop_btn")
        if stop_btn:
            st.session_state["auto_stop_requested"] = True
        else:
            st.session_state["auto_stop_requested"] = False

        stat_line    = st.empty()
        best_kpi_box = st.empty()
        table_box    = st.empty()
        chart_box    = st.empty()

        collected   = []          # [(algorithm, params, util, time, plan)]
        _best       = [None, -1.0]  # [plan, util] — nonlocal yerine liste kullan
        _start_auto = time.time()

        def _update_ui(label, plan, util, elapsed, params=None):
            collected.append({
                "Algoritma / Aşama": label,
                "Doluluk %":         round(util, 2),
                "Süre (sn)":         round(elapsed, 1),
                "Parametreler":      str(params)[:55] if params else "—",
            })
            if util > _best[1]:
                _best[1] = util
                _best[0] = plan
                best_kpi_box.success(
                    f"✅ Şu anki en iyi: **%{util:.2f}** doluluk  |  "
                    f"Araç: {len([b for b in plan.bins if b])}  |  "
                    f"Geçen süre: {time.time()-_start_auto:.0f}s"
                )
                try:
                    _bid0 = next(i for i, b in enumerate(plan.bins) if b)
                    _fig  = visualize_3d_plan(plan, trucks_3d, pieces_3d, _bid0, True, True)
                    chart_box.plotly_chart(_fig, use_container_width=True, key=f"auto_live_{len(collected)}")
                except Exception:
                    pass
            _df = pd.DataFrame(collected).sort_values("Doluluk %", ascending=False)
            table_box.dataframe(
                _df, hide_index=True, use_container_width=True,
                column_config={"Doluluk %": st.column_config.ProgressColumn(
                    "Doluluk %", min_value=0, max_value=100, format="%.2f%%")}
            )

        # ── Strateji çalıştır ───────────────────────────────────────────────
        if _strat_key in ("greedy_sa", "ffd_genetic", "full_chain"):
            # Pipeline modunda — her aşama tamamlandıkça güncelle
            if _strat_key == "greedy_sa":
                stages = [
                    ("1. Greedy", "Greedy", {}),
                    # FIX-K3: initial_temp: 1200.0 kaldırıldı → auto-kalibrasyon.
                    ("2. Simulated Annealing", "SimulatedAnnealing",
                     {"max_time": auto_time_budget * 0.75, "cooling_rate": 0.997}),
                ]
            elif _strat_key == "ffd_genetic":
                stages = [
                    ("1. FFD Seed", "FFD", {}),
                    ("2. Genetic Algorithm", "Genetic",
                     {"population_size": 80, "generations": max(60, int(auto_time_budget / 3)),
                      "crossover_rate": 0.85, "mutation_rate": 0.2}),
                    ("3. Simulated Annealing (rafine)", "SimulatedAnnealing",
                     {"max_time": auto_time_budget * 0.3, "cooling_rate": 0.998}),
                ]
            else:  # full_chain
                _gt = max(30, int(auto_time_budget * 0.25))
                stages = [
                    ("1. FFD",    "FFD",    {}),
                    ("2. Greedy", "Greedy", {}),
                    ("3. Genetic Algorithm", "Genetic",
                     {"population_size": 60, "generations": max(50, int(_gt/2))}),
                    ("4. Simulated Annealing", "SimulatedAnnealing",
                     {"max_time": _gt, "cooling_rate": 0.996}),
                    ("5. Tabu Search", "TabuSearch",
                     {"max_iterations": 400, "max_time": _gt}),
                ]

            from iterative_optimizer_3d import _run_algorithm
            # FIX-K4: prev_plan → best_plan seed mantığı.
            # SA kötüleşirse Tabu Search en iyi noktadan başlar,
            # kötü intermediate noktadan değil. (Fix-D ile aynı mantık.)
            best_plan_pipe = None
            best_util_pipe = -1.0
            for si, (label, alg, params) in enumerate(stages):
                if st.session_state.get("auto_stop_requested"):
                    stat_line.warning("⏹ Kullanıcı tarafından durduruldu.")
                    break
                prog_bar.progress((si) / len(stages))
                stat_line.info(f"⏳ {label} çalışıyor…")
                try:
                    t0 = time.time()
                    plan, elapsed = _run_algorithm(
                        alg, params, pieces_3d, trucks_3d, best_plan_pipe)
                    _update_ui(label, plan, plan.utilization, elapsed, params or None)
                    if plan.utilization >= best_util_pipe:
                        best_util_pipe = plan.utilization
                        best_plan_pipe = plan
                    if plan.utilization >= auto_target_util:
                        stat_line.success(f"🎯 Hedef %{auto_target_util} aşıldı! → %{plan.utilization:.2f}")
                        break
                except Exception as e:
                    stat_line.warning(f"⚠️ {label}: {e}")
            prog_bar.progress(1.0)

        else:
            # Parametre taraması
            from iterative_optimizer_3d import _run_algorithm, _param_combinations, PARAM_SPACES

            _search_algos = ["Genetic", "SimulatedAnnealing", "TabuSearch", "MonteCarlo"]

            # FFD seed
            stat_line.info("🔧 FFD seed hazırlanıyor…")
            try:
                ffd_seed, ffd_t = _run_algorithm("FFD", {}, pieces_3d, trucks_3d)
                _update_ui("FFD (Seed)", ffd_seed, ffd_seed.utilization, ffd_t)
                if ffd_seed.utilization >= auto_target_util:
                    stat_line.success(f"🎯 FFD zaten %{ffd_seed.utilization:.2f} — hedef aşıldı!")
            except Exception as e:
                ffd_seed = None
                st.warning(f"FFD seed hatası: {e}")

            total_elapsed = time.time() - _start_auto
            combo_count   = 0

            for alg in _search_algos:
                if st.session_state.get("auto_stop_requested"):
                    break
                if time.time() - _start_auto >= auto_time_budget:
                    break
                space  = PARAM_SPACES.get(alg, {})
                combos = _param_combinations(space)

                for params in combos:
                    if st.session_state.get("auto_stop_requested"):
                        break
                    if time.time() - _start_auto >= auto_time_budget:
                        break
                    combo_count += 1
                    elapsed_pct = min((time.time() - _start_auto) / auto_time_budget, 0.99)
                    prog_bar.progress(elapsed_pct)
                    stat_line.info(f"⏳ {alg}  {params}  (geçen: {time.time()-_start_auto:.0f}s / {auto_time_budget}s)")
                    try:
                        plan, elapsed = _run_algorithm(alg, params, pieces_3d, trucks_3d, ffd_seed)
                        _update_ui(alg, plan, plan.utilization, elapsed, params)
                        if plan.utilization >= auto_target_util:
                            stat_line.success(f"🎯 Hedef %{auto_target_util} aşıldı! → %{plan.utilization:.2f}")
                            break
                    except Exception as e:
                        pass
                else:
                    continue
                break

            prog_bar.progress(1.0)

        # ── Sonuç ────────────────────────────────────────────────────────────
        best_plan = _best[0]
        best_util = _best[1]
        if best_plan:
            # Öne sıkıştır
            if compact_fwd:
                try:
                    best_plan = compact_forward(best_plan, pieces_3d, trucks_3d)
                except Exception:
                    pass
            stat_line.success(
                f"✅ Tamamlandı → **%{best_util:.2f}** doluluk  |  "
                f"Toplam süre: {time.time()-_start_auto:.0f}s  |  "
                f"{len(collected)} deneme yapıldı"
            )
            # En iyi config hafızaya kaydet
            best_entry = max(collected, key=lambda r: r["Doluluk %"])
            st.session_state["auto_best_config"] = {
                "algorithm":   best_entry["Algoritma / Aşama"],
                "utilization": best_entry["Doluluk %"],
                "params":      best_entry["Parametreler"],
                "strategy":    auto_strategy,
            }
            # Session state'e kaydet — mevcut sonuç gösterimini kullan
            st.session_state["last_results"]   = {"🤖 Otomatik Optimizer": best_plan}
            st.session_state["last_pieces_3d"] = pieces_3d
            st.session_state["last_trucks_3d"] = trucks_3d
            st.session_state["last_mode"]      = "🎯 Tek"
            _fig_cache_auto = {}
            for _bid_a, _bpl_a in enumerate(best_plan.bins):
                if _bpl_a:
                    try:
                        _fig_cache_auto[("🤖 Otomatik Optimizer", _bid_a)] = visualize_3d_plan(
                            best_plan, trucks_3d, pieces_3d, _bid_a, show_truck, show_grid)
                    except Exception:
                        pass
            st.session_state["last_fig_cache"] = _fig_cache_auto
            st.rerun()
        else:
            stat_line.error("❌ Hiçbir sonuç üretilemedi.")

    if run_btn:
        # ── Algoritma YALNIZCA load_rules tablosundaki parçaları kullanır ─────
        pieces_3d = build_pieces_from_load_rules(
            st.session_state.get("load_rules", pd.DataFrame()),
            st.session_state.get("geom_store", {}),
        )
        trucks_3d = build_trucks(df_trucks)
        if not pieces_3d: st.error("❌ Yük tanımlanmamış!"); st.stop()
        if not trucks_3d: st.error("❌ Araç tanımlanmamış!"); st.stop()

        # ── Akıllı Araç Seçimi (toggle açıksa) ────────────────────────────────
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
                    trucks_3d = sorted(_best_cfg.trucks, key=lambda t: t.get_volume(), reverse=True)
                    _fs_stat.success(
                        f"✅ En iyi araç kombinasyonu: **{_best_cfg.label()}** — "
                        f"algoritmalar bu araçlarla çalışacak."
                    )
                else:
                    _fs_stat.warning("⚠️ Araç seçimi sonuç vermedi, orijinal filo kullanılıyor.")
            except Exception as _fe:
                _fs_stat.warning(f"⚠️ Araç seçimi hatası: {_fe} — orijinal filo kullanılıyor.")
            _fs_bar.progress(1.0)

        run_list = [sel_algo] if mode=="🎯 Tek" else sel_algos
        all_results = {}
        prog = st.progress(0); stat = st.empty()

        for idx, akey in enumerate(run_list):
            stat.info(f"⏳ {ALGORITHMS[akey]['name']} çalışıyor… ({idx+1}/{len(run_list)})")
            prog.progress(idx/len(run_list))
            try:
                plan = run_algo(akey, pieces_3d, trucks_3d,
                                ts_time=ts_time, ts_tenure=ts_tenure,
                                sa_time=sa_time, sa_temp=sa_temp, sa_cool=sa_cool,
                                mc_iter=mc_iter, ga_pop=ga_pop, ga_gen=ga_gen,
                                layer_strat=layer_strat, nfp_res=nfp_res, nfp_margin=nfp_margin,
                                bay_time=bay_time, bay_trials=bay_trials, bay_target=bay_target,
                                isl_islands=isl_islands, isl_pop=isl_pop, isl_gen=isl_gen, isl_mig=isl_mig,
                                ms_starts=ms_starts, ms_time=ms_time)
                if plan:
                    if compact_fwd:
                        try:
                            plan = compact_forward(plan, pieces_3d, trucks_3d)
                        except Exception:
                            pass
                    all_results[ALGORITHMS[akey]["name"]] = plan
            except Exception as e:
                st.warning(f"⚠️ {ALGORITHMS[akey]['name']}: {e}")

        prog.progress(1.0); stat.empty(); prog.empty()
        if not all_results: st.error("❌ Hiçbir algoritma tamamlanamadı!"); st.stop()

        # Sonuçları session_state'e kaydet — her rerun'da korunur
        st.session_state["last_results"]   = all_results
        st.session_state["last_pieces_3d"] = pieces_3d
        st.session_state["last_trucks_3d"] = trucks_3d
        st.session_state["last_mode"]      = mode

        # ── Görsel önbellekleme (Plotly) ─────────────────────────────────────
        _fig_cache = {}
        for _akey_c, _plan_c in all_results.items():
            for _bid_c, _bpl_c in enumerate(_plan_c.bins):
                if _bpl_c:
                    try:
                        _fig_cache[(_akey_c, _bid_c)] = visualize_3d_plan(
                            _plan_c, trucks_3d, pieces_3d, _bid_c, show_truck, show_grid)
                    except Exception:
                        pass
        st.session_state["last_fig_cache"] = _fig_cache

        # ── Yerleştirilemeyen parça uyarısı ─────────────────────────────────
        total_req = sum(p.quantity for p in pieces_3d)
        best_placed = max(sum(len(b) for b in plan.bins) for plan in all_results.values())
        if best_placed < total_req:
            missing = total_req - best_placed
            warn_msg = (
                f"⚠️ **{missing} parça yerleştirilemedi.** Olası nedenler: "
                "Araç kapasitesi yetersiz, parçalar araç boyutlarına sığmıyor, "
                "veya Min. aralık ayarı çok büyük. "
                "💡 Öneri: Büyük araç ekleyin veya araç adedini artırın, "
                "ardından Tabu Search / Genetic Algorithm ile tekrar deneyin."
            )
            st.warning(warn_msg)
        else:
            st.success(f"✅ {len(all_results)} algoritma tamamlandı — tüm {total_req} parça yerleştirildi!")

        # ─ NFP 2D Planı
        nfp_data = st.session_state.get("nfp_plot")
        if nfp_data and show_nfp2d:
            st.markdown("---")
            st.subheader("🔷 NFP — 2D Kesit Yerleşim Planı")
            dims = st.session_state.get("nfp_truck",(300,600))
            st.plotly_chart(visualize_nfp_layout(nfp_data,dims[0],dims[1]),
                            use_container_width=True, key="nfp_chart")

        # ─ Proje kaydet
        rdict = results_dict_from(all_results, pieces_3d)
        best_name = max(all_results, key=lambda k: all_results[k].utilization)
        if project_name:
            proj = db_mod.create_project(co["id"], user["id"], project_name, project_desc)
            db_mod.save_project_data(proj.id,
                trucks=df_trucks.to_dict("records"),
                pieces=st.session_state.df_pallets.to_dict("records"),
                params={"algorithms":run_list,"nfp_res":nfp_res},
                results=rdict)
            st.info(f"💾 Proje kaydedildi: **{project_name}**")

        # ─ Rapor indirme
        if HAS_REPORTS:
            st.markdown("---")
            st.subheader("📥 Rapor İndir")
            r1,r2 = st.columns(2)
            pdf_b = generate_pdf_report(project_name, co.get("name",""),
                        df_trucks.to_dict("records"),
                        st.session_state.df_pallets.to_dict("records"),
                        rdict, best_name, {}, user["full_name"])
            r1.download_button("📄 PDF İndir", pdf_b,
                file_name=f"{project_name}_{time.strftime('%Y%m%d')}.pdf",
                mime="application/pdf", use_container_width=True)
            xl_b = generate_excel_report(project_name, co.get("name",""),
                        df_trucks.to_dict("records"),
                        st.session_state.df_pallets.to_dict("records"),
                        rdict, best_name)
            r2.download_button("📊 Excel İndir", xl_b,
                file_name=f"{project_name}_{time.strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)


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
    _fig_cache   = st.session_state.get("last_fig_cache", {})

    def _cached_fig(aname, bid):
        if (aname, bid) in _fig_cache:
            return _fig_cache[(aname, bid)]
        return visualize_3d_plan(
            _all_results[aname], _trucks_3d, _pieces_3d, bid, show_truck, show_grid)

    def _show_3d_fast(aname, bid, plotly_key):
        fig = _cached_fig(aname, bid)
        if fig:
            st.plotly_chart(fig, use_container_width=True, key=plotly_key)
        else:
            st.info(f"⚠️ '{aname}' / Araç {bid+1} için görsel üretilemedi.")

    st.markdown("---")

    def _safe_k(base):
        clean = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(base))
        if len(clean) > 90:
            clean = clean[:45] + "_" + _hs.md5(base.encode()).hexdigest()[:8]
        return clean

    # ── 🏆 EN İYİ TEK SONUÇ KARTI ─────────────────────────────────────────
    _best_name = max(_all_results, key=lambda k: _all_results[k].utilization)
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
        st.dataframe(_cdf, hide_index=True, use_container_width=True,
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


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA: PROJELERİM
# ─────────────────────────────────────────────────────────────────────────────
elif page == "📁 Projelerim":
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
                    ]), hide_index=True, use_container_width=True)
                cd,ca = st.columns(2)
                if cd.button("🗑️ Sil",    key=f"del_{p.id}"): db_mod.delete_project(p.id); st.rerun()
                if ca.button("📦 Arşivle",key=f"arc_{p.id}"): db_mod.archive_project(p.id); st.rerun()
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

    t_info, t_users = st.tabs(["🏢 Şirket","👥 Kullanıcılar"])
    with t_info:
        st.metric("Şirket",  co.get("name",""))
        st.metric("Plan",    co.get("plan","standard").capitalize())
    with t_users:
        users_list = db_mod.list_company_users(co["id"])
        st.dataframe(pd.DataFrame([{
            "Ad Soyad":u.full_name,"E-posta":u.email,
            "Rol":u.role,"Aktif":"✅" if u.is_active else "❌",
            "Son Giriş":u.last_login.strftime("%d.%m.%Y") if u.last_login else "—"
        } for u in users_list]), hide_index=True, use_container_width=True)

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

# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("🚛 LoadPlan Pro · EP (Crainic 2008) · Layer Building (George 1980) "
           "· Tabu (Lodi 2004) · SA (Mack 2004) · NFP (Bennell & Oliveira 2008)")
