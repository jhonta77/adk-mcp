# Importaciones de bibliotecas estándar y de terceros.
import asyncio  # Para operaciones asíncronas.
import json  # Para codificar y decodificar JSON.
import logging  # Para registrar información, advertencias y errores.
import os  # Para interactuar con el sistema operativo (p. ej., rutas de archivos).
import sys  # Para interactuar con el intérprete de Python (p. ej., argumentos de línea de comandos).
import requests  # Para realizar peticiones HTTP a la API de XWiki.
import xml.etree.ElementTree as ET  # Para analizar respuestas XML de XWiki.
from requests.auth import HTTPBasicAuth  # Para la autenticación básica en las peticiones.

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

# Carga las variables de entorno desde un archivo .env para la configuración.
load_dotenv()

# --- Configuración de la Conexión a XWiki ---
# Define las credenciales y la URL para conectarse a la instancia de XWiki.
# Es recomendable gestionar estas credenciales de forma segura, por ejemplo, usando variables de entorno.
XWIKI_URL = "https://xwiki.cloudmanufaktur.digital/xwiki"
XWIKI_USER = "KarolineRingsdorf"
XWIKI_PASS = "=wtI2<04/Hs^"
XWIKI_WIKI_NAME = "xwiki"  # Nombre de la wiki a la que nos conectamos.

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

# --- Funciones de Herramientas para la API de XWiki ---
# Estas funciones interactúan directamente con la API REST de XWiki.

def get_page(space_name: str, page_name: str) -> dict:
    """Recupera el contenido de una página específica de XWiki."""
    api_url = f"{XWIKI_URL}/rest/wikis/{XWIKI_WIKI_NAME}/spaces/{space_name}/pages/{page_name}"
    try:
        response = requests.get(
            api_url,
            auth=HTTPBasicAuth(XWIKI_USER, XWIKI_PASS),
            headers={"Accept": "application/xml"}  # Solicitamos la respuesta en formato XML.
        )
        response.raise_for_status()  # Lanza un error si la petición no fue exitosa (código 2xx).
        root = ET.fromstring(response.content)  # Analiza el XML.
        namespace = {'xwiki': 'http://www.xwiki.org'}
        content_element = root.find('xwiki:content', namespace)
        if content_element is not None:
            return {"success": True, "content": content_element.text}
        else:
            return {"success": False, "message": "No se pudo encontrar el contenido en el XML de la página."}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error al obtener la página: {e}")
        return {"success": False, "message": str(e)}
    except ET.ParseError as e:
        logging.error(f"Error al analizar el XML: {e}")
        return {"success": False, "message": f"Error al analizar el XML: {e}"}

def create_or_update_page(space_name: str, page_name: str, content: str, title: str = "") -> dict:
    """Crea una nueva página o actualiza una existente en XWiki."""
    api_url = f"{XWIKI_URL}/rest/wikis/{XWIKI_WIKI_NAME}/spaces/{space_name}/pages/{page_name}"
    page_title = title if title else page_name
    # Construye el cuerpo de la petición en formato XML.
    xml_payload = f'''
    <page xmlns="http://www.xwiki.org">
      <title>{page_title}</title>
      <syntax>xwiki/2.1</syntax>
      <content>{content}</content>
    </page>
    '''
    try:
        response = requests.put(
            api_url,
            auth=HTTPBasicAuth(XWIKI_USER, XWIKI_PASS),
            headers={"Content-Type": "application/xml"},
            data=xml_payload.encode('utf-8')
        )
        response.raise_for_status()

        page_url = None
        try:
            # Intenta extraer la URL de la página de la respuesta.
            root = ET.fromstring(response.content)
            namespace = {'xwiki': 'http://www.xwiki.org'}
            url_element = root.find('xwiki:xwikiAbsoluteUrl', namespace)
            if url_element is not None:
                page_url = url_element.text
        except ET.ParseError:
            pass # Ignora el error si la respuesta no es XML (p. ej., en un código 204 No Content).

        if response.status_code == 201: # Creado
            return {"success": True, "message": f"Página '{page_name}' creada exitosamente.", "url": page_url}
        elif response.status_code in [200, 202, 204]: # Actualizado
            return {"success": True, "message": f"Página '{page_name}' actualizada exitosamente (Estado: {response.status_code}).", "url": page_url}
        else:
            return {"success": False, "message": f"Página '{page_name}' devolvió el estado {response.status_code}. Detalles: {response.text}"}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error al crear/actualizar la página: {e}")
        return {"success": False, "message": str(e)}

def search_pages(query: str) -> dict:
    """Busca páginas en XWiki que coincidan con un término de búsqueda."""
    api_url = f"{XWIKI_URL}/rest/wikis/{XWIKI_WIKI_NAME}/search"
    try:
        response = requests.get(
            api_url,
            auth=HTTPBasicAuth(XWIKI_USER, XWIKI_PASS),
            params={"keywords": query, "media": "json"} # Pide los resultados en JSON.
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error al buscar páginas: {e}")
        return {"success": False, "message": str(e)}

def list_pages(space_name: str) -> dict:
    """Lista todas las páginas en un espacio determinado de XWiki."""
    api_url = f"{XWIKI_URL}/rest/wikis/{XWIKI_WIKI_NAME}/spaces/{space_name}/pages"
    try:
        response = requests.get(
            api_url,
            auth=HTTPBasicAuth(XWIKI_USER, XWIKI_PASS),
            headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        return {"success": True, "pages": response.json().get("pages", [])}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error al listar las páginas del espacio '{space_name}': {e}")
        return {"success": False, "message": str(e)}

def list_spaces() -> dict:
    """Lista todos los espacios (carpetas) en la wiki."""
    api_url = f"{XWIKI_URL}/rest/wikis/{XWIKI_WIKI_NAME}/spaces"
    try:
        response = requests.get(
            api_url,
            auth=HTTPBasicAuth(XWIKI_USER, XWIKI_PASS),
            headers={"Accept": "application/json"}
        )
        response.raise_for_status()
        return {"success": True, "spaces": response.json().get("spaces", [])}
    except requests.exceptions.RequestException as e:
        logging.error(f"Error listing spaces: {e}")
        return {"success": False, "message": str(e)}

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
    # Este bloque contiene funciones para probar las herramientas de XWiki localmente
    # sin necesidad de un agente. Es muy útil para el desarrollo y la depuración.
    
    # (El bloque de pruebas detallado se omite aquí por brevedad, pero su propósito es
    # verificar que cada función de herramienta (get_page, list_spaces, etc.) funciona
    # como se espera. Se puede ejecutar con `python server.py all` o `python server.py <nombre_prueba>`)

    # --- BLOQUE DEL SERVIDOR MCP ---
    # Para iniciar el servidor real, el bloque de pruebas de arriba debe ser comentado
    # y este bloque debe estar activo.
    
    logging.info("Lanzando servidor MCP de XWiki vía stdio...")
    try:
        # Inicia el bucle de eventos de asyncio para correr el servidor.
        asyncio.run(run_mcp_stdio_server())
    except KeyboardInterrupt:
        # Permite detener el servidor limpiamente con Ctrl+C.
        logging.info("Servidor MCP de XWiki detenido por el usuario.")
    except Exception as e:
        # Captura cualquier otro error crítico que pueda detener el servidor.
        logging.critical(f"Servidor MCP de XWiki encontró un error no manejado: {e}", exc_info=True)
    finally:
        logging.info("Proceso del servidor MCP de XWiki finalizando.")
