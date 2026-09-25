# mentor-AI

PWA que transforma a rotina real do estudante de medicina em um checklist diário
de estudos para a residência, com replanejamento automático.

A especificação do produto é a fonte da verdade:
[Mentoria autodidata para residência — v0.1](https://claude.ai/code/artifact/9856f5d0-f2b6-4410-8507-ed6fc7e96f9f)

## Estado atual — fase 4

O ciclo diário fecha: o aluno abre a lista, marca feito com dois toques (o
segundo lança quantas questões acertou), e a marcação feita sem sinal fica numa
fila que sobe sozinha quando a internet volta — reenviar a fila inteira não
duplica nada. As notificações saem por Web Push, com e-mail de reserva para
quem não tem push.

Antes disso: o aluno responde o questionário, aceita o aviso de privacidade,
sobe a grade ou a escala e confere a semana que a IA leu. O motor monta o
horizonte até a prova e o job noturno recalcula de amanhã em diante sem tocar
na lista que ele já abriu.

```
apps/web/                 Angular + @angular/pwa
services/api/             FastAPI, jobs e o motor
  app/engine/             motor puro: sem banco, sem rede, sem relógio
db/migrations/            Alembic
  app/extraction/         LLM lendo a rotina, com a saída validada por schema
  app/documents/          upload, confirmação da semana e expurgo de retenção
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

## Arquivos do aluno e privacidade

O aluno aceita o aviso antes do primeiro upload — sem consentimento registrado,
nenhum arquivo entra. O original vive no object store até a confirmação da
semana mais sete dias; depois o expurgo apaga o arquivo e mantém só o JSON
extraído. O aluno pode apagar qualquer documento antes disso.

Na extração, o conteúdo do arquivo é tratado como dado, nunca como instrução, e
a resposta do modelo passa por JSON Schema antes de tocar o banco. Sem
`ANTHROPIC_API_KEY`, a API usa um dublê e não chama serviço externo nenhum.

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
