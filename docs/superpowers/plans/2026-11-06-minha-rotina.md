# Minha rotina — plano de implementação

> **Para agentes:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para executar tarefa por tarefa. Os passos usam checkbox (`- [ ]`).

**Objetivo:** tela de agenda onde o aluno vê, adiciona, edita e apaga os compromissos da semana com horário, e o plano se refaz de amanhã em diante.

**Arquitetura:** o compromisso ganha horário de início, série e marca de edição (migration 0006). O motor passa a contar sobreposição uma vez só. Um serviço novo, `app/routine/`, grava as séries por vigência, recalcula a capacidade e replaneja. Uma rota nova `/me/routine` serve a semana. No front entra o componente `/rotina`: uma grade de 7 colunas que vira um dia por vez abaixo de 768 px.

**Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic v2, pytest; Angular 20 standalone com signals, Karma/Jasmine.

**Spec:** [docs/superpowers/specs/2026-11-06-minha-rotina-design.md](../specs/2026-11-06-minha-rotina-design.md). Ler antes de começar.

**Branch:** trabalhar em `feat/minha-rotina`, nunca na `main`. Pelo CLAUDE.md, o commit fica com o Moisés. Cada tarefa termina num checkpoint com a suíte verde, e o commit só acontece quando ele autorizar.

## Restrições globais

- O motor é puro: `app/engine/` não importa banco, rede nem `datetime.now()` (regra 1). O `test_engine_purity.py` precisa continuar verde.
- Regra de capacidade só no motor (regra 2): o front exibe `free_minutes` e `light` como vierem da API.
- O dia de hoje fica congelado (regra 3): salvar a rotina recalcula a capacidade e replaneja só a partir de amanhã.
- O aluno vem da sessão (regra 8): série de outro aluno responde **404**.
- O relógio é lido só na borda (regra 15): a API usa `today_in(student.timezone)` de `app/clock.py`, e o serviço recebe `today: date`.
- Schema novo só por migration (regra 11): `db/migrations/versions/0006_rotina_editavel.py`, com `down_revision = "0005"`.
- Tipos de compromisso: `("aula", "plantao", "academia", "trabalho", "leitura", "outro")`.
- `label` vai até 160 caracteres e a duração vai de 1 a 1440 min. O teto é de 200 compromissos vigentes por aluno.
- Cobertura do `app/engine` ≥ 90%. `ruff check`, `ruff format --check`, `mypy app`, `npm run test:ci` e `npm run build` precisam passar.
- Código e identificadores em inglês; textos de interface, comentários e nomes de teste em português, seguindo o padrão do repo.

## Pontos de atenção na revisão

1. **Plantão noturno de domingo, 19h–7h:** a capacidade conta tudo no domingo. A agenda desenha o pedaço das 0h às 7h na segunda seguinte, e só quando a segunda está na mesma semana exibida. Testes: Tarefa 1 e Tarefa 6.
2. **Bloco de arquivo editado e depois documento apagado:** some tudo, inclusive os registros novos da edição. Teste na Tarefa 4.
3. **"Amanhã" no fuso do aluno:** às 22h em Fortaleza já é amanhã em UTC. A vigência nova usa a data local do aluno. Teste na Tarefa 5.
4. **Aluno sem prova principal salva a rotina:** responde 200, com `replan_summary == ""`, e a capacidade da semana vem calculada na hora. Teste na Tarefa 5.
5. **Clique duplo em "salvar":** o botão fica desabilitado enquanto a requisição está aberta, então não nasce uma série duplicada. Teste na Tarefa 6.

---

### Tarefa 1: horário no motor e sobreposição contada uma vez

**Arquivos:**
- Modificar: `services/api/app/engine/routine.py`
- Teste: `services/api/tests/test_engine_routine.py`

**Interfaces:**
- Produz: `Commitment(..., starts_at: datetime.time | None = None)`, com o novo campo por último e opcional. `busy_minutes(commitments, day) -> int` muda de regra; a assinatura continua a mesma.

- [ ] **Passo 1: escrever os testes que falham**

```python
def test_sobreposicao_com_horario_conta_uma_vez() -> None:
    aula = Commitment(kind="aula", weekday=0, duration_minutes=120, starts_at=time(17, 0))
    academia = Commitment(kind="academia", weekday=0, duration_minutes=75, starts_at=time(18, 0))
    assert busy_minutes([aula, academia], SEGUNDA) == 135  # 17h00–19h15

def test_compromisso_sem_horario_soma_como_antes() -> None:
    aula = Commitment(kind="aula", weekday=0, duration_minutes=120, starts_at=time(17, 0))
    leitura = Commitment(kind="leitura", weekday=0, duration_minutes=60)
    assert busy_minutes([aula, leitura], SEGUNDA) == 180

def test_intervalos_separados_somam() -> None:
    manha = Commitment(kind="aula", weekday=0, duration_minutes=60, starts_at=time(7, 0))
    noite = Commitment(kind="academia", weekday=0, duration_minutes=60, starts_at=time(18, 0))
    assert busy_minutes([manha, noite], SEGUNDA) == 120

def test_plantao_que_atravessa_a_meia_noite_conta_no_dia_em_que_comeca() -> None:
    noturno = Commitment(kind="plantao", weekday=6, duration_minutes=720, starts_at=time(19, 0))
    dias = capacities_from_commitments(semana() + [SEGUNDA + timedelta(days=7)], [noturno], 120)
    assert dias[6].free_minutes == 0          # domingo: 600 - 720 < 0
    assert dias[7].free_minutes == 120 and dias[7].light  # segunda seguinte: livre, mas leve
```

- [ ] **Passo 2: rodar e ver falhar**

Rodar: `cd services/api && python -m pytest tests/test_engine_routine.py -v`
Esperado: FAIL com `TypeError: ... unexpected keyword argument 'starts_at'`

- [ ] **Passo 3: implementar**

Acrescentar `starts_at: time | None = None` ao `Commitment`. Em `busy_minutes`, separar os compromissos do dia entre os que têm horário e os que não têm. Os com horário viram intervalos `[início, início + duração)`, em minutos desde a meia-noite, e o limite pode passar de 1440. Somar o comprimento da união desses intervalos, que se calcula ordenando e fundindo. Somar ao resultado a duração dos sem horário. Atualizar a docstring de `capacities_from_commitments`, que hoje diz que os compromissos "somam".

- [ ] **Passo 4: rodar e ver passar**

Rodar: `python -m pytest tests/test_engine_routine.py tests/test_engine_purity.py -v && python -m pytest --cov=app/engine --cov-fail-under=90 -q`
Esperado: PASS. O teste antigo `test_compromissos_do_mesmo_dia_somam` continua verde porque os compromissos dele não têm horário.

- [ ] **Passo 5: checkpoint.** Rodar `ruff check . && mypy app`. Sem commit.

---

### Tarefa 2: migration 0006 e modelo

**Arquivos:**
- Criar: `db/migrations/versions/0006_rotina_editavel.py`
- Modificar: `services/api/app/models.py` (`COMMITMENT_KINDS` e `Commitment`)
- Teste: `services/api/tests/test_routine_model.py` (arquivo novo)

**Interfaces:**
- Produz, nas colunas de `Commitment`:
  - `starts_at: Mapped[time | None]` (`Time`, anulável);
  - `series_id: Mapped[uuid.UUID | None]` (`Uuid`, anulável, `index=True`);
  - `edited_by_student: Mapped[bool]` (`Boolean`, `default=False`, `server_default=sa.false()`).
- Produz: `COMMITMENT_KINDS` com `"leitura"`.

- [ ] **Passo 1: escrever o teste que falha.** No teste, gravar um `Commitment(kind="leitura", starts_at=time(21, 0), series_id=uuid4(), ...)` pela fixture `session`, que roda em SQLite com `create_all`, e ler de volta. Verificar `edited_by_student is False`, o `starts_at` igual e o `series_id` igual.
- [ ] **Passo 2: rodar.** `python -m pytest tests/test_routine_model.py -v`. Esperado: FAIL.
- [ ] **Passo 3: implementar o modelo e a migration.** Na migration, usar `op.batch_alter_table("commitment")` para quatro coisas:
  - acrescentar as três colunas;
  - criar `ix_commitment_series_id`;
  - remover `ck_commitment_kind` e recriá-la com a lista nova;
  - no `upgrade`, rodar um backfill: `UPDATE commitment SET series_id = id WHERE series_id IS NULL`. Assim cada compromisso existente vira uma série de um registro só.

  O `downgrade` desfaz tudo na ordem inversa e falha se existir linha `kind='leitura'`, com uma mensagem clara.
- [ ] **Passo 4: rodar.**
  - `python -m pytest -q`: PASS.
  - Num Postgres limpo: `alembic -c ../../db/alembic.ini upgrade head && alembic -c ../../db/alembic.ini downgrade 0005 && alembic -c ../../db/alembic.ini upgrade head`: as três sem erro.
- [ ] **Passo 5: checkpoint.**

---

### Tarefa 3: horário e série no caminho do arquivo

**Arquivos:**
- Modificar:
  - `services/api/app/extraction/schema.py`
  - `services/api/app/extraction/prompt.py`
  - `services/api/app/extraction/demo.py`
  - `exemplos/rotina-esperada.json`
  - `services/api/app/documents/service.py`: `_engine_commitments`, `confirm`, e a contagem `edited_blocks`
  - `services/api/app/api/documents.py`: `DocumentOut.edited_blocks`
  - `services/api/app/api/auth.py`: o export
- Teste: `services/api/tests/test_documents.py`, `services/api/tests/test_extraction_office.py`

**Interfaces:**
- Consome: as colunas da Tarefa 2 e `Commitment.starts_at` do motor, da Tarefa 1.
- Produz:
  - `ExtractedCommitment.starts_at: time | None = None`, aceitando `"HH:MM"`;
  - `CommitmentKind` com `"leitura"`;
  - `DocumentOut.edited_blocks: int`, o número de compromissos daquele documento com `edited_by_student`;
  - `engine_commitments(rows) -> list[EngineCommitment]`, que é o atual `_engine_commitments` renomeado para nome público e passando a repassar `starts_at`. Ajustar quem chama a função; a Tarefa 4 reutiliza.

- [ ] **Passo 1: escrever os testes que falham** em `test_documents.py`:
  - `test_confirmacao_guarda_o_horario_de_inicio`: uma rotina com `"starts_at": "07:00"` gera `Commitment.starts_at == time(7, 0)`.
  - `test_mesmo_bloco_em_dias_diferentes_vira_uma_serie`: musculação seg/qua/sex com o mesmo tipo, rótulo, horário, duração e vigência gera três linhas com o mesmo `series_id`. Um compromisso de outro rótulo tem outro `series_id`.
  - `test_compromisso_de_data_unica_tem_serie_propria`.
  - `test_documento_conta_os_blocos_editados_pelo_aluno`: marcar uma linha `edited_by_student=True` e verificar que o `GET /documents/{id}` devolve `edited_blocks == 1`.
  - `test_reconfirmar_substitui_inclusive_os_editados`: depois de reconfirmar, nenhuma linha do documento tem `edited_by_student`.

  Em `test_extraction_office.py`, ou num teste de schema ao lado: `starts_at="25:00"` é recusado e `kind="leitura"` é aceito.
- [ ] **Passo 2: rodar.** `python -m pytest tests/test_documents.py -v`. Esperado: FAIL.
- [ ] **Passo 3: implementar.**
  - Prompt: acrescentar `"starts_at": "HH:MM ou null"` e `leitura` ao formato. Acrescentar também a regra "horário de início só quando o arquivo disser; nunca invente".
  - Em `demo.py` e em `exemplos/rotina-esperada.json`: dar horários coerentes com o README dos exemplos (enfermaria 07:00, musculação 18:00 etc.).
  - Em `confirm`: a chave da série é `(kind, label, starts_at, duration_minutes, starts_on, ends_on)` para os compromissos com `weekday`, e cada chave recebe um `uuid4()`. Compromisso com `on_day` recebe `series_id` próprio.
  - Export: acrescentar `"inicio": "HH:MM" | None` e `"origem": "arquivo" | "manual"`.
- [ ] **Passo 4: rodar.** `python -m pytest -q`. Esperado: PASS.
- [ ] **Passo 5: checkpoint.**

---

### Tarefa 4: serviço da rotina (`app/routine/`)

**Arquivos:**
- Criar: `services/api/app/routine/__init__.py`, `services/api/app/routine/service.py`
- Teste: `services/api/tests/test_routine_service.py`

**Interfaces:**
- Consome: `rebuild_capacities` e `engine_commitments` de `app.documents.service` (este segundo vem da Tarefa 3); `replan`, `primary_exam` e `PlanningError` de `app.planning`; `capacities_from_commitments` e `daily_budget` de `app.engine`; `engine_params()` de `app.params`.
- Produz:

```python
MAX_ACTIVE_COMMITMENTS = 200

class RoutineError(RuntimeError): ...            # vira 422
class SeriesNotFound(RoutineError): ...          # vira 404

@dataclass(frozen=True, slots=True)
class SeriesInput:
    kind: str
    label: str
    weekdays: tuple[int, ...]       # vazio quando on_day
    on_day: date | None
    starts_at: time | None
    duration_minutes: int
    starts_on: date | None = None
    ends_on: date | None = None

@dataclass(frozen=True, slots=True)
class SaveResult:
    series_id: uuid.UUID | None     # None no delete
    replan_summary: str             # "" quando não há prova principal

@dataclass(frozen=True, slots=True)
class RoutineItem:
    series_id: uuid.UUID
    kind: str
    label: str
    starts_at: time | None
    duration_minutes: int
    recurring: bool
    document_name: str | None       # original_name do documento de origem
    edited_by_student: bool
    editable: bool                  # False para data única de hoje ou do passado

@dataclass(frozen=True, slots=True)
class RoutineDay:
    day: date
    free_minutes: int
    light: bool
    computed: bool                  # True = calculado na hora, sem linha em DailyCapacity
    items: tuple[RoutineItem, ...]  # ordenados: sem horário primeiro, depois por starts_at

@dataclass(frozen=True, slots=True)
class RoutineWeek:
    week_start: date                # segunda-feira
    today: date
    changed_today: bool             # algum registro com ends_on == today ou starts_on == today+1
    days: tuple[RoutineDay, ...]    # 7

def create_series(session, student, data: SeriesInput, *, today: date) -> SaveResult: ...
def update_series(session, student, series_id: uuid.UUID, data: SeriesInput, *, today: date) -> SaveResult: ...
def delete_series(session, student, series_id: uuid.UUID, *, today: date) -> SaveResult: ...
def week_view(session, student, week_of: date, *, today: date) -> RoutineWeek: ...
```

As regras abaixo são a mecânica decidida na spec. `amanhã` é `today + 1 dia`.
- **Validação**, que levanta `RoutineError`:
  - ter `weekdays` (valores únicos de 0 a 6) **ou** `on_day`, um dos dois e nunca os dois;
  - `on_day` maior ou igual a amanhã;
  - `kind` dentro de `COMMITMENT_KINDS`;
  - `label` com até 160 caracteres;
  - duração entre 1 e 1440 minutos;
  - `ends_on` maior ou igual a `starts_on`;
  - depois de criar, o aluno ter no máximo 200 compromissos vigentes (`ends_on is None or ends_on >= today`).
- **create:** os registros novos nascem com `starts_on = max(data.starts_on or amanhã, amanhã)`, `document_id=None` e um `series_id` novo. São um registro por weekday, ou um registro só com `on_day`.
- **update/delete:** a série é encontrada por `series_id` **e** `student_id`. Se não existir, ou se não tiver nenhum registro vigente, levanta `SeriesNotFound`. Para cada registro da série:
  - data única com `on_day <= today`: levanta `RoutineError`;
  - data única futura: o update altera o registro e o delete apaga;
  - semanal com `starts_on > today`: apaga a linha;
  - semanal vigente (`ends_on is None or ends_on > today`): grava `ends_on = today`;
  - já encerrado: não toca.

  No update, depois disso, cria os registros novos como no create, com o **mesmo** `series_id`. Se a série veio de documento, os novos herdam o `document_id` e recebem `edited_by_student=True`.
- **Depois de qualquer escrita:** se o aluno tem prova principal, chamar `rebuild_capacities(session, student, amanhã, alvo.exam_date)` e `replan(session, student, today, reason="rotina editada")`, que usa `from_tomorrow=True`, e devolver `version.summary`. Sem prova principal, `replan_summary=""`.
- **week_view:** normalizar `week_of` para a segunda-feira. Para cada dia:
  - existe linha em `DailyCapacity`: usar a linha, com `computed=False`;
  - não existe: chamar `capacities_from_commitments([dia], engine_commitments(todos), daily_budget(student.weekly_hours), engine_params())`, com `computed=True` e sem gravar nada.

  Os itens são os registros que `EngineCommitment.happens_on(dia)` aceita. `editable` é falso só para data única com `on_day <= today`.

- [ ] **Passo 1: escrever os testes que falham.** Fixture: o aluno do seed com `HOJE = date(2026, 9, 25)`, que é sexta-feira, seguindo `test_documents.py`. Testes:
  - `test_criar_serie_semanal_grava_um_registro_por_dia_comecando_amanha`: `weekdays=(0, 2, 4)` gera 3 linhas com o mesmo `series_id`, `starts_on == date(2026, 9, 26)` e `document_id is None`.
  - `test_criar_recalcula_de_amanha_e_nao_toca_hoje`: guardar `DailyCapacity` e as `Task` de `HOJE` antes de criar, e verificar que ficaram iguais depois. A capacidade de 2026-09-28, uma segunda, cai com uma academia de 600 min.
  - `test_editar_fecha_a_vigencia_e_abre_outra_na_mesma_serie`: os registros antigos ficam com `ends_on == HOJE`, os novos com `starts_on == amanhã`, e o `series_id` é o mesmo.
  - `test_desmarcar_um_dia_nao_recria_esse_dia`: de `(0, 2, 4)` para `(0, 4)`, nenhum registro vigente fica com `weekday == 2`.
  - `test_apagar_preserva_semanas_passadas`: depois do delete, `week_view` da semana de 2026-09-21 ainda mostra o item, e a semana de 2026-09-28 não mostra.
  - `test_serie_que_ainda_nao_comecou_e_apagada_de_verdade`.
  - `test_data_unica_de_hoje_nao_se_edita`: levanta `RoutineError`.
  - `test_serie_de_outro_aluno_nao_e_encontrada`: levanta `SeriesNotFound`.
  - `test_editar_bloco_de_arquivo_marca_edited_e_mantem_o_documento`.
  - `test_apagar_documento_leva_inclusive_os_registros_editados`: chamar `erase` do `app.documents` e verificar que não sobra nenhuma linha daquele documento. É o ponto de atenção 2.
  - `test_teto_de_compromissos_vigentes`: o 201º levanta `RoutineError`.
  - `test_semana_sem_capacidade_gravada_vem_calculada`: com um aluno sem prova principal, `computed is True` e `free_minutes` igual ao que o motor dá.
  - `test_sem_prova_principal_salva_sem_replanejar`: `replan_summary == ""` e nenhuma `PlanVersion` nova.
  - `test_changed_today_liga_depois_de_editar`.
- [ ] **Passo 2: rodar.** `python -m pytest tests/test_routine_service.py -v`. Esperado: FAIL com `ModuleNotFoundError: app.routine`.
- [ ] **Passo 3: implementar** `app/routine/service.py` com as assinaturas e regras acima. Exportar no `__init__.py`.
- [ ] **Passo 4: rodar.** `python -m pytest -q && mypy app`. Esperado: PASS.
- [ ] **Passo 5: checkpoint.**

---

### Tarefa 5: API da rotina

**Arquivos:**
- Criar: `services/api/app/api/routine.py`
- Modificar: `services/api/app/api/__init__.py`, para registrar `routine_router` em `routers`
- Teste: `services/api/tests/test_api_routine.py`

**Interfaces:**
- Consome: tudo o que a Tarefa 4 produz.
- Produz, sob `/api/v1`, sempre com `current_student` e com `today = today_in(student.timezone)`:
  - `GET /me/routine?week=AAAA-MM-DD` (opcional; padrão hoje) → `RoutineWeekOut`;
  - `POST /me/commitment-series` com `CommitmentSeriesIn` → 201 `SaveOut`;
  - `PATCH /me/commitment-series/{series_id}` com `CommitmentSeriesIn` → 200 `SaveOut`;
  - `DELETE /me/commitment-series/{series_id}` → 200 `SaveOut`.

  Os schemas:
  - `CommitmentSeriesIn` (Pydantic, `extra="forbid"`): `kind: Literal[...6 tipos]`, `label: str (max 160)`, `weekdays: list[int] = []`, `on_day: date | None`, `starts_at: time | None`, `duration_minutes: int (1..1440)`, `starts_on: date | None`, `ends_on: date | None`.
  - `SaveOut`: `series_id: UUID | None`, `replan_summary: str`.
  - `RoutineWeekOut`: espelha `RoutineWeek`, com `starts_at` serializado como `"HH:MM"`.

  `SeriesNotFound` vira 404, `RoutineError` vira 422.

- [ ] **Passo 1: escrever os testes que falham.** Usar as fixtures `client` e `login`, com o padrão de `test_api_plan.py` para fixar o dia: monkeypatch de `app.api.routine.today_in`. Testes:
  - `test_sem_login_responde_401`.
  - `test_cria_lista_edita_e_apaga_uma_serie`: o fluxo completo pela API.
  - `test_serie_de_outro_aluno_responde_404`: tanto no PATCH quanto no DELETE.
  - `test_campo_desconhecido_e_recusado`: 422.
  - `test_semanal_e_data_unica_juntos_sao_recusados`: 422.
  - `test_amanha_e_o_do_fuso_do_aluno`: o aluno tem `timezone="America/Fortaleza"` e `today_in` é fixado devolvendo 2026-09-25. Os registros criados ficam com `starts_on == 2026-09-26`. É o ponto de atenção 3; garante que a rota passa o fuso do aluno.
  - `test_aluno_sem_prova_principal_salva_e_ve_a_semana`: 201, `replan_summary == ""`, e o GET traz 7 dias com `computed` verdadeiro. É o ponto de atenção 4.
  - `test_semana_normaliza_para_segunda`: `?week=2026-10-01` traz `week_start == "2026-09-28"`.
- [ ] **Passo 2: rodar.** `python -m pytest tests/test_api_routine.py -v`. Esperado: FAIL com 404 em todas as rotas.
- [ ] **Passo 3: implementar** `app/api/routine.py`. O endpoint não contém regra: converte o payload em `SeriesInput`, chama o serviço e traduz as exceções em status HTTP.
- [ ] **Passo 4: rodar.** A suíte inteira, `ruff check . && ruff format --check . && mypy app`, mais um `uvicorn` local abrindo `/docs` para conferir as quatro rotas.
- [ ] **Passo 5: checkpoint.**

---

### Tarefa 6: tela Minha rotina na PWA

**Arquivos:**
- Criar:
  - `apps/web/src/app/core/routine-api.ts`
  - `apps/web/src/app/routine/routine.ts`, `.html`, `.scss`
  - `apps/web/src/app/routine/commitment-form.ts`, `.html`, `.scss`
  - `apps/web/src/app/routine/routine.spec.ts`
- Modificar:
  - `apps/web/src/app/app.routes.ts`: rota `rotina` com `authGuard`;
  - `apps/web/src/app/app.html`: o link "Minha rotina" passa a apontar para `/rotina`;
  - `apps/web/src/app/core/onboarding-api.ts`: `starts_at` e `leitura` em `CompromissoExtraido`, e `edited_blocks` em `DocumentoOut`;
  - `apps/web/src/app/onboarding/onboarding.html` e `.ts`: campo de horário na conferência e aviso de blocos editados.

**Interfaces:**
- Consome: as rotas da Tarefa 5.
- Produz: `RoutineApi` com estes métodos:
  - `week(weekOf?: string): Observable<RoutineWeek>`
  - `create(input: SeriesInput): Observable<SaveResult>`
  - `update(seriesId: string, input: SeriesInput): Observable<SaveResult>`
  - `remove(seriesId: string): Observable<SaveResult>`

  Os tipos TS espelham os `*Out` da Tarefa 5, com `starts_at: string | null` no formato `"HH:MM"`.

Comportamento:
- **Um layout só, alternado por CSS:**
  - Acima de 768 px aparece a grade de 7 colunas, com horas de 6h a 24h na lateral e rolagem vertical.
  - Abaixo de 768 px aparecem as abas S T Q Q S S D, e só a coluna do `diaSelecionado()` fica visível. O dia inicial é hoje.
- **Itens sem horário** ficam numa faixa "sem horário" no topo da coluna.
- **Bloco que passa da meia-noite** é desenhado até 24h no dia de início. O resto aparece no topo do dia seguinte, se esse dia estiver na semana exibida.
- **Cores por tipo** via classe: `.aula`, `.plantao`, `.academia`, `.leitura`, `.trabalho`, `.outro`. Os tons de partida estão no esboço `.superpowers/brainstorm/*/content/rotina-layout.html`.
- **Rodapé de cada dia:**
  - "dia leve" quando `light`;
  - senão, `estudo: Xh` ou `estudo: Xh YYmin` a partir de `free_minutes`. Em zero, mostrar "estudo: 0".
  - Em hoje com `changed_today`, acrescentar "mudanças valem a partir de amanhã".
- **Navegação:** "semana anterior" e "próxima semana" recarregam com `week`.
- **O formulário (`commitment-form`)** abre vazio pelo "+ adicionar" ou preenchido ao tocar num bloco `editable`. Os campos:
  - tipo e nome;
  - "toda semana" (checkbox por dia) ou "só uma vez" (data);
  - início (`<input type="time">`) e duração em minutos;
  - em "mais opções", a vigência de/até.

  Num bloco de arquivo, o formulário mostra "veio de: {document_name}". O botão "apagar" aparece só na edição. "Salvar" e "apagar" ficam desabilitados quando `!navigator.onLine` ou durante uma requisição. Depois de salvar, aparece o `replan_summary` (se não vier vazio) e a semana é recarregada.
- **Link "enviar arquivo novo"** leva para `/comecar`.

- [ ] **Passo 1: escrever os testes que falham** em `routine.spec.ts`, com `HttpTestingController` e uma semana fixa: seg/qua/sex com academia às 18:00, terça com `free_minutes: 0`, sábado `light`, domingo com plantão às 19:00 de 720 min.
  - `mostra as sete colunas com os blocos da API`: 7 `.dia` e 3 `.academia`.
  - `o rodapé mostra estudo, zero e dia leve`: os textos "estudo: 2h", "estudo: 0" e "dia leve".
  - `plantão noturno de domingo não vaza para fora da semana`: o domingo tem o bloco e nenhuma coluna mostra "continua". É o ponto de atenção 1.
  - `adicionar academia seg/qua/sex envia a série`: o `POST /api/v1/me/commitment-series` tem o corpo `{kind:'academia', weekdays:[0,2,4], starts_at:'07:00', duration_minutes:60, ...}`.
  - `tocar num bloco abre a edição e salvar faz PATCH na série`.
  - `salvar fica desabilitado enquanto a requisição está aberta`: dois cliques geram uma requisição só. É o ponto de atenção 5.
  - `sem rede o salvar fica desabilitado`: simular com `spyOnProperty(navigator, 'onLine').and.returnValue(false)`.
  - `depois de salvar mostra o resumo e recarrega a semana`.
- [ ] **Passo 2: rodar.** `cd apps/web && npm run test:ci`. Esperado: FAIL.
- [ ] **Passo 3: implementar** os componentes e os ajustes de rota, navegação e onboarding descritos acima. A tela não calcula capacidade: só formata `free_minutes`.
- [ ] **Passo 4: rodar.** `npm run test:ci && npm run build`. Esperado: PASS. Depois, com `docker compose up`, abrir `/rotina` com o aluno do seed numa janela larga e numa estreita (DevTools, 390 px) e conferir as duas vistas.
- [ ] **Passo 5: checkpoint.**

---

### Tarefa 7: documentação

**Arquivos:**
- Modificar: `README.md`, para citar a tela Minha rotina na seção "Estado atual" e no fluxo "Como testar do zero".
- Modificar: `exemplos/README.md`. Corrigir "Na tela de conferência da rotina (`/rotina`)" para `/comecar` e citar `/rotina` para ajustes à mão.
- Modificar: `.gitignore`, acrescentando `.superpowers/`.

- [ ] **Passo 1:** editar os três arquivos.
- [ ] **Passo 2:** rodar a suíte inteira da API e da PWA uma última vez, com os mesmos comandos do CI.
- [ ] **Passo 3: checkpoint final.** Antes de propor o PR, rodar os agentes `test-engineer`, `spec-validator` e `code-reviewer`, e o `security-auditor` também, porque a mudança mexe em dado de aluno.
