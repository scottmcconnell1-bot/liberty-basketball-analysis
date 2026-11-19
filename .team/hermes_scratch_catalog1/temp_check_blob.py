import fitz
doc = fitz.open(r'C:\Users\scott\Documents\Basketball\Plays\BLOB\Pages from Fast Scout Plays 2021-2022.pdf')
print(f'BLOB PDF pages: {doc.page_count}')
doc.close()