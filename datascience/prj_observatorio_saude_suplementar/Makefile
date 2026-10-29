.PHONY: instalar dados rapido painel servir testes lint

instalar:  ## instala o projeto e as ferramentas de desenvolvimento
	pip install -e ".[dev,parquet]"

dados:     ## pipeline completo (download + indicadores + painel)
	python -m observatorio_ans

rapido:    ## pipeline sem beneficiários (mais rápido)
	python -m observatorio_ans --sem-beneficiarios

painel:    ## só regera o painel a partir de dados/ouro
	python -m observatorio_ans painel

servir:    ## abre o painel em http://localhost:8000
	python -m http.server 8000 --directory site

testes:
	pytest -q

lint:
	ruff check . && ruff format --check .
