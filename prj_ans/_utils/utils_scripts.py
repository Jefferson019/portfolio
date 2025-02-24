import io 
from ftplib import FTP
import zipfile
import pandas as pd

class SmartFTP(FTP):
    def makepasv(self):
        invalidhost, port = super(SmartFTP, self).makepasv()
        return self.host, port
    

def get_readfile(ftp, no_file):
    download_file = io.BytesIO()

    ftp.retrbinary('RETR ' + str(no_file), download_file.write)

    download_file.seek(0)
    return download_file 

def list_zip_from_ftp(ftp, zip_filename):
    # Baixar o arquivo ZIP
    zip_file = get_readfile(ftp, zip_filename)
    
    # Abrir o ZIP diretamente da memória
    with zipfile.ZipFile(zip_file, "r") as z:
        file_list = z.namelist()  # Lista de arquivos no ZIP
        print("Arquivos no ZIP:", file_list)
        
    return file_list

def download_save(list_zip, path_save):
    for filename in list_zip:
        if filename.endswith(".csv"):  # Se for um CSV
            with open(filename) as file:
                df = pd.read_csv(file, encoding="utf-8")
                path_save = path_save+"/"+file
                df.to_csv(path_save)
    return print(f"Arquivos salvos no PATH: {path_save}")



def process_zip_from_ftp(list_zip):
    dataframes = {}
        
    # Ler cada arquivo no ZIP e salvar em um dicionário
    for filename in list_zip:
        if filename.endswith(".csv"):  # Se for um CSV
            with open(filename) as file:
                df = pd.read_csv(file, encoding="utf-8")  # Ajuste o encoding se necessário
                dataframes[filename] = df
                print(f"Lido: {filename}, {df.shape}")

    return dataframes