import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every service directory has its own config.py/main.py/models.py, so we
# can't just dump all three on sys.path at once (name collisions + stale
# module caching). Instead, each test asks for a service module via this
# fixture, which resets sys.path/sys.modules to that service's directory
# before importing.
_SHARED_MODULE_NAMES = ["config", "main", "models", "ollama_client", "embeddings", "vector_store", "chunking", "services", "services.orchestrator"]


@pytest.fixture
def import_fresh():
    original_path = list(sys.path)

    def _import(service: str, module_name: str):
        service_dir = os.path.join(ROOT, service)
        for name in _SHARED_MODULE_NAMES:
            sys.modules.pop(name, None)
        sys.path = [service_dir] + original_path
        return importlib.import_module(module_name)

    yield _import

    for name in _SHARED_MODULE_NAMES:
        sys.modules.pop(name, None)
    sys.path = original_path
