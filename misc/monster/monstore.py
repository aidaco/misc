import sqlite3
import contextlib
import typing
import dataclasses
import datetime
import psutil


SQLITE3_OPTIMIZE_CONNECT = """
pragma journal_mode = WAL;
pragma synchronous = normal;
pragma temp_store = memory;
pragma mmap_size = 30000000000;
pragma foreign_keys = on;
pragma auto_vacuum = incremental;
"""

SQLITE3_CONFIGURE_CONNECT = """
pragma foreign_keys = on;
"""

SQLITE3_OPTIMIZE_CLOSE = """
pragma vacuum;
pragma incremental_vacuum;
pragma optimize;
"""

SQLITE3_ENSURE_TABLES = """
create table if not exists measurements (
  id integer primary key autoincrement,
  timestamp datetime default current_timestamp,

  cpu_percent real,
  load_1s real,
  load_5s real,
  load_15s real,

  memory_total integer,
  memory_used integer,
  memory_free integer,
  memory_percent real,

  swap_total integer,
  swap_used integer,
  swap_free integer,
  swap_percent real,

  disk_total integer,
  disk_used integer,
  disk_free integer,
  disk_percent real,

  disk_read_bytes integer,
  disk_read_bytes_sec real,
  disk_write_bytes integer,
  disk_write_bytes_sec real,

  network_send_bytes integer,
  network_send_bytes_sec real,
  network_send_errors integer,
  network_send_drops integer,
  network_receive_bytes integer,
  network_receive_bytes_sec real,
  network_receive_errors integer,
  network_receive_drops integer,
);
"""


@contextlib.contextmanager
def database(uri: str, **kwargs) -> typing.Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(uri, **kwargs)
    try:
        connection.executescript(SQLITE3_OPTIMIZE_CONNECT)
        connection.executescript(SQLITE3_CONFIGURE_CONNECT)
        connection.executescript(SQLITE3_ENSURE_TABLES)
        yield connection
    finally:
        try:
            connection.executescript(SQLITE3_OPTIMIZE_CLOSE)
        finally:
            connection.close()


def log_usage(conn):
    cpu_percent = psutil.cpu_percent()
    load_avg = psutil.getloadavg()
    mem_stat = psutil.virtual_memory()
    swap_stat = psutil.swap_memory()
    disk_usage = psutil.disk_usage("/")
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters()

    conn.execute(
        """
        insert into measurements (
            cpu_percent,
            load_1s, load_5s, load_15s,
            memory_total, memory_used, memory_free, memory_percent,
            swap_total, swap_used, swap_free, swap_percent,
            disk_total, disk_used, disk_free, disk_percent,
            disk_read_bytes, disk_read_bytes_sec, disk_write_bytes, disk_write_bytes_sec,
            network_send_bytes, network_send_bytes_sec, network_send_errors, network_send_drops,
            network_receive_bytes, network_receive_bytes_sec, network_receive_errors, network_receive_drops
        ) values (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        );
    """,
        (
            cpu_percent,
            load_avg[0],
            load_avg[1],
            load_avg[2],
            mem_stat.total,
            mem_stat.used,
            mem_stat.free,
            mem_stat.percent,
            swap_stat.total,
            swap_stat.used,
            swap_stat.free,
            swap_stat.percent,
            disk_usage.total,
            disk_usage.used,
            disk_usage.free,
            disk_usage.percent,
            disk_io.read_bytes,
            disk_io.read_time,
            disk_io.write_bytes,
            disk_io.write_time,
            net_io.bytes_sent,
            net_io.packets_sent,
            net_io.errout,
            net_io.dropout,
            net_io.bytes_recv,
            net_io.packets_recv,
            net_io.errin,
            net_io.dropin,
        ),
    )
    conn.commit()
