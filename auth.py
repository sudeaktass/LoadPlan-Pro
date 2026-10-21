# -*- coding: utf-8 -*-
"""
Auth — Kullanıcı Kimlik Doğrulama & Oturum Yönetimi
=====================================================
· bcrypt ile şifre hash
· Streamlit session_state tabanlı oturum
· Rol bazlı yetkilendirme: admin / manager / operator
"""

from __future__ import annotations
import html
import logging
import time as _time
from typing import Optional

import bcrypt
import streamlit as st

from database import (
    get_user_by_email, create_company, create_user,
    update_last_login, get_company
)

log = logging.getLogger(__name__)

# ============================================================================
# ŞİFRE
# ============================================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ============================================================================
# OTURUM YARDIMCILARI
# ============================================================================

# Oturum süresi (saniye) — 0 = zaman aşımı yok, environment'tan override edilebilir
# GÜVENLİ VARSAYILAN: 30 dk hareketsizlikte oturum düşer (eski varsayılan 0 =
# sınırsızdı). Kapatmak için SESSION_TIMEOUT_SECONDS=0 verin.
import os as _os
SESSION_TIMEOUT_SECONDS = int(_os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))

# ── Login brute-force freni (oturum bazlı) ───────────────────────────────────
_LOGIN_MAX_FAILS   = 5      # bu kadar başarısız denemeden sonra…
_LOGIN_LOCK_SECS   = 60     # …bu kadar saniye beklet


def login_blocked_seconds() -> int:
    """Arka arkaya başarısız girişten sonra kalan bekleme süresi (0 = serbest)."""
    fails = st.session_state.get("_login_fails", 0)
    if fails < _LOGIN_MAX_FAILS:
        return 0
    last = float(st.session_state.get("_login_last_fail", 0.0))
    remain = int(_LOGIN_LOCK_SECS - (_time.time() - last))
    if remain <= 0:
        st.session_state["_login_fails"] = 0
        return 0
    return remain


def _register_login_failure():
    st.session_state["_login_fails"] = st.session_state.get("_login_fails", 0) + 1
    st.session_state["_login_last_fail"] = _time.time()


def is_logged_in() -> bool:
    """
    Giriş yapılmış mı?
    SESSION_TIMEOUT_SECONDS > 0 ise hareketsizlik kontrolü yapılır.
    0 veya negatif değerde oturum hiç kapanmaz.
    """
    if st.session_state.get("user_id") is None:
        return False
    # Timeout kontrolü — yalnızca etkinleştirilmişse
    if SESSION_TIMEOUT_SECONDS > 0:
        from datetime import datetime
        last = st.session_state.get("last_activity")
        if last is not None:
            elapsed = datetime.now().timestamp() - float(last)
            if elapsed > SESSION_TIMEOUT_SECONDS:
                logout()
                st.warning(
                    f"⏰ Oturumunuz {SESSION_TIMEOUT_SECONDS // 60} dakika "
                    f"hareketsizlik nedeniyle sona erdi. Lütfen tekrar giriş yapın."
                )
                return False
        st.session_state["last_activity"] = datetime.now().timestamp()
    return True


def current_user() -> Optional[dict]:
    return st.session_state.get("current_user")


def current_company() -> Optional[dict]:
    return st.session_state.get("current_company")


def require_login():
    """Giriş yapılmamışsa sayfayı durdurur."""
    if not is_logged_in():
        st.error("🔒 Bu sayfayı görüntülemek için giriş yapmanız gerekiyor.")
        st.stop()


def require_role(*allowed_roles: str):
    """Yetersiz rol varsa sayfayı durdurur."""
    require_login()
    user = current_user()
    if user and user.get("role") not in allowed_roles:
        st.error(f"⛔ Bu işlem için yetkiniz yok. Gerekli rol: {', '.join(allowed_roles)}")
        st.stop()


# ============================================================================
# GİRİŞ / ÇIKIŞ
# ============================================================================

def login(email: str, password: str) -> bool:
    """
    E-posta ve şifre ile giriş yapar.
    Başarılıysa session_state'e kullanıcı ve şirket bilgilerini yazar.
    """
    if login_blocked_seconds() > 0:
        return False
    user_obj = get_user_by_email(email.strip().lower())
    if user_obj is None:
        _register_login_failure()
        return False
    if not user_obj.is_active:
        _register_login_failure()
        return False
    if not verify_password(password, user_obj.password_hash):
        _register_login_failure()
        return False
    st.session_state["_login_fails"] = 0

    update_last_login(user_obj.id)
    co = get_company(user_obj.company_id)

    # Oturum başlangıç zamanı — timeout kontrolü için
    from datetime import datetime
    st.session_state["session_start"]   = datetime.now().timestamp()
    st.session_state["last_activity"]   = datetime.now().timestamp()
    st.session_state["user_id"]    = user_obj.id
    st.session_state["company_id"] = user_obj.company_id
    st.session_state["current_user"] = {
        "id":        user_obj.id,
        "email":     user_obj.email,
        "full_name": user_obj.full_name,
        "role":      user_obj.role,
        "company_id": user_obj.company_id,
    }
    st.session_state["current_company"] = {
        "id":   co.id,
        "name": co.name,
        "slug": co.slug,
        "plan": co.plan,
        "logo_url": co.logo_url,
    } if co else {}
    return True


def logout():
    """Oturumu VE oturuma ait iş verilerini temizler.

    Eski sürüm yalnız auth anahtarlarını siliyordu; paylaşılan terminalde
    sonraki kullanıcı önceki kullanıcının planlarını/yük listesini görüyordu.
    """
    for key in ["user_id", "company_id", "current_user", "current_company",
                "session_start", "last_activity",
                # iş verileri
                "last_results", "last_pieces_3d", "last_trucks_3d",
                "last_fig_cache", "last_rdict", "last_best_name",
                "last_mode", "last_project_name",
                "load_rules", "load_rules_live", "deleted_ids", "geom_store",
                "df_pallets", "df_trucks", "df_trucks_live",
                "sw_shapes", "sw_staging", "custom_profiles", "nfp_plot"]:
        st.session_state.pop(key, None)


# ============================================================================
# KAYIT (Yeni Şirket + Admin Kullanıcı)
# ============================================================================

def register_company(company_name: str, admin_email: str,
                     admin_name: str, password: str) -> tuple[bool, str]:
    """
    Yeni şirket ve ilk admin kullanıcı oluşturur.
    Döndürür: (başarı, mesaj)
    """
    if len(password) < 8:
        return False, "Şifre en az 8 karakter olmalıdır."
    try:
        h = hash_password(password)
        create_company(
            name               = company_name,
            admin_email        = admin_email.strip().lower(),
            admin_name         = admin_name,
            admin_password_hash = h,
        )
        return True, f"✅ '{company_name}' şirketi oluşturuldu. Giriş yapabilirsiniz."
    except Exception as e:
        if "UNIQUE" in str(e) or "unique" in str(e):
            return False, "Bu şirket adı veya e-posta zaten kayıtlı."
        # İç hata detayı kullanıcıya sızdırılmaz — log'a yazılır
        log.error(f"Şirket kaydı hatası: {e}")
        return False, "Kayıt sırasında bir hata oluştu. Lütfen tekrar deneyin."


def add_user_to_company(company_id: int, email: str, full_name: str,
                        password: str, role: str = "operator") -> tuple[bool, str]:
    """Admin tarafından kullanıcı ekler."""
    try:
        h = hash_password(password)
        create_user(company_id, email.strip().lower(), full_name, h, role)
        return True, f"✅ {full_name} ({email}) eklendi."
    except Exception as e:
        if "UNIQUE" in str(e):
            return False, "Bu e-posta zaten kayıtlı."
        log.error(f"Kullanıcı ekleme hatası: {e}")
        return False, "Kullanıcı eklenirken bir hata oluştu."


# ============================================================================
# GİRİŞ SAYFASI UI KOMPONENTI
# ============================================================================

def render_login_page():
    """
    Tam sayfa giriş / kayıt UI'ı.
    app_3d.py'nin başında çağrılır; giriş yapılmamışsa sayfayı baskılar.
    """
    st.markdown("""
    <style>
    .auth-card {
        max-width: 440px; margin: 60px auto; padding: 2.5rem;
        background: #1a1f2e; border-radius: 16px;
        border: 1px solid rgba(56,139,253,0.3);
        box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    }
    .auth-title {
        font-size: 2rem; font-weight: 700; color: #e6edf3;
        text-align: center; margin-bottom: 0.3rem;
    }
    .auth-sub {
        color: #8b949e; text-align: center; margin-bottom: 1.8rem; font-size: 0.9rem;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
        st.markdown('<div class="auth-title">🚛 LoadPlan Pro</div>', unsafe_allow_html=True)
        st.markdown('<div class="auth-sub">Kurumsal 3D Araç Yükleme Optimizasyonu</div>',
                    unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["🔑 Giriş Yap", "🏢 Şirket Kaydı"])

        with tab_login:
            with st.form("login_form"):
                email    = st.text_input("E-posta", placeholder="ornek@sirket.com")
                password = st.text_input("Şifre", type="password")
                submitted = st.form_submit_button("Giriş Yap", type="primary",
                                                  width="stretch")
                if submitted:
                    _blocked = login_blocked_seconds()
                    if _blocked > 0:
                        st.error(f"⛔ Çok fazla başarısız deneme — "
                                 f"{_blocked} sn sonra tekrar deneyin.")
                    elif login(email, password):
                        st.success("✅ Giriş başarılı!")
                        st.rerun()
                    else:
                        st.error("❌ E-posta veya şifre hatalı.")

        with tab_register:
            with st.form("register_form"):
                co_name   = st.text_input("Şirket Adı", placeholder="ABC Lojistik A.Ş.")
                adm_name  = st.text_input("Adınız Soyadınız")
                adm_email = st.text_input("E-posta")
                adm_pass  = st.text_input("Şifre (min. 8 karakter)", type="password")
                adm_pass2 = st.text_input("Şifre Tekrar", type="password")
                submitted = st.form_submit_button("Şirketi Kaydet", type="primary",
                                                  width="stretch")
                if submitted:
                    if adm_pass != adm_pass2:
                        st.error("Şifreler eşleşmiyor.")
                    else:
                        ok, msg = register_company(co_name, adm_email, adm_name, adm_pass)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)

        st.markdown('</div>', unsafe_allow_html=True)

    st.stop()


# ============================================================================
# ŞİRKET PANELİ UI KOMPONENTI (sidebar'da gösterilir)
# ============================================================================

def render_user_sidebar():
    """Sidebar üst kısmında gelişmiş kullanıcı profil kartı + çıkış butonu."""
    user = current_user()
    co   = current_company()
    if not user:
        return

    # Rol renk & etiket tanımları
    ROLE_META = {
        "admin":    ("Admin",    "#FF5252", "#C62828"),
        "manager":  ("Yönetici", "#FFB300", "#E65100"),
        "operator": ("Operatör", "#69F0AE", "#1B5E20"),
    }
    role_label, role_color, role_dark = ROLE_META.get(
        user["role"], (user["role"], "#90CAF9", "#1565C0")
    )

    # Avatar baş harfleri (en fazla 2)
    full_name    = user.get("full_name", "?") or "?"
    initials     = "".join(w[0].upper() for w in full_name.split()[:2])
    company_name = (co.get("name", "—") if co else "—")
    email        = user.get("email", "")
    # E-posta çok uzunsa kısalt
    email_disp   = email if len(email) <= 26 else email[:23] + "…"

    # XSS koruması: kayıt formundan gelen değerler unsafe_allow_html HTML'e
    # gömülür — kaçışlanmadan basılırsa stored XSS olur. html.escape şart.
    full_name    = html.escape(full_name)
    initials     = html.escape(initials)
    company_name = html.escape(company_name)
    email_disp   = html.escape(email_disp)

    st.sidebar.markdown("---")

    # ── Profil kartı (HTML) — max 3 boşluk girinti (4 boşluk = md kod bloğu!) ──
    _avatar_style = (
        "flex-shrink:0;width:44px;height:44px;border-radius:50%;"
        f"background:linear-gradient(135deg,{role_dark},{role_color}55);"
        f"border:2px solid {role_color};"
        "display:flex;align-items:center;justify-content:center;"
        f"font-size:16px;font-weight:700;color:#fff;box-shadow:0 0 10px {role_color}44;"
    )
    _dot_style = (
        f"width:6px;height:6px;border-radius:50%;background:{role_color};"
        f"box-shadow:0 0 5px {role_color};display:inline-block;margin-right:5px;"
    )
    _badge_style = (
        f"display:inline-flex;align-items:center;background:{role_color}18;"
        f"border:1px solid {role_color}55;color:{role_color};"
        "font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px;"
        "letter-spacing:0.8px;text-transform:uppercase;"
    )
    st.sidebar.markdown(f"""
<div style="background:linear-gradient(145deg,rgba(255,255,255,0.06),rgba(255,255,255,0.02));border:1px solid rgba(255,255,255,0.10);border-radius:14px;padding:14px 14px 12px;margin-bottom:10px;">
 <div style="display:flex;align-items:center;gap:11px;margin-bottom:11px;">
  <div style="{_avatar_style}">{initials}</div>
  <div style="min-width:0;flex:1;">
   <div style="font-size:14px;font-weight:600;color:#e6edf3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1.3;">{full_name}</div>
   <div style="font-size:11px;color:#8b949e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px;">{company_name}</div>
  </div>
 </div>
 <div style="border-top:1px solid rgba(255,255,255,0.07);margin-bottom:10px;"></div>
 <div style="margin-bottom:8px;">
  <span style="{_badge_style}"><span style="{_dot_style}"></span>{role_label}</span>
 </div>
 <div style="display:flex;align-items:center;gap:6px;font-size:10px;color:#6e7681;">
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#6e7681" stroke-width="2" stroke-linecap="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2 7 10 7 10-7"/></svg>
  <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{email_disp}</span>
 </div>
</div>
""", unsafe_allow_html=True)

    # ── Çıkış butonu CSS (sadece bu butonu hedefle) ──────────────────────────
    st.sidebar.markdown("""
<style>
div[data-testid="stSidebar"] div[data-testid="stButton"]:last-of-type > button {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%) !important;
    border: 1px solid rgba(255,82,82,0.4) !important;
    color: #FF5252 !important;
    border-radius: 8px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stSidebar"] div[data-testid="stButton"]:last-of-type > button:hover {
    background: linear-gradient(135deg, #C62828 0%, #B71C1C 100%) !important;
    border-color: transparent !important;
    color: #fff !important;
    box-shadow: 0 4px 12px rgba(198,40,40,0.35) !important;
}
</style>
""", unsafe_allow_html=True)

    if st.sidebar.button("⏻  Çıkış Yap", width="stretch", key="sidebar_logout"):
        logout()
        st.rerun()

    st.sidebar.markdown("---")


def has_role(*allowed_roles: str) -> bool:
    """Sessiz kontrol — st.stop() çağırmaz, sadece bool döner.

    UI bölümlerini koşullu göstermek için kullanılır:
        if has_role("admin"):
            st.button("Admin İşlemi")
    """
    if not is_logged_in():
        return False
    user = current_user()
    return user is not None and user.get("role") in allowed_roles


def get_allowed_pages(role: str) -> list:
    """
    Bir rol için izin verilen sayfa listesini döndür.

    Yetki Matrisi:
        admin    → Tüm sayfalar (Dashboard, Optimizasyon, Projelerim, Şirket Ayarları)
        manager  → Dashboard, Optimizasyon, Projelerim, Şirket Ayarları (kullanıcı ekleme hariç)
        operator → Dashboard, Optimizasyon, Projelerim
    """
    base = ["🚀 Optimizasyon", "🚚 Filo", "📁 Projelerim"]
    if role in ("admin", "manager"):
        base.append("⚙️ Şirket Ayarları")
    return base
