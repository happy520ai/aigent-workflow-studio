# tests/test_ast_fuzz.py —— T53：AST 净化器模糊测试（hypothesis）
# 不变量：对任意输入，validate_and_heal 绝不抛异常，且净化产物永不包含
#   <script 标签、javascript: 伪协议、on*= 内联事件属性、危险标签（iframe/object/embed）。
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ast_validator import FrontendASTValidator

# 属性形态的内联事件（带词边界，避免把普通文本 "addition=" 误判为属性）
_ON_ATTR_RE = re.compile(r"(?<![\w-])on[a-zA-Z]+\s*=", re.IGNORECASE)
_DANGEROUS_TAGS_RE = re.compile(r"<\s*(script|iframe|object|embed|link|meta|base|form)\b", re.IGNORECASE)
_JS_PROTO_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def _assert_safe(output: str) -> None:
    assert "<script" not in output.lower()
    assert _DANGEROUS_TAGS_RE.search(output) is None, f"危险标签残留: {output[:200]}"
    assert _JS_PROTO_RE.search(output) is None, f"javascript: 残留: {output[:200]}"
    assert _ON_ATTR_RE.search(output) is None, f"内联事件属性残留: {output[:200]}"


# 任意文本（含 Unicode/控制字符）
any_text = st.text(max_size=512)


@given(any_text)
@settings(max_examples=300, deadline=None, database=None)
def test_fuzz_arbitrary_text_never_raises_and_is_safe(code: str) -> None:
    try:
        report = FrontendASTValidator.validate_and_heal(code)
    except Exception as exc:  # 净化器必须吞掉一切畸形输入
        pytest.fail(f"净化器对畸形输入抛出异常: {exc!r}\ninput={code[:200]!r}")
    _assert_safe(report.healed_code)


# 结构化攻击载荷：标签碎片 + 事件属性 + 危险协议组合
attack_fragments = st.sampled_from(
    [
        "<script>alert(1)</script>",
        "<SCRIPT SRC=//evil/x.js></SCRIPT>",
        "<scr<script>ipt>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "<img src=x ONERROR=alert(1)>",
        "<svg onload=alert(1)>",
        "<body onload=alert(1)>",
        "<a href=\"javascript:alert(1)\">x</a>",
        "<a href='JaVaScRiPt:alert(1)'>x</a>",
        "<iframe src=//evil></iframe>",
        "<object data=//evil></object>",
        "<embed src=//evil>",
        "<<script>script>alert(1)<</script>/script>",
        "<div onclick=alert(1) onmouseover=alert(2)>x</div>",
        "<input onfocus=alert(1) autofocus>",
        "<math><mtext></mtext><script>alert(1)</script></math>",
        "<style>body{background:url(javascript:alert(1))}</style>",
        "<base href=//evil/>",
        "<meta http-equiv=refresh content='0;url=javascript:alert(1)'>",
        "<form action=javascript:alert(1)><input type=submit>",
    ]
)


@given(attack_fragments, st.text(max_size=64), attack_fragments)
@settings(max_examples=200, deadline=None, database=None)
def test_fuzz_attack_composites(a: str, middle: str, b: str) -> None:
    payload = a + middle + b
    try:
        report = FrontendASTValidator.validate_and_heal(payload)
    except Exception as exc:
        pytest.fail(f"净化器对攻击组合抛出异常: {exc!r}\ninput={payload[:200]!r}")
    _assert_safe(report.healed_code)


# 属性值注入：合法标签 + 由模糊生成的属性值
_attr_value = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=0x2FFF).filter(lambda c: c not in '">'),
    max_size=64,
)


@given(_attr_value)
@settings(max_examples=200, deadline=None, database=None)
def test_fuzz_attribute_injection(value: str) -> None:
    payload = f"<div data-x=\"{value}\">content</div>"
    try:
        report = FrontendASTValidator.validate_and_heal(payload)
    except Exception as exc:
        pytest.fail(f"属性注入导致异常: {exc!r}\ninput={payload[:200]!r}")
    _assert_safe(report.healed_code)
