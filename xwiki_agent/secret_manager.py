"""Helpers para cargar credenciales de XWiki desde almacenes seguros."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

try:
    import keyring  # type: ignore
    from keyring.errors import KeyringError  # type: ignore
except ImportError:  # pragma: no cover - la dependencia es opcional
    keyring = None  # type: ignore

    class KeyringError(Exception):  # type: ignore
        """Fallback cuando keyring no está instalado."""


class SecretRetrievalError(RuntimeError):
    """Error lanzado cuando no se pueden obtener credenciales de manera segura."""


@dataclass(frozen=True)
class XWikiCredentials:
    """Contenedor seguro que evita exponer el password en representaciones."""

    username: str
    password: str
    source: str

    def __repr__(self) -> str:  # pragma: no cover - comportamiento trivial
        return f"XWikiCredentials(username='{self.username}', source='{self.source}')"


def _load_from_keyring(service: str, username_hint: Optional[str]) -> Optional[XWikiCredentials]:
    if not keyring:
        logging.debug("keyring no está disponible; se omite el acceso al almacén seguro")
        return None

    try:
        credential = getattr(keyring, "get_credential", None)
        if callable(credential):
            result = credential(service, username_hint)
            if result and result.password:
                username = result.username or username_hint
                if username and result.password:
                    return XWikiCredentials(username=username, password=result.password, source=f"keyring:{service}")
        if username_hint:
            password = keyring.get_password(service, username_hint)
            if password:
                return XWikiCredentials(username=username_hint, password=password, source=f"keyring:{service}")
    except KeyringError as exc:
        logging.error("No se pudo recuperar la credencial desde keyring: %s", exc)
    return None


def _load_from_command(command: str) -> Optional[XWikiCredentials]:
    """Permite obtener usuario:password ejecutando un comando externo."""
    import subprocess  # import local para evitar costos si no se usa

    try:
        completed = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        logging.error("Falló la ejecución del comando de secretos '%s': %s", command, exc)
        return None

    payload = (completed.stdout or "").strip()
    if not payload:
        logging.error("El comando de secretos '%s' no devolvió datos", command)
        return None

    parts = payload.split(":", maxsplit=1)
    if len(parts) != 2:
        logging.error("El comando de secretos debe devolver datos en el formato usuario:contraseña")
        return None
    username, password = (segment.strip() for segment in parts)
    if not username or not password:
        logging.error("El comando de secretos devolvió un usuario o contraseña vacío")
        return None
    return XWikiCredentials(username=username, password=password, source=f"command:{command}")


def _load_from_env() -> Optional[XWikiCredentials]:
    username = os.environ.get("XWIKI_USER")
    password = os.environ.get("XWIKI_PASS")
    if username and password:
        logging.warning(
            "Usando credenciales de XWiki desde variables de entorno. Considera migrarlas a un almacén seguro."
        )
        return XWikiCredentials(username=username, password=password, source="env")
    return None


@lru_cache(maxsize=1)
def load_xwiki_credentials() -> XWikiCredentials:
    """Obtiene las credenciales de XWiki priorizando mecanismos seguros."""

    service = os.environ.get("XWIKI_KEYRING_SERVICE")
    username_hint = os.environ.get("XWIKI_KEYRING_USERNAME") or os.environ.get("XWIKI_USER")
    if service:
        from_keyring = _load_from_keyring(service, username_hint)
        if from_keyring:
            return from_keyring

    secret_command = os.environ.get("XWIKI_SECRET_COMMAND")
    if secret_command:
        from_command = _load_from_command(secret_command)
        if from_command:
            return from_command

    from_env = _load_from_env()
    if from_env:
        return from_env

    raise SecretRetrievalError(
        "No se encontraron credenciales de XWiki. Configura 'XWIKI_KEYRING_SERVICE' + 'XWIKI_KEYRING_USERNAME' en el almacén seguro, "
        "un comando en 'XWIKI_SECRET_COMMAND' que devuelva usuario:contraseña, o bien variables de entorno 'XWIKI_USER' y 'XWIKI_PASS'."
    )


def get_masked_username() -> Optional[str]:
    """Devuelve el usuario parcialmente ofuscado para fines de logging o diagnósticos."""
    try:
        creds = load_xwiki_credentials()
    except SecretRetrievalError:
        return None
    if len(creds.username) <= 4:
        return creds.username
    return f"{creds.username[:2]}***{creds.username[-1]}"
