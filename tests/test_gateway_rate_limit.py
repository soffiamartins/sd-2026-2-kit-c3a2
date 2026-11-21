
"""Testes do rate limiting usando Redis simulado."""

from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from gateway.app import app


AMBIENTE_TESTE = {
    "JWT_SEGREDO": "segredo-de-testes-com-mais-de-trinta-e-dois-caracteres",
    "JWT_USUARIO": "aluno",
    "JWT_SENHA": "senha-de-teste",
    "RATE_LIMIT_MAXIMO": "2",
    "RATE_LIMIT_JANELA_SEGUNDOS": "60",
}


class TesteRateLimit(TestCase):
    def setUp(self):
        self.ambiente = patch.dict("os.environ", AMBIENTE_TESTE)
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)

        self.redis_patch = patch("gateway.app.obter_redis")
        self.redis_simulado = self.redis_patch.start().return_value
        self.redis_simulado.eval.return_value = [1, 60]
        self.addCleanup(self.redis_patch.stop)

        self.cliente = TestClient(app)
        self.addCleanup(self.cliente.close)

        login = self.cliente.post(
            "/login",
            json={
                "usuario": "aluno",
                "senha": "senha-de-teste",
            },
        )

        self.assertEqual(login.status_code, 200)
        token = login.json()["access_token"]

        self.cabecalhos = {
            "Authorization": f"Bearer {token}",
        }

    def test_bloqueia_apos_exceder_limite(self):
        self.redis_simulado.eval.side_effect = [
            [1, 60],
            [2, 59],
            [3, 58],
        ]

        with patch("gateway.app.requests.post") as requisicao:
            requisicao.return_value.json.return_value = {
                "sentimento": "positivo"
            }

            respostas = [
                self.cliente.post(
                    "/predict",
                    json={"texto": "teste"},
                    headers=self.cabecalhos,
                )
                for _ in range(3)
            ]

        self.assertEqual(
            [r.status_code for r in respostas],
            [202, 202, 429],
        )

        self.assertEqual(
            respostas[2].headers["retry-after"],
            "58",
        )

        self.assertEqual(requisicao.call_count, 2)

    def test_sem_token_nao_consulta_redis(self):
        resposta = self.cliente.post(
            "/predict",
            json={"texto": "teste"},
        )

        self.assertEqual(resposta.status_code, 401)
        self.redis_simulado.eval.assert_not_called()

    def test_redis_indisponivel_retorna_503(self):
        self.redis_simulado.eval.side_effect = RedisConnectionError(
            "Redis indisponivel"
        )

        resposta = self.cliente.post(
            "/predict",
            json={"texto": "teste"},
            headers=self.cabecalhos,
        )

        self.assertEqual(resposta.status_code, 503)

    def test_configuracao_invalida_retorna_503(self):
        with patch.dict(
            "os.environ",
            {"RATE_LIMIT_MAXIMO": "0"},
        ):
            resposta = self.cliente.post(
                "/predict",
                json={"texto": "teste"},
                headers=self.cabecalhos,
            )

        self.assertEqual(resposta.status_code, 503)
        self.redis_simulado.eval.assert_not_called()
