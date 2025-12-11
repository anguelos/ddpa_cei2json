import re
import anyascii
import bs4
import re
import json
import tqdm
import time
from lxml import etree
from typing import Tuple, Dict, Optional, Generator, Union


# TODO: (anguelos) add more month names.
__month2num = {
    "janner": 1,
    "januar": 1,
    "leden": 1,  # Czeck?
    "ledna": 1,  # misspelled leden
    "gennaio": 1,  # Italian?
    "gennao": 1,  # misspelled gennaio
    "gnnaio": 1,  # misspelled gennaio
    "gen.": 1,  # misspelled gennaio
    "janenr": 1,  # misspelled januar
    "i": 1,
    "janer": 1,  # misspelled janner
    "janaur": 1,  # misspelled januar
    "jannuar": 1,  # misspelled januar
    "jamuar": 1,  # misspelled januar
    "jabnuar": 1,  # misspelled januar
    "janunar": 1,  # misspelled januar
    "jan": 1,  # misspelled januar
    "jan.": 1,  # misspelled januar

    "februar": 2,
    "febbraio": 2,  # misspelled febbraio
    "feber": 2,  # misspelled februar
    "unor": 2,  # Czeck?
    "unora": 2,  # misspelled unor
    "ii": 2,
    "februuar": 2,  # misspelled februar
    "febbario": 2,  # misspelled febbraio
    "hornung": 2,  # old german month name
    "febuar": 2,  # misspelled februar
    "febr.": 2,  # misspelled februar
    "febrtuar": 2,  # misspelled februar
    "febraur": 2,  # misspelled februar
    "feb": 2,  # misspelled february
    "feb.": 2,
    "febr": 2,  # misspelled februar

    "marz": 3,
    "marzo": 3,  # Italian?
    "marts": 3,  # misspelled marz
    "brezen": 3,  # Czeck?
    "brezna": 3,  # misspelled brezen
    "iii": 3,
    "marzt": 3,  # misspelled marz
    "maez": 3,  # misspelled maerz
    "mar.": 3,  # misspelled marzo
    "mar": 3,  # misspelled marzo

    "april": 4,
    "apri": 4,  # misspelled april
    "iv": 4,
    "duben": 4,  # Czeck? https://en.wikipedia.org/wiki/Slavic_calendar
    "dube": 4,  # misspelled duben
    "aril": 4,  # misspelled april
    "aprile": 4,  # misspelled aprile
    "aprille": 4,  # misspelled aprile
    "dubna": 4,  # misspelled duben
    "apirl": 4,  # misspelled april
    "apr.": 4,  # misspelled april
    "apr": 4,  # misspelled april

    "mai": 5,
    "maggio": 5,  # Italian?
    "maggioo": 5,  # misspelled maggio
    "mag.": 5,  # misspelled maggio
    "v": 5,
    "kveten": 5,  # Hungarian?
    "kvetna": 5,  # misspelled kveten

    "juni": 6,
    "vi": 6,
    "giugno": 6,  # misspelled giugno
    "giungo": 6,  # misspelled giugno
    "cerven": 6,  # Czeck?
    "cervna": 6,  # misspelled cerven
    "jun": 6,  # misspelled juni
    "jun.": 6,  # misspelled juni

    "juli": 7,
    "luglio": 7,  # Italian?
    "lug.": 7,  # misspelled luglio
    "cervenec": 7,  # Czeck?
    "cervence": 7,  # misspelled cervenec
    "cervemec": 7,  # misspelled cervenec
    "vii": 7,
    "julie": 7,  # misspelled juli
    "uli": 7,  # misspelled juli
    "jul": 7,  # misspelled juli
    "jul.": 7,  # misspelled juli

    
    "august": 8,
    "srpen": 8,  # Czeck?
    "srpna": 8,  # misspelled srpen
    "spren": 8,  # misspelled srpen
    "setembre": 8,  # misspelled settembre
    "settembe": 8,  # misspelled settembre
    "set.": 8,  # misspelled settembre
    "viii": 8,
    "agosto": 8,  # Italian?
    "augsut": 8,  # misspelled august
    "augst": 8,  # misspelled august
    "aug.": 8,
    "aug": 8,  # misspelled august

    "september": 9,
    "settembre": 9,  # Italian?
    "septiembre": 9,  # Spanish?
    "septmeber": 9,  # misspelled september
    "spetember": 9,  # misspelled september
    "zari": 9,  # Czeck?
    "ix": 9,
    "sept.": 9,  # misspelled september
    "septemberer": 9,  # misspelled september
    "sep.": 9,  # misspelled september
    "sep": 9,  # misspelled september
    "sept": 9,  # misspelled september
    
    "oktober": 10,
    "ottobre": 10,  # Italian?
    "ottobe": 10,  # misspelled ottobre
    "x": 10,
    "rijen": 10,  # Czeck?
    "october": 10,  # misspelled oktober
    "rijna": 10,  # misspelled rijen
    "okotber": 10,  # misspelled oktober
    "okober": 10,  # misspelled oktober    
    "okt": 10,
    "okt.": 10,  # misspelled oktober

    "november": 11,
    "xi": 11,
    "listopad": 11,  # Czeck?
    "listopa": 11,  # misspelled listopad
    "listopadu": 11,  # misspelled listopad
    "novemver": 11,  # misspelled november
    "novembre": 11,  # misspelled novembre
    "npvember": 11,  # misspelled november
    "novenber": 11,  # misspelled november
    "novemmber": 11,  # misspelled november
    "novemer": 11,  # misspelled november
    "novermber": 11,  # misspelled november
    "novermber": 11,  # misspelled november
    "nov.": 11,  # misspelled november
    "nov": 11,  # misspelled november

    "december": 12,
    "dezember": 12,
    "dicembre": 12,  # Italian?
    "dic.": 12,  # misspelled dicembre
    "xii": 12,
    "prosinec": 12,  # Czeck?
    "dezemebr": 12,  # misspelled december
    "dez": 12,  # misspelled december
    "prosince": 12,  # misspelled prosinec
    "dez.": 12,  # misspelled december


    # Could not resolv even with guessing and LLMs
    "abt": 0,
    "yxi": 0,
    "iiii": 0,
    "xcix": 0,
    "viiii": 0,
}


def __remove_ambiguous_9(*date_tuple):
    assert len(date_tuple) == 3
    if date_tuple[0] == 9999:
        date_tuple = (0, date_tuple[1], date_tuple[2])
    if date_tuple[1] == 99:
        date_tuple = (date_tuple[0], 0, date_tuple[2])
    if date_tuple[2] == 99:
        date_tuple = (date_tuple[0], date_tuple[1], 0)
    return date_tuple


def __is_plausible_date(date_tuple):
    # TODO add 30-31 day checks.
    # TODO add leap year checks.
    # TODO add calendar reformation checks.
    if date_tuple[0] < 0 or date_tuple[0] > 2100:
        return False
    if date_tuple[1] < 0 or date_tuple[1] > 12:
        return False
    if date_tuple[2] < 0 or date_tuple[2] > 31:
        return False
    return True

# Tuple[int, int , int]
# Tuple[Tuple[int, int , int], Tuple[int, int , int]]
# Union[Tuple[Tuple[int, int , int], Tuple[int, int , int]], Tuple[int, int , int]]


def infer_date(date_str: str, fail_quietly: bool = False):
    """Tries to infer a date tuple from a string.

    Args:
        date_str (str): A unicode string that someone somewhen intended to be a date.
        fail_quietly (bool, optional): Whether uparseable dates should be considered 
        undefined or raise a ValueError. Defaults to False.

    Raises:
        ValueError: When parsing fails and fail_quietly is False.

    Returns:
        tuple(int, int, int): A tuple containing the year as the first element, the month 
        as the second and the day as the third. Unknown entries are replaced with 0.
    """
    date_str = anyascii.anyascii(date_str).lower(
    )  # TODO (anguelos) can we remove anyascii dependency?
    date_str = date_str.replace("wohl", "")  # We assume all is aproximate.
    date_str = " ".join(date_str.split())  # Remove extra spaces.
    # YYYMMDD we cant really know what is what but on 1000 Charters, that makes sence eg:25c52625b0576a7eec1a573cda314327/cei.xml
    if re.match("^[0-9]{7}$", date_str):
        date = __remove_ambiguous_9(int(date_str[:3]), int(
            date_str[3:5]), int(date_str[5:7]))
        if __is_plausible_date(date):
            return date

    if re.match("^1[0-9]{7}$", date_str):  # 1YYYMMDD assuming 1000-1999
        date = __remove_ambiguous_9(int(date_str[:4]), int(
            date_str[4:6]), int(date_str[6:8]))
        if __is_plausible_date(date):
            return date

    if re.match("^[0-9]{4}1[0-9]{3}$", date_str):  # DDMMYYYY
        date = __remove_ambiguous_9(int(date_str[4:]), int(
            date_str[4:6]), int(date_str[6:8]))
        if __is_plausible_date(date):
            return date

    if re.match("^[0-9\-,\.\s]{10}$", date_str):
        date = re.split("\-|\.|,|\s", date_str)
        if len(date) == 3 and len(date[2]) in (3, 4):
            date = date[::-1]
        date = [d if d != '' else '0' for d in date]
        if len(date[0]) == 4 and date[0][0] == "1":
            date = __remove_ambiguous_9(int(date[0]), int(date[1]), int(date[2]))
            if __is_plausible_date(date):
                return date
        else:
            return f"Unparsed_V1: '{date_str}', {repr(date)}"

    if re.match("^[0-9]+\.[0-9]+\.[0-9]+$", date_str):
        date = re.split("\.", date_str)
        if len(date) == 3 and len(date[2]) in (3, 4):
            date = date[::-1]
        if len(date[0]) in (3, 4) and len(date[1]) in (1, 2) and len(date[2]) in (1, 2):
            date = __remove_ambiguous_9(int(date[0]), int(date[1]), int(date[2]))
            if __is_plausible_date(date):
                return date
        else:
            return f"Unparsed_V2: '{date_str}', {repr(date)}"

    # The year is unknow, the date is broken nomater what.
    if re.match("^[0-9]*9{4}[0-9]*$", date_str):
        # TODO: (do we really care about months or days without years?)
        date = __remove_ambiguous_9(0, 0, 0)
        if __is_plausible_date(date):
            return date

    # Czeck dates.
    if re.match("^[0-9][0-9]?\.\s+[a-z]+\.?\s+[0-9]{3}[0-9]?$", date_str):
        date_list = date_str.split()
        if fail_quietly:
            date_list[1] = __month2num.get(date_list[1], 0)
        else:
            date_list[1] = __month2num[date_list[1]]
        date_list[0], date_list[2] = int(date_list[2]), int(
            date_list[0].replace(".", ""))
        date = __remove_ambiguous_9(*tuple(date_list))
        if __is_plausible_date(date):
            return date

    # EG '1288 dezember 22.'
    if re.match("^[0-9]{3}[0-9]?\s+[a-z]+\.?\s+[0-9][0-9]?\.?$", date_str):
        date_list = date_str.split()
        if fail_quietly:
            date_list[1] = __month2num.get(date_list[1], 0)
        else:
            date_list[1] = __month2num[date_list[1]]
        #date_list[1] = month2num[date_list[1]]
        date_list[0], date_list[2] = int(date_list[0]), int(
            date_list[2].replace(".", ""))
        date = __remove_ambiguous_9(*tuple(date_list))
        if __is_plausible_date(date):
            return date

    if re.match("^[0-9]{4}$", date_str):  # Only year.
        date = __remove_ambiguous_9(int(date_str), 0, 0)
        if __is_plausible_date(date):
            return date

    else:
        if fail_quietly:
            return (0, 0, 0)
        else:
            raise ValueError(f"Unparsable date: '{date_str}'")

