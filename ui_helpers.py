# -*- coding: utf-8 -*-
"""
UI Helpers — Kullanıcı Deneyimi İyileştirmeleri
==================================================
- Tooltip sözlüğü (tek yerde toplanır, her widget'a help= olarak verilir)
- Onboarding adımları (yeni kullanıcı yolu)
- Empty state mesajları
- Hata kodu → kullanıcı dostu mesaj sözlüğü
- Klavye kısayolu yardım kartı
"""

from typing import Optional, Dict
import streamlit as st


# ─── TOOLTIP SÖZLÜĞÜ ────────────────────────────────────────────────────────
# Tek yerde toplanır → kullanım: st.button("X", help=TIPS["truck_count"])

TIPS: Dict[str, str] = {
    # Araç filosu
    "truck_count": "Bu tipten kaç adet aracınız var? Algoritma minimum sayıda kullanır.",
    "truck_dims": "Araç iç ölçüleri (cm). Genişlik × Uzunluk × Yükseklik.",
    "truck_capacity": "Maksimum yük kapasitesi (kg). Bu değer aşılmamalıdır.",

    # Parça/palet
    "piece_priority": (
        "Yükleme önceliği. **1** = kapıya yakın yerleşir (önce indirilecek). "
        "Boş bırakılırsa öncelik yoktur. Sayı küçüldükçe öncelik artar."
    ),
    "piece_fragile": "Kırılgan ürünler ÜZERE başka bir şey istiflenmez.",
    "piece_quantity": "Aynı boyut ve özellikteki kaç adet ürün?",
    "piece_shape": (
        "Dikdörtgen kutular doğrudan, silindirler çevreleyici kutu (bounding box) "
        "olarak ele alınır."
    ),

    # Algoritma seçimi
    "algo_mode": (
        "🎯 **Tek**: yalnızca seçtiğiniz algoritma çalışır.  \n"
        "📊 **Karşılaştırmalı**: birden çok algoritma yan yana karşılaştırılır."
    ),
    "algo_select": (
        "Karmaşıklık önerisi için aşağıdaki **🤖 Algoritma Öner** kartına bakın. "
        "Şüphedeyseniz **FFD** ile başlayın."
    ),

    # Optimizasyon parametreleri
    "param_population": "Genetik Algoritma popülasyon büyüklüğü. Yüksek = daha kapsamlı, yavaş.",
    "param_generations": "GA nesil sayısı. Tipik 30-100.",
    "param_max_iter": "Tabu/SA iterasyon sayısı. 50-200 arası dengeli.",
    "param_max_time": "Algoritmaya verilen saniye bütçesi.",

    # Tam Optimizasyon
    "full_opt": (
        "**Tam Optimizasyon** birden çok algoritma yapılandırmasını tarar ve en iyi "
        "sonucu seçer. ⚠️ 100+ parçada birkaç dakika sürebilir."
    ),
    "auto_param": (
        "🤖 **Sadece Parametreler** modu: Bayesian Optimization ile en iyi "
        "hiperparametreyi otomatik bulur. Mevcut araç filosunu kullanır."
    ),

    # Çıktı
    "pdf_management": "Yönetici raporu: doluluk metrikleri, karşılaştırma, KPI'lar.",
    "pdf_driver": (
        "Sürücü için yükleme talimatı: her parça için sıra numarası + QR kod. "
        "Aracın arkasındaki parça **1**, kapıdaki son numara."
    ),

    # Sistem
    "backup": "Veritabanı yedeklemesi. Günlük cron önerilir.",
    "session_timeout": "Hareketsizlik halinde otomatik çıkış (default: 30 dk).",
}


# ─── EMPTY STATE MESAJLARI ──────────────────────────────────────────────────

def render_empty_state(
    icon: str,
    title: str,
    description: str,
    cta_label: Optional[str] = None,
    cta_target_page: Optional[str] = None,
):
    """
    Boş durum kartı — yeni kullanıcı için yol gösterici.

    Kullanım:
        render_empty_state(
            "📂", "Henüz proje yok",
            "İlk yükleme planınızı oluşturmak için Optimizasyon sayfasına gidin.",
            cta_label="🚀 Optimizasyona Git",
            cta_target_page="🚀 Optimizasyon",
        )
    """
    st.markdown(f"""
    <div style="
        text-align:center;
        padding:40px 20px;
        background:rgba(255,255,255,0.03);
        border:1px dashed rgba(255,255,255,0.15);
        border-radius:12px;
        margin:20px 0;
    ">
        <div style="font-size:48px;line-height:1;margin-bottom:12px">{icon}</div>
        <div style="font-size:18px;font-weight:600;color:#e6edf3;margin-bottom:8px">{title}</div>
        <div style="font-size:13px;color:#8b949e;max-width:400px;margin:0 auto 16px">
            {description}
        </div>
    </div>
    """, unsafe_allow_html=True)
    if cta_label and cta_target_page:
        if st.button(cta_label, type="primary", use_container_width=False):
            st.session_state.nav_page = cta_target_page
            st.rerun()


# ─── HATA KODU SÖZLÜĞÜ ──────────────────────────────────────────────────────
# Teknik hata → operatör dostu mesaj

ERROR_MESSAGES: Dict[str, Dict[str, str]] = {
    "ConstraintViolation": {
        "title": "⚠️ Bazı ürünler yerleşmedi",
        "user_msg": (
            "Mevcut araç sayısı tüm ürünleri kaldırmıyor. "
            "Çözüm: filoya araç ekleyin veya 'Adet' sayısını artırın."
        ),
        "tech_msg": "Algoritma sonu validate_all_placed başarısız oldu.",
    },
    "ValueError_fleet": {
        "title": "❌ Filo Yetersiz",
        "user_msg": (
            "Toplam yük araç filosunun hacim/ağırlık kapasitesini aşıyor. "
            "Sidebar'dan daha büyük araç ekleyin."
        ),
        "tech_msg": "minimum_vehicle_selector: total_demand > fleet_capacity.",
    },
    "ImpossibleToSolve": {
        "title": "❌ Geometrik Çözüm Yok",
        "user_msg": (
            "Filo toplam kapasitesi yeterli ama parçalar fiziksel olarak sığmıyor. "
            "Bunun sebebi olabilir: çok büyük tek parça, ağırlık merkezi kısıtı, "
            "veya öncelik çakışması. Tanı raporu için ekrandaki uyarıyı kontrol edin."
        ),
        "tech_msg": "rescue_placement de eksik üretti.",
    },
    "NoVehicleAvailable": {
        "title": "❌ Uygun Araç Yok",
        "user_msg": "Bu parçanın boyutuna/ağırlığına uygun araç filosunda yok.",
        "tech_msg": "assign_new_vehicle_for_unplaced: no candidate.",
    },
    "WeightCenterViolation": {
        "title": "⚖️ Ağırlık Merkezi Sınır Dışı",
        "user_msg": (
            "Yükleme planı aracın ağırlık merkezini bozar (trafik güvenliği). "
            "Algoritma alternatif yerleşim deneyecek."
        ),
        "tech_msg": "weight_center_ok döndü False.",
    },
}


def render_friendly_error(exception_name: str, original_msg: str = ""):
    """Hata kodunu kullanıcı dostu formatta göster."""
    info = ERROR_MESSAGES.get(exception_name)
    if not info:
        st.error(f"⚠️ Hata: {original_msg or exception_name}")
        return
    st.error(f"**{info['title']}**\n\n{info['user_msg']}")
    if original_msg:
        with st.expander("🔧 Teknik detay"):
            st.code(original_msg, language=None)
            st.caption(f"Sistem mesajı: `{info['tech_msg']}`")


# ─── KLAVYE KISAYOLU YARDIM KARTI ───────────────────────────────────────────

def render_keyboard_shortcuts_help():
    """Streamlit native kısayolları + ipuçları."""
    with st.expander("⌨️ Klavye Kısayolları & İpuçları"):
        st.markdown("""
        | Kısayol | İşlev |
        |---------|-------|
        | `R` | Sayfayı yenile (Streamlit native) |
        | `Ctrl/Cmd + Enter` | Form gönder |
        | `Esc` | Modal/popup kapat |
        | `?` (Streamlit menüsünden) | Yardım menüsü |

        **İpuçları:**
        - Sidebar'ı küçültmek için sol üstteki `<` butonuna basın.
        - Sayfa yenilendiğinde sonuçlar korunur (session state).
        - Sayfa çubuğunda navigasyon butonları sırasıyla aktif sayfayı gösterir.
        - Tablodaki sütun başlığına tıklayarak sıralayın.
        """)


# ─── ONBOARDING WIZARD ──────────────────────────────────────────────────────

def render_onboarding_card(user_name: str, project_count: int):
    """
    Yeni kullanıcı için 3 adımlı yönlendirme kartı.
    Sadece project_count == 0 ise gösterilir.
    """
    if project_count > 0:
        return

    st.markdown(f"""
    <div style="
        background:linear-gradient(135deg,#1e3a5f 0%,#2c5282 100%);
        border-radius:14px;
        padding:24px 28px;
        margin:16px 0;
        color:#e6edf3;
    ">
        <div style="font-size:20px;font-weight:600;margin-bottom:6px">
            👋 Hoş geldiniz, {user_name.split()[0] if user_name else 'kullanıcı'}!
        </div>
        <div style="font-size:13px;color:#a3b8d4;margin-bottom:16px">
            İlk yükleme planınızı 3 adımda oluşturun:
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap">
            <div style="flex:1;min-width:180px;background:rgba(255,255,255,0.08);padding:14px;border-radius:8px">
                <div style="font-size:24px;margin-bottom:6px">1️⃣</div>
                <div style="font-weight:600;margin-bottom:4px;font-size:13px">Araç Filosu Tanımla</div>
                <div style="font-size:11px;color:#a3b8d4;line-height:1.5">
                    Sidebar'dan boyutlar ve kapasite gir.
                </div>
            </div>
            <div style="flex:1;min-width:180px;background:rgba(255,255,255,0.08);padding:14px;border-radius:8px">
                <div style="font-size:24px;margin-bottom:6px">2️⃣</div>
                <div style="font-weight:600;margin-bottom:4px;font-size:13px">Paletleri Ekle</div>
                <div style="font-size:11px;color:#a3b8d4;line-height:1.5">
                    Excel'den içe aktar veya manuel ekle.
                </div>
            </div>
            <div style="flex:1;min-width:180px;background:rgba(255,255,255,0.08);padding:14px;border-radius:8px">
                <div style="font-size:24px;margin-bottom:6px">3️⃣</div>
                <div style="font-weight:600;margin-bottom:4px;font-size:13px">Optimizasyon Başlat</div>
                <div style="font-size:11px;color:#a3b8d4;line-height:1.5">
                    🤖 Algoritma öneri kartından seç ve çalıştır.
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─── ALGORİTMA ÖNERİ KARTI (sidebar entegrasyonu) ──────────────────────────

def render_algorithm_recommendation_card(pieces, trucks):
    """
    Sidebar'da gösterilebilen akıllı öneri kartı.
    algorithm_recommender modülünden öneri çeker.
    """
    if not pieces or not trucks:
        st.info("💡 Parça ve araç ekleyin → akıllı öneri burada görünecek")
        return None

    try:
        from algorithm_recommender import (
            profile_problem, recommend_algorithms, format_problem_summary,
        )
        profile = profile_problem(pieces, trucks)
        recs = recommend_algorithms(profile)
    except Exception as e:
        st.caption(f"⚠️ Öneri yüklenemedi: {e}")
        return None

    st.markdown("##### 🤖 Akıllı Öneri")
    st.caption(format_problem_summary(profile))

    cols = st.columns(3)
    tier_styles = {
        "fast":     ("⚡", "#27500A"),
        "balanced": ("⚖️", "#185FA5"),
        "best":     ("🏆", "#BA7517"),
    }
    for col, rec in zip(cols, recs):
        icon, color = tier_styles.get(rec.tier, ("•", "#666"))
        with col:
            st.markdown(
                f"""<div style="text-align:center;padding:8px;
                    border:1px solid {color}44;border-radius:8px;
                    background:{color}11">
                    <div style="font-size:22px">{rec.icon}</div>
                    <div style="font-size:11px;font-weight:600;color:{color}">
                        {icon} {rec.tier.upper()}
                    </div>
                    <div style="font-size:11px;color:var(--text-color);margin-top:3px">
                        {rec.label}
                    </div>
                    <div style="font-size:9px;color:#888;margin-top:2px">
                        ~{rec.estimated_time_sec:.0f}s
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button("Seç", key=f"rec_sel_{rec.tier}",
                         use_container_width=True):
                _cur_mode = st.session_state.get("_algo_mode", "🎯 Tek")
                if _cur_mode == "📊 Karşılaştırmalı":
                    # Karşılaştırmalı: bu algoritmayı seçililer listesine ekle,
                    # diğer seçimler kaybolmaz
                    st.session_state[f"cmp_{rec.algo_key}"] = True
                    return ("compare", rec.algo_key)
                else:
                    # Tek mod: bu algoritmayı radio'da ön-seç
                    st.session_state["_tek_sel_key"] = rec.algo_key
                    return ("tek", rec.algo_key)

    # Hangi öneri seçilirse onun açıklamasını göster
    with st.expander("📖 Neden bu öneriler?"):
        for rec in recs:
            st.markdown(
                f"**{rec.icon} {rec.label}** · {rec.tier.title()}  \n"
                f"_{rec.reason}_  \n"
                f"Tahmini süre: ~{rec.estimated_time_sec:.0f}s · "
                f"Beklenen doluluk: %{rec.expected_util_pct[0]:.0f}–%{rec.expected_util_pct[1]:.0f}"
            )
            st.markdown("---")

    return None
