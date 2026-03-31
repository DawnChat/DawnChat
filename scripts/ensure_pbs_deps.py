import os
import sys
import re

def normalize_pkg_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()

def parse_poetry_lock(lock_content):
    """
    Parse poetry.lock content to extract package versions.
    Returns a dictionary {package_name: version}.
    """
    versions = {}
    lines = lock_content.splitlines()
    in_package = False
    current_package = None
    
    for line in lines:
        line = line.strip()
        if line == "[[package]]":
            in_package = True
            current_package = None
            continue
            
        if in_package:
            if line.startswith('name = "'):
                current_package = line.split('"')[1]
            elif line.startswith('version = "'):
                version = line.split('"')[1]
                if current_package:
                    versions[normalize_pkg_name(current_package)] = version
                    # We don't break here because we might need to parse more fields if needed, 
                    # but for now we just need the version. 
                    # Note: poetry.lock might have multiple entries for same package? 
                    # Usually not for standard deps, but possible. 
                    # We take the last one or first? usually they are same version.
    return versions

def parse_requirements_line(line):
    """
    Parse a requirements.txt line.
    Returns (package_name, markers_part, original_line_content)
    """
    # Remove whitespace
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return None, None, line

    # Split comments/markers
    parts = stripped.split(';', 1)
    requirement_part = parts[0].strip()
    markers_part = f" ; {parts[1].strip()}" if len(parts) > 1 else ""

    # Extract package name. 
    # Valid characters: A-Z, a-z, 0-9, ., _, -
    # It must start with a letter or number.
    # We stop at the first character that is NOT part of the name (e.g. =, >, <, !, ~, space)
    match = re.match(r'^([a-zA-Z0-9\-_.]+)', requirement_part)
    if match:
        package_name = match.group(1)
        return package_name, markers_part, line
    
    return None, None, line

def main():
    if len(sys.argv) != 3:
        print("Usage: python ensure_pbs_deps.py <poetry.lock_path> <requirements.txt_path>")
        sys.exit(1)

    lock_path = sys.argv[1]
    req_path = sys.argv[2]

    if not os.path.exists(lock_path):
        print(f"Error: {lock_path} not found")
        sys.exit(1)

    if not os.path.exists(req_path):
        print(f"Error: {req_path} not found")
        sys.exit(1)

    print(f"Reading lock file: {lock_path}")
    try:
        with open(lock_path, 'r', encoding='utf-8') as f:
            lock_content = f.read()
    except Exception as e:
        print(f"Error reading lock file: {e}")
        sys.exit(1)

    lock_versions = parse_poetry_lock(lock_content)
    print(f"Found {len(lock_versions)} packages in lock file.")

    print(f"Reading requirements file: {req_path}")
    try:
        with open(req_path, 'r', encoding='utf-8') as f:
            req_lines = f.readlines()
    except Exception as e:
        print(f"Error reading requirements file: {e}")
        sys.exit(1)

    new_lines = []
    updated_count = 0
    
    for line in req_lines:
        pkg_name, markers, original = parse_requirements_line(line)
        
        if pkg_name:
            # Normalize package name (lowercase for comparison)
            pkg_key = normalize_pkg_name(pkg_name)
            
            if pkg_key in lock_versions:
                lock_ver = lock_versions[pkg_key]
                
                # Construct new line
                new_line = f"{pkg_name}=={lock_ver}{markers}\n"
                
                # Check if it's different from original (ignoring whitespace differences)
                # We check if the version part in original contains ==lock_ver
                # This is a heuristic. Simpler to just check string equality of cleaned lines.
                if new_line.strip() != line.strip():
                    # print(f"Updating {pkg_name}: {line.strip()} -> {new_line.strip()}")
                    new_lines.append(new_line)
                    updated_count += 1
                else:
                    new_lines.append(line)
            else:
                print(f"Warning: Package '{pkg_name}' found in requirements.txt but NOT in poetry.lock. Skipping.")
                new_lines.append(line)
        else:
            new_lines.append(line)

    if updated_count > 0:
        print(f"Updating {updated_count} dependencies in {req_path}...")
        try:
            with open(req_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print("requirements.txt updated successfully.")
        except Exception as e:
            print(f"Error writing requirements file: {e}")
            sys.exit(1)
    else:
        print("No changes needed. requirements.txt is up to date.")

if __name__ == "__main__":
    main()
