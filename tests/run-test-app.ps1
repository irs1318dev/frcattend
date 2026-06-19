# Start the IRSattend with a test database.

# The test_attendance_table test generates a sqlite database file with test data.
pytest test_database.py::test_attendance_table

# Run the app in dev mode.
textual run --dev -c "attend app -d output/testdatabase.db -c data/private/test-config.toml"