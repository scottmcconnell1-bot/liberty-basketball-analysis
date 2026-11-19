content = open('/mnt/c/Users/scott/Documents/liberty-playbook/.team/specs/12_numbered_lines_plan.md').read()

# Forbidden strings
forbidden = ["1-206", "Basketball\\Plays\\Fast Scout", "file://", "No server required"]
print("=== FORBIDDEN STRINGS (must NOT contain) ===")
for s in forbidden:
    found = s in content
    print(f"  '{s}': {'FOUND - VIOLATION' if found else 'NOT FOUND - OK'}")

# Required strings
required = ["dist\\docs\\imports", "PUT /api/playbook/choreography", "source_image", "mode=ro", "Liberty_Playbook_TestDB"]
print()
print("=== REQUIRED STRINGS (must contain) ===")
for s in required:
    found = s in content
    print(f"  '{s}': {'FOUND - OK' if found else 'MISSING - VIOLATION'}")

# Also check for '207-380' which should be removed
print(f"  '207-380': {'FOUND - should be removed' if '207-380' in content else 'NOT FOUND - OK'}")