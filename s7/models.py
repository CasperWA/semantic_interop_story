"""Generic data model for configuration attributes."""
from pydantic import BaseModel, FileUrl, create_model
import yaml

# XLS parser configuration
class Field(BaseModel):    
    header: str
    range: str
    type: str
    regexp: str

class Workbook(BaseModel):
    workbook: FileUrl
    sheet: str
    data_range: str
    data: BaseModel
    
def create_config(filename):    
    with open(filename) as stream:
        try:
            config = yaml.safe_load(stream)        
            XLSConfig = create_model(
                'XLSConfig',
                data = (create_model(
                    'XLSConfigData',
                    **{}.fromkeys(config['data'], (Field, ...))
                ), ...),
                __base__ = Workbook
            )

            xlsconf = XLSConfig(**config)                
            return xlsconf
        except yaml.YAMLError as err:
            print(err)
