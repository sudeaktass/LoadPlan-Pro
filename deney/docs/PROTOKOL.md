# Deney Protokolü — Pilot Geometri Veri Seti

Bu klasör, danışman raporunda **"ilk 10 iş günü görev paketi"** olarak tanımlanan
dört çıktıdan üçüncü ve dördüncüsüne karşılık gelir:

> *(3) ortak seed ve deney konfigürasyonu, (4) 30 örnekli pilot geometri veri seti*

---

## 1. Amaç

Bounding-box tabanlı doluluk ölçümü ile gerçek geometri tabanlı doluluk ölçümü
arasındaki farkın, yükteki **silindir hacim payına** bağlı olarak nasıl
büyüdüğünü kontrollü biçimde ölçmek.

Beklenen ilişki:

```
U_BB − U_G  ≈  U_BB × silindir_hacim_payı × (1 − π/4)
```

Silindir payı sıfırken fark sıfır olmalıdır (kutu için bounding-box = gerçek
hacim). Bu, veri setinin doğruluğunun da bir kontrolüdür.

---

## 2. Klasör yapısı

| Klasör | İçerik |
|---|---|
| `configs/` | Deney ayarları (YAML). Ayarlar koda gömülü değildir. |
| `seeds/` | Sabit seed listesi. **Değiştirilmemelidir.** |
| `instances/json/` | 30 problem örneği + `_ozet.json` |
| `instances/xlsx/` | Aynı 30 örneğin LoadPlan Pro'ya yüklenebilir Excel hâli |
| `results/raw/` | Ham koşum çıktıları (CSV) |
| `results/processed/` | Analiz tabloları |
| `scripts/` | Üreteç, koşum ve metrik kodu |
| `docs/` | Bu belge |

---

## 3. Nasıl çalıştırılır

Komutlar `enterprise_backup_20260410` klasöründen çalıştırılır.

**Örnekleri üret** (30 örnek, JSON + Excel):

```bash
python deney/scripts/ornek_ureteci.py
```

**Deneyi koş:**

```bash
python deney/scripts/kosum.py --pilot            # hızlı deneme (3 tekrar)
python deney/scripts/kosum.py --pilot --limit 3  # yalnızca 3 örnek
python deney/scripts/kosum.py                    # tam koşum (30 tekrar, uzun sürer)
```

Farklı bir deney tasarımı denemek için `configs/` altına yeni bir YAML koyup
`--config` ile gösterin; kod değiştirmeye gerek yoktur.

---

## 4. Tekrarlanabilirlik nasıl sağlanıyor

| Unsur | Yöntem |
|---|---|
| Örnek üretimi | Her örnek kendi seed'i ile üretilir (`taban_seed + seviye×100 + tekrar`) |
| Algoritma rastgeleliği | Tüm stokastik yöntemler `seeds/seeds_30.txt` içindeki **aynı** seed listesini kullanır |
| Ayarlar | Koda gömülü değil, `configs/*.yaml` içinde |
| Kod sürümü | Her koşum kaydına git commit hash'i yazılır (`+kirli` = kaydedilmemiş değişiklik var) |
| Ortam | İşletim sistemi ve Python sürümü her satıra kaydedilir |

**Doğrulandı:** Üreteç iki kez çalıştırıldığında 30 örneğin 30'u da birebir aynı
çıkmıştır (içerik SHA-256 karşılaştırması, zaman damgası hariç).

Tüm algoritmalar aynı seed listesini kullandığı için tasarım **eşleştirilmiştir**;
algoritmalar arası fark rastgelelikten değil yöntemden kaynaklanır.

---

## 5. Ölçülen metrikler

Tanımlar `scripts/metrikler.py` dosyasının başındadır. Özet:

| Metrik | Pay | Payda |
|---|---|---|
| `U_BB` | Yerleşen parçaların **bounding-box** hacmi | Kullanılan araçların hacmi |
| `U_G` | Yerleşen parçaların **gerçek** hacmi (silindir: π·r²·h) | Kullanılan araçların hacmi |
| `U_Fleet` | Yerleşen parçaların gerçek hacmi | **Mevcut tüm** filo hacmi (adet dahil) |
| `T_V` | Tüm parçaların gerçek hacmi | Tüm filo hacmi (hacim sıkılığı) |
| `T_W` | Tüm parçaların ağırlığı | Tüm filo kapasitesi (ağırlık sıkılığı) |

Üçü de her koşumda **ayrı ayrı** kaydedilir; hiçbiri diğerinin yerine
kullanılmaz. Ayrıca her kayıtta otomatik tutarlılık kontrolü yapılır
(örn. `U_BB < U_G` çıkarsa uyarı verilir).

---

## 6. Her koşumda kaydedilen alanlar

`ornek_id`, `algoritma`, `kosum_no`, `seed`, `U_BB`, `U_G`, `U_Fleet`, `T_V`,
`T_W`, `kullanilan_arac`, `yerlesen_parca`, `toplam_parca`, `yerlesen_oran`,
`sure_s`, `zaman_butcesi_s`, `stokastik`, `hedef_silindir_payi`,
`ulasilan_silindir_payi`, `commit_hash`, `ortam`, `config`, `uyarilar`

---

## 7. Tasarım kararları ve gerekçeleri

**Silindir payı neden hacim üzerinden tanımlandı, adet üzerinden değil?**
Bounding-box yanlılığı silindirlerin sayısına değil, toplam hacmin ne kadarını
kapladığına bağlıdır. 40 küçük silindir ile 3 büyük silindir aynı yanlılığı
üretmez.

**Hedef paya neden tam ulaşılamıyor?**
Parça boyutları rastgele seçildiği için hedef pay yaklaşık olarak tutturulur.
Bu nedenle her örnekte **ulaşılan** pay ayrıca kaydedilir; analizlerde hedef
değil ulaşılan pay kullanılmalıdır.

**Hacim sıkılığı (T_V) neden sabit tutuldu?**
Bu pilot sette yalnızca geometrinin etkisi ölçülmek istendiğinden, tüm
örneklerde T_V ≈ 0,55'e ölçeklenmiştir. Böylece gözlenen fark sıkılık
değişiminden değil geometriden kaynaklanır.

**Bayesian Optimization neden karşılaştırmada yok?**
Doğrudan yerleştirme yapan bir çözücü değil, hiperparametre ayarlayan üst
seviye bir katmandır. Adil head-to-head karşılaştırmaya dahil edilmesi kategori
hatasıdır (danışman raporu, kritik zaaf #4). Bu karar mevcut `deney_kosumu.py`
dosyasında zaten alınmıştı ve korunmuştur.

---

## 8. Bu pilotun kapsamadıkları

Aşağıdakiler bilinçli olarak **yapılmamıştır**; nihai deneyde ele alınmalıdır.

- **Örnek sayısı.** 30 örnek pilottur; danışman raporu nihai çalışma için
  150–300 örnek istemektedir.
- **Tekrar sayısı.** `--pilot` modu 3 tekrar kullanır. Nihai koşumda config'teki
  `tekrar_sayisi: 30` geçerlidir.
- **Diğer faktörler.** Parça sayısı, boyut heterojenliği, kısıt profili ve filo
  yapısı bu pilotta sabittir; Makale 2'nin tam faktöriyel tasarımı bunları da
  değiştirmelidir.
- **Düzensiz (mesh/STEP-STL) geometri.** Yalnızca kutu ve silindir üretilir.
  Mesh parçalar için `_fill_ratio` alanı ana algoritmaların hacim hesabına
  girmediğinden (bilinen tutarsızlık), bu pilotta kapsam dışı bırakılmıştır.
- **İstatistiksel testler.** Friedman / Wilcoxon-Holm ve etki büyüklüğü
  hesapları henüz eklenmemiştir; ham CSV bu analizler için hazırdır.
- **Kesin çözüm (MILP/CP-SAT) karşılaştırması.** Küçük örneklerde optimallik
  açığı hesabı yapılmamıştır.

---

*Son güncelleme: 8 Eylül 2026*
