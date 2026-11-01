"""IMP-SCN-003: 시나리오 JSON 열거값(짧은 소문자) ⇄ proto 열거값 이름.

proto 열거형은 `<접두어>_UNSPECIFIED = 0`을 갖는다. JSON에는 접두어를 뺀 소문자를 쓴다.
예: ENTITY_KIND_GROUND_TARGET ⇄ "ground_target"
"""

from typing import Any

from google.protobuf.descriptor import Descriptor, EnumDescriptor, FieldDescriptor

# 내용을 그대로 두는 well-known 타입 (임의 JSON 객체)
_OPAQUE = {"google.protobuf.Struct", "google.protobuf.Value", "google.protobuf.ListValue"}


def enum_prefix(enum: EnumDescriptor) -> str:
    zero = enum.values_by_number[0].name
    if not zero.endswith("_UNSPECIFIED"):
        raise ValueError(f"{enum.full_name}: value 0 must be <PREFIX>_UNSPECIFIED")
    return zero[: -len("UNSPECIFIED")]


def short_to_full(enum: EnumDescriptor, short: str) -> str:
    full = enum_prefix(enum) + short.upper()
    if full not in enum.values_by_name or enum.values_by_name[full].number == 0:
        raise ValueError(f"{enum.full_name}: unknown value {short!r}")
    return full


def full_to_short(enum: EnumDescriptor, full: str) -> str:
    prefix = enum_prefix(enum)
    if not full.startswith(prefix):
        raise ValueError(f"{enum.full_name}: unexpected value {full!r}")
    return full[len(prefix):].lower()


def _walk(desc: Descriptor, obj: dict[str, Any], conv) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in obj.items():
        field = desc.fields_by_name.get(key)
        if field is None:
            out[key] = val  # json_format이 알 수 없는 필드로 거부한다
        elif field.type == FieldDescriptor.TYPE_ENUM:
            out[key] = [conv(field.enum_type, v) for v in val] if isinstance(val, list) else conv(field.enum_type, val)
        elif field.type == FieldDescriptor.TYPE_MESSAGE and field.message_type.full_name not in _OPAQUE:
            sub = field.message_type
            out[key] = [_walk(sub, v, conv) for v in val] if isinstance(val, list) else _walk(sub, val, conv)
        else:
            out[key] = val
    return out


def to_proto_json(desc: Descriptor, obj: dict[str, Any]) -> dict[str, Any]:
    """시나리오 JSON 객체 → json_format.ParseDict 입력"""
    return _walk(desc, obj, short_to_full)


def from_proto_json(desc: Descriptor, obj: dict[str, Any]) -> dict[str, Any]:
    """json_format.MessageToDict 출력 → 시나리오 JSON 객체"""
    return _walk(desc, obj, full_to_short)
