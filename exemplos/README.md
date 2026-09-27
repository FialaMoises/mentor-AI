# Arquivos de exemplo

Uma aluna fictícia inteira, para testar o upload da rotina sem precisar dos
arquivos de ninguém de verdade.

**Marina Duarte Lopes**, 6º ano, internato de Clínica Médica. Prova principal:
ENAMED em 22/11/2026. Trabalha como monitora, dá aula particular, faz cursinho
no fim de semana e tira plantão de 12 horas. Nome, faculdade, hospital,
cursinho, preceptores e datas são inventados.

| Arquivo | Tipo no upload | Formato | O que traz |
|---|---|---|---|
| `grade-internato-2026-2.pdf` | grade | PDF | Enfermaria de segunda a sexta, ambulatório na terça, discussão de casos na quinta |
| `escala-plantoes-outubro-2026.xlsx` | escala | XLSX | Seis plantões de 12 h em outubro, dois deles noturnos |
| `rotina-academia-e-trabalho.docx` | outro | DOCX | Academia, monitoria, aulas particulares e cursinho |
| `cursinho-cronograma-foto.jpg` | cursinho | JPEG | Cronograma do cursinho, como foto de um papel |
| `escala-mural-novembro-foto.png` | escala | PNG | Escala de novembro, como foto do mural do hospital |

Os cinco formatos que a API aceita estão cobertos: PDF, XLSX, DOCX, JPEG e PNG.
Word e Excel não sobem para o modelo como arquivo — a API tira o texto de
dentro deles antes (`app/extraction/office.py`), inclusive convertendo as datas
da planilha, que no XLSX são números.

## Como usar

Na tela de conferência da rotina (`/rotina`), escolha o tipo, selecione o
arquivo e confira a semana que aparecer.

**Com `ANTHROPIC_API_KEY` no `.env`:** o modelo lê o arquivo de verdade. É o
caminho que interessa testar — inclusive o que ele erra.

**Sem a chave:** a API responde com uma rotina de exemplo e avisa, na própria
tela de conferência, que não leu arquivo nenhum. O que vem depois — conferir a
semana, recalcular a capacidade, replanejar — funciona igual.

`rotina-esperada.json` é a semana completa da Marina no formato que a API
aceita: dá para comparar com o que o modelo extraiu, ou mandar direto:

```powershell
curl.exe -X POST http://localhost:8000/api/v1/documents/SEU_ID_DE_DOCUMENTO/confirm ^
  -H "authorization: Bearer SEU_TOKEN" -H "content-type: application/json" ^
  -d "@exemplos/rotina-esperada.json"
```

## O que a semana dela faz com o plano

Com 14 horas de estudo por semana (120 min/dia) e a janela de estudo padrão de
10 horas por dia:

- segunda, quarta, quinta, sexta: 120 min — a enfermaria cabe no dia
- terça: 0 min — sai 7h, volta 20h entre enfermaria, ambulatório e monitoria
- dia de plantão de 12 h: 0 min
- dia seguinte a plantão de 12 h: dia leve, só revisão e questões

## Regerar

```bash
python exemplos/gerar.py
```

Precisa de `reportlab`, `openpyxl`, `python-docx` e `Pillow` — nenhum deles é
dependência da API, só deste script.
