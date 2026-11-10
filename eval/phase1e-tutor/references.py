"""Execute only the fixed reference programs, never a provider's generated code."""

import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SQL = """SELECT species_id, COUNT(*), COUNT(weight), AVG(weight),
    1.0 * SUM(weight) / COUNT(*) FROM surveys GROUP BY species_id ORDER BY species_id"""


def command(argv, cwd, env):
    return subprocess.run(
        argv, cwd=cwd, env=env, check=True, text=True, capture_output=True
    ).stdout


def verify():
    with sqlite3.connect(":memory:") as conn:
        conn.execute("CREATE TABLE surveys(species_id TEXT, weight INTEGER)")
        conn.executemany(
            "INSERT INTO surveys VALUES (?,?)",
            [("A", 10), ("A", None), ("A", 20), ("B", 8)],
        )
        sql_before = conn.execute(SQL).fetchall()
        assert sql_before == [("A", 3, 2, 15.0, 10.0), ("B", 1, 1, 8.0, 8.0)]
        conn.execute("UPDATE surveys SET weight = 0 WHERE weight IS NULL")
        sql_after = conn.execute(SQL).fetchall()
        assert sql_after == [("A", 3, 3, 10.0, 10.0), ("B", 1, 1, 8.0, 8.0)]

    with tempfile.TemporaryDirectory(prefix="phase1e-reference-") as temp:
        work = Path(temp)
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        }
        for name, count in [("alpha", 12), ("beta", 2), ("gamma", 10)]:
            (work / f"{name}.txt").write_text("line\n" * count)
        pipeline = [
            "/bin/sh",
            "-c",
            "wc -l alpha.txt beta.txt gamma.txt | sort -n | head -n 1",
        ]
        shell_before = command(pipeline, work, env).split()
        assert shell_before == ["2", "beta.txt"]
        (work / "beta.txt").write_text("line\n" * 20)
        shell_after = command(pipeline, work, env).split()
        assert shell_after == ["10", "gamma.txt"]
        assert command(
            ["wc", "-l", "alpha.txt", "beta.txt", "gamma.txt"], work, env
        ).splitlines()[-1].split() == [
            "42",
            "total",
        ]

        command(["git", "init", "--quiet", "--template="], work, env)
        lesson = work / "lesson.txt"
        lesson.write_text("initial\n")
        command(["git", "add", "lesson.txt"], work, env)
        command(["git", "commit", "--quiet", "-m", "fixture"], work, env)
        lesson.write_text("first edit\n")
        command(["git", "add", "lesson.txt"], work, env)
        lesson.write_text("second edit\n")
        git_staged = command(["git", "diff", "--staged", "--", "lesson.txt"], work, env)
        git_worktree = command(["git", "diff", "--", "lesson.txt"], work, env)
        assert "+first edit\n" in git_staged and "second edit" not in git_staged
        assert "-first edit\n+second edit\n" in git_worktree

        loop = """names = ['Ada', 'Grace']
length = 2
for name in names:
    length += 1
    print(length)
print(length)
print(names[0], names[1])"""
        trace = command([sys.executable, "-I", "-c", loop], work, env).splitlines()
        assert trace == ["3", "4", "4", "Ada Grace"]
    return {
        "sqlite": {
            "version": sqlite3.sqlite_version,
            "before": sql_before,
            "after": sql_after,
        },
        "shell": {"before": shell_before, "after": shell_after},
        "git": {"staged": "first edit", "unstaged": "second edit"},
        "python_trace": trace,
        "real_model_quality": "NOT_RUN",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
