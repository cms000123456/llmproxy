#!/usr/bin/env python3
"""Run all tests for the LLM Proxy project."""

import importlib
import sys

# Test modules
TEST_MODULES = [
    "test_cache",
    "test_tools",
    "test_metrics",
    "test_filters",
    "test_compressors",
    "test_config",
    "test_integration",
    # "test_server",  # Async tests - run separately
]


def run_test_module(module_name):
    """Run a test module and return success status."""
    print(f"\n{'=' * 60}")
    print(f"Running {module_name}")
    print("=" * 60)

    try:
        # Import and run the module
        module = importlib.import_module(module_name)

        # Run if it has a main block or explicit run function
        if hasattr(module, "run_all_tests"):
            module.run_all_tests()

        return True
    except Exception as e:
        print(f"❌ {module_name} failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("LLM Proxy Test Suite")
    print("=" * 60)

    passed = 0
    failed = 0

    for module_name in TEST_MODULES:
        if run_test_module(module_name):
            passed += 1
        else:
            failed += 1

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Passed: {passed}/{len(TEST_MODULES)}")
    print(f"Failed: {failed}/{len(TEST_MODULES)}")

    if failed == 0:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {failed} test module(s) failed")
        return 1


if __name__ == "__main__":
    # Add parent directory to path for imports
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    sys.exit(main())
