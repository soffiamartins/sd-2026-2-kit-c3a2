
import json
import unittest
from unittest.mock import patch

from worker.app import fila


class TestFilaWorker(unittest.TestCase):

    def test_reenfileirar_preserva_tentativas(self):
        tarefa = {
            "id": "teste-123",
            "texto": "produto excelente",
            "tentativas": 1,
        }

        with patch.object(fila, "cliente") as obter_cliente:
            fila.enfileirar_tarefa(tarefa)

        obter_cliente.return_value.rpush.assert_called_once_with(
            "tarefas",
            json.dumps(tarefa),
        )

    def test_dead_letter_atualiza_status(self):
        dados = {
            "tarefa": {
                "id": "teste-123",
                "texto": "produto excelente",
                "tentativas": 3,
            },
            "erro": "falha simulada",
            "tentativas": 3,
        }

        with patch.object(fila, "cliente") as obter_cliente:
            fila.guardar_dead_letter("teste-123", dados)

        obter_cliente.return_value.rpush.assert_called_once_with(
            "tarefas:dead-letter",
            json.dumps({"id": "teste-123", **dados}),
        )

        obter_cliente.return_value.set.assert_called_once_with(
            "resultado:teste-123",
            json.dumps({"status": "erro", "tentativas": 3}),
        )


if __name__ == "__main__":
    unittest.main()
