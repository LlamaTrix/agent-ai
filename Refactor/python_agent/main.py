import subprocess
import sys
import time

def run_services():
    # Levantar Streamlit
    streamlit = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", "8501"],
    )
    print("✅ Streamlit corriendo en http://localhost:8501")

    # Esperar un poco para que Streamlit arranque antes de la API
    time.sleep(2)

    # Levantar FastAPI (Uvicorn)
    fastapi = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--reload", "--port", "8001"],
    )
    print("✅ FastAPI corriendo en http://localhost:8000")

    try:
        # Mantener ambos procesos vivos
        streamlit.wait()
        fastapi.wait()
    except KeyboardInterrupt:
        print("\n🛑 Deteniendo servicios...")
        streamlit.terminate()
        fastapi.terminate()

if __name__ == "__main__":
    run_services()
    