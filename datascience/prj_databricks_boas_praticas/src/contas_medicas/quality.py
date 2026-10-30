"""Regras de qualidade de dados como DADOS (dicionários), não espalhadas no código.

As mesmas regras são usadas:
  - no pipeline, via `@dp.expect_all_or_drop(REGRAS_SILVER)` (métricas no event log)
  - na quarentena, invertendo as regras para capturar o que foi descartado
  - nos testes unitários, para garantir que as expressões fazem sentido
"""

from __future__ import annotations

# Expectativas = expressões SQL booleanas avaliadas linha a linha.
REGRAS_SILVER: dict[str, str] = {
    "id_conta_presente": "id_conta IS NOT NULL",
    "beneficiario_presente": "carteirinha IS NOT NULL",
    "valor_apresentado_positivo": "valor_apresentado > 0",
    "valor_pago_nao_excede": "valor_pago <= valor_apresentado",
    "data_atendimento_valida": "data_atendimento <= current_date()",
    "tipo_guia_conhecido": "tipo_guia IN ('CONSULTA', 'SADT', 'INTERNACAO', 'ODONTO')",
}

# Regras de "alerta" (WARN): não descartam a linha, só geram métrica.
REGRAS_ALERTA: dict[str, str] = {
    "codigo_tuss_8_digitos": "length(codigo_tuss) = 8",
}


def expressao_quarentena(regras: dict[str, str]) -> str:
    """Retorna a expressão que identifica linhas que violam QUALQUER regra.

    Útil para a tabela de quarentena: em vez de perder silenciosamente as
    linhas descartadas, guardamos para análise.
    """
    if not regras:
        raise ValueError("é preciso ao menos uma regra")
    return "NOT ({})".format(" AND ".join(f"coalesce({r}, false)" for r in regras.values()))
