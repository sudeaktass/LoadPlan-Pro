# 📦 LoadPlan Pro

**3B Konteyner / Palet Yükleme Optimizasyonu için Karar Destek Sistemi**

LoadPlan Pro, farklı boyut, ağırlık ve kısıtlara sahip yükleri araçlara/konteynerlere **en verimli ve fiziksel olarak uygulanabilir** biçimde yerleştiren bir 3B Bin-Packing (3D-KPP) optimizasyon aracıdır. Yedi algoritmayı aynı çatı altında karşılaştırmalı olarak sunar; sonuçları etkileşimli 3B görselleştirme, Excel/PDF raporları ve sürücü yükleme talimatlarıyla destekler.

> Streamlit tabanlı web arayüzü · 7 algoritma · çok kısıtlı yerleştirme · ortak amaç fonksiyonu · alt-sınır (optimallik açığı) analizi · bağımsız olurluluk doğrulaması

---

## ✨ Özellikler

- **7 optimizasyon algoritması** — yapıcı sezgiseller + metasezgiseller (aşağıda)
- **Manuel & Karşılaştırmalı mod** — tek algoritma çalıştır ya da hepsini yan yana kıyasla
- **Otomatik Araç Seçimi** — filodan en uygun araç kombinasyonunu bulur
- **Çok-kısıtlı yerleştirme** — ağırlık kapasitesi, boyut, istif, ağırlık merkezi (CoG), öncelik/LIFO, minimum aralık, rotasyon
- **Etkileşimli 3B görselleştirme** (Plotly) — araç bazlı yerleşim, ağırlık merkezi, kapı yönü
- **Excel içe/dışa aktarım** — araç ve yük listeleri
- **STL / STEP içe aktarım** (SolidWorks) — gerçek CAD geometrisiyle yerleştirme
- **PDF & Excel raporları** — Türkçe karakter destekli, kurumsal formatlı
- **Sürücü Yükleme Talimatı** — sıra numaralı, QR kodlu yükleme kılavuzu
- **Alt-sınır & optimallik açığı** — "çözüm optimuma ne kadar yakın?" ölçümü
- **Çok kullanıcılı** — kimlik doğrulama, rol tabanlı yetki (admin/manager/operator)
- **Doğrulama araçları** — algoritma uygunluk testi, deney koşumu, olurluluk doğrulayıcı

---

## 🧠 Algoritmalar

### Yapıcı Sezgiseller (constructive)
| Algoritma | Yaklaşım | Referans |
|-----------|----------|----------|
| **FFD** (Best-Fit Decreasing) | Çevrimdışı, azalan boyut + best-fit araç seçimi | Johnson (1973) |
| **Greedy** (Online Best-Fit) | Çevrimiçi, sıralama yok, en dolu uygun araç | Johnson (1973) |
| **Layer Building** | Duvar-inşa / katman tabanlı istifleme | George & Robinson (1980) |

### Metasezgiseller (metaheuristic)
| Algoritma | Paradigma | Referans |
|-----------|-----------|----------|
| **Tabu Search** | Bellek tabanlı yerel arama (tabu + frekans) | Glover & Laguna (1997) |
| **Simulated Annealing** | Fiziksel tavlama + Metropolis kabul | Kirkpatrick (1983) |
| **Genetic Algorithm** | Evrimsel (OX1 çaprazlama, indeks kodlama) | Holland (1975) |
| **Monte Carlo (RCS)** | Rastgele yapıcı arama + importance sampling | Rubinstein & Kroese (2004) |

Tüm metasezgiseller **ortak Extreme Points (EP) yerleştirme motorunu** ve **ortak amaç fonksiyonunu** kullanır — adil karşılaştırma için. (Crainic, Perboli & Tadei, 2008)

### Dondurulmuş varyantlar (karar A)

**Island GA**, **Multi-Start SA** ve **Bayesian Optimization** yerleştirme
algoritması olarak **kullanılmaz**: kullanıcıya açık seçim listelerinden,
açıklama kartından, `run_algo` sevk tablosundan ve varsayılan orkestrasyon
boru hattından çıkarıldılar.

Kodları **silinmedi** — `island_genetic_3d.py`, `multistart_sa_3d.py` ve
`bayesian_optimizer_3d.py` olduğu gibi duruyor ve varyant analizi için
doğrudan import edilip çağrılabilir (`deney/scripts/algoritma_denetimi.py`
bunu yapar).

---

## 🎯 Ortak Amaç Fonksiyonu

Beş metasezgisel aynı hedefi optimize eder (`amac_fonksiyonu.py`). Dört
düzey; üstteki alttakini **her zaman** yener:

1. **Geçersizlik** — yerleşmeyen parça, filo tavanı aşımı, dingil yükü ihlali
   (Deb 2000 kısıt-baskın kuralı)
2. **Araç sayısı** — az sefer her zaman iyidir (K1'in birinci ölçütü)
3. **Ağırlık merkezi toleransı** — yanal %10 · boylamsal %15 · dikey %60
4. **Sürekli ölçütler** — doluluk (Falkenauer 1996 biçimi) · öncelik · CoG

---

## 🚀 Kurulum

```bash
# 1. Depoyu klonlayın / dosyaları indirin
cd loadplan_pro

# 2. Sanal ortam (önerilir)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Bağımlılıkları kurun
pip install -r requirements.txt

# 4. (Opsiyonel) İleri özellikler
pip install scipy               # deneysel analiz (Friedman/Wilcoxon)
pip install optuna              # Bayesian Optimization (dondurulmuş varyant)
pip install "qrcode[pil]"       # Sürücü talimatı QR kodları
```

**Ana bağımlılıklar:** `streamlit · plotly · matplotlib · pandas · numpy · reportlab · openpyxl · sqlalchemy · bcrypt · trimesh · shapely`

> `matplotlib` zorunludur — `app_3d.py` backend'i sabitlemek için onu
> koşulsuz import eder. `requirements.txt` ile birlikte kurulur.

---

## ▶️ Kullanım

```bash
streamlit run app_3d.py
```

Tarayıcıda `http://localhost:8501` açılır.

**Tipik akış:**
1. **Araç Filosu** — sidebar'dan araçları tanımlayın (veya Excel'den içe aktarın)
2. **Yük Listesi** — parçaları girin: boyut, ağırlık, adet, kısıtlar (kırılgan, öncelik, vb.)
3. **Algoritma** — Tek mod (bir algoritma) veya Karşılaştırmalı mod (çoklu)
4. **Çalıştır** — sonuçları 3B görselde inceleyin
5. **Rapor** — PDF/Excel indirin veya sürücü talimatı üretin

---

## 📁 Proje Yapısı

```
├── app_3d.py                  # Ana Streamlit uygulaması (UI + akış)
├── core_3d.py                 # Veri modelleri, geometri, kısıtlar, ortak amaç fonksiyonu
├── extreme_points_3d.py       # EP yerleştirme motoru (ortak decoder)
├── maxrects_3d.py             # MaxRects yerleştirme motoru (alternatif)
│
├── ffd_3d.py                  # FFD (Best-Fit Decreasing)
├── greedy_3d.py               # Greedy (Online Best-Fit)
├── layer_building_3d.py       # Layer Building
├── tabu_search_3d.py          # Tabu Search
├── simulated_annealing_3d.py  # Simulated Annealing
├── genetic_3d.py              # Genetic Algorithm
├── island_genetic_3d.py       # Island GA
├── monte_carlo_3d.py          # Monte Carlo (RCS)
├── multistart_sa_3d.py        # Multi-Start SA
├── bayesian_optimizer_3d.py   # Bayesian Optimization (TPE)
│
├── amac_fonksiyonu.py         # ORTAK AMAÇ FONKSİYONU (tek kaynak)
├── doluluk.py                 # Doluluk ölçüleri: hacim (U_G) + ağırlık (U_W)
├── agirlik_dagilimi.py        # Ağırlık merkezi & yayılma ölçümü (cm)
├── yukleme_sirasi.py          # Yükleme sırası (sürücü talimatı + 3B rozetler)
│
├── filo_modeli.py             # Çekici + dorse veri modeli (KTY md.128)
├── filo_havuzu.py             # Ortak araç açma (filo = tavan)
├── filo_sayfasi.py            # 🚚 Filo sayfası (arayüz)
├── filo_excel.py              # Filo için Excel şablon / içe-dışa aktarım
├── filo_secimi.py             # Kalıcı filo seçimi
├── dingil_yuku.py             # Dingil yükü hesabı (Pollaris kaldıraç kuralı)
├── mevzuat_kty.py             # Karayolları Taşıma Yönetmeliği sınırları
├── palet_kutuphanesi.py       # Standart palet kütüphanesi (EUR/EPAL, ISO 6780)
├── ornek_filo.py              # Örnek araç tanımları
│
├── fleet_optimizer_3d.py      # Otomatik araç seçimi
├── bounds_3d.py               # Alt-sınır & optimallik açığı
├── priority_utils.py          # Öncelik/LIFO bölge yönetimi
├── nfp_engine.py              # NFP nesting (düzensiz şekiller)
├── shape_engine.py            # STL/STEP şekil işleme
│
├── plotly_3d.py               # 3B görselleştirme
├── reports.py                 # PDF & Excel raporları
├── database.py · auth.py      # Kalıcılık & kullanıcı yönetimi
│
├── test_algoritma_uygunlugu.py  # Algoritma uygunluk testi (conformance)
├── deney_kosumu.py            # Karşılaştırmalı deney altyapısı (istatistik)
└── dogrula_cozum.py           # Bağımsız olurluluk doğrulayıcı
```

---

## 🔒 Uygulanan Kısıtlar

- **Ağırlık kapasitesi** — araç yük sınırı (bağlayıcı kısıt)
- **Boyutsal uyum** — en/boy/yükseklik + rotasyon
- **İstif kuralları** — "altına yük konmaz" (zemine oturur), "üstüne yük konmaz" (kırılgan)
- **Destek oranı** — havadaki parça için minimum **%80** destekli taban
- **Ağırlık merkezi (CoG)** — yanal/boylamsal denge cezası
- **Öncelik / LIFO** — teslimat önceliği (kapıya yakın = son yüklenen)
- **Minimum aralık** — parçalar arası güvenlik boşluğu

---

## ✅ Doğrulama & Geçerleme (V&V)

```bash
python -m pytest -q                        # Birim + davranış testleri (474 test)
python test_algoritma_uygunlugu.py         # Algoritmalar kanonik tanımına uyuyor mu? (27 test)
python dogrula_cozum.py                    # Çözümler fiziksel olarak olurlu mu?
python deney_kosumu.py                     # Karşılaştırmalı deney + Friedman/Wilcoxon + gap
python deney/scripts/algoritma_denetimi.py --n 2 --butce 4
                                           # Parmak izi · tohumlu/tohumsuz · tohuma göre kayıp
```

Testler `deney/` altındaki kıyas kümelerini (Bischoff & Ratcliff 1995;
Davies & Bischoff 1999; Loh & Nee 1992; Ivancic vd. 1989) kullanır.

---

## 🛠️ Teknoloji Yığını

- **Arayüz:** Streamlit
- **Görselleştirme:** Plotly (3B), Matplotlib
- **Veri:** pandas, NumPy, SciPy
- **Optimizasyon:** özel algoritma implementasyonları (Optuna yalnız dondurulmuş BO varyantında)
- **Geometri/CAD:** trimesh, Shapely (STL/STEP, NFP nesting)
- **Raporlama:** ReportLab (PDF), openpyxl (Excel), qrcode
- **Kalıcılık:** SQLAlchemy (SQLite/PostgreSQL), bcrypt

---

## 📊 Değerlendirme Metrikleri

| Metrik | Açıklama |
|--------|----------|
| **Doluluk oranı** | Kullanılan hacim / toplam araç hacmi |
| **Fire hacmi** | Boşa giden hacim (m³) |
| **Hesaplama süresi** | Algoritma çalışma süresi |
| **Alt-sınır açığı** | Çözümün kanıtlanabilir optimuma uzaklığı |
| **Araç sayısı** | Kullanılan araç adedi |

---

## 📄 Lisans

Akademik/eğitim amaçlı geliştirilmiştir. Ticari kullanım için iletişime geçiniz.

---

*Endüstri mühendisliği bakış açısıyla değerlendirme için bkz. [`README_Endustri_Muhendisligi.md`](README_Endustri_Muhendisligi.md)*
