"""Artifact reuse must skip compilation without accepting stale build evidence."""

import copy
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import run
from build_cache import fingerprint, validate_reuse
from test_review import SHA, bundle, write_bundle
from verify import verify


def seed(directory):
    result, rows = bundle(directory)
    with zipfile.ZipFile(directory / "java-build.jar", "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "Start-Class: example.App\n")
    for name in ("java-app/BOOT-INF/classes/App.class", "java-addon/Wrapper.class"):
        path = directory / name
        path.parent.mkdir(parents=True)
        path.write_bytes(b"compiled-code")
    result.update(
        repository_root=str(run.ROOT),
        output_directory=str(directory),
        java_version="java 21",
        javac_version="javac 21",
        file_sha256={},
        java_build={
            "mode": "fresh",
            "artifacts": fingerprint(directory),
            "unchanged_at_end": True,
        },
    )
    result["config"]["java_build_mode"] = "fresh"
    # Reuse the existing fixture's independent metric accounting and config hash.
    result["config_sha256"] = hashlib.sha256(
        json.dumps(result["config"], sort_keys=True).encode()
    ).hexdigest()
    write_bundle(directory, result, rows)
    return result, rows


class BuildCache(unittest.TestCase):
    def test_same_clean_source_and_unchanged_artifacts_are_reusable(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            previous, _ = seed(directory)
            self.assertEqual(
                validate_reuse(previous, previous, directory, "java 21", "javac 21"),
                previous["java_build"]["artifacts"],
            )

    def test_stale_source_dirty_build_failed_run_and_toolchain_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            previous, _ = seed(directory)
            mutations = [
                lambda r: r.update(success=False),
                lambda r: r.update(valid_clean_source_evidence=False),
                lambda r: r["source"].update(sha="b" * 40),
                lambda r: r["source"].update(source_dirty=True),
                lambda r: r["end_source"].update(sha="b" * 40),
                lambda r: r.update(repository_root="elsewhere"),
                lambda r: r.update(output_directory="elsewhere"),
                lambda r: r.update(java_version="java 22"),
                lambda r: r.update(javac_version="javac 22"),
                lambda r: r.update(file_sha256={"changed": "0" * 64}),
                lambda r: r["java_build"].update(mode="reused"),
            ]
            for index, mutation in enumerate(mutations):
                with self.subTest(index=index):
                    bad = copy.deepcopy(previous)
                    mutation(bad)
                    with self.assertRaises(RuntimeError):
                        validate_reuse(bad, previous, directory, "java 21", "javac 21")

    def test_added_removed_and_tampered_artifacts_invalidate_cache(self):
        for mutation in ("add", "remove", "change"):
            with tempfile.TemporaryDirectory() as temp, self.subTest(mutation=mutation):
                directory = Path(temp)
                previous, _ = seed(directory)
                file = directory / "java-addon/Wrapper.class"
                if mutation == "add":
                    (directory / "java-addon/Extra.class").write_bytes(b"extra")
                elif mutation == "remove":
                    file.unlink()
                else:
                    file.write_bytes(b"different")
                with self.assertRaises(RuntimeError):
                    validate_reuse(previous, previous, directory, "java 21", "javac 21")

    def test_symlink_artifacts_and_empty_builds_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            seed(directory)
            file = directory / "java-addon/Wrapper.class"
            file.unlink()
            file.symlink_to(directory / "java-app/BOOT-INF/classes/App.class")
            with self.assertRaisesRegex(RuntimeError, "Linked"):
                fingerprint(directory)
            file.unlink()
            with self.assertRaisesRegex(RuntimeError, "Empty"):
                fingerprint(directory)

    def test_reuse_skips_maven_extraction_and_wrapper_compilation(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            previous, _ = seed(directory)
            env = run.Environment.__new__(run.Environment)
            env.options = run.arguments(
                [
                    "--output",
                    "unused",
                    "--offline",
                    "--reuse-build-from",
                    str(directory),
                ]
            )
            env.result = copy.deepcopy(previous)
            env.env = {}
            env.out = directory / "next-output"
            env.capture = Mock(
                side_effect=lambda cmd: {"java": "java 21", "javac": "javac 21"}.get(
                    cmd[0], ""
                )
            )
            env.run = Mock(side_effect=AssertionError("No build subprocess may run"))
            env.build_java = Mock(
                side_effect=AssertionError("No extraction or wrapper compilation")
            )
            with patch("run.subprocess.run"):
                env.dependencies()
            env.run.assert_not_called()
            env.build_java.assert_not_called()
            self.assertEqual(env.jar, directory / "java-build.jar")
            self.assertEqual(env.result["java_build"]["mode"], "reused")
            self.assertEqual(env.env["PERF_APP_MAIN_CLASS"], "example.App")
            self.assertIn(str(directory / "java-addon"), env.classpath)

    def test_fresh_build_retains_jar_and_extracted_classes_before_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            jar = directory / "target.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("META-INF/MANIFEST.MF", "Start-Class: example.App\n")
                archive.writestr("BOOT-INF/classes/App.class", b"class")
                archive.writestr("BOOT-INF/lib/dependency.jar", b"dependency")
            env = run.Environment.__new__(run.Environment)
            env.options = run.arguments(["--output", "unused", "--offline"])
            env.out = directory / "out"
            env.out.mkdir()
            env.jar, env.env, env.result = jar, {}, {}

            def command(cmd, name, *args):
                if name == "compile-delay-wrapper":
                    (env.out / "java-addon/Wrapper.class").write_bytes(b"wrapper")

            env.run = Mock(side_effect=command)
            env.build_java()
            self.assertEqual(
                env.run.call_args_list[0].args[0][-3:], ["-o", "clean", "package"]
            )
            self.assertEqual(env.jar, env.out / "java-build.jar")
            self.assertEqual(env.jar.read_bytes(), jar.read_bytes())
            self.assertEqual(
                env.result["java_build"]["artifacts"], fingerprint(env.out)
            )

    def test_artifact_drift_at_end_prevents_attestation(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result, _ = seed(directory)
            env = run.Environment.__new__(run.Environment)
            env.options = run.arguments(["--output", str(directory)])
            env.out, env.result = directory, result
            (directory / "java-addon/Wrapper.class").write_bytes(b"modified during run")
            with self.assertRaisesRegex(RuntimeError, "changed during"):
                env.attest()

    def test_reuse_requires_offline_and_disallows_dirty_source_override(self):
        for extra in ([], ["--offline", "--allow-dirty"]):
            with (
                self.subTest(extra=extra),
                patch("sys.stderr", new=io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                run.arguments(
                    ["--output", "unused", "--reuse-build-from", "seed", *extra]
                )

    def test_verifier_rejects_missing_or_drifted_build_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            original, rows = seed(directory)
            self.assertEqual(verify(directory, SHA)["status"], "PASS")
            mutations = [
                lambda r: r.pop("java_build"),
                lambda r: r["java_build"].update(unchanged_at_end=False),
                lambda r: r["java_build"].update(mode="reused"),
                lambda r: r["java_build"]["artifacts"].update(sha256="invalid"),
                lambda r: r["java_build"]["artifacts"].update(file_count=0),
            ]
            for index, mutation in enumerate(mutations):
                with self.subTest(index=index):
                    bad = copy.deepcopy(original)
                    mutation(bad)
                    write_bundle(directory, bad, rows)
                    with self.assertRaises(AssertionError):
                        verify(directory, SHA)

    def test_reused_build_provenance_must_be_complete_and_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            result, rows = seed(directory)
            result["config"].update(
                java_build_mode="reused", offline_dependency_bootstrap=True
            )
            result["java_build"].update(
                mode="reused", from_directory="seed", seed_result_sha256="b" * 64
            )
            for key, value in (
                (None, None),
                ("seed_result_sha256", "bad"),
                ("from_directory", ""),
            ):
                with self.subTest(key=key):
                    candidate = copy.deepcopy(result)
                    if key:
                        candidate["java_build"][key] = value
                    candidate["config_sha256"] = hashlib.sha256(
                        json.dumps(candidate["config"], sort_keys=True).encode()
                    ).hexdigest()
                    write_bundle(directory, candidate, rows)
                    if key:
                        with self.assertRaises(AssertionError):
                            verify(directory, SHA)
                    else:
                        self.assertEqual(verify(directory, SHA)["status"], "PASS")
            result["config"]["offline_dependency_bootstrap"] = False
            result["config_sha256"] = hashlib.sha256(
                json.dumps(result["config"], sort_keys=True).encode()
            ).hexdigest()
            write_bundle(directory, result, rows)
            with self.assertRaisesRegex(AssertionError, "provenance"):
                verify(directory, SHA)
