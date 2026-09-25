# mentor-AI

PWA que transforma a rotina real do estudante de medicina em um checklist diário
de estudos para a residência, com replanejamento automático.

A especificação do produto é a fonte da verdade:
[Mentoria autodidata para residência — v0.1](https://claude.ai/code/artifact/9856f5d0-f2b6-4410-8507-ed6fc7e96f9f)

## Estado atual — fase 5

O produto está inteiro para o piloto: o aluno entra por link mágico, responde o
questionário, sobe a rotina, recebe o plano até a prova, marca a lista do dia
(inclusive offline) e administra a própria assinatura — com o botão de pausar
ao lado do de cancelar. O painel em `/admin` mostra os números do piloto.

Não existe rota com id de aluno na URL: o aluno vem sempre da sessão. Quem pede
uma tarefa ou um documento de outra pessoa recebe 404.

```
apps/web/                 Angular + @angular/pwa
services/api/             FastAPI, jobs e o motor
  app/engine/             motor puro: sem banco, sem rede, sem relógio
db/migrations/            Alembic
  app/extraction/         LLM lendo a rotina, com a saída validada por schema
  app/documents/          upload, confirmação da semana e expurgo de retenção
  app/auth/               link mágico e sessões (só hash no banco)
  app/billing/            assinatura, pausa e webhook, atrás de uma porta
  app/metrics/            os números do piloto, tirados do histórico
db/catalog/               base canônica de temas, versionada em YAML
.claude/agents/           teste, validação, code review e segurança
```

A base canônica traz as sete áreas da matriz de referência do Inep — a mesma do
ENAMED, cuja nota o ENARE usa no acesso direto. Editar `db/catalog/base-canonica.yaml`
e rodar `python -m app.catalog` atualiza o banco sem duplicar nada.

## Subir tudo

```bash
cp .env.example .env
docker compose up --build
```

- PWA: http://localhost:4200
- API: http://localhost:8000/health e http://localhost:8000/docs

O serviço da API aplica as migrations e roda o seed antes de subir.

## Rodar sem Docker

API:

```bash
cd services/api
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://mentor:mentor@localhost:5432/mentor
alembic -c ../../db/alembic.ini upgrade head
python -m app.catalog
python -m app.seed
uvicorn app.main:app --reload
```

Os dois jobs diários:

```bash
python -m app.jobs.nightly     # replaneja de amanhã em diante
python -m app.jobs.notify      # lista do dia, aviso de estouro, recomeço
python -m app.jobs.retention   # apaga os originais que passaram do prazo
```

## Notificações

```bash
python -m app.tools.vapid   # gera o par de chaves e imprime as duas linhas do .env
```

Sem `VAPID_PRIVATE_KEY`, a API registra a intenção e não envia nada — o
desenvolvimento roda sem depender de serviço externo. No iPhone, o push só
funciona com o app instalado na tela de início; a tela `/avisos` explica o
caminho e cai para e-mail quando não há assinatura viva.

## Como testar do zero

```bash
cp .env.example .env
docker compose up -d --build
```

O aluno de exemplo já vem semeado, com plano até a prova. Para entrar como ele:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/auth/magic-link ^
  -H "content-type: application/json" ^
  -d "{\"email\": \"aluno.exemplo@mentor-ai.app\"}"

docker compose logs api --tail 20
```

Sem SMTP configurado, o link aparece no log da API. Abra-o no navegador: ele
entra e leva direto para a lista de hoje.

Para testar o cadastro de um aluno novo, peça o link para um e-mail qualquer
(`voce@exemplo.com`), pegue no log e siga o fluxo: questionário, aviso de
privacidade, upload da rotina, conferência da semana.

Sem `ANTHROPIC_API_KEY`, a extração usa o dublê e devolve rotina vazia — dá para
conferir a tela, não a leitura do arquivo. Com a chave no `.env` e um `docker
compose up -d` depois, o upload passa a ler o arquivo de verdade.

Para o painel do piloto, ponha `ADMIN_TOKEN` no `.env`, suba de novo e abra
http://localhost:4200/admin.

## Entrar, assinar e acompanhar o piloto

A entrada é por link mágico: o aluno digita o e-mail e recebe um link de 20
minutos, de uso único. No banco vivem só os hashes — nem do token de login, nem
do de sessão dá para voltar ao valor original.

A cobrança fica atrás de uma porta (`app/billing`). Sem provedor real
configurado, um gateway de mentira roda checkout, pausa, cancelamento e webhook
de ponta a ponta. Nenhum dado de cartão passa pela aplicação: guardamos só a
referência que o provedor devolve. O webhook confere a assinatura e é
idempotente — evento repetido não repete efeito.

O painel do piloto responde em `/admin`, protegido por `ADMIN_TOKEN`:

```bash
curl.exe -H "x-admin-token: SEU_TOKEN" http://localhost:8000/api/v1/admin/metrics
```

## Arquivos do aluno e privacidade

O aluno aceita o aviso antes do primeiro upload — sem consentimento registrado,
nenhum arquivo entra. O original vive no object store até a confirmação da
semana mais sete dias; depois o expurgo apaga o arquivo e mantém só o JSON
extraído. O aluno pode apagar qualquer documento antes disso.

Na extração, o conteúdo do arquivo é tratado como dado, nunca como instrução, e
a resposta do modelo passa por JSON Schema antes de tocar o banco. Sem
`ANTHROPIC_API_KEY`, a API usa um dublê e não chama serviço externo nenhum.

O aluno baixa tudo o que guardamos dele em `/conta` e pode apagar a conta por
ali — o que leva junto plano, progresso e arquivos.

PWA:

```bash
cd apps/web
npm install
npm start
```

## Qualidade

```bash
cd services/api
ruff check . && ruff format --check .
python -m mypy app
python -m pytest --cov=app/engine --cov-fail-under=90

cd ../../apps/web
npm run test:ci
npm run build
```

O mesmo conjunto roda no CI a cada PR, mais a aplicação das migrations num
Postgres limpo. Nada entra na `main` com CI vermelho.

## Agentes

`.claude/agents/` traz os quatro revisores do projeto. Nenhum faz commit, merge
ou deploy, e nenhum edita a especificação. Ver `CLAUDE.md` para as regras que
eles cobram.
