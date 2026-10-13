"""下载公开商品图片，Windows使用系统curl的TLS；不关闭证书校验。"""
import io
import os
import re
import subprocess
import urllib.request
from PIL import Image


def download_image(url,target):
    urls=list(dict.fromkeys([re.sub(r'\._[^/]*_\.jpg$','.jpg',url),url]))
    for source in urls:
        try:
            if os.name=='nt':
                result=subprocess.run(['curl.exe','--fail','--location','--max-time','30',source],capture_output=True)
                if result.returncode:continue
                data=result.stdout
            else:data=urllib.request.urlopen(source,timeout=30).read()
            with Image.open(io.BytesIO(data)) as image:image.verify()
            target.write_bytes(data)
            return
        except (OSError,ValueError):continue
    raise RuntimeError('商品主图下载失败，保留待发，不发送无图询盘')
