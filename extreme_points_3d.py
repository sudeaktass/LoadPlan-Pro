# -*- coding: utf-8 -*-
"""
Extreme Points 3D — Yerleştirme Motoru

Referans:
  Crainic, T.G., Perboli, G. & Tadei, R. (2008).
  "Extreme Point-Based Heuristics for Three-Dimensional Bin Packing."
  INFORMS Journal on Computing, 20(3), 368–384.

EP Konsepti:
  Her kutu yerleştirildikten sonra, kutunun köşelerinden projeksiyon
  yapılarak yeni aday noktalar (extreme points) üretilir. Corner
  Points'ten farklı olarak EP, bin duvarları ve mevcut kutuların
  yüzeylerine izdüşüm yaparak boş alanları daha iyi kullanır.

MaxRects3D ile aynı arayüzü sağlar → mevcut algoritmalar (FFD, Greedy,
GA, MC) hiçbir değişiklik yapmadan EP motorunu kullanabilir.

--- DÜZELTMELER (v2) ---

HATA-1 (Dominance Pruning): Orijinal kod, koordinat karşılaştırmasına
  dayanarak EP noktalarını "dominated" sayıp siliyordu. Bu mantık 3D bin
  packing için yanlıştır: (0,0,0) EP mevcut olsa bile (100,0,0) EP
  değerlidir — bazı kutu genişlikleri yalnızca x=100 pozisyonuna sığar.
  Agresif eleme geçerli yerleşim fırsatlarını yok ederek doluluk oranını
  düşürüyordu.
  ÇÖZÜM: Dominance pruning kaldırıldı. Yalnızca sınır dışı ve occupied
  kontrolleri yapılır. Performans için MAX_EXTREME_POINTS sınırı eklendi;
  limit aşılırsa BLF sıralamasına göre en iyi noktalar tutulur.

HATA-2 (Projeksiyon Nokta→Aralık): Orijinal _project_down_x/y/z
  fonksiyonları tek bir noktanın (x veya z koordinatının) varolan
  kutularla örtüşüp örtüşmediğini kontrol ediyordu. Yerleştirilen
  kutunun gerçek boyutları göz ardı edildiğinden bazı engelleyici
  kutular atlanıyordu; bu da parçaların havada asılı kalmasına yol
  açıyordu.
  ÇÖZÜM: Her projeksiyon fonksiyonu artık yerleştirilen kutunun ilgili
  boyutlarını parametre olarak alır ve aralık-aralık (interval-interval)
  örtüşme kontrolü yapar. _generate_extreme_points bu boyutları iletir.
"""

from typing import List, Tuple, Optional, Dict
from core_3d import (COG_FRONT_BIAS, COG_VERTICAL_MAX,
    Placement3D, Truck3D,
    check_collision_with_list,
    find_lowest_z_position, check_support_3d, check_stacking_rules,
    calculate_xy_overlap_area, DEFAULT_SUPPORT_RATIO
)
from priority_utils import get_priority_zone

# EP listesinin maksimum boyutu — bu limitin üzerinde BLF sırasına göre
# en iyi noktalar tutulur (performans/kalite dengesi).
# ARTTIRILDI 200→500: Oncelik zone (yüksek Y) EP'lerinin pruning sırasında
# atılmaması için. 200 limiti BLF (düşük Y tercih) pruning ile birleşince
# y>=700 bölgesindeki z=120 EP'leri siliniyordu; priority=1 items z=120
# ikinci katmanda yanlış zone'a yerleşiyordu.
MAX_EXTREME_POINTS = 500


class ExtremePoints3D:
    """
    Extreme Points tabanlı 3D yerleştirme motoru.

    Crainic vd. (2008): Bir kutu yerleştirildiğinde 3 yönde (X+, Y+, Z+)
    projeksiyon yapılarak yeni EP'ler üretilir. Projeksiyon, en yakın
    engele (başka kutu veya bin duvarı) kadar uzanır.

    MaxRects3D ile aynı public arayüz:
      - find_best_position_3d(piece_id, w, l, h, ...)
      - place_piece_3d(piece_id, placement_tuple)
      - placements (list)
    """

    def __init__(self, width: int, length: int, height: int,
                 heuristic: str = 'CP', truck: Optional[Truck3D] = None,
                 piece_info: Optional[Dict] = None):
        self.width = width
        self.length = length
        self.height = height
        self.heuristic = heuristic
        self.truck = truck
        self.piece_info = piece_info or {}

        self.placements: List[Placement3D] = []

        # Başlangıç EP: orijin noktası (0, 0, 0)
        self.extreme_points: List[Tuple[int, int, int]] = [(0, 0, 0)]

        # PERFORMANS: CoG skor terimi için artımlı ağırlık toplamları.
        # Eskiden her EP adayında tüm yerleşimler üzerinden yeniden
        # toplanıyordu (O(n) × EP). Aynı toplama sırası korunduğundan
        # (append-only liste) sonuç bit-düzeyinde özdeştir.
        self._w_total = 0.0
        self._wx = 0.0
        self._wy = 0.0
        self._wz = 0.0
        # Ağırlık kapasite kontrolü için de aynı toplam kullanılır
        self._weight_sum = 0.0

    # ------------------------------------------------------------------
    # PUBLIC: MaxRects3D uyumlu arayüz
    # ------------------------------------------------------------------

    def find_best_position_3d(self, piece_id: str, w: int, l: int, h: int,
                              allow_rotation: bool = True,
                              respect_gravity: bool = True,
                              y_min: Optional[int] = None,
                              y_max: Optional[int] = None) -> Optional[Tuple]:
        """
        En iyi EP'yi seçerek yerleşim pozisyonu döndür.

        y_min / y_max: Oncelik zone kisiti — yalnizca bu Y araligindaki
        EP'ler degerlendirilir (None = kisit yok, kurtarma modunda).

        Returns:
            (x, y, z, width, length, height, rotation) veya None
        """
        piece = self.piece_info.get(piece_id)

        # Ağırlık kontrolü (artımlı toplam — her çağrıda O(n) toplama yok)
        if self.truck and piece:
            if self._weight_sum + piece.weight > self.truck.capacity:
                return None

        best_score = float('inf')
        best_placement = None

        # PERFORMANS: döngü sabitleri hoist edildi; X/Y sınır kontrolü ve
        # ez+h ön kontrolü gravity'den ÖNCE yapılır (z >= ez olduğundan
        # ez+h > yükseklik ⇒ z+h > yükseklik — aynı adaylar elenir, ama
        # sığmayan EP'ler için O(n) gravity taraması hiç yapılmaz).
        _placing_shape = (self.piece_info[piece_id].shape
                          if piece_id in self.piece_info else 'box')
        _w_lim = self.width  - w
        _l_lim = self.length - l
        _h_lim = self.height - h
        _has_zone = (y_min is not None or y_max is not None)

        for ep in self.extreme_points:
            ex, ey, ez = ep

            # ── Sınır ön kontrolleri (gravity'siz elenebilenler) ───────
            if ex > _w_lim or ey > _l_lim or ez > _h_lim:
                continue

            # ── Oncelik zone kisiti (HARD constraint) ─────────────────
            # Parcayi merkez bazli kontrol et: parca merkezinin zone icinde olmasi gerek
            if _has_zone:
                piece_cy = ey + l / 2.0
                if y_min is not None and piece_cy < y_min:
                    continue
                if y_max is not None and piece_cy > y_max:
                    continue

            # Gravity: gerçek Z pozisyonunu bul
            if respect_gravity:
                z = find_lowest_z_position(ex, ey, w, l, self.placements,
                                           piece_info=self.piece_info,
                                           placing_shape=_placing_shape)
                if z < ez:
                    z = ez      # EP'nin z'sinden aşağı inemez
            else:
                z = ez

            # Bin sınırı kontrolü (yalnız z gravity ile değişti)
            if z > _h_lim:
                continue

            # Çakışma kontrolü
            candidate = Placement3D(ex, ey, z, w, l, h, piece_id, (0, 0, 0), 0)
            if check_collision_with_list(candidate, self.placements, piece_info=self.piece_info):
                continue

            # Destek + istiflenme kuralları kontrolü
            if piece:
                if z > 0:
                    if not check_support_3d(candidate, self.placements,
                                            min_support_ratio=DEFAULT_SUPPORT_RATIO,
                                            piece_info=self.piece_info):
                        continue
                    valid, _ = check_stacking_rules(
                        candidate, piece, self.placements, self.piece_info)
                    if not valid:
                        continue

            # Skorlama
            score = self._score_placement(ex, ey, z, w, l, h, piece_id)

            if score < best_score:
                best_score = score
                best_placement = (ex, ey, z, w, l, h, (0, 0, 0))

        # ── Zone scan fallback ────────────────────────────────────────────
        # EP Z+ projeksiyonu, stack tepesindeki yüksek-y EP'lerini ön duvara
        # (y=0) kaydiriyor: ornegin (0,720,120) yerine (0,0,120) olusturuyor.
        # Sonucta priority zone'da (yuksek y) gecerli EP yok, item yanlis
        # bolgeye gidiyor. Cozum: y_min/y_max belirtilmis ve EP bulunamazsa
        # zone icinde sistematik grid tara.
        if best_placement is None and (y_min is not None or y_max is not None):
            placing_shape = (self.piece_info.get(piece_id).shape
                             if piece_id in self.piece_info else 'box')
            ey_lo = y_min if y_min is not None else 0
            ey_hi = (y_max - l) if y_max is not None else (self.length - l)
            ey_lo = max(0, ey_lo)
            ey_hi = min(self.length - l, ey_hi)
            # Y adimi: item derinliginin 1/4'u (daha ince tarama)
            y_step = max(1, l // 4)
            x_step = max(1, w // 4)
            for ey in range(ey_lo, ey_hi + 1, y_step):
                cy = ey + l / 2.0
                if y_min is not None and cy < y_min:
                    continue
                if y_max is not None and cy > y_max:
                    break
                for ex in range(0, self.width - w + 1, x_step):
                    z_scan = find_lowest_z_position(
                        ex, ey, w, l, self.placements,
                        piece_info=self.piece_info, placing_shape=placing_shape
                    )
                    if ex + w > self.width or ey + l > self.length or z_scan + h > self.height:
                        continue
                    cand = Placement3D(ex, ey, z_scan, w, l, h, piece_id, (0, 0, 0), 0)
                    if check_collision_with_list(cand, self.placements,
                                                piece_info=self.piece_info):
                        continue
                    if piece and z_scan > 0:
                        if not check_support_3d(cand, self.placements,
                                                min_support_ratio=DEFAULT_SUPPORT_RATIO,
                                                piece_info=self.piece_info):
                            continue
                        valid_s, _ = check_stacking_rules(
                            cand, piece, self.placements, self.piece_info)
                        if not valid_s:
                            continue
                    sc = self._score_placement(ex, ey, z_scan, w, l, h, piece_id)
                    if sc < best_score:
                        best_score = sc
                        best_placement = (ex, ey, z_scan, w, l, h, (0, 0, 0))

        return best_placement if best_score != float('inf') else None

    def place_piece_3d(self, piece_id: str, placement: Tuple) -> None:
        """Kutuyu yerleştir ve yeni EP'ler üret."""
        x, y, z, w, l, h, rot = placement

        new_placement = Placement3D(x, y, z, w, l, h, piece_id, rot, 0)
        self.placements.append(new_placement)

        # Artımlı ağırlık/CoG toplamları (skor ve kapasite kontrolü için)
        _pc = self.piece_info.get(piece_id)
        if _pc is not None:
            _wt = _pc.weight
            self._weight_sum += _wt
            self._w_total += _wt
            self._wx += _wt * (x + w / 2)
            self._wy += _wt * (y + l / 2)
            self._wz += _wt * (z + h / 2)

        # Crainic vd. (2008): 3 yönde projeksiyon ile yeni EP üret
        # DÜZELTME: yerleştirilen kutunun boyutları projeksiyona iletiliyor
        _n_before = len(self.extreme_points)
        self._generate_extreme_points(x, y, z, w, l, h)

        # Geçersiz EP'leri temizle (eski EP'ler yalnız YENİ yerleşime karşı)
        self._prune_extreme_points(new_from=_n_before,
                                   new_placement=new_placement)

    # ------------------------------------------------------------------
    # EP ÜRETİMİ — Crainic vd. (2008) Algoritma  [DÜZELTME: HATA-2]
    # ------------------------------------------------------------------

    def _generate_extreme_points(self, x: int, y: int, z: int,
                                 w: int, l: int, h: int) -> None:
        """
        Yeni yerleştirilen kutunun 3 köşesinden projeksiyon yap:
          1. (x+w, y, z)  → X+ yönünde sağ kenar
          2. (x, y+l, z)  → Y+ yönünde arka kenar
          3. (x, y, z+h)  → Z+ yönünde üst kenar

        DÜZELTME (HATA-2): Her projeksiyon artık yerleştirilen kutunun
        ilgili boyutlarını (w, l, h) alarak aralık-aralık örtüşme kontrolü
        yapıyor. Eski tek-nokta kontrolü bazı engelleyici kutuları atlıyordu.
        """
        candidates = []

        # ── 1. X+ projeksiyon: kutunun sağ yüzü ─────────────────────────
        # Yeni EP: (x+w, ?, ?)
        # Y projeksiyonu: x=x+w pozisyonunda, Z aralığı [z, z+h]
        # Z projeksiyonu: x=x+w pozisyonunda, Y aralığı [y, y+l] (placed kutunun derinliği)
        px = x + w
        if px < self.width:
            proj_y = self._project_down_y(px, y, z, fx=1, fz=h)
            proj_z = self._project_down_z(px, proj_y, z, fx=1, fy=l)
            candidates.append((px, proj_y, proj_z))

            proj_z2 = self._project_down_z(px, y, z, fx=1, fy=l)
            proj_y2 = self._project_down_y(px, y, proj_z2, fx=1, fz=h)
            candidates.append((px, proj_y2, proj_z2))

        # ── 2. Y+ projeksiyon: kutunun arka yüzü ─────────────────────────
        # Yeni EP: (?, y+l, ?)
        # X projeksiyonu: y=y+l pozisyonunda, Z aralığı [z, z+h]
        # Z projeksiyonu: y=y+l pozisyonunda, X aralığı [x, x+w] (placed kutunun genişliği)
        py = y + l
        if py < self.length:
            proj_x = self._project_down_x(x, py, z, fy=1, fz=h)
            proj_z = self._project_down_z(proj_x, py, z, fx=w, fy=1)
            candidates.append((proj_x, py, proj_z))

            proj_z2 = self._project_down_z(x, py, z, fx=w, fy=1)
            proj_x2 = self._project_down_x(x, py, proj_z2, fy=1, fz=h)
            candidates.append((proj_x2, py, proj_z2))

        # ── 3. Z+ projeksiyon: kutunun üst yüzü ─────────────────────────
        # Yeni EP: (?, ?, z+h)
        # X projeksiyonu: z=z+h pozisyonunda, Y aralığı [y, y+l]
        # Y projeksiyonu: z=z+h pozisyonunda, X aralığı [x, x+w]
        pz = z + h
        if pz < self.height:
            # DUZELTME: Dogrudan (x, y, pz) EP'sini ekle — projeksiyon
            # Y yonunde z=pz seviyesinde engel bulamadiginda (fz=1 dilimi
            # mevcut kutularla [0,h] arasina girmez) ön duvara (y=0) kayar.
            # Bu "kayma" ust-katman EP'lerini yanlis yere koyar (ornek:
            # P1_0 nin ustu (0,720,120) yerine (0,0,120) olur). Crainic (2008)
            # orijinalinde dogrudan (x,y,z+h) EP'si vardir.
            candidates.append((x, y, pz))

            proj_x = self._project_down_x(x, y, pz, fy=l, fz=1)
            proj_y = self._project_down_y(proj_x, y, pz, fx=w, fz=1)
            candidates.append((proj_x, proj_y, pz))

            proj_y2 = self._project_down_y(x, y, pz, fx=w, fz=1)
            proj_x2 = self._project_down_x(x, proj_y2, pz, fy=l, fz=1)
            candidates.append((proj_x2, proj_y2, pz))

        # Geçerli adayları EP listesine ekle
        for cx, cy, cz in candidates:
            if (0 <= cx < self.width and
                0 <= cy < self.length and
                0 <= cz < self.height):
                ep = (cx, cy, cz)
                if ep not in self.extreme_points:
                    self.extreme_points.append(ep)

    # ------------------------------------------------------------------
    # PROJEKSIYON YARDIMCI FONKSİYONLARI  [DÜZELTME: HATA-2]
    # ------------------------------------------------------------------

    def _project_down_x(self, x: int, y: int, z: int,
                        fy: int = 1, fz: int = 1) -> int:
        """
        X yönünde en yakın engeli bul ve o noktaya kaydır (sola).

        DÜZELTME: Eski kod tek-nokta (y, z) kontrolü yapıyordu.
        Yeni kod, yerleştirilen kutunun Y derinliğini (fy) ve Z yüksekliğini
        (fz) kullanarak aralık-aralık örtüşme kontrolü yapıyor.

        Args:
            x:  Projeksiyon başlangıç X koordinatı
            y:  Projeksiyon başlangıç Y koordinatı
            z:  Projeksiyon başlangıç Z koordinatı
            fy: Kontrol edilecek Y aralığının uzunluğu (placed kutunun derinliği)
            fz: Kontrol edilecek Z aralığının uzunluğu (placed kutunun yüksekliği)
        """
        min_x = 0  # Duvar
        fy = max(fy, 1)
        fz = max(fz, 1)
        for p in self.placements:
            # Y aralığı [y, y+fy] ile p'nin Y aralığı [p.y, p.y+p.length] örtüşüyor mu?
            if p.y < y + fy and p.y + p.length > y:
                # Z aralığı [z, z+fz] ile p'nin Z aralığı [p.z, p.z+p.height] örtüşüyor mu?
                if p.z < z + fz and p.z + p.height > z:
                    right_edge = p.x + p.width
                    if right_edge <= x:
                        min_x = max(min_x, right_edge)
        return min_x

    def _project_down_y(self, x: int, y: int, z: int,
                        fx: int = 1, fz: int = 1) -> int:
        """
        Y yönünde en yakın engeli bul (öne).

        DÜZELTME: Eski kod tek-nokta (x, z) kontrolü yapıyordu.
        Yeni kod, X genişliğini (fx) ve Z yüksekliğini (fz) kullanarak
        aralık-aralık örtüşme kontrolü yapıyor.

        Args:
            x:  Projeksiyon başlangıç X koordinatı
            y:  Projeksiyon başlangıç Y koordinatı
            z:  Projeksiyon başlangıç Z koordinatı
            fx: Kontrol edilecek X aralığının uzunluğu (placed kutunun genişliği)
            fz: Kontrol edilecek Z aralığının uzunluğu (placed kutunun yüksekliği)
        """
        min_y = 0
        fx = max(fx, 1)
        fz = max(fz, 1)
        for p in self.placements:
            # X aralığı [x, x+fx] ile p'nin X aralığı [p.x, p.x+p.width] örtüşüyor mu?
            if p.x < x + fx and p.x + p.width > x:
                # Z aralığı [z, z+fz] ile p'nin Z aralığı [p.z, p.z+p.height] örtüşüyor mu?
                if p.z < z + fz and p.z + p.height > z:
                    back_edge = p.y + p.length
                    if back_edge <= y:
                        min_y = max(min_y, back_edge)
        return min_y

    def _project_down_z(self, x: int, y: int, z: int,
                        fx: int = 1, fy: int = 1) -> int:
        """
        Z yönünde en yakın engeli bul (aşağı).

        DÜZELTME: Eski kod tek-nokta (x, y) kontrolü yapıyordu.
        Yeni kod, X genişliğini (fx) ve Y derinliğini (fy) kullanarak
        aralık-aralık örtüşme kontrolü yapıyor.

        Args:
            x:  Projeksiyon başlangıç X koordinatı
            y:  Projeksiyon başlangıç Y koordinatı
            z:  Projeksiyon başlangıç Z koordinatı
            fx: Kontrol edilecek X aralığının uzunluğu (placed kutunun genişliği)
            fy: Kontrol edilecek Y aralığının uzunluğu (placed kutunun derinliği)
        """
        min_z = 0
        fx = max(fx, 1)
        fy = max(fy, 1)
        for p in self.placements:
            # X aralığı [x, x+fx] ile p'nin X aralığı örtüşüyor mu?
            if p.x < x + fx and p.x + p.width > x:
                # Y aralığı [y, y+fy] ile p'nin Y aralığı örtüşüyor mu?
                if p.y < y + fy and p.y + p.length > y:
                    top_edge = p.z + p.height
                    if top_edge <= z:
                        min_z = max(min_z, top_edge)
        return min_z

    # ------------------------------------------------------------------
    # EP TEMİZLEME  [DÜZELTME: HATA-1]
    # ------------------------------------------------------------------

    def _prune_extreme_points(self, new_from: Optional[int] = None,
                              new_placement: Optional[Placement3D] = None) -> None:
        """
        Geçersiz EP'leri temizle.

        DÜZELTME (HATA-1): Orijinal kod koordinat karşılaştırmasına
        dayalı "dominance pruning" yapıyordu — bir EP'nin tüm koordinatları
        başka bir EP'den büyükse "dominated" sayılıp siliniyordu. Bu mantık
        yanlıştır: (0,0,0) mevcut olsa bile (100,0,0) geçerli olabilir çünkü
        geniş bir kutu x=0'a sığmazken x=100'e sığabilir. Agresif eleme
        doluluk oranını %5-15 düşürüyordu.

        YAKLAŞIM:
          1. Sınır dışı EP'leri kaldır.
          2. Yerleşimlerin içine düşen EP'leri kaldır.
          3. Dominance pruning YAPILMAZ.
          4. MAX_EXTREME_POINTS sınırı aşılırsa BLF sırasına göre
             en iyi noktaları tut (performans için).

        PERFORMANS (new_from/new_placement verilirse): önceki turda hayatta
        kalan EP'ler eski yerleşimlerin dışındaydı ve sınır içindeydi —
        onları geçersiz kılabilecek TEK şey yeni yerleşimdir; yalnız ona
        karşı test edilirler. Yeni üretilen adaylar (index >= new_from)
        tüm yerleşimlere karşı test edilir. Sonuç kümesi, tam taramayla
        birebir aynıdır.
        """
        _incremental = new_from is not None and new_placement is not None
        valid = []
        for idx, ep in enumerate(self.extreme_points):
            ex, ey, ez = ep
            if _incremental and idx < new_from:
                # Eski EP: sınır içi ve eski yerleşimlerin dışında olduğu
                # zaten kanıtlı — yalnız yeni yerleşime karşı test et
                np_ = new_placement
                if (np_.x <= ex < np_.x + np_.width and
                        np_.y <= ey < np_.y + np_.length and
                        np_.z <= ez < np_.z + np_.height):
                    continue
                valid.append(ep)
                continue
            # Yeni aday (veya tam tarama modu): tüm kontroller
            if ex >= self.width or ey >= self.length or ez >= self.height:
                continue
            inside = False
            for p in self.placements:
                if (p.x <= ex < p.x + p.width and
                    p.y <= ey < p.y + p.length and
                    p.z <= ez < p.z + p.height):
                    inside = True
                    break
            if not inside:
                valid.append(ep)

        # ── Dominance pruning KALDIRILDI ────────────────────────────────
        # Koordinat bazlı eleme geçerli yerleşim fırsatlarını yok ediyordu.
        # Bunun yerine performans sınırı uygula.
        # DÜZELTME: Saf BLF budaması (düşük y tercihli) yüksek-Y (kapı /
        # öncelik bölgesi) EP'lerini tamamen atıyordu; limitin %20'si
        # yüksek-Y EP'lerine ayrılır ki öncelikli parçalar bölgelerinde
        # her zaman aday nokta bulabilsin.
        if len(valid) > MAX_EXTREME_POINTS:
            keep_main = int(MAX_EXTREME_POINTS * 0.8)
            valid.sort(key=lambda e: (e[2], e[1], e[0]))   # BLF: z, y, x
            head = valid[:keep_main]
            tail = valid[keep_main:]
            tail.sort(key=lambda e: (-e[1], e[2], e[0]))   # yüksek y önce
            head_set = set(head)
            for ep in tail:
                if len(head) >= MAX_EXTREME_POINTS:
                    break
                if ep not in head_set:
                    head.append(ep)
                    head_set.add(ep)
            valid = head

        self.extreme_points = valid if valid else [(0, 0, 0)]

    # ------------------------------------------------------------------
    # SKORLAMA
    # ------------------------------------------------------------------

    def _score_placement(self, x: int, y: int, z: int,
                         w: int, l: int, h: int,
                         piece_id: Optional[str] = None) -> float:
        """Yerleşim skoru — düşük = daha iyi."""
        if self.heuristic == 'CP':
            return self._score_contact_point(x, y, z, w, l, h, piece_id)
        else:
            return self._score_bottom_left(x, y, z)

    def _score_contact_point(self, x: int, y: int, z: int,
                             w: int, l: int, h: int,
                             piece_id: Optional[str]) -> float:
        """
        Contact Point heuristic — temas alanı fazla olan tercih edilir.

        DÜZELTME (HATA-4 — Score Normalizasyonu):
        Orijinal kod ham koordinat değerlerini sabit çarpanlarla
        (1000, 1500, 120000, 80000...) birleştiriyordu. Araç boyutuna
        normalize edilmemiş bu sayılar ölçek uyumsuzluğu yaratıyordu:
          - contact * 1000 → tipik değer: milyonlar
          - z * 1500        → tipik değer: yüz binler
          - front_bonus     → sabit ±120000/80000
        Araç 4m olduğunda front_bonus küçük katkı yaparken 10m araçta
        dominant olabiliyordu. Tutarsız karar davranışı ortaya çıkıyordu.

        YENİ YAKLAŞIM: Tüm terimler araç boyutlarına normalize edilir
        (referans: araç taban alanı, yüksekliği, uzunluğu). Ağırlıklar
        göreli önemi doğrudan yansıtır — araç boyutu değişse de davranış
        tutarlı kalır. Toplam skor aralığı: yaklaşık [-1.0, +0.7].

        Ağırlık önceliği:
          temas(1.0) > yükseklik(0.30) > ön-yükleme(0.25) >
          CoG(0.20) > LIFO(0.10) > derinlik(0.05) > yatay(0.01)
        """
        # ── 1. Temas alanı (ham değer, sonra normalize edilecek) ──────
        # PERFORMANS: abs() çağrıları inline aralık karşılaştırmalarına
        # çevrildi, uç koordinatlar hoist edildi — matematik birebir aynı.
        contact = 0
        if x == 0: contact += l * h
        if y == 0: contact += w * h
        if z == 0: contact += w * l
        x2 = x + w; y2 = y + l; z2 = z + h
        if x2 == self.width:  contact += l * h
        if y2 == self.length: contact += w * h
        if z2 == self.height: contact += w * l

        for p in self.placements:
            p_x = p.x; p_y = p.y; p_z = p.z
            p_x2 = p_x + p.width; p_y2 = p_y + p.length; p_z2 = p_z + p.height
            # Alt/üst temas (Z yönü)  [abs(z - p_z2) < 1  veya  abs(z2 - p_z) < 1]
            dz1 = z - p_z2; dz2 = z2 - p_z
            if -1 < dz1 < 1 or -1 < dz2 < 1:
                ox = (x2 if x2 < p_x2 else p_x2) - (x if x > p_x else p_x)
                if ox > 0:
                    oy = (y2 if y2 < p_y2 else p_y2) - (y if y > p_y else p_y)
                    if oy > 0:
                        contact += ox * oy * 2
            # X yönü yan temas
            dx1 = x2 - p_x; dx2 = p_x2 - x
            if -1 < dx1 < 1 or -1 < dx2 < 1:
                ov_y = (y2 if y2 < p_y2 else p_y2) - (y if y > p_y else p_y)
                if ov_y > 0:
                    ov_z = (z2 if z2 < p_z2 else p_z2) - (z if z > p_z else p_z)
                    if ov_z > 0:
                        contact += ov_y * ov_z
            # Y yönü yan temas
            dy1 = y2 - p_y; dy2 = p_y2 - y
            if -1 < dy1 < 1 or -1 < dy2 < 1:
                ov_x = (x2 if x2 < p_x2 else p_x2) - (x if x > p_x else p_x)
                if ov_x > 0:
                    ov_z = (z2 if z2 < p_z2 else p_z2) - (z if z > p_z else p_z)
                    if ov_z > 0:
                        contact += ov_x * ov_z

        # ── 2. Normalizasyon referansları (araç boyutlarına göre) ──────
        ref_area = self.width * self.length + 1e-9   # Taban alanı — temas referansı
        ref_h    = self.height + 1e-9
        ref_l    = self.length + 1e-9
        ref_w    = self.width  + 1e-9

        contact_norm = contact / ref_area   # [0, ~3] — köşelerde 3 üzeri mümkün
        z_norm       = z / ref_h            # [0, 1]
        y_norm       = y / ref_l            # [0, 1]
        x_norm       = x / ref_w            # [0, 1]

        # ── 3. Ön yükleme faktörü (normalize: [-1, +1]) ───────────────
        # Erbayrak et al. (2021) + Synák & Nedeliaková (2024)
        front_zone = self.length * COG_FRONT_BIAS
        piece_cy   = y + l / 2.0
        if piece_cy <= front_zone:
            # Ön bölge → ödül (negatif = daha iyi)
            front_factor = -(1.0 - piece_cy / (front_zone + 1e-9))
        else:
            # Arka bölge → ceza
            back_span    = ref_l - front_zone
            front_factor = (piece_cy - front_zone) / (back_span + 1e-9)

        # ── 4. CoG sapma cezası (normalize: [0, ~1]) ──────────────────
        # PERFORMANS: toplamlar place_piece_3d'de artımlı tutulur — her EP
        # adayında O(n) yeniden toplama yok. Toplama sırası aynı (append
        # sırası) olduğundan değerler bit-düzeyinde özdeştir.
        cog_norm = 0.0
        if self.piece_info and piece_id:
            piece = self.piece_info.get(piece_id)
            if piece:
                _pw = piece.weight
                cx_total = self._wx + _pw * (x + w / 2)
                cy_total = self._wy + _pw * (y + l / 2)
                cz_total = self._wz + _pw * (z + h / 2)
                tw = self._w_total + _pw
                if tw > 1e-6:
                    new_cog_x = cx_total / tw
                    new_cog_y = cy_total / tw
                    new_cog_z = cz_total / tw
                    x_dev = abs(new_cog_x - self.width  / 2) / (self.width  / 2 + 1e-9)
                    y_dev = abs(new_cog_y - self.length * COG_FRONT_BIAS) / (self.length + 1e-9)
                    z_dev = max(0.0, new_cog_z / (self.height + 1e-9) - COG_VERTICAL_MAX)
                    # Ağırlıklar: yanal denge(0.30), boylamsal(0.60), dikey(0.10)
                    cog_norm = 0.30 * x_dev + 0.60 * y_dev + 0.10 * z_dev  # [0, ~1]

        # ── 5. Öncelik / LIFO — zone-aware (normalize: [0, 1]) ────────
        # DUZELTME: Eski kod "ideal_y = priority * 50" kullaniyordu.
        # Bu tamamen yanlistir: priority=1 icin 50 cm (kamyon ONU) hesapliyordu,
        # oysa priority=1 = KAPI YAKINI = son %30 (y >= 0.70*L) olmali.
        # Yeni kod get_priority_zone() kullanarak dogru bolgeyi hesaplar.
        priority_norm = 0.0
        _prio_piece = self.piece_info.get(piece_id) if piece_id and self.piece_info else None
        _has_priority = (
            _prio_piece is not None
            and getattr(_prio_piece, 'priority', None) is not None
            and _prio_piece.priority > 0
        )
        if _has_priority:
            _y_min_z, _y_max_z = get_priority_zone(self.length, _prio_piece.priority)
            _piece_cy = y + l / 2.0
            if _y_min_z <= _piece_cy <= _y_max_z:
                priority_norm = 0.0  # Dogru bolgede — ceza yok
            else:
                _dist = min(abs(_piece_cy - _y_min_z), abs(_piece_cy - _y_max_z))
                priority_norm = _dist / ref_l  # [0, 1]

        # Oncelik urunu icin front_factor devre disi:
        # front_factor kamyonun ONUNU doldurmaya iter (dusuk y), ama oncelik
        # urunu ARKAYA (yuksek y) gitmesi gerekir — direkt catisma.
        _eff_front = 0.0 if _has_priority else front_factor
        # Oncelik agirligini artir: normal 0.10, oncelikli 1.00
        # 1.00 agirlik sinir zone ihlallerini (ornegin center_y=675 vs 700)
        # onler; dogru zone her zaman yanlis zone'a kiyasla net kazanir.
        _prio_w = 1.00 if _has_priority else 0.10

        # ── Ağırlıklı birleştirme — tüm terimler normalize ────────────
        # Düşük skor = daha iyi. Toplam aralık ≈ [-1.0, +0.7]
        return (
            -1.00 * contact_norm   # temas: maksimize → negatif = daha iyi
            + 0.30 * z_norm        # yükseklik: alçakta tut          [0, +0.30]
            + 0.25 * _eff_front    # ön yükleme: öncelikte devre dışı [-0.25, +0.25]
            + 0.20 * cog_norm      # CoG sapması: minimize            [0, +0.20]
            + _prio_w * priority_norm  # LIFO zone: 0.10 normal / 0.50 öncelik
            + 0.05 * y_norm        # derinlik: tiebreaker             [0, +0.05]
            + 0.01 * x_norm        # yatay: son tiebreaker            [0, +0.01]
        )

    def _score_bottom_left(self, x: int, y: int, z: int) -> float:
        """Bottom-Left-Fill: Z > Y > X önceliği."""
        return z * 1000000 + y * 1000 + x


# ============================================================================
# FABRİKA FONKSİYONU — Algoritmaların motor seçimi
# ============================================================================

def create_packing_engine(width: int, length: int, height: int,
                          engine: str = 'EP',
                          heuristic: str = 'CP',
                          truck: Optional[Truck3D] = None,
                          piece_info: Optional[Dict] = None):
    """
    Yerleştirme motoru oluştur.

    Args:
        engine: 'EP' (Extreme Points) veya 'MR' (MaxRects)
        diğer argümanlar: motor parametreleri

    Returns:
        ExtremePoints3D veya MaxRects3D instance
    """
    if engine == 'MR':
        from maxrects_3d import MaxRects3D
        return MaxRects3D(width, length, height, heuristic, truck, piece_info)
    else:
        return ExtremePoints3D(width, length, height, heuristic, truck, piece_info)
