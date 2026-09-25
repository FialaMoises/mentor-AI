# mentor-AI

PWA que transforma a rotina real do estudante de medicina em um checklist diário
de estudos para a residência, com replanejamento automático.

A especificação do produto é a fonte da verdade:
[Mentoria autodidata para residência — v0.1](https://claude.ai/code/artifact/9856f5d0-f2b6-4410-8507-ed6fc7e96f9f)

## Estado atual — fase 1

Fatia vertical funcionando ponta a ponta: o seed planeja o dia de um aluno de
exemplo com o motor, a API devolve a lista, e a PWA mostra o checklist e envia o
progresso de volta. A base canônica de temas já está carregada e consultável.

```
apps/web/                 Angular + @angular/pwa
services/api/             FastAPI, jobs e o motor
  app/engine/             motor puro: sem banco, sem rede, sem relógio
db/migrations/            Alembic
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
