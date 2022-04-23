from __future__ import annotations
from typing import Set
from dataclasses import dataclass
import yaml
import json

class DataProperty(BaseModel):    
    header: str
    range: str
    type: str
    regexp: str  
    
class XLSConfig(BaseModel):
    workbook: FileUrl
    sheet: str
    data_range: str
    data: AttrDict
    
@dataclass
class XLSParser:
    """ Parse excel documents given document configuration
        and an S7-entity
    """
    config: dict
    
def parse(config_filename):
    
    with open("config_filename", "r") as stream:
    try:
        config = yaml.safe_load(stream)
        xlsconf = XLSConfig(**config)
        for data in [DataProperty(**xlsconf.data[elem]) for elem in xlsconf.data]:   
            print (data)
        
    except yaml.YAMLError as exc:
        print(exc)
