# 🏭 LoadPlan Pro — Endüstri Mühendisliği Değerlendirmesi

*Bu belge, LoadPlan Pro'yu **teknik/kod detaylarından bağımsız** olarak, endüstri mühendisliği ve yöneylem araştırması bakış açısıyla değerlendirir. Hedef okuyucu: lojistik/tedarik zinciri karar vericileri, akademik jüri ve endüstri mühendisliği öğrencileri.*

---

## 1. Operasyonel Problem: Neden Önemli?

Kara yolu taşımacılığında **araç doluluk oranı**, doğrudan birim taşıma maliyetini belirleyen en kritik operasyonel göstergedir. Yarı dolu giden bir tır; yakıt, sürücü, amortisman ve sefer maliyetlerini aynı tutarken taşınan değeri düşürür — yani **birim başına maliyeti artırır** ve **karbon ayak izini** kötüleştirir.

LoadPlan Pro'nun çözdüğü problem, endüstri mühendisliği literatüründe **Üç Boyutlu Kutu-Palet Yerleştirme Problemi (3D Bin Packing / Container Loading Problem)** olarak bilinir:

> *"Farklı boyut ve ağırlıktaki yükleri, fiziksel ve operasyonel kısıtları ihlal etmeden, minimum sayıda araca en yüksek doluluk oranıyla yerleştirmek."*

Bu problem **NP-zor** sınıfındadır; yani elle veya deneme-yanılmayla optimum bulmak, gerçek ölçekli (yüzlerce parçalı) sevkiyatlarda pratik olarak imkânsızdır. Sistematik bir karar destek aracı bu noktada devreye girer.

---

## 2. Tedarik Zinciri ve Lojistikteki Yeri

| Fonksiyon | LoadPlan Pro'nun Katkısı |
|-----------|--------------------------|
| **Sevkiyat planlama** | Kaç araç gerektiğini ve neyin nereye konacağını önceden belirler |
| **Filo yönetimi** | Mevcut araç tiplerinden en uygun kombinasyonu seçer |
| **Depo/yükleme operasyonu** | Sürücüye sıra numaralı, QR kodlu yükleme talimatı verir |
| **Maliyet kontrolü** | Araç sayısını azaltarak doğrudan taşıma maliyetini düşürür |
| **Müşteri hizmet düzeyi** | Öncelikli teslimatları (LIFO) kapıya yakın konumlandırır |
| **İş güvenliği** | Ağırlık merkezi ve istif kısıtlarıyla devrilme/hasar riskini azaltır |

Bu yönleriyle LoadPlan Pro, klasik bir **operasyonel karar destek sistemi (DSS)** işlevi görür: kararı otomatikleştirmez, karar vericiye **kanıta dayalı öneri** sunar.

---

## 3. Algoritmaların Endüstri Mühendisliği Açısından Değerlendirmesi

Endüstri mühendisliğinde "en iyi algoritma" yoktur; **problem yapısına ve karar bağlamına uygun algoritma** vardır (No Free Lunch ilkesi). Aşağıda her yöntem, *ne zaman kullanılmalı* perspektifiyle değerlendirilmiştir.

### 🟢 Hızlı Sezgiseller — "Operasyonel hız gereken durumlar"

| Algoritma | Operasyonel Karşılık | Ne zaman? |
|-----------|----------------------|-----------|
| **Greedy (Online Best-Fit)** | Yükler geldikçe anında yerleştirme (çevrimiçi karar) | Yük sırası önceden bilinmiyorsa; canlı yükleme senaryosu |
| **FFD (Best-Fit Decreasing)** | Tüm yük bilinip önceden planlanıyorsa hızlı, iyi çözüm | Günlük sevkiyat planı; saniyeler içinde sonuç istenen durum |
| **Layer Building** | Katman katman, düzenli istifleme | Homojen (benzer boyutlu) yükler; operatörün kolay uygulayacağı düzen |

**EM yorumu:** Bu yöntemler *deterministik* ve *hızlıdır* — aynı girdi hep aynı sonucu verir, bu da operasyonel öngörülebilirlik sağlar. Ancak yerel kararlar verdikleri için optimumdan sapabilirler. Pratikte genellikle **hızlı bir taban çizgisi (baseline)** olarak kullanılırlar.

### 🟡 Metasezgiseller — "Kaliteyi maksimize etmek için zaman ayrılabilen durumlar"

| Algoritma | Operasyonel Karşılık | Ne zaman? |
|-----------|----------------------|-----------|
| **Tabu Search** | Denenmiş kötü düzenleri "yasaklayarak" sistematik iyileştirme | Karmaşık, heterojen yükte yüksek kalite gerektiğinde |
| **Simulated Annealing** | Başta cesur denemeler, sonra ince ayar | Yerel çözümlere takılmadan geniş arama istendiğinde |
| **Genetic / Island GA** | Birçok çözümü "evrimleştirerek" en iyisini üretme | En karmaşık, en heterojen sevkiyatlarda |
| **Multi-Start SA** | Farklı başlangıçlardan deneyip en iyisini seçme | Güvenilir, başlangıç-bağımsız sonuç istendiğinde |
| **Monte Carlo** | Çok sayıda rastgele deneme, en iyisini alma | Çeşitlilik/keşif gereken durumlarda; diğerlerine başlangıç üretme |

**EM yorumu:** Metasezgiseller *stokastiktir* (rastgelelik içerir) ve **süre-kalite ödünleşimi** sunar: daha çok süre → daha iyi çözüm. Endüstri mühendisliği açısından kritik nokta, bunların **saniyeler yerine dakikalar** gerektirmesidir — yani operasyonel aciliyet düşük, kalite beklentisi yüksek planlamalar için uygundur.

### 🔵 Meta-Katman — "Algoritmayı otomatik ayarlama"

| Algoritma | Operasyonel Karşılık |
|-----------|----------------------|
| **Bayesian Optimization** | Diğer algoritmaların "ayar düğmelerini" akıllıca ayarlar (bir paketleme çözücüsü değil, bir *ayar* aracıdır) |

**EM yorumu:** Bu, parametre ayarını uzmandan alıp veriye devreden bir üst-seviye araçtır; doğrudan yük yerleştirmez.

---

## 4. Kısıtların Operasyonel Anlamı

Akademik modeller çoğu zaman yalnızca hacmi dikkate alır; oysa gerçek lojistikte **fiziksel uygulanabilirlik** en az doluluk kadar önemlidir. LoadPlan Pro bu kısıtları operasyonel gerçeklikle modeller:

| Kısıt | Gerçek Dünya Karşılığı | Riski |
|-------|------------------------|-------|
| **Ağırlık kapasitesi** | Aracın yasal/teknik yük sınırı | Ceza, kaza, araç hasarı |
| **Ağırlık merkezi (CoG)** | Yükün dengeli dağılması | Devrilme, dingil aşımı, sürüş güvenliği |
| **İstif kuralları** | Kırılgan/hassas yük üstüne yük konmaması | Ürün hasarı, müşteri iadesi |
| **Destek oranı (%80)** | Havada asılı/yetersiz destekli parça olmaması | İstif çökmesi, yük kayması |
| **Öncelik / LIFO** | İlk teslim edilecek yükün en son (kapıya yakın) yüklenmesi | Teslimatta yeniden elleçleme, zaman kaybı |
| **Minimum aralık** | Parçalar arası güvenlik boşluğu | Yükleme/boşaltma sırasında hasar |

Bu kısıtların modele dahil edilmesi, çözümün **"kâğıt üzerinde verimli" değil, "sahada uygulanabilir"** olmasını sağlar — endüstri mühendisliğinin uygulanabilirlik ilkesinin doğrudan yansımasıdır.

---

## 5. Performans Göstergeleri ve İş Değeri

| Gösterge (KPI) | İş Değeri |
|----------------|-----------|
| **Doluluk oranı** ↑ | Daha az araçla daha çok yük → birim maliyet ↓ |
| **Araç sayısı** ↓ | Doğrudan yakıt, sürücü, sefer maliyeti tasarrufu |
| **Fire hacmi** ↓ | Boşa taşınan hava hacminin azalması |
| **Hesaplama süresi** | Planlama çevrim süresi (operasyonel tepki hızı) |
| **Optimallik açığı** | "Çözümüm en iyisine ne kadar yakın?" — yönetime güven metriği |

Özellikle **optimallik açığı (alt-sınıra uzaklık)**, endüstri mühendisliği açısından güçlü bir katkıdır: sistem yalnızca bir çözüm önermez, aynı zamanda *"bu çözüm teorik en iyiden en fazla %X uzakta"* diyerek kararın kalitesini **ölçülebilir** kılar. Bu, yönetime sunulan bir plana **güvenilirlik** kazandırır.

---

## 6. Karar Destek Sistemi Olarak Konumlandırma

LoadPlan Pro, klasik karar destek sistemi katmanlarını içerir:

- **Veri katmanı:** Araç ve yük tanımları (Excel/CAD ile entegre)
- **Model katmanı:** 10 algoritma + kısıt modeli + alt-sınır
- **Analiz katmanı:** Karşılaştırma, duyarlılık analizi, olurluluk doğrulama
- **Sunum katmanı:** 3B görselleştirme, raporlar, sürücü talimatları

Karar verici; farklı algoritmaları **aynı veride yan yana** koşturup, süre-kalite-uygulanabilirlik üçgeninde bilinçli bir seçim yapar. Bu, "tek bir kara-kutu cevap" yerine **şeffaf, karşılaştırmalı karar** yaklaşımıdır.

---

## 7. Sınırlılıklar (Dürüst Değerlendirme)

Endüstri mühendisliği titizliği, güçlü yanlar kadar sınırların da açıkça belirtilmesini gerektirir:

- **Mutlak optimum garantisi yoktur.** Problem NP-zor olduğundan, gerçek ölçekte (100+ parça) çözüm optimuma *yakındır* ama optimum olduğu *kanıtlanamaz*. Sistem bunu alt-sınır açığıyla dürüstçe raporlar.
- **Metasezgiseller stokastiktir.** Aynı problemde koşumdan koşuma küçük farklar olabilir; bu nedenle çoklu koşu ortalaması önerilir.
- **Girdi kalitesine bağımlıdır.** Yanlış boyut/ağırlık verisi, yanlış plan üretir (çöp girer, çöp çıkar ilkesi).
- **Statik planlama.** Sistem tek seferlik yerleşim planı üretir; dinamik/gerçek-zamanlı yeniden planlama kapsam dışıdır.

---

## 8. Özet Değerlendirme

LoadPlan Pro, endüstri mühendisliği açısından üç temel katkı sunar:

1. **Verimlilik:** Araç doluluğunu artırıp taşıma maliyetini ve karbon ayak izini düşürür.
2. **Uygulanabilirlik:** Ağırlık, denge, istif ve öncelik kısıtlarını modelleyerek *sahada uygulanabilir* planlar üretir.
3. **Şeffaflık:** Çözümü mutlak optimuma değil, kanıtlanabilir bir alt-sınıra göre konumlandırarak kararın kalitesini ölçülebilir kılar.

Kısacası proje, bir yöneylem araştırması problemini (3D-KPP) **operasyonel bir karar destek aracına** dönüştürerek, akademik yöntemler ile saha gerçekliği arasında köprü kurar.

---

*Teknik kurulum ve kod yapısı için bkz. [`README.md`](README.md)*
