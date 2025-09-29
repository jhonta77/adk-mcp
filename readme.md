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
| `xwiki_agent/agent.py` | Configures the ADK agent (`Xwiki_Buscador`), loads environment variables, and registers the MCP tools exposed by the server. |
| `xwiki_agent/server.py` | Implements the MCP server, wraps the XWiki REST API as callable tools, and manages request logging. |
| `xwiki_agent/prompt.py` | Base prompt that governs how the agent decides when and how to invoke the tools. |
| `xwiki_agent/diagnosis_script.py` | Self-diagnosis utility that verifies dependencies, credentials, and key files before running the agent. |
| `requirements.txt` | Minimal Python dependencies: `google-adk`, `requests`, `python-dotenv`. |
| `xwiki_agent/xwiki_mcp_server_activity.log` | Rolling log regenerated every time the MCP server starts. |

## 3. Prerequisites
- Python 3.8 or newer (3.10+ recommended).
- `pip` available on the PATH.
- Valid credentials for an accessible XWiki instance.
- Google AI Studio API key for ADK-compatible models.
- Optional but recommended: a virtual environment (`venv` or `virtualenv`).

## 4. Installation
1. Create and activate a virtual environment (optional):
   <pre><code>python -m venv .venv
   # Windows
   .\\.venv\\Scripts\\activate
   # macOS/Linux
   source .venv/bin/activate</code></pre>
2. Install the dependencies:
   <pre><code>pip install --upgrade pip
   pip install -r requirements.txt</code></pre>

## 5. Configuration
1. Create a `.env` file in the project root with the required variables:
   <pre><code>GOOGLE_API_KEY=AIza...                    # Google AI Studio key
MODEL_NAME=models/gemini-1.5-pro          # ADK-compatible model name
XWIKI_URL=https://<your-instance>/xwiki   # Base URL for XWiki
XWIKI_USER=<username>
XWIKI_PASS=<password>
XWIKI_WIKI_NAME=xwiki                     # Change if your wiki uses a different ID</code></pre>
   Never commit or share these secrets.

2. If you prefer not to rely on environment variables, override the constants inside `xwiki_agent/server.py`. For production deployments, loading from `.env` is safer.

3. Adjust `xwiki_agent/prompt.py` when you need a different tone, tool policy, or escalation strategy for the agent.

## 6. Running the Stack
1. (Optional) Run the diagnosis script to validate the environment:
   <pre><code>python xwiki_agent/diagnosis_script.py</code></pre>
   The report highlights missing dependencies, environment variables, or misconfigurations.

2. Start the MCP server over stdio:
   <pre><code>python xwiki_agent/server.py</code></pre>
   The server registers every function listed in `ADK_XWIKI_TOOLS` and streams logs to `xwiki_agent/xwiki_mcp_server_activity.log`.

3. In a separate terminal, launch the ADK agent for a local dry run:
   <pre><code>python xwiki_agent/agent.py</code></pre>
   The script spins up an in-memory session (`InMemorySessionService`) and sends a sample prompt so you can verify the available tools and overall wiring.

## 7. Exposed MCP Tools
| Tool | Parameters | Description |
| --- | --- | --- |
| `get_page` | `space_name`, `page_name` | Retrieves page content in XWiki 2.1 syntax. |
| `create_or_update_page` | `space_name`, `page_name`, `content`, `title?` | Creates or updates pages and returns the absolute URL when available. |
| `search_pages` | `query` | Performs a global search across the wiki. |
| `list_pages` | `space_name` | Lists every page within a given space. |
| `list_spaces` | - | Returns the spaces (folders) defined in the wiki. |
| `describe_space_tree` | `space_path?`, `depth?` | Devuelve la jerarquía de subespacios y páginas comenzando en `space_path` hasta una `depth` máxima. |

Each function is wrapped by `google.adk.tools.function_tool.FunctionTool` and translated to MCP schema so the agent can invoke it dynamically.

## 8. Logging and Monitoring
- The MCP server configures a `FileHandler` that overwrites `xwiki_agent/xwiki_mcp_server_activity.log` on each start. Inspect this file to trace tool calls, API responses, and HTTP failures.
- Consider adding a console handler or rotating logs if you deploy the server to a long-running environment.

## 9. Diagnostics and Quality Gates
- `diagnosis_script.py` checks the Python version, required packages, critical files, environment variables, and XWiki credentials before you ship.
- Extend the script with connectivity probes (for example, a sandboxed `requests.get` against a health endpoint) if you need stronger guarantees before starting the agent.

## 10. Troubleshooting
- **401/403 responses from XWiki**: double-check `XWIKI_USER` and `XWIKI_PASS`, and confirm the account has sufficient API permissions.
- **`ValueError: Missing XWIKI_URL, GOOGLE_API_KEY or MODEL_NAME`**: ensure the `.env` file is in the repository root and that `python-dotenv` loads it.
- **Network timeouts**: verify that the machine running the agent can reach the XWiki host (proxies, VPN requirements, firewalls, and SSL certificates often cause issues).
- **"Tool not found" messages**: confirm the function has been added to `ADK_XWIKI_TOOLS` and that the agent prompt references the exact same name.

## 11. Suggested Next Steps
- Harden secret management by sourcing XWiki credentials from a secure vault service or OS-level keychain.
- Swap `InMemorySessionService` for a persistent alternative if you plan to keep long-lived conversations.
- Automate deployment with process managers (for example, `systemd` or `supervisord`) to keep the MCP server online.

## 12. Error-Rate Measurement Tests
- Build replayable interaction transcripts and measure tool-call success versus failure to quantify the agent's error rate.
- Add contract tests around each MCP tool using mocked XWiki responses so regressions surface before hitting the live wiki.
- Track latency and failure metrics per tool invocation to inform retry logic or backoff strategies.

## 13. Parallel or Hierarchical Agent Integration
- Experiment with orchestration frameworks that support parallel agents handing off work, with this MCP server acting as a shared execution layer.
- Prototype a hierarchical setup where a planner agent decomposes goals and delegates XWiki operations to this agent as a specialist.
- Define communication protocols (messages, shared state, or memory stores) so agents avoid conflicting writes when operating concurrently.