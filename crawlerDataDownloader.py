#!/usr/bin/env python3

import gzip
import json
from urllib.request import urlopen
import os

def tojson(l):
    k=l.strip().decode("utf-8")
    dic = json.loads(k)
    return dic

def extractPayload(path,tell=0):
    flip= False
    k=[]  
    with gzip.open(path, 'rb') as f:
        f.seek(tell)
        l = f.readline()
        while (type(k) != dict or flip == True):
            l = f.readline()
            if len(l) < 1500:
                k=l.strip()
                k=k.split(b': ')
                if k[0] == b'Content-Type' and k[1]==b'application/json':
                    flip = True
#                 print("hey")
                elif k[0] == b'WARC-Target-URI':
                    uri=k[1]
            elif flip and len(l)>1500 :
                dic=tojson(l.strip())
                return dic,str(uri),f.tell()
            
def wget(url):
    file_name = url.split('/')[-1]
    file_name = file_name.strip()
    u = urlopen(url)
    f = open(file_name, 'wb')
    meta = u.info()
    file_size = int(meta.get("Content-Length"))
    print("Downloading: %s Bytes: %s" % (file_name, file_size))

    file_size_dl = 0
    block_sz = 8192
    while True:
        buffer = u.read(block_sz)
        if not buffer:
            break

        file_size_dl += len(buffer)
        f.write(buffer)
        status = r"%10d  [%3.2f%%]" % (file_size_dl, file_size_dl * 100. / file_size)
        status = status + chr(8)*(len(status)+1)
        print(status,end="\r")

    f.close()
    return file_name

def hostnamer(url):
    url_split=url.split('/')
    base_url = url_split[0].split("b'")[1]+"//"+url_split[2]
    return base_url

def extractFromFile(file_path,file_name):
    prevtell,tell=0,0
    pay=[]
    write_count=1
    save_file="RESULT-"+file_name
    f=open(save_file,'w')
    print("Extracting from "+file_path)
    while (tell!=prevtell or tell == 0):
        prevtell=tell
        links=[]
        k,uri,tell=extractPayload(file_path,tell)
        try:

            if k['Envelope']['Payload-Metadata']['Actual-Content-Type'] == 'application/http; msgtype=response' and k['Envelope']['Payload-Metadata']['HTTP-Response-Metadata']['Response-Message']['Status']:
                try:
                    if k['Envelope']['Payload-Metadata']['HTTP-Response-Metadata']['Headers']['Content-Type'].find('text/html') == 0:
                        try:
                            links.append(k['Envelope']['Payload-Metadata']['HTTP-Response-Metadata']['HTML-Metadata']['Head']['Link'])
                            links.append(k['Envelope']['Payload-Metadata']['HTTP-Response-Metadata']['HTML-Metadata']['Links'])
                        except (KeyError):
                            try:
                                links.append(k['Envelope']['Payload-Metadata']['HTTP-Response-Metadata']['HTML-Metadata']['Links'])
                            except (KeyError):
                                links.append(k['Envelope']['Payload-Metadata']['HTTP-Response-Metadata']['HTML-Metadata']['Head']['Link'])
                        finally:
                            pay.append({'uri':hostnamer(uri),'links':links})  
#                             print("and another one bites the dust ",len(pay))
#                     else:
#                         print(str(i)+"nope")
                except KeyError:
                    pass
        except (KeyError):
                pass


        if len(pay)>100 :
            json.dump(pay,f)
            pay=[]
            print("Written 100 to file: "+ str(write_count))
            write_count+=1
            
    json.dump(pay,f)
    pay=[]
#     print("reset")
    f.close()
    print("Saved To:"+save_file)
    
def main():
    url_base="http://commoncrawl.s3.amazonaws.com/"
    with open('CC-MAIN-2016-36/wat.paths.txt', 'r') as f:
        for relative_path in  f:
            url=url_base+relative_path
            saved_file=wget(url)
            result_saved_file=saved_file.strip().split(".")[0]+".json"
            extractFromFile(saved_file,result_saved_file)
            os.remove(saved_file)
            print(saved_file+" has been deleted.")
            
if __name__ == "__main__":
    main()
