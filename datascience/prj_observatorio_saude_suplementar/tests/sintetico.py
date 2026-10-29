"""Gerador de um "espelho" sintético do Portal de Dados Abertos da ANS, para testes.

Reproduz o formato dos arquivos reais (CSV com ';', vírgula decimal, aspas, zips trimestrais,
índices de diretório) e também as armadilhas conhecidas:
  * mudança do plano de contas (2023 no layout antigo: receitas financeiras no grupo 34);
  * encodings diferentes (latin-1 em 2023, UTF-8 depois) e dois formatos de data;
  * convenções de sinal diferentes (2025+ com saldos credores negativos);
  * saldos de resultado acumulados no ano, linha duplicada, trimestre faltante,
    operadora fora do cadastro e contas analíticas que devem ser ignoradas.

Também devolve o "gabarito" (valores verdadeiros) para comparar com o resultado do pipeline.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

MODALIDADES_SINT = [
    ("Medicina de Grupo", 0.78, 0.09, 0.035),
    ("Cooperativa Médica", 0.80, 0.10, 0.012),
    ("Seguradora Especializada em Saúde", 0.84, 0.05, 0.06),
    ("Autogestão", 0.92, 0.10, 0.0),
    ("Filantropia", 0.77, 0.10, 0.015),
    ("Odontologia de Grupo", 0.55, 0.15, 0.10),
    ("Cooperativa Odontológica", 0.58, 0.14, 0.06),
    ("Administradora de Benefícios", np.nan, 0.30, 0.10),
]
UFS = ["SP", "RJ", "MG", "DF", "PR", "RS", "BA", "PE"]
CICLO = {
    2019: 1.0,
    2020: 0.92,
    2021: 1.05,
    2022: 1.10,
    2023: 1.07,
    2024: 1.03,
    2025: 0.99,
    2026: 1.0,
}

DESC_RN435 = {
    "1": "ATIVO",
    "12": "ATIVO CIRCULANTE",
    "121": "DISPONÍVEL",
    "122": "APLICAÇÕES FINANCEIRAS",
    "123": "CRÉDITOS DE OPERAÇÕES COM PLANOS DE ASSISTÊNCIA À SAÚDE",
    "129": "OUTROS CRÉDITOS",
    "13": "ATIVO NÃO CIRCULANTE",
    "131": "REALIZÁVEL A LONGO PRAZO",
    "1311": "APLICAÇÕES GARANTIDORAS DE PROVISÕES TÉCNICAS",
    "1312": "APLICAÇÕES LIVRES",
    "133": "IMOBILIZADO",
    "2": "PASSIVO",
    "21": "PASSIVO CIRCULANTE",
    "211": "PROVISÕES TÉCNICAS DE OPERAÇÕES DE ASSISTÊNCIA À SAÚDE",
    "213": "DÉBITOS DE OPERAÇÕES DE ASSISTÊNCIA À SAÚDE",
    "23": "PASSIVO NÃO CIRCULANTE",
    "231": "PROVISÕES TÉCNICAS DE OPERAÇÕES DE ASSISTÊNCIA À SAÚDE",
    "25": "PATRIMÔNIO LÍQUIDO / PATRIMÔNIO SOCIAL",
    "3": "RECEITAS",
    "31": "CONTRAPRESTAÇÕES EFETIVAS DE PLANO DE ASSISTÊNCIA À SAÚDE",
    "311": "CONTRAPRESTAÇÕES LÍQUIDAS / PRÊMIOS RETIDOS",
    "31111": "CONTRAPRESTAÇÕES EMITIDAS",
    "32": "(-) TRIBUTOS DIRETOS DE OPERAÇÕES DE ASSISTÊNCIA À SAÚDE",
    "33": "OUTRAS RECEITAS OPERACIONAIS",
    "34": "(-) TRIBUTOS DIRETOS DE OUTRAS ATIVIDADES DE ASSISTÊNCIA À SAÚDE",
    "35": "RECEITAS FINANCEIRAS",
    "36": "RECEITAS PATRIMONIAIS",
    "4": "DESPESAS",
    "41": "EVENTOS INDENIZÁVEIS LÍQUIDOS / SINISTROS RETIDOS",
    "411": "EVENTOS / SINISTROS CONHECIDOS OU AVISADOS",
    "411111": "EVENTOS/ SINISTROS CONHECIDOS OU AVISADOS DE ASSISTÊNCIA A SAÚDE MEDICO HOSPITALAR",
    "414": "VARIAÇÃO DA PROVISÃO DE EVENTOS OCORRIDOS E NÃO AVISADOS",
    "43": "DESPESAS DE COMERCIALIZAÇÃO",
    "44": "OUTRAS DESPESAS OPERACIONAIS",
    "45": "DESPESAS FINANCEIRAS",
    "46": "DESPESAS ADMINISTRATIVAS",
    "47": "DESPESAS PATRIMONIAIS",
    "6": "CONTAS DE DESTINAÇÃO / APURAÇÃO DE RESULTADO",
    "61": "IMPOSTOS E PARTICIPAÇÕES SOBRE O LUCRO",
}
# Plano antigo (RN 290): sem grupos de tributos; financeiras = 34, patrimoniais = 35
DESC_RN290 = {k: v for k, v in DESC_RN435.items() if k not in {"32", "34", "35", "36"}}
DESC_RN290.update({"34": "RECEITAS FINANCEIRAS", "35": "RECEITAS PATRIMONIAIS"})


@dataclass
class OpSint:
    reg_ans: str
    nome: str
    modalidade: str
    uf: str
    receita_tri: float
    sinistralidade: float
    da: float
    dc: float
    crescimento: float
    beneficiarios: int
    no_cadastro: bool = True
    cancelada: bool = False
    pl_negativo: bool = False


def _operadoras(n: int, rng: np.random.Generator) -> list[OpSint]:
    ops = []
    for i in range(n):
        modalidade, sin, da, dc = MODALIDADES_SINT[i % len(MODALIDADES_SINT)]
        receita_tri = float(np.exp(rng.normal(17.0, 1.3)))  # mediana ~ R$ 24 mi por trimestre
        if modalidade == "Administradora de Benefícios":
            sin_op = 0.0
        else:
            sin_op = float(np.clip(rng.normal(sin, 0.05), 0.4, 1.3))
        ticket = 450.0 if "Odonto" not in modalidade else 35.0
        ops.append(
            OpSint(
                reg_ans=f"{300000 + i * 7:06d}",
                nome=f"OPERADORA EXEMPLO {i + 1:03d} {'ODONTO' if 'Odonto' in modalidade else 'SAÚDE'}",
                modalidade=modalidade,
                uf=UFS[i % len(UFS)],
                receita_tri=receita_tri,
                sinistralidade=sin_op,
                da=float(np.clip(rng.normal(da, 0.02), 0.02, 0.4)),
                dc=float(np.clip(rng.normal(dc, 0.01), 0.0, 0.2)),
                crescimento=float(rng.normal(0.025, 0.01)),
                beneficiarios=int(receita_tri / 3 / ticket),
            )
        )
    ops[3].no_cadastro = False  # aparece no DIOPS, mas não no cadastro
    ops[5].cancelada = True
    ops[7].pl_negativo = True
    return ops


def _fmt(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def gerar_espelho(
    raiz: Path,
    n_operadoras: int = 40,
    anos: tuple[int, ...] = (2023, 2024, 2025, 2026),
    ultimo_tri_2026: int = 2,
    semente: int = 7,
) -> pd.DataFrame:
    """Cria a árvore de arquivos em `raiz` e devolve o gabarito (valores acumulados no ano)."""
    rng = np.random.default_rng(semente)
    ops = _operadoras(n_operadoras, rng)
    raiz = Path(raiz)
    gabarito = []
    saldo_bal_anterior: dict[tuple[str, str], float] = {}

    for ano in anos:
        rn290 = ano == anos[0]  # primeiro ano no layout antigo do plano de contas
        descricoes = DESC_RN290 if rn290 else DESC_RN435
        credora_negativa = ano >= 2025
        encoding = "latin-1" if ano == anos[0] else "utf-8"
        formato_data = "%d/%m/%Y" if ano <= 2024 else "%Y-%m-%d"
        ytd: dict[tuple[str, str], float] = {}
        trimestres = range(1, (ultimo_tri_2026 if ano == 2026 else 4) + 1)
        for tri in trimestres:
            linhas = []
            data = pd.Timestamp(year=ano, month=(tri - 1) * 3 + 1, day=1).strftime(formato_data)
            for idx, op in enumerate(ops):
                if idx == 9 and ano == 2025 and tri == 3:
                    continue  # trimestre faltante para uma operadora
                t_abs = (ano - anos[0]) * 4 + tri
                rc = op.receita_tri * (1 + op.crescimento) ** t_abs * (1 + rng.normal(0, 0.01))
                td = -0.01 * rc if not rn290 else 0.0  # tributos diretos (negativos)
                # Sinistralidade com ciclo plurianual (queda em 2020, pico em 2022) e sazonalidade leve
                sin = op.sinistralidade * CICLO.get(ano, 1.0) * (1 + 0.02 * (tri - 2.5) / 1.5)
                das = rc * sin
                peona = das * 0.01
                fluxos = {
                    "31": rc,
                    "32": td,
                    "33": rc * 0.02,
                    "34": -rc * 0.001 if not rn290 else 0.0,
                    "fin": rc * 0.03,
                    "pat": rc * 0.002,
                    "41": das,
                    "411": das - peona,
                    "414": peona,
                    "43": rc * op.dc,
                    "44": rc * 0.03,
                    "45": rc * 0.005,
                    "46": rc * op.da,
                    "47": rc * 0.001,
                }
                resultado_antes = (
                    fluxos["31"]
                    + fluxos["32"]
                    + fluxos["33"]
                    + fluxos["34"]
                    + fluxos["fin"]
                    + fluxos["pat"]
                    - fluxos["41"]
                    - fluxos["43"]
                    - fluxos["44"]
                    - fluxos["45"]
                    - fluxos["46"]
                    - fluxos["47"]
                )
                fluxos["61"] = max(resultado_antes, 0) * 0.34
                for chave, valor in fluxos.items():
                    ytd[(op.reg_ans, chave)] = ytd.get((op.reg_ans, chave), 0.0) + valor

                # Balanço (posição no fim do trimestre)
                ativo_c = op.receita_tri * 1.1 * (1 + 0.01 * t_abs)
                aplic_cp = ativo_c * 0.5
                creditos = op.receita_tri * 0.15
                disponivel = ativo_c * 0.1
                outros_c = ativo_c - aplic_cp - creditos - disponivel
                aplic_lp1, aplic_lp2 = op.receita_tri * 0.3, op.receita_tri * 0.1
                rlp = aplic_lp1 + aplic_lp2
                imobilizado = op.receita_tri * 0.2
                ativo_nc = rlp + imobilizado
                ativo = ativo_c + ativo_nc
                prov_cp = op.receita_tri * 0.6
                passivo_c = prov_cp + op.receita_tri * 0.2
                prov_lp = op.receita_tri * 0.1
                passivo_nc = prov_lp
                pl = ativo - passivo_c - passivo_nc
                if op.pl_negativo:
                    passivo_nc = ativo - passivo_c + op.receita_tri * 0.3
                    prov_lp = passivo_nc
                    pl = ativo - passivo_c - passivo_nc
                balanco = {
                    "1": ativo,
                    "12": ativo_c,
                    "121": disponivel,
                    "122": aplic_cp,
                    "123": creditos,
                    "129": outros_c,
                    "13": ativo_nc,
                    "131": rlp,
                    "1311": aplic_lp1,
                    "1312": aplic_lp2,
                    "133": imobilizado,
                    "2": ativo,
                    "21": passivo_c,
                    "211": prov_cp,
                    "213": passivo_c - prov_cp,
                    "23": passivo_nc,
                    "231": prov_lp,
                    "25": pl,
                }

                cod_fin, cod_pat = ("34", "35") if rn290 else ("35", "36")
                contas_fluxo = {
                    "31": ytd[(op.reg_ans, "31")],
                    "311": ytd[(op.reg_ans, "31")],
                    "31111": ytd[(op.reg_ans, "31")],
                    cod_fin: ytd[(op.reg_ans, "fin")],
                    cod_pat: ytd[(op.reg_ans, "pat")],
                    "33": ytd[(op.reg_ans, "33")],
                    "41": ytd[(op.reg_ans, "41")],
                    "411": ytd[(op.reg_ans, "411")],
                    "411111": ytd[(op.reg_ans, "411")],
                    "414": ytd[(op.reg_ans, "414")],
                    "43": ytd[(op.reg_ans, "43")],
                    "44": ytd[(op.reg_ans, "44")],
                    "45": ytd[(op.reg_ans, "45")],
                    "46": ytd[(op.reg_ans, "46")],
                    "47": ytd[(op.reg_ans, "47")],
                    "61": ytd[(op.reg_ans, "61")],
                }
                if not rn290:
                    contas_fluxo["32"] = ytd[(op.reg_ans, "32")]
                    contas_fluxo["34"] = ytd[(op.reg_ans, "34")]
                receitas_total = sum(
                    v for k, v in contas_fluxo.items() if len(k) == 2 and k.startswith("3")
                )
                despesas_total = sum(
                    v for k, v in contas_fluxo.items() if len(k) == 2 and k.startswith("4")
                )
                contas_fluxo["3"] = receitas_total
                contas_fluxo["4"] = despesas_total
                contas_fluxo["6"] = contas_fluxo["61"]

                # Saldo inicial dos fluxos = acumulado até o trimestre anterior (zero no 1º trimestre)
                for conta, valor in {**contas_fluxo, **balanco}.items():
                    if conta in balanco:
                        inicial = saldo_bal_anterior.get((op.reg_ans, conta), valor)
                        saldo_bal_anterior[(op.reg_ans, conta)] = valor
                    else:
                        inicial = (
                            0.0
                            if tri == 1
                            else _ytd_anterior(gabarito, op.reg_ans, ano, tri - 1, conta, rn290)
                        )
                    final_ = valor
                    sinal = _sinal(conta, credora_negativa, descricoes)
                    linhas.append(
                        (
                            data,
                            op.reg_ans,
                            conta,
                            descricoes.get(conta, f"CONTA {conta}"),
                            _fmt(inicial * sinal),
                            _fmt(final_ * sinal),
                        )
                    )
                gabarito.append(
                    {
                        "reg_ans": op.reg_ans,
                        "ano": ano,
                        "tri": tri,
                        **{f"c_{k}": v for k, v in contas_fluxo.items()},
                        **{f"b_{k}": v for k, v in balanco.items()},
                        "rn290": rn290,
                    }
                )
            # Linha duplicada (deve ser removida)
            linhas.append(linhas[0])
            _escrever_zip_trimestral(raiz, ano, tri, linhas, encoding)

    _escrever_cadastro(raiz, ops)
    _escrever_beneficiarios(raiz, ops)
    gab = pd.DataFrame(gabarito)
    meta = pd.DataFrame([op.__dict__ for op in ops])
    return gab.merge(meta, on="reg_ans")


def _ytd_anterior(
    gabarito: list[dict], reg_ans: str, ano: int, tri: int, conta: str, rn290: bool
) -> float:
    for linha in reversed(gabarito):
        if linha["reg_ans"] == reg_ans and linha["ano"] == ano and linha["tri"] == tri:
            return linha.get(f"c_{conta}", 0.0)
    return 0.0


def _sinal(conta: str, credora_negativa: bool, descricoes: dict[str, str]) -> float:
    """Convenção 'credora negativa': passivo, PL e receitas negativos; deduções da receita positivas.
    Convenção 'absoluta' (anos anteriores): tudo positivo, inclusive as deduções."""
    redutora = descricoes.get(conta, "").startswith("(-)")
    if not credora_negativa:
        return -1.0 if redutora else 1.0  # valores internos das deduções já são negativos
    # Saldo credor negativo: toda a classe 2 e 3 troca de sinal (deduções, que são devedoras,
    # ficam positivas porque o valor interno delas já é negativo)
    return -1.0 if conta.startswith(("2", "3")) else 1.0


def _escrever_zip_trimestral(
    raiz: Path, ano: int, tri: int, linhas: list[tuple], encoding: str
) -> None:
    pasta = raiz / "demonstracoes_contabeis" / str(ano)
    pasta.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    buffer.write(
        '"DATA";"REG_ANS";"CD_CONTA_CONTABIL";"DESCRICAO";"VL_SALDO_INICIAL";"VL_SALDO_FINAL"\n'
    )
    for linha in linhas:
        buffer.write(";".join(f'"{v}"' for v in linha) + "\n")
    with zipfile.ZipFile(pasta / f"{tri}T{ano}.zip", "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{tri}T{ano}.csv", buffer.getvalue().encode(encoding))


def _escrever_cadastro(raiz: Path, ops: list[OpSint]) -> None:
    colunas = [
        "REGISTRO_OPERADORA",
        "CNPJ",
        "Razao_Social",
        "Nome_Fantasia",
        "Modalidade",
        "Logradouro",
        "Numero",
        "Complemento",
        "Bairro",
        "Cidade",
        "UF",
        "CEP",
        "DDD",
        "Telefone",
        "Fax",
        "Endereco_eletronico",
        "Representante",
        "Cargo_Representante",
        "Regiao_de_Comercializacao",
        "Data_Registro_ANS",
    ]
    ativas, canceladas = [], []
    for i, op in enumerate(ops):
        if not op.no_cadastro:
            continue
        linha = [
            op.reg_ans,
            f"{10000000000000 + i * 97:014d}",
            f"{op.nome} LTDA",
            op.nome if i % 4 else "",
            op.modalidade,
            "RUA EXEMPLO",
            str(i),
            "",
            "CENTRO",
            "CIDADE EXEMPLO",
            op.uf,
            "70000000",
            "61",
            "33330000",
            "",
            "contato@exemplo.com.br",
            "FULANO",
            "DIRETOR",
            "1",
            "2001-01-01",
        ]
        (canceladas if op.cancelada else ativas).append(linha)
    pasta_a = raiz / "operadoras_de_plano_de_saude_ativas"
    pasta_c = raiz / "operadoras_de_plano_de_saude_canceladas"
    pasta_a.mkdir(parents=True, exist_ok=True)
    pasta_c.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ativas, columns=colunas).to_csv(
        pasta_a / "Relatorio_cadop.csv", sep=";", index=False, encoding="utf-8"
    )
    df_c = pd.DataFrame(canceladas, columns=colunas)
    df_c["Data_Descredenciamento"] = "2025-08-01"
    df_c["Motivo_do_Descredenciamento"] = "Cancelamento a pedido"
    df_c.to_csv(
        pasta_c / "Relatorio_cadop_canceladas.csv", sep=";", index=False, encoding="latin-1"
    )


def _escrever_beneficiarios(raiz: Path, ops: list[OpSint]) -> None:
    pasta_raiz = raiz / "informacoes_consolidadas_de_beneficiarios-024"
    meses = [
        "202412",
        "202506",
        "202508",
        "202509",
        "202512",
        "202603",
        "202606",
        "202607",
        "202608",
    ]
    colunas = [
        "ID_CMPT_MOVEL",
        "CD_OPERADORA",
        "NM_RAZAO_SOCIAL",
        "NR_CNPJ",
        "MODALIDADE_OPERADORA",
        "SG_UF",
        "CD_MUNICIPIO",
        "NM_MUNICIPIO",
        "TP_SEXO",
        "DE_FAIXA_ETARIA",
        "DE_CONTRATACAO_PLANO",
        "DE_SEGMENTACAO_PLANO",
        "COBERTURA_ASSIST_PLAN",
        "TIPO_VINCULO",
        "QT_BENEFICIARIO_ATIVO",
        "QT_BENEFICIARIO_ADERIDO",
        "QT_BENEFICIARIO_CANCELADO",
        "DT_CARGA",
    ]
    for k, mes in enumerate(meses):
        pasta = pasta_raiz / mes
        pasta.mkdir(parents=True, exist_ok=True)
        for uf in ("SP", "RJ", "XX"):
            linhas = []
            for op in ops:
                if op.modalidade == "Administradora de Benefícios":
                    continue
                cobertura = "Odontológico" if "Odonto" in op.modalidade else "Médico-hospitalar"
                total = op.beneficiarios * (1 + 0.004 * k)
                fatia = {"SP": 0.6, "RJ": 0.35, "XX": 0.05}[uf]
                for contratacao, peso in (
                    ("Coletivo empresarial", 0.7),
                    ("Individual ou familiar", 0.2),
                    ("Coletivo por adesão", 0.1),
                ):
                    for sexo in ("M", "F"):
                        qtd = int(round(total * fatia * peso / 2))
                        linhas.append(
                            [
                                f"{mes[:4]}-{mes[4:]}",
                                op.reg_ans,
                                op.nome,
                                "",
                                op.modalidade,
                                uf,
                                "355030",
                                "SAO PAULO",
                                sexo,
                                "30 a 39 anos",
                                contratacao,
                                "Ambulatorial + Hospitalar",
                                cobertura,
                                "Titular",
                                str(qtd),
                                "0",
                                "0",
                                "2026-10-01",
                            ]
                        )
            texto = pd.DataFrame(linhas, columns=colunas).to_csv(sep=";", index=False)
            with zipfile.ZipFile(
                pasta / f"pda-024-icb-{uf}-{mes[:4]}_{mes[4:]}.zip", "w", zipfile.ZIP_DEFLATED
            ) as zf:
                zf.writestr(f"pda-024-icb-{uf}-{mes[:4]}_{mes[4:]}.csv", texto.encode("utf-8"))


def beneficiarios_esperados(ops_meta: pd.DataFrame, mes_indice: int) -> pd.Series:
    """Total esperado por operadora no k-ésimo mês da lista (para testes)."""
    return ops_meta.set_index("reg_ans")["beneficiarios"] * (1 + 0.004 * mes_indice)
