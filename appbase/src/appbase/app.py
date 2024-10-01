from pathlib import Path

from appbase.config import Config, ConfigConfigType, configconfig as _configconfig
from appbase.database import Database


class App:
    def __init__(
        self,
        name: str,
        conf: Config | None = None,
        confconf: ConfigConfigType | None = None,
        uri: str | Path | None = None,
        database: Database | None = None,
    ) -> None:
        self.name: str = name
        self._config: Config | None = conf
        self._configconfig: ConfigConfigType | None = confconf
        self._uri: str | Path | None = uri
        self._database: Database | None = database

    @property
    def configconfig(self) -> ConfigConfigType:
        if not self._configconfig:
            self._configconfig = _configconfig(self.name)
        return self._configconfig

    @property
    def config(self) -> Config:
        if not self._config:
            self._config = self.configconfig.load()
        return self._config

    @property
    def uri(self) -> str | Path:
        return self._uri or (Path.cwd() / f"{self.name}.sqlite3")

    @property
    def database(self) -> Database:
        if not self._database:
            self._database = Database.connect(self.uri)
        return self._database
