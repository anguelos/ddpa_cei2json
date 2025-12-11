import re
import json
import glob
import sys
from collections import defaultdict, Counter
from typing import Dict, Tuple
from tqdm import tqdm


def tokenize(x):
    x = x.lower()
    x = re.sub(r"\s", " ", x)
    x = re.sub(r"[^a-z0-9\s]", "", x)
    return x.split()


def load_cei2json(root: str, filename: str, fsdb_glob: str = "*/*/*", verbose: bool = False) -> Tuple[Dict[str, list], Dict[str, list], Dict[str, list], Dict[str, str], Dict[str, str]]:
    #print("FILEGLOB:", f"{root}/*/*/*/{filename}")
    idx_files = {f.split("/")[-2]:f for f in glob.glob(f"{root}/{fsdb_glob}/{filename}")}
    abstract_idx = {}
    tenor_idx = {}
    tenor_word2md5 = defaultdict(lambda:[])
    abstract_word2md5 = defaultdict(lambda:[])
    word2md5 = defaultdict(lambda:[])
    if verbose:
        item_it = tqdm(idx_files.items())
    else:
        item_it = idx_files.items()
    for idx, f in item_it:
        with open(f) as fi:
            data = json.load(fi)
            abstract_idx[idx] = data["abstract"]
            tenor_idx[idx] = data["tenor"]
            tenor_words = tokenize(data["tenor"])
            abstract_words = tokenize(data["abstract"])
            for tenor_word in tenor_words:
                tenor_word2md5[tenor_word].append(idx)
                word2md5[tenor_word].append(idx)
            for abstract_word in abstract_words:
                abstract_word2md5[abstract_word].append(idx)
                word2md5[abstract_word].append(idx)
    for word, md5_list in tenor_word2md5.items():
        occurence_count = len(md5_list)
        tenor_word2md5[word] = sorted([(count/occurence_count, item) for item, count in Counter(md5_list).items()])
    for word, md5_list in abstract_word2md5.items():
        occurence_count = len(md5_list)
        abstract_word2md5[word] = sorted([(count/occurence_count, item) for item, count in Counter(md5_list).items()], reverse=True)
    for word, md5_list in word2md5.items():
        occurence_count = len(md5_list)
        abstract_word2md5[word] = sorted([(count/occurence_count, item) for item, count in Counter(md5_list).items()], reverse=True)
    word2md5.update(tenor_word2md5)
    word2md5.update(abstract_word2md5)
    if verbose:
        print("Sample Words:", list(word2md5.keys())[:100], file=sys.stderr)
    return tenor_word2md5, abstract_word2md5, word2md5, abstract_idx, tenor_idx

