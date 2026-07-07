# -*- coding: utf-8 -*-
"""
STL Debug Aracı
===============
Kullanım:
    python test_stl_debug.py parca.stl

Çıktı:
    - Bounding box boyutları
    - Mesh istatistikleri
    - Plotly HTML dosyası (tarayıcıda aç)
"""
import sys
from pathlib import Path

def test_stl(filepath: str):
    try:
        import trimesh
    except ImportError:
        print("❌ trimesh kurulu değil: pip install trimesh")
        return

    print(f"\n📂 Dosya: {filepath}")
    mesh = trimesh.load(filepath, force='mesh')

    if mesh is None or mesh.is_empty:
        print("❌ Mesh boş veya yüklenemedi!")
        return

    print("✅ Mesh yüklendi")
    print(f"   Vertex sayısı : {len(mesh.vertices):,}")
    print(f"   Yüz (face) sayısı: {len(mesh.faces):,}")
    print(f"   Watertight     : {mesh.is_watertight}")

    # Ham boyutlar (mm — SolidWorks varsayılanı)
    b = mesh.bounds
    raw_w = b[1][0] - b[0][0]
    raw_l = b[1][1] - b[0][1]
    raw_h = b[1][2] - b[0][2]
    print(f"\n📐 Ham boyutlar (mm):  {raw_w:.1f} × {raw_l:.1f} × {raw_h:.1f}")

    # cm'ye çevir (x0.1)
    mesh.apply_scale(0.1)
    b = mesh.bounds
    w = b[1][0] - b[0][0]
    l = b[1][1] - b[0][1]
    h = b[1][2] - b[0][2]
    print(f"📐 cm boyutlar:        {w:.2f} × {l:.2f} × {h:.2f}")
    print(f"📦 Hacim: {mesh.volume:.1f} cm³  |  Doluluk: %{mesh.volume/(w*l*h)*100:.1f}")

    # Plotly görsel
    try:
        import plotly.graph_objects as go
        import numpy as np

        verts = np.array(mesh.vertices) - np.array(mesh.vertices).min(axis=0)
        faces = np.array(mesh.faces)

        fig = go.Figure(go.Mesh3d(
            x=verts[:, 0], y=verts[:, 1], z=verts[:, 2],
            i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
            color='#2196F3', opacity=0.85, flatshading=True,
            lighting=dict(ambient=0.6, diffuse=0.7, specular=0.3),
            name=Path(filepath).stem,
        ))
        fig.update_layout(
            title=f"STL Önizleme — {Path(filepath).name}  |  {w:.1f}×{l:.1f}×{h:.1f} cm",
            scene=dict(aspectmode='data',
                       xaxis_title="Genişlik (cm)",
                       yaxis_title="Uzunluk (cm)",
                       zaxis_title="Yükseklik (cm)"),
            paper_bgcolor="#0d1117",
            font=dict(color="#e6edf3"),
        )
        out = Path(filepath).stem + "_preview.html"
        fig.write_html(out)
        print(f"\n🌐 Görsel kaydedildi: {out}  (tarayıcıda aç)")
    except ImportError:
        print("⚠️ plotly kurulu değil, görsel oluşturulamadı.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python test_stl_debug.py <dosya.stl>")
    else:
        test_stl(sys.argv[1])
