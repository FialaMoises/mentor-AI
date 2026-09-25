"""Entrada por link mágico.

Nenhuma senha para guardar: o aluno digita o e-mail, recebe um link com um token
de uso único e curto, e volta com uma sessão. No banco vive só o hash — quem
lê o banco não consegue entrar na conta de ninguém.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuthSession, LoginToken, Student

#: O link vale pouco tempo: é para usar agora, não guardar.
LOGIN_TOKEN_MINUTES = 20
SESSION_DAYS = 30


class AuthError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MagicLink:
    """O token em claro só existe aqui e no e-mail do aluno."""

    token: str
    expires_at: datetime

    def url(self, base: str) -> str:
        return f"{base.rstrip('/')}/entrar?token={self.token}"


@dataclass(frozen=True, slots=True)
class LoggedIn:
    student: Student
    token: str
    expires_at: datetime
    is_new: bool


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    limpo = email.strip().lower()
    if "@" not in limpo or len(limpo) < 5:
        raise AuthError("e-mail inválido")
    return limpo


def request_login(session: Session, email: str, *, now: datetime | None = None) -> MagicLink:
    """Cria o token. Não diz se o e-mail já existe — isso é do dono do e-mail."""
    agora = now or datetime.now(UTC)
    endereco = normalize_email(email)
    token = secrets.token_urlsafe(32)
    expira = agora + timedelta(minutes=LOGIN_TOKEN_MINUTES)

    session.add(LoginToken(email=endereco, token_hash=_hash(token), expires_at=expira))
    session.flush()
    return MagicLink(token=token, expires_at=expira)


def _as_utc(momento: datetime) -> datetime:
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def verify_login(session: Session, token: str, *, now: datetime | None = None) -> LoggedIn:
    """Troca o token pela sessão. Token usado não volta a valer."""
    agora = now or datetime.now(UTC)
    registro = session.scalar(select(LoginToken).where(LoginToken.token_hash == _hash(token)))
    if registro is None:
        raise AuthError("link inválido")
    if registro.used_at is not None:
        raise AuthError("este link já foi usado")
    if _as_utc(registro.expires_at) < agora:
        raise AuthError("link expirado")

    registro.used_at = agora

    aluno = session.scalar(select(Student).where(Student.email == registro.email))
    novo = aluno is None
    if aluno is None:
        aluno = Student(
            phase="faculdade",
            mode="independente",
            email=registro.email,
            subscription_status="trial",
        )
        session.add(aluno)
        session.flush()

    token_sessao = secrets.token_urlsafe(32)
    expira = agora + timedelta(days=SESSION_DAYS)
    session.add(AuthSession(student_id=aluno.id, token_hash=_hash(token_sessao), expires_at=expira))
    session.flush()
    return LoggedIn(student=aluno, token=token_sessao, expires_at=expira, is_new=novo)


def student_for_token(
    session: Session, token: str, *, now: datetime | None = None
) -> Student | None:
    agora = now or datetime.now(UTC)
    sessao = session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
    if sessao is None or sessao.revoked_at is not None:
        return None
    if _as_utc(sessao.expires_at) < agora:
        return None
    return session.get(Student, sessao.student_id)


def logout(session: Session, token: str, *, now: datetime | None = None) -> None:
    sessao = session.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
    if sessao is not None and sessao.revoked_at is None:
        sessao.revoked_at = now or datetime.now(UTC)
        session.flush()


def revoke_all(session: Session, student: Student, *, now: datetime | None = None) -> int:
    """Sai de todos os aparelhos. Usado também antes de apagar a conta."""
    agora = now or datetime.now(UTC)
    sessoes = list(
        session.scalars(
            select(AuthSession).where(
                AuthSession.student_id == student.id, AuthSession.revoked_at.is_(None)
            )
        )
    )
    for sessao in sessoes:
        sessao.revoked_at = agora
    session.flush()
    return len(sessoes)
