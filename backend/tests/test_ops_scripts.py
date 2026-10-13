"""Scripts de operação (scripts/backup-db.sh e scripts/restore-db.sh) com um `docker` falso.

O docker falso registra cada chamada e simula o que o Compose faria: o pg_dump escreve um dump
novo, o pg_restore --list confere a entrada e o pg_restore grava o que recebeu num arquivo.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or not SCRIPTS.is_dir(), reason="precisa do bash e de scripts/"
)

FAKE_DOCKER = r"""#!/usr/bin/env bash
echo "$*" >>"$FAKE_DIR/calls.log"
case "$*" in
  *"pg_dump "*) echo "dump-novo" ;;
  *"pg_restore --list"*) cat >/dev/null ;;
  *"pg_restore -U"*) cat >"$FAKE_DIR/restored" ;;
  *) cat >/dev/null 2>&1 </dev/null ;;
esac
"""

OLD = time.time() - 20 * 86400


@pytest.fixture
def ops(tmp_path: Path) -> dict[str, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    env_file = tmp_path / "test.env"
    env_file.write_text(f"BACKUP_DIR={tmp_path / 'backups'}\nBACKUP_KEEP_DAYS=14\n")
    backups = tmp_path / "backups"
    backups.mkdir()
    return {"root": tmp_path, "bin": bin_dir, "env": env_file, "backups": backups}


def run(
    ops: dict[str, Path], script: str, *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{ops['bin']}:{os.environ['PATH']}",
        "HOME": str(ops["root"]),
        "FAKE_DIR": str(ops["root"]),
        "ENV_FILE": str(ops["env"]),
    }
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        cwd=cwd or ops["root"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def old_dump(ops: dict[str, Path], name: str, content: str) -> Path:
    dump = ops["backups"] / name
    dump.write_text(content)
    os.utime(dump, (OLD, OLD))
    return dump


def test_backup_rotates_old_dumps(ops: dict[str, Path]) -> None:
    old = old_dump(ops, "receita-20260101T031500Z.dump", "antigo")

    result = run(ops, "backup-db.sh")

    assert result.returncode == 0, result.stderr
    assert not old.exists()
    new = list(ops["backups"].glob("receita-*.dump"))
    assert len(new) == 1
    assert new[0].read_text() == "dump-novo\n"
    assert "rotação: 1 backup(s)" in result.stdout


def test_backup_no_rotate_keeps_old_dumps(ops: dict[str, Path]) -> None:
    old = old_dump(ops, "receita-20260101T031500Z.dump", "antigo")

    result = run(ops, "backup-db.sh", "--no-rotate")

    assert result.returncode == 0, result.stderr
    assert old.exists()
    assert len(list(ops["backups"].glob("receita-*.dump"))) == 2


def test_restore_of_dump_older_than_rotation_restores_it(ops: dict[str, Path]) -> None:
    """O backup de segurança não pode apagar (rotação) o dump que vai ser restaurado."""
    dump = old_dump(ops, "receita-20260101T031500Z.dump", "conteudo-do-backup-antigo")

    result = run(ops, "restore-db.sh", str(dump), "--yes")

    assert result.returncode == 0, result.stderr
    assert (ops["root"] / "restored").read_text() == "conteudo-do-backup-antigo"
    assert dump.exists()
    calls = (ops["root"] / "calls.log").read_text().splitlines()
    drop = next(i for i, c in enumerate(calls) if "DROP DATABASE" in c)
    restore = next(i for i, c in enumerate(calls) if "pg_restore -U" in c)
    backup = next(i for i, c in enumerate(calls) if "pg_dump" in c)
    assert backup < drop < restore
    assert calls[-1].endswith("up -d --wait")


def test_restore_accepts_path_relative_to_current_directory(ops: dict[str, Path]) -> None:
    elsewhere = ops["root"] / "copias"
    elsewhere.mkdir()
    (elsewhere / "receita-20261013T222250Z.dump").write_text("copia-local")

    result = run(ops, "restore-db.sh", "receita-20261013T222250Z.dump", "--yes", cwd=elsewhere)

    assert result.returncode == 0, result.stderr
    assert (ops["root"] / "restored").read_text() == "copia-local"


def test_restore_reports_missing_file(ops: dict[str, Path]) -> None:
    result = run(ops, "restore-db.sh", "nao-existe.dump", "--yes")

    assert result.returncode == 1
    assert "arquivo não encontrado: nao-existe.dump" in result.stderr
    assert not (ops["root"] / "calls.log").exists()
