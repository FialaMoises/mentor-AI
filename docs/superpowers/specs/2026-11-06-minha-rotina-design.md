# Minha rotina — agenda de compromissos editável pelo aluno

Data: 2026-11-06 · Status: rascunho para aprovação do Moisés

## Intenção

Hoje todo compromisso do aluno nasce de um arquivo (grade, escala, cronograma)
lido pela extração. O que quase nunca está num arquivo — academia às 18h, meia
hora de leitura antes de dormir, um dentista na quinta — não tem como entrar, e
o plano superestima o tempo livre do aluno nesses dias.

A tela **Minha rotina** dá ao aluno uma agenda no estilo Google Agenda onde ele
vê, adiciona, edita e apaga o que ocupa a semana dele. O motor continua fazendo
a mesma conta: compromisso come a janela do dia; o que sobra vira estudo.

O produto continua focado em residência médica. Ampliar para outros
profissionais foi considerado e adiado.

## Objetivos

- O aluno abre uma tela de agenda a qualquer momento (não só no onboarding).
- Vê todos os compromissos da semana com horário, coloridos por tipo, e
  embaixo de cada dia quanto sobra para estudo (ou "dia leve").
- Adiciona compromissos sem arquivo: principalmente os que se repetem toda
  semana (academia seg/qua/sex), e também os de um dia só (dentista dia 12).
- Edita e apaga qualquer compromisso, inclusive os que vieram de arquivo.
- Ao salvar, a capacidade é recalculada de amanhã até a prova e o plano é
  refeito; o aluno vê um resumo curto do efeito.

## Não-objetivos

- Academia e leitura **não** viram itens do checklist para marcar como feito.
  São só tempo ocupado.
- A lista de estudo do dia continua **sem horário** (decisão da spec). O
  horário existe só na agenda de compromissos.
- Não há integração com Google Agenda (exportar/importar fica para depois, como
  a spec já diz).
- Nada de arrastar e soltar blocos na grade nesta versão.

## Antiobjetivos (o que faria isso fracassar mesmo funcionando)

- Mexer na lista de hoje. A regra 3 do CLAUDE.md vale: salvar a rotina
  replaneja de amanhã em diante.
- Regra de capacidade no front ou no endpoint (regra 2). A tela mostra o que o
  motor calculou; não refaz a conta.
- Aceitar dado do aluno sem validação no servidor.

## Decisões do Moisés

1. Tela própria "Minha rotina", aberta pelo menu a qualquer momento.
2. Visual de agenda com horário e o que vai fazer, no estilo Google Agenda.
3. Layout responsivo (opção C do esboço): grade da semana em tela larga; um dia
   por vez com abas dos dias no celular. O esboço está em
   `.superpowers/brainstorm/*/content/rotina-layout.html`.
4. Compromissos que vieram de arquivo também podem ser editados e apagados.
5. Foco em compromissos que se repetem toda semana; o de data única também pode
   ser adicionado à mão.

## Como funciona

### Modelo de dados (migration nova, `0006_...`)

- `commitment.starts_at` (`time`, anulável): horário de início. Anulável porque
  os compromissos já gravados não têm horário.
- Tipo novo `leitura` em `COMMITMENT_KINDS` e no check constraint
  (`aula, plantao, academia, trabalho, leitura, outro`).
- `commitment.edited_by_student` (`bool`, padrão `false`): marca o bloco de
  arquivo que o aluno alterou à mão. *Decisão minha.*
- `commitment.series_id` (`uuid`, anulável, indexado): agrupa os registros de
  um mesmo compromisso semanal (um registro por dia da semana). Gravado na
  criação manual e também na confirmação de documento (compromissos extraídos
  com mesmo tipo, rótulo, início e duração em dias diferentes viram uma série).
  Compromisso de data única tem série própria de um registro.
- `document_id` já é anulável: compromisso digitado à mão fica com
  `document_id = null`.

### Motor (`app/engine/routine.py`, continua puro)

- `Commitment` ganha `starts_at: time | None`.
- **Sobreposição conta uma vez.** Com horário, dois compromissos que se
  sobrepõem (academia 18h–19h15 cadastrada à mão em cima de um bloco do
  arquivo) não podem descontar o tempo em dobro. `busy_minutes` passa a somar
  a união dos intervalos dos compromissos com horário, mais a duração dos sem
  horário (como hoje). *Decisão minha* — sem isso, a agenda nova piora o plano
  ao duplicar tempo.
- **Atravessar a meia-noite é permitido** (plantão noturno 19h–7h). Para a
  capacidade, o compromisso inteiro continua contando no dia em que começa,
  como hoje; a regra do dia leve depois de plantão longo não muda. A agenda
  desenha o bloco partido nos dois dias, quando os dois estão na semana
  exibida (o plantão de domingo não aparece na madrugada da segunda da semana
  seguinte; a capacidade está certa). *Decisão minha*, para não mudar a conta
  que já está testada.
- Duração continua de 1 min a 24 h.

### Extração (`app/extraction/`)

- `ExtractedCommitment` ganha `starts_at` (`"HH:MM"`, opcional) e `kind`
  aceita `leitura`. O prompt em `prompt.py` passa a pedir o horário de início
  quando o arquivo disser, sem inventar quando não disser.
- `demo.py` e `exemplos/rotina-esperada.json` ganham horários.
- A tela de conferência da semana mostra e permite corrigir o horário.

### API (`app/api/`, aluno sempre da sessão)

- `GET /api/v1/me/routine?week=AAAA-MM-DD` — compromissos que acontecem na
  semana pedida (já expandidos por dia, com vigência aplicada) e a capacidade
  de cada dia vinda de `DailyCapacity` (minutos livres, dia leve). A semana
  padrão é a atual.
- `POST /api/v1/me/commitment-series` — cria. Corpo: `kind`, `label`,
  `weekdays: int[]` **ou** `on_day`, `starts_at`, `duration_minutes`,
  `starts_on?`, `ends_on?`. Vários dias da semana viram vários registros (um
  por `weekday`), mantendo o modelo atual. *Decisão minha.*
- `PATCH /api/v1/me/commitment-series/{series_id}` e
  `DELETE /api/v1/me/commitment-series/{series_id}`. Série de outro aluno
  responde 404 (regra 8). Editar um bloco de arquivo liga `edited_by_student`.
- **Decisão do Moisés: editar ou apagar vale para a série toda, de amanhã em
  diante.** Não existe "só este dia" nesta versão. Semanas passadas não mudam:
  - editar fecha a vigência dos registros atuais (`ends_on = hoje`) e cria os
    novos com `starts_on = amanhã`, na mesma série — inclusive quando os dias
    marcados mudam (desmarcar quarta simplesmente não recria a quarta);
  - apagar fecha a vigência (`ends_on = hoje`);
  - registro cuja vigência ainda nem começou (`starts_on > hoje`) é editado ou
    apagado de verdade, já que não tem passado a preservar;
  - compromisso de data única é editado ou apagado direto, se a data for
    amanhã ou depois; data de hoje ou passada não se edita.
  *Decisão minha* sobre a mecânica (vigência em vez de apagar a linha).
- Validação no servidor com o mesmo schema estrito (`extra="forbid"`), rótulo
  até 160 caracteres, teto de compromissos por aluno (sugestão: 200, o mesmo
  da extração).
- Toda escrita roda no serviço (não no endpoint): grava, chama
  `rebuild_capacities(amanhã, prova)` e `replan(from_tomorrow=True,
  reason="rotina editada")`, e devolve o resumo da versão do plano. Hoje
  `rebuild_capacities` começa em `today`; para a rotina editada começa em
  amanhã, para não reescrever a capacidade de hoje.

### Capacidade mostrada na agenda

- Dia com linha em `DailyCapacity`: mostra a linha gravada.
- **Hoje** mostra a capacidade congelada; se o aluno mudou a rotina hoje, o
  rodapé de hoje diz "mudanças valem a partir de amanhã".
- Dia sem linha (semana passada, depois da prova, aluno sem prova principal):
  a API calcula na hora com `capacities_from_commitments` do motor, sem gravar
  nada. O front nunca faz a conta (regra 2). *Decisão minha.*
- Aluno sem prova principal pode salvar a rotina normalmente; só não há
  recálculo gravado nem replanejamento até existir prova principal.

### Rede

- Salvar a rotina exige rede: sem conexão, o formulário fica desabilitado com
  um aviso. A rotina **não** entra na fila offline do checklist, então não
  precisa de `client_event_id`. *Decisão minha.*

### Reenvio de arquivo e exclusão

- Reconfirmar o mesmo documento apaga e recria os compromissos dele a partir
  do JSON conferido (como hoje). Se algum bloco desse documento tiver
  `edited_by_student = true`, a tela de conferência avisa antes: "você
  editou N blocos deste arquivo na sua rotina; confirmar de novo substitui
  essas edições". *Decisão minha* — evita casar bloco editado com bloco
  extraído (frágil) e evita duplicação.
- Um arquivo novo (outra escala, outro rodízio) é outro documento: não toca
  nos compromissos dos documentos anteriores nem nos digitados à mão.
- Apagar o documento a pedido do aluno continua apagando todos os compromissos
  dele, inclusive os editados (regra 7, exclusão completa).
- Compromissos digitados à mão (`document_id = null`) nunca são tocados por
  upload, confirmação ou expurgo; somem só se o aluno apagar ou apagar a conta.
- `/me/export` passa a incluir `starts_at` e a origem de cada compromisso.

### PWA (`apps/web/`)

- Rota nova `/rotina` (protegida pelo `authGuard`) e link no menu.
  *Atenção:* o `exemplos/README.md` chama de `/rotina` a tela de conferência;
  hoje ela vive em `/comecar`. Ajustar o texto do README.
- Componente responsivo: acima de ~768 px, grade de 7 colunas com horas na
  lateral (0h–24h, sem rolagem interna, para a madrugada do plantão aparecer); abaixo, abas S T Q Q S S D e linha do tempo do
  dia. Compromisso sem horário aparece numa faixa "sem horário" no topo do dia,
  como evento de dia inteiro no Google Agenda.
- Cores por tipo: faculdade/aula, plantão, academia, leitura, trabalho, outro
  (as do esboço servem de ponto de partida).
- Cada item da semana traz `series`: a definição da série como ela vale de
  amanhã em diante (dias, horário, vigência). É isso que a edição abre — nunca
  o que a semana exibida mostra. Série sem registro vigente não é editável.
- Rodapé de cada dia: "estudo: 2h", "estudo: 0" ou "dia leve", lido da API.
- Tocar num bloco abre o formulário de edição; "+ adicionar" abre o mesmo
  formulário vazio. Campos: tipo, nome, "toda semana" (dias marcáveis) ou "só
  uma vez" (data), início, duração ou fim, e em "mais opções" a vigência
  (de/até). Bloco de arquivo mostra "veio da sua escala (arquivo X)".
- Navegação entre semanas (anterior/próxima), já que a escala muda por mês.
- Depois de salvar, mostrar o resumo que a API devolveu.

## Restrições do projeto que se aplicam

Regras 1, 2, 3, 8, 11, 15 (relógio só na borda: `today_in` decide o
"amanhã"), 16 e 18 do `CLAUDE.md`. A spec v0.1 não previa compromisso sem
arquivo nem horário de início; com autorização do Moisés, ganhou um parágrafo
sobre a tela Minha rotina na seção "Público e jornada do aluno", apontando
para este documento.

## Testes esperados

- Motor: união de intervalos sobrepostos; compromisso sem horário somando como
  hoje; plantão que atravessa a meia-noite; pureza preservada; cobertura ≥ 90%.
- API: CRUD do aluno dono, 404 para compromisso de outro aluno, validação de
  campos, hoje intocado depois de salvar, replanejamento disparado.
- Reconfirmação substituindo bloco editado (com o aviso na resposta);
  exclusão de documento levando tudo.
- Capacidade calculada na hora para dia sem linha, sem gravar.
- Front: a grade e a visão de dia renderizam a mesma semana; formulário
  semanal e de data única.

## Fica com quem constrói

Nome exato dos componentes, biblioteca (ou nenhuma) para a grade, formato do
campo de horário, paleta final, textos de interface e a ordem das tarefas no
plano de implementação.
