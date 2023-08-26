from datetime import datetime
from dataclasses import dataclass


@dataclass
class History:
    id: str
    time: datetime
    table: str
    table_id: str
    old: str
    new: str
