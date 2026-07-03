from .adapter import BAASAdapter
from .profile import BAASProfile, PROFILES, list_profiles, get_profile

__all__ = ["BAASAdapter", "BAASProfile", "PROFILES", "list_profiles", "get_profile"]

# Auto-register with the adapter registry
from adapter.registry import AdapterRegistry
AdapterRegistry.register("baas", BAASAdapter)
