"""Try to load public Indonesian datasets using available Python libraries."""
import sys


# Check what's available
print("=" * 60)
print("CHECKING AVAILABLE LIBRARIES")
print("=" * 60)
print()

libraries = ['datasets', 'huggingface_hub', 'pandas', 'numpy', 'sklearn']
for lib in libraries:
    try:
        __import__(lib)
        print(f"✅ {lib}: available")
    except ImportError:
        print(f"❌ {lib}: not available")


print()
print("=" * 60)
print("PYTHON VERSION")
print("=" * 60)
import sys
print(f"Python: {sys.version}")
print(f"Path: {sys.executable}")


print()
print("=" * 60)
print("INSTALLED PACKAGES (relevant)")
print("=" * 60)
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "pip", "list"],
    capture_output=True,
    text=True
)
# Filter relevant packages
relevant = []
for line in result.stdout.split('\n'):
    for keyword in ['dataset', 'hugging', 'transform', 'pandas', 'numpy', 'sklearn', 'nltk', 'indon']:
        if keyword in line.lower():
            relevant.append(line)
            break

for line in relevant[:20]:
    print(line)
