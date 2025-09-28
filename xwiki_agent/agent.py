# Importaciones necesarias para el funcionamiento del agente.
import asyncio  # Para manejar operaciones asíncronas.
import os  # Para interactuar con el sistema operativo, como leer variables de entorno.
import sys  # Para acceder a variables y funciones específicas del sistema.
import threading  # Para ejecutar corutinas en un hilo separado si ya hay un bucle de eventos corriendo.
from datetime import datetime  # Para obtener la fecha y hora actual.

from dotenv import load_dotenv  # Para cargar variables de entorno desde un archivo .env.

from google.adk.agents import Agent  # La clase base para crear agentes.
from google.adk.runners import Runner  # Para ejecutar la lógica del agente.
from google.adk.sessions import InMemorySessionService  # Para gestionar sesiones en memoria.
from google.genai import types  # Tipos de datos utilizados por la API de Google GenAI.

# Intenta importar las herramientas desde el servidor local.
# Esto es útil para mantener la modularidad y la separación de conceptos.
try:
    from .server import ADK_XWIKI_TOOLS
except ImportError:
    from server import ADK_XWIKI_TOOLS

# Función para ejecutar una corutina de forma síncrona.
def run_coro_sync(coro_fn, *args, **kwargs):
    """Ejecuta una función que produce una corutina, incluso si ya hay un bucle de eventos en ejecución."""
    try:
        # Comprueba si ya hay un bucle de eventos en ejecución.
        asyncio.get_running_loop()
    except RuntimeError:
        # Si no hay un bucle de eventos, ejecuta la corutina directamente.
        return asyncio.run(coro_fn(*args, **kwargs))

    result = {}

    # Define una función que se ejecutará en un hilo separado.
    def runner():
        try:
            # Ejecuta la corutina y almacena el resultado.
            result["value"] = asyncio.run(coro_fn(*args, **kwargs))
        except Exception as exc:  # pragma: no cover - para no afectar la cobertura de pruebas.
            # Si ocurre un error, lo almacena para lanzarlo en el hilo principal.
            result["error"] = exc

    # Crea y ejecuta el hilo.
    thread = threading.Thread(target=runner, name="agent-async-runner", daemon=True)
    thread.start()
    thread.join()  # Espera a que el hilo termine.

    # Si hubo un error en el hilo, lo lanza en el hilo principal.
    if "error" in result:
        raise result["error"]
    return result.get("value")

# Función para construir y configurar el agente.
def build_agent() -> Agent:
    """Carga la configuración y crea una instancia del agente."""
    # Carga las variables de entorno desde el archivo .env.
    load_dotenv(override=True)
    xwiki_url = os.environ.get("XWIKI_URL")
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    model_name = os.environ.get("MODEL_NAME")
    
    # Verifica que las variables de entorno necesarias estén definidas.
    if not (xwiki_url and google_api_key and model_name):
        raise ValueError("Faltan XWIKI_URL, GOOGLE_API_KEY o MODEL_NAME en .env")

    # Crea y devuelve la instancia del agente con su configuración.
    return Agent(
        name="Xwiki_Buscador",
        model=model_name,
        description="Agente para buscar informacion actualizada en XWiki.",
        tools=list(ADK_XWIKI_TOOLS.values()),  # Asigna las herramientas al agente.
        instruction=(
            "Eres un asistente amable y util. "
            "Cuando se te haga una pregunta, usa las herramientas de XWiki si es necesario. "
            "Proporciona respuestas concisas y claras. "
            "Si no estas seguro, busca informacion actualizada. "
            "Mantente educado y profesional."
        ),
    )

# Construye el agente principal que se utilizará en la aplicación.
root_agent = build_agent()

# Función principal que se ejecuta al iniciar el script.
def main():
    """Función principal para configurar y ejecutar el agente."""
    print("Bienvenido al tutorial de Google ADK!")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Python: {sys.version.split()[0]}")
    print("Entorno:", "Google Colab" if "google.colab" in sys.modules else "Local")

    # Configura el servicio de sesión en memoria.
    session_service = InMemorySessionService()
    app_name = root_agent.name
    user_id = "user_1"
    session_id = "session_001"

    # Crea una nueva sesión de forma síncrona.
    run_coro_sync(
        session_service.create_session,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    print(f"Sesion creada: app='{app_name}', usuario='{user_id}', sesion='{session_id}'")

    # Crea una instancia del Runner para manejar la ejecución del agente.
    runner = Runner(
        agent=root_agent,
        session_service=session_service,
        app_name=app_name,
    )

    # Imprime las herramientas que el agente tiene disponibles.
    print("\nHerramientas registradas:")
    for tool in root_agent.tools:
        tool_name = getattr(tool, "name", type(tool).__name__)
        tool_desc = getattr(tool, "description", "") or ""
        print(f"- {tool_name}: {tool_desc}")

    # Ejecuta el agente con un mensaje inicial del usuario.
    events = runner.run(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="Que herramientas tienes disponibles?")],
        ),
    )

    # Itera sobre los eventos generados por la ejecución del agente.
    for event in events:
        # Si el evento es una llamada a una herramienta, lo imprime.
        if hasattr(event, "is_tool_call") and event.is_tool_call():
            tool_name = getattr(getattr(event, "tool", None), "name", "desconocida")
            print(f"\nInvocando herramienta: {tool_name}")
            continue

        # Si el evento es la respuesta de una herramienta, la imprime.
        if hasattr(event, "is_tool_response") and event.is_tool_response():
            tool_name = getattr(getattr(event, "tool", None), "name", "desconocida")
            output = getattr(event, "output", None)
            print(f"Resultado de {tool_name}: {output}")
            continue

        # Si el evento es la respuesta final del agente, la imprime.
        if event.is_final_response():
            parts = getattr(event.content, "parts", [])
            text = parts[0].text if parts else ""
            print(f"\nAgent Response: {text}")

# Punto de entrada del script.
if __name__ == "__main__":
    main()