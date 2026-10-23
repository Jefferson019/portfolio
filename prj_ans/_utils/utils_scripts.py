import io
import os
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

def download_save(ftp, zip_filename, path_save, encoding="latin1", sep=";"):
    # Baixa o ZIP do FTP e salva cada CSV de dentro dele em path_save
    zip_file = get_readfile(ftp, zip_filename)
    saved = []

    with zipfile.ZipFile(zip_file, "r") as z:
        for filename in z.namelist():
            if filename.lower().endswith(".csv"):  # Se for um CSV
                with z.open(filename) as file:
                    df = pd.read_csv(file, encoding=encoding, sep=sep, low_memory=False)
                dest = os.path.join(path_save, os.path.basename(filename))
                df.to_csv(dest, index=False)
                saved.append(dest)

    print(f"Arquivos salvos no PATH: {path_save}")
    return saved



def process_zip_from_ftp(ftp, zip_filename, encoding="latin1", sep=";"):
    dataframes = {}
    zip_file = get_readfile(ftp, zip_filename)

    # Ler cada CSV de dentro do ZIP e salvar em um dicionário
    with zipfile.ZipFile(zip_file, "r") as z:
        for filename in z.namelist():
            if filename.lower().endswith(".csv"):  # Se for um CSV
                with z.open(filename) as file:
                    df = pd.read_csv(file, encoding=encoding, sep=sep, low_memory=False)
                dataframes[filename] = df
                print(f"Lido: {filename}, {df.shape}")

    return dataframes