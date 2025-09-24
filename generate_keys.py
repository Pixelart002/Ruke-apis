# File: generate_keys.py
# Run this once to get your keys
# You may need to run: pip install pywebpush

from pywebpush import vapid

private_key, public_key = vapid.generate_vapid_key_pair()

print("--- Save these as Environment Variables ---")
print(f"VAPID_PRIVATE_KEY={private_key}")
print(f"VAPID_PUBLIC_KEY={public_key}")