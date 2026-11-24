"""
Auxiliares de fila (Redis) - PRONTO, use como esta.

A fila guarda tarefas pendentes e os resultados prontos.
Conceito da Aula 8: quem pede nao espera; um worker processa depois.
"""
import json
import logging
import os
import uuid

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FILA_TAREFAS = "tarefas"
PREFIXO_RESULTADO = "resultado:"

_cliente = None


def cliente():
    global _cliente
    if _cliente is None:
        _cliente = redis.from_url(REDIS_URL, decode_responses=True)
    return _cliente


def enfileirar(texto: str, trace_id: str | None = None) -> str:
    """Coloca uma tarefa na fila com rastreamento distribuido."""

    tarefa_id = str(uuid.uuid4())
    trace_id = trace_id or uuid.uuid4().hex

    tarefa = {
        "id": tarefa_id,
        "texto": texto,
        "trace_id": trace_id,
    }

    with cliente().pipeline(transaction=True) as pipe:
        pipe.set(
            PREFIXO_RESULTADO + tarefa_id,
            json.dumps({"status": "na_fila"}),
        )
        pipe.rpush(FILA_TAREFAS, json.dumps(tarefa))
        pipe.execute()

    logging.info(
        f"[fila] trace_id={trace_id} | "
        f"id={tarefa_id} | tarefa enfileirada"
    )

    return tarefa_id


def proxima_tarefa(timeout: int = 5):
    """Bloqueia ate chegar tarefa (ou timeout). Usado pelo worker."""
    item = cliente().blpop(FILA_TAREFAS, timeout=timeout)
    if item is None:
        return None
    return json.loads(item[1])


def guardar_resultado(tarefa_id: str, resultado: dict) -> None:
    cliente().set(PREFIXO_RESULTADO + tarefa_id, json.dumps(resultado))


def buscar_resultado(tarefa_id: str):
    bruto = cliente().get(PREFIXO_RESULTADO + tarefa_id)
    return json.loads(bruto) if bruto else None
