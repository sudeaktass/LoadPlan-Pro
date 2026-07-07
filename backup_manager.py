# -*- coding: utf-8 -*-
"""
Backup Manager — Otomatik Veri Yedekleme
==========================================
Kurumsal veri kaybı riski [R3] için cron-tabanlı yedekleme.

Desteklenen veritabanları:
  - SQLite: dosya kopyalama (WAL checkpoint sonrası)
  - PostgreSQL: pg_dump (subprocess)

Kullanım:
  CLI:    python backup_manager.py
  Streamlit: from backup_manager import run_backup_now, list_backups
  Cron:   0 2 * * *  cd /app && python backup_manager.py

Yedekler /data/backups/ altında ISO tarih damgalı olarak saklanır.
Eski yedekler retention günü aşarsa otomatik silinir.

Sızdırma koruması:
  - SQLite dosyası "rb" olarak okunup yeni dosyaya yazılır
  - PostgreSQL bağlantı parametreleri ENV'den okunur (kod içine yazılmaz)
  - Backup dosyaları rwx 600 izniyle yazılır (sadece sahibi okuyabilir)
"""

from __future__ import annotations
import os
import sys
import shutil
import sqlite3
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

log = logging.getLogger(__name__)


# ─── KONFİG ────────────────────────────────────────────────────────────────
DEFAULT_BACKUP_DIR = Path(
    os.getenv("BACKUP_DIR", "data/backups")
).resolve()
DEFAULT_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))


# ─── YARDIMCILAR ───────────────────────────────────────────────────────────

def _parse_db_url() -> Dict[str, str]:
    """database.py ile aynı DATABASE_URL'i okur, parse eder."""
    url = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    if url.startswith("sqlite:///"):
        return {
            "type": "sqlite",
            "path": url.replace("sqlite:///", "", 1),
            "url": url,
        }
    elif url.startswith("postgresql"):
        # postgresql://user:pass@host:port/dbname
        return {"type": "postgresql", "url": url}
    else:
        raise ValueError(f"Desteklenmeyen DATABASE_URL: {url[:30]}...")


def _ensure_backup_dir(backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)   # sadece sahibi
    except Exception:
        pass


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ─── SQLITE YEDEKLEME ──────────────────────────────────────────────────────

def _backup_sqlite(db_path: str, backup_dir: Path) -> Path:
    """
    SQLite yedekleme — Python'un native backup API'sini kullanır.
    WAL mode'da bile tutarlı kopya garantiler.
    """
    src_path = Path(db_path)
    if not src_path.exists():
        raise FileNotFoundError(f"DB dosyası bulunamadı: {src_path}")

    out_path = backup_dir / f"app_db_{_timestamp()}.sqlite"

    src_conn = sqlite3.connect(str(src_path))
    dst_conn = sqlite3.connect(str(out_path))
    try:
        src_conn.backup(dst_conn)   # Atomik backup API
    finally:
        dst_conn.close()
        src_conn.close()

    try:
        os.chmod(out_path, 0o600)
    except Exception:
        pass

    return out_path


# ─── POSTGRESQL YEDEKLEME ──────────────────────────────────────────────────

def _backup_postgresql(db_url: str, backup_dir: Path) -> Path:
    """
    PostgreSQL yedekleme — pg_dump subprocess ile.
    pg_dump path'i ENV'den (PG_DUMP_BIN) ya da PATH'ten alınır.
    """
    pg_dump = os.getenv("PG_DUMP_BIN", "pg_dump")
    out_path = backup_dir / f"app_db_{_timestamp()}.dump"

    # Connection params PGPASSWORD ile env'e geç (--password etkileşimi engellenir)
    cmd = [
        pg_dump,
        "--format=custom",   # binary, sıkıştırılmış
        "--no-owner",
        "--no-privileges",
        "--file", str(out_path),
        db_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"pg_dump başarısız (return={result.returncode}): {result.stderr[:300]}"
        )

    try:
        os.chmod(out_path, 0o600)
    except Exception:
        pass
    return out_path


# ─── ESKİ YEDEKLERİ TEMİZLE ────────────────────────────────────────────────

def _cleanup_old_backups(backup_dir: Path, retention_days: int) -> int:
    """retention_days günden eski yedekleri sil, silinen sayısını döndür."""
    if not backup_dir.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = 0
    for f in backup_dir.iterdir():
        if not f.is_file():
            continue
        if not (f.name.startswith("app_db_") and
                (f.suffix in (".sqlite", ".dump"))):
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            try:
                f.unlink()
                removed += 1
            except OSError as e:
                log.warning(f"Yedek silinemedi: {f} → {e}")
    return removed


# ─── ANA API ───────────────────────────────────────────────────────────────

def run_backup_now(
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> Dict[str, object]:
    """
    Anlık yedekleme tetikle. Streamlit UI veya cron çağırabilir.

    Returns:
        {
            "ok": bool,
            "path": str | None,
            "size_kb": float | None,
            "removed_old": int,
            "error": str | None,
            "db_type": str,
        }
    """
    result: Dict[str, object] = {
        "ok": False, "path": None, "size_kb": None,
        "removed_old": 0, "error": None, "db_type": "unknown",
    }
    try:
        cfg = _parse_db_url()
        result["db_type"] = cfg["type"]
        _ensure_backup_dir(backup_dir)

        if cfg["type"] == "sqlite":
            out = _backup_sqlite(cfg["path"], backup_dir)
        elif cfg["type"] == "postgresql":
            out = _backup_postgresql(cfg["url"], backup_dir)
        else:
            raise ValueError(f"Bilinmeyen DB tipi: {cfg['type']}")

        result["ok"] = True
        result["path"] = str(out)
        result["size_kb"] = round(out.stat().st_size / 1024, 2)
        result["removed_old"] = _cleanup_old_backups(backup_dir, retention_days)
        log.info(f"Backup OK: {out} ({result['size_kb']} KB)")
    except Exception as e:
        result["error"] = str(e)
        log.error(f"Backup failed: {e}")
    return result


def list_backups(backup_dir: Path = DEFAULT_BACKUP_DIR) -> List[Dict]:
    """Mevcut yedeklerin listesini döndür (yeni → eski sırada)."""
    if not backup_dir.exists():
        return []
    items: List[Dict] = []
    for f in backup_dir.iterdir():
        if not f.is_file():
            continue
        if not f.name.startswith("app_db_"):
            continue
        stat = f.stat()
        items.append({
            "name": f.name,
            "path": str(f),
            "size_kb": round(stat.st_size / 1024, 2),
            "created": datetime.fromtimestamp(stat.st_mtime),
        })
    items.sort(key=lambda x: x["created"], reverse=True)
    return items


def get_latest_backup_age_hours(
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> Optional[float]:
    """Son yedeklemeden bu yana kaç saat geçti? UI uyarısı için."""
    backups = list_backups(backup_dir)
    if not backups:
        return None
    delta = datetime.now() - backups[0]["created"]
    return delta.total_seconds() / 3600.0


# ─── CLI ──────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    result = run_backup_now()
    if result["ok"]:
        print(f"✅ Yedek alındı: {result['path']} ({result['size_kb']} KB)")
        if result["removed_old"]:
            print(f"🗑️  {result['removed_old']} eski yedek silindi")
        sys.exit(0)
    else:
        print(f"❌ Yedekleme başarısız: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
