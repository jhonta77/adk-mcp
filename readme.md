# ADK XWiki Agent

## 1. Overview
This project delivers a conversational agent built with the Google Agent Development Kit (ADK) and the Model Context Protocol (MCP). The agent connects to an XWiki instance to fetch, create, and update content through structured tool calls while keeping a natural dialogue with the user.

### High-Level Flow
<pre>
User -> ADK Runner -> MCP Server (server.py) -> XWiki REST API
</pre>

## 2. Repository Layout
| Path | Purpose |
| --- | --- |
|  | Configures the ADK agent (), loads environment variables, and registers the MCP tools exposed by the server. |
|  | Implements the MCP server, wraps the XWiki REST API as callable tools, and manages request logging. |
|  | Base prompt that governs how the agent decides when and how to invoke the tools. |
| 🚀 INICIANDO DIAGNÓSTICO DEL AGENTE XWIKI MCP 🚀
Este script verificará que todos los componentes estén listos para la ejecución.

============================================================
🔍 VERIFICACIÓN DE VERSIÓN DE PYTHON
============================================================
🐍 Versión de Python detectada: 3.12.3
✅ Versión de Python
   └─ La versión 3.12 es compatible.

============================================================
🔍 VERIFICACIÓN DE DEPENDENCIAS
============================================================
❌ Paquete 'google-adk'
   └─ No se encontró. Instálalo con: pip install google-adk
❌ Paquete 'mcp'
   └─ No se encontró. Instálalo con: pip install mcp
✅ Paquete 'requests'
   └─ El módulo 'requests' se importó correctamente.
❌ Paquete 'python-dotenv'
   └─ No se encontró. Instálalo con: pip install python-dotenv

============================================================
🔍 VERIFICACIÓN DE ARCHIVOS DEL PROYECTO
============================================================
✅ Archivo 'server.py'
   └─ (REQUERIDO) Contiene la lógica del servidor MCP y las herramientas de XWiki.
✅ Archivo 'agent.py'
   └─ (REQUERIDO) Define y configura el agente de IA.
✅ Archivo '.env'
   └─ (RECOMENDADO) Para almacenar variables de entorno como claves de API.

============================================================
🔍 VERIFICACIÓN DE CLAVE DE API DE GOOGLE
============================================================
❌ Clave de API de Google (GOOGLE_API_KEY)
   └─ No se encontró en las variables de entorno. Asegúrate de crear un archivo .env con esta variable.

============================================================
🔍 VERIFICACIÓN DE SINTAXIS Y CONTENIDO DE SERVER.PY
============================================================
✅ Sintaxis de 'server.py'
   └─ El archivo tiene una sintaxis de Python válida.
✅ Elementos requeridos en 'server.py'
   └─ Todas las funciones y variables necesarias están presentes.

============================================================
🔍 VERIFICACIÓN DE CONFIGURACIÓN DE XWIKI
============================================================
✅ Variable 'XWIKI_URL'
   └─ URL del servidor XWiki parece estar configurada.
✅ Variable 'XWIKI_USER'
   └─ Usuario para la API de XWiki parece estar configurada.
✅ Variable 'XWIKI_PASS'
   └─ Contraseña para la API de XWiki parece estar configurada.

============================================================
🔍 REPORTE FINAL DE DIAGNÓSTICO
============================================================
📊 Total de verificaciones: 4 de 6 pasaron exitosamente.

⚠️ Se encontraron 2 problemas de configuración.
❌ Por favor, revisa los errores marcados con '❌' en el reporte de arriba antes de continuar.

🔧 PRÓXIMOS PASOS SUGERIDOS:
  1. Instala las dependencias de Python faltantes con 'pip install'.
  3. Configura tu clave de API de Google en un archivo .env. | Self-diagnosis utility that verifies dependencies, credentials, and key files before running the agent. |
|  | Minimal Python dependencies: , , . |
|  | Rolling log file regenerated every time the MCP server starts. |

## 3. Prerequisites
- Python 3.8 or newer (3.10+ recommended).
-  available on the PATH.
- Valid credentials for an accessible XWiki instance.
- Google AI Studio API key for ADK-compatible models.
- Optional but recommended: a virtual environment ( or ).

## 4. Installation
1. Create and activate a virtual environment (optional):
   <pre><code>python -m venv .venv
   # Windows
   .\.venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate</code></pre>
2. Install the dependencies:
   <pre><code>pip install --upgrade pip
   pip install -r requirements.txt</code></pre>

## 5. Configuration
1. Create a  file in the project root with the required variables:
   <pre><code>GOOGLE_API_KEY=AIza...                    # Google AI Studio key
MODEL_NAME=models/gemini-1.5-pro          # ADK-compatible model name
XWIKI_URL=https://<your-instance>/xwiki   # Base URL for XWiki
XWIKI_USER=<username>
XWIKI_PASS=<password>
XWIKI_WIKI_NAME=xwiki                     # Change if your wiki uses a different ID</code></pre>
   Never commit or share these secrets.

2. If you prefer not to rely on environment variables, you can override the constants inside , but loading them from  is safer for production deployments.

3. Adjust  when you need a different tone, tool policy, or escalation strategy for the agent.

## 6. Running the Stack
1. (Optional) Run the diagnosis script to validate the environment:
   <pre><code>python xwiki_agent/diagnosis_script.py</code></pre>
   The report highlights missing dependencies, environment variables, or misconfigurations.

2. Start the MCP server over stdio:
   <pre><code>python xwiki_agent/server.py</code></pre>
   The server registers every function listed in  and streams logs to .

3. In a separate terminal, launch the ADK agent for a local dry run:
   <pre><code>python xwiki_agent/agent.py</code></pre>
   The script spins up an in-memory session () and sends a sample prompt so you can verify the available tools and overall wiring.

## 7. Exposed MCP Tools
| Tool | Parameters | Description |
| --- | --- | --- |
|  | ,  | Retrieves page content in XWiki 2.1 syntax. |
|  | , , ,  | Creates or updates pages and returns the absolute URL when available. |
|  |  | Performs a global search across the wiki. |
|  |  | Lists every page within a given space. |
|  | - | Returns the spaces (folders) defined in the wiki. |

Each function is wrapped by  and translated to MCP schema so the agent can invoke it dynamically.

## 8. Logging and Monitoring
- The MCP server configures a  that overwrites  on each start. Inspect this file to trace tool calls, API responses, and HTTP failures.
- Consider adding a console handler or rotating logs if you deploy the server to a long-running environment.

## 9. Diagnostics and Quality Gates
-  checks the Python version, required packages, critical files, environment variables, and XWiki credentials before you ship.
- Extend the script with connectivity probes (for example, a sandboxed  against a health endpoint) if you need stronger guarantees before starting the agent.

## 10. Troubleshooting
- **401/403 responses from XWiki**: double-check  and , and confirm the account has sufficient API permissions.
- ****: ensure the  file is in the repository root and that  loads it.
- **Network timeouts**: verify that the machine running the agent can reach the XWiki host (proxies, VPN requirements, firewalls, and SSL certificates often cause issues).
- **"Tool not found" messages**: confirm the function has been added to  and that the agent prompt references the exact same name.

## 11. Suggested Next Steps
- Harden secret management by sourcing XWiki credentials from a secure vault service or OS-level keychain.
- Swap  for a persistent alternative if you plan to keep long-lived conversations.
- Automate deployment with process managers (for example,  or ) to keep the MCP server online.

## 12. Error-Rate Measurement Tests
- Build replayable interaction transcripts and measure tool-call success versus failure to quantify the agent's error rate.
- Add contract tests around each MCP tool using mocked XWiki responses so regressions surface before hitting the live wiki.
- Track latency and failure metrics per tool invocation to inform retry logic or backoff strategies.

## 13. Parallel or Hierarchical Agent Integration
- Experiment with orchestration frameworks that support parallel agents handing off work, with this MCP server acting as a shared execution layer.
- Prototype a hierarchical setup where a planner agent decomposes goals and delegates XWiki operations to this agent as a specialist.
- Define communication protocols (messages, shared state, or memory stores) so agents avoid conflicting writes when operating concurrently.
