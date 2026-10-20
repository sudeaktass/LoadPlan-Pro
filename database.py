# -*- coding: utf-8 -*-
"""
Database — SQLAlchemy ORM (SQLite / PostgreSQL)
================================================
Tablolar:
  · companies  — Şirket profilleri
  · users      — Kullanıcılar (şirketle ilişkili)
  · projects   — Optimizasyon projeleri
  · results    — Algoritma sonuçları

Cloud: PostgreSQL için DATABASE_URL env değişkeni ayarlanır.
       Ayarlanmadıysa SQLite (./data/app.db) kullanılır.
"""

from __future__ import annotations
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text,
    DateTime, Boolean, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

log = logging.getLogger(__name__)

# ─── Veritabanı URL ───────────────────────────────────────────────────────────
_DB_URL = os.getenv("DATABASE_URL", "sqlite:///data/app.db")

# PostgreSQL bağlantı string'i Streamlit Cloud secrets'dan gelebilir
if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)

# SQLite için klasörü oluştur
if _DB_URL.startswith("sqlite:///"):
    _path = Path(_DB_URL.replace("sqlite:///", ""))
    _path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False} if "sqlite" in _DB_URL else {},
    echo=False,
)

# SQLite dayanıklılık: WAL modu eşzamanlı okuma/yazmada "database is locked"
# hatasını büyük ölçüde önler; busy_timeout kalan çakışmalarda 5 sn bekletir.
if _DB_URL.startswith("sqlite"):
    from sqlalchemy import event as _sa_event

    @_sa_event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
        finally:
            cur.close()

# expire_on_commit=False: CRUD fonksiyonları session'ı kapatıp detached nesne
# döndürüyor — commit sonrası attribute expiry, kapalı session'da
# DetachedInstanceError üretirdi. Kolon değerleri artık bellekte kalır.
# (İlişki erişimi — örn. user.company — yine de session gerektirir.)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                            expire_on_commit=False)
Base = declarative_base()


# ============================================================================
# MODELLER
# ============================================================================

class Company(Base):
    __tablename__ = "companies"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(200), nullable=False, unique=True)
    slug       = Column(String(100), nullable=False, unique=True)  # url-safe
    logo_url   = Column(String(500), nullable=True)
    address    = Column(Text, nullable=True)
    phone      = Column(String(50), nullable=True)
    email      = Column(String(200), nullable=True)
    plan       = Column(String(50), default="standard")   # standard / professional / enterprise
    max_users  = Column(Integer, default=5)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active  = Column(Boolean, default=True)

    users    = relationship("User",    back_populates="company", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="company", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, index=True)
    company_id   = Column(Integer, ForeignKey("companies.id"), nullable=False)
    email        = Column(String(200), nullable=False, unique=True)
    full_name    = Column(String(200), nullable=False)
    password_hash = Column(String(200), nullable=False)
    role         = Column(String(50), default="operator")   # admin / manager / operator
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    last_login   = Column(DateTime, nullable=True)

    company  = relationship("Company", back_populates="users")
    projects = relationship("Project", back_populates="owner")


class Project(Base):
    __tablename__ = "projects"

    id           = Column(Integer, primary_key=True, index=True)
    company_id   = Column(Integer, ForeignKey("companies.id"), nullable=False)
    owner_id     = Column(Integer, ForeignKey("users.id"),    nullable=False)
    name         = Column(String(300), nullable=False)
    description  = Column(Text, nullable=True)
    status       = Column(String(50), default="draft")    # draft / running / completed / archived
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # JSON alanlar — tüm giriş ve sonuç verisi
    trucks_json  = Column(Text, nullable=True)    # list[dict]
    pieces_json  = Column(Text, nullable=True)    # list[dict]
    params_json  = Column(Text, nullable=True)    # algoritma parametreleri
    results_json = Column(Text, nullable=True)    # optimizasyon sonuçları

    # Özet metrikler (hızlı sorgulama için)
    best_utilization = Column(Float, nullable=True)
    best_algorithm   = Column(String(100), nullable=True)
    truck_count      = Column(Integer, nullable=True)
    piece_count      = Column(Integer, nullable=True)

    company = relationship("Company", back_populates="projects")
    owner   = relationship("User",    back_populates="projects")

    def get_trucks(self) -> list:
        return json.loads(self.trucks_json) if self.trucks_json else []

    def get_pieces(self) -> list:
        return json.loads(self.pieces_json) if self.pieces_json else []

    def get_params(self) -> dict:
        return json.loads(self.params_json) if self.params_json else {}

    def get_results(self) -> dict:
        return json.loads(self.results_json) if self.results_json else {}

    def set_trucks(self, data: list):
        self.trucks_json = json.dumps(data, ensure_ascii=False)

    def set_pieces(self, data: list):
        self.pieces_json = json.dumps(data, ensure_ascii=False)

    def set_params(self, data: dict):
        self.params_json = json.dumps(data, ensure_ascii=False)

    def set_results(self, data: dict):
        self.results_json = json.dumps(data, ensure_ascii=False)


# ============================================================================
# TABLO OLUŞTUR
# ============================================================================

def init_db():
    """Tüm tabloları oluşturur. Uygulama başlangıcında çağrılır."""
    Base.metadata.create_all(bind=engine)
    log.info(f"Veritabanı hazır: {_DB_URL}")


# ============================================================================
# CRUD OPERASYONLARI
# ============================================================================

def get_session() -> Session:
    return SessionLocal()


# ── Şirket ──────────────────────────────────────────────────────────────────

def create_company(name: str, admin_email: str, admin_name: str,
                   admin_password_hash: str, plan: str = "standard") -> Company:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    db = get_session()
    try:
        co = Company(name=name, slug=slug, plan=plan)
        db.add(co)
        db.flush()
        user = User(company_id=co.id, email=admin_email, full_name=admin_name,
                    password_hash=admin_password_hash, role="admin")
        db.add(user)
        db.commit()
        db.refresh(co)
        return co
    finally:
        db.close()


def get_company(company_id: int) -> Optional[Company]:
    db = get_session()
    try:
        return db.query(Company).filter(Company.id == company_id).first()
    finally:
        db.close()


# ── Kullanıcı ────────────────────────────────────────────────────────────────

def get_user_by_email(email: str) -> Optional[User]:
    db = get_session()
    try:
        return db.query(User).filter(User.email == email).first()
    finally:
        db.close()


def create_user(company_id: int, email: str, full_name: str,
                password_hash: str, role: str = "operator") -> User:
    db = get_session()
    try:
        u = User(company_id=company_id, email=email, full_name=full_name,
                 password_hash=password_hash, role=role)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def update_last_login(user_id: int):
    db = get_session()
    try:
        db.query(User).filter(User.id == user_id).update(
            {"last_login": datetime.utcnow()})
        db.commit()
    finally:
        db.close()


def list_company_users(company_id: int) -> List[User]:
    db = get_session()
    try:
        return db.query(User).filter(User.company_id == company_id).all()
    finally:
        db.close()


# ── Proje ────────────────────────────────────────────────────────────────────

def create_project(company_id: int, owner_id: int, name: str,
                   description: str = "") -> Project:
    db = get_session()
    try:
        p = Project(company_id=company_id, owner_id=owner_id,
                    name=name, description=description)
        db.add(p)
        db.commit()
        db.refresh(p)
        return p
    finally:
        db.close()


def get_project(project_id: int,
                company_id: Optional[int] = None) -> Optional[Project]:
    """company_id verilirse yalnız o şirketin projesi döner (IDOR koruması)."""
    db = get_session()
    try:
        q = db.query(Project).filter(Project.id == project_id)
        if company_id is not None:
            q = q.filter(Project.company_id == company_id)
        return q.first()
    finally:
        db.close()


def list_projects(company_id: int, owner_id: Optional[int] = None,
                  limit: int = 50) -> List[Project]:
    db = get_session()
    try:
        q = db.query(Project).filter(Project.company_id == company_id)
        if owner_id:
            q = q.filter(Project.owner_id == owner_id)
        return q.order_by(Project.updated_at.desc()).limit(limit).all()
    finally:
        db.close()


def save_project_data(project_id: int, trucks: list, pieces: list,
                      params: dict, results: Optional[dict] = None,
                      status: str = "completed") -> bool:
    db = get_session()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            return False
        p.set_trucks(trucks)
        p.set_pieces(pieces)
        p.set_params(params)
        p.status     = status
        p.piece_count = sum(pc.get("adet", pc.get("quantity", 1)) for pc in pieces)
        p.truck_count = sum(t.get("adet", t.get("available", 1)) for t in trucks)
        if results:
            p.set_results(results)
            # En iyi algoritma: (1) en çok yerleşen parça, (2) en az araç,
            # (3) en yüksek doluluk — salt utilization eksik parçalı planı
            # "en iyi" gösterebiliyordu.
            def _rank(k):
                r = results[k]
                return (r.get("placed", 0),
                        -r.get("truck_count", 0),
                        r.get("utilization", 0))
            best_key = max(results, key=_rank)
            p.best_algorithm   = best_key
            p.best_utilization = results[best_key].get("utilization", 0)
        p.updated_at = datetime.utcnow()
        db.commit()
        return True
    except Exception as e:
        log.error(f"Proje kaydedilemedi: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def delete_project(project_id: int,
                   company_id: Optional[int] = None) -> bool:
    """company_id verilirse yalnız o şirketin projesi silinebilir."""
    db = get_session()
    try:
        q = db.query(Project).filter(Project.id == project_id)
        if company_id is not None:
            q = q.filter(Project.company_id == company_id)
        p = q.first()
        if not p:
            return False
        db.delete(p)
        db.commit()
        return True
    finally:
        db.close()


def archive_project(project_id: int,
                    company_id: Optional[int] = None) -> bool:
    """company_id verilirse yalnız o şirketin projesi arşivlenebilir."""
    db = get_session()
    try:
        q = db.query(Project).filter(Project.id == project_id)
        if company_id is not None:
            q = q.filter(Project.company_id == company_id)
        q.update({"status": "archived", "updated_at": datetime.utcnow()},
                 synchronize_session=False)
        db.commit()
        return True
    finally:
        db.close()


# ── Misafir hesabı ───────────────────────────────────────────────────────────

def get_or_create_guest() -> tuple:
    """
    Misafir modu için GERÇEK bir şirket + kullanıcı satırı döndürür.

    Eski davranış owner_id="guest" (string) yazıyordu: SQLite tip esnekliğiyle
    çalışıyor, PostgreSQL'de Integer FK ihlaliyle proje kaydı SESSİZCE
    başarısız oluyordu. Gerçek satır her iki veritabanında da bütünlüğü korur.

    Returns: (Company, User)
    """
    GUEST_EMAIL = "guest@local"
    db = get_session()
    try:
        user = db.query(User).filter(User.email == GUEST_EMAIL).first()
        if user:
            co = db.query(Company).filter(Company.id == user.company_id).first()
            return co, user
        co = db.query(Company).filter(Company.slug == "misafir-local").first()
        if co is None:
            co = Company(name="Misafir Çalışma Alanı", slug="misafir-local",
                         plan="enterprise")
            db.add(co)
            db.flush()
        user = User(company_id=co.id, email=GUEST_EMAIL,
                    full_name="Misafir",
                    password_hash="!",   # kullanılamaz hash — şifreyle giriş yok
                    role="admin")
        db.add(user)
        db.commit()
        db.refresh(co); db.refresh(user)
        return co, user
    finally:
        db.close()


# ── İstatistik ───────────────────────────────────────────────────────────────

def company_stats(company_id: int) -> Dict[str, Any]:
    db = get_session()
    try:
        total = db.query(Project).filter(
            Project.company_id == company_id,
            Project.status != "archived"
        ).count()
        completed = db.query(Project).filter(
            Project.company_id == company_id,
            Project.status == "completed"
        ).count()
        from sqlalchemy import func
        avg_util = db.query(func.avg(Project.best_utilization)).filter(
            Project.company_id == company_id,
            Project.best_utilization.isnot(None)
        ).scalar()
        user_count = db.query(User).filter(
            User.company_id == company_id, User.is_active == True
        ).count()
        return {
            "total_projects":    total,
            "completed_projects": completed,
            "avg_utilization":   round(avg_util or 0, 1),
            "user_count":        user_count,
        }
    finally:
        db.close()
