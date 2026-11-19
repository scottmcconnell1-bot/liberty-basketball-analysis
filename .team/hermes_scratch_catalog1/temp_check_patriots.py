import fitz
doc = fitz.open(r'C:\Users\scott\Documents\Basketball\Plays\Patriots Playbook.pdf')
print(f'Patriots Playbook pages: {doc.page_count}')
for i in range(min(5, doc.page_count)):
    page = doc[i]
    text = page.get_text()
    print(f'Page {i+1}: {text[:200]}')
doc.close()