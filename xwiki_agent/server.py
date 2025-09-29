# Importaciones de bibliotecas estándar y de terceros.
import asyncio  # Para operaciones asíncronas.
import json  # Para codificar y decodificar JSON.
import logging  # Para registrar información, advertencias y errores.
import os  # Para interactuar con el sistema operativo (p. ej., rutas de archivos).
import sys  # Para interactuar con el interprete de Python (p. ej., argumentos de linea de comandos).
import re  # Para manejar separadores en rutas de espacios.
import requests  # Para realizar peticiones HTTP a la API de XWiki.
import xml.etree.ElementTree as ET  # Para analizar respuestas XML de XWiki.
from xml.sax.saxutils import escape  # Para escapar valores en XML.
from urllib.parse import quote  # Para codificar segmentos de la URL.
from requests.auth import HTTPBasicAuth  # Para la autenticación básica en las peticiones.
from html import unescape

# Importaciones específicas del framework MCP (Multi-Capability Protocol).
import mcp.server.stdio
from dotenv import load_dotenv  # Para cargar variables de entorno desde un archivo .env.

# Importaciones específicas del ADK (Agent Development Kit) de Google.
from google.adk.tools.function_tool import FunctionTool  # Para crear herramientas a partir de funciones de Python.
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type  # Utilidad para convertir herramientas de ADK a MCP.

# Importaciones de tipos y modelos del servidor MCP.
from mcp import types as mcp_types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

try:
    from .secret_manager import (
        SecretRetrievalError,
        get_masked_username,
        load_xwiki_credentials,
    )
except ImportError:  # Ejecución directa del script
    from secret_manager import (  # type: ignore
        SecretRetrievalError,
        get_masked_username,
        load_xwiki_credentials,
    )

# Carga las variables de entorno desde un archivo .env para la configuración.
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

# --- Configuración de la Conexión a XWiki ---
# Las credenciales se obtienen preferentemente desde almacenes seguros.
XWIKI_URL = os.environ.get("XWIKI_URL")
if not XWIKI_URL:
    raise RuntimeError("La variable de entorno XWIKI_URL es obligatoria para acceder a la instancia de XWiki.")
try:
    _XWIKI_CREDENTIALS = load_xwiki_credentials()
except SecretRetrievalError as exc:
    raise RuntimeError(f"No se pudieron cargar credenciales de XWiki: {exc}") from exc
XWIKI_USER = _XWIKI_CREDENTIALS.username
XWIKI_PASS = _XWIKI_CREDENTIALS.password
XWIKI_CREDENTIAL_SOURCE = _XWIKI_CREDENTIALS.source
XWIKI_WIKI_NAME = os.environ.get("XWIKI_WIKI_NAME", "xwiki")  # Nombre por defecto de la wiki virtual.
XWIKI_AUTH = HTTPBasicAuth(XWIKI_USER, XWIKI_PASS)
# Fallback opcional de espacios conocidos cuando la API no expone la jerarquía.
FALLBACK_SPACES = [
    seg.strip()
    for seg in os.environ.get("XWIKI_FALLBACK_SPACES", "Main").split(",")
    if seg.strip()
]
# --- Configuración del Logging ---
# Configura un sistema de logging para registrar la actividad del servidor en un archivo.
# Esto es crucial para la depuración y el monitoreo.
LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "xwiki_mcp_server_activity.log")
logging.basicConfig(
    level=logging.DEBUG,  # Nivel mínimo de mensajes a registrar.
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, mode="w"),  # Escribe los logs en el archivo especificado.
    ],
)

masked_user = get_masked_username()
if masked_user:
    logging.info("Credenciales de XWiki cargadas desde %s para el usuario '%s'.", XWIKI_CREDENTIAL_SOURCE, masked_user)
else:
    logging.warning("Credenciales de XWiki no disponibles; revisa la configuración de secret_manager.")

# Timeout por defecto para peticiones HTTP (conexion, lectura).
def _load_request_timeout(default_connect: float = 3.05, default_read: float = 10.0) -> tuple[float, float]:
    '''Obtiene los timeouts de conexion/lectura desde las variables de entorno.'''
    connect_env = os.environ.get("XWIKI_CONNECT_TIMEOUT")
    read_env = os.environ.get("XWIKI_READ_TIMEOUT")
    try:
        connect_timeout = float(connect_env) if connect_env else default_connect
    except (TypeError, ValueError):
        logging.warning(
            "Valor invalido para XWIKI_CONNECT_TIMEOUT (%s); se usara %.2f s.",
            connect_env,
            default_connect,
        )
        connect_timeout = default_connect
    try:
        read_timeout = float(read_env) if read_env else default_read
    except (TypeError, ValueError):
        logging.warning(
            "Valor invalido para XWIKI_READ_TIMEOUT (%s); se usara %.2f s.",
            read_env,
            default_read,
        )
        read_timeout = default_read
    return (connect_timeout, read_timeout)

REQUEST_TIMEOUT = _load_request_timeout()



_PAGE_CONTENT_MAX_CHARS_ENV = "XWIKI_PAGE_MAX_CHARS"
_DEFAULT_PAGE_CONTENT_MAX_CHARS = 1500



_SEARCH_MAX_RESULTS_ENV = "XWIKI_SEARCH_MAX_RESULTS"
_DEFAULT_SEARCH_MAX_RESULTS = 5
_SEARCH_SNIPPET_MAX_CHARS_ENV = "XWIKI_SEARCH_SNIPPET_MAX_CHARS"
_DEFAULT_SEARCH_SNIPPET_MAX_CHARS = 280
def _read_positive_int(env_name: str, default: int) -> int:
    value = os.environ.get(env_name)
    if not value:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logging.warning("Valor invalido para %s (%s); se usara %d.", env_name, value, default)
        return default
    if parsed <= 0:
        logging.warning("Valor para %s debe ser mayor a 0; se usara %d.", env_name, default)
        return default
    return parsed

def _truncate_text_field(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    if max_chars <= 3:
        return text[:max_chars], True
    return text[: max_chars - 3] + "...", True

PAGE_CONTENT_MAX_CHARS = _read_positive_int(_PAGE_CONTENT_MAX_CHARS_ENV, _DEFAULT_PAGE_CONTENT_MAX_CHARS)

SEARCH_MAX_RESULTS = _read_positive_int(_SEARCH_MAX_RESULTS_ENV, _DEFAULT_SEARCH_MAX_RESULTS)
SEARCH_SNIPPET_MAX_CHARS = _read_positive_int(_SEARCH_SNIPPET_MAX_CHARS_ENV, _DEFAULT_SEARCH_SNIPPET_MAX_CHARS)


_LINK_WITH_URL_PATTERN = re.compile(r"\[\[(?P<label>[^>\]]+?)>>(?:url:)?(?P<target>[^\]]+?)\]\]")

_HEADING_PATTERN = re.compile(r"==+\s*(.*?)\s*==+")

_BOLD_PATTERN = re.compile(r"\*\*(.*?)\*\*", re.DOTALL)

_ITALIC_PATTERN = re.compile(r"//(.*?)//", re.DOTALL)

_HTML_TAG_PATTERN = re.compile(r"<[^>]+>")


def _simplify_wiki_markup(text: str) -> str:

    if not text:

        return ""

    simplified = _LINK_WITH_URL_PATTERN.sub(lambda m: f"{m.group('label').strip()} ({m.group('target').strip()})", text)

    simplified = re.sub(r"\{\{\s*toc\s*/\s*\}\}", "", simplified, flags=re.IGNORECASE)

    simplified = _BOLD_PATTERN.sub(lambda m: m.group(1), simplified)

    simplified = _ITALIC_PATTERN.sub(lambda m: m.group(1), simplified)

    simplified = _HEADING_PATTERN.sub(lambda m: f"\n{m.group(1).strip()}:\n", simplified)

    simplified = simplified.replace('----', '\n')

    simplified = re.sub(r'\n{3,}', '\n\n', simplified)

    return simplified.strip()


def _clean_search_snippet(text: str) -> str:
    """Limpia el snippet devuelto por la API para reducir tokens."""
    if not text:
        return ""
    plain = _HTML_TAG_PATTERN.sub(" ", text)
    plain = unescape(plain)
    plain = _simplify_wiki_markup(plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


def _normalise_search_results(payload: dict) -> dict:
    """Reduce y estructura los resultados de búsqueda para el agente."""
    data = payload or {}
    raw_results = data.get("searchResults")
    if raw_results is None:
        raw_results = data.get("searchResult")

    if isinstance(raw_results, list):
        items = raw_results
    elif isinstance(raw_results, dict):
        items = raw_results.get("searchResult") or raw_results.get("result") or []
        if isinstance(items, dict):
            items = [items]
        elif not isinstance(items, list):
            items = [items] if items else []
    else:
        items = []

    simplified: list[dict[str, object]] = []
    for entry in items[:SEARCH_MAX_RESULTS]:
        if not isinstance(entry, dict):
            logging.debug("Resultado de búsqueda no reconocido: %s", entry)
            continue
        snippet = _clean_search_snippet(entry.get("highlight", ""))
        snippet, _ = _truncate_text_field(snippet, SEARCH_SNIPPET_MAX_CHARS)
        record: dict[str, object] = {
            "title": entry.get("title") or entry.get("pageName") or entry.get("id"),
            "url": entry.get("url"),
            "space": entry.get("space"),
            "type": entry.get("type"),
        }
        page_name = entry.get("pageName")
        if page_name:
            record["pageName"] = page_name
        page_id = entry.get("pageId") or entry.get("id")
        if page_id:
            record["pageId"] = page_id
        score = entry.get("score")
        if score is not None:
            record["score"] = score
        if snippet:
            record["snippet"] = snippet
        simplified.append(record)
    total = len(items)
    return {
        "success": True,
        "results": simplified,
        "total": total,
        "truncated": total > len(simplified),
    }



# --- Utilidades internas ---
# Estas funciones de apoyo encapsulan la manipulación de rutas REST, la
# validación de parámetros y la extracción de estructuras desde las respuestas
# JSON/XML de XWiki. Mantenerlas aquí nos permite reutilizarlas en todas las
# herramientas sin duplicar lógica.


def _encode_segment(value: str, field_name: str) -> str:
    """Valida un parámetro y devuelve una versión segura para la URL."""
    if value is None or not str(value).strip():
        raise ValueError(f"El parámetro '{field_name}' no puede estar vacío.")
    return quote(str(value).strip(), safe="")


def _build_space_url(space_segments: list[str], suffix: str) -> str:
    """Construye la URL REST para un espacio (y sus subespacios)."""
    # Comenzamos desde la raíz /rest/wikis/<wiki> y agregamos cada segmento de
    # espacio. XWiki representa subespacios como rutas anidadas: espacios/A/spaces/B/...
    url = f"{XWIKI_URL}/rest/wikis/{XWIKI_WIKI_NAME}"
    for idx, segment in enumerate(space_segments):
        url += f"/spaces/{_encode_segment(segment, f'space_segment[{idx}]')}"
    return url + suffix


def _extract_items(data: dict, collection_key: str, item_key: str) -> list[dict]:
    """Extrae listas anidadas que XWiki devuelve como objetos."""
    # Dependiendo del endpoint, XWiki puede responder "pages": {"page": [...]}
    # o simplemente "pages": [...]. Esta función lo homogeneiza a una lista.
    collection = data.get(collection_key, [])
    if isinstance(collection, dict):
        return collection.get(item_key, []) or []
    if isinstance(collection, list):
        return collection
    return []


def _normalise_space_path(space_path: str | None) -> list[str]:
    """Convierte el espacio en una lista de segmentos normalizados."""
    if not space_path:
        return []
    raw = str(space_path).strip()
    if not raw:
        return []
    cleaned = raw.replace('\\', '/')
    chunks = re.split(r'[\\/]+', cleaned)
    segments: list[str] = []
    for chunk in chunks:
        if not chunk:
            continue
        for part in (seg.strip() for seg in chunk.split('.') if seg.strip()):
            segments.append(part)
    if not segments:
        raise ValueError("El parametro 'space_path' no puede estar vacio tras normalizar.")
    return segments
# --- Funciones de Herramientas para la API de XWiki ---
# Estas funciones interactúan directamente con la API REST de XWiki.

def get_page(space_name: str, page_name: str) -> dict:
    """Recupera contenido y metadatos basicos de una pagina de XWiki.

    Devuelve un diccionario con `success` y, en caso de exito, `content` y `title`."""
    try:
        space_segments = _normalise_space_path(space_name)
        if not space_segments:
            raise ValueError("El parametro 'space_name' no puede estar vacio.")
        encoded_page = _encode_segment(page_name, "page_name")
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    api_url = _build_space_url(space_segments, f"/pages/{encoded_page}")
    try:
        response = requests.get(
            api_url,
            auth=XWIKI_AUTH,
            headers={"Accept": "application/xml"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespace = {'xwiki': 'http://www.xwiki.org'}
        content_element = root.find('xwiki:content', namespace)
        if content_element is None:
            return {"success": False, "message": "No se encontro la seccion de contenido en el XML de la pagina."}

        content_text = content_element.text or ''
        simplified_content = _simplify_wiki_markup(content_text)
        title_element = root.find('xwiki:title', namespace)
        page_title = title_element.text if title_element is not None and title_element.text else page_name
        trimmed_content, was_truncated = _truncate_text_field(simplified_content, PAGE_CONTENT_MAX_CHARS)

        payload = {"success": True, "content": trimmed_content, "title": page_title}
        if was_truncated:
            payload["content_truncated"] = True
            payload["original_content_length"] = len(simplified_content)
            payload["notice"] = (
                "El contenido completo de la pagina se trunco para reducir el tamano de la respuesta. "
                "Ajusta XWIKI_PAGE_MAX_CHARS si necesitas mas detalle."
            )

        return payload
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 404:
            space_path = "/".join(space_segments)
            message = f"La pagina '{page_name}' no se encontro en el espacio '{space_path}'."
            return {"success": False, "message": message}
        logging.error("Error HTTP al obtener la pagina '%s' en '%s': %s", page_name, space_segments, exc)
        return {"success": False, "message": str(exc)}
    except requests.exceptions.RequestException as exc:
        logging.error("Error al obtener la pagina '%s' en '%s': %s", page_name, space_segments, exc)
        return {"success": False, "message": str(exc)}
    except ET.ParseError as exc:
        logging.error("Error al analizar el XML: %s", exc)
        return {"success": False, "message": f"Error al analizar el XML: {exc}"}

def create_or_update_page(space_name: str, page_name: str, content: str, title: str = "") -> dict:
    """Crea una nueva pagina o actualiza una existente en XWiki."""
    if content is None:
        return {"success": False, "message": "El contenido no puede ser nulo."}

    try:
        space_segments = _normalise_space_path(space_name)
        if not space_segments:
            raise ValueError("El parametro 'space_name' no puede estar vacio.")
        encoded_page = _encode_segment(page_name, "page_name")
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    api_url = _build_space_url(space_segments, f"/pages/{encoded_page}")
    page_title = title if title else page_name
    safe_title = escape(str(page_title))
    safe_content = escape(str(content))
    xml_payload = (
        f"<?xml version='1.0' encoding='UTF-8'?>"
        f"<page>"
        f"  <title>{safe_title}</title>"
        f"  <content>{safe_content}</content>"
        f"</page>"
    )
    payload = "\n".join(xml_payload)

    headers = {"Content-Type": "application/xml", "Accept": "application/json"}

    try:
        response = requests.put(
            api_url,
            data=payload.encode('utf-8'),
            auth=XWIKI_AUTH,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return {"success": True, "message": "Pagina creada o actualizada correctamente."}
    except requests.exceptions.RequestException as exc:
        logging.error("Error al crear/actualizar la pagina '%s' en '%s': %s", page_name, space_segments, exc)
        return {"success": False, "message": str(exc)}

def search_pages(query: str, space_name: str = "") -> dict:
    """Busca páginas en XWiki, opcionalmente acotadas a un espacio concreto."""
    api_url = f"{XWIKI_URL}/rest/wikis/{XWIKI_WIKI_NAME}/search"
    try:
        response = requests.get(
            api_url,
            auth=XWIKI_AUTH,
            params={"keywords": query, "media": "json"}
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            logging.error("Respuesta de búsqueda no es JSON válido: %s", exc)
            return {"success": False, "message": "La API devolvió una respuesta no válida"}
        result = _normalise_search_results(payload)
        if not result.get("success"):
            return result

        suggest_space_tree = False

        if space_name:
            try:
                segments = _normalise_space_path(space_name)
            except ValueError as exc:
                return {"success": False, "message": str(exc)}
            target = "/".join(segments)
            segments_cf = [seg.casefold() for seg in segments]

            filtered: list[dict[str, object]] = []
            for item in result.get("results", []):
                space_value = str(item.get("space", ""))
                if not space_value:
                    continue
                cleaned = space_value.replace("\\", "/")
                parts = [seg for seg in re.split(r"[\\/\.]+", cleaned) if seg]
                parts_cf = [seg.casefold() for seg in parts]
                if parts_cf[: len(segments_cf)] == segments_cf:
                    filtered.append(item)

            if filtered:
                result["results"] = filtered
                result["total"] = len(filtered)
                result["truncated"] = False
            else:
                result["filter_warning"] = (
                    "No se encontraron coincidencias exactas en el espacio filtrado; se muestran resultados globales."
                )
                suggest_space_tree = True
            result["filtered_space"] = target

        if not result.get("results"):
            suggest_space_tree = True

        if suggest_space_tree:
            result["suggest_describe_space_tree"] = True

        return result
    except requests.exceptions.RequestException as exc:
        logging.error("Error al buscar páginas: %s", exc)
        return {"success": False, "message": str(exc)}


def list_pages(space_name: str) -> dict:
    """Lista todas las paginas en un espacio determinado de XWiki."""
    try:
        space_segments = _normalise_space_path(space_name)
        if not space_segments:
            raise ValueError("El parametro 'space_name' no puede estar vacio.")
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    api_url = _build_space_url(space_segments, "/pages")
    try:
        response = requests.get(
            api_url,
            auth=XWIKI_AUTH,
            headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        pages = response.json().get("pages", [])
        return {"success": True, "pages": pages}
    except requests.exceptions.RequestException as exc:
        logging.error("Error al listar las paginas del espacio '%s': %s", space_name, exc)
        return {"success": False, "message": str(exc)}

def list_spaces() -> dict:
    """Lista todos los espacios (carpetas) en la wiki."""
    api_url = f"{XWIKI_URL}/rest/wikis/{XWIKI_WIKI_NAME}/spaces"
    print(f"Intentando acceder a: {api_url}")
    try:
        response = requests.get(
            api_url,
            auth=XWIKI_AUTH,
            headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        return {"success": True, "spaces": response.json().get("spaces", [])}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error listing spaces: {e}")
        return {"success": False, "message": str(e)}


def _fetch_spaces(space_segments: list[str]) -> list[dict]:
    """Recupera los subespacios de una ruta dada."""
    # Construimos la URL hacia /spaces y pedimos JSON (más liviano que XML).
    url = _build_space_url(space_segments, "/spaces")
    try:
        response = requests.get(
            url,
            auth=XWIKI_AUTH,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        items = _extract_items(data, "spaces", "space")
        # Si la API devuelve vacío y estamos en la raíz, devolvemos los fallback.
        if not items and not space_segments:
            return [{"name": name} for name in FALLBACK_SPACES]
        return items
    except requests.exceptions.RequestException as exc:
        if not space_segments and FALLBACK_SPACES:
            # En caso de error al listar el root, retornamos espacios conocidos.
            logging.warning("Fallo al obtener espacios (%s). Usando fallback.", exc)
            return [{"name": name} for name in FALLBACK_SPACES]
        raise


def _fetch_pages(space_segments: list[str]) -> list[dict]:
    """Recupera las páginas de un espacio concreto."""
    # Este endpoint puede devolver 404 si el espacio no contiene páginas.
    url = _build_space_url(space_segments, "/pages")
    response = requests.get(
        url,
        auth=XWIKI_AUTH,
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    data = response.json()
    return _extract_items(data, "pages", "page")


def _explore_space(space_segments: list[str], depth: int) -> dict:
    """Construye recursivamente la jerarquía de espacios/páginas."""
    # Cada nodo del árbol incluye el nombre del espacio, las páginas directas y
    # una lista de subespacios (que a su vez contienen la misma estructura).
    node = {
        "space": "/".join(space_segments) if space_segments else "",
        "pages": [],
        "spaces": [],
    }

    try:
        pages = _fetch_pages(space_segments)
        node["pages"] = [page.get("name") for page in pages if page.get("name")]
    except requests.exceptions.HTTPError as exc:
        # Un 404 en páginas es normal si el espacio solo contiene subespacios.
        if exc.response is None or exc.response.status_code != 404:
            raise

    if depth <= 0:
        return node

    subspaces = _fetch_spaces(space_segments)
    for entry in subspaces:
        name = entry.get("name")
        if not name:
            continue
        child_segments = space_segments + [name]
        try:
            # Avanzamos un nivel más profundo. restamos 1 al depth para evitar
            # exploraciones infinitas.
            child_node = _explore_space(child_segments, depth - 1)
        except requests.exceptions.RequestException as exc:
            # En caso de error al conectar, devolvemos la descripción del fallo
            # para que el usuario pueda depurar qué subespacio falló.
            child_node = {
                "space": "/".join(child_segments),
                "error": str(exc),
            }
        node["spaces"].append(child_node)

    return node


def describe_space_tree(space_path: str = "", depth: int = 2) -> dict:
    """Devuelve la jerarquía de subespacios y páginas comenzando en `space_path`.

    Args:
        space_path: Ruta del espacio (separada por '/'). Si se omite, se usa la raíz.
        depth: Profundidad máxima de exploración (>=0).
    """

    if depth < 0:
        return {"success": False, "message": "El parámetro 'depth' debe ser mayor o igual a 0."}

    try:
        segments = _normalise_space_path(space_path)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    try:
        # _explore_space devuelve un diccionario con toda la jerarquía a partir
        # del espacio indicado. Ese árbol se entrega directamente al agente.
        tree = _explore_space(segments, depth)
        return {"success": True, "tree": tree}
    except requests.exceptions.RequestException as exc:
        logging.error("Error al explorar el espacio '%s': %s", space_path or "root", exc)
        return {"success": False, "message": str(exc)}

# --- Configuración del Servidor MCP ---
# Crea una instancia del servidor MCP que gestionará las herramientas.
app = Server("xwiki-mcp-server")

# Define un diccionario que mapea nombres de herramientas a instancias de FunctionTool.
# Esto hace que las funciones de Python sean "visibles" para el agente de IA.
ADK_XWIKI_TOOLS = {
    "get_page": FunctionTool(func=get_page),
    "create_or_update_page": FunctionTool(func=create_or_update_page),
    "search_pages": FunctionTool(func=search_pages),
    "list_pages": FunctionTool(func=list_pages),
    "list_spaces": FunctionTool(func=list_spaces),
    "describe_space_tree": FunctionTool(func=describe_space_tree),
}

# --- Implementación de los Endpoints del Servidor MCP ---

@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """Endpoint que el agente llama para descubrir las herramientas disponibles."""
    mcp_tools_list = []
    for tool_name, adk_tool_instance in ADK_XWIKI_TOOLS.items():
        if not adk_tool_instance.name:
            adk_tool_instance.name = tool_name
        # Convierte la definición de la herramienta del formato ADK al formato MCP.
        mcp_tool_schema = adk_to_mcp_tool_type(adk_tool_instance)
        mcp_tools_list.append(mcp_tool_schema)
    return mcp_tools_list

@app.call_tool()
async def call_mcp_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    """Endpoint que el agente llama para ejecutar una herramienta específica."""
    if name in ADK_XWIKI_TOOLS:
        adk_tool_instance = ADK_XWIKI_TOOLS[name]
        try:
            # Ejecuta la función de la herramienta de forma asíncrona.
            adk_tool_response = await adk_tool_instance.run_async(args=arguments, tool_context=None)
            # Formatea la respuesta como un string JSON para devolverla al agente.
            response_text = json.dumps(adk_tool_response, indent=2, ensure_ascii=False)
            return [mcp_types.TextContent(type="text", text=response_text)]
        except Exception as e:
            # Maneja errores durante la ejecución de la herramienta.
            error_payload = {"success": False, "message": f"Fallo al ejecutar la herramienta '{name}': {str(e)}"}
            error_text = json.dumps(error_payload, ensure_ascii=False)
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        # Responde si se llama a una herramienta que no existe.
        error_payload = {"success": False, "message": f"Herramienta '{name}' no implementada."}
        error_text = json.dumps(error_payload, ensure_ascii=False)
        return [mcp_types.TextContent(type="text", text=error_text)]

async def run_mcp_stdio_server():
    """Función asíncrona para iniciar el servidor MCP sobre E/S estándar (stdio)."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=app.name,
                server_version="0.1.0",
                capabilities=app.get_capabilities(notification_options=NotificationOptions(), experimental_capabilities={}),
            ),
        )

# --- Bloque Principal de Ejecución ---
# Este bloque se ejecuta solo cuando el script es llamado directamente.
if __name__ == "__main__":
    # --- BLOQUE DE PRUEBAS LOCALES ---
    # Este bloque permite probar las herramientas de XWiki localmente.
    # Uso: python server.py <nombre_prueba>
    # Pruebas disponibles: all, list_spaces, list_pages, get_page, create_page, search, tree

    def run_test(test_func, *args):
        print(f"--- Ejecutando prueba: {test_func.__name__} ---")
        try:
            result = test_func(*args)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error durante la prueba: {e}")
        print("--- Fin de la prueba ---\n")

    # --- Definiciones de las pruebas ---
    def test_list_spaces():
        run_test(list_spaces)

    def test_list_pages():
        # Reemplaza "Main" con un espacio que exista en tu XWiki
        run_test(list_pages, "Main")

    def test_get_page():
        # Reemplaza "Main" y "WebHome" con un espacio y página que existan
        run_test(get_page, "Main", "WebHome")

    def test_create_update_page():
        run_test(
            create_or_update_page,
            "TestSpace",
            "TestPage",
            "Este es el contenido de la página de prueba.",
            "Página de Prueba"
        )

    def test_search():
        run_test(search_pages, "test")

    def test_tree():
        run_test(describe_space_tree, "", 2)

    # --- Lógica para ejecutar las pruebas desde la línea de comandos ---
    if len(sys.argv) > 1:
        test_name = sys.argv[1]
        tests = {
            "list_spaces": test_list_spaces,
            "list_pages": test_list_pages,
            "get_page": test_get_page,
            "create_page": test_create_update_page,
            "search": test_search,
            "tree": test_tree,
        }

        if test_name == "all":
            for name, test_func in tests.items():
                test_func()
        elif test_name in tests:
            tests[test_name]()
        else:
            print(f"Prueba '{test_name}' no encontrada. Pruebas disponibles: {list(tests.keys())}")
            
    else:
        # --- BLOQUE DEL SERVIDOR MCP ---
        # Si no se especifica una prueba, se inicia el servidor.
        logging.info("Lanzando servidor MCP de XWiki vía stdio...")
        try:
            asyncio.run(run_mcp_stdio_server())
        except KeyboardInterrupt:
            logging.info("Servidor MCP de XWiki detenido por el usuario.")
        except Exception as e:
            logging.critical(f"Servidor MCP de XWiki encontró un error no manejado: {e}", exc_info=True)
        finally:
            logging.info("Proceso del servidor MCP de XWiki finalizando.")
