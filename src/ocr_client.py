"""Origin-side HTTP timing. No cross-host clock subtraction."""
import json
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request


def normalize(text):
    return unicodedata.normalize('NFC',text).strip()


def character_error_rate(hypothesis, reference):
    hypothesis,reference=normalize(hypothesis),normalize(reference)
    if not reference:return None
    previous=list(range(len(reference)+1))
    for i,a in enumerate(hypothesis,1):
        current=[i]
        for j,b in enumerate(reference,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(a!=b)))
        previous=current
    return previous[-1]/len(reference)


def health(url):
    with urllib.request.urlopen(url+'/health',timeout=5) as r:
        return json.load(r)


def recognize(url, image, request_id, tier, priority, timeout=190):
    query=urllib.parse.urlencode(dict(id=request_id,tier=tier,priority=priority))
    request=urllib.request.Request(url+'/ocr?'+query,data=image,headers={'Content-Type':'image/png'})
    start=time.monotonic()
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            result=json.load(response)
            status=response.status
    except urllib.error.HTTPError as exc:
        result=json.load(exc)
        status=exc.code
    result.update(http_status=status,origin_elapsed_s=time.monotonic()-start)
    return result
