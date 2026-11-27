"""E-mail de reserva, com a biblioteca padrão. Sem SMTP configurado, não envia."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from ..config import get_settings
from .base import EmailSender, Message, SendFailed


class SmtpEmailSender(EmailSender):
    def __init__(self) -> None:
        settings = get_settings()
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._from = settings.email_from

    def send(self, to: str, message: Message) -> None:
        if not self._host:
            raise SendFailed("SMTP não configurado")

        email = EmailMessage()
        email["Subject"] = message.title
        email["From"] = self._from
        email["To"] = to
        email.set_content(f"{message.body}\n\n{message.url}")

        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as servidor:
                servidor.starttls()
                if self._user:
                    servidor.login(self._user, self._password)
                servidor.send_message(email)
        except OSError as erro:
            raise SendFailed(str(erro)) from erro
