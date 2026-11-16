import fitz
from playbook_vector_extract import extract_page
PDF = 'uploads/bulk_imports/d125785a44474042b13589e9aadeca4f.pdf'
step = extract_page(PDF, 173)
print('Page 173 marks:', step['ink']['marks'])
print('Page 173 passes:', step['ink']['passes'])
for k, v in step['ink']['marks'].items():
    print(f'  {k}: {v}')