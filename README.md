# 📦 LoadPlan Pro

**3B Konteyner / Palet Yükleme Optimizasyonu için Karar Destek Sistemi**

LoadPlan Pro, farklı boyut, ağırlık ve kısıtlara sahip yükleri araçlara/konteynerlere **en verimli ve fiziksel olarak uygulanabilir** biçimde yerleştiren bir 3B Bin-Packing (3D-KPP) optimizasyon aracıdır. On farklı algoritmayı aynı çatı altında karşılaştırmalı olarak sunar; sonuçları etkileşimli 3B görselleştirme, Excel/PDF raporları ve sürücü yükleme talimatlarıyla destekler.

> Streamlit tabanlı web arayüzü · 10 algoritma · çok kısıtlı yerleştirme · alt-sınır (optimallik açığı) analizi · bağımsız olurluluk doğrulaması

---

## ✨ Özellikler

- **10 optimizasyon algoritması** — yapıcı sezgiseller + metasezgiseller (aşağıda)
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
| **Island GA** | Paralel ada modeli + halka göçü | Tanese (1989) |
| **Monte Carlo (RCS)** | Rastgele yapıcı arama + importance sampling | Rubinstein & Kroese (2004) |
| **Multi-Start SA** | Çeşitlendirilmiş çoklu başlangıç + SA | Martí (2003) |
| **Bayesian Optimization** | TPE vekil model (hiperparametre ayarı) | Bergstra vd. (2011) |

Tüm metasezgiseller **ortak Extreme Points (EP) yerleştirme motorunu** ve **ortak amaç fonksiyonunu** kullanır — adil karşılaştırma için. (Crainic, Perboli & Tadei, 2008)

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
pip install optuna              # Bayesian Optimization
pip install "qrcode[pil]"       # Sürücü talimatı QR kodları
```

**Ana bağımlılıklar:** `streamlit · plotly · pandas · numpy · reportlab · openpyxl · sqlalchemy · bcrypt · trimesh · shapely`

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
python test_algoritma_uygunlugu.py   # Algoritmalar kanonik tanımlarına uyuyor mu? (27 test)
python dogrula_cozum.py              # Çözümler fiziksel olarak olurlu mu? (bağımsız kontrol)
python deney_kosumu.py               # Karşılaştırmalı deney + Friedman/Wilcoxon + gap
```

---

## 🛠️ Teknoloji Yığını

- **Arayüz:** Streamlit
- **Görselleştirme:** Plotly (3B), Matplotlib
- **Veri:** pandas, NumPy, SciPy
- **Optimizasyon:** özel algoritma implementasyonları + Optuna (TPE)
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
