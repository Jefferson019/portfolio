# databricks-boas-praticas

Projeto-modelo de **engenharia de software no Databricks**, construído a partir das
recomendações oficiais (docs, out/2026) e de palestras e vídeos da comunidade. O domínio é
**contas médicas** (saúde suplementar), com **dados sintéticos**, em arquitetura medalhão:

```
Volume (CSV)  ──Auto Loader──▶  bronze_contas  ──expectativas──▶  silver_contas (AUTO CDC, SCD1)
                                     │                                   │
                                     └──────▶ quarentena_contas          └──▶ gold_resumo_mensal_prestador (MV)
                                                                                     │
                                                    job: pipeline ▶ checagens (wheel) ▶ alertas
```

> **Nota (portfolio):** aqui o projeto fica numa subpasta. O GitHub só executa workflows que estão
> em `.github/workflows/` na raiz do repositório, então os arquivos em `.github/workflows/` desta
> pasta servem como **modelo**. Em um repositório próprio, eles funcionam como estão.

O guia completo, com o motivo de cada prática e as fontes, está em
**[docs/BOAS_PRATICAS.md](docs/BOAS_PRATICAS.md)**.

## Estrutura

```
.
├── databricks.yml                 # Bundle: variáveis + targets dev/staging/prod
├── resources/                     # Recursos como código (1 arquivo por recurso)
│   ├── contas_medicas.pipeline.yml   # Lakeflow Declarative Pipeline (serverless)
│   ├── contas_medicas.job.yml        # Job: pipeline → checagens de qualidade
│   └── metadata.job.yml              # Job: comentários de tabelas/colunas
├── src/
│   ├── contas_medicas/            # Pacote Python (wheel) — TODA a lógica testável
│   │   ├── config.py                 # Ambiente (catalog/schema), parse de parâmetros
│   │   ├── transformations.py        # Funções puras DataFrame → DataFrame
│   │   ├── quality.py                # Regras de qualidade como dados
│   │   ├── checks.py                 # Entry point `checagens` (pós-pipeline)
│   │   └── logging_utils.py          # Logs JSON estruturados
│   ├── pipelines/contas_medicas/transformations/
│   │   ├── bronze.py                 # Auto Loader + linhagem
│   │   ├── silver.py                 # Expectativas, quarentena, AUTO CDC
│   │   └── gold.sql                  # Materialized view com liquid clustering
│   ├── sql/metadata/comments.sql  # Comentários UC versionados
│   └── notebooks/exploracao.py    # Notebook FINO (formato source, diff legível)
├── tests/                         # pytest: Python puro + Spark (local ou Connect)
├── fixtures/                      # Amostra sintética com registros ruins de propósito
├── .github/workflows/             # CI (PR) e CD (main → staging, tag → prod), OIDC
├── .pre-commit-config.yaml        # ruff, nbstripout, gitleaks, check-yaml
└── pyproject.toml                 # uv + hatchling, ruff, pytest
```

## Primeiros passos

```bash
# 1. Ferramentas
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh
pip install uv          # ou: curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Dependências (escolha local OU remote)
uv sync --group dev --group local      # Spark local (precisa de Java 17)
# uv sync --group dev --group remote   # Databricks Connect → serverless do workspace

# 3. Qualidade antes de commitar
uv run pre-commit install
uv run ruff check . && uv run pytest

# 4. Autenticar e fazer deploy no SEU ambiente de dev
databricks auth login --host https://<seu-workspace>
databricks bundle validate
databricks bundle deploy            # target dev é o default
databricks bundle run contas_medicas_job
```

Em `dev`, os recursos aparecem como `[dev seu_usuario] contas_medicas_job`, gravam no
schema `dev.<seu_usuario>` e os agendamentos ficam pausados.

## O que ajustar antes de usar

| Onde | O quê |
|---|---|
| `databricks.yml` | `workspace.host` de cada target, `warehouse_id`, grupos de permissão |
| GitHub → Settings → Environments | criar `dev`, `staging`, `prod` com as variáveis `DATABRICKS_HOST` e `DATABRICKS_CLIENT_ID`; em `prod`, exigir aprovação |
| Databricks | service principal com federation policy para o repositório (OIDC) e catálogos `dev`, `staging`, `prod` |
| Unity Catalog | volume `landing` em cada schema, ex.: `/Volumes/dev/<usuario>/landing/contas_medicas` |

## Fluxo de trabalho (trunk-based)

1. `git switch -c feat/minha-mudanca` (branch curta)
2. Desenvolver no IDE (extensão Databricks / Databricks Connect) ou em Git folder no workspace
3. `databricks bundle deploy` no seu dev e testar
4. Abrir PR → CI roda lint, testes e `bundle validate`
5. Merge em `main` → CD faz deploy em **staging** e roda o job ponta a ponta
6. `git tag v1.2.0 && git push --tags` → deploy em **prod** após aprovação
