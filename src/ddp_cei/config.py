import importlib.resources as resources
import json
from pathlib import Path
import os
from typing import List


def config() -> dict:
    with resources.files("ddp_cei").joinpath("default/config_service.json").open("r") as f:
        defaults = json.load(f)
    config_paths = defaults["CONFIG_PATHS"].copy()
    
    res = defaults
    for config_path in config_paths:
        if Path(config_path).exists():
            with open(config_path, "r") as f:
                user_conf = json.load(f)
            res.update(user_conf)
    res['CONFIG_PATHS'] = resolv_config_paths(config_paths)
    return res


def resolv_config_paths(config_paths: List[str]) -> List[str]:
    APP_DIR = Path(__file__).resolve().parent.parent.parent
    HOME = Path.home()
    config_paths = [p.replace("${APP_DIR}", str(APP_DIR)) for p in config_paths]
    config_paths = [p.replace("${HOME}", str(HOME)) for p in config_paths]