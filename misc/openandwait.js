openAndWait = async (url) => {
  let handle = window.open(url)
  while (!handle.closed) {
    await new Promise(r => setTimeout(r, 1000))
  }
}

for (let elem of Array.from(document.getElementsByClassName("snr-doc-card__name"))) {
  await openAndWait(elem.href)
}
