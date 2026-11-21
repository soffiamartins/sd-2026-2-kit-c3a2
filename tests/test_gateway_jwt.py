from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from gateway.app import app


SEGREDO_TESTE = "segredo-apenas-para-testes-com-mais-de-32-caracteres"
AMBIENTE_TESTE = {
    "JWT_SEGREDO": SEGREDO_TESTE,
    "JWT_USUARIO": "aluno",
    "JWT_SENHA": "senha-de-teste",
}


class TesteAutenticacaoJWT(TestCase):
    
    def setUp(self):
        self.ambiente = patch.dict("os.environ", AMBIENTE_TESTE)
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)

        # Simula o Redis nos testes da Etapa 1.
        self.redis_patch = patch("gateway.app.obter_redis")
        self.redis_simulado = self.redis_patch.start().return_value
        self.redis_simulado.eval.return_value = [1, 60]
        self.addCleanup(self.redis_patch.stop)

        self.cliente = TestClient(app)
        self.addCleanup(self.cliente.close)

    def autenticar(self):
        resposta = self.cliente.post(
            "/login", json={"usuario": "aluno", "senha": "senha-de-teste"}
        )
        self.assertEqual(resposta.status_code, 200)
        return resposta.json()["access_token"]

    def test_saude_continua_publica(self):
        resposta = self.cliente.get("/saude")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"status": "ok"})

    def test_login_valido_emite_token_com_expiracao(self):
        resposta = self.cliente.post(
            "/login", json={"usuario": "aluno", "senha": "senha-de-teste"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["token_type"], "bearer")
        self.assertEqual(resposta.json()["expires_in"], 3600)
        dados = jwt.decode(
            resposta.json()["access_token"], SEGREDO_TESTE, algorithms=["HS256"]
        )
        self.assertEqual(dados["sub"], "aluno")
        self.assertIn("exp", dados)

    def test_login_incorreto_retorna_401(self):
        for usuario, senha in [("aluno", "errada"), ("outro", "senha-de-teste")]:
            with self.subTest(usuario=usuario, senha=senha):
                resposta = self.cliente.post(
                    "/login", json={"usuario": usuario, "senha": senha}
                )
                self.assertEqual(resposta.status_code, 401)
                self.assertNotIn("access_token", resposta.json())

    def test_predict_sem_token_retorna_401(self):
        resposta = self.cliente.post("/predict", json={"texto": "oi"})
        self.assertEqual(resposta.status_code, 401)
        self.assertEqual(resposta.headers["www-authenticate"], "Bearer")

    def test_predict_com_token_invalido_retorna_401(self):
        for cabecalho in ["Bearer valor-invalido", "Basic abc123"]:
            with self.subTest(cabecalho=cabecalho):
                resposta = self.cliente.post(
                    "/predict",
                    json={"texto": "oi"},
                    headers={"Authorization": cabecalho},
                )
                self.assertEqual(resposta.status_code, 401)

    def test_predict_com_token_expirado_retorna_401(self):
        passado = datetime.now(timezone.utc) - timedelta(minutes=5)
        expirado = jwt.encode(
            {"sub": "aluno", "iat": passado, "exp": passado + timedelta(seconds=1)},
            SEGREDO_TESTE,
            algorithm="HS256",
        )
        resposta = self.cliente.post(
            "/predict",
            json={"texto": "oi"},
            headers={"Authorization": f"Bearer {expirado}"},
        )
        self.assertEqual(resposta.status_code, 401)

    def test_predict_com_token_assinado_por_outro_segredo_retorna_401(self):
        agora = datetime.now(timezone.utc)
        for payload, segredo in [
            ({"sub": "outro", "iat": agora, "exp": agora + timedelta(hours=1)}, SEGREDO_TESTE),
            (
                {"sub": "aluno", "iat": agora, "exp": agora + timedelta(hours=1)},
                "outro-segredo-para-testes-com-mais-de-32-caracteres",
            ),
        ]:
            with self.subTest(payload=payload, segredo=segredo):
                token = jwt.encode(payload, segredo, algorithm="HS256")
                resposta = self.cliente.post(
                    "/predict",
                    json={"texto": "oi"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                self.assertEqual(resposta.status_code, 401)

    def test_predict_com_token_valido_encaminha_para_inferencia(self):
        token = self.autenticar()
        with patch("gateway.app.requests.post") as requisicao:
            requisicao.return_value.json.return_value = {"sentimento": "positivo"}
            resposta = self.cliente.post(
                "/predict",
                json={"texto": "servico excelente"},
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(resposta.status_code, 202)
        self.assertEqual(resposta.json(), {"sentimento": "positivo"})
        self.assertEqual(requisicao.call_count, 1)
        self.assertEqual(
            requisicao.call_args.kwargs["json"], {"texto": "servico excelente"}
        )

    def test_sem_configuracao_nao_autentica(self):
        with patch.dict("os.environ", {"JWT_SEGREDO": "", "JWT_SENHA": ""}):
            resposta = self.cliente.post(
                "/login", json={"usuario": "aluno", "senha": "senha-de-teste"}
            )
            self.assertEqual(resposta.status_code, 503)