# backend/ast_validator.py
import re
from html.parser import HTMLParser

from pydantic import BaseModel


class ASTDiagnostic(BaseModel):
    level: str  # "error" | "warning" | "info"
    message: str
    line: int = 1


class ASTValidationReport(BaseModel):
    is_valid: bool
    security_score: float
    dom_depth: int
    element_count: int
    tailwind_class_count: int
    diagnostics: list[ASTDiagnostic]
    healed_code: str


class _DOMTreeAnalyzer(HTMLParser):
    """基于状态栈的 DOM / JSX 语法树深度与闭合校验解析器"""

    VOID_ELEMENTS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.tag_stack: list[tuple[str, int]] = []
        self.max_depth: int = 0
        self.element_count: int = 0
        self.tailwind_classes: list[str] = []
        self.diagnostics: list[ASTDiagnostic] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.element_count += 1
        line_no, _ = self.getpos()

        for attr_name, attr_val in attrs:
            if attr_name in ("class", "className") and attr_val:
                classes = [c.strip() for c in attr_val.split() if c.strip()]
                self.tailwind_classes.extend(classes)
            if attr_name and attr_name.lower().startswith("on"):
                self.diagnostics.append(
                    ASTDiagnostic(
                        level="warning",
                        message=f"内联事件属性 `{attr_name}` 已被移除，不再纳入沙盒监听",
                        line=line_no,
                    )
                )

        if tag.lower() not in self.VOID_ELEMENTS:
            self.tag_stack.append((tag, line_no))
            self.max_depth = max(self.max_depth, len(self.tag_stack))

    def handle_endtag(self, tag: str) -> None:
        line_no, _ = self.getpos()
        if tag.lower() in self.VOID_ELEMENTS:
            return
        if not self.tag_stack:
            self.diagnostics.append(
                ASTDiagnostic(
                    level="error",
                    message=f"发现多余的闭合标签 `</{tag}>`",
                    line=line_no,
                )
            )
            return

        top_tag, _ = self.tag_stack[-1]
        if top_tag.lower() == tag.lower():
            self.tag_stack.pop()
        else:
            self.diagnostics.append(
                ASTDiagnostic(
                    level="error",
                    message=f"标签闭合错位：期望闭合 `</{top_tag}>`，实际遇到 `</{tag}>`",
                    line=line_no,
                )
            )
            # 尝试在栈中回溯匹配以实现语法树自愈
            for idx in range(len(self.tag_stack) - 1, -1, -1):
                if self.tag_stack[idx][0].lower() == tag.lower():
                    del self.tag_stack[idx:]
                    break


class FrontendASTValidator:
    """前端智能体代码生成 AST 校验器与自愈编译器"""

    DANGEROUS_PATTERNS = [
        (r"<script\b[^>]*>([\s\S]*?)<\/script>", "拦截非法 `<script>` 注入标签"),
        (r"javascript\s*:", "拦截 `javascript:` 伪协议调用"),
        (r"\beval\s*\(", "拦截高危 `eval()` 动态执行调用"),
        (r"\bdocument\.cookie\b", "拦截敏感凭据 `document.cookie` 读取"),
    ]

    # 危险标签：整体删除（含内容），每类记 error
    DANGEROUS_TAGS = ["iframe", "object", "embed", "link", "meta", "base", "form"]

    @classmethod
    def validate_and_heal(cls, raw_code: str) -> ASTValidationReport:
        diagnostics: list[ASTDiagnostic] = []
        sanitized = raw_code.strip()

        # 1. 剥离 Markdown 代码围栏（防止大模型输出 ```html ... ```）
        sanitized = re.sub(r"^```[a-zA-Z]*\n?", "", sanitized)
        sanitized = re.sub(r"\n?```$", "", sanitized).strip()

        # 2. JSX 属性标准化为可直接挂载至 DOM 沙盒的 HTML 属性
        sanitized = re.sub(r"\bclassName=", "class=", sanitized)

        # 3. 安全扫描与危险载荷清洗
        security_score = 100.0
        for pattern, warn_msg in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, sanitized, flags=re.IGNORECASE):
                security_score -= 25.0
                diagnostics.append(ASTDiagnostic(level="error", message=warn_msg, line=1))
                sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)

        # 3.1 删除全部内联事件属性（onerror= / onclick= 等），每命中一次扣 10 分
        event_attr_pattern = r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)"
        for match in re.findall(event_attr_pattern, sanitized, flags=re.IGNORECASE):
            security_score -= 10.0
            diagnostics.append(
                ASTDiagnostic(level="warning", message="已移除内联事件属性", line=1)
            )
        sanitized = re.sub(event_attr_pattern, "", sanitized, flags=re.IGNORECASE)

        # 3.2 整体删除危险标签（iframe/object/embed/link/meta/base/form，含内容），每类记 error
        for tag in cls.DANGEROUS_TAGS:
            paired = rf"<{tag}\b[^>]*>[\s\S]*?<\/{tag}\s*>"
            single = rf"<{tag}\b[^>]*\/?>"
            if re.search(paired, sanitized, flags=re.IGNORECASE) or re.search(
                single, sanitized, flags=re.IGNORECASE
            ):
                security_score -= 25.0
                diagnostics.append(
                    ASTDiagnostic(level="error", message=f"已整体删除危险标签 `<{tag}>`", line=1)
                )
            sanitized = re.sub(paired, "", sanitized, flags=re.IGNORECASE)
            sanitized = re.sub(single, "", sanitized, flags=re.IGNORECASE)
            sanitized = re.sub(rf"<\/{tag}\s*>", "", sanitized, flags=re.IGNORECASE)

        # 3.3 清理 href/src/action 中的危险伪协议与 srcdoc 内联文档属性
        danger_url_pattern = r"\s(href|src|action)\s*=\s*(\"[^\"]*(?:javascript:|data:text\/html)[^\"]*\"|'[^']*(?:javascript:|data:text\/html)[^']*'|(?:javascript:|data:text\/html)[^\s>]*)"
        if re.search(danger_url_pattern, sanitized, flags=re.IGNORECASE):
            security_score -= 10.0
            diagnostics.append(
                ASTDiagnostic(level="warning", message="已清理 href/src/action 中的危险伪协议", line=1)
            )
        sanitized = re.sub(danger_url_pattern, "", sanitized, flags=re.IGNORECASE)
        if re.search(r"\ssrcdoc\s*=", sanitized, flags=re.IGNORECASE):
            security_score -= 10.0
            diagnostics.append(
                ASTDiagnostic(level="warning", message="已移除 srcdoc 内联文档属性", line=1)
            )
        sanitized = re.sub(r"\ssrcdoc\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", sanitized, flags=re.IGNORECASE)

        # 4. 花括号与圆括号平衡度检查
        open_braces = sanitized.count("{") - sanitized.count("}")
        if open_braces != 0:
            diagnostics.append(
                ASTDiagnostic(
                    level="warning",
                    message=f"花括号层级不平衡 (差值: {open_braces})，已自动配平",
                    line=1,
                )
            )
            if open_braces > 0:
                sanitized += "}" * open_braces

        # 5. 构建 DOM 语法树并分析标签栈
        analyzer = _DOMTreeAnalyzer()
        try:
            analyzer.feed(sanitized)
        except Exception as exc:
            diagnostics.append(ASTDiagnostic(level="error", message=f"AST 解析异常: {exc}", line=1))

        diagnostics.extend(analyzer.diagnostics)

        # 6. 自动闭合尚未闭合的悬挂标签（AST Auto-Healing）
        healed_code = sanitized
        if analyzer.tag_stack:
            for unclosed_tag, line_no in reversed(analyzer.tag_stack):
                diagnostics.append(
                    ASTDiagnostic(
                        level="warning",
                        message=f"自动补全第 {line_no} 行未闭合的标签 `<{unclosed_tag}>`",
                        line=line_no,
                    )
                )
                healed_code += f"</{unclosed_tag}>"

        has_fatal_error = any(d.level == "error" for d in diagnostics)
        return ASTValidationReport(
            is_valid=not has_fatal_error and security_score >= 75.0,
            security_score=max(0.0, security_score),
            dom_depth=max(1, analyzer.max_depth),
            element_count=analyzer.element_count,
            tailwind_class_count=len(analyzer.tailwind_classes),
            diagnostics=diagnostics,
            healed_code=healed_code,
        )
