.PHONY: instalar dados testes lint

instalar:  ## instala o projeto e as ferramentas de desenvolvimento
	pip install -e ".[dev,parquet]"

dados:     ## baixa do TSE e roda a análise completa (2018 e 2022)
	python -m eleicoes_tse

testes:
	pytest -q

lint:
	ruff check . && ruff format --check .
