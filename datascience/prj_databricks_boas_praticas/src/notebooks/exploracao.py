# Databricks notebook source
# MAGIC %md
# MAGIC # Exploração — contas médicas
# MAGIC
# MAGIC Notebook **fino**: só exploração e visualização. Ele importa o mesmo pacote
# MAGIC usado em produção, então o que você testa aqui é o que vai para o job.
# MAGIC
# MAGIC > Salvo no formato *source* (`.py` com `# COMMAND ----------`) para gerar diffs
# MAGIC > legíveis no git. Evite commitar notebooks com outputs.

# COMMAND ----------

dbutils.widgets.text("catalog", "dev")  # noqa: F821
dbutils.widgets.text("schema", "")  # noqa: F821
catalog = dbutils.widgets.get("catalog")  # noqa: F821
schema = dbutils.widgets.get("schema")  # noqa: F821

# COMMAND ----------

from contas_medicas.config import Ambiente  # noqa: E402
from contas_medicas.transformations import resumo_mensal_prestador  # noqa: E402

amb = Ambiente(catalog=catalog, schema=schema)
contas = spark.table(amb.tabela("silver_contas"))  # noqa: F821

# Filtre cedo (data skipping + liquid clustering) — nada de .cache() em tabelas Delta
recorte = contas.where("data_atendimento >= date_sub(current_date(), 90)")
display(resumo_mensal_prestador(recorte).orderBy("valor_glosa", ascending=False))  # noqa: F821
