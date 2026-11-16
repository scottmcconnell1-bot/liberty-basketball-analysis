import fitz
doc = fitz.open(r'C:\Users\scott\Documents\liberty-basketball-analysis\dist\docs\imports\Fast Scout Plays 2021-2022.pdf')
print(f'Master PDF pages: {doc.page_count}')
doc.close()