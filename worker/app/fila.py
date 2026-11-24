"""
Auxiliares de fila (Redis) - PRONTO, use como esta.

A fila guarda tarefas pendentes e os resultados prontos.
Conceito da Aula 8: quem pede nao espera; um worker processa depois.
"""
import json
import os
import uuid

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FILA_TAREFAS = "tarefas"
PREFIXO_RESULTADO = "resultado:"
TTL_RESULTADO = 86400  # Retencao de 24 horas
LIMITE_DEAD_LETTER = 100

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        _cliente = redis.from_url(REDIS_URL, decode_responses=True)
    return _cliente


def enfileirar(texto: str) -> str:
    """Coloca uma tarefa na fila e devolve o id para consulta posterior."""
    tarefa_id = str(uuid.uuid4())
    cliente().rpush(FILA_TAREFAS, json.dumps({"id": tarefa_id, "texto": texto}))
    cliente().set(
    PREFIXO_RESULTADO + tarefa_id,
    json.dumps({"status": "na_fila"}),
    ex=TTL_RESULTADO,
)
    return tarefa_id


def proxima_tarefa(timeout: int = 5):
    """Bloqueia ate chegar tarefa (ou timeout). Usado pelo worker."""
    item = cliente().blpop(FILA_TAREFAS, timeout=timeout)
    if item is None:
        return None
    return json.loads(item[1])


def guardar_resultado(tarefa_id: str, resultado: dict) -> None:
    cliente().set(
        PREFIXO_RESULTADO + tarefa_id,
        json.dumps(resultado),
        ex=TTL_RESULTADO,
    )


def buscar_resultado(tarefa_id: str):
    bruto = cliente().get(PREFIXO_RESULTADO + tarefa_id)
    return json.loads(bruto) if bruto else None


def enfileirar_tarefa(tarefa: dict) -> None:
    """Recoloca na fila uma tarefa que precisa de nova tentativa."""
    cliente().rpush(FILA_TAREFAS, json.dumps(tarefa))


def guardar_dead_letter(tarefa_id: str, dados: dict) -> None:
    """Registra a falha definitiva sem armazenar o texto original."""

    registro = {
        "id": tarefa_id,
        "tentativas": dados["tentativas"],
        "status": "erro",
    }

    with cliente().pipeline(transaction=True) as pipe:
        pipe.rpush(
            "tarefas:dead-letter",
            json.dumps(registro),
        )
        pipe.ltrim(
            "tarefas:dead-letter",
            -LIMITE_DEAD_LETTER,
            -1,
        )
        pipe.execute()

    guardar_resultado(
        tarefa_id,
        {
            "status": "erro",
            "tentativas": dados["tentativas"],
        },
    )