from queue import Queue
import asyncio
import threading
import multiprocessing

from inotify import INotify


class EventQueue:
    def __init__(self, queue=None):
        self.queue = queue or Queue

    def get(self):
        return self.queue.get()

    def put(self):
        return self.queue.put()

    async def aget(self):
        return self.queue.get()

    async def aput(self):
        return self.queue.put()

    def producer(self, fn, cancel):
        while not cancel.is_set():
            try:
                self.queue.put(fn())
            except BlockingIOError:
                continue

    async def asyncproducer(self, fn, cancel):
        while not cancel.is_set():
            try:
                self.queue.put(await fn())
            except BlockingIOError:
                await asyncio.sleep(0)

    def consumer(self, fn, cancel):
        while not cancel.is_set():
            fn(self.queue.get())

    async def asyncconsumer(self, fn, cancel):
        while not cancel.is_set():
            fn(await self.queue.aget())


def inotify_pipeline(
    ptransport, ctransport, queuecls, eventcls, ptaskcls, ctaskcls=None
):
    ctaskcls = ctaskcls or ptaskcls

    def in_pipe(fn, *paths):
        inotify = INotify()
        inotify.add(*paths)
        queue = EventQueue(queuecls())
        pcancel, ccancel = eventcls(), eventcls()
        producer = partial(eq.producer, inotify.read, pcancel)
        consumer = partial(eq.consumer, fn, ccancel)
        ptask = ptaskcls(producer)
        ctask = ctaskcls(consumer)
        return ptask, ctask, call_sequential(pcancel.set, ccancel.set)

    return in_pipe


as_coroutines = inotify_pipeline(
    EventQueue.asyncproducer,
    EventQueue.asyncconsumer,
    asyncio.Queue,
    asyncio.Event,
    lambda job: asyncio.create_task(job()),
)

as_threads = inotify_pipeline(
    EventQueue.producer,
    EventQueue.consumer,
    Queue,
    threading.Event,
    lambda job: threading.Thread(target=job, daemon=True),
)

as_coro_and_thread = inotify_pipeline(
    EventQueue.producer,
    EventQueue.asyncconsumer,
    multiprocessing.Queue,
    multiprocessing.Event,
    lambda producer: threading.Thread(target=producer, daemon=True),
    lambda consumer: asyncio.create_task(consumer()),
)


async def main():
    events = []
    tmp_dir = Path(tempfile.mkdtemp())
    w = watcher(tmp_dir) >> events.append
    print("MAIN :: Created watch")
    await w.start()
    await file_operations(tmp_dir)
    await asyncio.sleep(1)
    await w.stop()
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
