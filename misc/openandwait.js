let asyncMapElements = async (asyncFn, selector) => {
  let elems = document.querySelectorAll(selector)
  for (let elem of elems) {
    await asyncFn(elem)
  }
}

let openLinkAndWait = async (elem) => {
  let url = elem.href
  let handle = window.open(url)
  while (!handle.closed) {
    await new Promise(r => setTimeout(r, 1000))
  }
}

let unsignedDocumentSelector = '.snr-doc-card:not(:has(.snr-status-label--success)) .snr-doc-card__name'

let signAllUnsigned = () => asyncMapElements(openLinkAndWait, unsignedDocumentSelector)

document.addEventListener('keydown', (e)=>{
  if (e.ctrlKey && e.code == 'KeyS') {
    signAllUnsigned()
  }
})
