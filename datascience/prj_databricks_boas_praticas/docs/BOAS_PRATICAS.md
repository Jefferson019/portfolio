# Boas práticas de desenvolvimento no Databricks

Resumo da pesquisa (documentação oficial, blog técnico e fóruns da comunidade
Databricks, palestras do Data + AI Summit e canais de vídeo), feita em outubro de 2026.
Cada item indica **onde** está aplicado neste repositório.

> **Nomes novos:** *Databricks Asset Bundles (DABs)* passaram a se chamar
> **Declarative Automation Bundles**. *Delta Live Tables (DLT)* virou
> **Lakeflow Spark Declarative Pipelines** e *Workflows* virou **Lakeflow Jobs**.
> O CLI e o formato `databricks.yml` não mudaram.

---

## 1. Controle de versão

| Prática | Aqui |
|---|---|
| **Versionar quase tudo**: notebooks, `.py`, `.sql`, `databricks.yml` e overrides por ambiente. A doc oficial diz que, se algo não está no controle de versão, não existe. | todo o repo |
| **Não versionar artefatos de build** (`.whl`, `.jar`): o CI gera os artefatos e publica em volumes do UC | `.gitignore`, `artifacts` no `databricks.yml` |
| **Nunca versionar tokens nem credenciais**: use secret manager → secret scopes, ou OIDC | `.gitignore`, `gitleaks` no pre-commit |
| **Nunca versionar amostras reais nem PII**: use dados sintéticos | `fixtures/` sintético |
| **Um repositório** para código e configuração, mesmo com vários bundles (exceção: setores regulados que exigem separar) | monorepo |
| **Notebooks em formato source** (`.py` com `# COMMAND ----------`) e sem outputs no git | `src/notebooks/exploracao.py`, `nbstripout` |

## 2. Branches e ambientes

- **Trunk-based development**: a `main` fica sempre deployável. Use branches curtas,
  faça merge após testar em dev, a CI/CD publica em staging e roda os testes, e a
  promoção para prod acontece só se tudo passar. → `.github/workflows/`
- **Workspaces**: até ~5 engenheiros, *dev + prod*. Acima disso, *dev + staging + prod*,
  com staging espelhando prod. Em setores regulados (como **saúde**), isole fisicamente
  os workspaces e as contas cloud.
- **Unity Catalog**: **um metastore**, com **um catálogo por ambiente** (`dev`, `staging`,
  `prod`) e **schemas pessoais** para cada dev. O catálogo de prod fica vinculado em modo
  `ISOLATED` apenas ao workspace de prod. → `variables.catalog`/`schema` por target

## 3. Bundles (CI/CD como código)

- **Bundles são o caminho recomendado** para CI/CD. Terraform fica só para recursos
  cloud e de administração (workspaces, rede).
- **Bundles pequenos e focados**, cada um cobrindo **todos os ambientes** do projeto.
  Separe por domínio, dono, ciclo de vida ou necessidade de rollback.
- **Parametrize, não fixe valores**: tamanho de cluster, catálogo, schema e segredos. → `variables` + `targets`
- `mode: development` em dev (prefixo por usuário e schedules pausados) e
  `mode: production` em staging/prod. → `databricks.yml`
- **Deploy em pasta do time ou do SP**, nunca em `/Workspace/Shared`. `CAN_MANAGE` só
  para os donos. → `root_path`, `permissions`
- **Templates customizados** (`databricks bundle init <template>`) para padronizar
  guardrails (permissões, tags, políticas, CI) entre os projetos da empresa.
- **Dependências entre bundles** ficam na orquestração da CI/CD, não juntando bundles.
- **Rollback** = redeploy da última versão boa (tag) do bundle.
- Rode `databricks bundle validate` localmente e no CI, antes de qualquer deploy.

## 4. Identidade e segurança

- **Service principals** para toda automação fora de dev: um SP de **deploy** com acesso
  mínimo e um SP de **execução** (`run_as`) por workload. → `run_as` em staging/prod
- **Workload Identity Federation (OIDC)** no GitHub Actions ou Azure DevOps, eliminando
  segredos de longa duração. → `DATABRICKS_AUTH_TYPE: github-oidc`
- Compute **serverless** com network policies em prod sempre que possível.

## 5. Organização do código

- **Lógica de negócio fora de notebooks.** Notebooks servem para exploração, visualização
  e orquestração fina. → `src/contas_medicas/`
- Python em **módulos importáveis** dentro de `src/`, empacotados como **wheel**. → `pyproject.toml`
- SQL em arquivos **`.sql`** referenciados por jobs e pipelines. → `gold.sql`, `comments.sql`
- **Funções puras** (DataFrame entra, DataFrame sai), sem I/O, `dbutils` ou widgets
  dentro delas. → `transformations.py`
- Para passar valores entre tasks em tempo de execução, use
  `{{tasks.<task>.values.<chave>}}` (task values).
- **Comentários de tabela e coluna como código**, em `.sql` aplicado por um job. A
  descrição explica o que a linha representa, a unidade e os valores válidos. → `metadata.job.yml`

## 6. Testes

Pirâmide recomendada:

1. **Python puro** (config, regras, parsing): pytest comum, sem Spark. → `tests/test_config.py`
2. **Transformações Spark** com DataFrames pequenos:
   - local com `pyspark`, ou
   - **Databricks Connect v2 + pytest**, que roda no serverless com Spark, Delta e UC reais. → `tests/conftest.py`
   - use `assertDataFrameEqual` / `assertSchemaEqual` (Spark 3.5+ / DBR 14.2+).
3. **Integração em staging**: o CD roda o job ponta a ponta e o wheel `checagens` valida
   contagens, schema e taxa de quarentena. → `checks.py`, `cd.yml`

Teste com amostras **que incluem registros ruins** de propósito. → `fixtures/`
Nutter só faz sentido se você precisar testar o notebook inteiro (widgets, `dbutils`).

## 7. Lakeflow Declarative Pipelines

- **Tipo certo de dataset**: *streaming table* para ingestão e append, *materialized view*
  para agregações e *temporary view* para etapas intermediárias sem custo de storage.
- **Auto Loader** (`cloudFiles`) lendo de **Volumes** do UC. → `bronze.py`
- **Expectativas** (`expect`, `expect_or_drop`, `expect_or_fail`, `expect_all_*`) em vez de
  `WHERE` silencioso: elas geram métricas no event log. → `silver.py`
- **Quarentena** dos registros reprovados, usando as mesmas regras invertidas. → `quarentena_contas`
- **AUTO CDC** (`create_auto_cdc_flow`) no lugar de `MERGE` imperativo: trata ordenação,
  duplicidade, eventos fora de ordem e evolução de schema.
- **Parâmetros** via `configuration` + `spark.conf.get()`. Nomes de tabela sem catálogo
  usam o padrão do pipeline e ficam portáveis entre ambientes.
- **Modo triggered** por padrão. O contínuo exige cluster sempre ligado e custa bem mais.
- **Development mode** para iterar (reusa o cluster e não faz retry).

## 8. Delta Lake e desempenho

- Use **tabelas gerenciadas do UC** + **predictive optimization** (OPTIMIZE e VACUUM automáticos).
- **Liquid clustering** em vez de particionamento + Z-ORDER. → `cluster_by` / `CLUSTER BY`
- **Não use `.cache()`** em tabelas Delta: você perde data skipping e pode ler dado
  desatualizado. Filtre cedo com `WHERE`.
- Nunca mexa nos arquivos Parquet de uma tabela Delta. Use `CREATE OR REPLACE TABLE` em vez de DROP + CREATE.
- Em `MERGE`, restrinja o espaço de busca na condição (ex.: data) e prefira Low Shuffle Merge.
- Ao migrar de runtime, **remova configurações Delta legadas**.

## 9. Observabilidade

- **Logs estruturados** com bundle, ambiente, workload, `run_id` e um identificador de
  negócio, centralizados numa biblioteca compartilhada. → `logging_utils.py`
- Acompanhe status, duração, retries e frescor de cada workload de produção.
- Alertas de falha definidos no código. → `email_notifications`, `notifications`

## 10. Ferramentas de desenvolvimento

- **IDE local** (VS Code + extensão oficial Databricks, PyCharm) com Databricks Connect, ou
  **Git folders** no workspace. → `.vscode/`
- Gere o schema JSON do bundle para ter autocomplete nos YAML:
  `databricks bundle schema > .vscode/bundle_schema.json`
- `pre-commit` com ruff, nbstripout e gitleaks.

---

## Fontes

### Documentação oficial
- [Developer best practices on Databricks](https://docs.databricks.com/aws/en/developers/best-practices)
- [Best practices and recommended CI/CD workflows](https://docs.databricks.com/dev-tools/ci-cd/best-practices)
- [CI/CD on Databricks](https://docs.databricks.com/en/dev-tools/index-ci-cd.html)
- [Bundle project templates](https://docs.databricks.com/aws/dev-tools/bundles/templates)
- [Bundle configuration examples (serverless, wheels)](https://docs.databricks.com/dev-tools/bundles/examples)
- [Bundles FAQ](https://docs.databricks.com/aws/dev-tools/bundles/faqs)
- [Best practices for Lakeflow Spark Declarative Pipelines](https://docs.databricks.com/aws/en/ldp/best-practices)
- [Develop Lakeflow Declarative Pipelines](https://docs.databricks.com/aws/en/delta-live-tables/develop)
- [Best practices: Delta Lake](https://docs.databricks.com/aws/delta/best-practices)

### Blog técnico e comunidade Databricks
- [Writing unit tests for PySpark in Databricks](https://community.databricks.com/t5/technical-blog/writing-unit-tests-for-pyspark-in-databricks-approaches-and-best/bc-p/123186/highlight/true)
- [Running Spark tests (Databricks Connect v2 + serverless)](https://community.databricks.com/t5/data-engineering/running-spark-tests/td-p/152744)
- [Wheel task com serverless em bundles](https://community.databricks.com/t5/data-engineering/bundled-wheel-task-with-serverless-compute/m-p/146933/highlight/true)
- [Unity Catalog: metastore único, catálogo por ambiente](https://community.databricks.com/t5/get-started-discussions/unity-catalog-implementation/m-p/89155/highlight/true)
- [Predictive optimization / liquid clustering](https://community.databricks.com/t5/blogs/blogarticleprintpage/blog-id/technical-blog/article-id/474)

### Vídeos e palestras
- **Databricks Asset Bundles: A Unifying Tool for Deployment on Databricks**: Connor Brown e Pieter Noordhuis (Data + AI Summit, ~36 min, canal Databricks no YouTube) — [ficha](https://classcentral.com/course/youtube-databricks-asset-bundles-a-unifying-tool-for-deployment-on-databricks-306362)
- **Databricks CI/CD: Intro to Databricks Asset Bundles**: Dustin Vannoy (YouTube), com `bundle init` e deploy via GitHub Actions — [notas](https://sushantvema.github.io/notes/databricks_ci_cd_guide)
- **Databricks CI/CD: Azure DevOps Pipeline + DABs**: Dustin Vannoy — [Databricks TV](https://community.databricks.com/t5/databricks-tv/databricks-ci-cd-azure-devops-pipeline-dabs/ba-p/92589)
- **Tips for Databricks Asset Bundles**: Dustin Vannoy — [post](https://curatedsql.com/2024/06/26/tips-for-databricks-asset-bundles/)
- **From Imperative to Declarative: Rebuilding CI/CD with Hatch and DABs**: Data + AI Summit 2025 — [speaker](https://www.databricks.com/dataaisummit/speaker/luigi-di-tacchio)
- **Best of Data Engineering, Data + AI Summit 2025** (sessões on-demand) — [link](https://www.databricks.com/dataaisummit/best-of-data-engineering)
- **The path to Bundle your Databricks projects**: SQLBits 2025 — [sessão](https://sqlbits.com/sessions/event2025/The_path_to_Bundle_your_Databricks_projects)
