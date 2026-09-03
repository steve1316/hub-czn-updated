import os

# Turn the API token check off for the whole suite. An explicit empty value means "no token".
# This has to happen before api.main is imported, which is why it sits in the root conftest.
os.environ.setdefault("HUB_CZN_API_TOKEN", "")
