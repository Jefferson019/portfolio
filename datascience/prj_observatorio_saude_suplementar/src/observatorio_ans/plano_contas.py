"""Mapeamento entre o Plano de Contas Padrão da ANS e os conceitos usados nos indicadores.

O plano de contas mudou ao longo do tempo (RN 290/2012, RN 435/2018, RN 528/2022). Exemplo:
"Receitas Financeiras" era o grupo 34 e passou a ser o 35. Por isso cada conceito é resolvido
trimestre a trimestre pela DESCRIÇÃO da conta (que vem nos próprios arquivos da ANS), usando o
código padrão apenas como alternativa. O resultado da resolução fica registrado no relatório de
qualidade, para auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .util import normalizar_texto


@dataclass(frozen=True)
class Conceito:
    nome: str
    rotulo: str
    natureza: (
        str  # "fluxo" (DRE, acumulado no ano) ou "saldo" (balanço, posição no fim do trimestre)
    )
    prefixo: str  # prefixo do código das contas candidatas ("" = nível de classe)
    niveis: tuple[int, ...]  # quantidade de dígitos das contas candidatas
    palavras: tuple[str, ...]  # palavras-chave (sem acento, maiúsculas) na descrição
    padrao: str | None = None  # código usado se nenhuma descrição corresponder
    composto: bool = False  # soma todas as contas que correspondem (no nível mais raso)
    redutora: bool = False  # conta de dedução (valor deve ser negativo após normalização)


# A ordem importa: conceitos mais específicos são resolvidos antes dos genéricos.
CONCEITOS: list[Conceito] = [
    # ---------------------------------------------------------------- DRE: receitas (classe 3)
    Conceito(
        "tributos_diretos_operacoes",
        "(-) Tributos diretos de operações com planos",
        "fluxo",
        "3",
        (2,),
        ("TRIBUTOS DIRETOS DE OPERAC",),
        "32",
        redutora=True,
    ),
    Conceito(
        "tributos_diretos_outras",
        "(-) Tributos diretos de outras atividades",
        "fluxo",
        "3",
        (2,),
        ("TRIBUTOS DIRETOS DE OUTRAS",),
        "34",
        redutora=True,
    ),
    Conceito(
        "receita_contraprestacoes",
        "Contraprestações efetivas (receita de mensalidades)",
        "fluxo",
        "3",
        (2,),
        ("CONTRAPRESTAC", "PREMIOS GANHOS"),
        "31",
    ),
    Conceito(
        "outras_receitas_operacionais",
        "Outras receitas operacionais",
        "fluxo",
        "3",
        (2,),
        ("OUTRAS RECEITAS OPERACIONAIS",),
        "33",
    ),
    Conceito(
        "receitas_financeiras",
        "Receitas financeiras",
        "fluxo",
        "3",
        (2,),
        ("RECEITAS FINANCEIRAS",),
        "35",
    ),
    Conceito(
        "receitas_patrimoniais",
        "Receitas patrimoniais",
        "fluxo",
        "3",
        (2,),
        ("RECEITAS PATRIMONIAIS",),
        "36",
    ),
    # ---------------------------------------------------------------- DRE: despesas (classe 4)
    Conceito(
        "despesa_assistencial",
        "Eventos indenizáveis líquidos (despesa assistencial)",
        "fluxo",
        "4",
        (2,),
        ("EVENTOS INDENIZAVEIS", "SINISTROS RETIDOS"),
        "41",
    ),
    Conceito(
        "despesa_comercializacao",
        "Despesas de comercialização",
        "fluxo",
        "4",
        (2,),
        ("COMERCIALIZAC",),
        "43",
    ),
    Conceito(
        "outras_despesas_operacionais",
        "Outras despesas operacionais",
        "fluxo",
        "4",
        (2,),
        ("OUTRAS DESPESAS OPERACIONAIS",),
        "44",
    ),
    Conceito(
        "despesas_financeiras",
        "Despesas financeiras",
        "fluxo",
        "4",
        (2,),
        ("DESPESAS FINANCEIRAS",),
        "45",
    ),
    Conceito(
        "despesa_administrativa",
        "Despesas administrativas",
        "fluxo",
        "4",
        (2,),
        ("DESPESAS ADMINISTRATIVAS",),
        "46",
    ),
    Conceito(
        "despesas_patrimoniais",
        "Despesas patrimoniais",
        "fluxo",
        "4",
        (2,),
        ("DESPESAS PATRIMONIAIS",),
        "47",
    ),
    # ---------------------------------------------------------------- impostos (classe 6)
    Conceito(
        "impostos_participacoes",
        "Impostos e participações sobre o lucro",
        "fluxo",
        "6",
        (2,),
        ("IMPOSTOS E PARTICIPAC",),
        "61",
    ),
    # ---------------------------------------------------------------- balanço: ativo
    Conceito("ativo_total", "Ativo total", "saldo", "", (1,), ("ATIVO",), "1"),
    Conceito(
        "ativo_circulante", "Ativo circulante", "saldo", "1", (2,), ("ATIVO CIRCULANTE",), "12"
    ),
    Conceito(
        "ativo_nao_circulante",
        "Ativo não circulante",
        "saldo",
        "1",
        (2,),
        ("ATIVO NAO CIRCULANTE", "ATIVO PERMANENTE"),
        "13",
    ),
    Conceito("disponivel", "Disponível", "saldo", "12", (3,), ("DISPONIVEL",), "121"),
    Conceito(
        "aplicacoes_financeiras_cp",
        "Aplicações financeiras (circulante)",
        "saldo",
        "12",
        (3,),
        ("APLICAC",),
        "122",
    ),
    Conceito(
        "creditos_operacoes_planos",
        "Créditos de operações com planos (mensalidades a receber)",
        "saldo",
        "12",
        (3,),
        ("CREDITOS DE OPERAC",),
        "123",
    ),
    Conceito(
        "realizavel_longo_prazo",
        "Realizável a longo prazo",
        "saldo",
        "13",
        (3,),
        ("REALIZAVEL A LONGO PRAZO",),
        "131",
    ),
    Conceito(
        "aplicacoes_financeiras_lp",
        "Aplicações financeiras (longo prazo)",
        "saldo",
        "131",
        (4,),
        ("APLICAC",),
        None,
        composto=True,
    ),
    # ---------------------------------------------------------------- balanço: passivo
    Conceito("passivo_total", "Passivo total (inclui PL)", "saldo", "", (1,), ("PASSIVO",), "2"),
    Conceito(
        "passivo_circulante",
        "Passivo circulante",
        "saldo",
        "2",
        (2,),
        ("PASSIVO CIRCULANTE",),
        "21",
    ),
    Conceito(
        "passivo_nao_circulante",
        "Passivo não circulante",
        "saldo",
        "2",
        (2,),
        ("PASSIVO NAO CIRCULANTE", "EXIGIVEL A LONGO PRAZO"),
        "23",
    ),
    Conceito(
        "patrimonio_liquido",
        "Patrimônio líquido",
        "saldo",
        "2",
        (2,),
        ("PATRIMONIO LIQUIDO", "PATRIMONIO SOCIAL"),
        "25",
    ),
    Conceito(
        "provisoes_tecnicas_cp",
        "Provisões técnicas (circulante)",
        "saldo",
        "21",
        (3,),
        ("PROVISOES TECNICAS",),
        "211",
        composto=True,
    ),
    Conceito(
        "provisoes_tecnicas_lp",
        "Provisões técnicas (não circulante)",
        "saldo",
        "23",
        (3, 4),
        ("PROVISOES TECNICAS",),
        None,
        composto=True,
    ),
]

CONCEITOS_POR_NOME = {c.nome: c for c in CONCEITOS}
CONCEITOS_FLUXO = [c.nome for c in CONCEITOS if c.natureza == "fluxo"]
CONCEITOS_SALDO = [c.nome for c in CONCEITOS if c.natureza == "saldo"]

# Conceitos calculados somando todos os grupos (2 dígitos) da classe — servem para o resultado
# líquido (classe 3 - classe 4 - impostos) e para validar a convenção de sinais.
TOTAIS_DE_CLASSE = {"receita_total": "3", "despesa_total": "4"}
CONCEITOS_FLUXO_TODOS = CONCEITOS_FLUXO + list(TOTAIS_DE_CLASSE)


def contas_de_interesse(conta: pd.Series) -> pd.Series:
    """Filtro aplicado na leitura: guarda só as contas usadas (reduz memória e disco)."""
    tamanho = conta.str.len()
    return (tamanho <= 3) | (
        (tamanho == 4) & (conta.str.startswith("131") | conta.str.startswith("23"))
    )


@dataclass
class Resolucao:
    """Resultado da resolução dos conceitos para um trimestre."""

    contas: dict[str, list[str]] = field(default_factory=dict)  # conceito -> códigos
    origem: dict[str, str] = field(
        default_factory=dict
    )  # conceito -> "descricao" | "codigo_padrao"
    avisos: list[str] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {"contas": self.contas, "origem": self.origem, "avisos": self.avisos}


def descricoes_por_conta(df: pd.DataFrame) -> dict[str, str]:
    """Descrição mais frequente (normalizada) de cada código de conta no trimestre."""
    if "descricao" not in df or df.empty:
        return {}
    base = df[["conta", "descricao"]].dropna()
    base = base.assign(descricao=base["descricao"].map(normalizar_texto))
    base = base[base["descricao"] != ""]
    if base.empty:
        return {}
    moda = base.groupby(["conta", "descricao"]).size().reset_index(name="n")
    moda = moda.sort_values(["conta", "n"], ascending=[True, False]).drop_duplicates("conta")
    return dict(zip(moda["conta"], moda["descricao"], strict=True))


def _corresponde(descricao: str, palavras: tuple[str, ...]) -> bool:
    return any(p in descricao for p in palavras)


def resolver_conceitos(codigos: set[str], descricoes: dict[str, str]) -> Resolucao:
    """Decide quais contas compõem cada conceito, dado o conjunto de códigos de um trimestre."""
    res = Resolucao()
    reivindicadas: set[str] = set()

    for conceito in CONCEITOS:
        candidatos_por_nivel = {
            n: sorted(c for c in codigos if len(c) == n and c.startswith(conceito.prefixo))
            for n in conceito.niveis
        }
        escolhidas: list[str] = []
        for nivel in conceito.niveis:
            achadas = [
                c
                for c in candidatos_por_nivel[nivel]
                if c not in reivindicadas and _corresponde(descricoes.get(c, ""), conceito.palavras)
            ]
            if achadas:
                if conceito.composto:
                    escolhidas = achadas
                else:
                    escolhidas = [conceito.padrao] if conceito.padrao in achadas else [achadas[0]]
                break

        if escolhidas:
            res.origem[conceito.nome] = "descricao"
        elif (
            conceito.padrao and conceito.padrao in codigos and conceito.padrao not in reivindicadas
        ):
            descricao = descricoes.get(conceito.padrao, "")
            # Só usa o código padrão se a descrição dele não pertencer claramente a outro conceito
            outro = next(
                (
                    o.nome
                    for o in CONCEITOS
                    if o.nome != conceito.nome
                    and descricao
                    and _corresponde(descricao, o.palavras)
                    and o.prefixo == conceito.prefixo
                ),
                None,
            )
            if outro is None:
                escolhidas = [conceito.padrao]
                res.origem[conceito.nome] = "codigo_padrao"
                if descricao:
                    res.avisos.append(
                        f"{conceito.nome}: descrição da conta {conceito.padrao} ('{descricao}') não confere; "
                        "usado o código padrão"
                    )
        if escolhidas:
            res.contas[conceito.nome] = escolhidas
            reivindicadas.update(escolhidas)
        elif not conceito.composto:
            res.avisos.append(f"{conceito.nome}: nenhuma conta encontrada no trimestre")
    return res


def eh_redutora(descricao: str) -> bool:
    """Contas de dedução: começam com '(-)' ou são tributos diretos."""
    return descricao.startswith("(-)") or "TRIBUTOS DIRETOS" in descricao
