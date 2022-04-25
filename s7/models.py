"""Generic data model for configuration attributes."""
from pathlib import Path
from types import FunctionType
from typing import Any, ClassVar, Optional, Union

from pydantic import BaseModel, FileUrl, create_model, validator, PrivateAttr
import yaml


# XLS parser configuration
class Field(BaseModel):
    header: str
    range: str
    type: str
    regexp: Optional[str] = None
    unique: bool = False


class Workbook(BaseModel):
    workbook: FileUrl
    sheet: str
    data_range: str
    data: BaseModel

    @validator("workbook", pre=True)
    def convert_path_to_uri(value: str) -> str:
        """Convert a pathlib.Path to a URI."""
        if Path(value).resolve().exists and not value.startswith("file://"):
            return Path(value).resolve().as_uri()
        return str(value)


def create_config(filename: Union[str, Path]) -> Workbook:
    config = yaml.safe_load(Path(filename).resolve().read_text(encoding="utf8"))
    return create_model(
        "XLSConfig",
        data=(
            create_model(
                "XLSConfigData", **{}.fromkeys(config["data"], (Field, ...))
            ),
            ...,
        ),
        __base__ = Workbook,
    )(**config)


class SOFT7DataEntity(BaseModel):
    """Generic Data source entity"""

    def __getattribute__(self, name: str) -> Any:
        """Get an attribute.

        This function will _always_ be called whenever an attribute is accessed.
        """
        try:
            res = object.__getattribute__(self, name)
            if not name.startswith("_"):
                if name in object.__getattribute__(self, "__fields__"):
                    return res(name)
            return res
        except Exception as exc:
            raise AttributeError from exc


    class Config:
        """Pydantic configuration for 'SOFT7DataEntity'."""

        extra = "forbid"
        allow_mutation = False
        frozen = True
        validate_all = False
        # arbitrary_types_allowed = True
