import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, call

from worker.app import fila, modelo


class TesteArmazenamentoVetorial(unittest.TestCase):

    def test_gerar_vetor_tfidf(self):
        with TemporaryDirectory() as pasta:
            caminho = str(Path(pasta) / "modelo.joblib")

            with patch.object(modelo, "CAMINHO", caminho):
                classificador = modelo.carregar_modelo()
                vetor = classificador.vetorizar("adorei o produto")

        self.assertIsInstance(vetor, list)
        self.assertGreater(len(vetor), 0)
        self.assertTrue(
            all(isinstance(valor, float) for valor in vetor)
        )
        self.assertTrue(any(valor > 0 for valor in vetor))

    def test_guardar_resultado_com_vetor(self):
        resultado = {"status": "pronto"}
        vetor = [0.0, 0.5, 0.8]

        with patch.object(fila, "cliente") as cliente:
            pipe = (
                cliente.return_value.pipeline
                .return_value.__enter__.return_value
            )

            fila.guardar_resultado_com_vetor(
                "teste-123", resultado, vetor
            )

            cliente.return_value.pipeline.assert_called_once_with(
                transaction=True
            )

            self.assertEqual(
                pipe.set.call_args_list,
                [
                    call(
                        "resultado:teste-123",
                        json.dumps(resultado),
                        ex=86400,
                    ),
                    call(
                        "vetor:teste-123",
                        json.dumps(vetor),
                        ex=86400,
                    ),
                ],
            )

            pipe.execute.assert_called_once()

    def test_buscar_vetor(self):
        vetor = [0.0, 0.5, 0.8]

        with patch.object(fila, "cliente") as cliente:
            cliente.return_value.get.return_value = json.dumps(vetor)

            self.assertEqual(
                fila.buscar_vetor("teste-123"), vetor
            )

            cliente.return_value.get.assert_called_once_with(
                "vetor:teste-123"
            )

    def test_buscar_vetor_inexistente(self):
        with patch.object(fila, "cliente") as cliente:
            cliente.return_value.get.return_value = None

            self.assertIsNone(
                fila.buscar_vetor("inexistente")
            )


if __name__ == "__main__":
    unittest.main()