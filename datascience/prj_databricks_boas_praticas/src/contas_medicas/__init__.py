"""Pacote `contas_medicas`: lógica de negócio testável, empacotada como wheel.

Regra de ouro: notebooks e arquivos de pipeline são *orquestração fina*;
toda transformação relevante mora aqui, em funções puras que recebem e
devolvem DataFrames — e por isso podem ser testadas com pytest.
"""

__version__ = "0.1.0"
