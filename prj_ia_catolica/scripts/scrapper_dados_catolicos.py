import pandas as pd
from bs4 import BeautifulSoup
import requests
import spacy

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

    for link in all_links:
        print("...get link:",link)
        page = requests.get(link)
        soup = BeautifulSoup(page.text, 'html.parser')

        texts = soup.find_all('p')
        titulos = soup.find_all('h3')

        textos = [t.text for t in texts]
        #print(len(textos))
        dic = {'link':link, 'textos': textos}

        textos_link.append(dic)


    return textos_link

def get_embeddings(texto):
    
    return nlp_sm(texto).vector


DEBUG = True

if __name__ == '__main__':
    texts_embeddings = []
    if DEBUG:
        all_links = get_links(url, soup)
        textos = get_all_texts(all_links)

        for text in [texts['textos'] for texts in textos[:-1]]:
            
            if not isinstance(text, list):
                texts_embeddings.append(get_embeddings(text))
            
        #for t in textos[:10]:
        #    print(t)

      