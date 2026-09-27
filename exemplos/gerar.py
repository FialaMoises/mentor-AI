"""Gera os arquivos de exemplo da aluna fictícia Marina Duarte Lopes.

Os arquivos servem para testar o upload e a extração de ponta a ponta, nos
cinco formatos que o `app/storage` aceita: PDF, XLSX, DOCX, JPEG e PNG.

    python exemplos/gerar.py

Nada aqui entra no caminho da aplicação: é script de desenvolvimento. Os dados
são inventados — nome, faculdade, hospital, preceptores e datas.
"""

from __future__ import annotations

import subprocess
from datetime import date, time
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

AQUI = Path(__file__).resolve().parent

ALUNA = "Marina Duarte Lopes"
MATRICULA = "RA 2021104532"
FACULDADE = "Faculdade de Medicina do Vale do Piquiri"
HOSPITAL = "Hospital Municipal Dom Aquino"
CURSINHO = "Cursinho Residência Já"

SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ---------------------------------------------------------------- 1. grade PDF


def grade_pdf(destino: Path) -> None:
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "titulo", parent=estilos["Title"], fontSize=14, leading=18, spaceAfter=2
    )
    sub = ParagraphStyle(
        "sub", parent=estilos["Normal"], fontSize=9.5, alignment=1, textColor=colors.HexColor("#444")
    )
    corpo = ParagraphStyle("corpo", parent=estilos["Normal"], fontSize=9, leading=12)
    celula = ParagraphStyle("celula", parent=estilos["Normal"], fontSize=7.6, leading=9.4)
    rodape = ParagraphStyle(
        "rodape", parent=estilos["Normal"], fontSize=7, textColor=colors.HexColor("#777")
    )

    doc = SimpleDocTemplate(
        str(destino),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title="Grade do internato — 2026.2",
        author=FACULDADE,
    )

    def c(texto: str) -> Paragraph:
        return Paragraph(texto, celula)

    vazio = ""
    linhas = [
        [
            c("<b>Horário</b>"),
            c("<b>Segunda</b>"),
            c("<b>Terça</b>"),
            c("<b>Quarta</b>"),
            c("<b>Quinta</b>"),
            c("<b>Sexta</b>"),
            c("<b>Sábado</b>"),
        ],
        [
            c("07:00<br/>13:00"),
            c("Clínica Médica<br/>Enfermaria 3º and."),
            c("Clínica Médica<br/>Enfermaria 3º and."),
            c("Clínica Médica<br/>Enfermaria 3º and."),
            c("Clínica Médica<br/>Enfermaria 3º and."),
            c("Clínica Médica<br/>Enfermaria 3º and."),
            c(vazio),
        ],
        [
            c("13:00<br/>14:00"),
            c("Almoço"),
            c("Almoço"),
            c("Almoço"),
            c("Almoço"),
            c("Almoço"),
            c(vazio),
        ],
        [
            c("14:00<br/>18:00"),
            c(vazio),
            c("Ambulatório de<br/>Pediatria — sala 12"),
            c(vazio),
            c(vazio),
            c(vazio),
            c(vazio),
        ],
        [
            c("14:00<br/>16:00"),
            c(vazio),
            c(vazio),
            c(vazio),
            c("Discussão de casos<br/>Anfiteatro B"),
            c(vazio),
            c(vazio),
        ],
    ]

    largura = doc.width
    col = [largura * 0.10] + [largura * 0.15] * 6
    tabela = Table(linhas, colWidths=col, repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dce6f1")),
                ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f2f2f2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    doc.build(
        [
            Paragraph(FACULDADE.upper(), titulo),
            Paragraph("Coordenação do Internato — 6º ano", sub),
            Spacer(1, 10),
            Paragraph(
                f"<b>GRADE SEMANAL — 2º SEMESTRE DE 2026</b><br/>"
                f"Aluna: {ALUNA} ({MATRICULA})<br/>"
                f"Módulo vigente: Clínica Médica — 03/08/2026 a 18/12/2026",
                corpo,
            ),
            Spacer(1, 10),
            tabela,
            Spacer(1, 12),
            Paragraph(
                "<b>Observações</b><br/>"
                "1. A presença na enfermaria é das 07h às 13h, de segunda a sexta, "
                "durante todo o módulo.<br/>"
                "2. Os plantões de urgência não constam desta grade: seguem a escala "
                "mensal publicada pelo serviço.<br/>"
                "3. Não há atividade de internato nos feriados nem no recesso de fim de ano.",
                corpo,
            ),
            Spacer(1, 16),
            Paragraph(
                "Arquivo de exemplo do projeto mentor-AI. Instituição, pessoas e datas "
                "são fictícias.",
                rodape,
            ),
        ]
    )


# --------------------------------------------------------------- 2. escala XLSX

PLANTOES_OUTUBRO = [
    (date(2026, 10, 3), "Pronto-socorro adulto", time(7, 0), time(19, 0), "Dr. Heitor Sampaio"),
    (date(2026, 10, 11), "Pronto-socorro adulto", time(7, 0), time(19, 0), "Dra. Vanda Coutinho"),
    (date(2026, 10, 16), "Pronto-socorro pediátrico", time(19, 0), time(7, 0), "Dr. Ivo Rangel"),
    (date(2026, 10, 24), "Pronto-socorro adulto", time(7, 0), time(19, 0), "Dra. Vanda Coutinho"),
    (date(2026, 10, 27), "Pronto-socorro adulto", time(19, 0), time(7, 0), "Dr. Heitor Sampaio"),
    (date(2026, 10, 31), "Pronto-socorro adulto", time(7, 0), time(19, 0), "Dr. Ivo Rangel"),
]

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def escala_xlsx(destino: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Outubro 2026"

    borda = Border(*[Side(style="thin", color="BFBFBF")] * 4)
    cabecalho = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    fundo = PatternFill("solid", fgColor="1F4E79")
    normal = Font(name="Arial", size=10)

    ws["A1"] = f"{HOSPITAL} — ESCALA DE PLANTÕES"
    ws["A1"].font = Font(name="Arial", size=13, bold=True)
    ws["A2"] = "Internato 6º ano — outubro de 2026"
    ws["A2"].font = Font(name="Arial", size=10, italic=True)
    ws["A3"] = f"Aluna: {ALUNA} ({MATRICULA})"
    ws["A3"].font = normal

    titulos = ["Data", "Dia da semana", "Setor", "Entrada", "Saída", "Horas", "Preceptor"]
    for coluna, texto in enumerate(titulos, start=1):
        cel = ws.cell(row=5, column=coluna, value=texto)
        cel.font = cabecalho
        cel.fill = fundo
        cel.alignment = Alignment(horizontal="center")
        cel.border = borda

    linha = 6
    for dia, setor, entrada, saida, preceptor in PLANTOES_OUTUBRO:
        ws.cell(row=linha, column=1, value=dia).number_format = "DD/MM/YYYY"
        ws.cell(row=linha, column=2, value=DIAS[dia.weekday()])
        ws.cell(row=linha, column=3, value=setor)
        ws.cell(row=linha, column=4, value=entrada).number_format = "HH:MM"
        ws.cell(row=linha, column=5, value=saida).number_format = "HH:MM"
        # MOD resolve o plantão que atravessa a meia-noite.
        ws.cell(row=linha, column=6, value=f"=MOD(E{linha}-D{linha},1)*24").number_format = "0"
        ws.cell(row=linha, column=7, value=preceptor)
        for coluna in range(1, 8):
            cel = ws.cell(row=linha, column=coluna)
            cel.font = normal
            cel.border = borda
            if coluna in (1, 2, 4, 5, 6):
                cel.alignment = Alignment(horizontal="center")
        linha += 1

    ws.cell(row=linha, column=4, value="Total de horas").font = Font(
        name="Arial", size=10, bold=True
    )
    total = ws.cell(row=linha, column=6, value=f"=SUM(F6:F{linha - 1})")
    total.font = Font(name="Arial", size=10, bold=True)
    total.number_format = "0"
    total.border = borda

    ws.cell(
        row=linha + 2,
        column=1,
        value="Plantão noturno entra às 19h e sai às 7h do dia seguinte.",
    ).font = Font(name="Arial", size=9, italic=True)
    ws.cell(
        row=linha + 3,
        column=1,
        value="Troca de plantão só com aviso à preceptoria até 48h antes.",
    ).font = Font(name="Arial", size=9, italic=True)
    ws.cell(
        row=linha + 5,
        column=1,
        value="Arquivo de exemplo do projeto mentor-AI. Hospital, pessoas e datas são fictícios.",
    ).font = Font(name="Arial", size=8, color="808080")

    for coluna, largura in enumerate([12, 14, 28, 10, 10, 8, 22], start=1):
        ws.column_dimensions[get_column_letter(coluna)].width = largura
    ws.freeze_panes = "A6"

    wb.save(destino)


# --------------------------------------------------------------- 3. rotina DOCX


def rotina_docx(destino: Path) -> None:
    doc = Document()
    estilo = doc.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(11)

    titulo = doc.add_heading("Minha rotina fixa fora da faculdade", level=1)
    titulo.alignment = WD_ALIGN_PARAGRAPH.LEFT

    doc.add_paragraph(
        f"{ALUNA} — 6º ano, internato de Clínica Médica. "
        "Prova principal: ENAMED, em 22 de novembro de 2026."
    )

    doc.add_heading("Academia", level=2)
    doc.add_paragraph("Segunda, quarta e sexta, das 20:00 às 21:15 — musculação.", style="List Bullet")
    doc.add_paragraph("Domingo, das 08:00 às 09:00 — corrida leve no parque.", style="List Bullet")

    doc.add_heading("Trabalho", level=2)
    doc.add_paragraph(
        "Monitoria de Semiologia (bolsa da faculdade): terça, das 18:00 às 20:00.",
        style="List Bullet",
    )
    doc.add_paragraph(
        "Aulas particulares para o 2º ano: sábado, das 09:00 às 12:00.",
        style="List Bullet",
    )

    doc.add_heading("Cursinho", level=2)
    doc.add_paragraph(
        f"{CURSINHO} — aulas ao vivo no sábado, das 14:00 às 18:00.", style="List Bullet"
    )
    doc.add_paragraph("Revisão guiada do cursinho no domingo, das 10:00 às 12:00.", style="List Bullet")

    doc.add_heading("Resumo da semana", level=2)
    tabela = doc.add_table(rows=1, cols=3)
    tabela.style = "Table Grid"
    tabela.alignment = WD_TABLE_ALIGNMENT.LEFT
    cabecalho = tabela.rows[0].cells
    for celula, texto in zip(cabecalho, ["Dia", "Compromisso", "Horário"], strict=True):
        celula.text = texto
        celula.paragraphs[0].runs[0].font.bold = True

    for dia, compromisso, horario in [
        ("Segunda", "Academia", "20:00 – 21:15"),
        ("Terça", "Monitoria de Semiologia", "18:00 – 20:00"),
        ("Quarta", "Academia", "20:00 – 21:15"),
        ("Quinta", "Livre depois das 16:00", "—"),
        ("Sexta", "Academia", "20:00 – 21:15"),
        ("Sábado", "Aulas particulares e cursinho", "09:00 – 12:00 e 14:00 – 18:00"),
        ("Domingo", "Corrida e revisão do cursinho", "08:00 – 09:00 e 10:00 – 12:00"),
    ]:
        linha = tabela.add_row().cells
        linha[0].text = dia
        linha[1].text = compromisso
        linha[2].text = horario

    doc.add_paragraph()
    doc.add_paragraph(
        "Domingo à noite eu não estudo — fico com a minha família.",
    )

    nota = doc.add_paragraph()
    corrida = nota.add_run(
        "Arquivo de exemplo do projeto mentor-AI. Pessoas, cursinho e datas são fictícios."
    )
    corrida.font.size = Pt(8)
    corrida.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    doc.save(destino)


# ------------------------------------------------------- 4 e 5. fotos (JPEG/PNG)


def _papel(largura: int, altura: int, cor: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (largura, altura), cor)


def _fotografar(papel: Image.Image, fundo: tuple[int, int, int], giro: float) -> Image.Image:
    """Deixa a imagem com cara de foto: papel torto sobre uma mesa, com sombra."""
    margem = int(papel.width * 0.09)
    cena = Image.new("RGB", (papel.width + margem * 2, papel.height + margem * 2), fundo)

    sombra = Image.new("L", cena.size, 0)
    ImageDraw.Draw(sombra).rectangle(
        [margem + 10, margem + 14, margem + papel.width + 10, margem + papel.height + 14],
        fill=120,
    )
    sombra = sombra.filter(ImageFilter.GaussianBlur(14))
    cena.paste(Image.new("RGB", cena.size, (20, 18, 16)), (0, 0), sombra)

    cena.paste(papel, (margem, margem))
    cena = cena.rotate(giro, resample=Image.BICUBIC, expand=False, fillcolor=fundo)

    # Luz desigual, como a de uma foto tirada no corredor.
    brilho = Image.new("L", cena.size, 0)
    desenho = ImageDraw.Draw(brilho)
    desenho.ellipse(
        [-cena.width // 3, -cena.height // 2, cena.width, cena.height],
        fill=42,
    )
    brilho = brilho.filter(ImageFilter.GaussianBlur(90))
    cena.paste(Image.new("RGB", cena.size, (255, 252, 235)), (0, 0), brilho)
    return cena.filter(ImageFilter.GaussianBlur(0.4))


def cursinho_jpg(destino: Path) -> None:
    largura, altura = 1240, 1240
    papel = _papel(largura, altura, (253, 251, 246))
    d = ImageDraw.Draw(papel)
    titulo = ImageFont.truetype(SANS_BOLD, 46)
    negrito = ImageFont.truetype(SANS_BOLD, 34)
    texto = ImageFont.truetype(SANS, 32)
    miudo = ImageFont.truetype(SANS, 24)

    d.rectangle([0, 0, largura, 150], fill=(196, 30, 58))
    d.text((60, 42), CURSINHO.upper(), font=titulo, fill=(255, 255, 255))
    d.text((60, 200), "CRONOGRAMA — TURMA ENAMED 2026", font=negrito, fill=(30, 30, 30))
    d.text((60, 250), "Unidade Centro — sala 4", font=miudo, fill=(90, 90, 90))

    y = 340
    for dia, horario, conteudo in [
        ("SÁBADO", "14:00 às 18:00", "Aula ao vivo (2 blocos)"),
        ("DOMINGO", "10:00 às 12:00", "Revisão guiada + questões"),
    ]:
        d.rectangle([60, y, largura - 60, y + 190], outline=(150, 150, 150), width=3)
        d.text((85, y + 25), dia, font=negrito, fill=(196, 30, 58))
        d.text((85, y + 80), horario, font=texto, fill=(30, 30, 30))
        d.text((85, y + 130), conteudo, font=miudo, fill=(90, 90, 90))
        y += 230

    d.line([60, y + 20, largura - 60, y + 20], fill=(200, 200, 200), width=2)
    d.text((60, y + 60), "Vigência: 05/09/2026 a 15/11/2026", font=texto, fill=(30, 30, 30))
    d.text(
        (60, y + 120),
        "Na semana da prova não há aula: 16/11 a 22/11.",
        font=miudo,
        fill=(90, 90, 90),
    )
    d.text(
        (60, altura - 90),
        "Exemplo fictício — projeto mentor-AI",
        font=miudo,
        fill=(160, 160, 160),
    )

    foto = _fotografar(papel, (62, 70, 78), giro=-1.6)
    foto.save(destino, "JPEG", quality=82, optimize=True)


PLANTOES_NOVEMBRO = [
    ("04/11", "qua", "19:00 às 07:00", "PS adulto"),
    ("08/11", "dom", "07:00 às 19:00", "PS adulto"),
    ("13/11", "sex", "19:00 às 07:00", "PS pediátrico"),
    ("17/11", "ter", "19:00 às 07:00", "PS adulto"),
]


def mural_png(destino: Path) -> None:
    largura, altura = 1300, 830
    papel = _papel(largura, altura, (250, 250, 247))
    d = ImageDraw.Draw(papel)
    titulo = ImageFont.truetype(SANS_BOLD, 40)
    negrito = ImageFont.truetype(SANS_BOLD, 30)
    texto = ImageFont.truetype(SANS, 30)
    miudo = ImageFont.truetype(SANS, 22)

    d.text((60, 50), "ESCALA DE PLANTÕES — NOVEMBRO/2026", font=titulo, fill=(25, 25, 25))
    d.text((60, 105), f"{HOSPITAL} — internato 6º ano", font=miudo, fill=(100, 100, 100))
    d.text((60, 140), f"{ALUNA}", font=miudo, fill=(100, 100, 100))

    y = 210
    colunas = [70, 260, 430, 780]
    for coluna, cabecalho in zip(colunas, ["DATA", "DIA", "HORÁRIO", "SETOR"], strict=True):
        d.text((coluna, y), cabecalho, font=negrito, fill=(25, 25, 25))
    y += 50
    d.line([60, y, largura - 60, y], fill=(120, 120, 120), width=3)
    y += 20

    for data, dia, horario, setor in PLANTOES_NOVEMBRO:
        for coluna, valor in zip(colunas, [data, dia, horario, setor], strict=True):
            d.text((coluna, y), valor, font=texto, fill=(25, 25, 25))
        y += 62
        d.line([60, y - 12, largura - 60, y - 12], fill=(220, 220, 220), width=1)

    y += 30
    d.text((60, y), "Escala suspensa de 19/11 a 23/11 (ENAMED).", font=texto, fill=(170, 20, 20))
    d.text(
        (60, altura - 80),
        "Exemplo fictício — projeto mentor-AI",
        font=miudo,
        fill=(165, 165, 165),
    )

    foto = _fotografar(papel, (108, 112, 104), giro=1.2)
    foto.save(destino, "PNG", optimize=True)


# ---------------------------------------------------------------------- main


def main() -> None:
    grade_pdf(AQUI / "grade-internato-2026-2.pdf")
    escala_xlsx(AQUI / "escala-plantoes-outubro-2026.xlsx")
    rotina_docx(AQUI / "rotina-academia-e-trabalho.docx")
    cursinho_jpg(AQUI / "cursinho-cronograma-foto.jpg")
    mural_png(AQUI / "escala-mural-novembro-foto.png")

    recalc = Path("/mnt/skills/public/xlsx/scripts/recalc.py")
    if recalc.exists():  # calcula a coluna de horas e grava o valor no arquivo
        subprocess.run(
            ["python3", str(recalc), str(AQUI / "escala-plantoes-outubro-2026.xlsx")],
            check=False,
        )

    for arquivo in sorted(AQUI.iterdir()):
        if arquivo.suffix != ".py":
            print(f"{arquivo.name:42} {arquivo.stat().st_size / 1024:7.1f} KB")


if __name__ == "__main__":
    main()
