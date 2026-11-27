"""Texto de .docx e .xlsx para mandar ao modelo.

O modelo lê PDF e imagem direto; documento do Office, não. Em vez de subir uma
dependência de escritório inteira, tiramos daqui o texto: o arquivo é um zip de
XML, e o que interessa é o texto corrido e as células.

O arquivo vem do aluno, então é dado hostil até prova em contrário: o zip é
aberto com teto de entradas e de bytes descompactados, e o XML é varrido por
expressão regular — nada de parser com DTD, que é por onde entra bomba de
entidade.
"""

from __future__ import annotations

import re
import zipfile
from datetime import datetime, timedelta
from io import BytesIO

#: Tetos contra zip-bomb. Um horário de faculdade não chega perto disso.
MAX_ENTRIES = 512
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
#: O que sobra depois disso não é horário, é ruído — e custa token.
MAX_CHARS = 40_000

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
OFFICE_TYPES = frozenset({DOCX_TYPE, XLSX_TYPE})

#: Formatos de número embutidos que são data ou hora (ECMA-376, parte 1, 18.8.30).
BUILTIN_DATE_FORMATS = frozenset({14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47})
#: O dia 0 do Excel, já com o 29/02/1900 que nunca existiu descontado.
EXCEL_EPOCH = datetime(1899, 12, 30)

_TAG = re.compile(r"<[^>]+>")
_ENTITY = re.compile(r"&(#x?[0-9A-Fa-f]+|amp|lt|gt|quot|apos);")


class OfficeError(ValueError):
    """O arquivo não abre como documento do Office."""


def _unescape(texto: str) -> str:
    simples = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}

    def troca(m: re.Match[str]) -> str:
        bruto = m.group(1)
        if bruto in simples:
            return simples[bruto]
        try:
            ponto = int(bruto[2:], 16) if bruto[1] in "xX" else int(bruto[1:])
        except ValueError:  # pragma: no cover - entidade malformada
            return m.group(0)
        return chr(ponto) if 0 < ponto < 0x110000 else ""

    return _ENTITY.sub(troca, texto)


def _sem_marcacao(xml: str) -> str:
    return _unescape(_TAG.sub("", xml))


def _abrir(content: bytes) -> zipfile.ZipFile:
    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile as erro:
        raise OfficeError("o arquivo não é um documento do Office válido") from erro
    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise OfficeError("documento com entradas demais")
    if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
        raise OfficeError("documento grande demais depois de descompactar")
    return zf


def _ler(zf: zipfile.ZipFile, nome: str) -> str:
    try:
        return zf.read(nome).decode("utf-8", errors="replace")
    except KeyError as erro:
        raise OfficeError(f"documento sem {nome}") from erro


def text_from_docx(content: bytes) -> str:
    """Parágrafos e células do Word, um por linha."""
    with _abrir(content) as zf:
        xml = _ler(zf, "word/document.xml")

    xml = re.sub(r"<w:tab\b[^>]*/>", "\t", xml)
    xml = re.sub(r"<w:br\b[^>]*/>", "\n", xml)
    # Fim de parágrafo e de célula viram quebra; o resto da marcação some.
    xml = re.sub(r"</w:(p|tr)>", "\n", xml)
    xml = re.sub(r"</w:tc>", "\t", xml)
    return _limpar(_sem_marcacao(xml))


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        xml = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
    except KeyError:
        return []
    return [_sem_marcacao(bloco) for bloco in re.findall(r"<si>(.*?)</si>", xml, re.DOTALL)]


def _date_styles(zf: zipfile.ZipFile) -> set[int]:
    """Índices de estilo cuja formatação é data ou hora.

    Sem isso, `03/10/2026` chega ao modelo como `46296` — e ele não tem como
    saber que aquilo era uma data.
    """
    try:
        xml = zf.read("xl/styles.xml").decode("utf-8", errors="replace")
    except KeyError:  # pragma: no cover - planilha sem estilos
        return set()

    personalizados: set[int] = set()
    for ident, codigo in re.findall(r'<numFmt[^>]*numFmtId="(\d+)"[^>]*formatCode="([^"]*)"', xml):
        limpo = re.sub(r'\[[^\]]*\]|"[^"]*"|\\.', "", _unescape(codigo))
        if any(c in limpo for c in "ymdhs"):
            personalizados.add(int(ident))

    bloco = re.search(r"<cellXfs[^>]*>(.*?)</cellXfs>", xml, re.DOTALL)
    if bloco is None:  # pragma: no cover - planilha sem cellXfs
        return set()

    estilos: set[int] = set()
    for indice, xf in enumerate(re.findall(r"<xf\b[^>]*/?>", bloco.group(1))):
        achado = re.search(r'numFmtId="(\d+)"', xf)
        if achado is None:
            continue
        ident = int(achado.group(1))
        if ident in BUILTIN_DATE_FORMATS or ident in personalizados:
            estilos.add(indice)
    return estilos


def _serial_para_texto(valor: str) -> str:
    try:
        numero = float(valor)
    except ValueError:  # pragma: no cover - célula de data sem número
        return valor
    quando = EXCEL_EPOCH + timedelta(days=numero)
    if numero < 1:
        return quando.strftime("%H:%M")
    if abs(numero - round(numero)) < 1e-6:
        return quando.strftime("%d/%m/%Y")
    return quando.strftime("%d/%m/%Y %H:%M")


def _celula(xml: str, textos: list[str], datas: set[int]) -> str:
    tipo = re.search(r'\bt="([^"]+)"', xml)
    estilo = re.search(r'\bs="(\d+)"', xml)
    valor = re.search(r"<v[^>]*>(.*?)</v>", xml, re.DOTALL)

    if tipo is not None and tipo.group(1) == "s":
        if valor is None:
            return ""
        indice = int(valor.group(1))
        return textos[indice] if 0 <= indice < len(textos) else ""
    if tipo is not None and tipo.group(1) == "inlineStr":
        bloco = re.search(r"<is>(.*?)</is>", xml, re.DOTALL)
        return _sem_marcacao(bloco.group(1)) if bloco else ""
    if valor is None:
        return ""

    bruto = _sem_marcacao(valor.group(1))
    if estilo is not None and int(estilo.group(1)) in datas:
        return _serial_para_texto(bruto)
    return bruto


def text_from_xlsx(content: bytes) -> str:
    """Cada aba vira um bloco; cada linha, uma linha de células separadas por tabulação."""
    with _abrir(content) as zf:
        textos = _shared_strings(zf)
        datas = _date_styles(zf)
        planilhas = sorted(
            nome
            for nome in zf.namelist()
            if nome.startswith("xl/worksheets/") and nome.endswith(".xml")
        )
        if not planilhas:
            raise OfficeError("planilha sem abas")

        partes: list[str] = []
        for nome in planilhas:
            xml = _ler(zf, nome)
            linhas: list[str] = []
            for linha in re.findall(r"<row\b.*?(?:/>|</row>)", xml, re.DOTALL):
                celulas = [
                    _celula(c, textos, datas)
                    for c in re.findall(r"<c\b.*?(?:/>|</c>)", linha, re.DOTALL)
                ]
                if any(celula.strip() for celula in celulas):
                    linhas.append("\t".join(celulas).rstrip())
            if linhas:
                partes.append("\n".join(linhas))

    return _limpar("\n\n".join(partes))


def _limpar(texto: str) -> str:
    texto = texto.replace("\r\n", "\n").replace("\xa0", " ")
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return texto[:MAX_CHARS]


def text_from_office(content: bytes, content_type: str) -> str:
    if content_type == DOCX_TYPE:
        texto = text_from_docx(content)
    elif content_type == XLSX_TYPE:
        texto = text_from_xlsx(content)
    else:  # pragma: no cover - chamado só para os dois tipos acima
        raise OfficeError(f"{content_type} não é documento do Office")
    if not texto:
        raise OfficeError("documento sem texto legível")
    return texto
