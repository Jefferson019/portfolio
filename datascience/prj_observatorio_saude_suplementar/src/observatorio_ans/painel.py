"""Gera o painel estático em site/: um único index.html com os dados embutidos + CSVs para download.

O HTML não depende de servidor nem de bibliotecas externas: abre direto do disco, no GitHub Pages
ou em qualquer hospedagem estática.
"""

from __future__ import annotations

import json
import math
import shutil
import time
from importlib import resources

import pandas as pd

from .config import JANELAS, SEGMENTOS
from .util import log

PERIODOS_OPERADORAS = 5  # trimestres com detalhe por operadora (o mais recente + 4 anteriores)

COLUNAS_MERCADO = [
    "n_operadoras",
    "receita_contraprestacoes",
    "contraprestacoes_liquidas",
    "despesa_assistencial",
    "despesa_administrativa",
    "despesa_comercializacao",
    "outras_receitas_operacionais",
    "outras_despesas_operacionais",
    "tributos_diretos",
    "resultado_operacional",
    "resultado_financeiro",
    "resultado_patrimonial",
    "resultado_liquido",
    "receita_total",
    "aplicacoes_financeiras",
    "patrimonio_liquido",
    "provisoes_tecnicas",
    "beneficiarios",
    "sinistralidade",
    "indice_despesa_administrativa",
    "indice_despesa_comercializacao",
    "indice_combinado",
    "margem_operacional",
    "margem_liquida",
    "roe",
    "pct_resultado_liquido_positivo",
    "pct_resultado_operacional_negativo",
    "sinistralidade_p25",
    "sinistralidade_mediana",
    "sinistralidade_p75",
    "hhi",
    "cr5",
    "cr10",
]
COLUNAS_OPERADORA = [
    "receita_contraprestacoes",
    "receita_base",
    "despesa_assistencial",
    "resultado_operacional",
    "resultado_liquido",
    "receita_total",
    "beneficiarios",
    "sinistralidade",
    "indice_despesa_administrativa",
    "indice_despesa_comercializacao",
    "indice_combinado",
    "margem_operacional",
    "margem_liquida",
    "liquidez_corrente",
    "roe",
    "receita_por_beneficiario_mes",
    "patrimonio_liquido",
]
INTEIRAS = {
    "receita_contraprestacoes",
    "despesa_assistencial",
    "despesa_administrativa",
    "despesa_comercializacao",
    "outras_receitas_operacionais",
    "outras_despesas_operacionais",
    "tributos_diretos",
    "resultado_operacional",
    "resultado_financeiro",
    "resultado_patrimonial",
    "resultado_liquido",
    "receita_total",
    "aplicacoes_financeiras",
    "patrimonio_liquido",
    "provisoes_tecnicas",
    "beneficiarios",
    "receita_por_beneficiario_mes",
    "n_operadoras",
    "contraprestacoes_liquidas",
    "receita_base",
}
TEXTO = {"periodo", "janela", "recorte", "valor"}


def _num(v, casas: int):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, casas) if casas else int(round(f))


def _casas(colunas: list[str]) -> dict[str, int]:
    casas = {}
    for c in colunas:
        if c in INTEIRAS:
            casas[c] = 0
        elif c == "hhi":
            casas[c] = 1
        elif c not in TEXTO:
            casas[c] = 4
    return casas


def _tabela(df: pd.DataFrame, colunas: list[str], casas: dict[str, int]) -> dict:
    """Formato colunar compacto: {"cols": [...], "rows": [[...], ...]}."""
    linhas = []
    for registro in df[colunas].itertuples(index=False):
        linha = []
        for c, v in zip(colunas, registro, strict=True):
            if c in casas:
                linha.append(_num(v, casas[c]))
            elif v is None or (not isinstance(v, str) and pd.isna(v)):
                linha.append(None)
            else:
                if hasattr(v, "item"):  # escalares do numpy (bool_, int64...) viram tipos nativos
                    v = v.item()
                linha.append(v if isinstance(v, (str, bool, int, float)) else str(v))
        linhas.append(linha)
    return {"cols": colunas, "rows": linhas}


def montar_payload(
    cfg,
    ops: pd.DataFrame,
    merc: pd.DataFrame,
    conc: pd.DataFrame,
    hist_op: pd.DataFrame,
    hist_uf: pd.DataFrame,
    meta: dict,
) -> dict:
    periodos = sorted(merc["periodo"].astype(str).unique())
    janela_painel = periodos[-cfg.trimestres_no_painel :]

    # ------------------------------------------------------------------ mercado
    recortes = merc["recorte"].isin(["setor", "segmento", "modalidade", "porte_mh"])
    m = merc[recortes & merc["periodo"].astype(str).isin(janela_painel)].copy()
    m["valor"] = m["valor"].astype(str)
    cols_m = ["periodo", "janela", "recorte", "valor"] + [c for c in COLUNAS_MERCADO if c in m]
    mercado = _tabela(m, cols_m, _casas(cols_m))

    # ------------------------------------------------------------------ operadoras
    recentes = periodos[-PERIODOS_OPERADORAS:]
    o = ops[
        ops["periodo"].isin(recentes) & ops["segmento"].isin(["medico_hospitalar", "odontologico"])
    ].copy()
    o = o[o["receita_contraprestacoes"].fillna(0) > 0]
    ultimo = o.sort_values(["ano", "tri"]).drop_duplicates("reg_ans", keep="last")
    cadastro = ultimo[
        ["reg_ans", "nome", "modalidade", "segmento", "uf", "porte", "situacao"]
    ].sort_values("reg_ans")
    cadastro = cadastro.fillna({"uf": "", "porte": "sem_informacao", "situacao": ""})
    indice = {r: i for i, r in enumerate(cadastro["reg_ans"])}
    o["op"] = o["reg_ans"].map(indice).astype(int)
    o["amostra"] = o["amostra_valida"].astype(bool) & ~o["sinistralidade_atipica"].astype(bool)
    cols_o = ["op", "periodo", "janela", "amostra"] + [c for c in COLUNAS_OPERADORA if c in o]
    casas_o = {c: n for c, n in _casas(cols_o).items() if c not in {"op", "amostra"}}
    operadoras = _tabela(o, cols_o, casas_o)
    operadoras["rows"] = [[int(r[0]), r[1], r[2], bool(r[3]), *r[4:]] for r in operadoras["rows"]]

    serie = ops[
        ops["reg_ans"].isin(indice.keys())
        & ops["periodo"].isin(janela_painel)
        & (ops["janela"] == "12_meses")
    ][["reg_ans", "periodo", "sinistralidade", "receita_contraprestacoes"]].copy()
    serie["op"] = serie["reg_ans"].map(indice).astype(int)
    series = _tabela(
        serie.dropna(subset=["sinistralidade"]),
        ["op", "periodo", "sinistralidade", "receita_contraprestacoes"],
        {"op": 0, "sinistralidade": 4, "receita_contraprestacoes": 0},
    )

    beneficiarios = _payload_beneficiarios(hist_op, hist_uf, cadastro)

    # ------------------------------------------------------------------ conciliação
    cols_c = [
        "periodo",
        "janela",
        "recorte",
        "valor_recorte",
        "indicador",
        "descricao",
        "valor_ans",
        "valor_calculado",
        "diferenca",
        "status",
        "fonte",
        "url",
        "tipo_tolerancia",
        "tolerancia",
    ]
    c = (
        conc[[x for x in cols_c if x in conc]].copy()
        if not conc.empty
        else pd.DataFrame(columns=cols_c)
    )
    conciliacao = _tabela(
        c, list(c.columns), {"valor_ans": 6, "valor_calculado": 6, "diferenca": 6, "tolerancia": 4}
    )

    autor = {k: str(v) for k, v in (cfg.autor or {}).items()}
    painel_cfg = cfg.painel or {}
    return {
        "meta": {
            **meta,
            "titulo": painel_cfg.get("titulo", "Observatório da Saúde Suplementar"),
            "subtitulo": painel_cfg.get("subtitulo", ""),
            "url_repositorio": painel_cfg.get("url_repositorio", ""),
            "autor": autor,
            "gerado_em": time.strftime("%d/%m/%Y"),
            "fonte_url": "https://dadosabertos.ans.gov.br/FTP/PDA/",
            "janelas": JANELAS,
            "segmentos": SEGMENTOS,
        },
        "periodos": janela_painel,
        "periodos_operadoras": recentes,
        "mercado": mercado,
        "cadastro": _tabela(cadastro, list(cadastro.columns), {}),
        "operadoras": operadoras,
        "series": series,
        "beneficiarios": beneficiarios,
        "conciliacao": conciliacao,
    }


def _payload_beneficiarios(
    hist_op: pd.DataFrame, hist_uf: pd.DataFrame, cadastro: pd.DataFrame
) -> dict | None:
    if hist_op is None or hist_op.empty:
        return None
    comps = sorted(hist_op["competencia"].astype(str).unique())
    ultima = comps[-1]
    anterior = f"{int(ultima[:4]) - 1}{ultima[4:]}"
    anterior = anterior if anterior in comps else None
    nomes = dict(zip(cadastro["reg_ans"], cadastro["nome"], strict=True))
    saida: dict = {"competencia": ultima, "competencia_anterior": anterior, "por_cobertura": {}}
    for cob in ("medico_hospitalar", "odontologico"):
        atual = hist_op[(hist_op["competencia"] == ultima) & (hist_op["cobertura"] == cob)]
        info: dict = {"total": _num(atual["beneficiarios"].sum(), 0)}
        if anterior:
            prev = hist_op[(hist_op["competencia"] == anterior) & (hist_op["cobertura"] == cob)]
            info["total_anterior"] = _num(prev["beneficiarios"].sum(), 0)
        info["contratacao"] = {
            k: _num(v, 0) for k, v in atual.groupby("contratacao")["beneficiarios"].sum().items()
        }
        uf = hist_uf[(hist_uf["competencia"] == ultima) & (hist_uf["cobertura"] == cob)]
        uf = uf[uf["uf"].astype(str).str.fullmatch(r"[A-Z]{2}") & (uf["uf"] != "XX")]
        por_uf = uf.groupby("uf")["beneficiarios"].sum().sort_values(ascending=False)
        info["uf"] = [[u, _num(v, 0)] for u, v in por_uf.items()]
        por_op = atual.groupby("reg_ans")["beneficiarios"].sum().sort_values(ascending=False)
        total = float(por_op.sum())
        info["hhi"] = _num(float((((por_op / total) * 100) ** 2).sum()), 1) if total > 0 else None
        info["top"] = [
            [nomes.get(r, f"Registro ANS {r}"), r, _num(v, 0)] for r, v in por_op.head(10).items()
        ]
        saida["por_cobertura"][cob] = info
    return saida


def gerar_painel(cfg, ops, merc, conc, hist_op, hist_uf, meta) -> None:
    payload = montar_payload(cfg, ops, merc, conc, hist_op, hist_uf, meta)
    modelo = (
        resources.files("observatorio_ans")
        .joinpath("templates/painel.html")
        .read_text(encoding="utf-8")
    )
    dados = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    dados = dados.replace("</", "<\\/")  # nada no JSON pode fechar a tag <script>
    html = modelo.replace("/*__DADOS__*/{}", dados).replace(
        "__TITULO__", _escapar(payload["meta"]["titulo"])
    )
    cfg.dir_site.mkdir(parents=True, exist_ok=True)
    (cfg.dir_site / "index.html").write_text(html, encoding="utf-8")

    # Arquivos para download: os mesmos números do painel
    pasta = cfg.dir_site / "dados"
    pasta.mkdir(parents=True, exist_ok=True)
    merc.to_csv(pasta / "mercado_indicadores.csv", index=False)
    ops[ops["periodo"] == meta["periodo_mais_recente"]].to_csv(
        pasta / "operadoras_ultimo_trimestre.csv", index=False
    )
    ops.to_csv(pasta / "operadoras_indicadores.csv.gz", index=False, compression="gzip")
    conc.to_csv(pasta / "conciliacao_ans.csv", index=False)
    qualidade = cfg.dir_ouro / "relatorio_qualidade.json"
    if qualidade.exists():
        shutil.copy(qualidade, pasta / "relatorio_qualidade.json")
    (cfg.dir_site / ".nojekyll").write_text("", encoding="utf-8")
    tamanho = (cfg.dir_site / "index.html").stat().st_size / 1e6
    log.info("Painel gerado: %s (%.1f MB)", cfg.dir_site / "index.html", tamanho)


def _escapar(texto: str) -> str:
    return (
        str(texto)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
