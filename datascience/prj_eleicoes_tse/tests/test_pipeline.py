import json

import pandas as pd
import pytest

from eleicoes_tse import leitura
from eleicoes_tse.config import Config
from eleicoes_tse.fontes import ErroDownload, baixar
from eleicoes_tse.pipeline import executar


@pytest.fixture(scope="module")
def execucao(espelho_tse, tmp_path_factory):
    raiz = tmp_path_factory.mktemp("projeto")
    cfg = Config(raiz=raiz, anos=(2018, 2022), url_base=espelho_tse)
    resumo = executar(cfg)
    return cfg, resumo


def test_baixa_e_reaproveita_cache(execucao):
    cfg, _ = execucao
    zip_ = baixar(cfg, "votacao_candidato_munzona", 2022)
    assert zip_.exists() and zip_.parent == cfg.bronze / "votacao_candidato_munzona"


def test_404_vira_erro_claro(espelho_tse, tmp_path):
    with pytest.raises(ErroDownload, match="404"):
        baixar(Config(raiz=tmp_path, url_base=espelho_tse), "consulta_cand", 2014)


def test_so_presidente_e_sem_contagem_dupla(execucao):
    cfg, _ = execucao
    votos = leitura.votacao_presidente(
        cfg.bronze / "votacao_candidato_munzona" / "votacao_candidato_munzona_2022.zip"
    )
    assert set(votos["cd_cargo"]) == {1}
    # 5 municípios × 2 zonas × (3 candidatos no 1º turno + 2 no 2º), mesmo com o arquivo BR repetindo tudo
    assert len(votos) == 5 * 2 * (3 + 2)
    assert votos["municipio"].str.contains("SÃO PAULO").any()  # Latin-1 decodificado


def test_totais_batem_entre_niveis(execucao):
    cfg, _ = execucao
    br = pd.read_csv(cfg.resultados / "presidente_brasil.csv")
    uf = pd.read_csv(cfg.resultados / "presidente_uf.csv")
    mun = pd.read_csv(cfg.resultados / "presidente_municipio.csv.gz")
    for df in (uf, mun):
        soma = df.groupby(["ano", "turno", "nr_candidato"])["votos"].sum()
        assert soma.equals(br.set_index(["ano", "turno", "nr_candidato"])["votos"].sort_index())
    pct = br.groupby(["ano", "turno"])["pct_validos"].sum()
    assert ((pct - 100).abs() < 1e-3).all()


def test_participacao_consistente(execucao):
    cfg, _ = execucao
    p = pd.read_csv(cfg.resultados / "participacao_brasil.csv")
    assert (p["aptos"] == p["comparecimento"] + p["abstencoes"]).all()
    assert (p["comparecimento"] == p["validos"] + p["brancos"] + p["nulos"]).all()
    # 2018 não tem QT_VOTOS_VALIDOS: válidos vêm de nominais + legenda e precisam bater com a votação
    br = pd.read_csv(cfg.resultados / "presidente_brasil.csv")
    validos = br.groupby(["ano", "turno"])["votos"].sum()
    assert validos.equals(p.set_index(["ano", "turno"])["validos"].sort_index())


def test_candidaturas_ultimo_turno_e_aptas(execucao):
    cfg, _ = execucao
    perfil = pd.read_csv(cfg.resultados / "perfil_candidaturas.csv")
    pres = perfil[(perfil["ano"] == 2022) & (perfil["cargo"] == "PRESIDENTE")].iloc[0]
    assert pres["candidaturas"] == 3 and pres["eleitos"] == 1
    dep = perfil[(perfil["ano"] == 2022) & (perfil["cargo"] == "DEPUTADO FEDERAL")].iloc[0]
    assert dep["candidaturas"] == 2 * 39 and dep["eleitos"] == 16


def test_conferencia_detecta_divergencia(execucao):
    cfg, resumo = execucao
    conf = pd.read_csv(cfg.resultados / "conferencia_tse.csv")
    assert len(conf) == 11
    assert resumo["conferencia_ok"] is False  # dados sintéticos não reproduzem o resultado oficial


def test_relatorio_e_figuras(execucao):
    cfg, _ = execucao
    texto = (cfg.relatorio / "RELATORIO.md").read_text(encoding="utf-8")
    for trecho in ("## 1. Resultado nacional", "## 5. Quem se candidata", "PT", "conferem"):
        assert trecho in texto
    for linha in texto.splitlines():
        if linha.startswith("!["):
            assert (cfg.relatorio / linha.split("(", 1)[1].rstrip(")")).exists()
    fontes = json.loads((cfg.resultados / "fontes_e_execucao.json").read_text(encoding="utf-8"))
    assert len(fontes["fontes"]) == 6 and all(len(f["sha256"]) == 64 for f in fontes["fontes"])
