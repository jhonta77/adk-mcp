#!/usr/bin/env python3
"""
SCRIPT DE DIAGNÓSTICO PARA AGENTE XWIKI MCP
===========================================
Este script está diseñado para ser una herramienta de autodiagnóstico que verifica
si el entorno de ejecución está correctamente configurado antes de intentar
lanzar el agente principal. Realiza una serie de comprobaciones, desde la versión
de Python hasta la validez de los archivos de configuración y la conectividad.

EJECUCIÓN:
Desde la terminal, en el directorio 'xwiki_agent', ejecuta:
python diagnosis_script.py
"""

import sys
import os
import subprocess
from pathlib import Path
import importlib.util

# --- Funciones de Utilidad para la Interfaz ---

def print_header(title: str):
    """Imprime un encabezado visualmente distintivo para separar las secciones del diagnóstico."""
    print(f"\n{'='*60}")
    print(f"🔍 {title}")
    print('='*60)

def print_status(item: str, status: bool, details: str = ""):
    """Formatea y muestra el resultado de una comprobación específica.

    Args:
        item (str): La descripción de la comprobación.
        status (bool): True si la comprobación fue exitosa, False en caso contrario.
        details (str, optional): Información adicional sobre el resultado.
    """
    icon = "✅" if status else "❌"
    print(f"{icon} {item}")
    if details:
        # Imprime detalles con sangría para facilitar la lectura.
        print(f"   └─ {details}")

# --- Funciones de Verificación ---

def check_python_version():
    """Verifica que la versión de Python instalada sea compatible (3.8 o superior)."""
    print_header("VERIFICACIÓN DE VERSIÓN DE PYTHON")
    
    # Obtiene la información de la versión actual del intérprete.
    version = sys.version_info
    print(f"🐍 Versión de Python detectada: {version.major}.{version.minor}.{version.micro}")
    
    # Comprueba si la versión es igual o superior a 3.8.
    if version.major >= 3 and version.minor >= 8:
        print_status("Versión de Python", True, f"La versión {version.major}.{version.minor} es compatible.")
        return True
    else:
        print_status("Versión de Python", False, f"Se requiere Python 3.8 o superior, pero se encontró {version.major}.{version.minor}.")
        return False

def check_dependencies():
    """Asegura que todas las bibliotecas de Python requeridas estén instaladas."""
    print_header("VERIFICACIÓN DE DEPENDENCIAS")
    
    # Diccionario de módulos a verificar y el nombre del paquete para la instalación.
    dependencies = {
        "google.adk.agents": "google-adk",
        "mcp": "mcp", 
        "requests": "requests",
        "dotenv": "python-dotenv",
    }
    
    all_ok = True
    
    # Itera sobre cada dependencia requerida.
    for module_name, package_name in dependencies.items():
        try:
            # Intenta importar el módulo dinámicamente.
            importlib.import_module(module_name)
            print_status(f"Paquete '{package_name}'", True, f"El módulo '{module_name}' se importó correctamente.")
        except ImportError:
            # Si la importación falla, el paquete no está instalado.
            print_status(f"Paquete '{package_name}'", False, f"No se encontró. Instálalo con: pip install {package_name}")
            all_ok = False
    
    return all_ok

def check_files():
    """Verifica la existencia de los archivos clave del proyecto."""
    print_header("VERIFICACIÓN DE ARCHIVOS DEL PROYECTO")
    
    # Obtiene la ruta del directorio donde se encuentra este script.
    current_dir = Path(__file__).parent
    
    # Define los archivos que son cruciales para el funcionamiento.
    required_files = {
        "server.py": "(REQUERIDO) Contiene la lógica del servidor MCP y las herramientas de XWiki.",
        "agent.py": "(REQUERIDO) Define y configura el agente de IA.",
    }
    
    # Define archivos que son útiles pero no estrictamente necesarios.
    optional_files = {
        ".env": "(RECOMENDADO) Para almacenar variables de entorno como claves de API.",
    }
    
    all_required_ok = True
    
    # Comprueba la existencia de cada archivo requerido.
    for filename, description in required_files.items():
        filepath = current_dir / filename
        exists = filepath.exists()
        print_status(f"Archivo '{filename}'", exists, description)
        if not exists:
            all_required_ok = False
    
    # Comprueba la existencia de archivos opcionales.
    for filename, description in optional_files.items():
        filepath = current_dir / filename
        exists = filepath.exists()
        print_status(f"Archivo '{filename}'", exists, description)
    
    return all_required_ok

def check_server_syntax():
    """Analiza 'server.py' para detectar errores de sintaxis y elementos faltantes."""
    print_header("VERIFICACIÓN DE SINTAXIS Y CONTENIDO DE SERVER.PY")
    
    server_path = Path(__file__).parent / "server.py"
    
    if not server_path.exists():
        print_status("Análisis de 'server.py'", False, "El archivo no existe.")
        return False
    
    try:
        # Lee el contenido del archivo del servidor.
        with open(server_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Intenta compilar el código para validar la sintaxis de Python.
        compile(content, str(server_path), 'exec')
        print_status("Sintaxis de 'server.py'", True, "El archivo tiene una sintaxis de Python válida.")
        
        # Lista de funciones y variables críticas que deben estar definidas en el servidor.
        required_elements = [
            "list_spaces", "get_page", "create_or_update_page",
            "search_pages", "list_pages", "XWIKI_URL", "run_mcp_stdio_server"
        ]
        
        missing_elements = [elem for elem in required_elements if elem not in content]
        
        if missing_elements:
            print_status("Elementos requeridos en 'server.py'", False, f"Faltan las siguientes definiciones: {', '.join(missing_elements)}")
            return False
        else:
            print_status("Elementos requeridos en 'server.py'", True, "Todas las funciones y variables necesarias están presentes.")
            return True
            
    except SyntaxError as e:
        print_status("Sintaxis de 'server.py'", False, f"Error de sintaxis detectado: {e}")
        return False
    except Exception as e:
        print_status("Análisis de 'server.py'", False, f"Ocurrió un error inesperado al leer el archivo: {e}")
        return False

def check_api_keys():
    """Verifica que la clave de API de Google esté configurada y sea válida."""
    print_header("VERIFICACIÓN DE CLAVE DE API DE GOOGLE")
    
    try:
        from dotenv import load_dotenv
        load_dotenv() # Carga el archivo .env si existe.
    except ImportError:
        pass # Si python-dotenv no está, se omite.
    
    google_api_key = os.getenv("GOOGLE_API_KEY")
    
    if google_api_key:
        # Una clave válida de Google AI empieza con 'AIza' y tiene una longitud considerable.
        if len(google_api_key) > 30 and google_api_key.startswith("AIza"):
            masked_key = f"{google_api_key[:8]}...{google_api_key[-4:]}" # Ofusca la clave por seguridad.
            print_status("Clave de API de Google (GOOGLE_API_KEY)", True, f"Encontrada en variable de entorno: {masked_key}")
            return True
        else:
            print_status("Clave de API de Google (GOOGLE_API_KEY)", False, "La clave encontrada en la variable de entorno parece inválida o es un placeholder.")
            return False
    else:
        print_status("Clave de API de Google (GOOGLE_API_KEY)", False, "No se encontró en las variables de entorno. Asegúrate de crear un archivo .env con esta variable.")
        return False

def check_xwiki_config():
    """Verifica que las credenciales de XWiki estén configuradas en 'server.py'."""
    print_header("VERIFICACIÓN DE CONFIGURACIÓN DE XWIKI")
    
    server_path = Path(__file__).parent / "server.py"
    
    if not server_path.exists():
        print_status("Configuración de XWiki", False, "El archivo 'server.py' no fue encontrado.")
        return False
    
    try:
        with open(server_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Credenciales a buscar dentro del archivo.
        configs_to_check = {
            'XWIKI_URL': 'URL del servidor XWiki',
            'XWIKI_USER': 'Usuario para la API de XWiki',
            'XWIKI_PASS': 'Contraseña para la API de XWiki',
        }
        
        all_configs_ok = True
        
        for config_name, description in configs_to_check.items():
            # Busca la línea donde se define la variable.
            if config_name in content:
                lines = content.split('\n')
                found_line = False
                for line in lines:
                    if line.strip().startswith(f'{config_name} ='):
                        found_line = True
                        # Extrae el valor de la variable.
                        value = line.split('=', 1)[1].strip().strip('"\'')
                        # Comprueba si el valor es un placeholder o está vacío.
                        if value and 'your_' not in value.lower() and 'change_me' not in value.lower() and value != "":
                            print_status(f"Variable '{config_name}'", True, f"{description} parece estar configurada.")
                        else:
                            print_status(f"Variable '{config_name}'", False, f"{description} parece ser un placeholder o está vacía. Debes cambiarla en 'server.py'.")
                            all_configs_ok = False
                        break
                if not found_line:
                    print_status(f"Variable '{config_name}'", False, f"La definición de '{description}' no se encontró en el formato esperado.")
                    all_configs_ok = False
            else:
                print_status(f"Variable '{config_name}'", False, f"La definición de '{description}' no existe en 'server.py'.")
                all_configs_ok = False
        
        return all_configs_ok
        
    except Exception as e:
        print_status("Análisis de configuración de XWiki", False, f"Ocurrió un error inesperado: {e}")
        return False

# --- Reporte y Ejecución Principal ---

def generate_report(results: dict):
    """Genera un resumen final con los resultados de todas las verificaciones."""
    print_header("REPORTE FINAL DE DIAGNÓSTICO")
    
    total_checks = len(results)
    passed_checks = sum(1 for result in results.values() if result)
    
    print(f"📊 Total de verificaciones: {passed_checks} de {total_checks} pasaron exitosamente.")
    
    if passed_checks == total_checks:
        print("\n🎉 ¡Excelente! Parece que todo está configurado correctamente.")
        print("✅ Ahora puedes intentar ejecutar el agente principal con: python agent.py")
    else:
        print(f"\n⚠️ Se encontraron {total_checks - passed_checks} problemas de configuración.")
        print("❌ Por favor, revisa los errores marcados con '❌' en el reporte de arriba antes de continuar.")
        
        print("\n🔧 PRÓXIMOS PASOS SUGERIDOS:")
        # Proporciona una guía basada en las comprobaciones que fallaron.
        if not results.get('dependencies', True):
            print("  1. Instala las dependencias de Python faltantes con 'pip install'.")
        if not results.get('files', True):
            print("  2. Asegúrate de que los archivos 'server.py' y 'agent.py' estén en el mismo directorio que este script.")
        if not results.get('api_keys', True):
            print("  3. Configura tu clave de API de Google en un archivo .env.")
        if not results.get('xwiki_config', True):
            print("  4. Revisa y corrige las credenciales de XWiki en el archivo 'server.py'.")
        if not results.get('server_syntax', True):
            print("  5. Corrige los errores de sintaxis o las definiciones faltantes en 'server.py'.")

def main():
    """Función principal que orquesta la ejecución de todas las verificaciones."""
    print("🚀 INICIANDO DIAGNÓSTICO DEL AGENTE XWIKI MCP 🚀")
    print("Este script verificará que todos los componentes estén listos para la ejecución.")
    
    # Diccionario para almacenar los resultados (True/False) de cada comprobación.
    results = {
        'python_version': check_python_version(),
        'dependencies': check_dependencies(),
        'files': check_files(),
        'api_keys': check_api_keys(),
        'server_syntax': check_server_syntax(),
        'xwiki_config': check_xwiki_config(),
    }
    
    # Genera el reporte final basado en los resultados.
    generate_report(results)

# Punto de entrada del script: si se ejecuta directamente, llama a la función main.
if __name__ == "__main__":
    main()
