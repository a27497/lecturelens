"""Small, bounded Python-semantics interpreter for private practice observations.

No eval/exec/compile/import of submitted code, I/O, attributes except list.append,
loops, comprehensions, or host objects. Unsupported syntax is never marked verified.
"""

import ast
import json
import math
import operator


class UnsupportedExample(Exception):
    pass


class ExampleLimit(Exception):
    pass


class Returned(Exception):
    def __init__(self, value):
        self.value = value


class Function:
    def __init__(self, node):
        self.node = node


_UNBOUND = object()


class Interpreter:
    def __init__(self):
        self.steps = 0
        self.stack = []
        self.globals = {}
        self.stdout = ""

    def bounded(self, value, depth=0, budget=None):
        budget = [512] if budget is None else budget
        budget[0] -= 1
        if depth > 6 or budget[0] < 0:
            raise ExampleLimit()
        if value is None or type(value) is bool:
            return value
        if type(value) in (int, float):
            if abs(value) > 1_000_000_000 or (type(value) is float and not math.isfinite(value)):
                raise ExampleLimit()
        elif type(value) is str:
            if len(value) > 256:
                raise ExampleLimit()
        elif type(value) in (list, tuple):
            if len(value) > 32:
                raise ExampleLimit()
            for child in value:
                self.bounded(child, depth + 1, budget)
        else:
            raise UnsupportedExample()
        return value

    def tick(self):
        self.steps += 1
        if self.steps > 128:
            raise ExampleLimit()

    def lookup(self, name, local):
        if name in local:
            if local[name] is _UNBOUND:
                raise UnboundLocalError()
            return local[name]
        if name in self.globals:
            return self.globals[name]
        raise NameError()

    def expression(self, node, local):
        self.tick()
        if isinstance(node, ast.Constant):
            value = node.value
        elif isinstance(node, ast.Name):
            value = self.lookup(node.id, local)
        elif isinstance(node, (ast.List, ast.Tuple)):
            values = [self.expression(item, local) for item in node.elts]
            value = values if isinstance(node, ast.List) else tuple(values)
        elif isinstance(node, ast.BinOp):
            left, right = self.expression(node.left, local), self.expression(node.right, local)
            operations = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod,
            }
            if type(node.op) not in operations or (isinstance(node.op, ast.Mod) and type(left) is str):
                raise UnsupportedExample()
            if isinstance(node.op, ast.Mult):
                for sequence, count in ((left, right), (right, left)):
                    if type(sequence) in (str, list, tuple) and type(count) in (int, bool):
                        if len(sequence) * max(0, count) > (256 if type(sequence) is str else 32):
                            raise ExampleLimit()
            value = operations[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp):
            operations = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.not_}
            if type(node.op) not in operations:
                raise UnsupportedExample()
            value = operations[type(node.op)](self.expression(node.operand, local))
        elif isinstance(node, ast.Compare):
            operations = {
                ast.Eq: operator.eq,
                ast.NotEq: operator.ne,
                ast.Lt: operator.lt,
                ast.LtE: operator.le,
                ast.Gt: operator.gt,
                ast.GtE: operator.ge,
            }
            left = self.expression(node.left, local)
            value = True
            for op, item in zip(node.ops, node.comparators, strict=True):
                right = self.expression(item, local)
                if type(op) not in operations:
                    raise UnsupportedExample()
                if not operations[type(op)](left, right):
                    value = False
                    break
                left = right
        elif isinstance(node, ast.BoolOp):
            value = self.expression(node.values[0], local)
            for item in node.values[1:]:
                if (isinstance(node.op, ast.And) and not value) or (isinstance(node.op, ast.Or) and value):
                    break
                value = self.expression(item, local)
        elif isinstance(node, ast.IfExp):
            value = self.expression(node.body if self.expression(node.test, local) else node.orelse, local)
        elif isinstance(node, ast.Subscript):
            sequence = self.expression(node.value, local)
            if type(sequence) not in (str, list, tuple):
                raise TypeError()
            value = sequence[self.index(node.slice, local)]
        elif isinstance(node, ast.Call):
            value = self.call(node, local)
        else:
            raise UnsupportedExample()
        return self.bounded(value)

    def index(self, node, local):
        if isinstance(node, ast.Slice):
            values = [
                self.expression(part, local) if part is not None else None
                for part in (node.lower, node.upper, node.step)
            ]
            if any(v is not None and type(v) not in (int, bool) for v in values):
                raise TypeError()
            return slice(*values)
        value = self.expression(node, local)
        if type(value) not in (int, bool):
            raise TypeError()
        return value

    def call(self, node, local):
        if len(node.args) > 8 or any(isinstance(arg, ast.Starred) for arg in node.args):
            raise UnsupportedExample()
        args = [self.expression(arg, local) for arg in node.args]
        if isinstance(node.func, ast.Attribute) and node.func.attr == "append" and not node.keywords:
            target = self.expression(node.func.value, local)
            if type(target) is not list or len(args) != 1:
                raise UnsupportedExample()
            # Reject cycles before mutation; nested bounds also prevent unbounded graph growth.
            if self.contains(args[0], target):
                raise UnsupportedExample()
            self.bounded([*target, args[0]])
            target.append(args[0])
            return None
        if not isinstance(node.func, ast.Name):
            raise UnsupportedExample()
        name = node.func.id
        function = local.get(name, self.globals.get(name))
        if name == "print" and name not in local and name not in self.globals:
            keywords = {}
            for key in node.keywords:
                if key.arg not in ("sep", "end") or key.arg in keywords:
                    raise UnsupportedExample()
                keywords[key.arg] = self.expression(key.value, local)
            sep, end = keywords.get("sep", " "), keywords.get("end", "\n")
            sep, end = " " if sep is None else sep, "\n" if end is None else end
            if type(sep) is not str or type(end) is not str:
                raise TypeError()
            output = sep.join(str(arg) for arg in args) + end
            if len(self.stdout) + len(output) > 2048:
                raise ExampleLimit()
            self.stdout += output
            return None
        if name == "len" and name not in local and name not in self.globals:
            if node.keywords or len(args) != 1 or type(args[0]) not in (str, list, tuple):
                raise UnsupportedExample()
            return len(args[0])
        if not isinstance(function, Function) or node.keywords:
            raise UnsupportedExample()
        if len(self.stack) >= 4 or name in self.stack:
            raise ExampleLimit()
        names = [arg.arg for arg in function.node.args.args]
        if len(args) != len(names):
            raise TypeError()
        self.stack.append(name)
        try:
            assigned = {
                item.id
                for item in ast.walk(function.node)
                if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
            }
            frame = {name: _UNBOUND for name in assigned}
            frame.update(zip(names, args, strict=True))
            self.block(function.node.body, frame)
        except Returned as result:
            return result.value
        finally:
            self.stack.pop()
        return None

    @staticmethod
    def contains(value, target):
        if value is target:
            return True
        return type(value) in (tuple, list) and any(Interpreter.contains(item, target) for item in value)

    def assign(self, target, value, local):
        if isinstance(target, ast.Name):
            if len(local) >= 32 and target.id not in local:
                raise ExampleLimit()
            local[target.id] = value
        elif isinstance(target, ast.Subscript):
            sequence = self.expression(target.value, local)
            if type(sequence) is not list:
                raise TypeError()
            index = self.index(target.slice, local)
            if self.contains(value, sequence):
                raise UnsupportedExample()
            proposed = sequence.copy()
            proposed[index] = value
            self.bounded(proposed)
            sequence[index] = value
        else:
            raise UnsupportedExample()

    def block(self, nodes, local):
        for node in nodes:
            self.tick()
            if isinstance(node, ast.Assign):
                value = self.expression(node.value, local)
                for target in node.targets:
                    self.assign(target, value, local)
            elif isinstance(node, ast.Expr):
                self.expression(node.value, local)
            elif isinstance(node, ast.If):
                self.block(node.body if self.expression(node.test, local) else node.orelse, local)
            elif isinstance(node, ast.Return) and self.stack:
                raise Returned(self.expression(node.value, local) if node.value else None)
            elif isinstance(node, ast.FunctionDef) and not self.stack:
                if any(isinstance(child, ast.FunctionDef) and child is not node for child in ast.walk(node)):
                    raise UnsupportedExample()
                args = node.args
                if (
                    args.posonlyargs
                    or args.kwonlyargs
                    or args.vararg
                    or args.kwarg
                    or args.defaults
                    or node.decorator_list
                    or node.returns
                    or any(a.annotation for a in args.args)
                    or len(args.args) > 4
                ):
                    raise UnsupportedExample()
                if sum(isinstance(v, Function) for v in self.globals.values()) >= 4:
                    raise ExampleLimit()
                local[node.name] = Function(node)
            elif isinstance(node, ast.Pass):
                pass
            else:
                raise UnsupportedExample()


def check_example(program):
    runner = Interpreter()
    try:
        if len(program) > 1200:
            raise ExampleLimit()
        tree = ast.parse(program)
        nodes = list(ast.walk(tree))
        if len(nodes) > 256:
            raise ExampleLimit()
        # Fail closed even for an unsupported construct in an unexecuted branch.
        banned = (
            ast.Import,
            ast.ImportFrom,
            ast.While,
            ast.For,
            ast.AsyncFor,
            ast.With,
            ast.AsyncWith,
            ast.Try,
            ast.TryStar,
            ast.Raise,
            ast.Global,
            ast.Nonlocal,
            ast.ClassDef,
            ast.Lambda,
            ast.ListComp,
            ast.SetComp,
            ast.DictComp,
            ast.GeneratorExp,
            ast.Await,
            ast.Yield,
            ast.YieldFrom,
            ast.NamedExpr,
        )
        if any(isinstance(node, banned) for node in nodes):
            raise UnsupportedExample()
        runner.block(tree.body, runner.globals)
        result = {
            "status": "computed",
            "stdout": runner.stdout,
            "variables": {
                k: {"type": type(v).__name__, "repr": repr(v)}
                for k, v in runner.globals.items()
                if not isinstance(v, Function)
            },
        }
        if len(json.dumps(result, ensure_ascii=False)) > 8192:
            raise ExampleLimit()
    except SyntaxError:
        result = {"status": "program_error", "error": "SyntaxError", "stdout": runner.stdout}
    except (TypeError, IndexError, ZeroDivisionError, NameError, ValueError) as error:
        result = {"status": "program_error", "error": type(error).__name__, "stdout": runner.stdout}
    except (ExampleLimit, RecursionError):
        result = {"status": "limit", "stdout": runner.stdout}
    except UnsupportedExample:
        result = {"status": "unsupported", "stdout": runner.stdout}
    return {"semantics": "bounded_python_subset_v1", **result}
