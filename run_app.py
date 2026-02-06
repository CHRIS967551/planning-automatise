#!/usr/bin/env python3
import sys
try:
    print("Importing app...")
    import app
    print("OK - Import OK")
    print("Starting Flask...")
    app.app.run(debug=True)
except Exception as e:
    import traceback
    print(f"ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
