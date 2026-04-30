#!/usr/bin/env python3
# Test script for connection history and discovery

import json
import sys
sys.path.insert(0, '/workspaces/PanicPilot')

# Test 1: Import modules
print("Testing imports...")
try:
    from connection_history import ConnectionHistory
    print("✓ connection_history imported successfully")
except Exception as e:
    print(f"✗ connection_history import failed: {e}")
    sys.exit(1)

try:
    from discovery import RoomBroadcaster, RoomListener
    print("✓ discovery imported successfully")
except Exception as e:
    print(f"✗ discovery import failed: {e}")
    sys.exit(1)

# Test 2: ConnectionHistory basic operations
print("\nTesting ConnectionHistory...")
try:
    hist = ConnectionHistory()
    print(f"✓ ConnectionHistory created (max {hist.MAX_ENTRIES} entries)")
    
    # Add some connections
    hist.add_or_update("192.168.1.42", "Simon's Room", success=True)
    hist.add_or_update("192.168.1.50", "Alice's Setup", success=True)
    print("✓ Added 2 connections")
    
    # Get recent
    recent = hist.get_recent(limit=5)
    print(f"✓ Got {len(recent)} recent connections")
    
    # Find by IP
    conn = hist.find_by_ip("192.168.1.42")
    if conn:
        print(f"✓ Found connection: {conn['username']}")
    
except Exception as e:
    print(f"✗ ConnectionHistory test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: RoomBroadcaster and Listener
print("\nTesting RoomBroadcaster and RoomListener...")
try:
    broadcaster = RoomBroadcaster("Test Room", tcp_port=54321)
    listener = RoomListener()
    print("✓ Broadcaster and Listener created")
    
    # Note: Can't fully test without network setup
    # but we can verify they're instantiable
    
except Exception as e:
    print(f"✗ Discovery test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ All tests passed!")
