"""Generate SOFT7 entities based on basic information:

1. Data source (DB, File, Webpage, ...)
2. Generic data source parser
3. Data source parser configuration
4. SOFT7 entity data model.

Parts 2 and 3 are together considered to produce the "specific parser".
Parts 1 through 3 are provided through a single dictionary based on the
`ResourceConfig` from `oteapi.models`.

"""
import json
from pathlib import Path
from typing import Any, Optional, Union

from oteapi.models import ResourceConfig
from otelib import OTEClient
from pydantic import AnyUrl, BaseModel, create_model, Field, validator
import yaml

from .models import SOFT7DataEntity, SOFT7EntityPropertyType


class HashableResourceConfig(ResourceConfig):
    """ResourceConfig, but hashable."""

    def __hash__(self) -> int:
        return hash(
            tuple(
                (field_name, field_value)
                if isinstance(field_value, (str, bytes, tuple, frozenset, int, float)) or field_value is None
                else (field_name, None)
                for field_name, field_value in self.__dict__.items()
            )
        )


class SOFT7EntityProperty(BaseModel):
    """A SOFT7 Entity property."""

    type_: SOFT7EntityPropertyType = Field(
        ...,
        description="A valid property type.",
        alias="type",
    )
    shape: Optional[list[str]] = Field(
        None, description="List of dimensions making up the shape of the property."
    )
    description: Optional[str] = Field(None, description="A human description of the property.")
    unit: Optional[str] = Field(
        None,
        description=(
            "The unit of the property. Would typically refer to other ontologies, like"
            " EMMO, QUDT or OM, or simply be a conventional symbol for the unit (e.g. "
            "'km/h'). In future releases unit may be changed to a class."
        ),
    )


class SOFT7Entity(BaseModel):
    """A SOFT7 Entity."""

    identity: AnyUrl = Field(..., description="The semantic reference for the entity.")
    description: str = Field("", description="A description of the entity.")
    dimensions: Optional[dict[str, str]] = Field(
        None,
        description=(
            "A dictionary or model of dimension names (key) and descriptions "
            "(value)."
        ),
    )
    properties: dict[str, SOFT7EntityProperty] = Field(..., description="A dictionary of properties.")

    @validator("properties")
    def shapes_and_dimensions(
        value: dict[str, SOFT7EntityProperty], values: dict[str, Any]
    ) -> dict[str, SOFT7EntityProperty]:
        """Ensure the shape values are dimensions keys."""
        errors: list[tuple[str, str]] = []
        if not values.get("dimensions", None):
            for property_name, property_value in value.items():
                if property_value.shape:
                    errors.append(
                        (
                            property_name,
                            "Cannot have shape; no dimensions are defined.",
                        )
                    )
        else:
            for property_name, property_value in value.items():
                if property_value.shape and not all(
                    dimension in values.get("dimensions", {})
                    for dimension in property_value.shape
                ):
                    errors.append(
                        (
                            property_name,
                            "Contains shape dimensions that are not defined in "
                            "'dimensions'.",
                        )
                    )
        if errors:
            raise ValueError(
                "Property shape(s) and dimensions don't match.\n"
                + "\n".join(f"  {name}\n    {msg}" for name, msg in errors)
            )
        return value


def _get_property(name: str, config: HashableResourceConfig, url: Optional[str] = None) -> Any:
    """Get a property."""
    client = OTEClient(url or "http://localhost:8080")
    data_resource = client.create_dataresource(**config.dict())
    result: dict[str, Any] = json.loads(data_resource.get())
    if name in result:
        return result[name]
    raise AttributeError(f"{name!r} could not be determined")


def _get_property_local(
    config: HashableResourceConfig,
) -> Any:
    """Get a property - local."""
    from s7.xlsparser import XLSParser

    parser = XLSParser(config.configuration).get()

    def __get_property_local(name: str) -> Any:
        if name in parser:
            return parser[name]

        raise ValueError(f"Could find no data for {name!r}")
    return __get_property_local


def create_entity(
    data_model: Union[SOFT7Entity, Path, str, dict[str, Any]],
    resource_config: Union[ResourceConfig, dict[str, Any]],
) -> BaseModel:
    """Create and return a SOFT7 entity wrapped as a pydantic model.

    Parameters:
        data_model: A SOFT7 data model entity or a string/path to a YAML file of the
            data model.
        resource_config: A
            [`ResourceConfig`](https://emmc-asbl.github.io/oteapi-core/latest/all_models/#oteapi.models.ResourceConfig)
            or a valid dictionary that can be used to instantiate it.

    Returns:
        A SOFT7 entity class wrapped as a pydantic data model.

    """
    if isinstance(data_model, (str, Path)):
        if not Path(data_model).resolve().exists:
            raise FileNotFoundError(f"Could not find a data model YAML file at {data_model!r}")
        data_model: dict[str, Any] = yaml.safe_load(Path(data_model).resolve().read_text(encoding="utf8"))
    if isinstance(data_model, dict):
        data_model = SOFT7Entity(**data_model)
    if not isinstance(data_model, SOFT7Entity):
        raise TypeError("data_model must be a 'SOFT7Entity'")

    if isinstance(resource_config, dict):
        resource_config = HashableResourceConfig(**resource_config)
    if not isinstance(resource_config, HashableResourceConfig):
        raise TypeError(
            "resource_config must be a 'ResourceConfig' (from oteapi-core)"
        )

    if any(property_name.startswith("_") for property_name in data_model.properties):
        raise ValueError("data model property names may not start with an underscore (_)")

    return create_model(
        "DataSourceEntity",
        **{
            property_name: (
                property_value.type_.py_cls,
                Field(
                    default_factory=lambda: _get_property_local(resource_config),
                    description=property_value.description or "",
                    title=property_name.replace(" ", "_"),
                    type=property_value.type_.py_cls,
                    **{
                        f"x-{field}": getattr(property_value, field)
                        for field in property_value.__fields__
                        if field not in ("description", "type_", "shape") and getattr(property_value, field)
                    }
                )
            ) for property_name, property_value in data_model.properties.items()
        },
        __module__ = __name__,
        __base__ = SOFT7DataEntity,
    )
