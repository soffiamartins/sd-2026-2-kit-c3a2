import logging
import time
import os
import secrets

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel

from app import fila
from app.modelo import carregar_modelo

# Configuração de logs para a Tarefa 6
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Serviço de Inferência - C1.A2", version="0.1.0")

modelo = None

def exigir_chave_interna(
    x_chave_interna: Annotated[
        str | None, Header(alias="X-Chave-Interna")
    ] = None,
):
    chave = os.getenv("CHAVE_INTERNA", "")

    if len(chave) < 32:
        raise HTTPException(
            status_code=503,
            detail="Servico interno nao configurado.",
        )

    if not x_chave_interna or not secrets.compare_digest(
        x_chave_interna.encode("utf-8"),
        chave.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=403,
            detail="Acesso interno nao autorizado.",
        )

def obter_trace_id(valor: str | None = None) -> str:
    if valor:
        try:
            return UUID(valor).hex
        except ValueError:
            pass

    return uuid4().hex


class Entrada(BaseModel):
    texto: str


@app.on_event("startup")
def _subir():
    """Carrega o modelo UMA vez. Este é o ponto-chave da Aula 6."""
    global modelo
    inicio = time.time()
    modelo = carregar_modelo()
    print(f"[startup] modelo carregado em {time.time() - inicio:.3f}s")


@app.get("/saude")
def saude():
    return {"status": "ok", "modelo_carregado": modelo is not None}


@app.post("/predict-sync", dependencies=[Depends(exigir_chave_interna)])
def predict_sync(entrada: Entrada):
    """Inferência SÍNCRONA: o cliente espera a resposta. Lab da Aula 6."""
    if not entrada.texto.strip():
        raise HTTPException(status_code=400, detail="texto vazio")
    inicio = time.time()
    resultado = modelo.prever(entrada.texto)
    tempo_ms = round((time.time() - inicio) * 1000, 2)
    resultado["tempo_ms"] = tempo_ms

    # TAREFA 6: Log da requisição síncrona
    logging.info(f"[REST /predict-sync] tamanho_entrada={len(entrada.texto)} | tempo_ms={tempo_ms}")

    return resultado


# ------------------------------------------------------------------
# TAREFA 1 - submissão assíncrona
# ------------------------------------------------------------------
@app.post( "/predict", status_code=202, dependencies=[Depends(exigir_chave_interna)],)
def predict(
    entrada: Entrada,
    x_trace_id: Annotated[
        str | None, Header(alias="X-Trace-ID")
    ] = None,
):
    """Enfileira a tarefa com rastreamento distribuido."""

    trace_id = obter_trace_id(x_trace_id)

    if not entrada.texto.strip():
        raise HTTPException(
            status_code=400,
            detail="O texto não pode estar vazio",
        )

    tarefa_id = fila.enfileirar(
        entrada.texto,
        trace_id=trace_id,
    )

    logging.info(
        f"[inferencia] trace_id={trace_id} | "
        f"id={tarefa_id} | "
        f"tamanho_entrada={len(entrada.texto)} | "
        f"tarefa recebida"
    )

    return {"id": tarefa_id}

# ------------------------------------------------------------------
# TAREFA 2 - consulta do resultado
# ------------------------------------------------------------------
@app.get( "/resultado/{tarefa_id}", dependencies=[Depends(exigir_chave_interna)],)
def resultado(
    tarefa_id: str,
    x_trace_id: Annotated[
        str | None, Header(alias="X-Trace-ID")
    ] = None,
):
    """Consulta o resultado com rastreamento."""

    trace_id = obter_trace_id(x_trace_id)

    res = fila.buscar_resultado(tarefa_id)

    if res is None:
        logging.warning(
            f"[inferencia] trace_id={trace_id} | "
            f"id={tarefa_id} | NAO ENCONTRADO"
        )

        raise HTTPException(
            status_code=404,
            detail="tarefa não encontrada",
        )

    logging.info(
        f"[inferencia] trace_id={trace_id} | "
        f"id={tarefa_id} | status={res.get('status')}"
    )

    return res