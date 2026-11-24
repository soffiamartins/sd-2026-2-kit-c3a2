
import unittest
from uuid import UUID
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


class TesteTracing(unittest.TestCase):

    def setUp(self):
        ambiente = patch.dict("os.environ", AMBIENTE_TESTE)
        ambiente.start()
        self.addCleanup(ambiente.stop)

        circuito = patch(
            "gateway.app.circuit_breaker",
            CircuitBreaker(),
        )
        circuito.start()
        self.addCleanup(circuito.stop)

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

    def test_gateway_gera_trace_id_valido(self):
        resposta = self.cliente.get("/saude")

        self.assertEqual(resposta.status_code, 200)

        trace_id = resposta.headers["X-Trace-ID"]

        self.assertEqual(UUID(trace_id).hex, trace_id)

    def test_requisicoes_possuem_trace_ids_distintos(self):
        primeira = self.cliente.get("/saude")
        segunda = self.cliente.get("/saude")

        self.assertNotEqual(
            primeira.headers["X-Trace-ID"],
            segunda.headers["X-Trace-ID"],
        )

    def test_predict_propaga_trace_id(self):
        with patch("gateway.app.obter_redis") as redis_mock:
            redis_mock.return_value.eval.return_value = [1, 60]

            with patch("gateway.app.requests.post") as requisicao:
                requisicao.return_value.status_code = 202
                requisicao.return_value.json.return_value = {
                    "id": "teste-123"
                }

                resposta = self.cliente.post(
                    "/predict",
                    json={"texto": "Adorei o produto"},
                    headers=self.headers,
                )

        self.assertEqual(resposta.status_code, 202)

        trace_enviado = requisicao.call_args.kwargs[
            "headers"
        ]["X-Trace-ID"]

        self.assertEqual(
            resposta.headers["X-Trace-ID"],
            trace_enviado,
        )

    def test_retry_preserva_trace_id(self):
        sucesso = Mock(status_code=200)
        sucesso.json.return_value = {"status": "pronto"}

        with patch("gateway.app.requests.get") as requisicao:
            requisicao.side_effect = [
                ConnectionError("Falha temporaria"),
                sucesso,
            ]

            resposta = self.cliente.get(
                "/resultado/teste-123",
                headers=self.headers,
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(requisicao.call_count, 2)

        trace_id = resposta.headers["X-Trace-ID"]

        for chamada in requisicao.call_args_list:
            self.assertEqual(
                chamada.kwargs["headers"]["X-Trace-ID"],
                trace_id,
            )


if __name__ == "__main__":
    unittest.main()
