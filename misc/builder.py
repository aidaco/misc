from subprocess import run
from tempfile import TemporaryDirectory
from dataclasses import dataclass
from contextlib import chdir
from shutil import rmtree, copytree, copy
from pathlib import Path
from itertools import chain
from rich import print
from typer import Typer
import zipapp


def shell(cmd):
    return run([cmd], shell=True)


def rmdir(path):
    try:
        rmtree(path)
    except Exception as e:
        print(e)


def is_pypackage(path):
    return not path.is_dir() and (path / '__init__.py').exists()


@dataclass
class Project:
    packages: list[Path]
    config_files: list[Path]
    cache_dirs: list[Path]
    build_dirs: list[Path]
    dist_dirs: list[Path]

    @classmethod
    def default(cls):
        return cls(
            packages=[path for path in Path.cwd() if is_pypackage(path)],
            config_files=['pyproject.toml'],
            cache_dirs=[p for p in Path.cwd().rglob("*cache*") if p.name.startswith(('.', '__'))],
            build_dirs=list(Path.cwd().rglob('build')),
            dist_dirs=list(Path.cwd().rglob('dist'))
        )

    def fix(self):
        for target in chain(*self.pysources):
            shell(f'python -m black {target}')
            shell(f'python -m isort{target}')
            shell(f'python -m ruff {target} --fix')
            shell(f'python -m mypy {target}')

    def remove_caches(self):
        for dir in self.cache_dirs:
            rmdir(dir)

    def remove_build(self):
        for dir in self.build_dirs:
            rmdir(dir)

    def remove_dist(self):
        for dir in self.dist_dirs:
            rmdir(dir)

    def build_pyz(self, output: Path):
        with TemporaryDirectory() as tmp:
            ptmp = Path(tmp.name)
            for config in self.config_files:
                copy(config, ptmp/config.name)
            for dist in self.dist_dirs:
                copytree(dist, ptmp/dist.name)
            zipapp.create_archive(
                ptmp,
                output,
                interpreter='/usr/bin/env python',
            )


def make_app():
    cli = Typer()
    cli.command()
