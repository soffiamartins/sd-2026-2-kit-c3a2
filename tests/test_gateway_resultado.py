
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from requests.exceptions import ConnectionError as RequestsConnectionError

from gateway.app import app


AMBIENTE_TESTE = {
    "JWT_SEGREDO": "segredo-de-testes-com-mais-de-trinta-e-dois-caracteres",
    "JWT_USUARIO": "aluno",
    "JWT_SENHA": "senha-de-teste",
}


class TesteConsultaResultado(unittest.TestCase):

    def setUp(self):
        ambiente = patch.dict("os.environ", AMBIENTE_TESTE)
        ambiente.start()
        self.addCleanup(ambiente.stop)

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

    def test_consulta_sem_token_retorna_401(self):
        with patch("gateway.app.requests.get") as requisicao:
            resposta = self.cliente.get("/resultado/teste-123")

        self.assertEqual(resposta.status_code, 401)
        requisicao.assert_not_called()

    def test_consulta_com_token_retorna_resultado(self):
        resultado = {
            "status": "pronto",
            "sentimento": "positivo",
        }

        with patch("gateway.app.requests.get") as requisicao:
            requisicao.return_value.status_code = 200
            requisicao.return_value.json.return_value = resultado

            resposta = self.cliente.get(
                "/resultado/teste-123",
                headers=self.headers,
            )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), resultado)
        requisicao.assert_called_once()

    def test_tarefa_inexistente_retorna_404(self):
        with patch("gateway.app.requests.get") as requisicao:
            requisicao.return_value.status_code = 404

            resposta = self.cliente.get(
                "/resultado/id-inexistente",
                headers=self.headers,
            )

        self.assertEqual(resposta.status_code, 404)

    def test_inferencia_indisponivel_retorna_503(self):
        with patch("gateway.app.requests.get") as requisicao:
            requisicao.side_effect = RequestsConnectionError(
                "Falha de conexao"
            )

            resposta = self.cliente.get(
                "/resultado/teste-123",
                headers=self.headers,
            )

        self.assertEqual(resposta.status_code, 503)


if __name__ == "__main__":
    unittest.main()
