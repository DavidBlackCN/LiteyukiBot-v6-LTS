import ast
import re
from collections.abc import Callable
from typing import Any


_ATTRIBUTES = frozenset({"AGE", "CHR", "INT", "STR", "MNY", "SPR", "LIF", "TMS", "TLT", "EVT", "AVT"})
_MEMBERSHIP = re.compile(r"\b([A-Z]{3})([?!])\[([\d,\s]*)\]")
_ATTRIBUTE = re.compile(r"(?<![\w.])([A-Z]{3})\b")


def _normalize_condition(condition: str) -> str:
    """Convert the bundled remake condition DSL to a small Python expression."""

    def replace_membership(match: re.Match[str]) -> str:
        attribute, operator, values = match.groups()
        keyword = "in" if operator == "?" else "not in"
        return f"x.{attribute} {keyword} [{values}]"

    expression = _MEMBERSHIP.sub(replace_membership, condition.replace("AEVT", "AVT"))
    expression = _ATTRIBUTE.sub(r"x.\1", expression)
    return expression.replace("&", " and ").replace("|", " or ")


class _ConditionEvaluator:
    def __init__(self, prop: Any):
        self.prop = prop

    def evaluate(self, node: ast.AST) -> Any:
        match node:
            case ast.Expression(body=body):
                return self.evaluate(body)
            case ast.Constant(value=int() as value):
                return value
            case ast.List(elts=elements):
                return [self.evaluate(element) for element in elements]
            case ast.Attribute(value=ast.Name(id="x"), attr=attribute):
                if attribute not in _ATTRIBUTES:
                    raise ValueError(f"不支持的人生属性：{attribute}")
                return getattr(self.prop, attribute)
            case ast.BoolOp(op=ast.And(), values=values):
                return all(self.evaluate(value) for value in values)
            case ast.BoolOp(op=ast.Or(), values=values):
                return any(self.evaluate(value) for value in values)
            case ast.UnaryOp(op=ast.USub(), operand=operand):
                return -self.evaluate(operand)
            case ast.UnaryOp(op=ast.Not(), operand=operand):
                return not self.evaluate(operand)
            case ast.Compare(left=left, ops=operators, comparators=comparators):
                current = self.evaluate(left)
                for operator, comparator in zip(operators, comparators):
                    next_value = self.evaluate(comparator)
                    if not self._compare(current, operator, next_value):
                        return False
                    current = next_value
                return True
            case _:
                raise ValueError(f"不支持的人生条件表达式：{ast.dump(node)}")

    @staticmethod
    def _compare(left: Any, operator: ast.cmpop, right: Any) -> bool:
        if isinstance(operator, ast.In):
            return any(item in left for item in right) if isinstance(left, set) else left in right
        if isinstance(operator, ast.NotIn):
            return not any(item in left for item in right) if isinstance(left, set) else left not in right
        if isinstance(operator, ast.Eq):
            return left == right
        if isinstance(operator, ast.NotEq):
            return left != right
        if isinstance(operator, ast.Lt):
            return left < right
        if isinstance(operator, ast.LtE):
            return left <= right
        if isinstance(operator, ast.Gt):
            return left > right
        if isinstance(operator, ast.GtE):
            return left >= right
        raise ValueError(f"不支持的人生比较运算：{type(operator).__name__}")


def parse_condition(condition: str) -> Callable[[Any], bool]:
    """Parse remake's resource condition language without evaluating Python code."""

    expression = _normalize_condition(condition)
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"无效的人生条件：{condition}") from exc

    def check(prop: Any) -> bool:
        return bool(_ConditionEvaluator(prop).evaluate(tree))

    check.__doc__ = expression
    return check
