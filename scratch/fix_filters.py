import re

filepath = 'templates/document_extraction.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

                                     
                                                    
content = re.sub(r'\|\s+(\w+)\s*:\s*', r'|\1:', content)

                                                              
content = re.sub(r'\|\s*(\w+)\s*:\s*\"([^\"]+)\"', r'|\1:"\2"', content)

                                          
content = re.sub(r'\|\s+(\w+)', r'|\1', content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Filters fixed.")
