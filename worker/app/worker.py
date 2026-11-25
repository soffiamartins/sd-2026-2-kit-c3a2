import time
import logging
from uuid import uuid4

from app import fila
from app.modelo import carregar_modelo

logging.basicConfig(level=logging.INFO)
MAX_TENTATIVAS = 3


def main():
    logging.info("[worker] carregando modelo...")
    modelo = carregar_modelo()
    logging.info("[worker] pronto. aguardando tarefas (Ctrl+C para sair)")

    while True:
        tarefa = fila.proxima_tarefa(timeout=5)

        if tarefa is None:
            continue

        tarefa_id = tarefa["id"]
        texto = tarefa["texto"]
        tentativas = tarefa.get("tentativas", 0) + 1

        # Preserva o identificador durante todo o processamento
        trace_id = tarefa.get("trace_id") or uuid4().hex
        tarefa["trace_id"] = trace_id

        logging.info(
            f"[worker] trace_id={trace_id} | "
            f"id={tarefa_id} | "
            f"processando tentativa {tentativas}/{MAX_TENTATIVAS}"
        )

        inicio = time.time()

        try:
            resultado = modelo.prever(texto)
            vetor = modelo.vetorizar(texto)
            resultado["status"] = "pronto"

            tempo_ms = round((time.time() - inicio) * 1000, 2)
            resultado["tempo_ms"] = tempo_ms

            # Salva o resultado no Redis
            fila.guardar_resultado_com_vetor(tarefa_id, resultado, vetor)

            logging.info(
                f"[worker] trace_id={trace_id} | "
                f"OK id={tarefa_id} | "
                f"tamanho_texto={len(texto)} | "
                f"tempo_ms={tempo_ms}"
            )

        except Exception as erro:
            tempo_ms = round((time.time() - inicio) * 1000, 2)

            logging.error(
                f"[worker] trace_id={trace_id} | "
                f"ERRO id={tarefa_id} | "
                f"tentativa={tentativas} | "
                f"erro={type(erro).__name__} | "
                f"tempo_ms={tempo_ms}"
            )

            if tentativas < MAX_TENTATIVAS:
                # Reenfileira preservando o trace_id
                tarefa["tentativas"] = tentativas
                fila.enfileirar_tarefa(tarefa)

                logging.warning(
                    f"[worker] trace_id={trace_id} | "
                    f"id={tarefa_id} | tarefa reenfileirada"
                )

            else:
                # Excedeu o limite de tentativas
                fila.guardar_dead_letter(
                    tarefa_id,
                    {
                        "tarefa": tarefa,
                        "erro": str(erro),
                        "tentativas": tentativas,
                    },
                )

                logging.warning(
                    f"[worker] trace_id={trace_id} | "
                    f"id={tarefa_id} | DEAD-LETTER enviada"
                )


if __name__ == "__main__":
    main()