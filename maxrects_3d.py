# -*- coding: utf-8 -*-
"""
3D MaxRects Algorithm - 3 Boyutlu Maksimum Dikdörtgen Packing
"""

from typing import List, Tuple, Optional, Dict
from core_3d import (
    Placement3D, Truck3D, Cuboid,
    find_lowest_z_position,
    check_support_3d, check_stacking_rules
)


class MaxRects3D:
    """
    3D MaxRects Algorithm
    
    Özelliler:
    - 3D boş alan yönetimi (cuboids)
    - Gravity desteği (paletler havada as

ılı kalmaz)
    - İstiflenme kuralları
    - Çoklu heuristic desteği
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
        
        # Başlangıç: Tek bir dev cuboid
        self.free_cuboids: List[Cuboid] = [
            Cuboid(0, 0, 0, width, length, height)
        ]
        
        self.placements: List[Placement3D] = []
    
    def find_best_position_3d(self, piece_id: str, w: int, l: int, h: int,
                             allow_rotation: bool = True,
                             respect_gravity: bool = True) -> Optional[Tuple]:
        """
        En iyi 3D yerleşim pozisyonunu bul
        
        Returns:
            (x, y, z, width, length, height, rotation) veya None
        """
        piece = self.piece_info.get(piece_id)
        
        # Ağırlık kontrolü (eğer truck ve piece_info varsa)
        if self.truck and piece:
            current_weight = sum(
                self.piece_info[p.piece_id].weight for p in self.placements
            )
            if current_weight + piece.weight > self.truck.capacity:
                return None
        
        best_score = float('inf')
        best_placement = None
        
        # Tüm free cuboid'leri tara
        for cuboid in self.free_cuboids:
            # Sığacak mı?
            if w > cuboid.width or l > cuboid.length or h > cuboid.height:
                continue
            
            # Pozisyon adayı
            x, y = cuboid.x, cuboid.y
            
            # Gravity: En alttaki boş Z pozisyonunu bul
            if respect_gravity:
                placing_shape = self.piece_info.get(piece_id).shape if piece_id in self.piece_info else 'box'
                z = find_lowest_z_position(x, y, w, l, self.placements, piece_info=self.piece_info, placing_shape=placing_shape)
                
                # Cuboid içinde mi?
                if z < cuboid.z or z + h > cuboid.z + cuboid.height:
                    continue
            else:
                z = cuboid.z
            
            # Destek kontrolü
            if z > 0 and piece:
                candidate_placement = Placement3D(
                    x, y, z, w, l, h, piece_id, (0, 0, 0), 0
                )
                if not check_support_3d(candidate_placement, self.placements, min_support_ratio=0.95, piece_info=self.piece_info):
                    continue
                
                # İstiflenme kuralları
                if piece:
                    valid, msg = check_stacking_rules(
                        candidate_placement, piece, self.placements, self.piece_info
                    )
                    if not valid:
                        continue
            
            # Skor hesapla
            score = self.score_placement_3d(x, y, z, w, l, h, piece_id)
            
            if score < best_score:
                best_score = score
                best_placement = (x, y, z, w, l, h, (0, 0, 0))
        
        return best_placement if best_score != float('inf') else None
    
    def score_placement_3d(self, x: int, y: int, z: int,
                           w: int, l: int, h: int,
                           piece_id: Optional[str] = None) -> float:
        """
        3D yerleşim skoru
        
        Heuristikler:
        - CP (Contact Point): Temas sayısı (çok = iyi)
        - BSSF (Bottom Left): Z, Y, X önceliği
        - Volume: Hacim optimizasyonu
        """
        if self.heuristic == 'CP':
            return self._score_contact_point_3d(x, y, z, w, l, h, piece_id)
        elif self.heuristic == 'BSSF':
            return self._score_bottom_left_3d(x, y, z)
        else:
            return self._score_bottom_left_3d(x, y, z)
    
    def _score_contact_point_3d(self, x: int, y: int, z: int,
                                 w: int, l: int, h: int,
                                 piece_id: Optional[str]) -> float:
        """Contact Point heuristic (3D)"""
        contact = 0
        
        # Duvar temasları
        if x == 0: contact += l * h
        if y == 0: contact += w * h
        if z == 0: contact += w * l  # Zemin (ÖNEMLİ!)
        
        if x + w == self.width: contact += l * h
        if y + l == self.length: contact += w * h
        if z + h == self.height: contact += w * l
        
        # Palet temasları
        for p in self.placements:
            # Alttan/üstten temas (en önemli)
            if abs(z - (p.z + p.height)) < 1 or abs((z + h) - p.z) < 1:
                overlap_area = self._calculate_xy_overlap(
                    x, y, w, l, p.x, p.y, p.width, p.length
                )
                contact += overlap_area * 2  # Alttan/üstten temas önemli
            
            # Yandan temaslar
            # X ekseni
            if abs(x + w - p.x) < 1 or abs(p.x + p.width - x) < 1:
                overlap = self._calculate_yz_overlap(
                    y, z, l, h, p.y, p.z, p.length, p.height
                )
                contact += overlap
            
            # Y ekseni
            if abs(y + l - p.y) < 1 or abs(p.y + p.length - y) < 1:
                overlap = self._calculate_xz_overlap(
                    x, z, w, h, p.x, p.z, p.width, p.height
                )
                contact += overlap
        
        # Teslimat sırası cezası
        priority_penalty = 0
        if piece_id and self.piece_info:
            piece = self.piece_info.get(piece_id)
            if piece and piece.priority is not None:
                # Öncelik düşükse (erken teslimat) kapıya yakın olmalı
                ideal_y = piece.priority * 50  # Her priority seviyesi 50cm
                y_deviation = abs(y - ideal_y)
                priority_penalty = y_deviation * 0.1
        
        # Düşük skor = iyi
        score = -contact * 1000 + z * 1500 + y * 10 + x + priority_penalty
        return score
    
    def _score_bottom_left_3d(self, x: int, y: int, z: int) -> float:
        """Bottom-Left heuristic: Z öncelikli yerleşim"""
        return z * 1000000 + y * 1000 + x
    
    def _calculate_xy_overlap(self, x1, y1, w1, l1, x2, y2, w2, l2) -> int:
        """XY düzleminde overlap alanı"""
        overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
        overlap_y = max(0, min(y1 + l1, y2 + l2) - max(y1, y2))
        return overlap_x * overlap_y
    
    def _calculate_yz_overlap(self, y1, z1, l1, h1, y2, z2, l2, h2) -> int:
        """YZ düzleminde overlap alanı"""
        overlap_y = max(0, min(y1 + l1, y2 + l2) - max(y1, y2))
        overlap_z = max(0, min(z1 + h1, z2 + h2) - max(z1, z2))
        return overlap_y * overlap_z
    
    def _calculate_xz_overlap(self, x1, z1, w1, h1, x2, z2, w2, h2) -> int:
        """XZ düzleminde overlap alanı"""
        overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
        overlap_z = max(0, min(z1 + h1, z2 + h2) - max(z1, z2))
        return overlap_x * overlap_z
    
    def place_piece_3d(self, piece_id: str, placement: Tuple) -> None:
        """
        Parçayı 3D olarak yerleştir ve free cuboid'leri güncelle
        """
        x, y, z, w, l, h, rot = placement
        
        new_placement = Placement3D(x, y, z, w, l, h, piece_id, rot, 0)
        self.placements.append(new_placement)
        
        # Free cuboid'leri böl
        new_cuboids = []
        for cuboid in self.free_cuboids:
            new_cuboids.extend(self._split_cuboid_3d(cuboid, x, y, z, w, l, h))
        
        # Gereksizleri temizle
        self.free_cuboids = self._prune_cuboids_3d(new_cuboids)
    
    def _split_cuboid_3d(self, cuboid: Cuboid,
                          x: int, y: int, z: int,
                          w: int, l: int, h: int) -> List[Cuboid]:
        """
        3D cuboid bölme (karmaşık geometri!)
        
        Bir cuboid, yerleştirme ile kesildiğinde en fazla 6 yeni cuboid oluşur:
        - Alt, üst (Z ekseni)
        - Sol, sağ (X ekseni)
        - Ön, arka (Y ekseni)
        """
        cx, cy, cz = cuboid.x, cuboid.y, cuboid.z
        cw, cl, ch = cuboid.width, cuboid.length, cuboid.height
        
        # Kesişme var mı?
        if (x >= cx + cw or x + w <= cx or
            y >= cy + cl or y + l <= cy or
            z >= cz + ch or z + h <= cz):
            # Kesişme yok, cuboid aynen kalır
            return [cuboid]
        
        new_cuboids = []
        
        # 1. ALT cuboid (Z ekseni, altında kalan)
        if z > cz:
            new_cuboids.append(Cuboid(cx, cy, cz, cw, cl, z - cz))
        
        # 2. ÜST cuboid (Z ekseni, üstünde kalan)
        if z + h < cz + ch:
            new_cuboids.append(Cuboid(cx, cy, z + h, cw, cl, (cz + ch) - (z + h)))
        
        # 3. SOL cuboid (X ekseni, solunda kalan)
        if x > cx:
            new_cuboids.append(Cuboid(cx, cy, z, x - cx, cl, h))
        
        # 4. SAĞ cuboid (X ekseni, sağında kalan)
        if x + w < cx + cw:
            new_cuboids.append(Cuboid(x + w, cy, z, (cx + cw) - (x + w), cl, h))
        
        # 5. ÖN cuboid (Y ekseni, önünde kalan)
        if y > cy:
            new_cuboids.append(Cuboid(x, cy, z, w, y - cy, h))
        
        # 6. ARKA cuboid (Y ekseni, arkasında kalan)
        if y + l < cy + cl:
            new_cuboids.append(Cuboid(x, y + l, z, w, (cy + cl) - (y + l), h))
        
        # Geçerli cuboid'leri döndür
        return [c for c in new_cuboids if c.get_volume() > 0]
    
    def _prune_cuboids_3d(self, cuboids: List[Cuboid]) -> List[Cuboid]:
        """
        Gereksiz cuboid'leri temizle
        (Bir cuboid başka bir cuboid içindeyse gereksizdir)
        """
        pruned = []
        for i, c1 in enumerate(cuboids):
            contained = False
            for j, c2 in enumerate(cuboids):
                if i != j and self._contains_cuboid(c2, c1):
                    contained = True
                    break
            if not contained:
                pruned.append(c1)
        return pruned
    
    def _contains_cuboid(self, outer: Cuboid, inner: Cuboid) -> bool:
        """outer, inner'ı tamamen içeriyor mu?"""
        return (inner.x >= outer.x and
                inner.y >= outer.y and
                inner.z >= outer.z and
                inner.x + inner.width <= outer.x + outer.width and
                inner.y + inner.length <= outer.y + outer.length and
                inner.z + inner.height <= outer.z + outer.height)
