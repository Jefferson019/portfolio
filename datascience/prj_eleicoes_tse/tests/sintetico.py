"""Gera .zip no mesmo formato dos arquivos do TSE (CSV ';', aspas, Latin-1, um arquivo por UF + BR)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np

UFS = {
    "SP": [(71072, "SÃO PAULO"), (62910, "CAMPINAS")],
    "BA": [(38490, "SALVADOR"), (35173, "FEIRA DE SANTANA")],
    "ZZ": [(29539, "LISBOA")],
}
CANDIDATOS = {
    2018: [(17, "JAIR BOLSONARO", "PSL"), (13, "FERNANDO HADDAD", "PT"), (12, "CIRO GOMES", "PDT")],
    2022: [(13, "LULA", "PT"), (22, "JAIR BOLSONARO", "PL"), (15, "SIMONE TEBET", "MDB")],
}


def _csv(cabecalho: list[str], linhas: list[list]) -> bytes:
    txt = io.StringIO()
    txt.write(";".join(f'"{c}"' for c in cabecalho) + "\n")
    for linha in linhas:
        txt.write(";".join(f'"{v}"' for v in linha) + "\n")
    return txt.getvalue().encode("latin-1")


def _zip(destino: Path, arquivos: dict[str, bytes]) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, conteudo in arquivos.items():
            zf.writestr(nome, conteudo)


def gerar(raiz: Path, anos=(2018, 2022), semente: int = 7) -> None:
    rng = np.random.default_rng(semente)
    for ano in anos:
        cands = CANDIDATOS[ano]
        # ---- votação por candidato (inclui governador para checar o filtro de cargo)
        cab = ["DT_GERACAO", "ANO_ELEICAO", "CD_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA",
               "CD_CARGO", "DS_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO"]  # fmt: skip
        cab += (
            ["QT_VOTOS_NOMINAIS_VALIDOS", "QT_VOTOS_NOMINAIS"]
            if ano >= 2022
            else ["QT_VOTOS_NOMINAIS"]
        )
        cab_det = ["ANO_ELEICAO", "CD_ELEICAO", "NR_TURNO", "SG_UF", "CD_MUNICIPIO", "NM_MUNICIPIO", "NR_ZONA", "CD_CARGO",
                   "QT_APTOS", "QT_COMPARECIMENTO", "QT_ABSTENCOES", "QT_VOTOS_NOMINAIS", "QT_VOTOS_LEGENDA",
                   "QT_VOTOS_BRANCOS", "QT_VOTOS_NULOS"]  # fmt: skip
        if ano >= 2022:
            cab_det += ["QT_VOTOS_VALIDOS", "QT_TOTAL_VOTOS_NULOS"]
        votos_uf, det_uf, br = {}, {}, []
        for uf, municipios in UFS.items():
            linhas, linhas_det = [], []
            for cd, nome in municipios:
                for zona in (1, 2):
                    for turno in (1, 2):
                        disputando = cands if turno == 1 else cands[:2]
                        validos = 0
                        for i, (nr, nm, sg) in enumerate(disputando):
                            v = int(rng.integers(100, 1000))
                            validos += v
                            vals = [v, v] if ano >= 2022 else [v]
                            linha = [
                                "01/01/2023",
                                ano,
                                500 + turno,
                                turno,
                                uf,
                                cd,
                                nome,
                                zona,
                                1,
                                "Presidente",
                                ano * 100 + i,
                                nr,
                                nm,
                                sg,
                                *vals,
                            ]
                            linhas.append(linha)
                            br.append(linha)
                        linhas.append(
                            [
                                "01/01/2023",
                                ano,
                                600,
                                turno,
                                uf,
                                cd,
                                nome,
                                zona,
                                3,
                                "Governador",
                                999,
                                99,
                                "FULANO",
                                "XYZ",
                                *([5, 5] if ano >= 2022 else [5]),
                            ]
                        )
                        brancos, nulos = int(rng.integers(5, 50)), int(rng.integers(5, 80))
                        comp = validos + brancos + nulos
                        abst = int(rng.integers(50, 400))
                        det = [
                            ano,
                            500 + turno,
                            turno,
                            uf,
                            cd,
                            nome,
                            zona,
                            1,
                            comp + abst,
                            comp,
                            abst,
                            validos,
                            0,
                            brancos,
                            nulos,
                        ]
                        if ano >= 2022:
                            det += [validos, nulos]
                        linhas_det.append(det)
            votos_uf[f"votacao_candidato_munzona_{ano}_{uf}.csv"] = _csv(cab, linhas)
            det_uf[f"detalhe_votacao_munzona_{ano}_{uf}.csv"] = _csv(cab_det, linhas_det)
        # arquivo BR repete as linhas de presidente (os dados não podem ser contados duas vezes)
        votos_uf[f"votacao_candidato_munzona_{ano}_BR.csv"] = _csv(cab, br)
        votos_uf["leiame.pdf"] = b"%PDF"
        _zip(raiz / "votacao_candidato_munzona" / f"votacao_candidato_munzona_{ano}.zip", votos_uf)
        _zip(raiz / "detalhe_votacao_munzona" / f"detalhe_votacao_munzona_{ano}.zip", det_uf)

        # ---- candidaturas
        cab_c = ["ANO_ELEICAO", "NR_TURNO", "SG_UF", "CD_CARGO", "DS_CARGO", "SQ_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO",
                 "DS_GENERO", "DS_COR_RACA", "DS_GRAU_INSTRUCAO", "NR_IDADE_DATA_POSSE", "DS_SITUACAO_CANDIDATURA", "DS_SIT_TOT_TURNO"]  # fmt: skip
        linhas = []
        sq = 1
        for uf in ("SP", "BA"):
            for cargo, cd, n in (("DEPUTADO FEDERAL", 6, 40), ("GOVERNADOR", 3, 4)):
                for k in range(n):
                    genero = "FEMININO" if rng.random() < 0.33 else "MASCULINO"
                    cor = rng.choice(
                        ["BRANCA", "PARDA", "PRETA", "#NULO#"], p=[0.5, 0.35, 0.1, 0.05]
                    )
                    sit = (
                        "ELEITO POR QP"
                        if (cargo != "GOVERNADOR" and k < 8)
                        else ("ELEITO" if k == 0 else "NÃO ELEITO")
                    )
                    apto = "INAPTO" if k == n - 1 else "APTO"
                    linhas.append(
                        [
                            ano,
                            1,
                            uf,
                            cd,
                            cargo,
                            sq,
                            f"CAND {sq}",
                            "ABC",
                            genero,
                            cor,
                            "SUPERIOR COMPLETO",
                            int(rng.integers(25, 70)),
                            apto,
                            sit,
                        ]
                    )
                    sq += 1
        for i, (_nr, nm, sg) in enumerate(CANDIDATOS[ano]):
            for turno in (1, 2) if i < 2 else (1,):
                sit = "2º TURNO" if turno == 1 and i < 2 else ("ELEITO" if i == 0 else "NÃO ELEITO")
                linhas.append(
                    [
                        ano,
                        turno,
                        "BR",
                        1,
                        "PRESIDENTE",
                        ano * 100 + i,
                        nm,
                        sg,
                        "MASCULINO",
                        "BRANCA",
                        "SUPERIOR COMPLETO",
                        60,
                        "APTO",
                        sit,
                    ]
                )
        _zip(
            raiz / "consulta_cand" / f"consulta_cand_{ano}.zip",
            {f"consulta_cand_{ano}_BRASIL.csv": _csv(cab_c, linhas)},
        )
