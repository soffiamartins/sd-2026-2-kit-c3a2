import time
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from requests.exceptions import ConnectionError

from gateway.app import app, CircuitBreaker


AMBIENTE_TESTE = {
    "JWT_SEGREDO": "segredo-de-testes-com-mais-de-trinta-e-dois-caracteres",
    "JWT_USUARIO": "aluno",
    "JWT_SENHA": "senha-de-teste",
    "CHAVE_INTERNA": "chave-interna-ficticia-exclusiva-para-testes",
}


class TesteResiliencia(unittest.TestCase):

    def setUp(self):
        ambiente = patch.dict("os.environ", AMBIENTE_TESTE)
        ambiente.start()
        self.addCleanup(ambiente.stop)

        # Isola o Circuit Breaker de cada teste
        self.circuito = CircuitBreaker()
        circuito = patch("gateway.app.circuit_breaker", self.circuito)
        circuito.start()
        self.addCleanup(circuito.stop)

        # Simula o tempo sem precisar esperar 30 segundos
        tempo = patch("gateway.app.time", wraps=time)
        self.relogio = tempo.start()
        self.addCleanup(tempo.stop)
        self.relogio.sleep.return_value = None
        self.relogio.monotonic.return_value = 100

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

        self.headers = {
            "Authorization": f"Bearer {login.json()['access_token']}"
        }

    def consultar(self):
        return self.cliente.get(
            "/resultado/teste-123",
            headers=self.headers,
        )

    def abrir_circuito(self, requisicao):
        requisicao.side_effect = ConnectionError("Falha simulada")

        for _ in range(3):
            resposta = self.consultar()
            self.assertEqual(resposta.status_code, 503)

        self.assertEqual(self.circuito.estado, "ABERTO")

    def test_retry_recupera_falha_temporaria(self):
        sucesso = Mock(status_code=200)
        sucesso.json.return_value = {"status": "pronto"}

        with patch("gateway.app.requests.get") as requisicao:
            requisicao.side_effect = [
                ConnectionError("Falha temporaria"),
                sucesso,
            ]

            resposta = self.consultar()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(requisicao.call_count, 2)
        self.assertEqual(self.circuito.estado, "FECHADO")

    def test_retry_limita_tentativas(self):
        with patch("gateway.app.requests.get") as requisicao:
            requisicao.side_effect = ConnectionError("Falha simulada")

            resposta = self.consultar()

        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(requisicao.call_count, 3)

    def test_circuit_breaker_bloqueia_chamadas(self):
        with patch("gateway.app.requests.get") as requisicao:
            self.abrir_circuito(requisicao)

            self.assertEqual(requisicao.call_count, 9)

            resposta = self.consultar()

            self.assertEqual(resposta.status_code, 503)
            self.assertEqual(requisicao.call_count, 9)

    def test_circuit_breaker_recupera_servico(self):
        with patch("gateway.app.requests.get") as requisicao:
            self.abrir_circuito(requisicao)

            # Simula a passagem de 31 segundos
            self.relogio.monotonic.return_value = 131

            requisicao.side_effect = None
            requisicao.return_value.status_code = 200
            requisicao.return_value.json.return_value = {
                "status": "pronto"
            }

            resposta = self.consultar()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self.circuito.estado, "FECHADO")
        self.assertEqual(self.circuito.falhas, 0)

    def test_circuit_breaker_reabre_se_falhar(self):
        with patch("gateway.app.requests.get") as requisicao:
            self.abrir_circuito(requisicao)

            self.relogio.monotonic.return_value = 131

            resposta = self.consultar()

        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(self.circuito.estado, "ABERTO")


if __name__ == "__main__":
    unittest.main()