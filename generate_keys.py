# File: generate_keys.py
# Note: You need to temporarily install pywebpush for this script only
# Run: pip install pywebpush

from pywebpush import vapid

private_key, public_key = vapid.generate_vapid_key_pair()

print("--- Save these as Environment Variables ---")
print(f"VAPID_PRIVATE_KEY={private_key}")
print(f"VAPID_PUBLIC_KEY={public_key}")