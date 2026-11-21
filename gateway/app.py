
"""API Gateway: autenticacao JWT, rate limiting e inferencia."""

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import os
import secrets
import time

import jwt
import redis
import requests

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from redis.exceptions import RedisError


app = FastAPI(title="Gateway - C3.A2")

URL_INFERENCIA = os.getenv("URL_INFERENCIA", "http://localhost:8001")
AUTENTICACAO_BEARER = HTTPBearer(auto_error=False)
ALGORITMO_JWT = "HS256"
MINUTOS_EXPIRACAO = 60

# O incremento e a expiracao acontecem atomicamente no Redis.
SCRIPT_RATE_LIMIT = """
local contador = redis.call('INCR', KEYS[1])

if contador == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end

return {contador, redis.call('TTL', KEYS[1])}
"""


class Entrada(BaseModel):
    texto: str


class CredenciaisLogin(BaseModel):
    usuario: str
    senha: str


def configuracao_jwt() -> tuple[str, str, str]:
    segredo = os.getenv("JWT_SEGREDO", "")
    usuario = os.getenv("JWT_USUARIO", "")
    senha = os.getenv("JWT_SENHA", "")

    if len(segredo) < 32 or not usuario or not senha:
        raise HTTPException(
            status_code=503,
            detail="Autenticacao nao configurada. Verifique as variaveis JWT_*.",
        )

    return segredo, usuario, senha


def iguais_em_tempo_constante(primeiro: str, segundo: str) -> bool:
    return secrets.compare_digest(
        primeiro.encode("utf-8"),
        segundo.encode("utf-8"),
    )


def exigir_jwt(
    autorizacao: HTTPAuthorizationCredentials | None = Depends(AUTENTICACAO_BEARER),
) -> str:
    if autorizacao is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT ausente ou invalido.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    segredo, usuario_configurado, _ = configuracao_jwt()

    try:
        dados = jwt.decode(
            autorizacao.credentials,
            segredo,
            algorithms=[ALGORITMO_JWT],
            options={"require": ["sub", "iat", "exp"]},
        )

        if not iguais_em_tempo_constante(dados["sub"], usuario_configurado):
            raise jwt.InvalidTokenError("Usuario do token nao corresponde")

    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT ausente ou invalido.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    return dados["sub"]


@lru_cache
def obter_redis():
    return redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def configuracao_rate_limit() -> tuple[int, int]:
    try:
        maximo = int(os.getenv("RATE_LIMIT_MAXIMO", "10"))
        janela = int(os.getenv("RATE_LIMIT_JANELA_SEGUNDOS", "60"))
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="Configuracao de rate limiting invalida.",
        ) from None

    if maximo <= 0 or janela <= 0:
        raise HTTPException(
            status_code=503,
            detail="Configuracao de rate limiting invalida.",
        )

    return maximo, janela


def limitar_requisicoes(
    request: Request,
    response: Response,
    usuario: str = Depends(exigir_jwt),
) -> None:
    maximo, janela = configuracao_rate_limit()

    ip_cliente = request.client.host if request.client else "desconhecido"

    # Evita armazenar diretamente usuario e IP na chave do Redis.
    identificador = hashlib.sha256(
        f"{usuario}:{ip_cliente}".encode("utf-8")
    ).hexdigest()

    chave = f"rate-limit:predict:{identificador}"

    try:
        contador, tempo_restante = obter_redis().eval(
            SCRIPT_RATE_LIMIT,
            1,
            chave,
            janela,
        )
    except RedisError:
        raise HTTPException(
            status_code=503,
            detail="Servico de controle de requisicoes indisponivel.",
        ) from None

    contador = int(contador)
    tempo_restante = max(1, int(tempo_restante))

    if contador > maximo:
        raise HTTPException(
            status_code=429,
            detail="Limite de requisicoes excedido. Tente novamente mais tarde.",
            headers={
                "Retry-After": str(tempo_restante),
                "X-RateLimit-Limit": str(maximo),
                "X-RateLimit-Remaining": "0",
            },
        )

    response.headers["X-RateLimit-Limit"] = str(maximo)
    response.headers["X-RateLimit-Remaining"] = str(
        max(0, maximo - contador)
    )


@app.post("/login")
def login(credenciais: CredenciaisLogin):
    segredo, usuario_configurado, senha_configurada = configuracao_jwt()

    usuario_correto = iguais_em_tempo_constante(
        credenciais.usuario,
        usuario_configurado,
    )
    senha_correta = iguais_em_tempo_constante(
        credenciais.senha,
        senha_configurada,
    )

    if not (usuario_correto and senha_correta):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario ou senha incorretos.",
        )

    agora = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": usuario_configurado,
            "iat": agora,
            "exp": agora + timedelta(minutes=MINUTOS_EXPIRACAO),
        },
        segredo,
        algorithm=ALGORITMO_JWT,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 3600,
    }


@app.middleware("http")
async def registrar(request: Request, call_next):
    inicio = time.time()
    resposta = await call_next(request)

    ms = (time.time() - inicio) * 1000

    print(
        f"[gateway] {request.method} {request.url.path} "
        f"-> {resposta.status_code} ({ms:.1f}ms)"
    )

    return resposta


@app.get("/saude")
def saude():
    return {"status": "ok"}


@app.post("/predict", status_code=202, dependencies=[Depends(limitar_requisicoes)],)
def predict(entrada: Entrada):
    try:
        r = requests.post(
            f"{URL_INFERENCIA}/predict",
            json=entrada.model_dump(),
            timeout=10,
        )

        r.raise_for_status()
        return r.json()

    except requests.RequestException as e:
        raise HTTPException(
            status_code=503,
            detail=f"servico de inferencia indisponivel: {e}",
        )

@app.get("/resultado/{tarefa_id}", dependencies=[Depends(exigir_jwt)])
def consultar_resultado(tarefa_id: str):
    """Consulta o resultado da tarefa pela API de inferencia."""
    try:
        resposta = requests.get(
            f"{URL_INFERENCIA}/resultado/{tarefa_id}",
            timeout=10,
        )
    except requests.RequestException:
        raise HTTPException(
            status_code=503,
            detail="Servico de inferencia indisponivel.",
        ) from None

    if resposta.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="Tarefa nao encontrada.",
        )

    try:
        resposta.raise_for_status()
        return resposta.json()
    except requests.RequestException:
        raise HTTPException(
            status_code=503,
            detail="Servico de inferencia indisponivel.",
        ) from None
