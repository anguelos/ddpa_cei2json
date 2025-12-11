import bs4
import re
import json
import glob
import time
from collections import defaultdict, Counter
from lxml import etree
from .cei_dates import infer_date

__namespaces = {"atom": "http://www.w3.org/2005/Atom", "cei": "http://www.monasterium.net/NS/cei"}

__xpath_expressions = {
    "cei_date": "/atom:entry/atom:content/cei:text/cei:body/cei:chDesc/cei:issued/cei:date/text()",
    "cei_date_ATTRIBUTE_value": "/atom:entry/atom:content/cei:text/cei:body/cei:chDesc/cei:issued/cei:date/@value",
    "cei_date_ATTRIBUTE_notBefore": "/atom:entry/atom:content/cei:text/cei:body/cei:chDesc/cei:issued/cei:date/@notBefore",
    "cei_date_ATTRIBUTE_notAfter": "/atom:entry/atom:content/cei:text/cei:body/cei:chDesc/cei:issued/cei:date/@notAfter",
    "cei_dateRange": "/atom:entry/atom:content/cei:text/cei:body/cei:chDesc/cei:issued/cei:dateRange/text()",
    "cei_dateRange_ATTRIBUTE_from": "/atom:entry/atom:content/cei:text/cei:body/cei:chDesc/cei:issued/cei:dateRange/@from",
    "cei_dateRange_ATTRIBUTE_to": "/atom:entry/atom:content/cei:text/cei:body/cei:chDesc/cei:issued/cei:dateRange/@to"
}


def extract_cei_dates(cei_path):
    with open(cei_path, "rb") as f:
        root = etree.parse(f).getroot()
        data = {}
        for key, xpath_expr in __xpath_expressions.items():
            result = root.xpath(xpath_expr, namespaces=__namespaces, smart_strings=False)
            if len(result) == 1:
                data[key] = result[0] or None
            else:
                data[key] = result or None
        valid_dates = sorted(list([str(d).strip() for d in data.values() if d is not None]))
        return valid_dates


def parse_cei(cei_path):
    soup = bs4.BeautifulSoup(open(cei_path,"r"), features="xml")
    abstracts =  soup.find_all("cei:abstract")
    if len(abstracts)>0:
        abstracts = [" ".join([str(a) for a in  abstract.contents]) for abstract in abstracts]
        #abstracts = " ".join([" ".join(abstract.contents) for abstract in abstracts])
        abstracts = " ".join(abstracts)
        abstracts = " ".join(abstracts.split())
    else:
        abstracts = ""
    # <cei:dateRange from="14640225" to="14640225">25. Februar 1464</cei:dateRange>
    #dates = [d.attrs["from"] for d in soup.find_all("cei:daterange")]
    #dates += [d.attrs["to"] for d in soup.find_all("cei:daterange")]
    #dates += [d.attrs["value"] for d in soup.find_all("cei:date")]
    dates = extract_cei_dates(cei_path)
    dates = [infer_date(d, fail_quietly=True) for d in dates]
    dates = [d for d in dates if not isinstance(d, str)]  # fix infer dates

    tenors =  soup.find_all("cei:tenor")
    if len(tenors)>0:
        tenors = [" ".join([str(t) for t in  tenor.contents]) for tenor in tenors]
        tenors = " ".join(tenors)
        tenors = " ".join(tenors.split())
    else:
        tenors = ""
    tenors = re.sub("<\/?[a-zA-Z0-9:]+\/?>","", tenors)
    return {"abstract":abstracts, "dates":sorted(dates), "tenor":tenors}

