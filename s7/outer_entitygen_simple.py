"""Generate SOFT7 (outer mapping) entities based on basic information:

1. SOFT7 entity data model.
2. Semantic Mapping.
3. Internal data source SOFT7 entity.

"""
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Union, Callable

from IPython import display
from oteapi.models import ResourceConfig
from pydantic import create_model, Field
import yaml

from s7 import known_functions
from .models import SOFT7DataEntity
from .graph import Graph

TEST_KNOWLEDGE_BASE = Graph(
    [
        ("imp_to_eis", "isA", "function"),
        ("imp_to_eis", "expects", "ImpedanceOhm"),
        ("imp_to_eis", "outputs", "EISEfficiency"),
        ("imp_to_lpr", "isA", "function"),
        ("imp_to_lpr", "expects", "ImpedanceLogOhm"),
        ("imp_to_lpr", "outputs", "LPREfficiency"),
        ("ImpedanceOhm", "isA", "Resistance"),
        ("ImpedanceLogOhm", "isA", "Resistance"),
        ("EISEfficiency", "isA", "InhibitorEfficiency"),
        ("LPREfficiency", "isA", "InhibitorEfficiency"),
        ("Resistance", "isA", "Parameter"),
        ("InhibitorEfficiency", "isA", "Output"),
        ("cas_to_smiles", "isA", "function"),
        ("cas_to_smiles", "expects", "CAS#"),
        ("cas_to_smiles", "outputs", "SMILES"),
    ]
)


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


class SOFT7EntityPropertyType(str, Enum):
    """Property type enumeration."""

    STR = "string"
    FLOAT = "float"

    @property
    def py_cls(self) -> type:
        """Get the equivalent Python cls."""
        return {
            self.STR: str,
            self.FLOAT: float,
        }[self]


def composite_functions(*func):

    outer_func = func[0]

    def composite(f, g):
        return lambda x: f(g(x))

    for function_ in func:
        composite()
    return [composite(outer_func, composite(_)) for _ in func[1:]]

def _get_property_local(
    graph: Graph,
) -> Callable[[str], Any]:
    """Get a property - local."""
    predicate_filter = ["mapsTo", "outputs", "expects", "hasProperty"]

    def __get_property(name: str) -> Any:
        path = graph.path(f"outer.{name}", "inner", predicate_filter)
        print(path)
        if len(path) > 1:
            raise RuntimeError("Found more than one path through the graph !")
        path = path[0]

        functions = [
            _ for _ in path
            if _ in [s for s, _, _ in graph.match(None, "isA", "function")]
        ]
        print(functions)

        # callable_functions = 

        if len(functions) > 1:
            raise RuntimeError("Currently only supports running a single function, sorry.")

        function_name = functions[0]

        function_expects = [
            expects for _, _, expects in graph.match(function_name, "expects", None)
        ]
        print(function_expects)

        function_inputs: list[str] = []
        for function_expect in function_expects:
            function_input = [input_ for input_, _, _ in graph.match(None, "mapsTo", function_expect)]
            if len(function_input) > 1:
                raise RuntimeError(f"Expected exactly 1 mapping to {function_expect}, instead found {len(function_input)} !")
            function_inputs.append(function_input[0])

        print(function_inputs)

        if len(function_inputs) > 1:
            raise RuntimeError("Currently only supports functions with a single input, sorry.")

        input_ = [
            function_ for _, _, function_ in graph.match(function_inputs[0], "get", None)
        ][0]
        return [function_ for _, _, function_ in graph.match(function_name, "executes", None)][0](
            input_(function_inputs[0].split(".")[-1])
        )

    return __get_property


def create_outer_entity(
    data_model: Union[Path, str, dict[str, Any]],
    inner_entity: SOFT7DataEntity,
    mapping: Union[Graph, Iterable[tuple[str, str, str]]],
) -> SOFT7DataEntity:
    """Create and return a SOFT7 entity wrapped as a pydantic model.

    Parameters:
        data_model: A SOFT7 data model entity or a string/path to a YAML file of the
            data model.
        inner_entity: The data source SOFT7 entity.
        mapping: A sequence of RDF triples representing the mapping.

    Returns:
        A SOFT7 entity class wrapped as a pydantic data model.

    """
    if isinstance(data_model, (str, Path)):
        if not Path(data_model).resolve().exists:
            raise FileNotFoundError(f"Could not find a data model YAML file at {data_model!r}")
        data_model: dict[str, Any] = yaml.safe_load(Path(data_model).resolve().read_text(encoding="utf8"))
    if not isinstance(data_model, dict):
        raise TypeError("data_model must be a dict")

    if not isinstance(inner_entity, SOFT7DataEntity):
        raise TypeError("inner_entity must be a SOFT7DataEntity")

    if isinstance(mapping, Iterable):
        mapping = Graph(list(mapping))
    if not isinstance(mapping, Graph):
        raise TypeError("mapping must be a Graph")

    if any(
        property_name.startswith("_")
        for property_name in data_model.get("properties", {})
    ):
        raise ValueError(
            "data model property names may not start with an underscore (_)"
        )

    # Create "complete" local graph
    local_graph = Graph(
        [
            ("inner", "isA", "DataSourceEntity"),
            ("outer", "isA", "OuterEntity"),
            ("DataSourceEntity", "isA", "SOFT7DataEntity"),
            ("OuterEntity", "isA", "SOFT7DataEntity"),
        ]
    )
    for s, p, o in mapping.triples:
        local_graph.append((s, p, o))
        split_subject = s.split(".")
        if split_subject[0] == "inner":
            for triple in [
                (split_subject[0], "hasProperty", s),
                (s, "get", lambda property_name: getattr(inner_entity, property_name)),
            ]:
                local_graph.append(triple)

    for triple in TEST_KNOWLEDGE_BASE.triples:
        local_graph.append(triple)

    # Generate lambda functions for properties
    # functions: list[str] = [
    #     function_name for function_name, _, _ in mapping.match(p="isA", o="function")
    # ]
    for function_name, _, _ in local_graph.match(p="isA", o="function"):
        missing_functions = []
        if not hasattr(known_functions, function_name):
            missing_functions.append(function_name)
        else:
            local_graph.append(
                (
                    function_name,
                    "executes",
                    getattr(known_functions, function_name),
                )
            )
        if missing_functions:
            raise ValueError(
                f"{missing_functions} not found in known functions !"
            )

    display.display(local_graph.plot())

    return create_model(
        "OuterEntity",
        **{
            property_name: (
                SOFT7EntityPropertyType(property_value.get("type", "")).py_cls,
                Field(
                    default_factory=lambda: _get_property_local(local_graph),
                    description=property_value.get("description", ""),
                    title=property_name.replace(" ", "_"),
                    type=SOFT7EntityPropertyType(property_value.get("type", "")).py_cls,
                )
            ) for property_name, property_value in data_model.get("properties", {}).items()
        },
        __module__ = __name__,
        __base__ = SOFT7DataEntity,
    )
