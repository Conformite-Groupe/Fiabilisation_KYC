import os

file_path = r"c:\Users\mamsylla\OneDrive - BANK OF AFRICA(1)\Documents\Projets\2025\Plateforme notatio kyc v2\Fiabilisation_kyc - Copie\templates\pilotage_kyc.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

                                                                   
target = 'bg-amber-500'
if target in content:
    content = content.replace(target, 'bg-red-500')
    print("Replaced bg-amber-500 successfully.")
else:
    print("bg-amber-500 not found in file.")

with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
    f.write(content)
