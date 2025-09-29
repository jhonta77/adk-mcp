# -*- coding: utf-8 -*-
"""Punto de entrada del agente XWiki con manejo mejorado de herramientas."""

# Importaciones necesarias para el funcionamiento del agente.
import asyncio  # Para ejecutar codigo asincrono.
import json  # Para manejar datos en formato JSON.
import logging  # Para reportar avisos e información operativa.
import os  # Para interactuar con el sistema operativo (variables de entorno, rutas).
import sys  # Para informacion especifica del sistema, como la version de Python.
import threading  # Para ejecutar tareas en hilos separados (usado para corutinas).
import re  # Para usar expresiones regulares en la extraccion de texto.
import time  # Para pausar la ejecucion (usado en reintentos).
from datetime import datetime  # Para manejar fechas y horas (en logs).
from pathlib import Path  # Para manejar rutas de archivos en disco.
from typing import Any, Callable  # Para anotaciones de tipo estaticas.

# Carga variables de entorno desde un archivo .env.
from dotenv import load_dotenv

# Componentes del Google ADK (Agent Development Kit).
from google.adk.agents import Agent  # La clase base para crear un agente.
from google.adk.runners import Runner  # Para ejecutar el agente.
from google.adk.sessions import InMemorySessionService  # Un servicio de sesion simple en memoria.
try:
    from google.adk.sessions.sqlite import SqliteSessionService  # Servicio persistente basado en SQLite.
except (ImportError, ModuleNotFoundError):
    SqliteSessionService = None  # type: ignore[assignment]
from google.genai import types  # Tipos de datos usados por la API de Gemini.

# Importa las herramientas personalizadas del servidor. Maneja el caso de ejecucion local.
try:
    from .server import ADK_XWIKI_TOOLS
except ImportError:
    from server import ADK_XWIKI_TOOLS

# --- Constantes para Configuracion --- #

# Nombres de variables de entorno para configurar el comportamiento de los logs y resumenes.
_TOOL_LOG_PATH_ENV = "TOOL_RESPONSE_LOG_PATH"  # Ruta para el log de respuestas completas de herramientas.
_TOOL_SUMMARY_ITEMS_ENV = "TOOL_SUMMARY_MAX_ITEMS"  # Maximo de items en listas para el resumen.
_TOOL_SUMMARY_CHARS_ENV = "TOOL_SUMMARY_MAX_CHARS"  # Maximo de caracteres para el resumen.
_TOOL_SUMMARY_DEPTH_ENV = "TOOL_SUMMARY_MAX_DEPTH"  # Profundidad maxima en estructuras de datos para el resumen.
_TOOL_LOG_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"  # Formato de fecha para los logs.

# Variables para estimar el coste por token (USD por 1M tokens).
_TOKEN_INPUT_COST_ENV = "GEMINI_INPUT_TOKEN_COST_USD"
_TOKEN_OUTPUT_COST_ENV = "GEMINI_OUTPUT_TOKEN_COST_USD"
_TOKEN_CACHE_COST_ENV = "GEMINI_CACHE_TOKEN_COST_USD"
_DEFAULT_INPUT_COST_PER_MILLION = 0.35
_DEFAULT_OUTPUT_COST_PER_MILLION = 1.05
_DEFAULT_CACHE_COST_PER_MILLION = 0.08

# Nombres de variables de entorno y valores para la logica de reintentos ante errores de cuota.
_TOOL_MAX_RETRIES_ENV = "TOOL_API_MAX_RETRIES"  # Maximo numero de reintentos.
_MIN_RETRY_WAIT_SECONDS = 1.0  # Tiempo minimo de espera entre reintentos.
_MAX_RETRY_WAIT_SECONDS = 30.0  # Tiempo maximo de espera entre reintentos.


# --- Funciones Auxiliares para Manejo de Herramientas y Logs --- #

def _default_tool_log_path() -> str:
    """Devuelve la ruta de log por defecto para las cargas utiles completas de las herramientas."""
    # El log se guarda en el mismo directorio que este script.
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, "tool_responses.log")


def _read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _read_int_env(name: str, default: int) -> int:
    """Lee una variable de entorno entera con un fallback seguro."""
    value = os.environ.get(name)
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    # Asegura que el valor sea positivo.
    return parsed if parsed > 0 else default


def _truncate_text(text: str, max_chars: int) -> str:
    """Recorta un texto a la longitud deseada, anadiendo puntos suspensivos."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."


def _trim_structure(value: Any, max_items: int, max_chars: int, max_depth: int, depth: int = 0) -> Any:
    """Recorta recursivamente colecciones grandes para mantener los resumenes legibles."""
    # Evita una recursion infinita o demasiado profunda.
    if depth >= max_depth:
        return "... limite de profundidad alcanzado ..."

    # Si es una lista, recorta los elementos.
    if isinstance(value, list):
        trimmed = [_trim_structure(item, max_items, max_chars, max_depth, depth + 1) for item in value[:max_items]]
        if len(value) > max_items:
            trimmed.append(f"... {len(value) - max_items} items mas omitidos")
        return trimmed

    # Si es un diccionario, recorta los valores de cada clave.
    if isinstance(value, dict):
        trimmed_dict: dict[str, Any] = {}
        for key, item in value.items():
            trimmed_dict[str(key)] = _trim_structure(item, max_items, max_chars, max_depth, depth + 1)
        return trimmed_dict

    # Si es una cadena, la trunca.
    if isinstance(value, str):
        return _truncate_text(value, max_chars)

    # Devuelve cualquier otro tipo de dato sin cambios.
    return value


def _summarise_tool_output(raw_payload: str) -> tuple[str, bool]:
    """Devuelve un resumen legible para humanos y una bandera que indica si fue truncado."""
    # Lee la configuracion desde las variables de entorno.
    max_items = _read_int_env(_TOOL_SUMMARY_ITEMS_ENV, 5)
    max_chars = _read_int_env(_TOOL_SUMMARY_CHARS_ENV, 1500)
    max_depth = _read_int_env(_TOOL_SUMMARY_DEPTH_ENV, 4)
    trimmed_flag = False

    payload = raw_payload.strip()
    if not payload:
        return "(la herramienta no devolvio contenido)", False

    # Intenta parsear el contenido como JSON.
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        # Si no es JSON, lo trata como texto plano y lo trunca.
        summary = _truncate_text(payload, max_chars)
        trimmed_flag = len(summary) < len(payload)
        return summary, trimmed_flag

    # Verifica si la estructura parseada excede los limites para activar la bandera de truncado.
    if isinstance(parsed, list) and len(parsed) > max_items:
        trimmed_flag = True
    elif isinstance(parsed, dict):
        trimmed_flag = any(isinstance(value, list) and len(value) > max_items for value in parsed.values())

    # Recorta la estructura de datos (JSON).
    trimmed_structure = _trim_structure(parsed, max_items, max_chars, max_depth)
    summary = json.dumps(trimmed_structure, ensure_ascii=False, indent=2)

    # Finalmente, trunca el resumen JSON si es demasiado largo.
    if len(summary) > max_chars:
        summary = _truncate_text(summary, max_chars)
        trimmed_flag = True

    return summary, trimmed_flag


def _log_tool_output(tool_name: str, payload: str) -> str | None:
    """Guarda las cargas utiles completas de las herramientas en un archivo de log."""
    log_path = os.environ.get(_TOOL_LOG_PATH_ENV) or _default_tool_log_path()
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.now().strftime(_TOOL_LOG_DATETIME_FORMAT)}] {tool_name}\n")
            handle.write(payload.rstrip())
            handle.write("\n\n")
    except OSError:
        # Si no se puede escribir en el log, no detiene la ejecucion.
        return None
    return log_path


def _normalise_tool_output(output: Any) -> str:
    """Convierte cualquier salida de una herramienta a texto plano."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        # Convierte cada elemento de la lista a texto y los une.
        parts = [_normalise_tool_output(item) for item in output]
        return "\n".join(part for part in parts if part)
    if hasattr(output, "text"):
        # Si el objeto tiene un atributo 'text', lo usa.
        text_value = getattr(output, "text")
        if text_value is not None:
            return str(text_value)
    try:
        # Intenta convertir a JSON como ultimo recurso.
        return json.dumps(output, ensure_ascii=False, default=str)
    except TypeError:
        # Si todo falla, convierte a una representacion de cadena simple.
        return str(output)

# --- Logica de Reintentos para Errores de Cuota de API --- #

def _is_quota_error(exc: Exception) -> bool:
    """Detecta si una excepcion indica un problema de cuota o limite de tasa (rate limit)."""
    message = str(getattr(exc, "message", exc))
    status = getattr(exc, "status", None)
    code = getattr(exc, "code", None)
    http_status = getattr(exc, "status_code", None)

    # Comprueba codigos de estado y mensajes comunes de error de cuota.
    if code == 429 or http_status == 429:
        return True
    if isinstance(status, str) and status.upper() == "RESOURCE_EXHAUSTED":
        return True
    lowered = message.lower()
    return any(token in lowered for token in ("resource_exhausted", "quota exceeded", "quotaexceeded", "rate limit", "429", "cuota agotada"))


def _extract_retry_delay(message: str) -> float | None:
    """Intenta extraer el tiempo de espera recomendado desde el mensaje de error usando expresiones regulares."""
    for pattern in (r"retry in ([0-9]+(?:\.[0-9]+)?)s", r"retryDelay['\"']?: [\'\"']?([0-9]+(?:\.[0-9]+)?)s?"):
        match = re.search(pattern, message)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


def _get_retry_delay_seconds(exc: Exception) -> float | None:
    """Obtiene el tiempo de espera recomendado a partir de la excepcion."""
    # Algunas APIs de Google incluyen un atributo 'retry_delay'.
    retry_hint = getattr(exc, "retry_delay", None)
    seconds: float | None = None
    if retry_hint is not None:
        if hasattr(retry_hint, "total_seconds"):
            try:
                seconds = float(retry_hint.total_seconds())
            except (TypeError, ValueError):
                seconds = None
        else:
            try:
                seconds = float(retry_hint)
            except (TypeError, ValueError):
                seconds = None
    if seconds is not None and seconds > 0:
        return seconds
    # Si no, intenta extraerlo del mensaje de error.
    return _extract_retry_delay(str(exc))

def _execute_with_quota_retries(operation: Callable[[], Any], *, context: str) -> Any:
    """Ejecuta una operacion, reintentando automaticamente ante errores de cuota."""
    max_attempts = max(1, _read_int_env(_TOOL_MAX_RETRIES_ENV, 5))
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            # Si no es un error de cuota o es el ultimo intento, lanza la excepcion.
            if not _is_quota_error(exc) or attempt == max_attempts:
                raise
            
            # Calcula el tiempo de espera (delay).
            retry_delay = _get_retry_delay_seconds(exc)
            if retry_delay is None:
                # Si la API no sugiere un delay, usa un backoff exponencial.
                retry_delay = min(2 ** attempt, _MAX_RETRY_WAIT_SECONDS)
            retry_delay = max(retry_delay, _MIN_RETRY_WAIT_SECONDS)
            
            error_preview = _truncate_text(str(exc), 250)
            print(
                f"Aviso: cuota de la API agotada ({error_preview}). Reintentando {context} en {retry_delay:.1f}s... (intento {attempt} de {max_attempts})"
            )
            time.sleep(retry_delay)
    
    if last_exc is not None:
        raise last_exc
    return [] # No deberia alcanzarse si la logica es correcta.

def _install_runner_retry_patch() -> None:
    """Aplica un parche global a 'Runner.run' para que maneje errores de cuota."""
    # Esto es 'monkey-patching': modifica una clase existente en tiempo de ejecucion.
    # Se hace para no tener que modificar el codigo fuente del ADK.
    if getattr(Runner.run, "_quota_retry_patched", False):
        return # El parche ya fue aplicado.
    
    original_run = Runner.run

    def patched_run(self, *args, **kwargs):
        session_id = kwargs.get("session_id") or "?"
        context = f"runner.run(session_id={session_id})"

        def invoke():
            # Llama a la funcion original dentro del wrapper de reintentos.
            return original_run(self, *args, **kwargs)

        return _execute_with_quota_retries(invoke, context=context)

    patched_run._quota_retry_patched = True  # type: ignore[attr-defined]
    Runner.run = patched_run # Reemplaza el metodo original con el parcheado.

# Aplica el parche tan pronto como se carga el modulo.
_install_runner_retry_patch()

# --- Ayudante para Ejecucion Sincrona de Corutinas --- #

def run_coro_sync(coro_fn, *args, **kwargs):
    """Ejecuta una corutina asincrona incluso si ya existe un bucle de eventos."""
    # asyncio.run() falla si ya hay un bucle corriendo (ej. en Jupyter notebooks).
    # Este wrapper lo soluciona ejecutando la corutina en un hilo separado.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No hay bucle, se puede usar asyncio.run() de forma segura.
        return asyncio.run(coro_fn(*args, **kwargs))

    result: dict[str, Any] = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro_fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover
            result["error"] = exc

    thread = threading.Thread(target=runner, name="agent-async-runner", daemon=True)
    thread.start()
    thread.join() # Espera a que el hilo termine.

    if "error" in result:
        raise result["error"]
    return result.get("value")


# --- Servicio de sesiones persistentes --- #

def _default_session_db(app_name: str) -> Path:
    base_dir = os.environ.get("ADK_SESSION_STATE_DIR")
    if base_dir:
        candidate = Path(os.path.expanduser(base_dir))
    else:
        candidate = Path(__file__).resolve().parent / "state"
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate / f"{app_name}.sqlite3"


def _build_session_service(app_name: str):
    db_path_env = os.environ.get("ADK_SESSION_DB_PATH")
    if SqliteSessionService:
        if db_path_env:
            db_path = Path(os.path.expanduser(db_path_env))
        else:
            db_path = _default_session_db(app_name)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logging.info("Usando almacenamiento de sesiones persistente en %s", db_path)
        return SqliteSessionService(db_path=str(db_path))
    logging.warning(
        "SqliteSessionService no está disponible; las sesiones se almacenarán solo en memoria."
    )
    return InMemorySessionService()


# --- Contabilidad de tokens y costes --- #

_INPUT_COST_PER_TOKEN = _read_float_env(_TOKEN_INPUT_COST_ENV, _DEFAULT_INPUT_COST_PER_MILLION) / 1_000_000
_OUTPUT_COST_PER_TOKEN = _read_float_env(_TOKEN_OUTPUT_COST_ENV, _DEFAULT_OUTPUT_COST_PER_MILLION) / 1_000_000
_CACHE_COST_PER_TOKEN = _read_float_env(_TOKEN_CACHE_COST_ENV, _DEFAULT_CACHE_COST_PER_MILLION) / 1_000_000


def _safe_int(value) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _lookup(obj, name):
    if obj is None:
        return None
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name)
    return None


def _iterable_field(obj, name):
    value = _lookup(obj, name)
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


class TokenTracker:
    """Acumula tokens consumidos y estima el coste aproximado."""

    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.cached_tokens = 0
        self.output_tokens = 0
        self.thought_tokens = 0

    def add_usage(self, usage) -> None:
        prompt = _safe_int(_lookup(usage, "prompt_token_count"))
        output = _safe_int(_lookup(usage, "candidates_token_count"))
        thoughts = _safe_int(_lookup(usage, "thoughts_token_count")) or _safe_int(_lookup(usage, "thought_token_count"))
        cached = 0
        for detail in _iterable_field(usage, "cache_tokens_details"):
            cached += _safe_int(_lookup(detail, "cached_content_token_count")) or _safe_int(_lookup(detail, "token_count"))
        if prompt:
            self.prompt_tokens += prompt
        if output:
            self.output_tokens += output
        if cached:
            self.cached_tokens += cached
        if thoughts:
            self.thought_tokens += thoughts

    def record_event(self, event) -> None:
        usage = getattr(event, "usage_metadata", None)
        if usage:
            self.add_usage(usage)

    def totals(self) -> dict[str, float]:
        prompt_paid = max(self.prompt_tokens - self.cached_tokens, 0)
        cost = (
            prompt_paid * _INPUT_COST_PER_TOKEN
            + self.cached_tokens * _CACHE_COST_PER_TOKEN
            + self.output_tokens * _OUTPUT_COST_PER_TOKEN
        )
        return {
            "prompt": self.prompt_tokens,
            "cached": self.cached_tokens,
            "output": self.output_tokens,
            "thoughts": self.thought_tokens,
            "cost": cost,
        }

    def format_summary(self) -> str:
        totals = self.totals()
        return (
            f"Tokens entrada: {totals['prompt']} (cache {totals['cached']}), "
            f"salida: {totals['output']}, coste≈${totals['cost']:.4f}"
        )


# --- Fabrica del Agente --- #

def build_agent() -> Agent:
    """Carga la configuracion y crea la instancia del agente XWiki."""
    # Carga las variables desde el archivo .env.
    load_dotenv(override=True)
    xwiki_url = os.environ.get("XWIKI_URL")
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    model_name = os.environ.get("MODEL_NAME")

    if not (xwiki_url and google_api_key and model_name):
        raise ValueError("Faltan XWIKI_URL, GOOGLE_API_KEY o MODEL_NAME en .env")

    # Instrucciones para el modelo de lenguaje (LLM) que definen su comportamiento.
    instruction = (
        "Eres un asistente amable y util. "
        "Antes de llamar a una herramienta, analiza si la pregunta necesita datos adicionales. "
        "Cuando una herramienta sea necesaria, formula consultas concretas para evitar respuestas voluminosas. "
        "Resume los hallazgos clave de cada herramienta antes de responder al usuario. "
        "Evita repetir la misma herramienta con los mismos parametros y explica por que la elegiste. "
        "Si la informacion sigue siendo insuficiente, aclara lo que falta y propone proximos pasos."
    )

    # Crea y devuelve la instancia del agente.
    return Agent(
        name="Xwiki_agent",
        model=model_name,
        description="Agente para buscar informacion actualizada en XWiki.",
        tools=list(ADK_XWIKI_TOOLS.values()), # Las herramientas que el agente puede usar.
        instruction=instruction,
    )

# Crea la instancia principal del agente al iniciar.
root_agent = build_agent()


# --- Punto de Entrada Principal --- #

def main():
    """Configura el entorno de ejecucion y ejecuta el agente una vez."""
    print("Bienvenido al tutorial de Google ADK!")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Python: {sys.version.split()[0]}")
    print("Entorno:", "Google Colab" if "google.colab" in sys.modules else "Local")

    # Configura un servicio de sesiones persistente cuando está disponible.
    app_name = root_agent.name
    session_service = _build_session_service(app_name)
    user_id = "user_1"
    session_id = "session_001"

    # Crea la sesion de forma sincrona.
    run_coro_sync(
        session_service.create_session,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    print(f"Sesion creada: app='{app_name}', usuario='{user_id}', sesion='{session_id}'")

    # Crea el Runner, que es el encargado de orquestar la interaccion con el agente.
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name=app_name,
    )

    token_tracker = TokenTracker()

    print("\nHerramientas registradas:")
    for tool in root_agent.tools:
        tool_name = getattr(tool, "name", type(tool).__name__)
        tool_desc = getattr(tool, "description", "") or ""
        print(f"- {tool_name}: {tool_desc}")

    # Mensaje inicial del usuario para iniciar la conversacion.
    initial_message = types.Content(
        role="user",
        parts=[types.Part(text="Que herramientas tienes disponibles?")],
    )

    try:
        # Ejecuta el agente con el mensaje inicial.
        events = runner.run(
            user_id=user_id,
            session_id=session_id,
            new_message=initial_message,
        )
    except Exception as exc:
        # Manejo especifico para errores de cuota en el nivel superior.
        if _is_quota_error(exc):
            print(
                "\nNo se pudo completar la solicitud porque se excedio la cuota de la API. Intenta nuevamente en unos instantes o revisa los limites de tu cuenta."
            )
            return
        raise

    # Itera sobre los eventos devueltos por el runner para mostrar el flujo de la conversacion.
    for event in events:
        token_tracker.record_event(event)

        # Evento: El modelo decide llamar a una herramienta.
        if hasattr(event, "is_tool_call") and event.is_tool_call():
            tool_obj = getattr(event, "tool", None)
            tool_name = getattr(tool_obj, "name", getattr(event, "tool_name", "desconocida"))
            arguments = getattr(event, "arguments", None)
            if not arguments and hasattr(event, "tool_input"):
                arguments = getattr(event, "tool_input")
            preview = "{}"
            if arguments:
                try:
                    preview = json.dumps(arguments, ensure_ascii=False)
                except TypeError:
                    preview = str(arguments)
                preview = _truncate_text(preview, 200)
            print(f"\nUso de tokens (acumulado): {token_tracker.format_summary()}")
            print(f"\nInvocando herramienta: {tool_name} con parametros {preview}")
            continue

        # Evento: La herramienta devuelve un resultado.
        if hasattr(event, "is_tool_response") and event.is_tool_response():
            tool_obj = getattr(event, "tool", None)
            tool_name = getattr(tool_obj, "name", getattr(event, "tool_name", "desconocida"))
            output_payload = getattr(event, "output", None)
            raw_output = _normalise_tool_output(output_payload)
            log_path = _log_tool_output(tool_name, raw_output) if raw_output else None
            summary, truncated = _summarise_tool_output(raw_output)
            print(f"Resultado de {tool_name}:")
            print(summary)
            if truncated and log_path:
                print(f"(Resultado completo guardado en {log_path})")

            if (
                tool_name == "search_pages"
                and isinstance(output_payload, dict)
                and output_payload.get("suggest_describe_space_tree")
            ):
                filtered = output_payload.get("filtered_space")
                hint = (
                    "Considera invocar describe_space_tree para explorar la jerarquía"
                    + (f" bajo '{filtered}'" if filtered else "")
                )
                print(f"Sugerencia: {hint}.")
            continue

        # Evento: El modelo da su respuesta final al usuario.
        if event.is_final_response():
            parts = getattr(event.content, "parts", [])
            text = parts[0].text if parts else ""
            print(f"\nAgent Response: {text}")
            print(f"\nResumen de coste: {token_tracker.format_summary()}")

# Este bloque asegura que la funcion main() solo se ejecute cuando el script es invocado directamente.
if __name__ == "__main__":
    main()
