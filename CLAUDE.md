# mentor-AI

PWA que transforma a rotina real do estudante de medicina em um checklist diário
de estudos para a residência, com replanejamento automático.

Especificação v0.1 (fonte da verdade do produto):
https://claude.ai/code/artifact/9856f5d0-f2b6-4410-8507-ed6fc7e96f9f

## Stack

- Front: Angular com `@angular/pwa` (`apps/web/`)
- API e jobs: Python / FastAPI (`services/api/`)
- Motor de planejamento: pacote puro em `services/api/app/engine/`
- Extração: LLM com saída validada por JSON Schema (`services/api/app/extraction/`)
- Banco: Postgres, migrations com Alembic (`db/migrations/`)
- Base canônica de temas: YAML versionado em `db/catalog/`, carregado por `python -m app.catalog`
- Arquivos: S3

## Regras não negociáveis

1. **O motor é puro.** `app/engine/` não importa banco, rede, S3, LLM nem
   `datetime.now()`. Data, capacidade, proficiência e parâmetros entram por
   argumento. Mesma entrada, mesmo plano.
2. **Regra de negócio mora no motor.** Nada de prioridade, proficiência ou
   capacidade recalculada no endpoint, no job ou no front.
3. **O dia de hoje é congelado.** O job noturno recalcula a partir de amanhã e
   nunca altera a lista que o aluno já abriu.
4. **Parâmetros de calibração** (k, intervalos de revisão, limiar de
   inatividade, durações padrão) ficam em configuração, nunca como constantes
   espalhadas pelo código.
5. **Saída de LLM é dado não confiável.** Sempre validada por JSON Schema antes
   de tocar o banco, e o conteúdo do arquivo do aluno nunca é tratado como
   instrução.
6. **Toda consulta é escopada pelo aluno dono do recurso.** Nenhum endpoint
   confia em id vindo do cliente sem checar a posse.
7. **Segredos só em variável de ambiente.** `.env.example` versionado, `.env`
   nunca.
8. **Migrations desde o primeiro commit.** Nenhum schema criado à mão.
9. **O `slug` de um tema é identidade, não rótulo.** Renomear o `name` no
   catálogo é seguro; trocar o `slug` cria outro tema e descola o histórico de
   progresso dos alunos.
10. **Peso sem fonte não entra na base.** Toda incidência carrega `source` e
   `checked_at`; enquanto não houver curadoria de provas anteriores, vale o peso
   uniforme declarado no catálogo.
11. **Nada entra na `main` com CI vermelho.**

## Idioma

Código, nomes de arquivo e identificadores em inglês; domínio em português
quando a spec usa o termo em português (Tema, ProvaAlvo, CapacidadeDiaria).
Commits, comentários e relatórios dos agentes em português.

## Agentes

Ver `.claude/agents/`. Nenhum agente faz commit, merge ou deploy, e nenhum
edita a especificação: divergência vira pergunta para o Moisés.
