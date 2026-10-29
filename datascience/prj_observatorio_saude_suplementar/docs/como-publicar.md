# Como publicar (painel no ar e atualização automática)

Este projeto vive na pasta `datascience/prj_observatorio_saude_suplementar` do repositório
[`portfolio`](https://github.com/Jefferson019/portfolio). Os workflows do GitHub Actions ficam na **raiz** do
repositório, porque o GitHub só executa workflows de lá:

| Workflow | Arquivo | Quando roda |
|---|---|---|
| Observatório — testes | `.github/workflows/observatorio-testes.yml` | A cada push ou pull request que mexe nesta pasta |
| Observatório — atualizar dados e painel | `.github/workflows/observatorio-atualizar.yml` | Todo dia 8 e quando disparado manualmente |

## 1. Ligue o GitHub Pages (uma vez)

**Settings → Pages → Build and deployment → Source: GitHub Actions.**

## 2. Dispare a primeira atualização

**Actions → "Observatório — atualizar dados e painel" → Run workflow.**

O workflow baixa os dados da ANS, calcula tudo, versiona o histórico de beneficiários em `dados/historico/` e
publica o painel em **https://jefferson019.github.io/portfolio/observatorio-saude-suplementar/**. A raiz
(`https://jefferson019.github.io/portfolio/`) redireciona para o painel. A primeira execução leva de 30 a 60
minutos; as seguintes são mais rápidas, porque só processam o que mudou.

## 3. Confira a conferência

Abra a seção **"Conferência com os números oficiais da ANS"** no painel. Os mesmos dados ficam em
`.../observatorio-saude-suplementar/dados/conciliacao_ans.csv`. Se algum número divergir muito, o
`.../observatorio-saude-suplementar/dados/relatorio_qualidade.json` mostra trimestre a trimestre como as contas
foram mapeadas, qual convenção de sinal foi detectada e se os totais de classe bateram.

## Levar o projeto para um repositório próprio

1. Copie o conteúdo desta pasta para a raiz do novo repositório.
2. Mova os dois workflows para `.github/workflows/` do novo repositório e, neles, remova o bloco `defaults`
   (`working-directory`), a variável `PROJETO`, o prefixo `datascience/prj_observatorio_saude_suplementar/` dos
   caminhos e o passo "Montar o site" (publique a pasta `site` diretamente).
3. Ajuste os links do `README.md` e do `projeto.toml`.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Erro de certificado SSL ao acessar o portal da ANS | No workflow de atualização, mude `ANS_PERMITIR_HTTP` para `"1"`. Os arquivos são públicos; a opção só permite repetir o download por HTTP quando o certificado do servidor falha. |
| Workflow demorando muito na primeira vez | É o download de beneficiários (~400 MB por mês processado). Para uma primeira publicação rápida, dispare com a opção "Pular os beneficiários". |
| Portal da ANS fora do ar | O cliente tenta de novo algumas vezes; se persistir, rode mais tarde (Actions → Re-run). |
| Quero rodar sem internet | Coloque os zips em `dados/bronze/demonstracoes_contabeis/AAAA/` e o `Relatorio_cadop.csv` em `dados/bronze/cadop/` e rode `python -m observatorio_ans --sem-download`. |
