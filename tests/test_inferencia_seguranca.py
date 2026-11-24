import importlib.util
import sys
import unittest

from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient


CHAVE_TESTE = "chave-interna-ficticia-exclusiva-para-testes"


class TesteSegurancaInferencia(unittest.TestCase):

    def setUp(self):
        ambiente = patch.dict(
            "os.environ",
            {"CHAVE_INTERNA": CHAVE_TESTE},
        )
        ambiente.start()
        self.addCleanup(ambiente.stop)

        # Simula Redis e modelo de IA
        self.fila = Mock()
        self.modelo = Mock()

        pacote = ModuleType("app")
        pacote.__path__ = []
        pacote.fila = self.fila

        modulo_modelo = ModuleType("app.modelo")
        modulo_modelo.carregar_modelo = Mock(
            return_value=self.modelo
        )

        caminho = (
            Path(__file__).resolve().parents[1]
            / "inferencia"
            / "app"
            / "api_rest.py"
        )

        spec = importlib.util.spec_from_file_location(
            "inferencia_api_teste",
            caminho,
        )

        modulo = importlib.util.module_from_spec(spec)

        with patch.dict(
            sys.modules,
            {
                "app": pacote,
                "app.fila": self.fila,
                "app.modelo": modulo_modelo,
            },
        ):
            spec.loader.exec_module(modulo)

        modulo.modelo = self.modelo

        self.cliente = TestClient(modulo.app)
        self.addCleanup(self.cliente.close)

        self.headers = {
            "X-Chave-Interna": CHAVE_TESTE
        }

    def verificar_bloqueio(self, headers):
        rotas = [
            ("POST", "/predict"),
            ("POST", "/predict-sync"),
            ("GET", "/resultado/teste-123"),
        ]

        for metodo, rota in rotas:
            with self.subTest(rota=rota):
                if metodo == "POST":
                    resposta = self.cliente.post(
                        rota,
                        json={"texto": "Texto de teste"},
                        headers=headers,
                    )
                else:
                    resposta = self.cliente.get(
                        rota,
                        headers=headers,
                    )

                self.assertEqual(resposta.status_code, 403)

        self.fila.enfileirar.assert_not_called()
        self.fila.buscar_resultado.assert_not_called()
        self.modelo.prever.assert_not_called()

    def test_sem_chave_bloqueia_rotas(self):
        self.verificar_bloqueio({})

    def test_chave_incorreta_bloqueia_rotas(self):
        self.verificar_bloqueio({
            "X-Chave-Interna": "chave-incorreta"
        })

    def test_chave_correta_permite_previsao(self):
        self.fila.enfileirar.return_value = "teste-123"

        resposta = self.cliente.post(
            "/predict",
            json={"texto": "Adorei o produto"},
            headers=self.headers,
        )

        self.assertEqual(resposta.status_code, 202)
        self.assertEqual(
            resposta.json(),
            {"id": "teste-123"},
        )
        self.fila.enfileirar.assert_called_once()

    def test_chave_correta_permite_consulta(self):
        self.fila.buscar_resultado.return_value = {
            "status": "pronto",
            "sentimento": "positivo",
        }

        resposta = self.cliente.get(
            "/resultado/teste-123",
            headers=self.headers,
        )

        self.assertEqual(resposta.status_code, 200)
        self.fila.buscar_resultado.assert_called_once_with(
            "teste-123"
        )

    def test_chave_correta_permite_previsao_sync(self):
        self.modelo.prever.return_value = {
            "sentimento": "positivo"
        }

        resposta = self.cliente.post(
            "/predict-sync",
            json={"texto": "Adorei o produto"},
            headers=self.headers,
        )

        self.assertEqual(resposta.status_code, 200)
        self.modelo.prever.assert_called_once()

    def test_sem_configuracao_retorna_503(self):
        with patch.dict(
            "os.environ",
            {"CHAVE_INTERNA": ""},
        ):
            resposta = self.cliente.post(
                "/predict",
                json={"texto": "Texto de teste"},
                headers=self.headers,
            )

        self.assertEqual(resposta.status_code, 503)
        self.fila.enfileirar.assert_not_called()

    def test_saude_continua_publica(self):
        resposta = self.cliente.get("/saude")

        self.assertEqual(resposta.status_code, 200)


if __name__ == "__main__":
    unittest.main()