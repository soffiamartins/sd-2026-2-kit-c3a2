
import os
import signal
import subprocess
import sys
import time

processos = []
encerrando = False


def solicitar_encerramento(*_):
    global encerrando
    encerrando = True


signal.signal(signal.SIGTERM, solicitar_encerramento)
signal.signal(signal.SIGINT, solicitar_encerramento)


def main():
    porta = os.getenv("PORT", "8001")

    # Inicia o worker, que consome as tarefas do Redis
    worker = subprocess.Popen(
        [sys.executable, "-m", "app.worker"],
        cwd="/app/worker",
    )
    processos.append(worker)

    # Inicia a API de inferência
    api = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.api_rest:app",
            "--host", "0.0.0.0",
            "--port", porta,
        ],
        cwd="/app/inferencia",
    )
    processos.append(api)

    try:
        while not encerrando:
            for processo in processos:
                if processo.poll() is not None:
                    print(
                        f"Um processo encerrou: {processo.returncode}",
                        flush=True,
                    )
                    return 1
            time.sleep(1)

        return 0

    finally:
        for processo in processos:
            if processo.poll() is None:
                processo.terminate()

        for processo in processos:
            try:
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.kill()


if __name__ == "__main__":
    sys.exit(main())
