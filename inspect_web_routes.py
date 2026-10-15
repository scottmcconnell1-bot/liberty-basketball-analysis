import os
import re

def find_review_routes():
    """
    Scans project python files to locate stat book review route definitions and handlers.
    """
    print("=" * 70)
    print("       WEB ROUTE INSPECTION UTILITY       ")
    print("=" * 70)

    project_dir = r"C:\Users\scott\Documents\liberty-basketball-analysis"
    python_files = [f for f in os.listdir(project_dir) if f.endswith(".py")]

    found_routes = False

    for file_name in python_files:
        file_path = os.path.join(project_dir, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Search for routes containing 'stat-books' or 'review'
            if "stat-books" in content or "review" in content:
                print(f"\nFound references in file: {file_name}")
                matches = re.findall(r'@.*route\(.*\)', content)
                for match in matches:
                    print(f"  -> Route definition: {match}")
                    found_routes = True
        except Exception as e:
            print(f"Error reading {file_name}: {e}")

    if not found_routes:
        print("\n[INFO] No explicit Flask/FastAPI route decorators matching 'stat-books' found in root .py files.")
        print("Checking subdirectories...")

    print("=" * 70)

if __name__ == "__main__":
    find_review_routes()