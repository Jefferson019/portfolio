import io 
from ftplib import FTP

class SmartFTP(FTP):
    def makepasv(self):
        invalidhost, port = super(SmartFTP, self).makepasv()
        return self.host, port
    

def get_readfile(ftp, no_file):
    download_file = io.BytesIO()

    ftp.retrbinary('RETR ' + str(no_file), download_file.write)

    download_file.seek(0)
    return download_file 
