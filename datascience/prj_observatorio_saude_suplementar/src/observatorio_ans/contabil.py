"""Demonstrações contábeis (DIOPS): leitura, padronização, sinais e janelas de tempo.

Fluxo:
    bronze (zip da ANS) -> prata (contas de interesse, CSV.gz por trimestre)
    -> conceitos por operadora e trimestre (sinais normalizados)
    -> janelas: acumulado no ano, trimestre isolado e últimos 12 meses.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from .fontes import ClienteANS
from .plano_contas import (
    CONCEITOS_FLUXO_TODOS,
    CONCEITOS_SALDO,
    TOTAIS_DE_CLASSE,
    contas_de_interesse,
    descricoes_por_conta,
    eh_redutora,
    resolver_conceitos,
)
from .util import (
    inspecionar_csv,
    log,
    mapear_colunas,
    normalizar_coluna,
    normalizar_conta,
    normalizar_reg_ans,
    parse_valor_br,
    periodo,
)

ALIASES_CONTABIL = {
    "DATA": ["DATA", "DT_REFERENCIA", "DATA_REFERENCIA"],
    "REG_ANS": ["REG_ANS", "REGISTRO_ANS", "REGISTRO_OPERADORA", "CD_OPERADORA"],
    "CD_CONTA_CONTABIL": ["CD_CONTA_CONTABIL", "CD_CONTA", "CONTA_CONTABIL", "CONTA"],
    "DESCRICAO": ["DESCRICAO", "DS_CONTA", "DESCRICAO_CONTA", "NM_CONTA"],
    "VL_SALDO_INICIAL": ["VL_SALDO_INICIAL", "SALDO_INICIAL"],
    "VL_SALDO_FINAL": ["VL_SALDO_FINAL", "SALDO_FINAL", "VL_SALDO"],
}
_PADRAO_ARQUIVO = re.compile(r"([1-4])T(\d{4})", re.IGNORECASE)


# ============================================================================ descoberta e download


def listar_trimestres(
    cliente: ClienteANS, ano_inicio: int, ano_fim: int | None = None
) -> list[tuple[int, int, str]]:
    """Lista os arquivos trimestrais disponíveis no portal: [(ano, tri, url), ...]."""
    raiz = cliente.listar("demonstracoes_contabeis/")
    anos = sorted(
        int(e.nome)
        for e in raiz
        if e.diretorio
        and e.nome.isdigit()
        and int(e.nome) >= ano_inicio
        and (ano_fim is None or int(e.nome) <= ano_fim)
    )
    encontrados: dict[tuple[int, int], str] = {}
    for ano in anos:
        for entrada in cliente.listar(f"demonstracoes_contabeis/{ano}/"):
            if entrada.diretorio or not entrada.nome.lower().endswith(".zip"):
                continue
            m = _PADRAO_ARQUIVO.search(entrada.nome)
            if m and int(m.group(2)) == ano:
                encontrados[(ano, int(m.group(1)))] = entrada.url
            else:
                log.warning(
                    "Arquivo ignorado (nome fora do padrão nTAAAA.zip): %s/%s", ano, entrada.nome
                )
    return [(a, t, u) for (a, t), u in sorted(encontrados.items())]


def baixar_trimestres(
    cliente: ClienteANS,
    dir_bronze: Path,
    ano_inicio: int,
    ano_fim: int | None = None,
    forcar: bool = False,
) -> list[tuple[int, int, Path]]:
    arquivos = []
    for ano, tri, url in listar_trimestres(cliente, ano_inicio, ano_fim):
        destino = dir_bronze / "demonstracoes_contabeis" / str(ano) / f"{tri}T{ano}.zip"
        arquivos.append((ano, tri, cliente.baixar(url, destino, forcar=forcar)))
    log.info("Demonstrações contábeis: %d trimestres disponíveis", len(arquivos))
    return arquivos


# ============================================================================ leitura (bronze -> prata)


def _trimestre_da_data(valor: str) -> tuple[int, int] | None:
    valor = (valor or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2}).*", valor) or None
    if m:
        ano, mes = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4}).*", valor)
        if not m:
            return None
        ano, mes = int(m.group(3)), int(m.group(2))
    return ano, (mes - 1) // 3 + 1


def _codigos_em_largura_fixa(conta: pd.Series) -> bool:
    """True se os códigos vierem preenchidos com zeros à direita (ex.: 310000000 em vez de 31).

    No formato hierárquico, os grupos de 2 dígitos (31, 41...) aparecem como linhas próprias.
    """
    conta = conta[conta != ""]
    if conta.empty:
        return False
    tamanhos = conta.str.len()
    return bool(tamanhos.nunique() == 1 and tamanhos.iloc[0] >= 6 and not (tamanhos <= 2).any())


def ler_trimestre(
    caminho_zip: Path, ano: int | None = None, tri: int | None = None
) -> tuple[pd.DataFrame, dict]:
    """Lê o CSV de um zip trimestral e devolve as contas de interesse já tipadas.

    Colunas de saída: reg_ans, conta, descricao, saldo_inicial, saldo_final.
    """
    caminho_zip = Path(caminho_zip)
    if ano is None or tri is None:
        m = _PADRAO_ARQUIVO.search(caminho_zip.name)
        if not m:
            raise ValueError(f"Não foi possível inferir o trimestre de {caminho_zip.name}")
        tri, ano = int(m.group(1)), int(m.group(2))

    info: dict = {"arquivo": caminho_zip.name, "periodo": periodo(ano, tri), "avisos": []}
    partes: list[pd.DataFrame] = []
    linhas_lidas = 0
    with zipfile.ZipFile(caminho_zip) as zf:
        membros = [m for m in zf.namelist() if m.lower().endswith((".csv", ".txt"))]
        if not membros:
            raise ValueError(f"Nenhum CSV dentro de {caminho_zip}")
        for membro in membros:
            encoding, sep, colunas = inspecionar_csv(lambda m=membro: zf.open(m))
            mapa = mapear_colunas(colunas, ALIASES_CONTABIL)
            faltando = [
                c for c in ("REG_ANS", "CD_CONTA_CONTABIL", "VL_SALDO_FINAL") if c not in mapa
            ]
            if faltando:
                raise ValueError(
                    f"{caminho_zip.name}/{membro}: colunas obrigatórias ausentes {faltando}. "
                    f"Colunas encontradas: {colunas}"
                )
            info.update({"encoding": encoding, "separador": sep, "colunas": colunas})
            if "VL_SALDO_INICIAL" not in mapa:
                info["avisos"].append("arquivo sem VL_SALDO_INICIAL")
            with zf.open(membro) as f:
                leitor = pd.read_csv(
                    f,
                    sep=sep,
                    dtype=str,
                    encoding=encoding,
                    encoding_errors="replace",
                    keep_default_na=False,
                    chunksize=400_000,
                    quotechar='"',
                )
                for bloco in leitor:
                    bloco.columns = [normalizar_coluna(c) for c in bloco.columns]
                    renomear = {normalizar_coluna(orig): canon for canon, orig in mapa.items()}
                    bloco = bloco.rename(columns=renomear)
                    linhas_lidas += len(bloco)
                    conta = normalizar_conta(bloco["CD_CONTA_CONTABIL"]).fillna("")
                    if "codigos_largura_fixa" not in info:
                        info["codigos_largura_fixa"] = _codigos_em_largura_fixa(conta)
                        if info["codigos_largura_fixa"]:
                            info["avisos"].append(
                                "códigos de conta em largura fixa: zeros à direita removidos"
                            )
                    if info["codigos_largura_fixa"]:
                        conta = conta.str.rstrip("0")
                    manter = contas_de_interesse(conta) & (conta != "")
                    if "DATA" in bloco and "formato_data" not in info:
                        amostra = next((v for v in bloco["DATA"] if v), "")
                        info["data_exemplo"] = amostra
                        info["formato_data"] = (
                            "AAAA-MM-DD" if re.match(r"\d{4}-", amostra) else "DD/MM/AAAA"
                        )
                        achado = _trimestre_da_data(amostra)
                        if achado and achado != (ano, tri):
                            info["avisos"].append(
                                f"DATA {amostra!r} aponta {periodo(*achado)}; usado o período do arquivo"
                            )
                    sub = pd.DataFrame(
                        {
                            "reg_ans": normalizar_reg_ans(bloco.loc[manter, "REG_ANS"]),
                            "conta": conta[manter],
                            "descricao": bloco.loc[manter, "DESCRICAO"]
                            if "DESCRICAO" in bloco
                            else "",
                            "saldo_inicial": parse_valor_br(bloco.loc[manter, "VL_SALDO_INICIAL"])
                            if "VL_SALDO_INICIAL" in bloco
                            else np.nan,
                            "saldo_final": parse_valor_br(bloco.loc[manter, "VL_SALDO_FINAL"]),
                        }
                    )
                    partes.append(sub)

    df = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=["reg_ans", "conta", "descricao", "saldo_inicial", "saldo_final"])
    )
    df = df.dropna(subset=["reg_ans"])
    antes = len(df)
    df = df.drop_duplicates(subset=["reg_ans", "conta"], keep="last").reset_index(drop=True)
    info.update(
        {
            "linhas_lidas": linhas_lidas,
            "linhas_mantidas": len(df),
            "duplicatas_removidas": antes - len(df),
            "operadoras": int(df["reg_ans"].nunique()),
        }
    )
    if info["duplicatas_removidas"]:
        info["avisos"].append(
            f"{info['duplicatas_removidas']} linhas duplicadas (operadora+conta) removidas"
        )
    return df, info


def caminho_prata(dir_prata: Path, ano: int, tri: int) -> Path:
    return dir_prata / "contabil" / f"{periodo(ano, tri)}.csv.gz"


def bronze_para_prata(arquivos: list[tuple[int, int, Path]], dir_prata: Path) -> dict[str, dict]:
    """Converte cada zip trimestral em CSV.gz padronizado (reaproveita se já estiver atualizado)."""
    relatorio = {}
    for ano, tri, zip_path in arquivos:
        destino = caminho_prata(dir_prata, ano, tri)
        info_path = destino.with_suffix(".info.json")
        if (
            destino.exists()
            and info_path.exists()
            and destino.stat().st_mtime >= Path(zip_path).stat().st_mtime
        ):
            relatorio[periodo(ano, tri)] = json.loads(info_path.read_text(encoding="utf-8"))
            continue
        log.info("Lendo %s", Path(zip_path).name)
        df, info = ler_trimestre(zip_path, ano, tri)
        destino.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(destino, index=False, compression="gzip")
        info_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        relatorio[periodo(ano, tri)] = info
    return relatorio


def ler_prata(dir_prata: Path, ano: int, tri: int) -> pd.DataFrame:
    return pd.read_csv(
        caminho_prata(dir_prata, ano, tri),
        dtype={"reg_ans": str, "conta": str, "descricao": str},
        keep_default_na=False,
        na_values={"saldo_inicial": [""], "saldo_final": [""]},
    )


# ============================================================================ sinais e conceitos


def _mediana_nao_nula(valores: pd.Series) -> float:
    v = valores[valores.abs() > 0]
    return float(v.median()) if len(v) else np.nan


def normalizar_sinais(df: pd.DataFrame, descricoes: dict[str, str]) -> tuple[pd.DataFrame, dict]:
    """Garante a convenção: receitas, despesas, ativo e passivo positivos; deduções negativas.

    A ANS não documenta a convenção de sinal dos saldos. Em vez de supor, o sinal de cada classe
    é inferido pela mediana da conta-âncoras entre todas as operadoras do trimestre (ex.: se a
    mediana das contraprestações é negativa, a classe 3 está com sinal credor negativo).
    """
    df = df.copy()
    info: dict = {"classes_invertidas": [], "redutoras_invertidas": []}
    ancoras = {"1": ["1", "12"], "2": ["2", "21"], "3": ["31", "3"], "4": ["41", "4"]}
    inverter: dict[str, bool] = {}
    for classe, contas in ancoras.items():
        mediana = np.nan
        for conta in contas:
            mediana = _mediana_nao_nula(df.loc[df["conta"] == conta, "saldo_final"])
            if not np.isnan(mediana):
                break
        inverter[classe] = bool(mediana < 0) if not np.isnan(mediana) else False
    inverter["6"] = inverter[
        "4"
    ]  # impostos sobre o lucro têm a mesma natureza (devedora) das despesas

    colunas = ["saldo_inicial", "saldo_final"]
    for classe, inv in inverter.items():
        if inv:
            mascara = df["conta"].str.startswith(classe)
            df.loc[mascara, colunas] = -df.loc[mascara, colunas]
            info["classes_invertidas"].append(classe)

    # Deduções da receita (ex.: tributos diretos): devem ficar negativas
    for conta in sorted(c for c in df["conta"].unique() if len(c) == 2 and c.startswith("3")):
        if eh_redutora(descricoes.get(conta, "")):
            mediana = _mediana_nao_nula(df.loc[df["conta"] == conta, "saldo_final"])
            if not np.isnan(mediana) and mediana > 0:
                mascara = df["conta"].str.startswith(conta)
                df.loc[mascara, colunas] = -df.loc[mascara, colunas]
                info["redutoras_invertidas"].append(conta)
    return df, info


def conceitos_do_trimestre(df: pd.DataFrame, ano: int, tri: int) -> tuple[pd.DataFrame, dict]:
    """Resolve os conceitos e soma as contas por operadora. Saída em formato longo."""
    descricoes = descricoes_por_conta(df)
    df, info_sinais = normalizar_sinais(df, descricoes)
    codigos = set(df["conta"].unique())
    resolucao = resolver_conceitos(codigos, descricoes)

    partes = []
    for conceito, contas in resolucao.contas.items():
        sub = (
            df[df["conta"].isin(contas)]
            .groupby("reg_ans")[["saldo_inicial", "saldo_final"]]
            .sum(min_count=1)
        )
        partes.append(sub.assign(conceito=conceito).reset_index())
    for conceito, classe in TOTAIS_DE_CLASSE.items():
        grupos = [c for c in codigos if len(c) == 2 and c.startswith(classe)]
        sub = (
            df[df["conta"].isin(grupos)]
            .groupby("reg_ans")[["saldo_inicial", "saldo_final"]]
            .sum(min_count=1)
        )
        partes.append(sub.assign(conceito=conceito).reset_index())

    longo = (
        pd.concat(partes, ignore_index=True)
        if partes
        else pd.DataFrame(columns=["reg_ans", "saldo_inicial", "saldo_final", "conceito"])
    )
    longo["ano"] = ano
    longo["tri"] = tri

    # Validação da convenção de sinais: soma dos grupos x linha da classe (quando existe)
    validacao = {}
    for conceito, classe in TOTAIS_DE_CLASSE.items():
        linha_classe = df[df["conta"] == classe].set_index("reg_ans")["saldo_final"]
        soma = longo[longo["conceito"] == conceito].set_index("reg_ans")["saldo_final"]
        comum = linha_classe.index.intersection(soma.index)
        if len(comum):
            dif = (linha_classe[comum] - soma[comum]).abs()
            tolerancia = np.maximum(1.0, 0.01 * linha_classe[comum].abs())
            validacao[f"classe_{classe}_confere"] = round(float((dif <= tolerancia).mean()), 4)
    info = {"sinais": info_sinais, "resolucao": resolucao.como_dict(), "validacao": validacao}
    return longo[["reg_ans", "ano", "tri", "conceito", "saldo_inicial", "saldo_final"]], info


def montar_conceitos(dir_prata: Path, periodos: list[tuple[int, int]]) -> tuple[pd.DataFrame, dict]:
    partes, relatorio = [], {}
    for ano, tri in periodos:
        df = ler_prata(dir_prata, ano, tri)
        longo, info = conceitos_do_trimestre(df, ano, tri)
        partes.append(longo)
        relatorio[periodo(ano, tri)] = info
    conceitos = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    return conceitos, relatorio


# ============================================================================ acumulação e janelas


def detectar_modo_acumulacao(conceitos: pd.DataFrame) -> dict[int, dict]:
    """Descobre, ano a ano, se os saldos de resultado são acumulados no ano ou do trimestre.

    Em balancetes acumulados, o saldo inicial do trimestre t é igual ao saldo final de t-1.
    """
    base = conceitos[
        conceitos["conceito"].isin(["receita_contraprestacoes", "despesa_assistencial"])
    ]
    modos: dict[int, dict] = {}
    for ano in sorted(base["ano"].unique()):
        anual = base[base["ano"] == ano]
        atual = anual[anual["tri"] > 1][["reg_ans", "conceito", "tri", "saldo_inicial"]]
        anterior = anual[["reg_ans", "conceito", "tri", "saldo_final"]].assign(
            tri=lambda d: d["tri"] + 1
        )
        pares = atual.merge(anterior, on=["reg_ans", "conceito", "tri"])
        pares = pares[(pares["saldo_final"].abs() > 1000) & pares["saldo_inicial"].notna()]
        n = len(pares)
        if n < 10:
            modos[int(ano)] = {
                "modo": "acumulado",
                "evidencia": "assumido (poucos pares para testar)",
                "pares": n,
            }
            continue
        igual = (pares["saldo_inicial"] - pares["saldo_final"]).abs() <= np.maximum(
            1.0, 0.005 * pares["saldo_final"].abs()
        )
        zerado = pares["saldo_inicial"].abs() <= 1.0
        if igual.mean() >= 0.6:
            modo, evidencia = (
                "acumulado",
                f"{igual.mean():.0%} dos saldos iniciais = saldo final anterior",
            )
        elif zerado.mean() >= 0.6:
            modo, evidencia = "trimestral", f"{zerado.mean():.0%} dos saldos iniciais zerados"
        else:
            modo, evidencia = "acumulado", "indeterminado; assumido acumulado"
        modos[int(ano)] = {"modo": modo, "evidencia": evidencia, "pares": n}
        # Em balancetes acumulados, a receita do 4º trimestre deve superar a do 3º
        rc = anual[anual["conceito"] == "receita_contraprestacoes"].pivot_table(
            index="reg_ans", columns="tri", values="saldo_final", aggfunc="sum"
        )
        if modo == "acumulado" and {3, 4} <= set(rc.columns):
            razao = (rc[4] / rc[3].where(rc[3] > 0)).dropna()
            if len(razao) >= 10 and razao.median() < 0.5:
                modos[int(ano)]["alerta"] = (
                    "4º trimestre com receita acumulada menor que a do 3º (encerramento do exercício?)"
                )
    return modos


def calcular_janelas(conceitos: pd.DataFrame, modos: dict[int, dict]) -> pd.DataFrame:
    """Gera uma linha por operadora, período e janela (acumulado_ano, trimestre, 12_meses)."""
    chaves = ["reg_ans", "ano", "tri"]
    final = conceitos.pivot_table(
        index=chaves, columns="conceito", values="saldo_final", aggfunc="sum"
    )
    inicial = conceitos.pivot_table(
        index=chaves, columns="conceito", values="saldo_inicial", aggfunc="sum"
    )
    final.columns.name = None
    saldos = [c for c in CONCEITOS_SALDO if c in final.columns]
    for c in CONCEITOS_FLUXO_TODOS + CONCEITOS_SALDO:
        if c not in final.columns:
            final[c] = np.nan
    fluxos = CONCEITOS_FLUXO_TODOS
    # Operadora presente no trimestre sem uma conta específica = valor zero naquele conceito
    final[fluxos] = final[fluxos].fillna(0.0)

    # ---------------------------------------------------------------- acumulado no ano (YTD)
    ytd = final[fluxos].copy()
    anos_trimestrais = [a for a, m in modos.items() if m["modo"] == "trimestral"]
    if anos_trimestrais:
        inicial = inicial.reindex(columns=fluxos).reindex(final.index)
        fluxo_tri = final[fluxos] - inicial.fillna(0.0)
        mascara = fluxo_tri.index.get_level_values("ano").isin(anos_trimestrais)
        acumulado = fluxo_tri[mascara].groupby(level=["reg_ans", "ano"]).cumsum()
        # Só é válido se nenhum trimestre anterior estiver faltando
        contagem = fluxo_tri[mascara].groupby(level=["reg_ans", "ano"]).cumcount() + 1
        tri_idx = fluxo_tri[mascara].index.get_level_values("tri")
        lacuna = np.asarray(contagem.values != np.asarray(tri_idx))
        acumulado.loc[lacuna, :] = np.nan
        ytd.loc[mascara, fluxos] = acumulado

    base = ytd.reset_index()
    # ---------------------------------------------------------------- trimestre isolado
    anterior = base.assign(tri=base["tri"] + 1)
    junto = base.merge(anterior, on=chaves, how="left", suffixes=("", "__ant"))
    trimestre = junto[chaves].copy()
    for c in fluxos:
        trimestre[c] = np.where(junto["tri"] == 1, junto[c], junto[c] - junto[f"{c}__ant"])

    # ---------------------------------------------------------------- últimos 12 meses
    mesmo_tri_ano_ant = base.assign(ano=base["ano"] + 1)
    quarto_tri_ano_ant = (
        base[base["tri"] == 4].drop(columns="tri").assign(ano=lambda d: d["ano"] + 1)
    )
    j12 = base.merge(mesmo_tri_ano_ant, on=chaves, how="left", suffixes=("", "__a1"))
    j12 = j12.merge(
        quarto_tri_ano_ant.rename(columns={c: f"{c}__q4" for c in fluxos}),
        on=["reg_ans", "ano"],
        how="left",
    )
    doze = j12[chaves].copy()
    for c in fluxos:
        doze[c] = np.where(j12["tri"] == 4, j12[c], j12[c] + j12[f"{c}__q4"] - j12[f"{c}__a1"])

    saldos_df = final[saldos].reset_index() if saldos else final.reset_index()[chaves]
    janelas = []
    for nome, tabela in (("acumulado_ano", base), ("trimestre", trimestre), ("12_meses", doze)):
        t = tabela.merge(saldos_df, on=chaves, how="left")
        t.insert(3, "janela", nome)
        janelas.append(t)
    resultado = pd.concat(janelas, ignore_index=True)
    for c in CONCEITOS_SALDO:
        if c not in resultado:
            resultado[c] = np.nan
    resultado["periodo"] = (
        resultado["ano"].astype(int).astype(str) + "T" + resultado["tri"].astype(int).astype(str)
    )
    return resultado
