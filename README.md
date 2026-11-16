
# Kit de Partida — C3.A2: Plataforma de IA como Serviço (projeto integrador)

**Sistemas Distribuídos e Computação em Nuvem · FAESA · 2026/2**
Prof. Howard Cruz Roatti · Lançado na Aula 13 (05/11) · Entrega na Aula 17 (26/11)

---

## O que é isto

O projeto que fecha o semestre. Você pega tudo o que construiu e transforma numa
plataforma de verdade: **conteinerizada, publicada na internet, observável e protegida**.
Ao final você terá um sistema distribuído completo e público — material de portfólio
para entrevista de emprego.

> **Sobre a IA neste trabalho:** todo contato com inteligência artificial aqui é
> **chamada de biblioteca ou de API**. Você **não vai treinar modelos** nem precisar de
> matemática de aprendizado de máquina. O modelo já vem pronto e configurado.
> A sua nota vem da **engenharia distribuída**: arquitetura, comunicação, resiliência e
> execução reproduzível — a sofisticação do modelo **não pontua**.

> **Status:** trabalho em andamento. A etapa 1 (autenticacao JWT do gateway) esta
> implementada e possui testes automatizados. Os diretorios `inferencia/` e
> `worker/` ainda sao estruturas vazias do kit de partida. Por isso, o comando
> `docker compose up --build` so podera funcionar ao final das etapas 3 e 4.

---

## Como começar

```bash
# 1. Clone o kit e entre na pasta
git clone https://github.com/howardroatti/sd-2026-2-kit-c3a2.git
cd sd-2026-2-kit-c3a2

# 2. Crie e ative o ambiente virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements-test.txt
```

```bash
# 4. Copie o arquivo de ambiente
cp .env.example .env

# 5. Quando as etapas 3 e 4 estiverem prontas, suba a stack com UM comando
docker compose up --build

# 6. Teste pelo gateway (apos o inicio da stack)
curl http://localhost:8000/saude
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"usuario":"SEU_USUARIO","senha":"SUA_SENHA"}'
# Copie o campo access_token retornado pelo /login:
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer SEU_TOKEN" \
  -d '{"texto":"servico excelente"}'

# 7. Publique na nuvem seguindo deploy/INSTRUCOES.md
```

---

## Etapa 1: autenticacao JWT (concluida)

- `POST /login` recebe `{"usuario": "...", "senha": "..."}` e retorna um
  `access_token` do tipo Bearer, valido por 60 minutos.
- `POST /predict` retorna **401** sem token ou com token invalido/expirado.
- `GET /saude` continua publico para verificacao de disponibilidade.
- As credenciais de demonstracao sao configuradas por `JWT_USUARIO`, `JWT_SENHA`
  e `JWT_SEGREDO` no ambiente; nao existem valores padrao no codigo.
- Para `JWT_SEGREDO`, utilize pelo menos 32 caracteres aleatorios. Gere um valor
  com `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- Copie `.env.example` para `.env` e preencha `JWT_USUARIO`, `JWT_SENHA` e
  `JWT_SEGREDO` antes de executar o Docker Compose. Nunca versione `.env`.

**Testes isolados do gateway (sem Docker e sem servico de inferencia):**

```bash
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -v
```

Os testes verificam login correto/incorreto, protecao por token, expiracao,
assinatura, configuracao ausente e encaminhamento simulado para a inferencia.

**Exemplo manual em PowerShell (Windows):** em um terminal, dentro da raiz do
projeto, defina valores proprios e execute o gateway:

```powershell
$env:JWT_SEGREDO = (python -c "import secrets; print(secrets.token_urlsafe(48))")
$env:JWT_USUARIO = "aluno"
$env:JWT_SENHA = "senha-forte-somente-local"
python -m uvicorn gateway.app:app --port 8000
```

Em um **segundo** terminal PowerShell:

```powershell
curl.exe http://localhost:8000/saude
curl.exe -i -X POST http://localhost:8000/predict -H "Content-Type: application/json" -d '{"texto":"teste"}'
$token = (Invoke-RestMethod -Method Post -Uri http://localhost:8000/login -ContentType "application/json" -Body '{"usuario":"aluno","senha":"senha-forte-somente-local"}').access_token
```

O `POST /predict` sem token deve responder **401**. O login deve fornecer um
token; o `POST /predict` autenticado so retornara **200** quando o servico de
inferencia estiver implementado (etapas seguintes). Ate la, pode retornar 503.

---

## Estrutura do projeto

```
sd-2026-2-kit-c3a2/
├── gateway/
│   ├── app.py              # TAREFAS 1 e 2 (JWT e rate limit)
│   └── Dockerfile          # PRONTO - use de modelo
├── inferencia/             # traga o seu C1.A2 para cá
├── worker/                 # traga o seu worker para cá
├── deploy/INSTRUCOES.md    # passo a passo do free tier
├── Dockerfile.exemplo      # modelo para os demais serviços
├── docker-compose.yml      # TAREFA 4
└── TAREFAS.md              # <- comece por aqui
```

---

## O que você precisa fazer

Abra o arquivo **`TAREFAS.md`**: ele lista o núcleo obrigatório item a item, indicando
o arquivo e a aula de referência de cada um.

---

## Como você será avaliado

| Critério | Pontos |
|---|---|
| Arquitetura e decomposição em serviços | 1,5 |
| Comunicação funcionando (REST / gRPC / mensageria) | 1,5 |
| Resiliência e tratamento de falhas | 1,0 |
| Execução reproduzível (README, container, deploy) | 1,0 |
| **Sofisticação do modelo de IA** | **não pontua** |
| **Total** | **5,0** |

**Entrega:** no seu repositório do GitHub, **sem apresentação oral**. Grupos livres.

---

## Aulas de referência

- **Aula 13** — Nuvem, containers e o primeiro deploy
- **Aula 14** — Orquestração, serverless e borda
- **Aula 15** — Observabilidade e rastreamento distribuído
- **Aula 16** — Segurança, LGPD e revisão para o ENADE

---

## Dúvidas frequentes

**Preciso saber machine learning?** Não. O modelo já está pronto e você só chama uma função.

**E se eu não tiver internet no laboratório?** Tudo neste kit funciona offline. O modelo é
treinado localmente e o cliente de LLM tem modo simulado.

**Posso trocar a linguagem?** O kit é em Python porque é o ecossistema usado nas aulas.
Se quiser usar outra linguagem, converse com o professor antes.

**Posso usar IA para me ajudar a programar?** Sim. Este é um trabalho prático feito fora de
sala, e usar ferramentas de IA é realista. O que se avalia é o **sistema funcionando** e as
**decisões de arquitetura** — que você precisa saber explicar.
