import os
env = os.getenv('DJANGO_ENV','dev').lower()

if env == "prod":
    from .prod import *
if env == "dev":
    from .dev import *