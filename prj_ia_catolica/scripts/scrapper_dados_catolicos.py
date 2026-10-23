import os

import pandas as pd
from bs4 import BeautifulSoup
import requests

url = "https://www.vatican.va/archive/cathechism_po/index_new/prima-pagina-cic_po.html"

# caminho de saída relativo ao script (independe do diretório de execução)
PATH_OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files", "scrapper_dados_catecismo_lg.csv")


def get_soup(url):
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return BeautifulSoup(response.text, 'html.parser')


def get_links(url, soup):

    links = soup.find_all('a')

    all_links = []
    for link in links:
        href = link.get('href')
        if href:
            if isinstance(href, list):
                print("List found")
                all_links.extend(href)
            else:
                new_url = '/'.join(url.split("/")[:-1])+"/"+href
                all_links.append(new_url)

    all_links = list(set(t for t in all_links))

    all_links.sort()

    return all_links

def get_all_texts(all_links):

    textos_link = []

    for i, link in enumerate(all_links):
        print(f"-->>> {str(i)}.get link:",link)
        try:
            soup = get_soup(link)
        except requests.RequestException as e:
            print(f"Erro ao acessar {link}: {e}")
            continue

        texts = soup.find_all('p')

        textos = [t.text for t in texts]
        dic = {'link':link, 'textos': textos}

        textos_link.append(dic)


    return textos_link


def save_scrapper(texts_scrapper):
    try:
        os.makedirs(os.path.dirname(PATH_OUTPUT), exist_ok=True)
        df = pd.DataFrame(texts_scrapper)
        df.to_csv(PATH_OUTPUT, index=False)
        print("Textos salvos com sucesso em:", PATH_OUTPUT)
    except Exception as e:
        print("Erro ao salvar textos:", e)


DEBUG = True

if __name__ == '__main__':
    texts_links = []
    if DEBUG:
        soup = get_soup(url)
        all_links = get_links(url, soup)
        textos = get_all_texts(all_links[11:])

        for texts in textos:
            for text in texts['textos']:
                link = texts['link']
                if not isinstance(text, list):
                    texts_links.append({'link':link, 'text': text})

        save_scrapper(texts_links)
