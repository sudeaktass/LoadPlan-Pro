# -*- coding: utf-8 -*-
"""
🚚 Filo sayfası — çekici ve dorse kayıtları (karar J, 21 Ekim 2026)
===================================================================
Ayrı bir sayfa, iki sekme: Çekiciler ve Dorseler.

Her formda:
  * zorunlu ve isteğe bağlı alanlar AYRI gruplarda
  * birim etiketleri (kg, mm) görünür
  * kaynak ve "varsayım" bilgisi görünür
  * dorse formunda iç hacim HESAPLANIR (girilmez)
  * eşleşme önizlemesi: yasal toplam, faydalı yük ve BAĞLAYAN sınır

Veriler veritabanında kalıcıdır (karar I); plaka benzersizliği çekici ve
dorse tablolarında birlikte kontrol edilir (karar S17-b).
"""

from __future__ import annotations

import dataclasses
from typing import List, Optional

import pandas as pd
import streamlit as st

import database as db_mod
from dingil_yuku import arac_dingil_raporu, cm_to_mm_cg
from filo_havuzu import eslesme_to_truck3d, mm_to_cm
from filo_modeli import Cekici, Dorse, cekici_ata, eslesme_hesapla
from filo_secimi import (aktif_filo, eski_tablo_ayarla,
                         eski_tablo_mu, secimi_kaydet)
from ornek_filo import ford_fmax_4x2, schmitz_scs_24l


# ─────────────────────────────────────────────────────────────────────────────
# Veritabanı ↔ dataclass
# ─────────────────────────────────────────────────────────────────────────────

def _cekici_kayitlari() -> List[Cekici]:
    with db_mod.get_session() as s:
        satirlar = (s.query(db_mod.CekiciKaydi)
                    .filter(db_mod.CekiciKaydi.aktif.is_(True))
                    .order_by(db_mod.CekiciKaydi.plaka).all())
        return [_cekici_cevir(r.get_veri()) for r in satirlar]


def _dorse_kayitlari() -> List[Dorse]:
    with db_mod.get_session() as s:
        satirlar = (s.query(db_mod.DorseKaydi)
                    .filter(db_mod.DorseKaydi.aktif.is_(True))
                    .order_by(db_mod.DorseKaydi.plaka).all())
        return [_dorse_cevir(r.get_veri()) for r in satirlar]


def _alanlari_suz(veri: dict, klass) -> dict:
    """Bilinmeyen alanları at — eski kayıtlar yeni sürümde de açılsın."""
    gecerli = {f.name for f in dataclasses.fields(klass)}
    return {k: v for k, v in (veri or {}).items() if k in gecerli}


def _cekici_cevir(veri: dict) -> Cekici:
    return Cekici(**_alanlari_suz(veri, Cekici))


def _dorse_cevir(veri: dict) -> Dorse:
    return Dorse(**_alanlari_suz(veri, Dorse))


def _cekici_kaydet(c: Cekici) -> Optional[str]:
    hata = db_mod.plaka_kullanimda_mi(c.plaka, haric_tablo="cekici",
                                      haric_id=_mevcut_id("cekici", c.plaka))
    if hata and _mevcut_id("cekici", c.plaka) is None:
        return hata
    with db_mod.get_session() as s:
        satir = (s.query(db_mod.CekiciKaydi)
                 .filter(db_mod.CekiciKaydi.plaka == c.plaka).first())
        if satir is None:
            satir = db_mod.CekiciKaydi(plaka=c.plaka)
            s.add(satir)
        satir.marka_model = c.marka_model
        satir.set_veri(dataclasses.asdict(c))
        satir.aktif = True
        s.commit()
    return None


def _dorse_kaydet(d: Dorse) -> Optional[str]:
    hata = db_mod.plaka_kullanimda_mi(d.plaka, haric_tablo="dorse",
                                      haric_id=_mevcut_id("dorse", d.plaka))
    if hata and _mevcut_id("dorse", d.plaka) is None:
        return hata
    with db_mod.get_session() as s:
        satir = (s.query(db_mod.DorseKaydi)
                 .filter(db_mod.DorseKaydi.plaka == d.plaka).first())
        if satir is None:
            satir = db_mod.DorseKaydi(plaka=d.plaka)
            s.add(satir)
        satir.tip = d.tip
        satir.set_veri(dataclasses.asdict(d))
        satir.aktif = True
        s.commit()
    return None


def _mevcut_id(tur: str, plaka: str) -> Optional[int]:
    with db_mod.get_session() as s:
        model = db_mod.CekiciKaydi if tur == "cekici" else db_mod.DorseKaydi
        satir = s.query(model).filter(model.plaka == plaka).first()
        return satir.id if satir else None


def _pasife_al(tur: str, plaka: str) -> None:
    with db_mod.get_session() as s:
        model = db_mod.CekiciKaydi if tur == "cekici" else db_mod.DorseKaydi
        satir = s.query(model).filter(model.plaka == plaka).first()
        if satir:
            satir.aktif = False
            s.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────────────────────────────────────

def _bos_mu(x) -> bool:
    return x is None or x == 0


def _sayi_veya_none(x):
    return None if (x is None or float(x) <= 0) else float(x)


def _cekici_listesi(cekiciler: List[Cekici]) -> None:
    """Kayıtlı çekicilerin özet tablosu — tek bakışta görünsün."""
    if not cekiciler:
        st.caption("Henüz çekici kaydı yok.")
        return
    satirlar = []
    for c in cekiciler:
        eksik = c.eksik_dingil_alanlari()
        satirlar.append({
            "Plaka": c.plaka,
            "Marka / model": c.marka_model or "—",
            "Dingil": c.dingil_sayisi,
            "Boş ağırlık (kg)": int(c.bos_agirlik_kg or 0),
            "GCW (kg)": int(c.teknik_gcw_kg) if c.teknik_gcw_kg else "—",
            "e (mm)": int(c.besinci_teker_ofset_mm or 0),
            "Dingil kontrolü": "✅" if not eksik else f"⚠️ {len(eksik)} eksik",
            "Varsayım": "🔎" if c.varsayim_alanlari else "",
        })
    st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch")


def _dorse_listesi(dorseler: List[Dorse]) -> None:
    """Kayıtlı dorselerin özet tablosu."""
    if not dorseler:
        st.caption("Henüz dorse kaydı yok.")
        return
    satirlar = []
    for d in dorseler:
        eksik = d.eksik_dingil_alanlari()
        satirlar.append({
            "Plaka": d.plaka,
            "Tip": d.tip,
            "İç ölçü (mm)": f"{d.ic_uzunluk_mm:.0f}×{d.ic_genislik_mm:.0f}"
                            f"×{d.ic_yukseklik_mm:.0f}",
            "İç hacim (m³)": round(d.ic_hacim_m3, 1),
            "Boş ağırlık (kg)": int(d.bos_agirlik_kg or 0),
            "Dingil": d.dingil_sayisi,
            "Dingil kontrolü": "✅" if not eksik else f"⚠️ {len(eksik)} eksik",
            "40 ft": "📦" if d.iso_40ft_konteyner else "",
        })
    st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch")


def _uyarilari_goster(uyarilar, varsayimlar=None):
    for u in uyarilar or []:
        if "yapılamadı" in u or "uygulanmadı" in u:
            st.warning(f"⚠️ {u}")
        elif "VARSAYIM" in u:
            st.info(f"🔎 {u}")
        else:
            st.caption(f"• {u}")
    for alan, metin in (varsayimlar or {}).items():
        st.info(f"🔎 **{alan}** — {metin}")


# ─────────────────────────────────────────────────────────────────────────────
# Çekici sekmesi
# ─────────────────────────────────────────────────────────────────────────────

def _cekici_formu(mevcut: Optional[Cekici]):
    v = mevcut or Cekici(cekici_id="", plaka="", bos_agirlik_kg=0.0)

    st.markdown("##### Zorunlu alanlar")
    c1, c2, c3 = st.columns(3)
    plaka = c1.text_input("Plaka", value=v.plaka, key="ck_plaka")
    marka = c2.text_input("Marka / model", value=v.marka_model, key="ck_marka")
    dingil = c3.number_input("Dingil sayısı", min_value=1, max_value=5,
                             value=int(v.dingil_sayisi or 2), key="ck_dingil",
                             help="4x2 → 2 · 6x2 / 6x4 → 3. "
                                  "44 t konteyner istisnası 3 dingil ister.")
    c4, c5 = st.columns(2)
    bos = c4.number_input("Boş ağırlık (kg)", min_value=0.0, step=10.0,
                          value=float(v.bos_agirlik_kg or 0), key="ck_bos")
    e_ofset = c5.number_input(
        "Beşinci teker ofseti · e (mm)", step=10.0,
        value=float(v.besinci_teker_ofset_mm or 0), key="ck_e",
        help="Beşinci tekerin TAHRİK DİNGİLİNE yatay uzaklığı. Beşinci "
             "teker dingilin ÖNÜNDE ise POZİTİF. Araç üzerinde "
             "ölçülebilir. Dingil kontrolünün sonucunu doğrudan etkiler: "
             "600 mm'de tam yük geçerli, 900 mm'de ön dingil aşılıyor.")

    st.markdown("##### Dingil kontrolü grubu")
    st.caption("Bu grup **ya tamamen doldurulur ya da tamamen boş bırakılır**. "
               "Boş bırakılırsa araç kaydedilir ama dingil kontrolü yapılamaz.")
    d1, d2, d3 = st.columns(3)
    bos_on = d1.number_input("Boş ön dingil (kg)", min_value=0.0, step=10.0,
                             value=float(v.bos_on_dingil_kg or 0), key="ck_bon")
    bos_arka = d2.number_input("Boş arka (tahrik) dingil (kg)", min_value=0.0,
                               step=10.0,
                               value=float(v.bos_arka_dingil_kg or 0),
                               key="ck_barka")
    wb = d3.number_input("Dingil mesafesi · WB (mm)", min_value=0.0, step=10.0,
                         value=float(v.dingil_mesafesi_mm or 0), key="ck_wb")
    d4, d5 = st.columns(2)
    on_izin = d4.number_input("Ön dingil izni (kg)", min_value=0.0, step=100.0,
                              value=float(v.on_dingil_izin_kg or 0),
                              key="ck_onizin",
                              help="Föydeki yasal ön dingil sınırı. "
                                   "KTY tahriksiz tek dingil 10.000 kg ile "
                                   "karşılaştırılır, küçüğü bağlar.")
    tahrik_izin = d5.number_input("Tahrik dingil izni (kg)", min_value=0.0,
                                  step=100.0,
                                  value=float(v.tahrik_dingil_izin_kg or 0),
                                  key="ck_tahrikizin",
                                  help="KTY tahrikli tek dingil 11.500 kg ile "
                                       "karşılaştırılır, küçüğü bağlar.")

    st.markdown("##### İsteğe bağlı")
    gcw = st.number_input("Teknik GCW (kg)", min_value=0.0, step=100.0,
                          value=float(v.teknik_gcw_kg or 0), key="ck_gcw",
                          help="Üreticinin kombinasyon için verdiği sınır. "
                               "Yasal toplamla karşılaştırılır, küçüğü bağlar.")

    yeni = Cekici(
        cekici_id=v.cekici_id or plaka,
        plaka=plaka.strip(),
        marka_model=marka,
        bos_agirlik_kg=float(bos),
        dingil_sayisi=int(dingil),
        besinci_teker_ofset_mm=float(e_ofset),
        bos_on_dingil_kg=_sayi_veya_none(bos_on),
        bos_arka_dingil_kg=_sayi_veya_none(bos_arka),
        on_dingil_izin_kg=_sayi_veya_none(on_izin),
        tahrik_dingil_izin_kg=_sayi_veya_none(tahrik_izin),
        dingil_mesafesi_mm=_sayi_veya_none(wb),
        teknik_gcw_kg=_sayi_veya_none(gcw),
        varsayim_alanlari=dict(v.varsayim_alanlari),
        kaynak_notlari=dict(v.kaynak_notlari),
    )

    eksik = yeni.eksik_dingil_alanlari()
    if not plaka.strip():
        # Boş formda uyarı yağdırmak yerine ne yapılacağını söyle
        st.caption("Plakayı girince alanlar doğrulanmaya başlar.")
    elif eksik:
        st.warning("⚠️ Dingil kontrolü **yapılamayacak** — eksik alanlar: "
                   + ", ".join(eksik))
    else:
        kap = yeni.kingpin_kapasitesi_kg()
        st.success(f"✅ Dingil kontrolü yapılabilir. Bu çekicinin "
                   f"kaldırabileceği en büyük kingpin yükü: "
                   f"**{kap:,.0f} kg**".replace(",", "."))
    _uyarilari_goster([], yeni.varsayim_alanlari)
    return yeni


# ─────────────────────────────────────────────────────────────────────────────
# Dorse sekmesi
# ─────────────────────────────────────────────────────────────────────────────

def _dorse_formu(mevcut: Optional[Dorse]):
    v = mevcut or Dorse(dorse_id="", plaka="", tip="tenteli",
                        ic_uzunluk_mm=0, ic_genislik_mm=0, ic_yukseklik_mm=0,
                        bos_agirlik_kg=0, dingil_sayisi=3)
    tipler = ["tenteli", "frigorifik", "kapalı kasa", "mega"]

    st.markdown("##### Zorunlu alanlar")
    c1, c2, c3 = st.columns(3)
    plaka = c1.text_input("Plaka", value=v.plaka, key="dr_plaka")
    tip = c2.selectbox("Tip", tipler,
                       index=tipler.index(v.tip) if v.tip in tipler else 0,
                       key="dr_tip")
    dingil = c3.number_input("Dingil sayısı", min_value=1, max_value=4,
                             value=int(v.dingil_sayisi or 3), key="dr_dingil")
    o1, o2, o3 = st.columns(3)
    ic_u = o1.number_input("İç uzunluk (mm)", min_value=0.0, step=10.0,
                           value=float(v.ic_uzunluk_mm or 0), key="dr_u")
    ic_g = o2.number_input("İç genişlik (mm)", min_value=0.0, step=10.0,
                           value=float(v.ic_genislik_mm or 0), key="dr_g")
    ic_y = o3.number_input("İç yükseklik (mm)", min_value=0.0, step=10.0,
                           value=float(v.ic_yukseklik_mm or 0), key="dr_y")
    bos = st.number_input("Boş ağırlık (kg)", min_value=0.0, step=10.0,
                          value=float(v.bos_agirlik_kg or 0), key="dr_bos")

    st.markdown("##### Dingil kontrolü grubu")
    st.caption("Bu grup **ya tamamen doldurulur ya da tamamen boş bırakılır**.")
    d1, d2, d3 = st.columns(3)
    aralik = d1.number_input("Dingil aralığı (mm)", min_value=0.0, step=10.0,
                             value=float(v.dingil_araligi_mm or 0),
                             key="dr_aralik",
                             help="KTY md.128 grup sınırını belirler. "
                                  "Üç dingilde: ≤1.300 → 21 t · "
                                  "1.300–1.400 → 24 t · >1.400 → KTY'de "
                                  "değer yok, föy değeri kullanılır.")
    grup_izin = d2.number_input("Dingil grubu izni (kg)", min_value=0.0,
                                step=100.0,
                                value=float(v.dingil_grubu_izin_kg or 0),
                                key="dr_grup")
    kingpin_izin = d3.number_input("Kingpin izni (kg)", min_value=0.0,
                                   step=100.0,
                                   value=float(v.kingpin_izin_kg or 0),
                                   key="dr_kingpin")
    k1, k2, k3 = st.columns(3)
    kp_kenar = k1.number_input(
        "Kingpin — ön DIŞ kenardan (mm)", min_value=0.0, step=10.0,
        value=float(v.kingpin_on_kenar_mesafe_mm or 0), key="dr_kpkenar",
        help="Föydeki değer (örn. 'king pin, position 1690 mm, acc. to SAE'). "
             "Dış kenardan ölçülür.")
    duvar = k2.number_input("Ön duvar kalınlığı (mm)", min_value=0.0, step=5.0,
                            value=float(v.on_duvar_kalinligi_mm or 0),
                            key="dr_duvar",
                            help="Motorun ekseni İÇ ön duvardan başlar. "
                                 "c = kingpin mesafesi − duvar kalınlığı.")
    kp_grup = k3.number_input(
        "Kingpin → dingil grubu (mm)", min_value=0.0, step=10.0,
        value=float(v.kingpin_dingil_grubu_mesafe_mm or 0), key="dr_kpgrup",
        help="Föyde genelde 'wheelbase' olarak geçer; kingpin ile dingil "
             "grubunun ORTA dingili arası.")

    st.markdown("##### Boş ağırlığın paylaşımı (isteğe bağlı)")
    st.caption("Boş bırakılırsa ağırlık merkezi yük alanının ORTASINDA "
               "varsayılır ve uyarı gösterilir.")
    b1, b2 = st.columns(2)
    bos_kp = b1.number_input("Boş — kingpin payı (kg)", min_value=0.0,
                             step=10.0,
                             value=float(v.bos_kingpin_payi_kg or 0),
                             key="dr_boskp")
    bos_grup = b2.number_input("Boş — dingil grubu payı (kg)", min_value=0.0,
                               step=10.0,
                               value=float(v.bos_dingil_grubu_payi_kg or 0),
                               key="dr_bosgrup")

    st.markdown("##### İsteğe bağlı")
    i1, i2 = st.columns(2)
    teknik = i1.number_input("Teknik azami ağırlık (kg)", min_value=0.0,
                             step=100.0,
                             value=float(v.teknik_azami_kg or 0),
                             key="dr_teknik")
    konteyner = i2.checkbox(
        "40 ft ISO konteyner taşıyor", value=bool(v.iso_40ft_konteyner),
        key="dr_konteyner",
        help="44 t istisnası YALNIZCA bu işaretliyse VE çekici 3 dingilliyse "
             "uygulanır (KTY md.128).")

    yeni = Dorse(
        dorse_id=v.dorse_id or plaka,
        plaka=plaka.strip(),
        tip=tip,
        ic_uzunluk_mm=float(ic_u), ic_genislik_mm=float(ic_g),
        ic_yukseklik_mm=float(ic_y),
        bos_agirlik_kg=float(bos),
        dingil_sayisi=int(dingil),
        dingil_araligi_mm=_sayi_veya_none(aralik),
        dingil_grubu_izin_kg=_sayi_veya_none(grup_izin),
        kingpin_izin_kg=_sayi_veya_none(kingpin_izin),
        kingpin_on_kenar_mesafe_mm=_sayi_veya_none(kp_kenar),
        on_duvar_kalinligi_mm=float(duvar),
        kingpin_dingil_grubu_mesafe_mm=_sayi_veya_none(kp_grup),
        bos_kingpin_payi_kg=_sayi_veya_none(bos_kp),
        bos_dingil_grubu_payi_kg=_sayi_veya_none(bos_grup),
        bos_payi_kaynagi="elle" if (bos_kp and bos_grup) else "",
        teknik_azami_kg=_sayi_veya_none(teknik),
        iso_40ft_konteyner=bool(konteyner),
        varsayim_alanlari=dict(v.varsayim_alanlari),
        kaynak_notlari=dict(v.kaynak_notlari),
    )

    # ── Hesaplanan değerler ────────────────────────────────────────────
    if ic_u and ic_g and ic_y:
        m1, m2 = st.columns(2)
        m1.metric("İç hacim (hesaplanır)", f"{yeni.ic_hacim_m3:.1f} m³")
        m2.metric("Motordaki ölçü (cm)",
                  f"{mm_to_cm(ic_g)}×{mm_to_cm(ic_u)}×{mm_to_cm(ic_y)}",
                  help="mm → cm aşağı yuvarlanır; araç gerçeğinden büyük "
                       "görünmez (karar S10).")
    if yeni.c_mm is not None:
        st.caption(f"Kingpinin iç ön duvara uzaklığı: **c = "
                   f"{yeni.c_mm:,.0f} mm** ({kp_kenar:,.0f} − {duvar:,.0f})"
                   .replace(",", "."))

    eksik = yeni.eksik_dingil_alanlari()
    if not plaka.strip():
        st.caption("Plakayı girince alanlar doğrulanmaya başlar.")
    elif eksik:
        st.warning("⚠️ Dingil kontrolü **yapılamayacak** — eksik alanlar: "
                   + ", ".join(eksik))
    _uyarilari_goster(yeni.tutarlilik_uyarilari(), yeni.varsayim_alanlari)
    if yeni.dingil_sayisi and yeni.dingil_araligi_mm:
        _deger, _kaynak, _uy = yeni.dingil_grubu_siniri_kg()
        if _deger:
            st.caption(f"Bağlayan dingil grubu sınırı: **{_deger:,.0f} kg** "
                       f"— {_kaynak}".replace(",", "."))
        _uyarilari_goster(_uy)
    return yeni


# ─────────────────────────────────────────────────────────────────────────────
# Eşleşme önizlemesi
# ─────────────────────────────────────────────────────────────────────────────

def _excel_sekmesi(cekiciler: List[Cekici], dorseler: List[Dorse]) -> None:
    """Excel'den toplu çekici/dorse ekleme (optimizasyon sayfasının eşi).

    Şablon statik bir dosya değil, `filo_excel.sablon_uret()` ile anında
    üretiliyor — veri modeline alan eklenince şablon kendiliğinden güncel
    kalsın diye.
    """
    import filo_excel as fx

    st.subheader("📊 Excel ile toplu ekleme")

    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown("**1. Şablonu indir**")
        st.caption("Boş şablon + örnek sayfa + her sütunun açıklaması.")
        try:
            st.download_button(
                "⬇️ Boş şablonu indir", data=fx.sablon_uret(),
                file_name="loadplan_filo_sablonu.xlsx",
                mime=("application/vnd.openxmlformats-officedocument"
                      ".spreadsheetml.sheet"),
                type="primary", width="stretch", key="filo_sablon_indir")
        except Exception as e:                               # noqa: BLE001
            st.error(f"Şablon üretilemedi: {e}")

        if cekiciler or dorseler:
            st.markdown("**Mevcut filoyu dışa aktar**")
            st.caption("Aynı biçimde; düzenleyip geri yükleyebilirsiniz.")
            try:
                st.download_button(
                    "⬇️ Mevcut filoyu indir",
                    data=fx.disa_aktar(cekiciler, dorseler),
                    file_name="loadplan_filo.xlsx",
                    mime=("application/vnd.openxmlformats-officedocument"
                          ".spreadsheetml.sheet"),
                    width="stretch", key="filo_disa_aktar")
            except Exception as e:                           # noqa: BLE001
                st.error(f"Dışa aktarılamadı: {e}")

    with c2:
        st.markdown("**2. Doldurulmuş dosyayı yükle**")
        st.caption(f"'{fx.SAYFA_CEKICI}' ve '{fx.SAYFA_DORSE}' sayfaları "
                   f"okunur. Bilinmeyen alanı **boş bırakın** — tahmini "
                   f"değer yazmayın.")
        dosya = st.file_uploader("Excel dosyası seç", type=["xlsx", "xls"],
                                 key="filo_excel_yukle",
                                 label_visibility="collapsed")

    if dosya is None:
        return

    with st.spinner("Excel okunuyor…"):
        yeni_ck, yeni_dr, hatalar, uyarilar = fx.oku(dosya.read())

    for h in hatalar:
        st.error(f"❌ {h}")
    for u in uyarilar:
        st.warning(f"⚠️ {u}")

    if not yeni_ck and not yeni_dr:
        st.info("Eklenecek kayıt bulunamadı.")
        return

    # ── Önizleme ────────────────────────────────────────────────────────
    st.markdown("##### Okunan kayıtlar")
    if yeni_ck:
        st.caption(f"🚛 {len(yeni_ck)} çekici")
        _cekici_listesi(yeni_ck)
    if yeni_dr:
        st.caption(f"🚍 {len(yeni_dr)} dorse")
        _dorse_listesi(yeni_dr)

    # ── Mevcut verilerle ne yapılsın? (yük yükleme akışındaki gibi) ─────
    mevcut = {c.plaka for c in cekiciler} | {d.plaka for d in dorseler}
    cakisan = sorted(
        {k.plaka for k in list(yeni_ck) + list(yeni_dr)} & mevcut)

    st.markdown("##### Mevcut filoyla ne yapılsın?")
    kip = st.radio(
        "Mevcut filoyla ne yapılsın?",
        ["➕ Mevcut filoya ekle",
         "🔄 Üzerine yaz (mevcut filoyu temizle)"],
        horizontal=True, key="filo_excel_kip", label_visibility="collapsed")
    uzerine_yaz = kip.startswith("🔄")

    if uzerine_yaz:
        st.warning(
            f"⚠️ Kayıtlı **{len(cekiciler)} çekici ve {len(dorseler)} "
            f"dorse pasife alınacak**, yerine dosyadaki "
            f"{len(yeni_ck) + len(yeni_dr)} kayıt gelecek. Kayıtlar "
            f"silinmez, pasife alınır — eski planların hangi araçla "
            f"yapıldığı korunur.")
    elif cakisan:
        st.warning("⚠️ Bu plakalar zaten kayıtlı, **üzerine yazılacak**: "
                   + ", ".join(cakisan))

    if st.button("✅ Uygula", type="primary", key="filo_excel_uygula"):
        if uzerine_yaz:
            for c in cekiciler:
                _pasife_al("cekici", c.plaka)
            for d in dorseler:
                _pasife_al("dorse", d.plaka)
        eklenen, basarisiz = 0, []
        for kayit in yeni_ck:
            hata = _cekici_kaydet(kayit)
            if hata:
                basarisiz.append(f"{kayit.plaka}: {hata}")
            else:
                eklenen += 1
        for kayit in yeni_dr:
            hata = _dorse_kaydet(kayit)
            if hata:
                basarisiz.append(f"{kayit.plaka}: {hata}")
            else:
                eklenen += 1
        for b in basarisiz:
            st.error(f"❌ {b}")
        if eklenen:
            st.success(f"✅ {eklenen} kayıt eklendi/güncellendi.")
            st.rerun()


def _otomatik_eslestirme(cekiciler: List[Cekici], dorseler: List[Dorse]):
    """Sistemin yapacağı eşleştirme + neden böyle olduğu.

    Eşleştirme ELLE YAPILMAZ ve Excel'de de bir sütunu yoktur: çekici ve
    dorse kayıtları girilir, eşleştirmeyi sistem kurala göre yapar
    (karar C). Bu tablo o kararı görünür kılar.
    """
    from filo_havuzu import ACMA_SIRASI, eslestirme_dokumu

    st.subheader("🔗 Sistemin yaptığı eşleştirme")
    st.caption(
        "Eşleştirmeyi **sistem** yapar; elle ya da Excel'den "
        "belirlenmez. Kural (karar C): **1)** en yüksek faydalı yük → "
        "**2)** eşitse en geniş dingil payı → **3)** hâlâ eşitse liste "
        "sırası (plakaya göre). Dorseler hacme göre "
        f"{'büyükten küçüğe' if ACMA_SIRASI == 'buyukten_kucuge' else 'küçükten büyüğe'} "
        "sıraya dizilir.")

    dokum = eslestirme_dokumu(cekiciler, dorseler)
    satirlar = []
    for s in dokum:
        satirlar.append({
            "Çekici": s["cekici"].plaka if s["cekici"] else "— yok —",
            "Dorse": s["dorse"].plaka,
            "Hacim (m³)": round(s["dorse"].ic_hacim_m3, 1),
            "Faydalı yük (kg)": (int(s["faydali_yuk_kg"])
                                 if s["faydali_yuk_kg"] else "—"),
            "Neden bu çekici?": s["neden"],
        })
    st.dataframe(pd.DataFrame(satirlar), hide_index=True, width="stretch")

    if all("liste sırası" in s["neden"] for s in dokum if s["cekici"]):
        st.info("ℹ️ Bu filodaki çekicilerin hepsi birbirinin aynı (aynı "
                "faydalı yük, aynı dingil payı), dorseler de aynı. Bu "
                "yüzden kuralın ilk iki ölçütü eşit çıkıyor ve eşleştirme "
                "**plaka sırasına** göre yapılıyor. Farklı modeller "
                "girerseniz ilk ölçüt devreye girer.")
    st.markdown("---")


def _eslesme_onizleme(cekiciler: List[Cekici], dorseler: List[Dorse]):
    _otomatik_eslestirme(cekiciler, dorseler)

    st.subheader("🔍 Tek tek incele")
    st.caption("Aşağıdaki seçim YALNIZCA inceleme içindir; eşleştirmeyi "
               "değiştirmez.")
    if not cekiciler or not dorseler:
        st.info("İnceleme için en az bir çekici ve bir dorse kaydı gerekli.")
        return

    c1, c2 = st.columns(2)
    ck = c1.selectbox("Çekici", cekiciler,
                      format_func=lambda c: f"{c.plaka} — {c.marka_model}",
                      key="es_ck")
    dr = c2.selectbox("Dorse", dorseler,
                      format_func=lambda d: f"{d.plaka} — {d.tip}",
                      key="es_dr")

    es = eslesme_hesapla(ck, dr)
    m1, m2, m3 = st.columns(3)
    m1.metric("Yasal toplam", f"{es.yasal_toplam_kg:,.0f} kg".replace(",", "."))
    m2.metric("Faydalı yük", f"{es.faydali_yuk_kg:,.0f} kg".replace(",", "."))
    m3.metric("İç hacim", f"{dr.ic_hacim_m3:.1f} m³")
    st.caption(f"**Uygulanan sınırın kaynağı:** {es.yasal_toplam_kaynak}")
    st.info(es.faydali_yuk_aciklamasi())

    s = es.dingil_sinirlari
    st.markdown("**Dingil sınırları**")
    st.table({
        "Sınır": ["ön dingil", "tahrik dingili", "kingpin", "dingil grubu",
                  "toplam"],
        "kg": [f"{s.on_dingil_kg:,.0f}", f"{s.tahrik_dingil_kg:,.0f}",
               f"{s.kingpin_kg:,.0f}" if s.kingpin_kg else "—",
               f"{s.dingil_grubu_kg:,.0f}" if s.dingil_grubu_kg else "—",
               f"{s.toplam_kg:,.0f}"],
        "Kaynak": [s.kaynaklar.get("on_dingil", ""),
                   s.kaynaklar.get("tahrik_dingil", ""),
                   s.kaynaklar.get("kingpin", ""),
                   s.kaynaklar.get("dingil_grubu", ""),
                   s.kaynaklar.get("toplam", "")],
    })
    _uyarilari_goster(es.uyarilar)


# ─────────────────────────────────────────────────────────────────────────────
# Sayfa
# ─────────────────────────────────────────────────────────────────────────────

def render():
    st.title("🚚 Filo")
    st.caption("Çekici ve dorse ayrı varlıklardır (karar V-B). Kütle "
               "kapasitesi KTY md.128'den **hesaplanır**, elle girilmez.")

    cekiciler = _cekici_kayitlari()
    dorseler = _dorse_kayitlari()

    # ── Tek bakışta durum ───────────────────────────────────────────────
    if cekiciler or dorseler:
        # Özet KAYITLI filoyu anlatır (o anki seçimi değil) — yoksa
        # "1 çekici, 1 dorse ama 0 sefer" gibi yanıltıcı bir tablo çıkar.
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Çekici", len(cekiciler))
        m2.metric("Dorse", len(dorseler))
        _sefer = min(len(cekiciler), len(dorseler))
        m3.metric("Olası sefer", _sefer,
                  help="Her çekici en çok bir sefer yapar; sefer sayısı "
                       "çekici ve dorse sayısının küçüğüyle sınırlıdır.")
        if _sefer:
            from filo_havuzu import havuz_olustur_cekici_dorse
            _toplam = sum(t.capacity for t in
                          havuz_olustur_cekici_dorse(cekiciler,
                                                     dorseler).trucks)
            m4.metric("Toplam faydalı yük",
                      f"{_toplam:,.0f} kg".replace(",", "."))
        else:
            m4.metric("Toplam faydalı yük", "—",
                      help="Hem çekici hem dorse kaydı gerekir.")

        # ── Bu filo optimizasyonda kullanılıyor mu? ──────────────────────
        if eski_tablo_mu():
            u1, u2 = st.columns([3, 1])
            u1.warning("Bu filo şu anda **kullanılmıyor** — optimizasyon "
                       "kenar çubuğundaki eski araç tablosuyla çalışıyor.")
            if u2.button("✅ Bu filoyu kullan", type="primary",
                         width="stretch", key="ust_filoya_gec"):
                secimi_kaydet([c.plaka for c in cekiciler],
                              [d.plaka for d in dorseler])
                st.rerun()
        elif _sefer:
            st.success("✅ Bu filo optimizasyonda **kullanılıyor**.")

        if len(dorseler) > len(cekiciler):
            st.warning(f"⚠️ {len(dorseler) - len(cekiciler)} dorse için boş "
                       f"çekici yok → o dorseler sefer yapamaz.")
        st.markdown("---")

    if not cekiciler and not dorseler:
        st.info("Filo boş. Örnek filoyu yükleyerek başlayabilirsiniz "
                "(Ford F-MAX 4x2 + Schmitz SCS 24/L).")
        if st.button("📥 Örnek filoyu yükle", type="primary"):
            _cekici_kaydet(ford_fmax_4x2())
            _dorse_kaydet(schmitz_scs_24l())
            st.success("Örnek filo eklendi.")
            st.rerun()

    t1, t2, t3, t4 = st.tabs([f"🚛 Çekiciler ({len(cekiciler)})",
                              f"🚍 Dorseler ({len(dorseler)})",
                              "🔗 Eşleşme",
                              "📊 Excel"])

    # ── Çekiciler ───────────────────────────────────────────────────────
    with t1:
        _cekici_listesi(cekiciler)
        st.markdown("---")
        secenekler = ["➕ Yeni çekici"] + [c.plaka for c in cekiciler]
        secim = st.selectbox("Kayıt", secenekler, key="ck_secim")
        mevcut = next((c for c in cekiciler if c.plaka == secim), None)
        yeni = _cekici_formu(mevcut)

        b1, b2 = st.columns(2)
        if b1.button("💾 Kaydet", type="primary", key="ck_kaydet"):
            if not yeni.plaka:
                st.error("Plaka zorunlu.")
            elif yeni.bos_agirlik_kg <= 0:
                st.error("Boş ağırlık zorunlu.")
            else:
                hata = _cekici_kaydet(yeni)
                if hata:
                    st.error(hata)
                else:
                    st.success(f"✅ {yeni.plaka} kaydedildi.")
                    st.rerun()
        if mevcut and b2.button("🗑️ Pasife al", key="ck_sil"):
            _pasife_al("cekici", mevcut.plaka)
            st.success(f"{mevcut.plaka} pasife alındı (kayıt silinmedi).")
            st.rerun()

    # ── Dorseler ────────────────────────────────────────────────────────
    with t2:
        _dorse_listesi(dorseler)
        st.markdown("---")
        secenekler = ["➕ Yeni dorse"] + [d.plaka for d in dorseler]
        secim = st.selectbox("Kayıt", secenekler, key="dr_secim")
        mevcut = next((d for d in dorseler if d.plaka == secim), None)
        yeni = _dorse_formu(mevcut)

        b1, b2 = st.columns(2)
        if b1.button("💾 Kaydet", type="primary", key="dr_kaydet"):
            if not yeni.plaka:
                st.error("Plaka zorunlu.")
            elif not (yeni.ic_uzunluk_mm and yeni.ic_genislik_mm
                      and yeni.ic_yukseklik_mm):
                st.error("İç ölçüler zorunlu.")
            elif yeni.bos_agirlik_kg <= 0:
                st.error("Boş ağırlık zorunlu.")
            else:
                hata = _dorse_kaydet(yeni)
                if hata:
                    st.error(hata)
                else:
                    st.success(f"✅ {yeni.plaka} kaydedildi.")
                    st.rerun()
        if mevcut and b2.button("🗑️ Pasife al", key="dr_sil"):
            _pasife_al("dorse", mevcut.plaka)
            st.success(f"{mevcut.plaka} pasife alındı (kayıt silinmedi).")
            st.rerun()

    # ── Excel ───────────────────────────────────────────────────────────
    with t4:
        _excel_sekmesi(cekiciler, dorseler)

    # ── Eşleşme ─────────────────────────────────────────────────────────
    with t3:
        _eslesme_onizleme(cekiciler, dorseler)

        st.markdown("---")
        st.subheader("🚀 Optimizasyonda kullan")
        st.caption("Seçilen çekici ve dorseler bir TAVAN oluşturur; hangi "
                   "araçların açılacağına algoritma karar verir (karar K4). "
                   "Her çekici en çok bir sefer yapar.")
        if cekiciler and dorseler:
            sec_ck = st.multiselect("Çekiciler", [c.plaka for c in cekiciler],
                                    default=[c.plaka for c in cekiciler],
                                    key="kullan_ck")
            sec_dr = st.multiselect("Dorseler", [d.plaka for d in dorseler],
                                    default=[d.plaka for d in dorseler],
                                    key="kullan_dr")
            if st.button("✅ Bu filoyu optimizasyonda kullan", type="primary"):
                secimi_kaydet(sec_ck, sec_dr)
                st.success(
                    f"✅ {len(sec_ck)} çekici + {len(sec_dr)} dorse seçildi. "
                    f"Optimizasyon sayfasında bu filo kullanılacak. "
                    f"(Seçim kalıcıdır, sayfa yenilense de korunur.)")

        if eski_tablo_mu():
            st.warning("Şu anda **eski araç tablosu** kullanılıyor. "
                       "Yukarıdaki düğmeyle bu filoya geçebilirsiniz.")
        else:
            _ck_a, _dr_a = aktif_filo()
            if _ck_a and _dr_a:
                st.caption(f"Şu anda kullanılan filo: **{len(_ck_a)} çekici, "
                           f"{len(_dr_a)} dorse**.")
                if st.button("↩️ Eski araç tablosuna dön"):
                    eski_tablo_ayarla(True)
                    st.rerun()
