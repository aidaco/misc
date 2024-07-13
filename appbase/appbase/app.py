from functools import cached_property

from appbase.config import Config
from appbase.database import DatabaseBase


class AppBase:
    @cached_property
    def config(self) -> Config:
        return Config()

    @cached_property
    def database(self) -> DatabaseBase:
        return DatabaseBase()
