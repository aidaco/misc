def nmerge():
    import warnings
    import re
    from pathlib import Path
    from PyPDF2 import PdfFileReader, PdfFileWriter
    warnings.filterwarnings('ignore')
    o = PdfFileWriter()
    pdfs = Path().glob('*.pdf')
    matches = lambda s: re.match('(\d+)[^\d].*', str(s)) is not None
    num = lambda s: int(re.match('(\d+)[^\d].*', str(s)).group(1))
    for f in sorted((p for p in pdfs if matches(p)), key=num):
        print(f)
        for pg in PdfFileReader(f).pages:
            o.addPage(pg)
    o.write(open('nmerged.pdf', 'wb'))

if __name__ == '__main__':
    nmerge()
    
