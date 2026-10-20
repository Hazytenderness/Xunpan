"""把同一商家、同一引用消息中的影像证据转成网站接受的链接。"""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


def media_values(fact, batch, offer, field):
    batch=Path(batch).resolve();offer=str(offer)
    values=fact.get('值');values=values if isinstance(values,list) else [values]
    direct=[];local=[]
    for value in values:
        if not isinstance(value,str):continue
        text=value.strip().replace('\\','/')
        if text in ('无','不能提供'):direct.append(text);continue
        if text.startswith('https://'):
            parsed=urlsplit(text)
            if parsed.hostname and not parsed.username and not parsed.password:direct.append(text)
        elif '/' in text and not re.search(r'[:?#]',text) and not any(p in ('','..','.') for p in text.split('/')):
            candidate=(batch.parent.parent/text if text.startswith('batches/') else batch/text).resolve()
            if candidate.is_relative_to(batch/'media'/offer) and candidate.is_file():local.append(text)
    chat=batch/'chats'/f'{offer}.json'
    wanted=set(re.findall(r'(\d{8}T\d{6})_',json.dumps(fact,ensure_ascii=False)))
    try:wanted.add(datetime.fromisoformat(fact.get('时间','')).strftime('%Y%m%dT%H%M%S'))
    except (TypeError,ValueError):pass
    links=[]
    if chat.exists() and wanted:
        for msg in json.loads(chat.read_text(encoding='utf-8')).get('消息',[]):
            if msg.get('发送方')!='对方':continue
            try:stamp=datetime.fromisoformat(msg.get('时间','')).strftime('%Y%m%dT%H%M%S')
            except (TypeError,ValueError):continue
            if stamp not in wanted:continue
            for url in msg.get('图片' if field=='实拍图' else '视频',[]):
                if not isinstance(url,str):continue
                parsed=urlsplit(url)
                if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password:links.append(url)
    return list(dict.fromkeys(direct or links or local))
