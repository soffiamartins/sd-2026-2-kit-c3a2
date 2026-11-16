
"""API Gateway: autenticacao JWT e roteamento para a inferencia."""
from datetime import datetime, timedelta, timezone
import os
import secrets
import time

import jwt
import requests
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

app = FastAPI(title="Gateway - C3.A2")
URL_INFERENCIA = os.getenv("URL_INFERENCIA", "http://localhost:8001")
AUTENTICACAO_BEARER = HTTPBearer(auto_error=False)
ALGORITMO_JWT = "HS256"
MINUTOS_EXPIRACAO = 60


class Entrada(BaseModel):
    texto: str


class CredenciaisLogin(BaseModel):
    usuario: str
    senha: str


def configuracao_jwt() -> tuple[str, str, str]:
    """Nao permite autenticar com credenciais padrao ou configuracao incompleta."""
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
    """Compara credenciais UTF-8 sem rejeitar caracteres acentuados."""
    return secrets.compare_digest(primeiro.encode("utf-8"), segundo.encode("utf-8"))


def exigir_jwt(
    autorizacao: HTTPAuthorizationCredentials | None = Depends(AUTENTICACAO_BEARER),
) -> None:
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


@app.post("/login")
def login(credenciais: CredenciaisLogin):
    segredo, usuario_configurado, senha_configurada = configuracao_jwt()
    usuario_correto = iguais_em_tempo_constante(credenciais.usuario, usuario_configurado)
    senha_correta = iguais_em_tempo_constante(credenciais.senha, senha_configurada)
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
    return {"access_token": token, "token_type": "bearer", "expires_in": 3600}


@app.middleware("http")
async def registrar(request: Request, call_next):
    inicio = time.time()
    resposta = await call_next(request)
    ms = (time.time() - inicio) * 1000
    print(f"[gateway] {request.method} {request.url.path} "
          f"-> {resposta.status_code} ({ms:.1f}ms)")
    return resposta


@app.get("/saude")
def saude():
    return {"status": "ok"}


@app.post("/predict", dependencies=[Depends(exigir_jwt)])
def predict(entrada: Entrada):
    # TAREFA 2: aplicar limite de requisicoes por cliente.
    try:
        r = requests.post(f"{URL_INFERENCIA}/predict",
                          json=entrada.model_dump(), timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=503,
                            detail=f"servico de inferencia indisponivel: {e}")
