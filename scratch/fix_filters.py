import re

filepath = 'templates/document_extraction.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix spacing around filter pipelines
# e.g., | yesno: "true,false" -> |yesno:"true,false"
content = re.sub(r'\|\s+(\w+)\s*:\s*', r'|\1:', content)

# And specifically |yesno: "true,false" -> |yesno:"true,false"
content = re.sub(r'\|\s*(\w+)\s*:\s*\"([^\"]+)\"', r'|\1:"\2"', content)

# Fix filter without args like | pluralize
content = re.sub(r'\|\s+(\w+)', r'|\1', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Filters fixed.")
