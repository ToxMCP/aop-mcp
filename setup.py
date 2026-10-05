"""Stage canonical runtime data into the wheel without duplicating source files."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self) -> None:
        super().run()
        root = Path(__file__).parent
        for source, destination in (
            ("docs/contracts/schemas", "schemas"),
            ("tests/golden/read", "fixtures/read"),
        ):
            self.copy_tree(
                str(root / source),
                str(Path(self.build_lib) / "src" / "_resources" / destination),
            )


setup(cmdclass={"build_py": BuildPy})
