
# Relatório de Trade-offs

## C3.A2 — Plataforma de IA como Serviço

### 1. Teorema CAP

A arquitetura utiliza uma instância centralizada de Redis
para gerenciar tarefas e resultados.

Em situações de falha de comunicação, o Gateway utiliza
timeout, retry e circuit breaker, podendo retornar HTTP 503
quando o serviço de inferência está indisponível.

Essa abordagem sacrifica disponibilidade para evitar
confirmações indevidas de operações.

Como não existe replicação do Redis, não é possível
classificar formalmente toda a arquitetura como CP ou AP.

### 2. Custos

A plataforma utiliza os serviços gratuitos do Render.

| Componente | Custo mensal previsto |
|---|---:|
| API Gateway | US$ 0,00 |
| Inferência | US$ 0,00 |
| Worker | US$ 0,00 |
| Redis/Valkey | US$ 0,00 |
| Total | US$ 0,00 |

O Worker compartilha a infraestrutura do serviço de
inferência na nuvem, reduzindo custos, mas limitando
a escalabilidade independente.

O Redis gratuito possui 25 MB de memória, limite de
50 conexões e persistência desativada.

Os custos apresentados consideram os limites dos planos
gratuitos selecionados.

### 3. Latência

O processamento assíncrono permite que o Gateway
responda à solicitação sem aguardar a conclusão da
inferência.

Durante uma execução real no Render, foram registrados
os seguintes tempos:

| Operação | Tempo registrado |
|---|---:|
| POST /predict | 99,3 ms |
| GET /resultado | 61,6 ms |
| Processamento do Worker | 1,7 ms |

Esses valores representam uma execução individual,
não uma média de desempenho ou uma medição completa
de ponta a ponta.

A inicialização a frio dos serviços gratuitos e as
tentativas de reconexão podem aumentar a latência.

### 4. Principais trade-offs

| Decisão | Benefício | Limitação |
|---|---|---|
| Processamento assíncrono | Resposta inicial rápida | Consulta posterior do resultado |
| Redis em memória | Baixa latência | Risco de perda de dados |
| Plano gratuito | Baixo custo | Limites de recursos e disponibilidade |
| Circuit breaker | Proteção contra falhas em cascata | Indisponibilidade temporária |
| Worker junto à inferência na nuvem | Economia de infraestrutura | Escalabilidade acoplada |
| Retenção de resultados por 24 horas | Minimização de dados | Histórico temporário |

### 5. Conclusão

A arquitetura prioriza baixo custo, simplicidade,
resiliência e reprodução do ambiente.

As decisões são adequadas ao contexto acadêmico,
considerando as limitações da infraestrutura gratuita.

Em um ambiente de produção, seria necessário avaliar
replicação, persistência, escalabilidade independente
e mecanismos adicionais de recuperação de tarefas.