import subprocess
import sys


def test_one_command_migrates_the_database_to_head():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
