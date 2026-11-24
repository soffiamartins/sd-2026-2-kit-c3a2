import importlib.util
import json
import unittest

from pathlib import Path
from unittest.mock import MagicMock, patch


RAIZ = Path(__file__).resolve().parents[1]


def carregar_fila(servico):
    caminho = RAIZ / servico / "app" / "fila.py"

    spec = importlib.util.spec_from_file_location(
        f"fila_{servico}_teste",
        caminho,
    )

    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    return modulo


fila_inferencia = carregar_fila("inferencia")
fila_worker = carregar_fila("worker")


class TesteRetencaoDados(unittest.TestCase):

    def test_tarefa_inferencia_tem_ttl(self):
        redis_mock = MagicMock()
        pipe = redis_mock.pipeline.return_value.__enter__.return_value

        with patch.object(
            fila_inferencia,
            "cliente",
            return_value=redis_mock,
        ):
            tarefa_id = fila_inferencia.enfileirar(
                "Texto de teste"
            )

        pipe.set.assert_called_once_with(
            "resultado:" + tarefa_id,
            json.dumps({"status": "na_fila"}),
            ex=86400,
        )

    def test_resultado_inferencia_tem_ttl(self):
        redis_mock = MagicMock()
        resultado = {"status": "pronto"}

        with patch.object(
            fila_inferencia,
            "cliente",
            return_value=redis_mock,
        ):
            fila_inferencia.guardar_resultado(
                "teste-123",
                resultado,
            )

        redis_mock.set.assert_called_once_with(
            "resultado:teste-123",
            json.dumps(resultado),
            ex=86400,
        )

    def test_tarefa_worker_tem_ttl(self):
        redis_mock = MagicMock()

        with patch.object(
            fila_worker,
            "cliente",
            return_value=redis_mock,
        ):
            tarefa_id = fila_worker.enfileirar(
                "Texto de teste"
            )

        redis_mock.set.assert_called_once_with(
            "resultado:" + tarefa_id,
            json.dumps({"status": "na_fila"}),
            ex=86400,
        )

    def test_resultado_worker_tem_ttl(self):
        redis_mock = MagicMock()
        resultado = {"status": "pronto"}

        with patch.object(
            fila_worker,
            "cliente",
            return_value=redis_mock,
        ):
            fila_worker.guardar_resultado(
                "teste-123",
                resultado,
            )

        redis_mock.set.assert_called_once_with(
            "resultado:teste-123",
            json.dumps(resultado),
            ex=86400,
        )

    def test_dead_letter_minimiza_dados(self):
        redis_mock = MagicMock()
        pipe = redis_mock.pipeline.return_value.__enter__.return_value

        dados = {
            "texto": "Informacao privada de teste",
            "erro": "Detalhes internos do erro",
            "tentativas": 3,
        }

        with patch.object(
            fila_worker,
            "cliente",
            return_value=redis_mock,
        ):
            fila_worker.guardar_dead_letter(
                "teste-123",
                dados,
            )

        pipe.rpush.assert_called_once_with(
            "tarefas:dead-letter",
            json.dumps({
                "id": "teste-123",
                "tentativas": 3,
                "status": "erro",
            }),
        )

        pipe.ltrim.assert_called_once_with(
            "tarefas:dead-letter",
            -100,
            -1,
        )

        pipe.execute.assert_called_once()

        redis_mock.set.assert_called_once_with(
            "resultado:teste-123",
            json.dumps({
                "status": "erro",
                "tentativas": 3,
            }),
            ex=86400,
        )

if __name__ == "__main__":
    unittest.main()