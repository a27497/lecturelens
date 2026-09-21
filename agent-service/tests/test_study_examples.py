import pytest

from lecturelens_agent.study.examples import check_example


@pytest.mark.parametrize(
    "program,stdout,variables",
    [
        ("s = 'world'\nprint(s[1:])\nprint('l' + s[2:])", "orld\nlrld\n", {"s": "world"}),
        ("s = 'world'\nprint('l' + s[1:3] + s[4:])", "lord\n", {"s": "world"}),
        (
            "def f(i):\n    print('with return')\n    return i % 2 == 0\nprint(f(7))",
            "with return\nFalse\n",
            {},
        ),
        ("def f():\n    print('hello')\nx = f()\nprint(x)", "hello\nNone\n", {"x": None}),
        ("def f(): print('hello'); f()", "", {}),
        (
            "a = [1, 2]\nb = a\nc = a[:]\nb[0] = 3\nprint(a, b, c)",
            "[3, 2] [3, 2] [1, 2]\n",
            {"a": [3, 2], "b": [3, 2], "c": [1, 2]},
        ),
        ("a = [1]\na.append(2)\nprint(len(a))", "2\n", {"a": [1, 2]}),
        ("print('abcdef'[::-2], (10 + 50) // 2)", "fdb 30\n", {}),
        ("x = 7\nif x % 2:\n    y = 'odd'\nelse:\n    y = 'even'\nprint(y)", "odd\n", {"x": 7, "y": "odd"}),
        ("print(False and (1 / 0), 2 if True else (1 / 0))", "False 2\n", {}),
        ("print('a', 'b', sep='-', end='!')\nprint()", "a-b!\n", {}),
        ("x = 10\ndef f():\n    return x + 2\nprint(f())", "12\n", {"x": 10}),
    ],
)
def test_bounded_python_computes_real_example_results(program, stdout, variables):
    result = check_example(program)
    assert result == {
        "semantics": "bounded_python_subset_v1",
        "status": "computed",
        "stdout": stdout,
        "variables": {k: {"type": type(v).__name__, "repr": repr(v)} for k, v in variables.items()},
    }


@pytest.mark.parametrize(
    "program,error,stdout",
    [
        ("s = 'hello'\ns[0] = 'y'", "TypeError", ""),
        ("print('before')\nprint(1 / 0)", "ZeroDivisionError", "before\n"),
        ("print([1][2])", "IndexError", ""),
        ("print(missing)", "NameError", ""),
        ("def f(: pass", "SyntaxError", ""),
        ("x = 1\ndef f():\n    print(x)\n    x = 2\nf()", "UnboundLocalError", ""),
        ("print('abc'[::0])", "ValueError", ""),
    ],
)
def test_observed_program_errors_are_not_silently_repaired(program, error, stdout):
    assert check_example(program) == {
        "semantics": "bounded_python_subset_v1",
        "status": "program_error",
        "error": error,
        "stdout": stdout,
    }


@pytest.mark.parametrize(
    "program",
    [
        "import os",
        "__import__('os').system('echo forbidden')",
        "open('/tmp/forbidden', 'w')",
        "while True: pass",
        "for i in [1]: pass",
        "[x for x in [1,2]]",
        "lambda: 1",
        "print((1).__class__)",
        "print(2 ** 1000)",
        "class X: pass",
        "a = []\na.append(a)",
        "a = []\nb = [a]\na.append(b)",
        "def f(x=2): return x",
        "def f():\n    def g(): return 1\n    return g()",
        "print('%s' % 'formatted')",
        "if False:\n    import os",
    ],
)
def test_unsupported_constructs_never_claim_verification(program, tmp_path):
    assert check_example(program)["status"] == "unsupported"


@pytest.mark.parametrize(
    "program",
    [
        "print('x' * 1000000000)",
        "a = [0] * 1000000000",
        "def f(): return f()\nf()",
        "x = 1000000001",
        "x = " + "9" * 1000,
        "a=[0]\nb=[a]*32\nc=[b]*32\nd=[c]*32",
        "x = 1\n" * 200,
    ],
)
def test_execution_and_expansion_limits_are_explicit(program):
    assert check_example(program)["status"] == "limit"


def test_no_submitted_code_can_write_files(tmp_path):
    path = tmp_path / "should-not-exist"
    result = check_example(f"open({str(path)!r}, 'w').write('bad')")
    assert result["status"] == "unsupported" and not path.exists()
