"""
Quick helper for lightweight typed models in Django.

Django models don't work well with typehints. This uses a quick
wrapper to give dataclass style prompts on incorrect types or missing fields
on class construction.

For a basic conversion, you just need to change to use the
field wrappper. This lets django fields be used while not conflicting
with the dataclass typehint.

so rather than

class ExampleModel(models.Model):
    field1 = models.CharField(max_length=255)
    field2 = models.IntegerField()

You would write:

class ExampleModel(TypedModel):
    field1: str = field(CharField, max_length=255)
    field2: int = field(IntegerField)

As with pydantic, the field defintions can be moved to annotations.
Here we just use the regular django fields as the annotations.
We can also use pydantic validations in the annotations.


e.g.

CharField = Annotated[
    str, models.CharField(max_length=255), StringConstraints(max_length=255)
    ]
IntegerField = Annotated[int, models.IntegerField()]

class ExampleModel(TypedModel):
    field1: CharField
    field2: IntegerField

As in dataclasses, default can be specified either in the field definition.

class ExampleModel(TypedModel):
    field1: CharField = field(CharField, max_length=255, default="default")
    field2: IntegerField

Or just by specifying the default in the class definition

class ExampleModel(TypedModel):
    field1: CharField = "default"
    field2: IntegerField = 15


Pydantic validation is only run on model creation when not made by the database.
This is to avoid validation errors when loading from the database.

When modifying properties of the model, the pydantic model is kept in sync and will
validate the changes.

e.g.

e.g.

ExampleModel(field1="test") # will validate
ExampleModel(field1="test", field2=15) # will validate
ExampleModel(field1="test", field2="15") # will raise a validation error

model = ExampleModel(field1="test")
model.field2 = 15 # will validate
model.field2 = "15" # will raise a validation error

"""

from __future__ import annotations

import ast
import datetime
import sys
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import (
    Annotated,
    Any,
    Callable,
    ClassVar,
    ForwardRef,
    Generic,
    NamedTuple,
    Optional,
    ParamSpec,
    Type,
    TypeVar,
    Union,
    dataclass_transform,
    get_args,
    get_origin,
)

from django.core.files import File
from django.db import models
from django.forms.models import model_to_dict

from pydantic import BaseModel, ConfigDict, create_model
from pydantic.fields import Field as PydanticField
from pydantic.fields import FieldInfo

T = TypeVar("T")
FieldType = TypeVar(
    "FieldType",
    bound=models.Field,
)
ModelType = TypeVar(
    "ModelType",
    bound=models.Model,
)
P = ParamSpec("P")


class DummyManager(models.Manager, Generic[ModelType]):
    def __class_getitem__(cls, item: Any) -> Any:
        return item

    def all(self) -> models.QuerySet[ModelType]: ...

    def filter(self, *args: Any, **kwargs: Any) -> models.QuerySet[ModelType]: ...

    def get(self, *args: Any, **kwargs: Any) -> ModelType: ...


AllowJustAnnotated = object()

ForeignKey = Annotated[
    ModelType, lambda x: field(models.ForeignKey, to=x, on_delete=models.CASCADE)
]
DoNothingForeignKey = Annotated[
    ModelType,
    lambda x: field(
        models.ForeignKey, to=x, on_delete=models.DO_NOTHING, db_constraint=False
    ),
]
ManyToMany = Annotated[
    DummyManager[ModelType],
    lambda x: field(models.ManyToManyField, to=x),
    AllowJustAnnotated,
]

DummyOneToMany = Annotated[DummyManager[ModelType], AllowJustAnnotated]
DummyManyToMany = Annotated[DummyManager[ModelType], AllowJustAnnotated]


Dummy = Annotated[T, AllowJustAnnotated]

# Demonstration of storing model fields in Annotations, plus mixing with
# pydantic validations
PrimaryKey = Annotated[
    Optional[int], models.BigAutoField(primary_key=True), PydanticField(default=None)
]
OptionalDateTimeField = Annotated[
    Optional[datetime.datetime],
    models.DateTimeField(null=True),
    PydanticField(default=None),
]
CharField = Annotated[
    str, models.CharField(max_length=255), PydanticField(max_length=255)
]
TextField = Annotated[str, models.TextField()]
IntegerField = Annotated[int, models.IntegerField()]
PositiveIntegerField = Annotated[
    int, models.PositiveIntegerField(), PydanticField(gt=0)
]
DateTimeField = Annotated[datetime.datetime, models.DateTimeField()]
DateField = Annotated[datetime.date, models.DateField()]
SlugField = Annotated[str, models.SlugField(max_length=255)]
EmailField = Annotated[str, models.EmailField(max_length=255)]
FileField = Annotated[File, models.FileField(upload_to="uploads")]
ImageField = Annotated[File, models.ImageField(upload_to="uploads")]
BinaryField = Annotated[bytes, models.BinaryField()]
BooleanField = Annotated[bool, models.BooleanField()]
DecimalField = Annotated[Decimal, models.DecimalField(max_digits=10, decimal_places=2)]
FloatField = Annotated[float, models.FloatField()]
DurationField = Annotated[datetime.timedelta, models.DurationField()]
BinaryField = Annotated[bytes, models.BinaryField()]
JSONField = Annotated[Union[list, dict], models.JSONField()]

# Lookup table for field types.
types_to_fields: dict[type | str, Annotated] = {
    str: CharField,
    int: IntegerField,
    bool: BooleanField,
    Decimal: DecimalField,
    float: FloatField,
    bytes: BinaryField,
    list: JSONField,
    dict: JSONField,
    datetime.datetime: DateTimeField,
    datetime.date: DateField,
    datetime.timedelta: DurationField,
    File: FileField,
}


def convert_to_forward_refs(
    type_hint: str,
    local_scope: Optional[dict[str, Any]] = None,
    global_scope: Optional[dict[str, Any]] = None,
) -> Any:
    """
    Similar to pydantic behind the scenes, get
    objects from string typehints that fails to using forward refs.
    Allows access to global and local scope for resolving type hints.
    """
    if global_scope is None:
        global_scope = globals()
    if local_scope is None:
        local_scope = locals()

    def _convert_type(node: ast.AST) -> Any:
        if isinstance(node, ast.Subscript):
            value = _convert_type(node.value)
            slice_val = _convert_type(node.slice)
            return value[slice_val]
        elif isinstance(node, ast.Name):
            type_name = node.id
            try:
                return eval(type_name, global_scope, local_scope)
            except NameError:
                return ForwardRef(type_name)
        elif isinstance(node, ast.Attribute):
            value = _convert_type(node.value)
            return getattr(value, node.attr)
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Tuple):
            return tuple(_convert_type(elt) for elt in node.elts)
        elif isinstance(node, ast.List):
            return [_convert_type(elt) for elt in node.elts]
        elif isinstance(node, ast.Call):
            return None
        elif isinstance(node, ast.BinOp):
            # for union style type hints
            # str | int
            left = _convert_type(node.left)
            right = _convert_type(node.right)
            # and recombine as a union type
            return Union[left, right]
        else:
            raise ValueError(f"Unsupported AST node type: {type(node)}")

    node: ast.AST = ast.parse(type_hint, mode="eval").body
    return _convert_type(node)


def enum_to_choices(en: Type[StrEnum]) -> list[tuple[str, str]]:
    return [(enum_.value, enum_.value.title().replace("_", " ")) for enum_ in en]


def intenum_to_choices(en: Type[IntEnum]) -> list[tuple[int, str]]:
    return [(enum_.value, enum_.name.title().replace("_", " ")) for enum_ in en]


class ExtraKwargs(NamedTuple):
    kwargs: dict[str, Any]


def blank_callable(*args: Any, **kwargs: Any) -> Any:
    pass


def related_name(related_name: str) -> Any:
    """
    The trick we're doing here is we're passing back the field,
    but related_name is not registered with dataclass transform.
    Meaning it is seen as a default value.
    This means the dataclass isn't upset a value isn't being passed to it.
    As we can do *either* field or field_id in django.
    If you always want to use field rather than field_id, use the longer
    field(related_name="name") - and this will require the value to be set.
    """
    return field(related_name=related_name)


def field(
    model_class: Callable[P, FieldType] = blank_callable,
    null: Optional[bool] = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> Any:
    """
    Helper function to hide Field creation - but return Any
    So the type checker doesn't complain about the return type
    and you can specify the specify type of the item as a typehint.
    """
    if args:
        raise ValueError("Positional arguments are not supported")
    if null is not None:
        kwargs["null"] = null
    if model_class == blank_callable:
        return ExtraKwargs(kwargs)
    elif isinstance(model_class, type) and issubclass(model_class, models.Field):
        # convert any forwardrefs values back to strings (foreign keys accept these)
        unpacked_kwargs = {
            k: v.__forward_arg__ if isinstance(v, ForwardRef) else v
            for k, v in kwargs.items()
        }
        klass = model_class(**unpacked_kwargs)
        klass.__original_kwargs__ = unpacked_kwargs  # type: ignore
        return klass
    else:
        raise ValueError(f"Invalid model class {model_class}")


def pure_pydantic_annotations(type: Any, allow_bare_annotation: bool) -> Any:
    """
    Pydantic constructor doesn't like having the django
    fields in there. This function removes them.
    """

    # If not annotated - back we go
    if get_origin(type) not in [Annotated, Union, Optional]:
        return Annotated[type, PydanticField()]

    # If Annotated - we need to look at the metadata
    # and remove anything that is an instance of models.Field

    base_type, *metadata = get_args(type)
    new_metadata = [m for m in metadata if not isinstance(m, models.Field)]

    # If there is *nothing* left, return the the basic type
    if len(new_metadata) == 0:
        return Annotated[base_type, PydanticField()]

    # check the first new_metadata is FieldInfo
    if isinstance(new_metadata[0], FieldInfo) is False:
        if allow_bare_annotation:
            return None
        else:
            raise ValueError("First metadata must be a FieldInfo")

    # If there is anything else left, return that as a new Annotated
    return Annotated[tuple([base_type] + new_metadata)]  # type: ignore


def copy_field(field: models.Field) -> models.Field:
    """
    When moving things from annotations to construct django fields
    Need to copy the field so different field objects are assigned.
    """
    name, import_path, args, kwargs = field.deconstruct()
    return field.__class__(*args, **kwargs)


FieldType = TypeVar("FieldType", bound=models.Field)


def merge_field_instances(fields: list[FieldType], kwargs: dict[str, Any]) -> FieldType:
    all_kwargs = {}
    for field in fields:
        if hasattr(field, "__original_kwargs__"):
            all_kwargs.update(field.__original_kwargs__)  # type: ignore
        else:
            name, import_path, args, field_kwargs = field.deconstruct()
            all_kwargs.update(field_kwargs)
    all_kwargs.update(kwargs)
    obj = fields[0].__class__(**all_kwargs)
    obj.__original_kwargs__ = all_kwargs  # type: ignore
    return obj


@dataclass_transform(kw_only_default=True, field_specifiers=(field,))
class TypedModelBase(models.base.ModelBase):
    def __new__(cls, name: str, bases: tuple[type], dct: dict[str, Any], **kwargs: Any):
        """
        Thie goal of this wrapper is to construct a
        normal django model while giving the relevant typehints.

        This does several things:
        - Extracts the fields from the annotations
        - Or where a field has been directly specified
        - Merges in any defaults specified
        - Creates a parallel pydantic model for validation

        """

        fields = {}
        pydantic_fields = {}
        annotations = dct.get("__annotations__", {})

        caller_globals = sys._getframe(1).f_globals  # type: ignore
        all_globals = {**globals(), **caller_globals}

        # Extract valid fields from annotations
        for field_name, field_type in annotations.items():
            potential_fields: list[models.Field] = []
            append_to_field = {}
            if isinstance(field_type, str):
                field_type = convert_to_forward_refs(field_type, locals(), all_globals)

            # expand out the preconstructed ones
            if field_type in types_to_fields:
                field_type = types_to_fields[field_type]

            allow_bare_annotation = False
            if get_origin(field_type) is Annotated:
                main_field, *metadata_list = get_args(field_type)
                for metadata in metadata_list:
                    if isinstance(metadata, models.Field):
                        # need to copy the field so different field objects are assigned
                        # to different items
                        potential_fields.append(copy_field(metadata))
                    elif callable(metadata):
                        response = metadata(main_field)
                        if isinstance(response, models.Field):
                            potential_fields.append(response)
                    elif metadata is AllowJustAnnotated:
                        allow_bare_annotation = True

            dct_value = dct.get(field_name, models.NOT_PROVIDED)
            if isinstance(dct_value, models.Field):
                potential_fields.append(dct_value)
            elif isinstance(dct_value, ExtraKwargs):
                append_to_field |= dct_value.kwargs
            else:
                # assume assigned is default value
                append_to_field["default"] = dct_value

            # if is classvar, let's just move on
            if get_origin(field_type) is ClassVar:
                continue

            if len(potential_fields) == 0:
                if isinstance(field_type, type) and issubclass(field_type, StrEnum):
                    potential_fields.append(
                        models.CharField(
                            max_length=255,
                            choices=enum_to_choices(field_type),
                        )
                    )
                elif isinstance(field_type, type) and issubclass(field_type, IntEnum):
                    potential_fields.append(
                        models.IntegerField(choices=intenum_to_choices(field_type))
                    )
                else:
                    if allow_bare_annotation is False:
                        raise ValueError(f"No field found for {field_name}")
            elif len(potential_fields) > 1:
                # check all same type
                types = [type(f) for f in potential_fields]
                if len(set(types)) != 1:
                    raise ValueError(
                        f"Multiple fields found for {field_name}, of different types"
                    )
                valid_field = merge_field_instances(potential_fields, kwargs={})
            if potential_fields:
                # might still be blank if we've allow_bare_annotation
                valid_field = potential_fields[0]
                if append_to_field:
                    valid_field = merge_field_instances(
                        [valid_field], kwargs=append_to_field
                    )
                fields[field_name] = valid_field
                default_value = getattr(valid_field, "default", models.NOT_PROVIDED)
                if default_value is not models.NOT_PROVIDED:
                    pydantic_fields[field_name] = (
                        pure_pydantic_annotations(
                            field_type, allow_bare_annotation=True
                        ),
                        default_value,
                    )
                else:
                    pydantic_fields[field_name] = pure_pydantic_annotations(
                        field_type, allow_bare_annotation=True
                    )

        dct.update(fields)

        pydantic_fields["model_config"] = ConfigDict(validate_assignment=True)
        pydantic_fields["__base__"] = DjangoAdjustedBaseModel
        pydantic_fields = {
            k: v for k, v in pydantic_fields.items() if v not in [(None, None), None]
        }
        pydantic_model_class = create_model(name, **pydantic_fields)
        dct["_inner_pydantic_class"] = pydantic_model_class

        if kwargs:
            dct["Meta"] = type("Meta", (dct.get("Meta", type),), kwargs)
        return super().__new__(cls, name, bases, dct)


class DjangoAdjustedBaseModel(BaseModel):
    id: Optional[int] = None
    pk: Optional[int] = None


class TypedModel(models.Model, metaclass=TypedModelBase, abstract=True):
    id: PrimaryKey = None
    _inner_pydantic_class: ClassVar[Type[DjangoAdjustedBaseModel]]

    def __init__(self, *args, **kwargs):
        """
        Validate the item via pydantic but return a django model
        """
        cls = self.__class__
        pydantic_instance = None
        # don't validate when the database creates them
        if len(args) == 0 and len(kwargs) > 0:
            pydantic_instance = cls._inner_pydantic_class(**kwargs)
        super().__init__(*args, **kwargs)
        if pydantic_instance is not None:
            pydantic_instance = cls._inner_pydantic_class.model_construct(
                **model_to_dict(self)
            )
        self._inner_pydantic_instance = pydantic_instance

    def get_pydantic(self) -> DjangoAdjustedBaseModel:
        if not hasattr(self, "_inner_pydantic_instance"):
            raise ValueError("Pydantic instance not created")
        if self._inner_pydantic_instance is None:
            raise ValueError("Pydantic instance is None")
        return self._inner_pydantic_instance

    def __setattr__(self, name: str, value: Any) -> None:
        # keep pydantic and django in sync to trigger validation
        if hasattr(self, "_inner_pydantic_instance"):
            try:
                setattr(self._inner_pydantic_instance, name, value)
            except AttributeError:
                pass
        return super().__setattr__(name, value)


class TypedUnmanagedModel(TypedModel, abstract=True, managed=False):
    """
    Managed is False - used to connect to existing databases but
    use djangoish syntax
    """
