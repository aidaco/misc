from pyppeteer import launch
from pyppeteer.page import Page
import typing
import asyncio
import itertools


async def run(domains: typing.Iterator[str]):
    browser, page = await open_browser()
    scraper = GenXYZBulkSearchScraper(page)
    await show_all(scraper.search(domains))
    await close_browser(browser, page)


async def format(results):
    async for domain, price in results:
        price = f'{price:.2f}' if price else '-'
        yield f"{domain: <30}${price: >10}"


async def available(results):
    async for domain, price in results:
        if price:
            yield f"{domain: <30}${price: >10}"


async def open_browser():
    browser = await launch(
        headless=True, dumpio=False, args=["--disable-gpu", "--no-sandbox"]
    )
    page = await browser.newPage()
    return browser, page


async def close_browser(browser, page):
    await page.close()
    await browser.close()


class GenXYZBulkSearchScraper:
    URL = "https://gen.xyz/register#"
    BATCH_SIZE = 50

    def __init__(self, page: Page):
        self.page = page

    async def search(self, domains: typing.Iterator[str], batch_delay: float = 0.5):
        await self.navigate()
        await self.toggle_bulk()
        for batch in itertools.batched(domains, self.BATCH_SIZE):
            await self.set_text('\n'.join(batch))
            await self.submit()
            results = (await self.available()) | (await self.unavailable())
            for result in results:
                yield result
            await asyncio.sleep(batch_delay)

    async def navigate(self):
        current_url = await self.page.evaluate("window.location.href")
        if current_url != self.URL:
            await self.page.goto(self.URL, waitUntil=["load", 'networkidle0'])

    async def set_text(self, text: str):
        await self.page.Jeval("textarea#domainBulk", "(e, s) => e.value = s", text)

    async def toggle_bulk(self):
        bulk_toggle = await self.page.querySelector("a.bulk-search")
        if await bulk_toggle.boundingBox():
            await bulk_toggle.click()

    async def submit(self):
        submit = await self.page.querySelector("button#bulkSearchGo")
        await submit.click()

    async def available(self):
        available = await self.page.waitFor("#bulkSearchAvailable")

        domains = await available.JJeval('.bulk-domain', '(arr) => arr.map((e) => e.innerText.trim())')
        prices = await available.JJeval(
            '.bulk-price',
            r'(arr) => arr.map((e) => e.innerText.trim().match(/\$(\d+(\.\d\d)?)/)[1]).map(parseFloat)'
        )
        return set(zip(domains, prices))

    async def unavailable(self):
        unavailable = await self.page.waitFor("#bulkSearchNotAvailable")
        return {
            (domain, None)
            for domain in await unavailable.JJeval(
                'li > span', '(arr) => arr.map((e) => e.innerText)'
            )
        }
