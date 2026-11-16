import fitz
doc = fitz.open(r'C:\Users\scott\Documents\Basketball\Plays\Fast Scout Plays 2021-2022.pdf')
print(f'Master PDF pages: {doc.page_count}')
doc.close()