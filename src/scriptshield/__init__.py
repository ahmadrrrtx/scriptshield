"""ScriptShield — orthography-disentangled safety steering for Urdu / Roman Urdu.

The package imports cleanly WITHOUT torch. Heavy model code lives in
``scriptshield.models`` and ``scriptshield.steering.safetune_adapter`` and is
imported lazily so that the local 2 GB environment can run schema validation,
linear algebra and statistics.
"""
__version__ = "0.0.1"
