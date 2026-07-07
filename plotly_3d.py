# -*- coding: utf-8 -*-
"""
3D Bin Packing Visualization — Plotly  (v6 — düzensiz şekil desteği)
Eklenenler:
  · NFP cross-section nesting görselleştirme (L/T/I/Poligon)
  · İçi boş boru (hollow cylinder) mesh
  · Şirket renk teması
"""
import math
import plotly.graph_objects as go

BG_COLOR      = '#0D1117'
SCENE_BG      = '#0D1117'
GRID_COLOR    = 'rgba(56,139,253,0.15)'
TRUCK_EDGE    = 'rgba(56,139,253,0.85)'
TITLE_COLOR   = '#E6EDF3'
LEGEND_BG     = 'rgba(22,27,34,0.92)'
LEGEND_BORDER = 'rgba(56,139,253,0.4)'
TEXT_COLOR    = '#8B949E'

COLORS = [
    '#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD',
    '#98D8C8','#F7DC6F','#BB8FCE','#85C1E9','#F8C471','#82E0AA',
    '#F1948A','#76D7C4','#AED6F1','#FAD7A0','#A9CCE3','#A8D5A2',
    '#F9A7B0','#C39BD3','#7FB3D3','#52BE80','#EB984E','#AF7AC5',
]
CYL_SEGMENTS = 32


def _box_mesh(x, y, z, w, l, h, color, opacity, name, hover_extra=''):
    vx = [x,   x+w, x+w, x,   x,   x+w, x+w, x  ]
    vy = [y,   y,   y+l, y+l, y,   y,   y+l, y+l]
    vz = [z,   z,   z,   z,   z+h, z+h, z+h, z+h]
    hover = (f"<b>📦 {name}</b><br>Konum: ({x}, {y}, {z}) cm<br>"
             f"Boyut: {w} × {l} × {h} cm<br>" + hover_extra + "<extra></extra>")
    return go.Mesh3d(
        x=vx, y=vy, z=vz, alphahull=0, color=color, opacity=opacity,
        flatshading=True,
        lighting=dict(ambient=0.55, diffuse=0.70, specular=0.35, roughness=0.6, fresnel=0.2),
        lightposition=dict(x=200, y=-300, z=500),
        name=name, showlegend=True, hovertemplate=hover,
    )


def _cylinder_mesh(x, y, z, diameter, height, color, opacity, name, hover_extra=''):
    r = diameter / 2.0; cx = x + r; cy = y + r; n = CYL_SEGMENTS
    angles = [2 * math.pi * i / n for i in range(n)]
    rim_x = [cx + r * math.cos(a) for a in angles]
    rim_y = [cy + r * math.sin(a) for a in angles]
    vx = rim_x + rim_x + [cx, cx]
    vy = rim_y + rim_y + [cy, cy]
    vz = [z]*n + [z+height]*n + [z, z+height]
    bc = 2*n; tc = 2*n + 1
    ti, tj, tk = [], [], []
    for i in range(n):
        ni = (i + 1) % n
        ti += [bc, tc, i,  ni]; tj += [i,  n+i, ni, n+ni]; tk += [ni, n+ni, n+i, n+i]
    hover = (f"<b>🔵 {name}</b><br>Konum: ({x:.0f}, {y:.0f}, {z:.0f}) cm<br>"
             f"Çap: {diameter} cm · Yükseklik: {height} cm<br>" + hover_extra + "<extra></extra>")
    return go.Mesh3d(
        x=vx, y=vy, z=vz, i=ti, j=tj, k=tk, color=color, opacity=opacity, flatshading=True,
        lighting=dict(ambient=0.55, diffuse=0.70, specular=0.35, roughness=0.6, fresnel=0.2),
        lightposition=dict(x=200, y=-300, z=500),
        name=name, showlegend=True, hovertemplate=hover,
    )


def _stl_mesh(x_off, y_off, z_off, vertices, faces, color, opacity, name, hover_extra=''):
    """
    STL / STEP dosyasından gelen gerçek mesh verisini Plotly Mesh3d olarak çizer.
    vertices: (N, 3) numpy array — cm cinsinden, orijinden başlayan (bbox'a göre hizalanmış)
    faces:    (M, 3) numpy array — üçgen vertex indeksleri
    x_off, y_off, z_off: yerleşim konumu (cm)
    """
    import numpy as np
    v = np.array(vertices, dtype=float)
    f = np.array(faces, dtype=int)

    # Mesh'i bounding-box köşesine taşı (orijin = 0,0,0 olmalı)
    v_min = v.min(axis=0)
    v = v - v_min  # normalize

    vx = (v[:, 0] + x_off).tolist()
    vy = (v[:, 1] + y_off).tolist()
    vz = (v[:, 2] + z_off).tolist()

    hover = (f"<b>🔷 {name}</b><br>Konum: ({x_off:.0f}, {y_off:.0f}, {z_off:.0f}) cm<br>"
             + hover_extra + "<extra></extra>")
    return go.Mesh3d(
        x=vx, y=vy, z=vz,
        i=f[:, 0].tolist(), j=f[:, 1].tolist(), k=f[:, 2].tolist(),
        color=color, opacity=opacity, flatshading=True,
        lighting=dict(ambient=0.55, diffuse=0.70, specular=0.35, roughness=0.6, fresnel=0.2),
        lightposition=dict(x=200, y=-300, z=500),
        name=name, showlegend=True, hovertemplate=hover,
    )


def _hollow_cylinder_mesh(x, y, z, outer_diameter, inner_diameter, height,
                          color, opacity, name, hover_extra=''):
    """İçi boş boru (tüp) mesh — dış yüzey + iç yüzey + üst/alt halka."""
    ro = outer_diameter / 2.0
    ri = max(min(inner_diameter / 2.0, ro * 0.98), 0.0)
    if ri <= 0:
        # İç çap yoksa düz silindir olarak çiz
        return _cylinder_mesh(x, y, z, outer_diameter, height, color, opacity, name, hover_extra)
    cx = x + ro
    cy = y + ro
    n = CYL_SEGMENTS
    angles = [2 * math.pi * i / n for i in range(n)]

    # 4 × n vertex:
    # 0..n-1  : alt dış halka   n..2n-1 : üst dış halka
    # 2n..3n-1: alt iç halka    3n..4n-1: üst iç halka
    vx, vy, vz = [], [], []
    for a in angles:
        vx.append(cx + ro * math.cos(a)); vy.append(cy + ro * math.sin(a)); vz.append(z)
    for a in angles:
        vx.append(cx + ro * math.cos(a)); vy.append(cy + ro * math.sin(a)); vz.append(z + height)
    for a in angles:
        vx.append(cx + ri * math.cos(a)); vy.append(cy + ri * math.sin(a)); vz.append(z)
    for a in angles:
        vx.append(cx + ri * math.cos(a)); vy.append(cy + ri * math.sin(a)); vz.append(z + height)

    ti, tj, tk = [], [], []
    for i in range(n):
        ni = (i + 1) % n
        # Dış yüzey (2 üçgen)
        ti += [i,       ni    ]; tj += [ni,    n+ni   ]; tk += [n+i,    n+i   ]
        # İç yüzey (ters winding — içe bakan normallar)
        ti += [2*n+i,   3*n+i ]; tj += [3*n+i, 3*n+ni ]; tk += [2*n+ni, 2*n+ni]
        # Üst halka (annulus)
        ti += [n+i,     n+ni  ]; tj += [n+ni,  3*n+ni ]; tk += [3*n+i,  3*n+i ]
        # Alt halka (annulus): quad A=i, B=ni, C=2n+ni, D=2n+i → iki üçgen ABC + ACD
        ti += [i,    i    ]; tj += [ni,   2*n+ni]; tk += [2*n+ni, 2*n+i]

    hover = (f"<b>🔵 {name}</b><br>Konum: ({x:.0f}, {y:.0f}, {z:.0f}) cm<br>"
             f"Dış Çap: {outer_diameter:.0f} cm · İç Çap: {inner_diameter:.0f} cm · "
             f"Yükseklik: {height:.0f} cm<br>" + hover_extra + "<extra></extra>")
    return go.Mesh3d(
        x=vx, y=vy, z=vz, i=ti, j=tj, k=tk,
        color=color, opacity=opacity, flatshading=True,
        lighting=dict(ambient=0.55, diffuse=0.70, specular=0.35, roughness=0.6, fresnel=0.2),
        lightposition=dict(x=200, y=-300, z=500),
        name=name, showlegend=True, hovertemplate=hover,
    )


def _polygon_extrude_mesh(x_off, y_off, z_off, polygon, height, color, opacity, name, hover_extra=''):
    """Shapely Polygon → Plotly Mesh3d extrude (L/T/I/Poligon profiller için)."""
    try:
        coords = list(polygon.exterior.coords[:-1])
        n = len(coords)
        vx = [c[0]+x_off for c in coords] + [c[0]+x_off for c in coords]
        vy = [c[1]+y_off for c in coords] + [c[1]+y_off for c in coords]
        vz = [z_off]*n + [z_off+height]*n
        ti, tj, tk = [], [], []
        for i in range(n):
            ni = (i + 1) % n
            ti += [i, ni, i, ni]; tj += [ni, n+ni, n+i, n+i]; tk += [n+i, i, ni, n+ni]
        cx = sum(c[0] for c in coords)/n + x_off
        cy = sum(c[1] for c in coords)/n + y_off
        vx += [cx, cx]; vy += [cy, cy]; vz += [z_off, z_off+height]
        bc = 2*n; tc = 2*n+1
        for i in range(n):
            ni = (i+1) % n
            ti += [bc, tc]; tj += [i, n+i]; tk += [ni, n+ni]
        hover = (f"<b>🔷 {name}</b><br>Konum: ({x_off:.0f}, {y_off:.0f}, {z_off:.0f}) cm<br>"
                 f"Yükseklik: {height} cm<br>" + hover_extra + "<extra></extra>")
        return go.Mesh3d(
            x=vx, y=vy, z=vz, i=ti, j=tj, k=tk,
            color=color, opacity=opacity, flatshading=True,
            lighting=dict(ambient=0.55, diffuse=0.70, specular=0.35, roughness=0.6, fresnel=0.2),
            lightposition=dict(x=200, y=-300, z=500),
            name=name, showlegend=True, hovertemplate=hover,
        )
    except Exception:
        # polygon Shapely değilse (list/None) bounding-box'ı elle hesapla
        try:
            minx, miny, maxx, maxy = polygon.bounds
        except AttributeError:
            if hasattr(polygon, '__iter__'):
                coords = list(polygon)
                xs = [c[0] for c in coords]; ys = [c[1] for c in coords]
                minx, miny, maxx, maxy = min(xs), min(ys), max(xs), max(ys)
            else:
                return None
        return _box_mesh(x_off+minx, y_off+miny, z_off, maxx-minx, maxy-miny, height,
                         color, opacity, name, hover_extra)


def _truck_wireframe(truck):
    W, L, H = truck.width, truck.length, truck.height
    lx, ly, lz = [], [], []
    for (x1,y1,z1),(x2,y2,z2) in [
        [(0,0,0),(W,0,0)],[(W,0,0),(W,L,0)],[(W,L,0),(0,L,0)],[(0,L,0),(0,0,0)],
        [(0,0,H),(W,0,H)],[(W,0,H),(W,L,H)],[(W,L,H),(0,L,H)],[(0,L,H),(0,0,H)],
        [(0,0,0),(0,0,H)],[(W,0,0),(W,0,H)],[(W,L,0),(W,L,H)],[(0,L,0),(0,L,H)],
    ]:
        lx += [x1,x2,None]; ly += [y1,y2,None]; lz += [z1,z2,None]
    return go.Scatter3d(
        x=lx, y=ly, z=lz, mode='lines',
        line=dict(color=TRUCK_EDGE, width=2),
        name='Araç', showlegend=True,
        hovertemplate=f"<b>Araç: {truck.id}</b><br>{W}×{L}×{H} cm<extra></extra>",
    )


def visualize_3d_plan(
    plan, trucks, pieces, bin_id=0, show_truck=True, show_grid=True
) -> go.Figure:
    placements = plan.bins[bin_id] if bin_id < len(plan.bins) else []
    truck_id   = plan.truck_assignments.get(bin_id, trucks[0].id if trucks else "—")
    truck      = next((t for t in trucks if t.id == truck_id), trucks[0] if trucks else None)
    piece_map  = {p.id: p for p in pieces}
    id_colors  = {p.id: COLORS[i % len(COLORS)] for i, p in enumerate(pieces)}

    # ── Ağırlık hesapları ────────────────────────────────────────────────────
    total_weight   = sum(
        (piece_map[pl.piece_id].weight if pl.piece_id in piece_map else 0)
        for pl in placements
    )
    truck_capacity = truck.capacity if truck and hasattr(truck, 'capacity') else None

    # Ağırlık merkezi (CoG)
    wx = wy = wz = 0.0
    for pl in placements:
        pc = piece_map.get(pl.piece_id)
        w  = pc.weight if pc else 0.0
        wx += w * (pl.x + pl.width  / 2)
        wy += w * (pl.y + pl.length / 2)
        wz += w * (pl.z + pl.height / 2)
    if total_weight > 0:
        cog_x = wx / total_weight
        cog_y = wy / total_weight
        cog_z = wz / total_weight
    else:
        cog_x = cog_y = cog_z = 0.0

    # Yanal denge uyarısı (%20'den fazla sapma)
    cog_ok = True
    if truck and total_weight > 0:
        center_x = truck.width / 2
        x_dev = abs(cog_x - center_x) / center_x if center_x > 0 else 0
        cog_ok = x_dev <= 0.20

    fig = go.Figure()
    if show_truck and truck:
        fig.add_trace(_truck_wireframe(truck))

    # ── Ağırlık merkezi işareti + ideal bölge ───────────────────────────────
    # Kaynak: Synák & Nedeliaková (2024), Erbayrak et al. (2021)
    if total_weight > 0 and truck:
        # Üç eksenli denge kontrolü
        from core_3d import (COG_LATERAL_TOL, COG_LONG_TOL,
                              COG_VERTICAL_MAX, COG_FRONT_BIAS,
                              check_weight_balance)
        piece_map_cog = {p.id: p for p in pieces}
        lat_ok, lon_ok, vert_ok, cog_det = check_weight_balance(
            placements, piece_map_cog, truck)
        all_ok = lat_ok and lon_ok and vert_ok

        # Renk: tüm eksenler OK → yeşil, biri bozuk → sarı, ikisi+ → kırmızı
        fails = sum([not lat_ok, not lon_ok, not vert_ok])
        cog_color = '#4CAF50' if fails == 0 else ('#FFB300' if fails == 1 else '#FF5252')

        status_lines = []
        status_lines.append(f"Yanal (X): {'✅' if lat_ok else '⚠️'} dev=%{cog_det.get('x_dev',0)*100:.1f} (lim:%{COG_LATERAL_TOL*100:.0f})")
        status_lines.append(f"Boylamsal (Y): {'✅' if lon_ok else '⚠️'} dev=%{cog_det.get('y_dev',0)*100:.1f} (lim:%{COG_LONG_TOL*100:.0f})")
        status_lines.append(f"Dikey (Z): {'✅' if vert_ok else '⚠️'} yükseklik=%{cog_det.get('z_frac',0)*100:.1f} (maks:%{COG_VERTICAL_MAX*100:.0f})")

        # ── Gerçek CoG noktası ───────────────────────────────────────────────
        fig.add_trace(go.Scatter3d(
            x=[cog_x], y=[cog_y], z=[cog_z],
            mode='markers+text',
            marker=dict(size=12, color=cog_color, symbol='diamond',
                        line=dict(color='white', width=2)),
            text=["⚖️"],
            textfont=dict(color=cog_color, size=14),
            textposition='top center',
            name=f"⚖️ Ağırlık Merkezi {'✅' if all_ok else '⚠️'}",
            showlegend=True,
            hovertemplate=(
                f"<b>⚖️ Ağırlık Merkezi</b><br>"
                f"X: {cog_x:.1f} cm  |  Y: {cog_y:.1f} cm  |  Z: {cog_z:.1f} cm<br>"
                f"Toplam yük: {total_weight:.1f} kg<br><br>"
                + "<br>".join(status_lines)
                + "<extra></extra>"
            ),
        ))

        # ── İdeal CoG: sadece merkez hedef çizgisi (X ekseni) ─────────────
        # Kalabalık bölge kutusu yerine, araç merkezinde tek dikey çizgi
        cx_ideal = truck.width / 2
        cy_ideal = truck.length * COG_FRONT_BIAS
        fig.add_trace(go.Scatter3d(
            x=[cx_ideal, cx_ideal],
            y=[cy_ideal, cy_ideal],
            z=[0, truck.height * COG_VERTICAL_MAX],
            mode='lines',
            line=dict(color='rgba(76,175,80,0.5)', width=3, dash='dash'),
            name='🎯 İdeal CoG Hedefi',
            showlegend=True,
            hovertemplate=(
                "<b>🎯 İdeal CoG Hedefi</b><br>"
                f"X hedef: {cx_ideal:.0f} cm (araç merkezi)<br>"
                f"Y hedef: {cy_ideal:.0f} cm (ön-%{COG_FRONT_BIAS*100:.0f})<br>"
                "<extra></extra>"
            ),
        ))
    seen = set()
    for pl in placements:
        piece  = piece_map.get(pl.piece_id)
        color  = id_colors.get(pl.piece_id, '#CCCCCC')
        w, l, h = pl.width, pl.length, pl.height
        show_leg = pl.piece_id not in seen; seen.add(pl.piece_id)
        winfo = ""
        if piece:
            winfo = f"Ağırlık: {piece.weight:.1f} kg<br>"
            if not getattr(piece, 'is_stackable', True):
                winfo += "🚫 Altına yük konmaz<br>"
            if getattr(piece, 'is_fragile', False):
                winfo += "⛔ Üstüne yük konmaz<br>"
        shape_type    = getattr(piece, '_shape_type', None) if piece else None
        cross_sec     = getattr(piece, '_cross_section', None) if piece else None
        mesh_vertices = getattr(piece, '_mesh_vertices', None) if piece else None
        mesh_faces    = getattr(piece, '_mesh_faces', None) if piece else None
        # ── BUG FIX 4: Gerçek STL geometrisi — ölçek bozma OLMADAN render ──
        import numpy as _np_render
        if shape_type == "custom" and mesh_vertices is not None and mesh_faces is not None:
            # ── Gerçek STL / STEP mesh ──────────────────────────────────────
            # shape_engine zaten cm'e çevirdi ve orijine normalize etti.
            # Sadece placement offset'i ekle — eksenleri bağımsız ÖLÇEKLEME,
            # bu geometriyi kutuya sıkıştırır ve gerçek şekli bozar.
            verts = _np_render.array(mesh_vertices, dtype=float)
            # Orijine normalize (shape_engine yapmışsa bu noop olur)
            verts = verts - verts.min(axis=0)
            v_range = verts.max(axis=0)  # [W, L, H] — mesh'in gerçek boyutu

            # Piece boyutları (int) ile mesh boyutu (float) arasındaki küçük
            # farkı gidermek için TEK bir uniform scale kullan — aspect ratio korunur
            pl_dims   = _np_render.array([float(w), float(l), float(h)])
            mesh_dims = _np_render.array([
                v_range[0] if v_range[0] > 1e-6 else float(w),
                v_range[1] if v_range[1] > 1e-6 else float(l),
                v_range[2] if v_range[2] > 1e-6 else float(h),
            ])
            # En büyük eksen farkını uniform scale olarak kullan
            ratios = pl_dims / mesh_dims
            uniform_scale = float(_np_render.median(ratios))   # outlier'a karşı median
            verts_scaled = verts * uniform_scale

            shape_label = pl.piece_id.split(".")[0]
            dim_info = (f"Gerçek boyut: {mesh_dims[0]:.1f}×{mesh_dims[1]:.1f}×"
                        f"{mesh_dims[2]:.1f} cm<br>")
            tr = _stl_mesh(pl.x, pl.y, pl.z, verts_scaled, mesh_faces,
                           color, 0.85, f"{shape_label} [SW]", dim_info + winfo)
            tr.showlegend = show_leg
            fig.add_trace(tr)
        elif shape_type == "hollow_cylinder":
            # ── İçi boş boru — özel halka mesh ──────────────────────────────
            outer_d = float(w)  # sınırlayıcı kutu genişliği = dış çap
            inner_d = float(getattr(piece, '_inner_diameter', 0) if piece else 0)
            tr = _hollow_cylinder_mesh(pl.x, pl.y, pl.z, outer_d, inner_d, h,
                                       color, 0.85, f"{pl.piece_id} [BORU]", winfo)
            tr.showlegend = show_leg
            fig.add_trace(tr)
        elif shape_type in ("l_profile","t_profile","i_profile","polygon") and cross_sec:
            # ── Parametrik profil mesh (extrude) ────────────────────────────
            label_map = {"l_profile":"L", "t_profile":"T", "i_profile":"I", "polygon":"POL"}
            short = label_map.get(shape_type, shape_type.upper())
            tr = _polygon_extrude_mesh(pl.x, pl.y, pl.z, cross_sec, h, color, 0.85,
                                       f"{pl.piece_id} [{short}]", winfo)
            tr.showlegend = show_leg
            fig.add_trace(tr)
        elif piece and piece.shape == 'cylinder':
            tr = _cylinder_mesh(pl.x, pl.y, pl.z, w, h, color, 0.82, pl.piece_id, winfo)
            tr.showlegend = show_leg; fig.add_trace(tr)
        else:
            clr_check = getattr(piece, '_clearance_cm', 0) if piece else 0
            if clr_check and clr_check > 0:
                # Clearance varsa: şeffaf yer tutucu kutu (algoritma bölgesi)
                tr = _box_mesh(pl.x, pl.y, pl.z, w, l, h, color, 0.08, pl.piece_id, winfo)
            else:
                tr = _box_mesh(pl.x, pl.y, pl.z, w, l, h, color, 0.82, pl.piece_id, winfo)
            tr.showlegend = show_leg; fig.add_trace(tr)

        # ── Min. Aralık görsel göstergesi ──────────────────────────────────
        # Algoritma eff_w/eff_l (clearance dahil) ile yerleştirdi.
        # Görsel: gerçek parça clearance offset'li + turuncu kesik çizgi = güvenlik bölgesi
        clr = getattr(piece, '_clearance_cm', 0) if piece else 0
        # Rotasyon varsa gerçek boyutlar da takas edilmiş olabilir
        # Algoritma eff_w/eff_l'yi rotate ederek yerleştirdi
        # w = pl.width = eff boyut (clearance dahil, possibly rotated)
        # _real_width/_real_length = clearance öncesi ham boyutlar (unrotated)
        _rw_unrot = getattr(piece, '_real_width',  None) if piece else None
        _rl_unrot = getattr(piece, '_real_length', None) if piece else None
        if _rw_unrot is not None and _rl_unrot is not None and clr:
            # Parça rotasyon aldıysa (w != original_w), real boyutları da takas et
            eff_unrot_w = _rw_unrot + 2 * clr
            # Eğer yerleştirilen w, unrotated eff_w'ye yakınsa → rotate edilmemiş
            if abs(w - eff_unrot_w) < 2:
                rw, rl = _rw_unrot, _rl_unrot   # no rotation
            else:
                rw, rl = _rl_unrot, _rw_unrot   # rotated: swap
        else:
            rw = _rw_unrot if _rw_unrot else w
            rl = _rl_unrot if _rl_unrot else l
        if clr and clr > 0 and piece and piece.shape != 'cylinder' and shape_type not in (
                "custom","l_profile","t_profile","i_profile","polygon","hollow_cylinder"):
            # Ana trace'i daha saydam yap (clearance bölgesi zaten çizildi)
            tr.update(opacity=0.55)
            # Gerçek parça — clearance bölgesinin tam ortasında
            real_hover = (f"Gerçek boyut: {rw:.0f}×{rl:.0f}×{h:.0f} cm<br>"
                          f"Min. aralık: {clr} cm her yönde<br>") + winfo
            real_tr = _box_mesh(pl.x + clr, pl.y + clr, pl.z, rw, rl, h,
                                color, 0.92, f"{pl.piece_id}", real_hover)
            real_tr.showlegend = False
            fig.add_trace(real_tr)
            # Güvenlik bölgesi kesik çizgi wireframe (clearance dahil tam kutu)
            _cx, _cy, _cz0 = pl.x, pl.y, pl.z
            _lx, _ly, _lz = [], [], []
            for (x1,y1,z1),(x2,y2,z2) in [
                [(_cx,_cy,_cz0),(_cx+w,_cy,_cz0)],[(_cx+w,_cy,_cz0),(_cx+w,_cy+l,_cz0)],
                [(_cx+w,_cy+l,_cz0),(_cx,_cy+l,_cz0)],[(_cx,_cy+l,_cz0),(_cx,_cy,_cz0)],
                [(_cx,_cy,_cz0+h),(_cx+w,_cy,_cz0+h)],[(_cx+w,_cy,_cz0+h),(_cx+w,_cy+l,_cz0+h)],
                [(_cx+w,_cy+l,_cz0+h),(_cx,_cy+l,_cz0+h)],[(_cx,_cy+l,_cz0+h),(_cx,_cy,_cz0+h)],
                [(_cx,_cy,_cz0),(_cx,_cy,_cz0+h)],[(_cx+w,_cy,_cz0),(_cx+w,_cy,_cz0+h)],
                [(_cx+w,_cy+l,_cz0),(_cx+w,_cy+l,_cz0+h)],[(_cx,_cy+l,_cz0),(_cx,_cy+l,_cz0+h)],
            ]:
                _lx += [x1,x2,None]; _ly += [y1,y2,None]; _lz += [z1,z2,None]
            fig.add_trace(go.Scatter3d(
                x=_lx, y=_ly, z=_lz, mode='lines',
                line=dict(color='rgba(255,200,0,0.6)', width=2, dash='dot'),
                name=f"↔️ {pl.piece_id} güvenlik (+{clr}cm)",
                showlegend=show_leg,
                hovertemplate=(f"<b>↔️ Güvenlik Bölgesi</b><br>"
                               f"{pl.piece_id}: her yönde +{clr} cm boşluk<br>"
                               f"Toplam: {w:.0f}×{l:.0f} cm"
                               "<extra></extra>"),
            ))
    TW = truck.width if truck else 300
    TL = truck.length if truck else 600
    TH = truck.height if truck else 270

    # ── Başlık satırları ────────────────────────────────────────────────────
    weight_str = f"{total_weight:,.0f} kg"
    if truck_capacity:
        pct = total_weight / truck_capacity * 100
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        cap_str = f" / {truck_capacity:,.0f} kg  [{bar}] %{pct:.0f}"
        weight_color = "#FF5252" if pct > 100 else ("#FFB300" if pct > 90 else "#4CAF50")
    else:
        cap_str = ""
        weight_color = "#4CAF50"
    balance_str = "" if cog_ok else "  ⚠️ YANAL DENGE SORUNU"

    title_text = (
        f"🚛 {truck_id}  |  "
        f"📦 {len(placements)}/{sum(p.quantity for p in pieces)} parça  |  "
        f"%{plan.utilization:.1f} doluluk  |  "
        f"⚖️ {weight_str}{cap_str}{balance_str}"
    )


    # ── KAPI YÜZEYI ─────────────────────────────────────────────────────────
    # Y = truck.length düzlemi: tırın kapı tarafını gösterir
    if truck:
        fig.add_trace(go.Mesh3d(
            x=[0, truck.width, truck.width, 0],
            y=[truck.length] * 4,
            z=[0, 0, truck.height, truck.height],
            i=[0, 0], j=[1, 2], k=[2, 3],
            color='rgba(56,139,253,0.12)',
            opacity=0.3,
            name='Kapı',
            showlegend=False,
            hovertemplate='<b>🚪 KAPI</b><extra></extra>',
        ))

    # Ağırlık çubuğu annotation (görselin üstünde)
    annotations = []
    if truck_capacity:
        annotations.append(dict(
            text=(f"<b>Kapasite:</b> {total_weight:,.0f} / {truck_capacity:,.0f} kg  "
                  f"(%{pct:.0f})" + ("  <b style='color:red'>AŞILDI!</b>" if pct > 100 else "")),
            xref="paper", yref="paper", x=0.01, y=1.04,
            showarrow=False,
            font=dict(size=12, color=weight_color),
            bgcolor=BG_COLOR, borderpad=4,
        ))
    if not cog_ok:
        annotations.append(dict(
            text="⚠️ Ağırlık merkezi araç merkezinden >%20 saptı — yükleri dengeleyin!",
            xref="paper", yref="paper", x=0.5, y=1.04,
            showarrow=False,
            font=dict(size=11, color="#FF5252"),
            bgcolor=BG_COLOR, borderpad=4,
        ))


    fig.update_layout(
        title=dict(text=title_text, font=dict(color=TITLE_COLOR, size=13)),
        paper_bgcolor=BG_COLOR,
        scene=dict(
            bgcolor=SCENE_BG,
            xaxis=dict(title="Genişlik (cm)", range=[0, TW+20], backgroundcolor=SCENE_BG,
                       gridcolor=GRID_COLOR, showbackground=True, visible=show_grid),
            yaxis=dict(title="Uzunluk (cm)",  range=[0, TL+20], backgroundcolor=SCENE_BG,
                       gridcolor=GRID_COLOR, showbackground=True, visible=show_grid),
            zaxis=dict(title="Yükseklik (cm)",range=[0, TH+20], backgroundcolor=SCENE_BG,
                       gridcolor=GRID_COLOR, showbackground=True, visible=show_grid),
            aspectmode='data', camera=dict(eye=dict(x=1.5, y=-1.5, z=1.2)),
            # ── KAPI yazısı: 3D scene annotation (x,y,z destekler) ────────
            annotations=[
                dict(
                    x=truck.width / 2 if truck else TW / 2,
                    y=truck.length if truck else TL,
                    z=truck.height / 2 if truck else TH / 2,
                    text="🚪 KAPI",
                    showarrow=False,
                    font=dict(size=16, color='rgba(56,139,253,0.9)'),
                    xanchor='center',
                    yanchor='middle',
                )
            ] if truck else [],
        ),
        legend=dict(font=dict(color=TITLE_COLOR, size=10), bgcolor=LEGEND_BG,
                    bordercolor=LEGEND_BORDER, borderwidth=1),
        margin=dict(l=0, r=0, t=60, b=0), height=560,
        annotations=annotations,
    )
    return fig


def create_weight_distribution_viz(plan, truck, pieces, bin_id=0):
    placements = plan.bins[bin_id] if bin_id < len(plan.bins) else []
    piece_map  = {p.id: p for p in pieces}
    gx_n = gy_n = 5
    grid = [[0.0]*gy_n for _ in range(gx_n)]
    W = truck.width; L = truck.length
    for pl in placements:
        piece = piece_map.get(pl.piece_id)
        if not piece: continue
        gx = min(int((pl.x + pl.width/2) / W * gx_n), gx_n-1)
        gy = min(int((pl.y + pl.length/2) / L * gy_n), gy_n-1)
        grid[gx][gy] += piece.weight
    fig = go.Figure(data=go.Heatmap(
        z=[[grid[gx][gy] for gy in range(gy_n)] for gx in range(gx_n)],
        colorscale='RdYlGn_r',
        colorbar=dict(title='kg', tickfont=dict(color=TITLE_COLOR)),
    ))
    fig.update_layout(
        title=dict(text="⚖️ Ağırlık Dağılımı", font=dict(color=TITLE_COLOR, size=13)),
        paper_bgcolor=BG_COLOR, plot_bgcolor=SCENE_BG,
        xaxis=dict(title="Derinlik (Y)", color=TITLE_COLOR),
        yaxis=dict(title="Genişlik (X)", color=TITLE_COLOR),
        font=dict(color=TITLE_COLOR), height=420,
    )
    return fig


def visualize_nfp_layout(nfp_plot_data, truck_width, truck_length,
                          title="2D Kesit Yerleşim Planı") -> go.Figure:
    """NFP nested packing sonucunu 2D zemin planı olarak gösterir."""
    fig = go.Figure()
    for item in nfp_plot_data:
        coords = item["polygon_coords"]
        xs = [c[0] for c in coords] + [coords[0][0]]
        ys = [c[1] for c in coords] + [coords[0][1]]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, fill='toself', fillcolor=item["color"],
            line=dict(color='white', width=1), opacity=0.75,
            name=item["piece_id"],
            hovertemplate=(f"<b>{item['piece_id']}</b><br>"
                           f"Konum: ({item['x']:.1f}, {item['y']:.1f}) cm<br>"
                           f"Z: {item['z_start']:.0f}–{item['z_end']:.0f} cm<br>"
                           f"Rotasyon: {item['rotation']:.0f}°<extra></extra>"),
        ))
    fig.add_shape(type="rect", x0=0, y0=0, x1=truck_width, y1=truck_length,
                  line=dict(color=TRUCK_EDGE, width=2.5, dash="dash"))
    fig.update_layout(
        title=dict(text=title, font=dict(color=TITLE_COLOR, size=13)),
        paper_bgcolor=BG_COLOR, plot_bgcolor=SCENE_BG,
        xaxis=dict(title="Genişlik (cm)", color=TITLE_COLOR,
                   range=[-5, truck_width+5], scaleanchor="y"),
        yaxis=dict(title="Uzunluk (cm)", color=TITLE_COLOR, range=[-5, truck_length+5]),
        legend=dict(bgcolor=LEGEND_BG, bordercolor=LEGEND_BORDER,
                    font=dict(color=TITLE_COLOR, size=9)),
        height=480, margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig
