import sys
from typing import Dict, Generator, Optional, Tuple
import numpy as np
from collections import defaultdict, Counter
import glob
import json
import re
import pylelemmatize
from pylelemmatize import AbstractLemmatizer, LemmatizerBMP
import string
from tqdm import tqdm
from .cei2json import load_cei2json


class StandoffStrIdx:
    @staticmethod
    def __get_regex_escaped_lemmatizer_mapping(lemmatizer: AbstractLemmatizer) -> Dict[str, str]:
        mapping = lemmatizer.mapping_dict.copy()
        mapping.update({c:c for c in "[\\]^$.|?*+()-{}"})
        return LemmatizerBMP(mapping_dict=mapping)

    @classmethod
    def idxdict_to_npconcatenated(cls, md52txtdict: Dict[str, str], start_marker: str , stop_marker: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        all_txts = []
        np_idx = []
        np_md5 = []
        rev_idx: Dict[str, Tuple[int, int]] = {}
        cur_pos = 0
        for n, (md5_idx, txt) in enumerate(md52txtdict.items()):
            txt = f"{start_marker}{txt}{stop_marker}"
            all_txts.append(txt)
            idx = np.empty(len(txt), dtype=np.int32)
            idx[:] = n
            np_idx.append(idx)
            np_md5.append(md5_idx)
            rev_idx[md5_idx] = (cur_pos, cur_pos + len(txt))
            cur_pos += len(txt)
        np_idx = np.concatenate(np_idx, axis=0)
        print(repr(np_md5[0]))
        np_md5 = np.array(np_md5, dtype="<U32")
        all_txts = ''.join(all_txts)
        return all_txts, np_idx, np_md5, rev_idx

    @classmethod
    def from_md5dict(cls, md5dict: Dict[str, str], start_marker: str = "{\n", stop_marker: str = "\n}") -> "StandoffStrIdx":
        all_txts, np_idx, np_md5, rev_idx = cls.idxdict_to_npconcatenated(md5dict, start_marker=start_marker, stop_marker=stop_marker)
        return cls(all_txts, np_idx, np_md5, rev_idx, start_marker=start_marker, stop_marker=stop_marker)
    
    def __init__(self, all_txts: str, np_idx: np.ndarray, np_md5: np.ndarray, rev_idx: Dict[str, Tuple[int, int]], 
                 default_lemmatizer: Optional[LemmatizerBMP]= None, start_marker="@(@", stop_marker="@)@"):
        self.all_txts = all_txts
        self.np_idx = np_idx
        self.np_md5 = np_md5
        self.rev_idx = rev_idx
        self.start_marker = start_marker
        self.stop_marker = stop_marker
        if default_lemmatizer is None:
            self.default_lemmatizer = pylelemmatize.LemmatizerBMP({c:c for c in string.printable})
        else:
            self.default_lemmatizer = default_lemmatizer
        self.default_regex_lemmatizer = self.__get_regex_escaped_lemmatizer_mapping(self.default_lemmatizer)
    
    def get_tttf(self, md5_id:str, start_end: Tuple[int, int], lemmatizer: Optional[LemmatizerBMP] = None) -> str:
        md5_start, md5_stop = self.rev_idx[md5_id]
        md5_start = max(md5_start, len(self.start_marker))
        md5_stop = min(md5_stop, len(self.all_txts)-len(self.stop_marker))
        abs_start = md5_start + start_end[0]
        abs_stop = md5_start + start_end[1]
        if lemmatizer is not None:
            return lemmatizer(self.all_txts[abs_start:abs_stop])
        else:
            return self.all_txts[abs_start:abs_stop]

    def find(self, pattern: str, lemmatizer: Optional[LemmatizerBMP] = None) -> Generator[Tuple[str, Tuple[int, int]], None, None]:
        if lemmatizer is None:
            lemmatizer = self.default_lemmatizer
            regex_lemmatizer = self.default_regex_lemmatizer    
        else:
            regex_lemmatizer = self.__get_regex_escaped_lemmatizer_mapping(lemmatizer)
        pattern = regex_lemmatizer(pattern)
        corpus = lemmatizer(self.all_txts)
        for regex_match in re.finditer(pattern, corpus):
            loc_start, loc_end = regex_match.start(), regex_match.end()
            md5_id = self.np_md5[self.np_idx[loc_start]]
            md5_start, _ = self.rev_idx[md5_id]
            yield (md5_id, (loc_start - md5_start, loc_end - md5_start))
    
    def __len__(self) -> int:
        return len(self.all_txts)
    
    def __str__(self):
        return f"StandoffStrIdx(len={len(self.all_txts)}, n_docs={len(self.rev_idx)})"


if __name__ == "__main__":
    import time
    t=time.time()
    ll = LemmatizerBMP({c:c.lower() for c in string.printable})
    tenor_word2md5, abstract_word2md5, word2md5, abstract_idx, tenor_idx = load_cei2json(root="/home/anguelos/data/monasterium/", filename="CH.cei2json.json", verbose=True)
    print(f"Loaded in {time.time()-t:.5} sec.")
    standoff_tenor_idx = StandoffStrIdx.from_md5dict(tenor_idx)
    print(f"Tenor Index created in {time.time()-t:.5} sec. Sz: {len(standoff_tenor_idx)}")
    standoff_abstract_idx = StandoffStrIdx.from_md5dict(abstract_idx)
    print(f"Abstract Index created in {time.time()-t:.5} sec. Sz: {len(standoff_abstract_idx)}")

    tenor_results = list(standoff_tenor_idx.find("gegen", lemmatizer=ll))
    print(f"Found {len(tenor_results)} results in {time.time()-t:.5} sec.")
    for n, (id, (start, end)) in enumerate(tenor_results[:30]):
        print(f"{n:<5} {id}: {standoff_tenor_idx.get_tttf(id, (start - 10, end + 10))}")

    abstract_results = list(standoff_abstract_idx.find("seb.*stian", lemmatizer=ll))
    print(f"Found {len(abstract_results)} results in {time.time()-t:.5} sec.")
    for n, (id, (start, end)) in enumerate(abstract_results[:30]):
        print(f"{n:<5} {id}: {standoff_abstract_idx.get_tttf(id, (start - 10, end + 10))}")
