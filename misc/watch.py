from asyncio.events import get_running_loop
from pathlib import Path
from collections import deque
import tempfile
import asyncio

from inotify import INotify, INEvent


class watch(INotify):
    def __init__(
        self,
        *paths: Path,
        chunked: bool = False,
        chunk_size: int = 4096,
        mask: int = INEvent.all(),
    ):
        self.paths = paths
        self.mask = mask
        self.chunked = chunked
        self.chunk_size = chunk_size
        if chunked:
            self.msgs: deque = deque()

    def __enter__(self):
        super().__init__(self, *self.paths, mask=self.mask)
        return self

    async def __aenter__(self):
        super().__init__(*self.paths, mask=self.mask)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __iter__(self):
        return self

    def __aiter__(self):
        return self

    def __next__(self):
        while not self.closed:
            try:
                if self.chunked:
                    if not self.msgs:
                        self.msgs.extend(
                            self.read(chunked=True, chunk_size=self.chunk_size)
                        )
                    return self.msgs.pop(0)
                return self.read()
            except BlockingIOError:
                continue
        raise StopIteration

    async def __anext__(self):
        while not self.closed:
            try:
                if self.chunked:
                    if not self.msgs:
                        self.msgs.extend(
                            self.read(chunked=True, chunk_size=self.chunk_size)
                        )
                    return self.msgs.pop(0)
                return self.read()
            except BlockingIOError:
                await asyncio.sleep(0)
        raise StopAsyncIteration


def watcher(
    *paths, mask: int = INEvent.all(), chunked: bool = False, chunk_size: int = 4096
):
    with watch(*paths, mask=mask, chunked=chunked, chunk_size=chunk_size) as w:
        for msg in w:
            yield (msg)


async def asyncwatcher(
    *paths, mask: int = INEvent.all(), chunked: bool = False, chunk_size: int = 4096
):
    try:
        async with watch(
            *paths, mask=mask, chunked=chunked, chunk_size=chunk_size
        ) as w:
            print("ASYNCWATCHER :: WATCHING")
            async for msg in w:
                print("ASYNCWATCHER :: RECVD")
                yield msg
            print("ASYNCWATCHER :: EXITING")
    except asyncio.CancelledError:
        print("ASNYNCWATCHER :: DONE")


async def main():
    loop = asyncio.get_running_loop()
    events = []
    tmp_dir = Path(tempfile.mkdtemp())

    async def wcoro():
        try:
            print("WCORO :: STARTED")
            async for event in asyncwatcher(tmp_dir):
                print("WCORO :: RECVD")
                events.append(event)
        except asyncio.CancelledError:
            print("WCORO :: DONE")

    task = asyncio.gather(wcoro(), file_operations(tmp_dir))
    await asyncio.sleep(2)
    task.cancel()
    await task
    print("MAIN :: Stopped watcher")
    print(f"MAIN :: Received Events:")
    print("", *(str(event) for event in events), sep="\n\t")


async def file_operations(dpath):
    print("FILEOPS :: Started")
    with open(dpath / "test1", "w") as f:
        f.write("Hello world")
    (dpath / "test1").unlink()
    (dpath / "test2").touch()
    (dpath / "test2").unlink()
    print("FILEOPS :: Completed")


if __name__ == "__main__":
    asyncio.run(main())
