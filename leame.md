# Agente ADK XWiki

## 1. Visión general
Este proyecto entrega un agente conversacional construido con el Agent Development Kit (ADK) de Google y el Model Context Protocol (MCP). El agente se conecta a una instancia de XWiki para consultar, crear y actualizar contenido mediante llamadas a herramientas estructuradas mientras mantiene un diálogo natural con la persona usuaria.

### Flujo de alto nivel
<pre>
Usuario -> ADK Runner -> Servidor MCP (server.py) -> API REST de XWiki
</pre>

## 2. Estructura del repositorio
| Ruta | Propósito |
| --- | --- |
| `xwiki_agent/agent.py` | Configura el agente ADK (`Xwiki_Buscador`), carga variables de entorno y registra las herramientas MCP expuestas por el servidor. |
| `xwiki_agent/server.py` | Implementa el servidor MCP, envuelve la API REST de XWiki como herramientas invocables y gestiona el registro de actividad. |
| `xwiki_agent/prompt.py` | Prompt base que define cómo el agente decide cuándo y cómo usar las herramientas. |
| `xwiki_agent/diagnosis_script.py` | Utilidad de autodiagnóstico que verifica dependencias, credenciales y archivos clave antes de ejecutar el agente. |
| `requirements.txt` | Dependencias mínimas de Python: `google-adk`, `requests`, `python-dotenv`. |
| `xwiki_agent/xwiki_mcp_server_activity.log` | Registro rotativo que se genera en cada arranque del servidor MCP. |

## 3. Requisitos previos
- Python 3.8 o superior (3.10+ recomendado).
- `pip` disponible en la variable PATH.
- Credenciales válidas para una instancia accesible de XWiki.
- Clave de Google AI Studio para modelos compatibles con ADK.
- Opcional pero recomendado: un entorno virtual (`venv` o `virtualenv`).

## 4. Instalación
1. Crear y activar un entorno virtual (opcional):
   <pre><code>python -m venv .venv
   # Windows
   .\.venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate</code></pre>
2. Instalar las dependencias:
   <pre><code>pip install --upgrade pip
   pip install -r requirements.txt</code></pre>

## 5. Configuración
1. Copia `xwiki_agent/.env` a la raíz del proyecto y renómbralo como `.env` si aún no existe.
2. Registra las credenciales en un almacén seguro:
   - Con `keyring`: `keyring set xwiki/adk bot@example.com` y define `XWIKI_KEYRING_SERVICE` / `XWIKI_KEYRING_USERNAME`.
   - O proporciona un comando en `XWIKI_SECRET_COMMAND` que devuelva `usuario:contraseña`.
   - Solo si no tienes otra opción, define `XWIKI_USER` y `XWIKI_PASS` directamente como variables de entorno.
3. Ajusta en `.env` los valores de `XWIKI_URL`, `MODEL_NAME`, `GOOGLE_API_KEY` y cualquier parámetro adicional del agente.
4. (Opcional) Establece `ADK_SESSION_DB_PATH` para controlar dónde se guarda la base de datos SQLite de sesiones persistentes.
5. Ejecuta `python -m keyring --list-backends` para confirmar que tu sistema ofrece un almacén seguro compatible.
6. Ajusta si lo necesitas `XWIKI_SEARCH_MAX_RESULTS`, `XWIKI_SEARCH_SNIPPET_MAX_CHARS` o los costes `GEMINI_*_TOKEN_COST_USD` para adaptar los límites de búsqueda y el cálculo económico.


## 6. Puesta en marcha
1. (Opcional) Ejecuta el script de diagnóstico para validar el entorno:
   <pre><code>python xwiki_agent/diagnosis_script.py</code></pre>
   El reporte indica dependencias, variables o configuraciones faltantes.

2. Inicia el servidor MCP por stdio:
   <pre><code>python xwiki_agent/server.py</code></pre>
   El servidor registra cada función listada en `ADK_XWIKI_TOOLS` y envía los logs a `xwiki_agent/xwiki_mcp_server_activity.log`.

3. En otra terminal, lanza el agente ADK para una prueba local:
   <pre><code>python xwiki_agent/agent.py</code></pre>
   El script usa una base de datos SQLite persistente para las sesiones cuando está disponible y recurre a `InMemorySessionService` solo como respaldo. Antes de cada llamada a herramienta imprime los tokens acumulados y el coste estimado.

### Automatización del servidor MCP
- Copia y ajusta `deploy/systemd/xwiki-mcp.service` para ejecutar el servidor con `systemd` (define `ExecStart`, `EnvironmentFile` y `WorkingDirectory`).
- Alternativamente, registra `deploy/supervisor/xwiki-mcp.conf` en `supervisord` para reinicios automáticos y control de logs.

## 7. Herramientas MCP expuestas
| Herramienta | Parámetros | Descripción |
| --- | --- | --- |
| `get_page` | `space_name`, `page_name` | Recupera contenido de páginas en sintaxis XWiki 2.1. |
| `create_or_update_page` | `space_name`, `page_name`, `content`, `title?` | Crea o actualiza páginas y devuelve la URL absoluta cuando está disponible. |
| `search_pages` | `query` | Realiza búsqueda global en la wiki. |
| `list_pages` | `space_name` | Lista todas las páginas dentro de un espacio. |
| `list_spaces` | - | Devuelve los espacios (carpetas) configurados en la wiki. |
| `describe_space_tree` | `space_path?`, `depth?` | Devuelve la jerarquía de subespacios y páginas comenzando en `space_path` hasta una `depth` máxima. |

Cada función se envuelve con `google.adk.tools.function_tool.FunctionTool` y se traduce al esquema MCP para que el agente pueda invocarla dinámicamente.

## 8. Monitoreo y registro
- El servidor MCP configura un `FileHandler` que sobrescribe `xwiki_agent/xwiki_mcp_server_activity.log` en cada inicio. Revisa este archivo para rastrear llamadas a herramientas, respuestas de la API y fallos HTTP.
- Considera agregar salida a consola o rotación de logs si despliegas el servidor en entornos de larga duración.

## 9. Diagnósticos y controles de calidad
- `diagnosis_script.py` comprueba versión de Python, paquetes requeridos, archivos críticos, variables de entorno y credenciales de XWiki antes de ejecutar.
- Extiende el script con pruebas de conectividad (por ejemplo, un `requests.get` controlado contra un endpoint de salud) si necesitas garantías adicionales antes de iniciar el agente.

## 10. Solución de problemas
- **Respuestas 401/403 desde XWiki**: confirma que `XWIKI_URL` sea accesible y que las credenciales estén correctamente registradas en el almacén seguro (ej. `keyring get xwiki/adk bot@example.com`).
- **`ValueError: Missing XWIKI_URL, GOOGLE_API_KEY or MODEL_NAME`**: asegúrate de que `.env` esté en la raíz del repositorio y que `python-dotenv` lo cargue.
- **Tiempos de espera o fallos de red**: confirma que la máquina que ejecuta el agente puede alcanzar el host de XWiki (proxies, VPN, firewalls y certificados SSL suelen ser la causa).
- **Mensajes de "Tool not found"**: verifica que la función esté en `ADK_XWIKI_TOOLS` y que el prompt del agente use exactamente el mismo nombre.

## 11. Próximos pasos sugeridos
- Añade rotación y envío centralizado de logs (por ejemplo, con `logging.handlers.RotatingFileHandler` o integraciones con tu stack observability).
- Instrumenta métricas de disponibilidad para el servidor MCP (endpoints de salud, uso de `supervisord` events o sondas de `systemd`).
- Define pruebas automatizadas que simulen llamadas a herramientas de XWiki con datos controlados para detectar regresiones antes del despliegue.


## 12. Pruebas para medir tasa de error
- Construye transcripciones reproducibles y mide el éxito o fallo de las llamadas a herramientas para cuantificar la tasa de error del agente.
- Añade pruebas de contrato alrededor de cada herramienta MCP usando respuestas simuladas de XWiki para detectar regresiones antes de llegar a producción.
- Registra métricas de latencia y fallas por invocación de herramienta para ajustar estrategias de reintento o retroceso exponencial.

## 13. Integración con agentes paralelos o jerárquicos
- Experimenta con marcos de orquestación que permitan agentes paralelos compartiendo este servidor MCP como capa de ejecución.
- Prototipa una configuración jerárquica donde un agente planificador descomponga objetivos y delegue operaciones de XWiki a este agente como especialista.
- Define protocolos de comunicación (mensajes, estado compartido o memorias externas) para evitar escrituras en conflicto cuando múltiples agentes actúan de forma concurrente.
