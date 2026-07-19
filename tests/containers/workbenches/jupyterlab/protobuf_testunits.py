"""Protobuf UPB / endian smoke tests, run inside images by libraries_test.py.

Why this suite exists: image tests that only `import feast` / `feast version`
passed on protobuf 7.35.1 UPB while proto2 packed repeated enums silently
decoded as [0, 0, 0] on s390x (missing MungeInt32 in DecodeEnumPacked). That
alone justifies a dedicated roundtrip gate. Fixed-width scalars (explicit
little-endian on the wire) and map keys (separate BE hash/munge paths, e.g.
BoolKeys) are the next highest-value probes beyond that regression.

Force UPB before any google.protobuf import so we exercise the C extension that
has historically broken on s390x (AIPCC-13675), not a pure-Python fallback that
would give false confidence.
"""

# Image-only deps; not installed in the notebooks repo venv.
# pyright: reportMissingImports=false, reportMissingModuleSource=false

from __future__ import annotations

import os
import unittest

# Must be set before importing google.protobuf (impl is chosen at import time).
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "upb"

# ruff: noqa: PLC0415 `import` should be at the top-level of a file


def _make_message(
    *,
    syntax: str,
    field_name: str = "f",
    field_number: int = 1,
    field_type: int,
    label: int,
    packed: bool | None = None,
    type_name: str | None = None,
    enum_values: list[tuple[str, int]] | None = None,
):
    """Build a dynamic message class via FileDescriptorProto (no .proto file)."""
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

    fp = descriptor_pb2.FileDescriptorProto()
    fp.name = f"dyn_{syntax}_{field_name}.proto"
    fp.package = "dyn"
    fp.syntax = syntax

    if enum_values is not None:
        en = fp.enum_type.add()
        en.name = "E"
        for name, number in enum_values:
            v = en.value.add()
            v.name = name
            v.number = number
        type_name = ".dyn.E"

    msg = fp.message_type.add()
    msg.name = "M"
    f = msg.field.add()
    f.name = field_name
    f.number = field_number
    f.label = label
    f.type = field_type
    if type_name is not None:
        f.type_name = type_name
    if packed is not None:
        f.options.packed = packed

    pool = descriptor_pool.DescriptorPool()
    pool.Add(fp)
    return message_factory.GetMessageClass(pool.FindMessageTypeByName("dyn.M"))


def _roundtrip_scalar(msg_cls, attr: str, value) -> None:
    x = msg_cls()
    setattr(x, attr, value)
    y = msg_cls()
    y.ParseFromString(x.SerializeToString())
    got = getattr(y, attr)
    if got != value:
        raise AssertionError(f"roundtrip {attr}: expected {value!r}, got {got!r}")


def _roundtrip_repeated(msg_cls, attr: str, values: list) -> None:
    x = msg_cls()
    getattr(x, attr).extend(values)
    wire = x.SerializeToString()
    y = msg_cls()
    y.ParseFromString(wire)
    got = list(getattr(y, attr))
    if got != values:
        raise AssertionError(f"roundtrip repeated {attr}: expected {values!r}, got {got!r}, wire={wire.hex()}")


class TestProtobufUpb(unittest.TestCase):
    """Cross-platform protobuf encoding checks aimed at UPB / big-endian bugs."""

    @classmethod
    def setUpClass(cls):
        from google.protobuf.internal import api_implementation as api

        impl = api.Type()
        print(f"protobuf impl={impl} (forced PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=upb)")
        assert impl == "upb", (
            f"Expected protobuf impl=upb after PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=upb, got {impl!r}. "
            "Binary UPB extension missing from the wheel — pin/lift is not exerciseable."
        )
        import google.protobuf as pb

        print(f"protobuf version={pb.__version__}")
        cls.pb_version = pb.__version__

    def test_timestamp_pb2(self):
        """Feast / AIPCC-13675 crash path: AddSerializedFile + Timestamp."""
        import google.protobuf.timestamp_pb2 as t

        ts = t.Timestamp()
        ts.GetCurrentTime()
        self.assertGreater(ts.seconds, 0)
        again = t.Timestamp()
        again.ParseFromString(ts.SerializeToString())
        self.assertEqual(again.seconds, ts.seconds)
        self.assertEqual(again.nanos, ts.nanos)
        print("TIMESTAMP=PASS", ts.seconds)

    def test_well_known_types_roundtrip(self):
        from google.protobuf import (
            any_pb2,
            duration_pb2,
            empty_pb2,
            field_mask_pb2,
            struct_pb2,
            wrappers_pb2,
        )
        from google.protobuf.timestamp_pb2 import Timestamp

        dur = duration_pb2.Duration(seconds=3, nanos=500)
        dur2 = duration_pb2.Duration()
        dur2.ParseFromString(dur.SerializeToString())
        self.assertEqual((dur2.seconds, dur2.nanos), (3, 500))

        empty = empty_pb2.Empty()
        self.assertEqual(empty_pb2.Empty().SerializeToString(), empty.SerializeToString())

        mask = field_mask_pb2.FieldMask(paths=["a.b", "c"])
        mask2 = field_mask_pb2.FieldMask()
        mask2.ParseFromString(mask.SerializeToString())
        self.assertEqual(list(mask2.paths), ["a.b", "c"])

        st = struct_pb2.Struct()
        st["k"] = 1.5
        st2 = struct_pb2.Struct()
        st2.ParseFromString(st.SerializeToString())
        self.assertEqual(st2["k"], 1.5)

        iv = wrappers_pb2.Int64Value(value=0x0102030405060708)
        iv2 = wrappers_pb2.Int64Value()
        iv2.ParseFromString(iv.SerializeToString())
        self.assertEqual(iv2.value, 0x0102030405060708)

        bv = wrappers_pb2.BytesValue(value=b"\x01\x02\xff")
        bv2 = wrappers_pb2.BytesValue()
        bv2.ParseFromString(bv.SerializeToString())
        self.assertEqual(bv2.value, b"\x01\x02\xff")

        ts = Timestamp()
        ts.GetCurrentTime()
        any_msg = any_pb2.Any()
        any_msg.Pack(ts)
        out = Timestamp()
        self.assertTrue(any_msg.Unpack(out))
        self.assertEqual(out.seconds, ts.seconds)
        print("WKT=PASS")

    def test_fixed_width_scalars_and_wire(self):
        """fixed/sfixed/float/double use explicit little-endian on the wire."""
        from google.protobuf import descriptor_pb2

        T = descriptor_pb2.FieldDescriptorProto
        cases = [
            ("fixed32", T.TYPE_FIXED32, 0x01020304, bytes.fromhex("0d04030201")),
            ("sfixed32", T.TYPE_SFIXED32, -2, bytes.fromhex("0dfeffffff")),
            ("fixed64", T.TYPE_FIXED64, 0x0102030405060708, bytes.fromhex("090807060504030201")),
            ("sfixed64", T.TYPE_SFIXED64, -2, bytes.fromhex("09feffffffffffffff")),
            ("float", T.TYPE_FLOAT, 1.5, bytes.fromhex("0d0000c03f")),
            ("double", T.TYPE_DOUBLE, 1.5, bytes.fromhex("09000000000000f83f")),
        ]
        for name, ftype, value, expected_wire in cases:
            with self.subTest(name=name):
                M = _make_message(
                    syntax="proto3",
                    field_type=ftype,
                    label=T.LABEL_OPTIONAL,
                )
                x = M()
                x.f = value
                wire = x.SerializeToString()
                self.assertEqual(
                    wire,
                    expected_wire,
                    f"{name}: wire mismatch got={wire.hex()} expected={expected_wire.hex()}",
                )
                _roundtrip_scalar(M, "f", value)
        print("FIXED_WIDTH=PASS")

    def test_varint_and_length_delimited_scalars(self):
        from google.protobuf import descriptor_pb2

        T = descriptor_pb2.FieldDescriptorProto
        cases = [
            ("int32", T.TYPE_INT32, -1),
            ("int64", T.TYPE_INT64, -(1 << 40)),
            ("uint32", T.TYPE_UINT32, 0xFFFFFFFF),
            ("uint64", T.TYPE_UINT64, (1 << 60) + 7),
            ("sint32", T.TYPE_SINT32, -12345),
            ("sint64", T.TYPE_SINT64, -(1 << 50)),
            ("bool", T.TYPE_BOOL, True),
            ("string", T.TYPE_STRING, "héllo"),
            ("bytes", T.TYPE_BYTES, b"\x00\xff\x01"),
        ]
        for name, ftype, value in cases:
            with self.subTest(name=name):
                M = _make_message(syntax="proto3", field_type=ftype, label=T.LABEL_OPTIONAL)
                _roundtrip_scalar(M, "f", value)
        print("VARINT_LEN=PASS")

    def test_proto2_packed_enum_endian(self):
        """Regression for UPB DecodeEnumPacked missing MungeInt32 (7.35.x → [0,0,0])."""
        from google.protobuf import descriptor_pb2

        T = descriptor_pb2.FieldDescriptorProto
        M = _make_message(
            syntax="proto2",
            field_type=T.TYPE_ENUM,
            label=T.LABEL_REPEATED,
            packed=True,
            enum_values=[("U", 0), ("A", 1), ("B", 2), ("C", 3)],
        )
        vals = [1, 2, 3]
        x = M()
        x.f.extend(vals)
        wire = x.SerializeToString()
        self.assertEqual(wire, bytes.fromhex("0a03010203"), f"unexpected wire {wire.hex()}")
        y = M()
        y.ParseFromString(wire)
        got = list(y.f)
        self.assertEqual(
            got,
            vals,
            f"PROTO2_PACKED_ENUM expected {vals}, got {got} (wire ok → UPB decode endian bug)",
        )
        print("PROTO2_PACKED_ENUM=PASS")

    def test_packed_repeated_matrix(self):
        """Packed repeated for types with distinct UPB decode paths."""
        from google.protobuf import descriptor_pb2

        T = descriptor_pb2.FieldDescriptorProto
        # (name, type, values, proto2 packed=True / proto3 default packed)
        numeric = [
            ("int32", T.TYPE_INT32, [1, 2, 3, -1]),
            ("fixed32", T.TYPE_FIXED32, [0x01020304, 0xAABBCCDD]),
            ("fixed64", T.TYPE_FIXED64, [0x0102030405060708, 9]),
            ("float", T.TYPE_FLOAT, [1.5, -2.25]),
            ("double", T.TYPE_DOUBLE, [1.5, -2.25]),
            ("bool", T.TYPE_BOOL, [True, False, True]),
        ]
        for name, ftype, values in numeric:
            with self.subTest(syntax="proto2", name=name):
                M = _make_message(
                    syntax="proto2",
                    field_type=ftype,
                    label=T.LABEL_REPEATED,
                    packed=True,
                )
                _roundtrip_repeated(M, "f", values)
            with self.subTest(syntax="proto3", name=name):
                M = _make_message(
                    syntax="proto3",
                    field_type=ftype,
                    label=T.LABEL_REPEATED,
                )
                _roundtrip_repeated(M, "f", values)

        with self.subTest(syntax="proto3", name="enum"):
            M = _make_message(
                syntax="proto3",
                field_type=T.TYPE_ENUM,
                label=T.LABEL_REPEATED,
                enum_values=[("U", 0), ("A", 1), ("B", 2), ("C", 3)],
            )
            _roundtrip_repeated(M, "f", [1, 2, 3])

        with self.subTest(syntax="proto2", name="unpacked_enum"):
            M = _make_message(
                syntax="proto2",
                field_type=T.TYPE_ENUM,
                label=T.LABEL_REPEATED,
                packed=False,
                enum_values=[("U", 0), ("A", 1), ("B", 2), ("C", 3)],
            )
            _roundtrip_repeated(M, "f", [1, 2, 3])

        print("PACKED_MATRIX=PASS")

    def test_map_fixed_and_bool_keys(self):
        """Map key paths have had separate BE bugs (e.g. BoolKeys / hash)."""
        from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

        def make_map(key_type: int, value_type: int, key_type_name: str | None = None):
            fp = descriptor_pb2.FileDescriptorProto()
            fp.name = f"map_{key_type}_{value_type}.proto"
            fp.package = "dyn"
            fp.syntax = "proto3"
            # map<entry> is a nested message with map_entry option
            entry = fp.message_type.add()
            entry.name = "Entry"
            entry.options.map_entry = True
            k = entry.field.add()
            k.name = "key"
            k.number = 1
            k.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
            k.type = key_type
            if key_type_name:
                k.type_name = key_type_name
            v = entry.field.add()
            v.name = "value"
            v.number = 2
            v.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
            v.type = value_type

            outer = fp.message_type.add()
            outer.name = "M"
            f = outer.field.add()
            f.name = "m"
            f.number = 1
            f.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
            f.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
            f.type_name = ".dyn.Entry"

            pool = descriptor_pool.DescriptorPool()
            pool.Add(fp)
            return message_factory.GetMessageClass(pool.FindMessageTypeByName("dyn.M"))

        T = descriptor_pb2.FieldDescriptorProto

        with self.subTest(keys="bool"):
            M = make_map(T.TYPE_BOOL, T.TYPE_INT32)
            x = M()
            x.m[True] = 7
            x.m[False] = 8
            y = M()
            y.ParseFromString(x.SerializeToString())
            self.assertEqual(dict(y.m), {True: 7, False: 8})

        with self.subTest(keys="fixed32"):
            M = make_map(T.TYPE_FIXED32, T.TYPE_INT32)
            x = M()
            x.m[0x01020304] = 9
            y = M()
            y.ParseFromString(x.SerializeToString())
            self.assertEqual(dict(y.m), {0x01020304: 9})

        with self.subTest(keys="fixed64"):
            M = make_map(T.TYPE_FIXED64, T.TYPE_INT32)
            x = M()
            x.m[0x0102030405060708] = 10
            y = M()
            y.ParseFromString(x.SerializeToString())
            self.assertEqual(dict(y.m), {0x0102030405060708: 10})

        with self.subTest(keys="string"):
            M = make_map(T.TYPE_STRING, T.TYPE_INT32)
            x = M()
            x.m["k"] = 11
            y = M()
            y.ParseFromString(x.SerializeToString())
            self.assertEqual(dict(y.m), {"k": 11})

        print("MAP_KEYS=PASS")

    def test_oneof_and_submessage(self):
        from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

        fp = descriptor_pb2.FileDescriptorProto()
        fp.name = "oneof_sub.proto"
        fp.package = "dyn"
        fp.syntax = "proto3"

        inner = fp.message_type.add()
        inner.name = "Inner"
        f = inner.field.add()
        f.name = "n"
        f.number = 1
        f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        f.type = descriptor_pb2.FieldDescriptorProto.TYPE_FIXED32

        outer = fp.message_type.add()
        outer.name = "M"
        oo = outer.oneof_decl.add()
        oo.name = "choice"
        a = outer.field.add()
        a.name = "a"
        a.number = 1
        a.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        a.type = descriptor_pb2.FieldDescriptorProto.TYPE_INT32
        a.oneof_index = 0
        b = outer.field.add()
        b.name = "b"
        b.number = 2
        b.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        b.type = descriptor_pb2.FieldDescriptorProto.TYPE_FIXED64
        b.oneof_index = 0
        c = outer.field.add()
        c.name = "c"
        c.number = 3
        c.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        c.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
        c.type_name = ".dyn.Inner"
        c.oneof_index = 0

        pool = descriptor_pool.DescriptorPool()
        pool.Add(fp)
        M = message_factory.GetMessageClass(pool.FindMessageTypeByName("dyn.M"))

        x = M()
        x.b = 0x0102030405060708
        y = M()
        y.ParseFromString(x.SerializeToString())
        self.assertEqual(y.WhichOneof("choice"), "b")
        self.assertEqual(y.b, 0x0102030405060708)

        x = M()
        x.c.n = 0x0A0B0C0D
        y = M()
        y.ParseFromString(x.SerializeToString())
        self.assertEqual(y.WhichOneof("choice"), "c")
        self.assertEqual(y.c.n, 0x0A0B0C0D)
        print("ONEOF_SUBMSG=PASS")

    def test_unknown_field_preserved(self):
        from google.protobuf import descriptor_pb2

        T = descriptor_pb2.FieldDescriptorProto
        M1 = _make_message(syntax="proto3", field_type=T.TYPE_FIXED32, label=T.LABEL_OPTIONAL, field_number=1)
        M2 = _make_message(syntax="proto3", field_type=T.TYPE_FIXED32, label=T.LABEL_OPTIONAL, field_number=2)

        x = M1()
        x.f = 0x01020304
        # Parse into a message that only knows field 2 → field 1 becomes unknown
        y = M2()
        y.ParseFromString(x.SerializeToString())
        z = M1()
        z.ParseFromString(y.SerializeToString())
        self.assertEqual(z.f, 0x01020304)
        print("UNKNOWN_FIELDS=PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
