# Generated manually to fix PostgreSQL collation version mismatch

from django.db import migrations


def fix_collation_version(apps, schema_editor):
    """
    Fix PostgreSQL collation version mismatch by refreshing collation version.
    This migration addresses the warning:
    'database has a collation version mismatch'
    """
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            # Get the current database name
            cursor.execute("SELECT current_database();")
            db_name = cursor.fetchone()[0]

            # Refresh collation version for current database
            try:
                cursor.execute(f"ALTER DATABASE {db_name} REFRESH COLLATION VERSION;")
                print(
                    f"Successfully refreshed collation version for database: {db_name}"
                )
            except Exception as e:
                print(f"Warning: Could not refresh collation for {db_name}: {e}")

            # Also try to refresh template1 (requires superuser privileges)
            try:
                cursor.execute("ALTER DATABASE template1 REFRESH COLLATION VERSION;")
                print("Successfully refreshed collation version for template1")
            except Exception as e:
                print(f"Warning: Could not refresh collation for template1: {e}")
                print("This is normal if you don't have superuser privileges")

            # Try to refresh postgres database (requires superuser privileges)
            try:
                cursor.execute("ALTER DATABASE postgres REFRESH COLLATION VERSION;")
                print("Successfully refreshed collation version for postgres")
            except Exception as e:
                print(f"Warning: Could not refresh collation for postgres: {e}")
                print("This is normal if you don't have superuser privileges")


def reverse_fix_collation_version(apps, schema_editor):
    """
    This migration cannot be reversed as it only updates metadata.
    """
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("task_processor", "0011_alter_item_estimated_duration"),
    ]

    operations = [
        migrations.RunPython(
            fix_collation_version,
            reverse_fix_collation_version,
        ),
    ]
