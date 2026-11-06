# tests/test_ast_security.py —— A6(b)：AST 校验器移除内联事件、危险标签与危险伪协议
from ast_validator import FrontendASTValidator


def test_inline_event_handlers_removed():
    code = '<div onclick="alert(1)" onerror="steal()">ok</div>'
    report = FrontendASTValidator.validate_and_heal(code)
    healed = report.healed_code.lower()
    assert "onclick" not in healed
    assert "onerror" not in healed
    assert "alert(1)" not in report.healed_code
    assert "ok" in report.healed_code
    # 每次命中记一条「已移除」warning 并扣分
    removed_warnings = [d for d in report.diagnostics if "已移除内联事件属性" in d.message]
    assert len(removed_warnings) >= 2


def test_dangerous_tags_removed_entirely():
    code = '<iframe src="evil"></iframe><object data="x"></object><form action="y"><input/></form><p>keep</p>'
    report = FrontendASTValidator.validate_and_heal(code)
    healed = report.healed_code.lower()
    for tag in ("iframe", "object", "form"):
        assert f"<{tag}" not in healed
        assert f"</{tag}" not in healed
    assert "<p>keep</p>" in report.healed_code
    # 每类危险标签记 error
    tag_errors = [d for d in report.diagnostics if d.level == "error" and "危险标签" in d.message]
    assert len(tag_errors) >= 3
    assert report.security_score < 100.0


def test_javascript_href_cleaned():
    code = '<a href="javascript:alert(1)">link</a>'
    report = FrontendASTValidator.validate_and_heal(code)
    assert "javascript" not in report.healed_code.lower()
    assert "link" in report.healed_code


def test_data_text_html_href_cleaned():
    code = '<a href="data:text/html;base64,PHNjcmlwdD4=">link</a>'
    report = FrontendASTValidator.validate_and_heal(code)
    assert "data:text/html" not in report.healed_code.lower()


def test_script_removed_and_score_drops():
    code = '<div><script>alert(1)</script>safe</div>'
    report = FrontendASTValidator.validate_and_heal(code)
    assert "<script" not in report.healed_code.lower()
    assert "safe" in report.healed_code
    assert report.security_score < 100.0
    # healed_code 是清洗后的结果
    assert report.healed_code == "<div>safe</div>"
