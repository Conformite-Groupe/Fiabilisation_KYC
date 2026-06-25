import os
import sys
import django
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kyc_project.settings')
django.setup()

from kyc.models import Kyc_pp
from django.db.models import Q

start = time.time()
qs = Kyc_pp.objects.filter(Q(CLIENT__regex=r'^.$'))
count = qs.count()
end = time.time()
print(f"REGEX Count: {count}, Time: {end - start:.2f}s")

start = time.time()
qs = Kyc_pp.objects.filter(Q(CLIENT__isnull=True) | Q(CLIENT=""))
count = qs.count()
end = time.time()
print(f"EMPTY Count: {count}, Time: {end - start:.2f}s")
