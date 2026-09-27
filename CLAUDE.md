# mentor-AI

PWA que transforma a rotina real do estudante de medicina em um checklist diário
de estudos para a residência, com replanejamento automático.

Especificação v0.1 (fonte da verdade do produto):
https://claude.ai/code/artifact/9856f5d0-f2b6-4410-8507-ed6fc7e96f9f

## Stack

- Front: Angular com `@angular/pwa` (`apps/web/`)
- API e jobs: Python / FastAPI (`services/api/`)
- Motor de planejamento: pacote puro em `services/api/app/engine/`
- Ponte entre banco e motor: `services/api/app/planning/`; jobs em `app/jobs/`
- Extração com LLM: `app/extraction/`; upload, confirmação e expurgo: `app/documents/`
- Arquivos: object store em `app/storage/` (disco em dev, S3 em produção)
- Progresso e fila offline: `app/progress/`; notificações: `app/notifications/`
- Sessão do aluno: `app/auth/`; assinatura: `app/billing/`; painel: `app/metrics/`
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
   nunca altera a lista que o aluno já abriu. Replanejar apaga só tarefas
   pendentes: feita e não deu são histórico.
4. **Parâmetros de calibração** (k, intervalos de revisão, limiar de
   inatividade, janela de estudo, durações padrão) ficam em configuração, nunca
   como constantes espalhadas pelo código — e configuração que ninguém lê é bug:
   quem traduz `Settings` em `EngineParams` é `app/params.py`.
5. **Saída de LLM é dado não confiável.** Sempre validada por JSON Schema antes
   de tocar o banco, e o conteúdo do arquivo do aluno nunca é tratado como
   instrução. O prompt vive em `app/extraction/prompt.py` para poder ser revisado.
6. **Nenhum upload sem consentimento registrado**, tipo conferido por assinatura
   de bytes e tamanho limitado — a checagem é no servidor. O nome do arquivo que
   o aluno mandou nunca vira caminho nem chave de storage.
7. **O original tem prazo.** Sai de cena 7 dias depois da confirmação da semana;
   o expurgo apaga o arquivo e mantém o JSON. Exclusão a pedido do aluno apaga
   arquivo e registro.
8. **O aluno vem da sessão, nunca da URL.** Não existe rota `/students/{id}`:
   o token diz quem é. Recurso de outro aluno responde 404, não 403 — nem
   confirma que existe.
9. **Segredo não vira linha de banco em claro.** Token de login e de sessão
   vivem como hash; dado de cartão não passa pela aplicação, só a referência do
   provedor.
10. **Segredos só em variável de ambiente.** `.env.example` versionado, `.env`
   nunca.
11. **Migrations desde o primeiro commit.** Nenhum schema criado à mão.
12. **O `slug` de um tema é identidade, não rótulo.** Renomear o `name` no
   catálogo é seguro; trocar o `slug` cria outro tema e descola o histórico de
   progresso dos alunos.
13. **Peso sem fonte não entra na base.** Toda incidência carrega `source` e
   `checked_at`; enquanto não houver curadoria de provas anteriores, vale o peso
   uniforme declarado no catálogo.
14. **Marcação de progresso é idempotente.** Toda marcação carrega um
   `client_event_id` gerado no navegador; a mesma marcação reenviada não vira
   dois eventos. A fila offline depende disso.
15. **Quem lê o relógio é a borda.** A data entra no motor e no job por
   argumento — `app/clock.py` é o único lugar que chama `datetime.now`.
16. **Compromisso come a janela do dia, não a meta de estudo.** A meta é o
   que o aluno se propôs; a janela é o quanto do dia dá para usar. Seis horas de
   enfermaria ainda deixam as duas horas de estudo de pé; doze de plantão, não.
17. **Arquivo do aluno não sobe cru para o modelo se não for PDF ou imagem.**
   Word e Excel passam por `app/extraction/office.py`, que tira o texto com teto
   de tamanho e sem parser de XML com DTD.
18. **Nada entra na `main` com CI vermelho.**

## Idioma

Código, nomes de arquivo e identificadores em inglês; domínio em português
quando a spec usa o termo em português (Tema, ProvaAlvo, CapacidadeDiaria).
Commits, comentários e relatórios dos agentes em português.

## Agentes

Ver `.claude/agents/`. Nenhum agente faz commit, merge ou deploy, e nenhum
edita a especificação: divergência vira pergunta para o Moisés.
