import pandas as pd
from bs4 import BeautifulSoup
import requests
import spacy
import os

from langchain_chroma import Chroma
from langchain_community.embeddings.spacy_embeddings import SpacyEmbeddings

nlp_sm = spacy.load("pt_core_news_lg")

url = "https://www.vatican.va/archive/cathechism_po/index_new/prima-pagina-cic_po.html"
response = requests.get(url)
soup = BeautifulSoup(response.text, 'html.parser')

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
        page = requests.get(link)
        soup = BeautifulSoup(page.text, 'html.parser')

        texts = soup.find_all('p')
        titulos = soup.find_all('h3')

        textos = [t.text for t in texts]
        #print(len(textos))
        dic = {'link':link, 'textos': textos}

        textos_link.append(dic)


    return textos_link


def save_scrapper(texts_scrapper):
    try:
        df = pd.DataFrame(texts_scrapper)
        df.to_csv("../files/scrapper_dados_catecismo_lg.csv", index=False)
        print("Embeddings salvos com sucesso!")
    except Exception as e:
        print("Erro ao salvar embeddings:", e)


DEBUG = True

if __name__ == '__main__':
    texts_links = []
    if DEBUG:
        all_links = get_links(url, soup)
        textos = get_all_texts(all_links[11:])

        for texts in textos:
            for text in texts['textos']:
                link = texts['link']
                #print(text)
                if not isinstance(text, list):
                    texts_links.append({'link':link, 'text': text})

        save_scrapper(texts_links)
            
        #for t in textos[:10]:
        #    print(t)

      